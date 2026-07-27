"""Game constants and data for Word Battler."""

# ── Scrabble-style letter point values ──────────────────────────────────────
LETTER_VALUES: dict[str, int] = {
    "a": 1, "e": 1, "i": 1, "o": 1, "u": 1,
    "l": 1, "n": 1, "s": 1, "t": 1, "r": 1,
    "d": 2, "g": 2,
    "b": 3, "c": 3, "m": 3, "p": 3,
    "f": 4, "h": 4, "v": 4, "w": 4, "y": 4,
    "k": 5,
    "j": 8, "x": 8,
    "q": 10, "z": 10,
    "*": 0,  # wildcard
}

# ── Deck ────────────────────────────────────────────────────────────────────
STARTING_DECK: list[str] = [
    "a", "e", "i", "o", "u",   # vowels
    "t", "n", "s", "r", "h",   # common consonants
    "l", "d", "c", "m", "p",   # more common consonants
    "*", "*", "*", "*", "*",   # wildcards
]

# ── Game rules ──────────────────────────────────────────────────────────────
HAND_SIZE: int = 8
MAX_HP: int = 10
ENCOUNTERS_BEFORE_BOSS: int = 3   # 3 normal encounters, then the boss
ROUNDS_PER_ENCOUNTER: int = 3

# ── Archetypes ───────────────────────────────────────────────────────────────
ARCHETYPES: dict[str, dict] = {
    "brawler": {
        "name": "Brawler",
        "description": "Aggressive requirements -2",
        "aggressive_bonus": -2,
        "hand_bonus": 0,
        "wildcard_bonus": 0,
    },
    "thinker": {
        "name": "Thinker",
        "description": "Draw +1 card each round",
        "aggressive_bonus": 0,
        "hand_bonus": 1,
        "wildcard_bonus": 0,
    },
    "charmer": {
        "name": "Charmer",
        "description": "Wildcards give +2 points",
        "aggressive_bonus": 0,
        "hand_bonus": 0,
        "wildcard_bonus": 2,
    },
}

# ── Modifiers ────────────────────────────────────────────────────────────────
# Each modifier has: name, description, penalty (score reduction when violated).
# The modifier key is stored on each encounter.

MODIFIERS: dict[str, dict] = {
    "no_vowel_start": {
        "name": "No Vowel Start",
        "description": "Your word cannot start with a vowel (a, e, i, o, u).",
        "type": "blocking",
        "penalty": 2,
    },
    "no_double_letters": {
        "name": "No Double Letters",
        "description": "You cannot use the same letter twice in your word.",
        "type": "blocking",
        "penalty": 2,
    },
    "must_use_highest": {
        "name": "Use Highest Letter",
        "description": "You must include the highest-point letter from your hand.",
        "type": "blocking",
        "penalty": 2,
    },
    "min_length_4": {
        "name": "Minimum Length 4",
        "description": "Your word must be at least 4 letters long.",
        "type": "blocking",
        "penalty": 2,
    },
    "no_wildcards": {
        "name": "No Wildcards",
        "description": "You cannot use wildcard (*) cards in your word.",
        "type": "blocking",
        "penalty": 2,
    },
    "must_use_two_vowels": {
        "name": "Two Vowels Required",
        "description": "Your word must contain at least 2 vowels (a, e, i, o, u).",
        "type": "blocking",
        "penalty": 2,
    },
}

BOSS_MODIFIERS: dict[str, dict] = {
    "boss_vowel_double": {
        "name": "No Vowel Start + No Doubles",
        "description": "Your word cannot start with a vowel AND cannot repeat any letter.",
        "type": "blocking",
        "penalty": 3,
    },
    "boss_highest_length": {
        "name": "Use Highest + Min Length 5",
        "description": "You must use the highest-point letter AND your word must be 5+ letters.",
        "type": "blocking",
        "penalty": 3,
    },
}

# ── Encounters ──────────────────────────────────────────────────────────────
# Each encounter has a "name", a "modifier" key, and a "rounds" list.
# Each round dict has: flavor, prompt, aggressive, charisma, intelligence.

ENCOUNTER_POOL: list[dict] = [
    {
        "name": "Goblin",
        "modifier": "no_vowel_start",
        "rounds": [
            {
                "flavor": "A grimy goblin blocks the path, clutching a rusty dagger. It snarls and lunges at you!",
                "prompt": "You sidestep its lunge and [ ______ ] it.",
                "aggressive": 9, "charisma": 8, "intelligence": 11,
            },
            {
                "flavor": "The goblin staggers but isn't done yet. It spits on the ground and raises its blade again.",
                "prompt": "Before it can strike, you [ ______ ] it.",
                "aggressive": 11, "charisma": 9, "intelligence": 12,
            },
            {
                "flavor": "Bleeding and desperate, the goblin makes one final, wild charge!",
                "prompt": "You stand your ground and [ ______ ] it.",
                "aggressive": 12, "charisma": 11, "intelligence": 9,
            },
        ],
    },
    {
        "name": "Skeleton",
        "modifier": "no_double_letters",
        "rounds": [
            {
                "flavor": "A rattling skeleton rises from a pile of bones, hollow eyes fixed on you. It clatters forward.",
                "prompt": "Facing the skeleton, you [ ______ ] it.",
                "aggressive": 11, "charisma": 9, "intelligence": 12,
            },
            {
                "flavor": "You crack a few ribs, but the skeleton reassembles itself with a dry clatter. It draws a rusty sword.",
                "prompt": "As it swings, you [ ______ ] it.",
                "aggressive": 12, "charisma": 11, "intelligence": 9,
            },
            {
                "flavor": "The skeleton's bones are splintering. Dark energy flickers in its eye sockets as it makes a final lunge.",
                "prompt": "With one last effort, you [ ______ ] it.",
                "aggressive": 9, "charisma": 12, "intelligence": 11,
            },
        ],
    },
    {
        "name": "Dark Mage",
        "modifier": "must_use_highest",
        "rounds": [
            {
                "flavor": "A hooded mage crackles with dark energy, muttering an incantation. Purple lightning arcs from their fingertips.",
                "prompt": "Before the spell completes, you [ ______ ] the mage.",
                "aggressive": 12, "charisma": 11, "intelligence": 9,
            },
            {
                "flavor": "The mage snarls and teleports behind you. 'You'll have to do better than that!'",
                "prompt": "You spin around and [ ______ ] the mage.",
                "aggressive": 9, "charisma": 12, "intelligence": 11,
            },
            {
                "flavor": "Robes smoldering, the mage begins a forbidden ritual. The ground beneath you trembles.",
                "prompt": "You disrupt the ritual and [ ______ ] the mage.",
                "aggressive": 11, "charisma": 9, "intelligence": 12,
            },
        ],
    },
    {
        "name": "Troll",
        "modifier": "min_length_4",
        "rounds": [
            {
                "flavor": "A hulking troll lumbers toward you, club dragging on the ground. Each step shakes the earth.",
                "prompt": "You duck under its swing and [ ______ ] it.",
                "aggressive": 14, "charisma": 12, "intelligence": 15,
            },
            {
                "flavor": "The troll roars in fury, swinging its club in a wide arc. Spittle flies from its tusks.",
                "prompt": "You dodge the blow and [ ______ ] it.",
                "aggressive": 12, "charisma": 15, "intelligence": 11,
            },
            {
                "flavor": "The troll is wounded but enraged. It raises its club high for a crushing overhead smash!",
                "prompt": "In that split second, you [ ______ ] it.",
                "aggressive": 15, "charisma": 11, "intelligence": 12,
            },
        ],
    },
    {
        "name": "Bandit",
        "modifier": "no_wildcards",
        "rounds": [
            {
                "flavor": "A masked bandit leaps from the shadows, a curved dagger glinting. 'Your gold or your life!'",
                "prompt": "You look the bandit in the eye and [ ______ ] it.",
                "aggressive": 11, "charisma": 12, "intelligence": 9,
            },
            {
                "flavor": "The bandit curses and flips the dagger in their hand. 'Lucky shot. Let's see you do that again.'",
                "prompt": "As the bandit circles you, you [ ______ ] it.",
                "aggressive": 12, "charisma": 9, "intelligence": 11,
            },
            {
                "flavor": "Cornered and desperate, the bandit throws a handful of blinding powder at your face!",
                "prompt": "Shielding your eyes, you [ ______ ] it.",
                "aggressive": 9, "charisma": 11, "intelligence": 12,
            },
        ],
    },
    {
        "name": "Spider",
        "modifier": "must_use_two_vowels",
        "rounds": [
            {
                "flavor": "A massive spider drops from the ceiling, its many eyes glistening. It skitters toward you with terrifying speed.",
                "prompt": "You brace yourself and [ ______ ] the spider.",
                "aggressive": 11, "charisma": 9, "intelligence": 12,
            },
            {
                "flavor": "The spider scuttles up the wall and leaps at your face! Venom drips from its fangs.",
                "prompt": "You dodge aside and [ ______ ] the spider.",
                "aggressive": 12, "charisma": 11, "intelligence": 9,
            },
            {
                "flavor": "Wounded but furious, the spider spins a web strand and swings straight at you, fangs bared.",
                "prompt": "With quick reflexes, you [ ______ ] the spider.",
                "aggressive": 9, "charisma": 12, "intelligence": 11,
            },
        ],
    },
    {
        "name": "Ghost",
        "modifier": "no_vowel_start",
        "rounds": [
            {
                "flavor": "A wailing ghost drifts through the wall, its translucent form flickering. An icy chill fills the air.",
                "prompt": "You steel your nerves and [ ______ ] the ghost.",
                "aggressive": 12, "charisma": 11, "intelligence": 9,
            },
            {
                "flavor": "The ghost lets out a piercing shriek that rattles your bones. It phases through your guard!",
                "prompt": "You focus your will and [ ______ ] the ghost.",
                "aggressive": 9, "charisma": 12, "intelligence": 11,
            },
            {
                "flavor": "The ghost gathers dark energy into a spectral orb, its form flickering between rage and sorrow.",
                "prompt": "You stand tall and [ ______ ] the ghost.",
                "aggressive": 11, "charisma": 9, "intelligence": 12,
            },
        ],
    },
]

BOSS_POOL: list[dict] = [
    {
        "name": "Dragon",
        "modifier": "boss_vowel_double",
        "rounds": [
            {
                "flavor": "The ground shakes. A massive red dragon descends, smoke curling from its nostrils. It fixes its burning gaze on you.",
                "prompt": "With everything on the line, you [ ______ ] the dragon.",
                "aggressive": 18, "charisma": 15, "intelligence": 17,
            },
            {
                "flavor": "The dragon rears back, inhaling deeply. Flames gather in its throat — it's about to breathe fire!",
                "prompt": "You dive for cover and [ ______ ] the dragon.",
                "aggressive": 17, "charisma": 18, "intelligence": 15,
            },
            {
                "flavor": "The dragon's wings are tattered, its breath ragged. It lets out a deafening roar and lunges with claws bared.",
                "prompt": "This is it. You [ ______ ] the dragon.",
                "aggressive": 15, "charisma": 17, "intelligence": 18,
            },
        ],
    },
    {
        "name": "Lich King",
        "modifier": "boss_highest_length",
        "rounds": [
            {
                "flavor": "A throne of bones rises before you. Upon it sits the Lich King, crowned in frost. His hollow gaze pierces your soul.",
                "prompt": "You raise your weapon and [ ______ ] the Lich King.",
                "aggressive": 17, "charisma": 18, "intelligence": 15,
            },
            {
                "flavor": "The Lich King raises a skeletal hand. Ice shards form in the air, each one aimed at your heart.",
                "prompt": "You weave between the shards and [ ______ ] the Lich King.",
                "aggressive": 18, "charisma": 15, "intelligence": 17,
            },
            {
                "flavor": "The Lich King descends from his throne, a blade of frozen shadow in his grip. The air itself freezes around you.",
                "prompt": "With a final cry, you [ ______ ] the Lich King.",
                "aggressive": 15, "charisma": 17, "intelligence": 18,
            },
        ],
    },
]

# ── Potions ──────────────────────────────────────────────────────────────────
# One-time-use items.  Key → {name, description, effect}

POTIONS: dict[str, dict] = {
    "shuffle": {
        "name": "Shuffle Potion",
        "description": "Shuffle your hand into your deck and redraw.",
        "effect": "shuffle",
    },
    "healing": {
        "name": "Healing Potion",
        "description": "Restore 5 HP.",
        "effect": "healing",
    },
    "wildcard": {
        "name": "Wildcard Potion",
        "description": "Add a wildcard (*) to your hand. It disappears after use.",
        "effect": "wildcard",
    },
}

POTION_KEYS: list[str] = list(POTIONS.keys())

# ── Accessories ──────────────────────────────────────────────────────────────
# Permanent items.  Key → {name, description, effect}

ACCESSORIES: dict[str, dict] = {
    "extra_draw": {
        "name": "Lucky Charm",
        "description": "Draw +1 card at the start of each round.",
        "effect": "extra_draw",
    },
    "wildcard_plus": {
        "name": "Star Pendant",
        "description": "Wildcards (*) are worth +1 point.",
        "effect": "wildcard_plus",
    },
    "double_letter": {
        "name": "Twin Ring",
        "description": "Using two of the same letter in a word gives +2 points.",
        "effect": "double_letter",
    },
    "vowel_bonus": {
        "name": "Vowel Charm",
        "description": "Using two or more vowels in a word gives +1 point.",
        "effect": "vowel_bonus",
    },
    "long_word": {
        "name": "Sage's Tome",
        "description": "Words of 5+ letters earn +3 bonus points.",
        "effect": "long_word",
    },
    "consonant_bonus": {
        "name": "Stone Amulet",
        "description": "Using 3+ consonants in a word gives +2 points.",
        "effect": "consonant_bonus",
    },
    "vitality_core": {
        "name": "Vitality Core",
        "description": "Grants +3 maximum health.",
        "effect": "vitality_core",
    },
}

ACCESSORY_KEYS: list[str] = list(ACCESSORIES.keys())
