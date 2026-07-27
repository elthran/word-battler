"""OpenAI-powered word scoring for Word Battler.

Calls the OpenAI API to rate a word on three dimensions:
1. Exoticness / interest — how unusual or interesting the word is
2. Suitability — how well the word fits into the given sentence
3. Uniqueness — how different the word is from previously played words

Returns an additive bonus (-2 to +3) and two multipliers (0.75x-1.25x, 0.75x-1.25x).

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

_PROMPT_PATH = Path(__file__).parent / "openai_prompt.txt"
with open(_PROMPT_PATH, "r", encoding="utf-8") as _f:
    SYSTEM_PROMPT = _f.read()


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
               played_words: list[str] | None = None) -> dict:
    """Call the OpenAI API to rate a word for a sentence.

    Args:
        sentence: The sentence prompt with a blank like "[ ______ ]".
        word: The word the player chose to fill the blank.
        game_id: A unique identifier for this game session (used for logging).
        played_words: List of words already played this game (for uniqueness rating).

    Returns:
        A dict with:
            exoticness: int 0-10
            suitability: int 0-10
            uniqueness: int 0-10
            additive_bonus: int -2 to +3 (mapped from exoticness)
            suitability_multiplier: float 0.75-1.25 (mapped from suitability)
            uniqueness_multiplier: float 0.75-1.25 (mapped from uniqueness)
    """
    if played_words is None:
        played_words = []

    played_words_str = ", ".join(played_words) if played_words else "(none yet)"
    user_prompt = (
        f"Sentence: {sentence}\n"
        f"Word: {word}\n"
        f"Previously played words: {played_words_str}"
    )

    timestamp = datetime.datetime.now().isoformat()

    # Log the request
    _log_entry(game_id, {
        "type": "request",
        "timestamp": timestamp,
        "sentence": sentence,
        "word": word,
        "played_words": played_words,
        "model": _OPENAI_MODEL,
        "system_prompt": SYSTEM_PROMPT,
        "user_prompt": user_prompt,
    })

    client = _get_client()
    response = client.chat.completions.create(
        model=_OPENAI_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
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

    # Map exoticness 0-10 → additive bonus -2 to +3
    additive_bonus = round(exoticness / 10 * 5 - 2)

    # Map suitability 0-10 → multiplier 0.75-1.25
    suitability_multiplier = 0.75 + suitability / 10 * 0.5

    # Map uniqueness 0-10 → multiplier 0.75-1.25
    uniqueness_multiplier = 0.75 + uniqueness / 10 * 0.5

    result = {
        "exoticness": exoticness,
        "suitability": suitability,
        "uniqueness": uniqueness,
        "additive_bonus": additive_bonus,
        "suitability_multiplier": suitability_multiplier,
        "uniqueness_multiplier": uniqueness_multiplier,
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
