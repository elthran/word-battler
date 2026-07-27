"""OpenAI-powered word scoring and story generation for Word Battler.

Calls the OpenAI API to:
1. Rate a word on three dimensions (exoticness, suitability, uniqueness)
2. Generate dynamic encounter flavor text and prompts

All requests and responses are logged to ``logs/openai/<game_id>.jsonl``.
"""

import os
import json
import datetime
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables from .env.local
load_dotenv(".env.local")

LOG_DIR = Path(__file__).parent / "logs" / "openai"

_PROMPTS_DIR = Path(__file__).parent / "prompts"

with open(_PROMPTS_DIR / "scoring.txt", "r", encoding="utf-8") as _f:
    SCORING_SYSTEM_PROMPT = _f.read()

with open(_PROMPTS_DIR / "story.txt", "r", encoding="utf-8") as _f:
    STORY_SYSTEM_PROMPT = _f.read()

with open(_PROMPTS_DIR / "approaches.txt", "r", encoding="utf-8") as _f:
    APPROACHES_SYSTEM_PROMPT = _f.read()


def _get_client() -> OpenAI:
    """Create an OpenAI client using the OPENAI_API_KEY environment variable."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY environment variable not set. "
            "Please set it to your OpenAI API key."
        )
    return OpenAI(api_key=api_key)


def _get_model() -> str:
    """Return the OpenAI model name from env, defaulting to gpt-4o-mini."""
    return os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


_OPENAI_MODEL = _get_model()


def _log_entry(game_id: str, entry: dict):
    """Append a JSON line to the game's log file."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"{game_id}.jsonl"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def score_word(sentence: str, word: str, game_id: str = "unknown",
               played_words: list[str] | None = None,
               expected_pos: str = "noun") -> dict:
    """Call the OpenAI API to rate a word for a sentence.

    Args:
        sentence: The sentence prompt with a blank like "[ ______ ]".
        word: The word the player chose to fill the blank.
        game_id: A unique identifier for this game session (used for logging).
        played_words: List of words already played this game (for uniqueness rating).
        expected_pos: The expected part of speech — "noun" or "verb".

    Returns:
        A dict with:
            exoticness: int 0-10
            suitability: int 0-10
            uniqueness: int 0-10
            additive_bonus: int -2 to +3 (mapped from exoticness)
            suitability_multiplier: float 0.75-1.25 (mapped from suitability)
            uniqueness_multiplier: float 0.75-1.25 (mapped from uniqueness)
            pos_match: bool — whether the word matches the expected part of speech
            pos_penalty: float — 0.5 if pos mismatch, 0.0 otherwise
    """
    if played_words is None:
        played_words = []

    played_words_str = ", ".join(played_words) if played_words else "(none yet)"
    user_prompt = (
        f"Sentence: {sentence}\n"
        f"Word: {word}\n"
        f"Expected part of speech: {expected_pos}\n"
        f"Previously played words: {played_words_str}"
    )

    timestamp = datetime.datetime.now().isoformat()

    # Log the request
    _log_entry(game_id, {
        "type": "request",
        "timestamp": timestamp,
        "sentence": sentence,
        "word": word,
        "expected_pos": expected_pos,
        "played_words": played_words,
        "model": _OPENAI_MODEL,
        "system_prompt": SCORING_SYSTEM_PROMPT,
        "user_prompt": user_prompt,
    })

    client = _get_client()
    response = client.chat.completions.create(
        model=_OPENAI_MODEL,
        messages=[
            {"role": "system", "content": SCORING_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
        max_tokens=100,
    )

    raw_content = response.choices[0].message.content.strip()
    # Strip markdown code fences if present
    if raw_content.startswith("```"):
        raw_content = raw_content.split("\n", 1)[1]
        raw_content = raw_content.rsplit("```", 1)[0]
    raw_content = raw_content.strip()

    data = json.loads(raw_content)
    exoticness = max(0, min(10, int(data["exoticness"])))
    suitability = max(0, min(10, int(data["suitability"])))
    uniqueness = max(0, min(10, int(data.get("uniqueness", 10))))
    pos_match = data.get("pos_match", True)  # True if word matches expected POS

    # Map exoticness 0-10 → additive bonus -2 to +3
    additive_bonus = round(exoticness / 10 * 5 - 2)

    # Map suitability 0-10 → multiplier 0.75-1.25
    suitability_multiplier = 0.75 + suitability / 10 * 0.5

    # Map uniqueness 0-10 → multiplier 0.75-1.25
    uniqueness_multiplier = 0.75 + uniqueness / 10 * 0.5

    # POS penalty: 0.5x multiplier if the word doesn't match expected part of speech
    pos_penalty = 0.5 if not pos_match else 0.0

    result = {
        "exoticness": exoticness,
        "suitability": suitability,
        "uniqueness": uniqueness,
        "additive_bonus": additive_bonus,
        "suitability_multiplier": suitability_multiplier,
        "uniqueness_multiplier": uniqueness_multiplier,
        "pos_match": pos_match,
        "pos_penalty": pos_penalty,
    }

    # Log the response
    _log_entry(game_id, {
        "type": "response",
        "timestamp": datetime.datetime.now().isoformat(),
        "raw_content": raw_content,
        "parsed": data,
        "result": result,
    })

    return result


def generate_story_round(
    encounter_name: str,
    modifier_name: str,
    approach: str,
    requirement: int,
    round_number: int,
    total_rounds: int,
    story_so_far: list[dict],
    game_id: str = "unknown",
    expects_verb: bool = False,
    chosen_noun: dict | None = None,
) -> dict:
    """Call the OpenAI API to generate flavor text and a prompt for a round.

    Args:
        encounter_name: Name of the current encounter (e.g. "Goblin", "Dragon").
        modifier_name: The modifier rule name (e.g. "No Vowel Start").
        approach: The approach the player chose ("aggressive", "charisma", "intelligence").
        requirement: The point requirement for this round.
        round_number: Which round this is (1-based).
        total_rounds: Total rounds in this encounter.
        story_so_far: List of dicts for previous rounds, each with keys:
            "flavor", "prompt", "word" (the word the player chose).
        game_id: A unique identifier for this game session (used for logging).
        expects_verb: If True, the blank in the prompt should expect a verb.
        chosen_noun: If the player chose a noun card, a dict with "word" and "points".

    Returns:
        A dict with "flavor" and "prompt" strings.
    """
    # Build the story-so-far text
    story_lines = []
    for i, entry in enumerate(story_so_far):
        story_lines.append(
            f"Round {i + 1}:\n"
            f"  flavor: \"{entry['flavor']}\"\n"
            f"  prompt: \"{entry['prompt']}\"\n"
            f"  player's word: \"{entry['word']}\""
        )
    story_text = "\n".join(story_lines) if story_lines else "(This is the first round — no story yet.)"

    if expects_verb:
        pos_instruction = "The blank [ ______ ] should expect a VERB."
    else:
        pos_instruction = "The blank [ ______ ] should expect an ADJECTIVE."

    noun_instruction = ""
    if chosen_noun:
        noun_word = chosen_noun["word"]
        noun_instruction = (
            f"\nIMPORTANT: The player has chosen the item \"{noun_word}\" to use this round. "
            f"The prompt sentence MUST include the phrase \"[ ______ ] {noun_word}\" — the blank "
            f"must be placed directly before the word \"{noun_word}\" so the player's adjective "
            f"modifies that specific noun. For example: \"You deliver a [ ______ ] {noun_word} strike\" "
            f"or \"With a [ ______ ] {noun_word}, you attack.\" "
            f"Do NOT put the blank next to any other noun — it must be adjacent to \"{noun_word}\"."
        )

    user_prompt = (
        f"Encounter: {encounter_name}\n"
        f"Modifier: {modifier_name}\n"
        f"Approach: {approach}\n"
        f"Requirement: {requirement} pts\n"
        f"Round: {round_number} of {total_rounds}\n"
        f"{pos_instruction}\n"
        f"{noun_instruction}\n"
        f"\n"
        f"Story so far:\n{story_text}\n"
        f"\n"
        f"Generate the flavor and prompt for round {round_number}."
    )

    timestamp = datetime.datetime.now().isoformat()

    # Log the request
    _log_entry(game_id, {
        "type": "story_request",
        "timestamp": timestamp,
        "encounter_name": encounter_name,
        "modifier_name": modifier_name,
        "approach": approach,
        "requirement": requirement,
        "round_number": round_number,
        "total_rounds": total_rounds,
        "expects_verb": expects_verb,
        "chosen_noun": chosen_noun,
        "story_so_far": story_so_far,
        "model": _OPENAI_MODEL,
        "system_prompt": STORY_SYSTEM_PROMPT,
        "user_prompt": user_prompt,
    })

    client = _get_client()
    response = client.chat.completions.create(
        model=_OPENAI_MODEL,
        messages=[
            {"role": "system", "content": STORY_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.8,
        max_tokens=300,
    )

    raw_content = response.choices[0].message.content.strip()
    # Strip markdown code fences if present
    if raw_content.startswith("```"):
        raw_content = raw_content.split("\n", 1)[1]
        raw_content = raw_content.rsplit("```", 1)[0]
    raw_content = raw_content.strip()

    data = json.loads(raw_content)
    result = {
        "flavor": data.get("flavor", ""),
        "prompt": data.get("prompt", ""),
    }

    # Log the response
    _log_entry(game_id, {
        "type": "story_response",
        "timestamp": datetime.datetime.now().isoformat(),
        "raw_content": raw_content,
        "parsed": data,
        "result": result,
    })

    return result


def generate_approaches(
    encounter_name: str,
    modifier_name: str,
    aggressive_req: int,
    charisma_req: int,
    intelligence_req: int,
    story_so_far: list[dict],
    game_id: str = "unknown",
) -> dict:
    """Call the OpenAI API to generate short approach descriptions.

    Args:
        encounter_name: Name of the current encounter (e.g. "Goblin", "Dragon").
        modifier_name: The modifier rule name (e.g. "No Vowel Start").
        aggressive_req: Point requirement for aggressive approach.
        charisma_req: Point requirement for charisma approach.
        intelligence_req: Point requirement for intelligence approach.
        story_so_far: List of dicts for previous rounds, each with keys:
            "flavor", "prompt", "word" (the word the player chose).
        game_id: A unique identifier for this game session (used for logging).

    Returns:
        A dict with "aggressive", "charisma", "intelligence" description strings.
    """
    # Build the story-so-far text
    story_lines = []
    for i, entry in enumerate(story_so_far):
        story_lines.append(
            f"Round {i + 1}:\n"
            f"  flavor: \"{entry['flavor']}\"\n"
            f"  prompt: \"{entry['prompt']}\"\n"
            f"  player's word: \"{entry['word']}\""
        )
    story_text = "\n".join(story_lines) if story_lines else "(This is the first round — no story yet.)"

    user_prompt = (
        f"Encounter: {encounter_name}\n"
        f"Modifier: {modifier_name}\n"
        f"Requirements — Aggressive: {aggressive_req} pts, Charisma: {charisma_req} pts, Intelligence: {intelligence_req} pts\n"
        f"\n"
        f"Story so far:\n{story_text}\n"
        f"\n"
        f"Generate approach descriptions for this encounter."
    )

    timestamp = datetime.datetime.now().isoformat()

    # Log the request
    _log_entry(game_id, {
        "type": "approaches_request",
        "timestamp": timestamp,
        "encounter_name": encounter_name,
        "modifier_name": modifier_name,
        "aggressive_req": aggressive_req,
        "charisma_req": charisma_req,
        "intelligence_req": intelligence_req,
        "story_so_far": story_so_far,
        "model": _OPENAI_MODEL,
        "system_prompt": APPROACHES_SYSTEM_PROMPT,
        "user_prompt": user_prompt,
    })

    client = _get_client()
    response = client.chat.completions.create(
        model=_OPENAI_MODEL,
        messages=[
            {"role": "system", "content": APPROACHES_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.8,
        max_tokens=200,
    )

    raw_content = response.choices[0].message.content.strip()
    # Strip markdown code fences if present
    if raw_content.startswith("```"):
        raw_content = raw_content.split("\n", 1)[1]
        raw_content = raw_content.rsplit("```", 1)[0]
    raw_content = raw_content.strip()

    data = json.loads(raw_content)
    result = {
        "aggressive": data.get("aggressive", "Approach it aggressively"),
        "charisma": data.get("charisma", "Approach it charismatically"),
        "intelligence": data.get("intelligence", "Approach it intelligently"),
    }

    # Log the response
    _log_entry(game_id, {
        "type": "approaches_response",
        "timestamp": datetime.datetime.now().isoformat(),
        "raw_content": raw_content,
        "parsed": data,
        "result": result,
    })

    return result
