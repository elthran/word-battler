"""Game engine for Word Battler — pure logic, no PyGame dependencies."""

import random
import os
from data import (
    LETTER_VALUES, STARTING_DECK, HAND_SIZE, MAX_HP,
    ENCOUNTERS_BEFORE_BOSS, ROUNDS_PER_ENCOUNTER, ARCHETYPES,
    ENCOUNTER_POOL, BOSS_ENCOUNTER,
)


class GameEngine:
    """Core game state and logic.  No rendering or I/O."""

    def __init__(self, archetype_key: str):
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
        self.hand_size = HAND_SIZE + self.hand_bonus
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
        """Shuffle the pool, take the first N, then append the boss."""
        pool = list(ENCOUNTER_POOL)
        random.shuffle(pool)
        self._encounter_queue = pool[:ENCOUNTERS_BEFORE_BOSS]
        self._encounter_queue.append(BOSS_ENCOUNTER)

    # ── Properties ──────────────────────────────────────────────────────

    @property
    def hand(self) -> list[str]:
        return list(self._hand)

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
    def is_encounter_finished(self) -> bool:
        """True when all rounds for the current encounter are done."""
        return self.current_round > self.rounds_per_encounter

    @property
    def current_round_data(self) -> dict | None:
        """Return the dict for the current round (flavor, prompt, requirements)."""
        if self.current_encounter is None:
            return None
        rounds = self.current_encounter.get("rounds", [])
        idx = self.current_round - 1
        if 0 <= idx < len(rounds):
            return rounds[idx]
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
        return dict(self.current_encounter)

    def advance_round(self):
        """Move to the next round.  If the encounter is finished, increment
        ``encounters_cleared``."""
        self.current_round += 1
        if self.is_encounter_finished:
            self.encounters_cleared += 1

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
        return self.current_requirement

    # ── Word play ───────────────────────────────────────────────────────

    def play_word(self, word: str) -> dict:
        """
        Validate *word* against the dictionary and the current hand,
        calculate the score, apply damage, and refresh the hand.

        *word* may contain ``'*'`` characters representing wildcards.

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

        # 4.  Damage
        damage = max(0, self.current_requirement - score)
        self.hp = max(0, self.hp - damage)

        # 5.  Discard used cards & draw back to hand size
        self._discard_used_cards(w)
        self._draw_cards(self.hand_size - len(self._hand))

        # 6.  Track round success
        round_success = score >= self.current_requirement

        # 7.  Generate narrative
        narrative = self._narrative_result(round_success, damage)

        return {
            "valid": True, "error": None,
            "score": score, "requirement": self.current_requirement,
            "damage_to_player": damage, "resolved_word": resolved,
            "round_success": round_success, "narrative": narrative,
        }

    def calculate_score(self, word: str) -> int:
        """Return the point value of *word*, applying archetype bonuses."""
        total = 0
        for ch in word.lower():
            if ch == '*':
                total += self.wildcard_bonus
            else:
                total += LETTER_VALUES.get(ch, 0)
        return total

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
