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


# ── Button ───────────────────────────────────────────────────────────────────

class Button:
    """A clickable rectangle with text."""

    def __init__(
        self, rect: pygame.Rect, text: str,
        font: pygame.font.Font | None = None,
        color: tuple = BUTTON_COLOR,
        hover_color: tuple = BUTTON_HOVER,
        text_color: tuple = TEXT_COLOR,
        disabled: bool = False,
    ):
        self.rect = rect
        self.text = text
        self.font = font or _make_font(28)
        self.color = color
        self.hover_color = hover_color
        self.text_color = text_color
        self.disabled = disabled
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

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Return ``True`` if clicked."""
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                return True
        return False

    def draw(self, screen: pygame.Surface, font: pygame.font.Font,
             small_font: pygame.font.Font):
        bg = CARD_SELECTED if self.selected else CARD_COLOR
        y_offset = -8 if self.selected else 0
        r = self.rect.move(0, y_offset)
        pygame.draw.rect(screen, bg, r, border_radius=6)
        border_c = ACCENT_COLOR if self.letter == '*' else CARD_BORDER
        pygame.draw.rect(screen, border_c, r, width=2, border_radius=6)

        # letter
        letter_surf = font.render(self.letter.upper(), True, (20, 20, 30))
        lx = r.centerx - letter_surf.get_width() // 2
        ly = r.centery - letter_surf.get_height() // 2 - 4
        screen.blit(letter_surf, (lx, ly))

        # point value
        pts = LETTER_VALUES.get(self.letter, 0)
        pt_surf = small_font.render(str(pts), True, (80, 80, 100))
        px = r.right - pt_surf.get_width() - 6
        py = r.bottom - pt_surf.get_height() - 4
        screen.blit(pt_surf, (px, py))


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

    def handle_event(self, event: pygame.event.Event):
        if event.type == pygame.MOUSEMOTION:
            self._hovered = self.rect.collidepoint(event.pos)

    def draw(self, screen: pygame.Surface, small_font: pygame.font.Font):
        acc = ACCESSORIES.get(self.key, {})
        name = acc.get("name", "???")
        desc = acc.get("description", "")

        color = BUTTON_HOVER if self._hovered else PANEL_COLOR
        pygame.draw.rect(screen, color, self.rect, border_radius=6)
        pygame.draw.rect(screen, SUCCESS_COLOR, self.rect, width=2, border_radius=6)

        # Full name centered in the icon
        name_surf = small_font.render(name, True, TEXT_COLOR)
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
        self._result_data: dict | None = None
        self._result_timer: int = 0
        self._error_message: str = ""

        # Potions & accessories
        self._potion_buttons: list[PotionButton] = []
        self._accessory_icons: list[AccessoryIcon] = []

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
            case GameState.PLAY_WORD:
                self._play_word_event(event)
            case GameState.RESULT:
                self._result_event(event)
            case GameState.GAME_OVER:
                self._game_over_event(event)
            case GameState.VICTORY:
                self._victory_event(event)

    def _update(self, dt: int):
        if self.state == GameState.RESULT:
            self._result_timer -= dt
            if self._result_timer <= 0:
                self._result_timer = 0
                self._advance_after_result()

    def _draw(self):
        self.screen.fill(BG_COLOR)
        match self.state:
            case GameState.MAIN_MENU:
                self._draw_main_menu()
            case GameState.ARCHETYPE_SELECT:
                self._draw_archetype()
            case GameState.ENCOUNTER:
                self._draw_encounter()
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
                    self.engine = GameEngine(key)
                    self.engine.next_encounter()
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
                    req = self.engine.choose_approach(approach)
                    self._build_card_buttons()
                    self._build_potion_buttons()
                    self._build_accessory_icons()
                    self._current_word = []
                    self._error_message = ""
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

        # encounter name & flavor
        enc = eng.current_encounter
        rd = eng.current_round_data
        enc_name = eng.encounter_name
        _draw_text_center(self.screen, f"Blocked by a {enc_name}",
                          self.heading_font, ACCENT_COLOR, 150)
        if rd:
            _draw_text_center(self.screen, rd["flavor"], self.body_font,
                              TEXT_COLOR, 210)

        # modifier display
        modifier_key = enc.get("modifier")
        if modifier_key:
            mod = BOSS_MODIFIERS.get(modifier_key) or MODIFIERS.get(modifier_key)
            if mod:
                mod_text = f"⚡ Modifier: {mod['name']}"
                _draw_text_center(self.screen, mod_text, self.small_font,
                                  ACCENT_COLOR, 250)
                _draw_text_center(self.screen, mod['description'], self.small_font,
                                  (200, 200, 220), 275)

        # approach buttons
        if rd:
            approaches = [
                ("aggressive", f"Aggressive (Req: {max(1, rd['aggressive'] + eng.aggressive_bonus)} pts)"),
                ("charisma", f"Charisma (Req: {rd['charisma']} pts)"),
                ("intelligence", f"Intelligence (Req: {rd['intelligence']} pts)"),
            ]
        else:
            approaches = []
        self._approach_buttons: list[tuple[str, Button]] = []
        for i, (key, label) in enumerate(approaches):
            y = 400 + i * 70
            btn = Button(
                pygame.Rect((WINDOW_W - 400) // 2, y, 400, 56),
                label, self.body_font,
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

    # ── PLAY WORD (Phase B) ──────────────────────────────────────────────

    def _build_card_buttons(self):
        """Rebuild card buttons from the engine's current hand."""
        self._card_buttons = []
        hand = self.engine.hand
        for i, letter in enumerate(hand):
            cb = CardButton(letter, i)
            self._card_buttons.append(cb)

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
        """Position card buttons in a row at ~2/3 vertical."""
        n = len(self._card_buttons)
        total_w = n * CARD_W + (n - 1) * CARD_GAP
        start_x = (WINDOW_W - total_w) // 2
        y = WINDOW_H * 2 // 3 - CARD_H // 2
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
        # card clicks
        for cb in self._card_buttons:
            if cb.handle_event(event):
                if cb.selected:
                    # deselect
                    cb.selected = False
                    self._current_word.remove(cb.letter)
                else:
                    cb.selected = True
                    self._current_word.append(cb.letter)
                self._error_message = ""
                return

        # potion clicks
        for pb in self._potion_buttons:
            if pb.handle_event(event):
                result = self.engine.use_potion(pb.index)
                if result:
                    # Rebuild UI after potion use
                    self._build_card_buttons()
                    self._build_potion_buttons()
                    self._current_word = []
                    self._error_message = f"Used {result['name']}!"
                return

        # accessory hover
        for ai in self._accessory_icons:
            ai.handle_event(event)

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            # submit
            if self._submit_btn and not self._submit_btn.disabled and self._submit_btn.rect.collidepoint(event.pos):
                word = "".join(self._current_word)
                self._result_data = self.engine.play_word(word)
                self._result_timer = 2500  # ms
                self.state = GameState.RESULT
                return

            # clear
            if self._clear_btn and self._clear_btn.rect.collidepoint(event.pos):
                for cb in self._card_buttons:
                    cb.selected = False
                self._current_word = []
                self._error_message = ""

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

        # deck / discard counts (top-right)
        deck_text = f"Deck: {eng.deck_size}  |  Discard: {eng.discard_size}"
        deck_surf = self.small_font.render(deck_text, True, (160, 160, 200))
        self.screen.blit(deck_surf, (WINDOW_W - deck_surf.get_width() - 30, 24))

        # ── info text (upper-middle, ~1/3 vertical) ──────────────────
        info_y = WINDOW_H // 3

        # encounter name
        enc_name = eng.encounter_name
        if enc_name:
            _draw_text_center(self.screen, f"Blocked by a {enc_name}",
                              self.body_font, ACCENT_COLOR, info_y - 60)

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

        # current word display
        word_display = "".join(self._current_word).upper() if self._current_word else "___"
        word_color = ACCENT_COLOR if self._current_word else (100, 100, 120)
        _draw_text_center(self.screen, word_display, self.heading_font,
                          word_color, info_y + 130)

        # live score preview
        modifier_violated = False
        modifier_penalty = 0
        modifier_type = None
        modifier_detail = ""
        if self._current_word:
            word_str = "".join(self._current_word)
            preview_score = eng.calculate_score(word_str)
            req = eng.current_requirement
            # Check modifier for preview
            mod_result = eng.check_modifier_preview(word_str)
            modifier_violated = mod_result["violated"]
            modifier_penalty = mod_result["penalty"] if modifier_violated else 0
            modifier_type = mod_result.get("type")
            modifier_detail = mod_result.get("detail", "")

            if modifier_violated and modifier_type == "blocking":
                # Blocking rules: show score without penalty, don't show (-X mod)
                effective_preview = preview_score
                score_text = f"Score: {effective_preview} pts / {req} pts"
                score_color = SUCCESS_COLOR if effective_preview >= req else DANGER_COLOR
            else:
                # Penalty modifiers: show effective score with penalty
                effective_preview = max(0, preview_score - modifier_penalty)
                score_text = f"Score: {effective_preview} pts / {req} pts"
                if modifier_violated:
                    score_text += f"  (-{modifier_penalty} mod)"
                score_color = SUCCESS_COLOR if effective_preview >= req else DANGER_COLOR
            _draw_text_center(self.screen, score_text, self.small_font,
                              score_color, info_y + 175)

        # error message
        if self._error_message:
            _draw_text_center(self.screen, self._error_message, self.body_font,
                              DANGER_COLOR, info_y + 180)

        # ── cards (lower-middle, ~2/3 vertical) ──────────────────────
        self._layout_cards()
        for cb in self._card_buttons:
            cb.draw(self.screen, self.card_font, self.small_font)

        # submit / clear buttons (just below cards)
        card_y = WINDOW_H * 2 // 3 - CARD_H // 2
        btn_y = card_y + CARD_H + 10
        submit_disabled = len(self._current_word) == 0 or (modifier_violated and modifier_type == "blocking")
        self._submit_btn = Button(
            pygame.Rect(WINDOW_W // 2 + 20, btn_y, 160, 48),
            "Submit Word", self.small_font,
            disabled=submit_disabled,
        )
        self._clear_btn = Button(
            pygame.Rect(WINDOW_W // 2 - 180, btn_y, 160, 48),
            "Clear", self.small_font,
        )
        self._submit_btn.draw(self.screen)
        self._clear_btn.draw(self.screen)

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
        for ai in self._accessory_icons:
            ai.draw(self.screen, self.small_font)

    # ── RESULT overlay ───────────────────────────────────────────────────

    def _result_event(self, event: pygame.event.Event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._result_timer = 0
            self._advance_after_result()

    def _draw_result_overlay(self):
        # dim background
        overlay = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))

        data = self._result_data
        if data is None:
            return

        if not data["valid"]:
            narrative = data.get("narrative", data["error"])
            _draw_text_center(self.screen, narrative, self.body_font,
                              DANGER_COLOR, 240)
        else:
            score = data["score"]
            req = data["requirement"]
            resolved = data.get("resolved_word", "")
            narrative = data.get("narrative", "")

            # narrative message
            y = 200
            if narrative:
                _draw_text_center(self.screen, narrative, self.body_font,
                                  TEXT_COLOR, y)
                y += 40

            # show the resolved word
            if resolved:
                _draw_text_center(self.screen, f"Word: {resolved.upper()}",
                                  self.body_font, ACCENT_COLOR, y)
                y += 36

            # score line
            effective_score = data.get("effective_score", score)
            if data["round_success"]:
                _draw_text_center(self.screen,
                                  f"Score: {effective_score}/{req}  —  No damage!",
                                  self.body_font, SUCCESS_COLOR, y)
            else:
                dmg = data["damage_to_player"]
                _draw_text_center(self.screen,
                                  f"Score: {effective_score}/{req}  —  Took {dmg} damage!",
                                  self.body_font, DANGER_COLOR, y)
            y += 36

            # modifier violation message
            if data.get("modifier_violated"):
                _draw_text_center(self.screen, data["modifier_message"],
                                  self.small_font, ACCENT_COLOR, y)
                y += 30

        _draw_text_center(self.screen, "Click to continue...", self.small_font,
                          (160, 160, 180), 320)

    def _advance_after_result(self):
        """Move to the next state after the result overlay."""
        eng = self.engine

        # invalid words: stay on the same round, go back to word entry
        if self._result_data and not self._result_data.get("valid"):
            if eng.is_game_over:
                self.state = GameState.GAME_OVER
            else:
                self._build_card_buttons()
                self._build_potion_buttons()
                self._build_accessory_icons()
                self._current_word = []
                self._error_message = ""
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
                eng.next_encounter()
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
