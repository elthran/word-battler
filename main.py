"""Word Battler — PyGame UI and state machine."""

import sys
from enum import Enum, auto
import pygame
from engine import GameEngine
from data import LETTER_VALUES, ARCHETYPES, MAX_HP, POTIONS, ACCESSORIES, MODIFIERS, BOSS_MODIFIERS, ENCOUNTERS_BEFORE_BOSS

# ── Constants ───────────────────────────────────────────────────────────────
WINDOW_W, WINDOW_H = 1500, 800
FPS = 60

# Colours (R, G, B)
BG_COLOR       = (24, 24, 36)
PANEL_COLOR    = (40, 40, 60)
BUTTON_COLOR   = (70, 70, 110)
BUTTON_HOVER   = (100, 100, 160)
BUTTON_DISABLED = (50, 50, 70)
TEXT_COLOR     = (230, 230, 240)
ACCENT_COLOR   = (220, 180, 60)   # gold
DANGER_COLOR   = (220, 60, 60)    # red
SUCCESS_COLOR  = (60, 200, 100)   # green
WILDCARD_COLOR = (200, 160, 40)   # darker gold
CARD_COLOR     = (240, 240, 250)
CARD_SELECTED  = (140, 140, 160)
CARD_BORDER    = (60, 60, 80)

# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_font(size: int, bold: bool = False) -> pygame.font.Font:
    return pygame.font.Font(None, size)


def _draw_text_center(
    screen: pygame.Surface, text: str, font: pygame.font.Font,
    color: tuple, y: int,
):
    surf = font.render(text, True, color)
    x = (WINDOW_W - surf.get_width()) // 2
    screen.blit(surf, (x, y))


def _draw_text_left(
    screen: pygame.Surface, text: str, font: pygame.font.Font,
    color: tuple, x: int, y: int,
):
    surf = font.render(text, True, color)
    screen.blit(surf, (x, y))


def _draw_text_center_multiline(
    screen: pygame.Surface, text: str, font: pygame.font.Font,
    color: tuple, y: int, max_width: int | None = None,
) -> int:
    """Draw text centered, splitting on '. ' for natural line breaks.

    Returns the y position after the last line drawn.
    """
    if max_width is None:
        max_width = WINDOW_W - 100

    # Split on sentence boundaries: ". " or "! " or "? "
    sentences = []
    current = ""
    i = 0
    while i < len(text):
        current += text[i]
        if text[i] in ('.', '!', '?') and i + 1 < len(text) and text[i + 1] == ' ':
            sentences.append(current.strip())
            current = ""
            i += 2  # skip the punctuation and the space
            continue
        i += 1
    if current.strip():
        sentences.append(current.strip())

    # If no sentence breaks found, just render as one line
    if len(sentences) <= 1:
        surf = font.render(text, True, color)
        x = (WINDOW_W - surf.get_width()) // 2
        screen.blit(surf, (x, y))
        return y + surf.get_height()

    line_height = font.get_height() + 4
    for sentence in sentences:
        surf = font.render(sentence, True, color)
        x = (WINDOW_W - surf.get_width()) // 2
        screen.blit(surf, (x, y))
        y += line_height
    return y


# ── Button ───────────────────────────────────────────────────────────────────

class Button:
    """A clickable rectangle with text and optional subtitle."""

    def __init__(
        self, rect: pygame.Rect, text: str,
        font: pygame.font.Font | None = None,
        color: tuple = BUTTON_COLOR,
        hover_color: tuple = BUTTON_HOVER,
        text_color: tuple = TEXT_COLOR,
        disabled: bool = False,
        subtitle: str = "",
        subtitle_color: tuple | None = None,
    ):
        self.rect = rect
        self.text = text
        self.font = font or _make_font(28)
        self.color = color
        self.hover_color = hover_color
        self.text_color = text_color
        self.disabled = disabled
        self.subtitle = subtitle
        self.subtitle_color = subtitle_color or (180, 200, 220)
        self._hovered = False

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Return ``True`` if the button was clicked."""
        if self.disabled:
            return False
        if event.type == pygame.MOUSEMOTION:
            self._hovered = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                return True
        return False

    def draw(self, screen: pygame.Surface):
        color = self.hover_color if self._hovered and not self.disabled else self.color
        if self.disabled:
            color = BUTTON_DISABLED
        pygame.draw.rect(screen, color, self.rect, border_radius=8)
        pygame.draw.rect(screen, CARD_BORDER, self.rect, width=2, border_radius=8)

        if self.subtitle:
            # Two-line layout: subtitle on top, main text below
            sub_surf = self.font.render(self.subtitle, True, self.subtitle_color)
            main_surf = self.font.render(self.text, True, self.text_color)
            total_h = sub_surf.get_height() + main_surf.get_height() + 4
            start_y = self.rect.centery - total_h // 2

            sx = self.rect.centerx - sub_surf.get_width() // 2
            screen.blit(sub_surf, (sx, start_y))

            mx = self.rect.centerx - main_surf.get_width() // 2
            screen.blit(main_surf, (mx, start_y + sub_surf.get_height() + 4))
        else:
            surf = self.font.render(self.text, True, self.text_color)
            tx = self.rect.centerx - surf.get_width() // 2
            ty = self.rect.centery - surf.get_height() // 2
            screen.blit(surf, (tx, ty))


# ── Card (hand) ──────────────────────────────────────────────────────────────

CARD_W, CARD_H = 80, 110
CARD_GAP = 10


class CardButton:
    """A single card in the player's hand."""

    def __init__(self, letter: str, index: int):
        self.letter = letter
        self.index = index
        self.selected = False
        self.rect = pygame.Rect(0, 0, CARD_W, CARD_H)
        self.highlight: str | None = None  # "gold" or "red" or None
        self.chosen_letter: str = ""       # the actual letter chosen for a wildcard

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Return ``True`` if clicked."""
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                return True
        return False

    def draw(self, screen: pygame.Surface, font: pygame.font.Font,
             small_font: pygame.font.Font):
        y_offset = -8 if self.selected else 0
        r = self.rect.move(0, y_offset)

        if self.highlight == "red":
            bg = CARD_COLOR
            border_c = DANGER_COLOR
            border_w = 3
        elif self.selected:
            bg = CARD_SELECTED
            border_c = CARD_BORDER
            border_w = 2
        elif self.highlight == "gold":
            bg = CARD_COLOR
            border_c = ACCENT_COLOR
            border_w = 2
        elif self.letter == '*':
            bg = CARD_COLOR
            border_c = WILDCARD_COLOR
            border_w = 2
        else:
            bg = CARD_COLOR
            border_c = CARD_BORDER
            border_w = 2

        pygame.draw.rect(screen, bg, r, border_radius=6)
        pygame.draw.rect(screen, border_c, r, width=border_w, border_radius=6)

        # Red glow overlay — semi-transparent red on top of the card
        if self.highlight == "red":
            glow = pygame.Surface((r.width, r.height), pygame.SRCALPHA)
            glow.fill((220, 40, 40, 60))  # bright red, ~24% opacity
            screen.blit(glow, (r.x, r.y))

        # letter
        display_letter = self.chosen_letter.upper() if self.selected and self.chosen_letter else self.letter.upper()
        letter_surf = font.render(display_letter, True, (20, 20, 30))
        lx = r.centerx - letter_surf.get_width() // 2
        ly = r.centery - letter_surf.get_height() // 2 - 4
        screen.blit(letter_surf, (lx, ly))

        # point value
        pts = LETTER_VALUES.get(self.chosen_letter if self.selected and self.chosen_letter else self.letter, 0)
        pt_surf = small_font.render(str(pts), True, (80, 80, 100))
        px = r.right - pt_surf.get_width() - 6
        py = r.bottom - pt_surf.get_height() - 4
        screen.blit(pt_surf, (px, py))


# ── Noun Card (noun round) ───────────────────────────────────────────────────

NOUN_CARD_W, NOUN_CARD_H = 200, 130
NOUN_CARD_GAP = 20


class NounCardButton:
    """A noun card displayed during noun rounds — wider, showing word + points."""

    def __init__(self, noun_data: dict, index: int):
        self.word = noun_data["word"]
        self.points = noun_data["points"]
        self.index = index
        self.selected = False
        self.rect = pygame.Rect(0, 0, NOUN_CARD_W, NOUN_CARD_H)
        self._hovered = False

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Return True if clicked."""
        if event.type == pygame.MOUSEMOTION:
            self._hovered = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                return True
        return False

    def draw(self, screen: pygame.Surface, font: pygame.font.Font,
             small_font: pygame.font.Font):
        y_offset = -8 if self.selected else 0
        r = self.rect.move(0, y_offset)

        if self.selected:
            bg = CARD_SELECTED
            border_c = ACCENT_COLOR
            border_w = 3
        elif self._hovered:
            bg = BUTTON_HOVER
            border_c = ACCENT_COLOR
            border_w = 2
        else:
            bg = CARD_COLOR
            border_c = CARD_BORDER
            border_w = 2

        pygame.draw.rect(screen, bg, r, border_radius=8)
        pygame.draw.rect(screen, border_c, r, width=border_w, border_radius=8)

        # Word
        word_surf = font.render(self.word.upper(), True, (20, 20, 30))
        wx = r.centerx - word_surf.get_width() // 2
        wy = r.centery - word_surf.get_height() // 2 - 10
        screen.blit(word_surf, (wx, wy))

        # Points
        pts_text = f"+{self.points} pts"
        pts_surf = small_font.render(pts_text, True, ACCENT_COLOR)
        px = r.centerx - pts_surf.get_width() // 2
        py = wy + word_surf.get_height() + 4
        screen.blit(pts_surf, (px, py))


# ── Potion button ────────────────────────────────────────────────────────────

POTION_W, POTION_H = 130, 56
POTION_GAP = 8


class PotionButton:
    """A clickable potion in the 1×3 grid."""

    def __init__(self, potion_key: str, index: int):
        self.key = potion_key
        self.index = index
        self.rect = pygame.Rect(0, 0, POTION_W, POTION_H)
        self._hovered = False

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Return True if clicked."""
        if event.type == pygame.MOUSEMOTION:
            self._hovered = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                return True
        return False

    def draw(self, screen: pygame.Surface, small_font: pygame.font.Font):
        potion = POTIONS.get(self.key, {})
        name = potion.get("name", "???")
        desc = potion.get("description", "")

        color = BUTTON_HOVER if self._hovered else BUTTON_COLOR
        pygame.draw.rect(screen, color, self.rect, border_radius=8)
        pygame.draw.rect(screen, ACCENT_COLOR, self.rect, width=2, border_radius=8)

        # Full name centered in the button
        name_surf = small_font.render(name, True, TEXT_COLOR)
        nx = self.rect.centerx - name_surf.get_width() // 2
        ny = self.rect.centery - name_surf.get_height() // 2
        screen.blit(name_surf, (nx, ny))

        # Tooltip on hover
        if self._hovered:
            self._draw_tooltip(screen, small_font, name, desc)

    def _draw_tooltip(self, screen, font, name, desc):
        """Draw a tooltip above the potion."""
        pad = 8
        name_surf = font.render(name, True, TEXT_COLOR)
        desc_surf = font.render(desc, True, (200, 200, 220))
        tw = max(name_surf.get_width(), desc_surf.get_width()) + pad * 2
        th = name_surf.get_height() + desc_surf.get_height() + pad * 3
        tx = self.rect.centerx - tw // 2
        ty = self.rect.top - th - 6

        # Keep on screen
        tx = max(4, min(tx, WINDOW_W - tw - 4))
        ty = max(4, ty)

        pygame.draw.rect(screen, PANEL_COLOR, (tx, ty, tw, th), border_radius=6)
        pygame.draw.rect(screen, ACCENT_COLOR, (tx, ty, tw, th), width=1, border_radius=6)
        screen.blit(name_surf, (tx + pad, ty + pad))
        screen.blit(desc_surf, (tx + pad, ty + pad + name_surf.get_height() + 4))


# ── Accessory icon ───────────────────────────────────────────────────────────

ACC_W, ACC_H = 150, 40
ACC_GAP = 6


class AccessoryIcon:
    """A non-clickable accessory display with hover tooltip."""

    def __init__(self, acc_key: str, index: int):
        self.key = acc_key
        self.index = index
        self.rect = pygame.Rect(0, 0, ACC_W, ACC_H)
        self._hovered = False
        self.active = False  # set externally when the accessory's condition is met

    def handle_event(self, event: pygame.event.Event):
        if event.type == pygame.MOUSEMOTION:
            self._hovered = self.rect.collidepoint(event.pos)

    def draw(self, screen: pygame.Surface, small_font: pygame.font.Font):
        acc = ACCESSORIES.get(self.key, {})
        name = acc.get("name", "???")
        desc = acc.get("description", "")

        if self.active:
            color = (60, 50, 20)  # warm dark gold background
            border_color = ACCENT_COLOR
            border_width = 3
            text_color = ACCENT_COLOR
        elif self._hovered:
            color = BUTTON_HOVER
            border_color = SUCCESS_COLOR
            border_width = 2
            text_color = TEXT_COLOR
        else:
            color = PANEL_COLOR
            border_color = SUCCESS_COLOR
            border_width = 2
            text_color = TEXT_COLOR

        pygame.draw.rect(screen, color, self.rect, border_radius=6)
        pygame.draw.rect(screen, border_color, self.rect, width=border_width, border_radius=6)

        # Full name centered in the icon
        name_surf = small_font.render(name, True, text_color)
        nx = self.rect.centerx - name_surf.get_width() // 2
        ny = self.rect.centery - name_surf.get_height() // 2
        screen.blit(name_surf, (nx, ny))

        # Tooltip on hover
        if self._hovered:
            self._draw_tooltip(screen, small_font, name, desc)

    def _draw_tooltip(self, screen, font, name, desc):
        pad = 8
        name_surf = font.render(name, True, TEXT_COLOR)
        desc_surf = font.render(desc, True, (200, 200, 220))
        tw = max(name_surf.get_width(), desc_surf.get_width()) + pad * 2
        th = name_surf.get_height() + desc_surf.get_height() + pad * 3
        tx = self.rect.centerx - tw // 2
        ty = self.rect.top - th - 6

        tx = max(4, min(tx, WINDOW_W - tw - 4))
        ty = max(4, ty)

        pygame.draw.rect(screen, PANEL_COLOR, (tx, ty, tw, th), border_radius=6)
        pygame.draw.rect(screen, SUCCESS_COLOR, (tx, ty, tw, th), width=1, border_radius=6)
        screen.blit(name_surf, (tx + pad, ty + pad))
        screen.blit(desc_surf, (tx + pad, ty + pad + name_surf.get_height() + 4))


# ── State machine ────────────────────────────────────────────────────────────

class GameState(Enum):
    MAIN_MENU = auto()
    ARCHETYPE_SELECT = auto()
    ENCOUNTER = auto()
    NOUN_SELECT = auto()
    PLAY_WORD = auto()
    RESULT = auto()
    GAME_OVER = auto()
    VICTORY = auto()


# ── Main App ─────────────────────────────────────────────────────────────────

class App:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
        pygame.display.set_caption("Word Battler")
        self.clock = pygame.time.Clock()
        self.running = True

        # fonts
        self.title_font = _make_font(64, bold=True)
        self.heading_font = _make_font(44, bold=True)
        self.body_font = _make_font(32)
        self.small_font = _make_font(22)
        self.card_font = _make_font(38, bold=True)

        # state
        self.state = GameState.MAIN_MENU
        self.engine: GameEngine | None = None

        # PLAY_WORD state
        self._card_buttons: list[CardButton] = []
        self._current_word: list[str] = []       # letters chosen so far
        self._wildcard_letters: list[str] = []    # chosen wildcard letters in click order
        self._result_data: dict | None = None
        self._result_timer: int = 0
        self._error_message: str = ""

        # OpenAI preview state
        self._preview_data: dict | None = None   # cached API result from preview
        self._preview_word: str = ""             # the word that was previewed
        self._loading: bool = False              # True while waiting for API response
        self._wildcard_prompt: bool = False      # True while waiting for wildcard letter input
        self._wildcard_card_index: int = -1      # which card triggered the wildcard prompt

        # Potions & accessories
        self._potion_buttons: list[PotionButton] = []
        self._accessory_icons: list[AccessoryIcon] = []

        # Noun round state
        self._noun_card_buttons: list[NounCardButton] = []
        self._noun_selected_index: int = -1

    # ── Main loop ────────────────────────────────────────────────────────

    def run(self):
        while self.running:
            dt = self.clock.tick(FPS)
            self._handle_events()
            self._update(dt)
            self._draw()
            pygame.display.flip()
        pygame.quit()
        sys.exit()

    def _handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            self._dispatch_event(event)

    def _dispatch_event(self, event: pygame.event.Event):
        match self.state:
            case GameState.MAIN_MENU:
                self._main_menu_event(event)
            case GameState.ARCHETYPE_SELECT:
                self._archetype_event(event)
            case GameState.ENCOUNTER:
                self._encounter_event(event)
            case GameState.NOUN_SELECT:
                self._noun_select_event(event)
            case GameState.PLAY_WORD:
                self._play_word_event(event)
            case GameState.RESULT:
                self._result_event(event)
            case GameState.GAME_OVER:
                self._game_over_event(event)
            case GameState.VICTORY:
                self._victory_event(event)

    def _update(self, dt: int):
        pass

    def _draw(self):
        self.screen.fill(BG_COLOR)
        match self.state:
            case GameState.MAIN_MENU:
                self._draw_main_menu()
            case GameState.ARCHETYPE_SELECT:
                self._draw_archetype()
            case GameState.ENCOUNTER:
                self._draw_encounter()
            case GameState.NOUN_SELECT:
                self._draw_noun_select()
            case GameState.PLAY_WORD:
                self._draw_play_word()
            case GameState.RESULT:
                self._draw_play_word()
                self._draw_result_overlay()
            case GameState.GAME_OVER:
                self._draw_game_over()
            case GameState.VICTORY:
                self._draw_victory()

    # ── MAIN MENU ────────────────────────────────────────────────────────

    def _main_menu_event(self, event: pygame.event.Event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self._start_btn.rect.collidepoint(event.pos):
                self.state = GameState.ARCHETYPE_SELECT
            elif self._quit_btn.rect.collidepoint(event.pos):
                self.running = False

    def _draw_main_menu(self):
        _draw_text_center(self.screen, "WORD BATTLER", self.title_font,
                          ACCENT_COLOR, 120)
        _draw_text_center(self.screen, "A roguelike word game",
                          self.body_font, TEXT_COLOR, 190)

        self._start_btn = Button(
            pygame.Rect((WINDOW_W - 220) // 2, 300, 220, 56),
            "Start Game", self.body_font,
        )
        self._quit_btn = Button(
            pygame.Rect((WINDOW_W - 220) // 2, 380, 220, 56),
            "Quit", self.body_font,
        )
        self._start_btn.draw(self.screen)
        self._quit_btn.draw(self.screen)

    # ── ARCHETYPE SELECT ─────────────────────────────────────────────────

    def _archetype_event(self, event: pygame.event.Event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for key, btn in self._arch_buttons:
                if btn.rect.collidepoint(event.pos):
                    self._loading = True
                    self._draw()
                    pygame.display.flip()
                    self.engine = GameEngine(key)
                    self.engine.next_encounter()
                    self._loading = False
                    self._enter_encounter()

    def _draw_archetype(self):
        _draw_text_center(self.screen, "Choose Your Archetype",
                          self.heading_font, ACCENT_COLOR, 60)

        keys = list(ARCHETYPES.keys())
        self._arch_buttons: list[tuple[str, Button]] = []
        for i, key in enumerate(keys):
            arch = ARCHETYPES[key]
            y = 160 + i * 120
            btn = Button(
                pygame.Rect((WINDOW_W - 500) // 2, y, 500, 90),
                f"{arch['name']}: {arch['description']}",
                self.body_font,
            )
            self._arch_buttons.append((key, btn))
            btn.draw(self.screen)

        if self._loading:
            _draw_text_center(self.screen, "Loading...", self.body_font,
                              ACCENT_COLOR, WINDOW_H - 80)

    # ── ENCOUNTER (Phase A) ──────────────────────────────────────────────

    def _enter_encounter(self):
        """Build UI elements when entering the encounter screen."""
        self._build_potion_buttons()
        self._build_accessory_icons()
        self.state = GameState.ENCOUNTER

    def _encounter_event(self, event: pygame.event.Event):
        # hover tooltips for accessories and potions (not clickable on encounter screen)
        for ai in self._accessory_icons:
            ai.handle_event(event)
        for pb in self._potion_buttons:
            pb.handle_event(event)

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for approach, btn in self._approach_buttons:
                if btn.rect.collidepoint(event.pos):
                    self._loading = True
                    self._draw()
                    pygame.display.flip()
                    req = self.engine.choose_approach(approach)
                    self._loading = False
                    self._current_word = []
                    self._wildcard_letters = []
                    self._build_card_buttons()
                    self._build_potion_buttons()
                    self._build_accessory_icons()
                    self._error_message = ""
                    # Noun round: go to noun select first
                    if not self.engine.expects_verb:
                        self._enter_noun_select()
                    else:
                        self.state = GameState.PLAY_WORD

    def _draw_encounter(self):
        eng = self.engine

        # HP
        hp_text = f"HP: {eng.hp}/{eng.max_hp}"
        hp_color = DANGER_COLOR if eng.hp <= 2 else SUCCESS_COLOR
        _draw_text_left(self.screen, hp_text, self.body_font, hp_color, 30, 20)

        # encounter counter
        total = eng.encounters_cleared + 1
        max_total = ENCOUNTERS_BEFORE_BOSS + 1
        enc_text = f"Encounter {total}/{max_total}"
        _draw_text_center(self.screen, enc_text, self.small_font, TEXT_COLOR, 20)

        # round counter
        round_text = f"Round {eng.current_round}/{eng.rounds_per_encounter}"
        _draw_text_center(self.screen, round_text, self.body_font, ACCENT_COLOR, 50)

        # boss warning
        if eng.is_boss_encounter:
            _draw_text_center(self.screen, "⚠  BOSS  ⚠", self.heading_font,
                              DANGER_COLOR, 100)

        # bonus round indicator
        if eng.is_bonus_round:
            _draw_text_center(self.screen, "⚡ BONUS ROUND ⚡", self.heading_font,
                              DANGER_COLOR, 100)

        # encounter HP bar
        next_y = self._draw_encounter_hp_bar(130)

        # encounter name & flavor (multiline)
        enc = eng.current_encounter
        rd = eng.current_round_data
        enc_name = eng.encounter_name
        _draw_text_center(self.screen, f"Blocked by a {enc_name}",
                          self.heading_font, ACCENT_COLOR, next_y)
        next_y += 60
        if rd:
            next_y = _draw_text_center_multiline(
                self.screen, rd["flavor"], self.body_font,
                TEXT_COLOR, next_y,
            )

        # modifier display
        modifier_key = enc.get("modifier")
        if modifier_key:
            mod = BOSS_MODIFIERS.get(modifier_key) or MODIFIERS.get(modifier_key)
            if mod:
                next_y += 10
                mod_text = f"⚡ Modifier: {mod['name']}"
                _draw_text_center(self.screen, mod_text, self.small_font,
                                  ACCENT_COLOR, next_y)
                next_y += 25
                _draw_text_center(self.screen, mod['description'], self.small_font,
                                  (200, 200, 220), next_y)
                next_y += 30

        # approach buttons with generated descriptions inside
        if rd:
            approach_descs = eng.approach_descriptions
            approaches = [
                ("aggressive", f"Aggressive (Req: {max(1, rd['aggressive'] + eng.aggressive_bonus)} pts)",
                 approach_descs.get("aggressive", "")),
                ("charisma", f"Charisma (Req: {rd['charisma']} pts)",
                 approach_descs.get("charisma", "")),
                ("intelligence", f"Intelligence (Req: {rd['intelligence']} pts)",
                 approach_descs.get("intelligence", "")),
            ]
        else:
            approaches = []

        next_y = max(next_y + 10, 360)
        self._approach_buttons: list[tuple[str, Button]] = []
        for i, (key, label, desc) in enumerate(approaches):
            y = next_y + i * 80
            btn = Button(
                pygame.Rect((WINDOW_W - 400) // 2, y, 400, 68),
                label, self.small_font,
                subtitle=desc,
            )
            self._approach_buttons.append((key, btn))
            btn.draw(self.screen)

        # potions (bottom-right)
        self._layout_potions()
        for pb in self._potion_buttons:
            pb.draw(self.screen, self.small_font)

        # accessories (bottom-left)
        self._layout_accessories()
        for ai in self._accessory_icons:
            ai.draw(self.screen, self.small_font)

        # loading indicator
        if self._loading:
            _draw_text_center(self.screen, "Loading...", self.body_font,
                              ACCENT_COLOR, WINDOW_H - 80)

    def _draw_encounter_hp_bar(self, y: int):
        """Draw the encounter HP bar at the given y position. Returns next y."""
        eng = self.engine
        if eng.encounter_max_hp <= 0:
            return y
        bar_w = 400
        bar_h = 20
        bar_x = (WINDOW_W - bar_w) // 2

        # Label
        label = f"{eng.encounter_name} HP: {eng.encounter_hp}/{eng.encounter_max_hp}"
        _draw_text_center(self.screen, label, self.small_font, ACCENT_COLOR, y)
        y += 22

        # Background
        pygame.draw.rect(self.screen, (60, 60, 80), (bar_x, y, bar_w, bar_h), border_radius=4)
        # HP fill
        ratio = eng.encounter_hp / eng.encounter_max_hp
        fill_w = int(bar_w * ratio)
        if ratio > 0.5:
            fill_color = SUCCESS_COLOR
        elif ratio > 0.25:
            fill_color = ACCENT_COLOR
        else:
            fill_color = DANGER_COLOR
        if fill_w > 0:
            pygame.draw.rect(self.screen, fill_color, (bar_x, y, fill_w, bar_h), border_radius=4)
        # Border
        pygame.draw.rect(self.screen, CARD_BORDER, (bar_x, y, bar_w, bar_h), width=1, border_radius=4)
        return y + bar_h + 10

    # ── NOUN SELECT ──────────────────────────────────────────────────────

    def _enter_noun_select(self):
        """Draw 3 noun cards and let the player pick one."""
        eng = self.engine
        eng.draw_noun_hand()
        self._noun_card_buttons = []
        for i, noun in enumerate(eng.noun_hand):
            self._noun_card_buttons.append(NounCardButton(noun, i))
        self._noun_selected_index = -1
        self.state = GameState.NOUN_SELECT

    def _noun_select_event(self, event: pygame.event.Event):
        for nb in self._noun_card_buttons:
            if nb.handle_event(event):
                self._noun_selected_index = nb.index
                for b in self._noun_card_buttons:
                    b.selected = (b.index == nb.index)
                return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self._noun_confirm_btn and not self._noun_confirm_btn.disabled \
                    and self._noun_confirm_btn.rect.collidepoint(event.pos):
                if self._noun_selected_index >= 0:
                    eng = self.engine
                    eng.choose_noun(self._noun_selected_index)
                    # Now go to PLAY_WORD for the word entry
                    self._current_word = []
                    self._wildcard_letters = []
                    self._build_card_buttons()
                    self._build_potion_buttons()
                    self._build_accessory_icons()
                    self._error_message = ""
                    self._preview_data = None
                    self._preview_word = ""
                    self._wildcard_prompt = False
                    self.state = GameState.PLAY_WORD

    def _draw_noun_select(self):
        eng = self.engine

        # HP
        hp_text = f"HP: {eng.hp}/{eng.max_hp}"
        hp_color = DANGER_COLOR if eng.hp <= 2 else SUCCESS_COLOR
        _draw_text_left(self.screen, hp_text, self.body_font, hp_color, 30, 20)

        # encounter counter
        total = eng.encounters_cleared + 1
        max_total = ENCOUNTERS_BEFORE_BOSS + 1
        enc_text = f"Encounter {total}/{max_total}"
        _draw_text_center(self.screen, enc_text, self.small_font, TEXT_COLOR, 20)

        # round counter
        round_text = f"Round {eng.current_round}/{eng.rounds_per_encounter}"
        _draw_text_center(self.screen, round_text, self.body_font, ACCENT_COLOR, 50)

        # bonus round indicator
        if eng.is_bonus_round:
            _draw_text_center(self.screen, "⚡ BONUS ROUND ⚡", self.heading_font,
                              DANGER_COLOR, 90)

        # encounter HP bar
        next_y = self._draw_encounter_hp_bar(130)

        # encounter name
        enc_name = eng.encounter_name
        if enc_name:
            _draw_text_center(self.screen, f"Blocked by a {enc_name}",
                              self.body_font, ACCENT_COLOR, next_y)
            next_y += 40

        # requirement
        req_text = f"Requirement: {eng.current_requirement} pts"
        _draw_text_center(self.screen, req_text, self.body_font, ACCENT_COLOR, next_y)
        next_y += 30

        # noun round indicator (no prompt yet — that comes after noun selection)
        _draw_text_center(self.screen, "🎒 Noun Round — pick an item, then play an adjective!",
                          self.body_font, ACCENT_COLOR, next_y)
        next_y += 50

        # Noun cards
        n = len(self._noun_card_buttons)
        total_w = n * NOUN_CARD_W + (n - 1) * NOUN_CARD_GAP
        start_x = (WINDOW_W - total_w) // 2
        for i, nb in enumerate(self._noun_card_buttons):
            nb.rect.x = start_x + i * (NOUN_CARD_W + NOUN_CARD_GAP)
            nb.rect.y = next_y
            nb.draw(self.screen, self.body_font, self.small_font)

        # Confirm button
        btn_y = next_y + NOUN_CARD_H + 20
        self._noun_confirm_btn = Button(
            pygame.Rect((WINDOW_W - 200) // 2, btn_y, 200, 48),
            "Confirm Noun", self.small_font,
            disabled=self._noun_selected_index < 0,
        )
        self._noun_confirm_btn.draw(self.screen)

        # Chosen noun display
        if self._noun_selected_index >= 0:
            noun = eng.noun_hand[self._noun_selected_index]
            chosen_text = f"Selected: {noun['word'].upper()} (+{noun['points']} pts)"
            _draw_text_center(self.screen, chosen_text, self.body_font,
                              ACCENT_COLOR, btn_y + 60)

    # ── PLAY WORD (Phase B) ──────────────────────────────────────────────

    def _build_resolved_word(self) -> str | None:
        """Build the fully resolved word by replacing wildcards with chosen letters.
        Returns None if there are no wildcards (engine handles resolution)."""
        if '*' not in self._current_word:
            return None
        wild_choices = list(self._wildcard_letters)
        chars = []
        wi = 0
        for ch in self._current_word:
            if ch == '*' and wi < len(wild_choices):
                chars.append(wild_choices[wi])
                wi += 1
            else:
                chars.append(ch)
        return "".join(chars)

    def _build_card_buttons(self):
        """Rebuild card buttons from the engine's current hand."""
        self._card_buttons = []
        hand = self.engine.hand
        for i, letter in enumerate(hand):
            cb = CardButton(letter, i)
            self._card_buttons.append(cb)
        self._refresh_card_highlights()

    def _refresh_card_highlights(self):
        """Update card highlights based on the current modifier and word."""
        word = "".join(self._current_word)
        red_letters = self.engine.get_red_highlight_letters(word)
        for cb in self._card_buttons:
            if cb.letter in red_letters:
                cb.highlight = "red"
            else:
                cb.highlight = None

    def _build_potion_buttons(self):
        """Rebuild potion buttons from the engine's current potions."""
        self._potion_buttons = []
        for i, key in enumerate(self.engine.potions):
            self._potion_buttons.append(PotionButton(key, i))

    def _build_accessory_icons(self):
        """Rebuild accessory icons from the engine's current accessories."""
        self._accessory_icons = []
        for i, key in enumerate(self.engine.accessories):
            self._accessory_icons.append(AccessoryIcon(key, i))

    def _layout_cards(self):
        """Position card buttons in a row near the bottom."""
        n = len(self._card_buttons)
        total_w = n * CARD_W + (n - 1) * CARD_GAP
        start_x = (WINDOW_W - total_w) // 2
        y = WINDOW_H * 3 // 4 - CARD_H // 2
        for i, cb in enumerate(self._card_buttons):
            cb.rect.x = start_x + i * (CARD_W + CARD_GAP)
            cb.rect.y = y

    def _layout_potions(self):
        """Position potion buttons in a row at the bottom-right."""
        n = len(self._potion_buttons)
        if n == 0:
            return
        total_w = n * POTION_W + (n - 1) * POTION_GAP
        start_x = WINDOW_W - total_w - 30
        y = WINDOW_H - POTION_H - 30
        for i, pb in enumerate(self._potion_buttons):
            pb.rect.x = start_x + i * (POTION_W + POTION_GAP)
            pb.rect.y = y

    def _layout_accessories(self):
        """Position accessory icons in a row at the bottom-left."""
        n = len(self._accessory_icons)
        if n == 0:
            return
        total_w = n * ACC_W + (n - 1) * ACC_GAP
        start_x = 30
        y = WINDOW_H - ACC_H - 30
        for i, ai in enumerate(self._accessory_icons):
            ai.rect.x = start_x + i * (ACC_W + ACC_GAP)
            ai.rect.y = y

    def _play_word_event(self, event: pygame.event.Event):
        # Wildcard prompt: waiting for a single letter keypress
        if self._wildcard_prompt:
            if event.type == pygame.KEYDOWN:
                if event.unicode.isalpha() and len(event.unicode) == 1:
                    ch = event.unicode.lower()
                    self._current_word.append('*')  # engine needs '*' for wildcards
                    self._wildcard_letters.append(ch)  # track in click order
                    # Store the chosen letter on the specific wildcard card
                    for cb in self._card_buttons:
                        if cb.index == self._wildcard_card_index:
                            cb.chosen_letter = ch
                            break
                    self._wildcard_prompt = False
                    self._wildcard_card_index = -1
                    self._error_message = ""
                    self._preview_data = None
                    self._preview_word = ""
                return
            # Ignore all other events while in wildcard prompt
            return

        # card clicks
        for cb in self._card_buttons:
            if cb.handle_event(event):
                if self._loading:
                    return
                if cb.selected:
                    # deselect
                    cb.selected = False
                    if cb.letter == '*':
                        # Remove the last wildcard entry matching this card's chosen letter
                        self._current_word.remove('*')
                        if cb.chosen_letter and cb.chosen_letter in self._wildcard_letters:
                            self._wildcard_letters.remove(cb.chosen_letter)
                        cb.chosen_letter = ""
                    else:
                        self._current_word.remove(cb.letter)
                elif cb.letter == '*':
                    # Wildcard: prompt for a letter instead of adding '*'
                    cb.selected = True
                    self._wildcard_prompt = True
                    self._wildcard_card_index = cb.index
                else:
                    cb.selected = True
                    self._current_word.append(cb.letter)
                self._error_message = ""
                self._preview_data = None  # word changed, invalidate preview
                self._preview_word = ""
                self._refresh_card_highlights()
                return

        # potion clicks
        for pb in self._potion_buttons:
            if pb.handle_event(event):
                if self._loading:
                    return
                result = self.engine.use_potion(pb.index)
                if result:
                    # Rebuild UI after potion use
                    self._current_word = []
                    self._wildcard_letters = []
                    self._build_card_buttons()
                    self._build_potion_buttons()
                    self._error_message = f"Used {result['name']}!"
                    self._preview_data = None
                    self._preview_word = ""
                    self._wildcard_prompt = False
                return

        # accessory hover
        for ai in self._accessory_icons:
            ai.handle_event(event)

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self._loading:
                return

            # preview score
            if (self._preview_btn and not self._preview_btn.disabled
                    and self._preview_btn.rect.collidepoint(event.pos)):
                word = "".join(self._current_word)
                resolved = self._build_resolved_word()
                self._loading = True
                self._draw()
                pygame.display.flip()
                result = self.engine.preview_openai_score(word, resolved_word=resolved)
                self._loading = False
                if result is not None:
                    self._preview_data = result
                    self._preview_word = word
                    self._error_message = ""
                else:
                    self._error_message = "Cannot preview — not a valid word."
                return

            # submit
            if self._submit_btn and not self._submit_btn.disabled and self._submit_btn.rect.collidepoint(event.pos):
                word = "".join(self._current_word)
                resolved = self._build_resolved_word()
                # Use cached preview data if it matches the current word
                cached = self._preview_data if self._preview_word == word else None
                self._loading = True
                self._draw()
                pygame.display.flip()
                # Use play_noun if a noun card was chosen, otherwise play_word
                if self.engine.chosen_noun is not None:
                    self._result_data = self.engine.play_noun(word, cached_openai_result=cached,
                                                              resolved_word=resolved)
                else:
                    self._result_data = self.engine.play_word(word, cached_openai_result=cached,
                                                              resolved_word=resolved)
                self._loading = False
                self._result_timer = 2500  # ms
                self._preview_data = None
                self._preview_word = ""
                self.state = GameState.RESULT
                return

            # clear
            if self._clear_btn and self._clear_btn.rect.collidepoint(event.pos):
                for cb in self._card_buttons:
                    cb.selected = False
                self._current_word = []
                self._wildcard_letters = []
                self._error_message = ""
                self._preview_data = None
                self._preview_word = ""
                self._wildcard_prompt = False
                self._refresh_card_highlights()

            # shuffle
            if self._shuffle_btn and self._shuffle_btn.rect.collidepoint(event.pos):
                self.engine.shuffle_hand()
                self._current_word = []
                self._wildcard_letters = []
                self._build_card_buttons()
                self._error_message = ""
                self._preview_data = None
                self._preview_word = ""
                self._wildcard_prompt = False

    def _draw_play_word(self):
        eng = self.engine

        # ── top bar ──────────────────────────────────────────────────
        # HP
        hp_text = f"HP: {eng.hp}/{eng.max_hp}"
        hp_color = DANGER_COLOR if eng.hp <= 2 else SUCCESS_COLOR
        _draw_text_left(self.screen, hp_text, self.body_font, hp_color, 30, 20)

        # encounter counter
        total = eng.encounters_cleared + 1
        max_total = ENCOUNTERS_BEFORE_BOSS + 1
        enc_text = f"Encounter {total}/{max_total}"
        _draw_text_center(self.screen, enc_text, self.small_font, TEXT_COLOR, 20)

        # round counter
        round_text = f"Round {eng.current_round}/{eng.rounds_per_encounter}"
        _draw_text_center(self.screen, round_text, self.body_font, ACCENT_COLOR, 50)

        # bonus round indicator
        if eng.is_bonus_round:
            _draw_text_center(self.screen, "⚡ BONUS ROUND ⚡", self.heading_font,
                              DANGER_COLOR, 90)

        # encounter HP bar
        next_y = self._draw_encounter_hp_bar(130)

        # deck / discard counts (top-right)
        deck_text = f"Deck: {eng.deck_size}  |  Discard: {eng.discard_size}"
        deck_surf = self.small_font.render(deck_text, True, (160, 160, 200))
        self.screen.blit(deck_surf, (WINDOW_W - deck_surf.get_width() - 30, 24))

        # ── info text (upper-middle) ──────────────────────────────────
        info_y = next_y + 20

        # encounter name
        enc_name = eng.encounter_name
        if enc_name:
            _draw_text_center(self.screen, f"Blocked by a {enc_name}",
                              self.body_font, ACCENT_COLOR, info_y)
            info_y += 40

        # requirement
        req_text = f"Requirement: {eng.current_requirement} pts"
        _draw_text_center(self.screen, req_text, self.body_font, ACCENT_COLOR, info_y)

        # prompt
        rd = eng.current_round_data
        prompt = rd["prompt"] if rd else "Choose your word..."
        _draw_text_center(self.screen, prompt, self.body_font, TEXT_COLOR, info_y + 30)

        # modifier reminder
        enc = eng.current_encounter
        if enc:
            modifier_key = enc.get("modifier")
            if modifier_key:
                mod = BOSS_MODIFIERS.get(modifier_key) or MODIFIERS.get(modifier_key)
                if mod:
                    mod_text = f"⚡ {mod['name']}"
                    _draw_text_center(self.screen, mod_text, self.small_font,
                                      ACCENT_COLOR, info_y + 90)

        # verb/noun expectation indicator
        if eng.expects_verb:
            pos_text = "📝 Expects a VERB"
            pos_color = (180, 140, 60)  # warm amber
        else:
            pos_text = "📝 Expects an ADJECTIVE"
            pos_color = (140, 180, 220)  # cool blue
        _draw_text_center(self.screen, pos_text, self.small_font,
                          pos_color, info_y + 115)

        # noun card indicator
        noun = eng.chosen_noun
        if noun:
            noun_text = f"🎒 Noun: {noun['word'].upper()} (+{noun['points']} pts)"
            _draw_text_center(self.screen, noun_text, self.small_font,
                              ACCENT_COLOR, info_y + 140)

        # current word display — show chosen letters for wildcards
        if self._current_word:
            # Use _wildcard_letters which tracks wildcard choices in click order
            wild_choices = list(self._wildcard_letters)
            display_chars = []
            wi = 0
            for ch in self._current_word:
                if ch == '*' and wi < len(wild_choices):
                    display_chars.append(wild_choices[wi])
                    wi += 1
                else:
                    display_chars.append(ch)
            word_display = "".join(display_chars).upper()
        else:
            word_display = "___"
        word_color = ACCENT_COLOR if self._current_word else (100, 100, 120)
        _draw_text_center(self.screen, word_display, self.heading_font,
                          word_color, info_y + 130)

        # ── Score preview & modifier display ─────────────────────────
        modifier_violated = False
        modifier_penalty = 0
        modifier_type = None
        modifier_detail = ""
        preview_score = 0
        req = eng.current_requirement

        if self._current_word:
            word_str = "".join(self._current_word)
            preview_score = eng.calculate_score(word_str)
            # Check modifier for preview
            mod_result = eng.check_modifier_preview(word_str)
            modifier_violated = mod_result["violated"]
            modifier_penalty = mod_result["penalty"] if modifier_violated else 0
            modifier_type = mod_result.get("type")
            modifier_detail = mod_result.get("detail", "")

        # ── OpenAI modifier display ──────────────────────────────────
        mod_y = info_y + 170
        mod_line_h = 22

        if self._preview_data is not None and self._preview_word == "".join(self._current_word):
            # Show actual values from preview
            pd = self._preview_data
            ex = pd["exoticness"]
            ab = pd["additive_bonus"]
            ab_sign = "+" if ab >= 0 else ""
            ex_text = f"Exotic: {ex}/10  →  {ab_sign}{ab}  (-2 to +3)"
            _draw_text_center(self.screen, ex_text, self.small_font, ACCENT_COLOR, mod_y)

            su = pd["suitability"]
            sm = pd["suitability_multiplier"]
            su_text = f"Suitable: {su}/10  →  ×{sm:.2f}  (×0.75 to ×1.25)"
            _draw_text_center(self.screen, su_text, self.small_font, ACCENT_COLOR, mod_y + mod_line_h)

            un = pd["uniqueness"]
            um = pd["uniqueness_multiplier"]
            un_text = f"Unique: {un}/10  →  ×{um:.2f}  (×0.75 to ×1.25)"
            _draw_text_center(self.screen, un_text, self.small_font, ACCENT_COLOR, mod_y + mod_line_h * 2)

            # Word type match display
            pos_match = pd.get("pos_match", True)
            pos_penalty = pd.get("pos_penalty", 0.0)
            if pos_penalty > 0:
                expected = "VERB" if eng.expects_verb else "ADJECTIVE"
                pos_text = f"NOT AN {expected}  →  ×0.5 penalty!"
                pos_color = DANGER_COLOR
            else:
                pos_text = "Word type: match  →  no penalty"
                pos_color = SUCCESS_COLOR
            _draw_text_center(self.screen, pos_text, self.small_font, pos_color, mod_y + mod_line_h * 3)

            # Show actual projected score
            if modifier_violated and modifier_type == "blocking":
                effective_preview = preview_score
            else:
                effective_preview = max(0, preview_score - modifier_penalty)
            projected = max(0, int((effective_preview + ab) * sm * um))
            if pos_penalty > 0:
                projected = max(0, int(projected * pos_penalty))
            score_text = f"Score: {projected} pts / {req} pts"
            score_color = SUCCESS_COLOR if projected >= req else DANGER_COLOR
            _draw_text_center(self.screen, score_text, self.small_font,
                              score_color, mod_y + mod_line_h * 4)
        elif self._current_word:
            # Show ? with min/max ranges
            ex_text = "Exotic: ?  (-2 to +3)"
            _draw_text_center(self.screen, ex_text, self.small_font, (140, 140, 180), mod_y)

            su_text = "Suitable: ?  (×0.75 to ×1.25)"
            _draw_text_center(self.screen, su_text, self.small_font, (140, 140, 180), mod_y + mod_line_h)

            un_text = "Unique: ?  (×0.75 to ×1.25)"
            _draw_text_center(self.screen, un_text, self.small_font, (140, 140, 180), mod_y + mod_line_h * 2)

            pos_text = "Word type: ?  (×0.5 penalty if wrong)"
            _draw_text_center(self.screen, pos_text, self.small_font, (140, 140, 180), mod_y + mod_line_h * 3)

            # Show raw score + min/max range in brackets
            if modifier_violated and modifier_type == "blocking":
                effective_preview = preview_score
            else:
                effective_preview = max(0, preview_score - modifier_penalty)
            min_score = max(0, int((effective_preview - 2) * 0.75 * 0.75 * 0.5))
            max_score = max(0, int((effective_preview + 3) * 1.25 * 1.25))
            score_text = f"Score: {effective_preview} pts ({min_score}–{max_score}) / {req} pts"
            score_color = SUCCESS_COLOR if max_score >= req else DANGER_COLOR
            _draw_text_center(self.screen, score_text, self.small_font,
                              score_color, mod_y + mod_line_h * 4)

        # error message
        if self._error_message:
            _draw_text_center(self.screen, self._error_message, self.body_font,
                              DANGER_COLOR, mod_y + mod_line_h * 4 + 30)

        # loading indicator
        if self._loading:
            _draw_text_center(self.screen, "Loading...", self.body_font,
                              ACCENT_COLOR, mod_y + mod_line_h * 4 + 30)

        # wildcard prompt indicator
        if self._wildcard_prompt:
            _draw_text_center(self.screen, "Type a letter for the wildcard...",
                              self.body_font, ACCENT_COLOR, mod_y + mod_line_h * 4 + 30)

        # ── cards (lower-middle, ~2/3 vertical) ──────────────────────
        self._layout_cards()

        for cb in self._card_buttons:
            cb.draw(self.screen, self.card_font, self.small_font)

        # submit / clear / shuffle / preview buttons (just below cards)
        card_y = WINDOW_H * 3 // 4 - CARD_H // 2
        btn_y = card_y + CARD_H + 10
        btn_w = 130
        btn_gap = 10
        total_w = 4 * btn_w + 3 * btn_gap
        start_x = (WINDOW_W - total_w) // 2
        all_disabled = self._loading
        submit_disabled = all_disabled or len(self._current_word) == 0 or (modifier_violated and modifier_type == "blocking")
        preview_disabled = all_disabled or len(self._current_word) == 0

        self._clear_btn = Button(
            pygame.Rect(start_x, btn_y, btn_w, 48),
            "Clear", self.small_font,
            disabled=all_disabled,
        )
        self._shuffle_btn = Button(
            pygame.Rect(start_x + btn_w + btn_gap, btn_y, btn_w, 48),
            "Shuffle", self.small_font,
            disabled=all_disabled,
        )
        self._preview_btn = Button(
            pygame.Rect(start_x + 2 * (btn_w + btn_gap), btn_y, btn_w, 48),
            "Preview Score", self.small_font,
            disabled=preview_disabled,
        )
        self._submit_btn = Button(
            pygame.Rect(start_x + 3 * (btn_w + btn_gap), btn_y, btn_w, 48),
            "Submit Word", self.small_font,
            disabled=submit_disabled,
        )
        self._clear_btn.draw(self.screen)
        self._shuffle_btn.draw(self.screen)
        self._preview_btn.draw(self.screen)
        self._submit_btn.draw(self.screen)

        # reason text below submit button when blocked
        if submit_disabled and modifier_detail:
            reason_text = modifier_detail
            _draw_text_center(self.screen, reason_text, self.small_font,
                              DANGER_COLOR, btn_y + 56)

        # potions (bottom-right)
        self._layout_potions()
        for pb in self._potion_buttons:
            pb.draw(self.screen, self.small_font)

        # accessories (bottom-left)
        self._layout_accessories()
        word_str = "".join(self._current_word)
        for ai in self._accessory_icons:
            ai.active = bool(word_str) and eng.check_accessory_active(ai.key, word_str)
            ai.draw(self.screen, self.small_font)

    # ── RESULT overlay ───────────────────────────────────────────────────

    def _result_event(self, event: pygame.event.Event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._result_timer = 0
            self._advance_after_result()

    def _draw_result_overlay(self):
        # Full dark overlay so text is clearly readable
        overlay = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 200))
        self.screen.blit(overlay, (0, 0))

        data = self._result_data
        if data is None:
            return

        if not data["valid"]:
            narrative = data.get("narrative", data["error"])
            _draw_text_center(self.screen, narrative, self.body_font,
                              DANGER_COLOR, 240)
            _draw_text_center(self.screen, "Click to continue...", self.small_font,
                              (160, 160, 180), 320)
            return

        score = data["score"]
        req = data["requirement"]
        resolved = data.get("resolved_word", "")
        effective_score = data.get("effective_score", score)
        ob = data.get("openai_bonus", {})
        modifier_penalty = data.get("modifier_penalty", 0)
        modifier_violated = data.get("modifier_violated", False)

        # ── Draw a solid panel behind the results ─────────────────────
        panel_w = 600
        panel_h = 540
        panel_x = (WINDOW_W - panel_w) // 2
        panel_y = 100
        panel_rect = pygame.Rect(panel_x, panel_y, panel_w, panel_h)
        pygame.draw.rect(self.screen, PANEL_COLOR, panel_rect, border_radius=12)
        pygame.draw.rect(self.screen, ACCENT_COLOR, panel_rect, width=2, border_radius=12)

        y = panel_y + 20
        line_h = 28

        # ── 1. Your word ──────────────────────────────────────────────
        if resolved:
            _draw_text_center(self.screen, f"Your word: {resolved.upper()}",
                              self.heading_font, ACCENT_COLOR, y)
            y += 46

        # ── 2. Modifier breakdown ─────────────────────────────────────
        _draw_text_center(self.screen, "── Bonuses ──", self.small_font,
                          (180, 180, 200), y)
        y += line_h

        # Exoticness
        exoticness = ob.get("exoticness", 0)
        additive_bonus = ob.get("additive_bonus", 0)
        ab_sign = "+" if additive_bonus >= 0 else ""
        exotic_text = f"Exotic: {exoticness}/10  →  {ab_sign}{additive_bonus} score  (-2 to +3)"
        _draw_text_center(self.screen, exotic_text, self.small_font,
                          ACCENT_COLOR, y)
        y += line_h

        # Suitability
        suitability = ob.get("suitability", 0)
        suitability_mult = ob.get("suitability_multiplier", 1.0)
        suit_text = f"Suitable: {suitability}/10  →  ×{suitability_mult:.2f}  (×0.75 to ×1.25)"
        _draw_text_center(self.screen, suit_text, self.small_font,
                          ACCENT_COLOR, y)
        y += line_h

        # Uniqueness
        uniqueness = ob.get("uniqueness", 0)
        uniqueness_mult = ob.get("uniqueness_multiplier", 1.0)
        uniq_text = f"Unique: {uniqueness}/10  →  ×{uniqueness_mult:.2f}  (×0.75 to ×1.25)"
        _draw_text_center(self.screen, uniq_text, self.small_font,
                          ACCENT_COLOR, y)
        y += line_h

        # Word type match
        pos_match = ob.get("pos_match", True)
        pos_penalty = ob.get("pos_penalty", 0.0)
        if pos_penalty > 0:
            expected = "VERB" if self.engine.expects_verb else "ADJECTIVE"
            pos_text = f"NOT AN {expected}  →  ×0.5 penalty!"
            pos_color = DANGER_COLOR
        else:
            pos_text = "Word type: match  →  no penalty"
            pos_color = SUCCESS_COLOR
        _draw_text_center(self.screen, pos_text, self.small_font, pos_color, y)
        y += line_h

        # Modifier penalty
        if modifier_violated and modifier_penalty > 0:
            penalty_text = f"Modifier penalty: -{modifier_penalty}"
            _draw_text_center(self.screen, penalty_text, self.small_font,
                              DANGER_COLOR, y)
            y += line_h

        # ── 3. Score calculation ──────────────────────────────────────
        y += 4
        _draw_text_center(self.screen, "── Score Calculation ──", self.small_font,
                          (180, 180, 200), y)
        y += line_h

        calc_lines = []
        calc_lines.append(f"Raw letter score: {score}")
        if modifier_penalty > 0:
            calc_lines.append(f"  − Modifier penalty: -{modifier_penalty}")
            calc_lines.append(f"  = After penalty: {max(0, score - modifier_penalty)}")
        if additive_bonus != 0:
            ab_sign = "+" if additive_bonus > 0 else ""
            calc_lines.append(f"  {ab_sign} Exotic bonus: {ab_sign}{additive_bonus}")
        if suitability_mult != 1.0:
            calc_lines.append(f"  × Suitable multiplier: ×{suitability_mult:.2f}")
        if uniqueness_mult != 1.0:
            calc_lines.append(f"  × Unique multiplier: ×{uniqueness_mult:.2f}")
        if pos_penalty > 0:
            calc_lines.append(f"  × Wrong word type penalty: ×0.5")

        for line in calc_lines:
            _draw_text_center(self.screen, line, self.small_font,
                              TEXT_COLOR, y)
            y += line_h

        total_text = f"  = Total score: {effective_score}"
        _draw_text_center(self.screen, total_text, self.body_font,
                          ACCENT_COLOR, y)
        y += line_h + 6

        # ── 4. Result ─────────────────────────────────────────────────
        if data["round_success"]:
            _draw_text_center(self.screen,
                              f"✓ {effective_score} ≥ {req}  —  No damage!",
                              self.body_font, SUCCESS_COLOR, y)
        else:
            dmg = data["damage_to_player"]
            _draw_text_center(self.screen,
                              f"✗ {effective_score} < {req}  —  Took {dmg} damage!",
                              self.body_font, DANGER_COLOR, y)

        _draw_text_center(self.screen, "Click to continue...", self.small_font,
                          (160, 160, 180), y + 40)

    def _advance_after_result(self):
        """Move to the next state after the result overlay."""
        eng = self.engine

        # invalid words: stay on the same round, go back to word entry
        if self._result_data and not self._result_data.get("valid"):
            if eng.is_game_over:
                self.state = GameState.GAME_OVER
            else:
                self._current_word = []
                self._wildcard_letters = []
                self._build_card_buttons()
                self._build_potion_buttons()
                self._build_accessory_icons()
                self._error_message = ""
                self._preview_data = None
                self._preview_word = ""
                self._wildcard_prompt = False
                self.state = GameState.PLAY_WORD
            return

        if eng.is_game_over:
            self.state = GameState.GAME_OVER
            return

        # advance the round
        eng.advance_round()

        if eng.is_encounter_finished:
            # encounter is over — check victory or move to next
            if eng.is_victory:
                self.state = GameState.VICTORY
            else:
                self._loading = True
                self._draw()
                pygame.display.flip()
                eng.next_encounter()
                self._loading = False
                self._enter_encounter()
        else:
            # more rounds in this encounter — go back to approach selection
            self._enter_encounter()

    # ── GAME OVER ────────────────────────────────────────────────────────

    def _game_over_event(self, event: pygame.event.Event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self._go_again_btn.rect.collidepoint(event.pos):
                self.state = GameState.ARCHETYPE_SELECT
            elif self._go_menu_btn.rect.collidepoint(event.pos):
                self.state = GameState.MAIN_MENU

    def _draw_game_over(self):
        _draw_text_center(self.screen, "GAME OVER", self.title_font,
                          DANGER_COLOR, 160)
        cleared = self.engine.encounters_cleared
        _draw_text_center(self.screen, f"Encounters cleared: {cleared}",
                          self.body_font, TEXT_COLOR, 240)

        self._go_again_btn = Button(
            pygame.Rect((WINDOW_W - 220) // 2, 340, 220, 56),
            "Play Again", self.body_font,
        )
        self._go_menu_btn = Button(
            pygame.Rect((WINDOW_W - 220) // 2, 420, 220, 56),
            "Main Menu", self.body_font,
        )
        self._go_again_btn.draw(self.screen)
        self._go_menu_btn.draw(self.screen)

    # ── VICTORY ──────────────────────────────────────────────────────────

    def _victory_event(self, event: pygame.event.Event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self._vic_again_btn.rect.collidepoint(event.pos):
                self.state = GameState.ARCHETYPE_SELECT
            elif self._vic_menu_btn.rect.collidepoint(event.pos):
                self.state = GameState.MAIN_MENU

    def _draw_victory(self):
        _draw_text_center(self.screen, "VICTORY!", self.title_font,
                          SUCCESS_COLOR, 140)
        _draw_text_center(self.screen, "You defeated the Dragon!",
                          self.body_font, TEXT_COLOR, 220)
        _draw_text_center(self.screen,
                          f"HP remaining: {self.engine.hp}/{self.engine.max_hp}",
                          self.body_font, TEXT_COLOR, 260)

        self._vic_again_btn = Button(
            pygame.Rect((WINDOW_W - 220) // 2, 340, 220, 56),
            "Play Again", self.body_font,
        )
        self._vic_menu_btn = Button(
            pygame.Rect((WINDOW_W - 220) // 2, 420, 220, 56),
            "Main Menu", self.body_font,
        )
        self._vic_again_btn.draw(self.screen)
        self._vic_menu_btn.draw(self.screen)


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    App().run()
