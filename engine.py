"""Game engine for Word Battler — pure logic, no PyGame dependencies."""

import random
import os
import datetime
from data import (
    LETTER_VALUES, STARTING_DECK, HAND_SIZE, MAX_HP,
    ENCOUNTERS_BEFORE_BOSS, ROUNDS_PER_ENCOUNTER, ARCHETYPES,
    ENCOUNTER_POOL, BOSS_POOL,
    MODIFIERS, BOSS_MODIFIERS,
    POTIONS, POTION_KEYS, ACCESSORIES, ACCESSORY_KEYS,
    NOUN_POOL, STARTING_NOUNS, ENCOUNTER_HP, NOUN_DRAW_COUNT,
)
from openai_scorer import score_word, generate_story_round, generate_approaches


class GameEngine:
    """Core game state and logic.  No rendering or I/O."""

    def __init__(self, archetype_key: str):
        # ── Game session ID (for OpenAI log files) ──────────────────────
        now = datetime.datetime.now()
        self.game_id = now.strftime("game_%Y%m%d_%H%M%S")

        # ── Dictionary ──────────────────────────────────────────────────
        self._valid_words: set[str] = set()
        self._words_by_length: dict[int, set[str]] = {}
        self._load_dictionary()

        # ── Archetype ────────────────────────────────────────────────────
        arch = ARCHETYPES[archetype_key]
        self.archetype_key = archetype_key
        self.archetype_name = arch["name"]
        self.aggressive_bonus = arch["aggressive_bonus"]
        self.hand_bonus = arch["hand_bonus"]
        self.wildcard_bonus = arch["wildcard_bonus"]

        # ── Player state ────────────────────────────────────────────────
        self.hp = MAX_HP
        self.max_hp = MAX_HP
        self._base_hand_size = HAND_SIZE + self.hand_bonus
        self.encounters_cleared = 0

        # ── Current encounter ───────────────────────────────────────────
        self.current_encounter: dict | None = None
        self.current_approach: str | None = None
        self.current_requirement: int = 0
        self.current_round: int = 1
        self.rounds_per_encounter: int = ROUNDS_PER_ENCOUNTER

        # ── Deck ────────────────────────────────────────────────────────
        self._deck: list[str] = list(STARTING_DECK)
        self._discard: list[str] = []
        self._hand: list[str] = []

        # ── Accessories (must init before drawing cards — hand_size depends on it)
        self._accessories: list[str] = []
        self._init_accessories()

        # Apply vitality_core bonus to max_hp
        if "vitality_core" in self._accessories:
            self.max_hp += 3
            self.hp = self.max_hp  # heal to new max

        # ── Potions ─────────────────────────────────────────────────────
        self._potions: list[str] = []
        self._init_potions()

        # ── Played words (for OpenAI uniqueness scoring) ───────────────
        self._played_words: list[str] = []

        # ── Story generation tracking ─────────────────────────────────
        self._story_so_far: list[dict] = []       # {flavor, prompt, word} per round
        self._generated_round_data: dict | None = None  # generated flavor/prompt for current round
        self._generated_approaches: dict | None = None  # generated approach descriptions

        # ── Noun-round tracking ──────────────────────────────────────
        # Exactly 1 of every 3 rounds is a noun round; determined per encounter.
        # Weighted: 25% round 1, 50% round 2, 100% round 3
        self._noun_round: int = 0  # 1, 2, or 3 — set when encounter starts

        # ── Noun deck ─────────────────────────────────────────────────
        self._noun_deck: list[dict] = list(STARTING_NOUNS)
        self._noun_hand: list[dict] = []   # 3 noun cards drawn for noun round
        self._chosen_noun: dict | None = None  # the noun the player picked this round

        # ── Encounter HP ──────────────────────────────────────────────
        self._encounter_hp: int = 0
        self._encounter_max_hp: int = 0
        self._bonus_round: bool = False  # True when in the 4th bonus round

        random.shuffle(self._deck)
        self._draw_cards(self.hand_size)

        # ── Encounter queue ─────────────────────────────────────────────
        self._encounter_queue: list[dict] = []
        self._build_encounter_queue()

    # ── Dictionary loading ───────────────────────────────────────────────

    def _load_dictionary(self):
        """Load words_alpha.txt into a set and a by-length lookup."""
        dict_path = os.path.join(os.path.dirname(__file__), "words_alpha.txt")
        with open(dict_path, "r", encoding="utf-8") as f:
            for line in f:
                word = line.strip().lower()
                if word:
                    self._valid_words.add(word)
                    length = len(word)
                    self._words_by_length.setdefault(length, set()).add(word)

    # ── Encounter queue ──────────────────────────────────────────────────

    def _build_encounter_queue(self):
        """Shuffle the pool, take the first N, then append a random boss."""
        pool = list(ENCOUNTER_POOL)
        random.shuffle(pool)
        self._encounter_queue = pool[:ENCOUNTERS_BEFORE_BOSS]
        boss = random.choice(BOSS_POOL)
        self._encounter_queue.append(dict(boss))  # copy so we don't mutate the pool

    # ── Potions ──────────────────────────────────────────────────────────

    def _init_potions(self):
        """Start the game with 3 random potions."""
        keys = list(POTION_KEYS)
        random.shuffle(keys)
        self._potions = keys[:3]

    def use_potion(self, index: int) -> dict | None:
        """Use the potion at *index* (0-2). Returns effect info or None."""
        if index < 0 or index >= len(self._potions):
            return None
        key = self._potions.pop(index)
        potion = POTIONS[key]
        effect = potion["effect"]

        if effect == "shuffle":
            # Shuffle hand into deck and redraw to previous hand count
            previous_count = len(self._hand)
            self._deck.extend(self._hand)
            self._hand = []
            random.shuffle(self._deck)
            self._draw_cards(previous_count)
        elif effect == "healing":
            self.hp = min(self.max_hp, self.hp + 5)
        elif effect == "wildcard":
            # Add a temporary wildcard to hand (doesn't go to deck/discard)
            self._hand.append("*")

        return {"key": key, "name": potion["name"], "effect": effect}

    def _maybe_gain_potion(self):
        """50% chance to gain a random potion after an encounter."""
        if random.random() < 0.5:
            key = random.choice(POTION_KEYS)
            self._potions.append(key)

    # ── Accessories ──────────────────────────────────────────────────────

    def _init_accessories(self):
        """Start the game with 1 random accessory."""
        self._accessories = [random.choice(ACCESSORY_KEYS)]

    def _gain_random_accessory(self):
        """Add a random accessory (no duplicates)."""
        available = [k for k in ACCESSORY_KEYS if k not in self._accessories]
        if available:
            self._accessories.append(random.choice(available))

    def _gain_random_noun(self):
        """Add a random noun card to the noun deck (no duplicates by word)."""
        existing_words = {n["word"] for n in self._noun_deck}
        available = [n for n in NOUN_POOL if n["word"] not in existing_words]
        if available:
            self._noun_deck.append(random.choice(available))

    def draw_noun_hand(self):
        """Draw 3 noun cards from the noun deck for a noun round."""
        self._noun_hand = []
        available = list(self._noun_deck)
        random.shuffle(available)
        self._noun_hand = available[:NOUN_DRAW_COUNT]

    def choose_noun(self, index: int) -> dict | None:
        """Choose a noun card from the noun hand by index.
        Removes the card permanently from the noun deck.
        Regenerates the story prompt to include the chosen noun.
        Returns the card or None."""
        if index < 0 or index >= len(self._noun_hand):
            return None
        self._chosen_noun = self._noun_hand[index]
        # Remove from the noun deck permanently
        chosen_word = self._chosen_noun["word"]
        self._noun_deck = [n for n in self._noun_deck if n["word"] != chosen_word]
        # Regenerate story so the prompt includes the chosen noun
        self._generate_story_for_round()
        return dict(self._chosen_noun)

    # ── Properties ──────────────────────────────────────────────────────

    @property
    def hand(self) -> list[str]:
        return list(self._hand)

    def shuffle_hand(self):
        """Shuffle the current hand in place."""
        random.shuffle(self._hand)

    @property
    def hand_size(self) -> int:
        """Dynamic hand size including accessory bonuses."""
        size = self._base_hand_size
        if "extra_draw" in self._accessories:
            size += 1
        return size

    @property
    def deck_size(self) -> int:
        return len(self._deck)

    @property
    def discard_size(self) -> int:
        return len(self._discard)

    @property
    def is_game_over(self) -> bool:
        return self.hp <= 0

    @property
    def is_victory(self) -> bool:
        return self.encounters_cleared > ENCOUNTERS_BEFORE_BOSS

    @property
    def is_boss_encounter(self) -> bool:
        return self.encounters_cleared == ENCOUNTERS_BEFORE_BOSS

    @property
    def potions(self) -> list[str]:
        return list(self._potions)

    @property
    def accessories(self) -> list[str]:
        return list(self._accessories)

    @property
    def played_words(self) -> list[str]:
        return list(self._played_words)

    @property
    def is_encounter_finished(self) -> bool:
        """True when all rounds for the current encounter are done."""
        return self.current_round > self.rounds_per_encounter

    @property
    def expects_verb(self) -> bool:
        """True when the current round expects a verb (2 of 3 rounds)."""
        return self.current_round != self._noun_round

    @property
    def noun_deck(self) -> list[dict]:
        return list(self._noun_deck)

    @property
    def noun_hand(self) -> list[dict]:
        return list(self._noun_hand)

    @property
    def chosen_noun(self) -> dict | None:
        return dict(self._chosen_noun) if self._chosen_noun else None

    @property
    def encounter_hp(self) -> int:
        return self._encounter_hp

    @property
    def encounter_max_hp(self) -> int:
        return self._encounter_max_hp

    @property
    def is_bonus_round(self) -> bool:
        return self._bonus_round

    @property
    def current_round_data(self) -> dict | None:
        """Return the dict for the current round (flavor, prompt, requirements).

        If story generation produced custom flavor/prompt, those override the
        static data.  Otherwise falls back to the static encounter data.
        For bonus round 4, reuses round 3's data as a template.
        """
        if self.current_encounter is None:
            return None
        rounds = self.current_encounter.get("rounds", [])
        idx = self.current_round - 1
        # Bonus round: reuse the last round's data
        if idx >= len(rounds):
            if rounds:
                rd = dict(rounds[-1])
                rd["flavor"] = f"The {self.encounter_name} is barely standing! One final push..."
                rd["prompt"] = rd.get("prompt", "You [ ______ ] it.")
            else:
                return None
        elif 0 <= idx < len(rounds):
            rd = dict(rounds[idx])
        else:
            return None
        # Override with generated story if available
        if self._generated_round_data is not None:
            rd["flavor"] = self._generated_round_data.get("flavor", rd.get("flavor", ""))
            rd["prompt"] = self._generated_round_data.get("prompt", rd.get("prompt", ""))
        # For noun rounds, inject the chosen noun into the prompt if not already there
        if not self.expects_verb and self._chosen_noun:
            noun_word = self._chosen_noun["word"]
            prompt = rd.get("prompt", "")
            if noun_word not in prompt:
                rd["prompt"] = f"You ready your {noun_word} and deliver a [ ______ ] blow!"
        return rd

    @property
    def encounter_name(self) -> str:
        """Return the name of the current encounter."""
        if self.current_encounter is None:
            return ""
        return self.current_encounter.get("name", "")

    def get_highest_letter(self) -> str | None:
        """Return the highest-point letter in the hand for 'Use Highest Letter' modifier, or None."""
        enc = self.current_encounter
        if enc is None:
            return None
        modifier_key = enc.get("modifier")
        if modifier_key not in ("must_use_highest", "boss_highest_length"):
            return None
        highest_letter = None
        highest_value = -1
        for card in self._hand:
            val = LETTER_VALUES.get(card, 0)
            if val > highest_value:
                highest_value = val
                highest_letter = card
        return highest_letter

    def get_red_highlight_letters(self, current_word: str) -> set[str]:
        """Return the set of letters in the hand that should glow red,
        based on the current modifier and word-building state."""
        red: set[str] = set()
        enc = self.current_encounter
        if enc is None:
            return red
        modifier_key = enc.get("modifier", "")

        # "Use Highest Letter" — always highlight the highest-point letter
        if modifier_key in ("must_use_highest", "boss_highest_length"):
            hl = self.get_highest_letter()
            if hl:
                red.add(hl)

        # "No Vowel Start" — highlight vowels when word is empty
        if modifier_key in ("no_vowel_start", "boss_vowel_double"):
            if not current_word:
                vowels = {"a", "e", "i", "o", "u"}
                for card in self._hand:
                    if card in vowels:
                        red.add(card)

        # "No Wildcards" — highlight wildcards
        if modifier_key == "no_wildcards":
            for card in self._hand:
                if card == '*':
                    red.add(card)

        return red

    def check_modifier_preview(self, word: str) -> dict:
        """
        Check the current encounter's modifier against a *word* without
        any side effects.  Returns the same shape as ``_check_modifier``::

            {"violated": bool, "penalty": int, "message": str, "type": str}

        Resolves wildcards where possible so that vowel/consonant checks
        work correctly during preview.
        """
        resolved = self._resolve_wildcards(word.lower()) or word.lower()
        return self._check_modifier(word, resolved)

    def preview_openai_score(self, word: str, resolved_word: str | None = None) -> dict | None:
        """
        Call the OpenAI API to score *word* without consuming cards or
        advancing the game state.  Resolves wildcards first.

        *resolved_word* is the fully resolved word (wildcards replaced with
        chosen letters). If not provided, the engine resolves wildcards
        automatically (first dictionary match).

        Returns the same dict as ``score_word()``, or ``None`` if the
        word cannot be resolved to a valid dictionary word.
        """
        w = word.lower()
        if resolved_word is not None:
            resolved = resolved_word.lower()
            if resolved not in self._valid_words:
                return None
        else:
            resolved = self._resolve_wildcards(w)
            if resolved is None:
                return None

        rd = self.current_round_data
        if rd is None:
            return None

        sentence = rd.get("prompt", "")
        try:
            return score_word(
                sentence, resolved, game_id=self.game_id,
                played_words=self._played_words,
                expected_pos="verb" if self.expects_verb else "adjective",
            )
        except Exception:
            return None

    # ── Encounter flow ───────────────────────────────────────────────────

    def next_encounter(self) -> dict | None:
        """Pop and return the next encounter, or None if the run is over."""
        if self.is_game_over or self.is_victory:
            return None
        if not self._encounter_queue:
            return None
        self.current_encounter = self._encounter_queue.pop(0)
        self.current_approach = None
        self.current_requirement = 0
        self.current_round = 1
        self._bonus_round = False
        self._story_so_far = []
        self._generated_round_data = None
        self._generated_approaches = None
        self._chosen_noun = None
        # Set encounter HP from data
        enc_name = self.current_encounter.get("name", "")
        self._encounter_max_hp = ENCOUNTER_HP.get(enc_name, 25)
        self._encounter_hp = self._encounter_max_hp
        # Pick which round (1-3) is the noun round with weighted probability:
        # 25% round 1, 50% round 2, 100% round 3
        roll = random.random()
        if roll < 0.25:
            self._noun_round = 1
        elif roll < 0.75:
            self._noun_round = 2
        else:
            self._noun_round = 3
        self._generate_approaches_for_encounter()
        return dict(self.current_encounter)

    def advance_round(self):
        """Move to the next round.  If the encounter is finished, increment
        ``encounters_cleared`` and grant rewards.  If encounter HP > 0 after
        round 3, trigger a bonus 4th round.  If HP > 0 after round 4, game over."""
        self.current_round += 1
        self._chosen_noun = None  # clear noun card for next round
        if self.is_encounter_finished:
            # Check if encounter HP is still above 0 — bonus round!
            if self._encounter_hp > 0 and not self._bonus_round:
                self._bonus_round = True
                self.rounds_per_encounter = 4
                # Don't advance — we're in the bonus round now
                return
            # Bonus round finished but encounter still alive — instant death
            if self._bonus_round and self._encounter_hp > 0:
                self.hp = 0
                return
            self.encounters_cleared += 1
            self.rounds_per_encounter = ROUNDS_PER_ENCOUNTER  # reset for next encounter
            # Grant post-encounter rewards (not after boss/victory)
            if not self.is_victory:
                self._maybe_gain_potion()
                self._gain_random_accessory()
                self._gain_random_noun()

    def _generate_story_for_round(self):
        """Call the OpenAI API to generate dynamic flavor/prompt for the current round.

        Falls back to static encounter data if the API call fails.
        """
        self._generated_round_data = None
        enc = self.current_encounter
        if enc is None:
            return

        # Get modifier name
        modifier_key = enc.get("modifier", "")
        mod = BOSS_MODIFIERS.get(modifier_key) or MODIFIERS.get(modifier_key, {})
        modifier_name = mod.get("name", "None")

        rounds = enc.get("rounds", [])
        idx = self.current_round - 1
        if idx < 0 or idx >= len(rounds):
            # Bonus round — still try to generate story
            pass

        try:
            result = generate_story_round(
                encounter_name=enc.get("name", "Unknown"),
                modifier_name=modifier_name,
                approach=self.current_approach or "aggressive",
                requirement=self.current_requirement,
                round_number=self.current_round,
                total_rounds=self.rounds_per_encounter,
                story_so_far=self._story_so_far,
                game_id=self.game_id,
                expects_verb=self.expects_verb,
                chosen_noun=self._chosen_noun,
            )
            if result.get("flavor") and result.get("prompt"):
                self._generated_round_data = result
        except Exception:
            pass  # Fall back to static data

    def _generate_approaches_for_encounter(self):
        """Call the OpenAI API to generate approach descriptions for the current encounter.

        Falls back to generic descriptions if the API call fails.
        """
        self._generated_approaches = None
        enc = self.current_encounter
        if enc is None:
            return

        # Get modifier name
        modifier_key = enc.get("modifier", "")
        mod = BOSS_MODIFIERS.get(modifier_key) or MODIFIERS.get(modifier_key, {})
        modifier_name = mod.get("name", "None")

        rounds = enc.get("rounds", [])
        if not rounds:
            return

        # Use the first round's requirements
        rd0 = rounds[0]
        aggressive_req = max(1, rd0.get("aggressive", 10) + self.aggressive_bonus)
        charisma_req = rd0.get("charisma", 10)
        intelligence_req = rd0.get("intelligence", 10)

        try:
            result = generate_approaches(
                encounter_name=enc.get("name", "Unknown"),
                modifier_name=modifier_name,
                aggressive_req=aggressive_req,
                charisma_req=charisma_req,
                intelligence_req=intelligence_req,
                story_so_far=self._story_so_far,
                game_id=self.game_id,
            )
            if result.get("aggressive") and result.get("charisma") and result.get("intelligence"):
                self._generated_approaches = result
        except Exception:
            pass  # Fall back to generic descriptions

    @property
    def approach_descriptions(self) -> dict:
        """Return generated approach descriptions, or generic fallbacks."""
        if self._generated_approaches:
            return dict(self._generated_approaches)
        return {
            "aggressive": "Approach it aggressively",
            "charisma": "Approach it charismatically",
            "intelligence": "Approach it intelligently",
        }

    def choose_approach(self, approach: str) -> int:
        """Lock in an approach and return the (adjusted) point requirement."""
        rd = self.current_round_data
        if rd is None:
            raise ValueError("No active encounter round.")

        base = rd[approach]
        if approach == "aggressive":
            base += self.aggressive_bonus

        self.current_approach = approach
        self.current_requirement = max(1, base)

        # Generate story for this round now that we know the approach.
        # For noun rounds, skip — story is generated later in choose_noun()
        # when we know which noun the player picked.
        if self.expects_verb:
            self._generate_story_for_round()

        return self.current_requirement

    # ── Word play ───────────────────────────────────────────────────────

    def play_word(self, word: str, cached_openai_result: dict | None = None,
                  resolved_word: str | None = None) -> dict:
        """
        Validate *word* against the dictionary and the current hand,
        calculate the score, apply damage, and refresh the hand.

        *word* may contain ``'*'`` characters representing wildcards.
        *resolved_word* is the fully resolved word (wildcards replaced with
        chosen letters). If not provided, the engine resolves wildcards
        automatically (first dictionary match).

        If *cached_openai_result* is provided (from a preview call), the
        OpenAI API is not called again — the cached values are used instead.

        Returns a dict::

            {
                "valid": bool,
                "error": str | None,
                "score": int,
                "requirement": int,
                "damage_to_player": int,
                "resolved_word": str | None,
                "round_success": bool,
                "narrative": str,
            }
        """
        w = word.lower()

        # 1.  Can the word be formed from the current hand?
        hand_ok = self._can_form_from_hand(w)
        if not hand_ok["valid"]:
            self.hp = max(0, self.hp - 1)
            return {
                "valid": False, "error": hand_ok["error"],
                "score": 0, "requirement": self.current_requirement,
                "damage_to_player": 1, "resolved_word": None,
                "round_success": False,
                "narrative": f"Invalid word! You take 1 damage and must try again.",
            }

        # 2.  Is it a real English word (resolving wildcards)?
        if resolved_word is not None:
            resolved = resolved_word.lower()
            if resolved not in self._valid_words:
                self.hp = max(0, self.hp - 1)
                return {
                    "valid": False,
                    "error": f"'{resolved}' is not a valid English word.",
                    "score": 0, "requirement": self.current_requirement,
                    "damage_to_player": 1, "resolved_word": None,
                    "round_success": False,
                    "narrative": f"'{resolved}' is not a word! You take 1 damage and must try again.",
                }
        else:
            resolved = self._resolve_wildcards(w)
            if resolved is None:
                self.hp = max(0, self.hp - 1)
                return {
                    "valid": False,
                    "error": f"'{word}' is not a valid English word.",
                    "score": 0, "requirement": self.current_requirement,
                    "damage_to_player": 1, "resolved_word": None,
                    "round_success": False,
                    "narrative": f"'{word}' is not a word! You take 1 damage and must try again.",
                }

        # 3.  Score
        score = self.calculate_score(w)

        # 3b. Modifier check — blocking modifiers reject the word outright
        modifier_result = self._check_modifier(w, resolved)
        if modifier_result["violated"] and modifier_result.get("type") == "blocking":
            self.hp = max(0, self.hp - 1)
            return {
                "valid": False, "error": modifier_result["message"],
                "score": 0, "requirement": self.current_requirement,
                "damage_to_player": 1, "resolved_word": None,
                "round_success": False,
                "narrative": f"Rule broken! {modifier_result['detail']} You take 1 damage and must try again.",
            }

        # 3c. Penalty modifiers reduce effective score
        modifier_penalty = modifier_result["penalty"] if modifier_result["violated"] else 0
        effective_score = max(0, score - modifier_penalty)

        # 3d. OpenAI scoring — additive bonus from exoticness, multipliers from suitability & uniqueness
        openai_bonus = {
            "exoticness": 0, "suitability": 0, "uniqueness": 0,
            "additive_bonus": 0, "suitability_multiplier": 1.0, "uniqueness_multiplier": 1.0,
            "pos_match": True, "pos_penalty": 0.0,
        }
        expected_pos = "verb"
        if cached_openai_result is not None:
            openai_bonus = cached_openai_result
        else:
            try:
                rd = self.current_round_data
                if rd:
                    sentence = rd.get("prompt", "")
                    openai_result = score_word(
                        sentence, resolved, game_id=self.game_id,
                        played_words=self._played_words,
                        expected_pos=expected_pos,
                    )
                    openai_bonus = openai_result
            except Exception:
                pass  # If OpenAI call fails, just use no bonus

        additive_bonus = openai_bonus["additive_bonus"]
        suitability_mult = openai_bonus["suitability_multiplier"]
        uniqueness_mult = openai_bonus["uniqueness_multiplier"]
        pos_penalty = openai_bonus.get("pos_penalty", 0.0)

        # Apply additive bonus first, then both multipliers, then wrong word type penalty
        effective_score = max(0, int((effective_score + additive_bonus) * suitability_mult * uniqueness_mult))
        if pos_penalty > 0:
            effective_score = max(0, int(effective_score * pos_penalty))

        # 4.  Damage (based on effective score after modifier penalty)
        damage = max(0, self.current_requirement - effective_score)
        self.hp = max(0, self.hp - damage)

        # 4b. Reduce encounter HP by effective score
        self._encounter_hp = max(0, self._encounter_hp - effective_score)

        # 5.  Discard used cards & draw back to hand size
        self._discard_used_cards(w)
        self._draw_cards(self.hand_size - len(self._hand))

        # 6.  Track round success
        round_success = effective_score >= self.current_requirement

        # 7.  Track played word for uniqueness scoring
        self._played_words.append(resolved)

        # 7b. Record this round in the story so far (for future story generation)
        rd = self.current_round_data
        if rd:
            self._story_so_far.append({
                "flavor": rd.get("flavor", ""),
                "prompt": rd.get("prompt", ""),
                "word": resolved,
            })

        # 8.  Generate narrative
        narrative = self._narrative_result(round_success, damage)

        return {
            "valid": True, "error": None,
            "score": score, "effective_score": effective_score,
            "requirement": self.current_requirement,
            "damage_to_player": damage, "resolved_word": resolved,
            "round_success": round_success, "narrative": narrative,
            "modifier_violated": modifier_result["violated"],
            "modifier_penalty": modifier_penalty,
            "modifier_message": modifier_result["message"],
            "openai_bonus": openai_bonus,
        }

    def play_noun(self, word: str, cached_openai_result: dict | None = None,
                  resolved_word: str | None = None) -> dict:
        """
        Play a word during a noun round. The player has already chosen a noun
        card (via ``choose_noun``), and now plays an **adjective** from their
        hand.  The noun card's points are added to the effective score.

        *resolved_word* is the fully resolved word (wildcards replaced with
        chosen letters). If not provided, the engine resolves wildcards
        automatically (first dictionary match).

        Returns the same dict shape as ``play_word``.
        """
        if self._chosen_noun is None:
            return {
                "valid": False, "error": "No noun card chosen.",
                "score": 0, "requirement": self.current_requirement,
                "damage_to_player": 0, "resolved_word": None,
                "round_success": False,
                "narrative": "You must choose a noun card first.",
            }

        w = word.lower()

        # 1.  Can the word be formed from the current hand?
        hand_ok = self._can_form_from_hand(w)
        if not hand_ok["valid"]:
            self.hp = max(0, self.hp - 1)
            return {
                "valid": False, "error": hand_ok["error"],
                "score": 0, "requirement": self.current_requirement,
                "damage_to_player": 1, "resolved_word": None,
                "round_success": False,
                "narrative": f"Invalid word! You take 1 damage and must try again.",
            }

        # 2.  Is it a real English word?
        if resolved_word is not None:
            resolved = resolved_word.lower()
            if resolved not in self._valid_words:
                self.hp = max(0, self.hp - 1)
                return {
                    "valid": False,
                    "error": f"'{resolved}' is not a valid English word.",
                    "score": 0, "requirement": self.current_requirement,
                    "damage_to_player": 1, "resolved_word": None,
                    "round_success": False,
                    "narrative": f"'{resolved}' is not a word! You take 1 damage and must try again.",
                }
        else:
            resolved = self._resolve_wildcards(w)
            if resolved is None:
                self.hp = max(0, self.hp - 1)
                return {
                    "valid": False,
                    "error": f"'{word}' is not a valid English word.",
                    "score": 0, "requirement": self.current_requirement,
                    "damage_to_player": 1, "resolved_word": None,
                    "round_success": False,
                    "narrative": f"'{word}' is not a word! You take 1 damage and must try again.",
                }

        # 3.  Score
        score = self.calculate_score(w)

        # 3b. Modifier check
        modifier_result = self._check_modifier(w, resolved)
        if modifier_result["violated"] and modifier_result.get("type") == "blocking":
            self.hp = max(0, self.hp - 1)
            return {
                "valid": False, "error": modifier_result["message"],
                "score": 0, "requirement": self.current_requirement,
                "damage_to_player": 1, "resolved_word": None,
                "round_success": False,
                "narrative": f"Rule broken! {modifier_result['detail']} You take 1 damage and must try again.",
            }

        modifier_penalty = modifier_result["penalty"] if modifier_result["violated"] else 0
        effective_score = max(0, score - modifier_penalty)

        # 3c. OpenAI scoring
        openai_bonus = {
            "exoticness": 0, "suitability": 0, "uniqueness": 0,
            "additive_bonus": 0, "suitability_multiplier": 1.0, "uniqueness_multiplier": 1.0,
            "pos_match": True, "pos_penalty": 0.0,
        }
        if cached_openai_result is not None:
            openai_bonus = cached_openai_result
        else:
            try:
                rd = self.current_round_data
                if rd:
                    sentence = rd.get("prompt", "")
                    openai_result = score_word(
                        sentence, resolved, game_id=self.game_id,
                        played_words=self._played_words,
                        expected_pos="adjective",
                    )
                    openai_bonus = openai_result
            except Exception:
                pass

        additive_bonus = openai_bonus["additive_bonus"]
        suitability_mult = openai_bonus["suitability_multiplier"]
        uniqueness_mult = openai_bonus["uniqueness_multiplier"]
        pos_penalty = openai_bonus.get("pos_penalty", 0.0)

        effective_score = max(0, int((effective_score + additive_bonus) * suitability_mult * uniqueness_mult))
        if pos_penalty > 0:
            effective_score = max(0, int(effective_score * pos_penalty))

        # 3d. Add noun card points
        noun_points = self._chosen_noun.get("points", 0)
        effective_score += noun_points

        # 4.  Damage
        damage = max(0, self.current_requirement - effective_score)
        self.hp = max(0, self.hp - damage)

        # 4b. Reduce encounter HP
        self._encounter_hp = max(0, self._encounter_hp - effective_score)

        # 5.  Discard used cards & draw back
        self._discard_used_cards(w)
        self._draw_cards(self.hand_size - len(self._hand))

        # 6.  Track round success
        round_success = effective_score >= self.current_requirement

        # 7.  Track played word
        self._played_words.append(resolved)

        # 7b. Record in story
        rd = self.current_round_data
        if rd:
            self._story_so_far.append({
                "flavor": rd.get("flavor", ""),
                "prompt": rd.get("prompt", ""),
                "word": resolved,
            })

        # 8.  Narrative
        narrative = self._narrative_result(round_success, damage)

        return {
            "valid": True, "error": None,
            "score": score, "effective_score": effective_score,
            "requirement": self.current_requirement,
            "damage_to_player": damage, "resolved_word": resolved,
            "round_success": round_success, "narrative": narrative,
            "modifier_violated": modifier_result["violated"],
            "modifier_penalty": modifier_penalty,
            "modifier_message": modifier_result["message"],
            "openai_bonus": openai_bonus,
        }

    def calculate_score(self, word: str) -> int:
        """Return the point value of *word*, applying archetype & accessory bonuses."""
        w = word.lower()
        # Resolve wildcards for vowel/consonant checks; fall back to raw word
        rw = self._resolve_wildcards(w) or w
        total = 0
        for ch in w:
            if ch == '*':
                total += self.wildcard_bonus
            else:
                total += LETTER_VALUES.get(ch, 0)

        # ── Accessory bonuses ──────────────────────────────────────────
        # wildcard_plus: wildcards worth +1
        if "wildcard_plus" in self._accessories:
            wildcard_count = w.count('*')
            total += wildcard_count * 1

        # double_letter: two of the same letter → +2
        if "double_letter" in self._accessories:
            letter_counts: dict[str, int] = {}
            for ch in rw:
                letter_counts[ch] = letter_counts.get(ch, 0) + 1
            for count in letter_counts.values():
                if count >= 2:
                    total += 2

        # vowel_bonus: 2+ vowels → +1
        if "vowel_bonus" in self._accessories:
            vowels = set("aeiou")
            vowel_count = sum(1 for ch in rw if ch in vowels)
            if vowel_count >= 2:
                total += 1

        # long_word: 5+ letters → +3
        if "long_word" in self._accessories:
            if len(rw) >= 5:
                total += 3

        # consonant_bonus: 3+ consonants → +2
        if "consonant_bonus" in self._accessories:
            vowels = set("aeiou")
            consonant_count = sum(1 for ch in rw if ch not in vowels)
            if consonant_count >= 3:
                total += 2

        return total

    def check_accessory_active(self, acc_key: str, word: str) -> bool:
        """Return True if the accessory *acc_key* would activate for *word*."""
        w = word.lower()
        # Resolve wildcards for vowel/consonant checks; fall back to raw word
        rw = self._resolve_wildcards(w) or w
        if acc_key == "wildcard_plus":
            return '*' in w
        if acc_key == "double_letter":
            letter_counts: dict[str, int] = {}
            for ch in rw:
                letter_counts[ch] = letter_counts.get(ch, 0) + 1
            return any(c >= 2 for c in letter_counts.values())
        if acc_key == "vowel_bonus":
            vowels = set("aeiou")
            return sum(1 for ch in rw if ch in vowels) >= 2
        if acc_key == "long_word":
            return len(rw) >= 5
        if acc_key == "consonant_bonus":
            vowels = set("aeiou")
            return sum(1 for ch in rw if ch not in vowels) >= 3
        if acc_key == "extra_draw":
            return True  # always active
        if acc_key == "vitality_core":
            return True  # always active
        return False

    def _narrative_result(self, success: bool, damage: int) -> str:
        """Return a narrative description of the round outcome."""
        approach = self.current_approach or "aggressive"
        enc_name = self.current_encounter["name"] if self.current_encounter else "foe"

        if success:
            lines = {
                "aggressive": [
                    f"Your fierce attack overwhelms the {enc_name}!",
                    f"You strike with precision, driving the {enc_name} back!",
                    f"A powerful blow! The {enc_name} reels from your assault.",
                ],
                "charisma": [
                    f"Your silver tongue confounds the {enc_name}!",
                    f"You talk circles around the {enc_name} — it's completely thrown off!",
                    f"Your charm disarms the {enc_name} entirely!",
                ],
                "intelligence": [
                    f"Your clever strategy outwits the {enc_name}!",
                    f"You spot a weakness and exploit it brilliantly!",
                    f"Your quick thinking leaves the {enc_name} baffled!",
                ],
            }
        else:
            if damage > 0:
                lines = {
                    "aggressive": [
                        f"Your aggressive move backfires and you take {damage} damage.",
                        f"The {enc_name} counters your attack — you take {damage} damage.",
                        f"You overextend and the {enc_name} punishes you for {damage} damage.",
                    ],
                    "charisma": [
                        f"Your words fall flat and the {enc_name} strikes you for {damage} damage.",
                        f"The {enc_name} isn't swayed by your charm — you take {damage} damage.",
                        f"Your smooth talk backfires and you take {damage} damage.",
                    ],
                    "intelligence": [
                        f"Your plan goes awry and you take {damage} damage.",
                        f"The {enc_name} sees through your strategy — you take {damage} damage.",
                        f"Your clever idea doesn't pan out and you take {damage} damage.",
                    ],
                }
            else:
                lines = {
                    "aggressive": [
                        f"Your attack glances off the {enc_name} harmlessly.",
                        f"You swing but the {enc_name} dodges — no damage either way.",
                    ],
                    "charisma": [
                        f"The {enc_name} ignores your words, but you stay safe.",
                        f"Your charm has no effect, but at least you avoid harm.",
                    ],
                    "intelligence": [
                        f"Your plan fizzles, but you manage to stay out of danger.",
                        f"The {enc_name} counters your strategy, but you hold your ground.",
                    ],
                }

        pool = lines.get(approach, lines["aggressive"])
        return random.choice(pool)

    # ── Modifier check ──────────────────────────────────────────────────

    def _check_modifier(self, word: str, resolved_word: str) -> dict:
        """
        Check the current encounter's modifier against the played word.

        Returns::

            {
                "violated": bool,
                "penalty": int,
                "message": str,
                "detail": str,
                "type": str | None,   # "blocking" or "penalty" or None
            }
        """
        enc = self.current_encounter
        if enc is None:
            return {"violated": False, "penalty": 0, "message": "", "detail": "", "type": None}

        modifier_key = enc.get("modifier")
        if modifier_key is None:
            return {"violated": False, "penalty": 0, "message": "", "detail": "", "type": None}

        # Determine if this is a boss modifier or regular modifier
        if modifier_key in BOSS_MODIFIERS:
            mod = BOSS_MODIFIERS[modifier_key]
        elif modifier_key in MODIFIERS:
            mod = MODIFIERS[modifier_key]
        else:
            return {"violated": False, "penalty": 0, "message": "", "detail": "", "type": None}

        penalty = mod["penalty"]
        mod_type = mod.get("type", "penalty")
        name = mod["name"]
        w = word.lower()
        rw = resolved_word.lower() if resolved_word else w

        violated = False
        detail = ""

        if modifier_key == "no_vowel_start":
            vowels = set("aeiou")
            if rw and rw[0] in vowels:
                violated = True
                detail = "Your word can't start with a vowel"

        elif modifier_key == "no_double_letters":
            seen = set()
            for ch in rw:
                if ch in seen:
                    violated = True
                    detail = "Your word can't repeat a letter"
                    break
                seen.add(ch)

        elif modifier_key == "must_use_highest":
            # Find the highest-point letter in the player's hand
            highest_letter = None
            highest_value = -1
            for card in self._hand:
                val = LETTER_VALUES.get(card, 0)
                if val > highest_value:
                    highest_value = val
                    highest_letter = card
            # Check if that letter (or a wildcard standing in for it) is in the word
            if highest_letter and highest_letter not in w:
                violated = True
                detail = f"Your word must include {highest_letter.upper()} (highest-point letter)"

        elif modifier_key == "min_length_4":
            if len(rw) < 4:
                violated = True
                detail = "Your word must be at least 4 letters long"

        elif modifier_key == "no_wildcards":
            if '*' in w:
                violated = True
                detail = "Your word can't use wildcards"

        elif modifier_key == "must_use_two_vowels":
            vowels = set("aeiou")
            vowel_count = sum(1 for ch in rw if ch in vowels)
            if vowel_count < 2:
                violated = True
                detail = "Your word must have at least 2 vowels"

        elif modifier_key == "boss_vowel_double":
            # Compound: no vowel start AND no double letters
            vowels = set("aeiou")
            vowel_start = rw and rw[0] in vowels
            seen = set()
            has_double = False
            for ch in rw:
                if ch in seen:
                    has_double = True
                    break
                seen.add(ch)
            if vowel_start and has_double:
                violated = True
                detail = "Your word can't start with a vowel AND can't repeat a letter"
            elif vowel_start:
                violated = True
                detail = "Your word can't start with a vowel"
            elif has_double:
                violated = True
                detail = "Your word can't repeat a letter"

        elif modifier_key == "boss_highest_length":
            # Compound: must use highest letter AND word must be 5+ letters
            highest_letter = None
            highest_value = -1
            for card in self._hand:
                val = LETTER_VALUES.get(card, 0)
                if val > highest_value:
                    highest_value = val
                    highest_letter = card
            too_short = len(rw) < 5
            missing_highest = highest_letter and highest_letter not in w
            if too_short and missing_highest:
                violated = True
                detail = f"Your word must be 5+ letters AND include {highest_letter.upper()}"
            elif too_short:
                violated = True
                detail = "Your word must be at least 5 letters long"
            elif missing_highest:
                violated = True
                detail = f"Your word must include {highest_letter.upper()} (highest-point letter)"

        if violated:
            if mod_type == "blocking":
                message = f"Rule: {name} — {detail}"
            else:
                message = f"Modifier: {name} — {detail} (-{penalty} pts)"
            return {
                "violated": True,
                "penalty": penalty,
                "message": message,
                "detail": detail,
                "type": mod_type,
            }
        return {"violated": False, "penalty": 0, "message": "", "detail": "", "type": None}

    # ── Internal helpers ─────────────────────────────────────────────────

    def _can_form_from_hand(self, word: str) -> dict:
        """Check whether *word* can be assembled from ``self._hand``."""
        available: dict[str, int] = {}
        for card in self._hand:
            available[card] = available.get(card, 0) + 1

        for ch in word:
            if available.get(ch, 0) > 0:
                available[ch] -= 1
            elif available.get('*', 0) > 0:
                available['*'] -= 1
            else:
                return {"valid": False,
                        "error": f"Not enough '{ch}' cards in hand."}
        return {"valid": True, "error": None}

    def _resolve_wildcards(self, word: str) -> str | None:
        """
        If *word* contains ``'*'``, find the first dictionary word that
        matches the pattern.  Returns the resolved word or ``None``.
        """
        if '*' not in word:
            return word if word in self._valid_words else None

        length = len(word)
        if length not in self._words_by_length:
            return None

        chars = list(word)
        wild_positions = [i for i, ch in enumerate(chars) if ch == '*']

        for candidate in self._words_by_length[length]:
            if all(chars[i] in ('*', candidate[i]) for i in range(length)):
                return candidate
        return None

    def _discard_used_cards(self, word: str):
        """Remove the cards used to form *word* from the hand, discarding them."""
        hand = list(self._hand)
        used: list[str] = []
        for ch in word:
            if ch in hand:
                hand.remove(ch)
                used.append(ch)
            elif '*' in hand:
                hand.remove('*')
                used.append('*')
        self._discard.extend(used)   # used cards → discard
        self._hand = hand            # unused cards stay in hand

    def _draw_cards(self, n: int):
        """Draw up to *n* cards, reshuffling the discard pile when needed."""
        for _ in range(n):
            if not self._deck:
                if not self._discard:
                    break
                self._deck = self._discard
                self._discard = []
                random.shuffle(self._deck)
            self._hand.append(self._deck.pop())
