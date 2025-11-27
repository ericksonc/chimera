"""
Visual effects widgets for Textual CLI.
Ported from cli/effects/display.py.
"""

import math
import random
import time
from enum import Enum

from rich.text import Text
from textual.app import RenderResult
from textual.widgets import Static

# --- Color System (Ported/Simplified) ---


def get_gray(brightness: int) -> str:
    """Get gray color hex for brightness level (-5 to 5)."""
    # Map -5..5 to 0..255
    # -5 -> 30 (very dark gray)
    # 0 -> 128 (middle gray)
    # 5 -> 255 (white)

    if brightness < -5:
        brightness = -5
    if brightness > 5:
        brightness = 5

    # Linear mapping for simplicity
    val = int(30 + (brightness + 5) * (225 / 10))
    return f"rgb({val},{val},{val})"


def get_brand_color(brightness: int) -> str:
    """Get brand teal color with brightness adjustment."""
    # Base teal: #00D4AA (R=0, G=212, B=170)
    # We'll just use the hex for now, maybe adjust opacity or lightness if needed.
    # For text, we often want it bright.
    if brightness >= 5:
        return "#00D4AA"  # Base
    elif brightness >= 0:
        return "#00A080"  # Darker
    else:
        return "#006050"  # Very dark


# --- Alien Spinner (Logic) ---


class SpinnerStyle(Enum):
    DOTS = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    DOTS_ALT = "⣾⣽⣻⢿⡿⣟⣯⣷"
    MINIMAL = "⠁⠂⠄⡀⢀⠠⠐⠈"
    BLOCKS = " ▂▃▄▅▆▇█▇▆▅▄▃▂"
    ARROWS = "←↖↑↗→↘↓↙"


class AlienSpinner:
    """Algorithmic rhythm spinner with organic feel."""

    def __init__(self, style: SpinnerStyle = SpinnerStyle.DOTS):
        self.frames = style.value
        self.index = 0
        self.base_interval = 0.08
        self.slow_phase = 0.0
        self.fast_phase = 0.0
        self.jitter = 0.0
        self.last_update = time.time()
        self.slow_period = 3.7
        self.fast_period = 1.3
        self.jitter_damping = 0.8

    def get_next_interval(self) -> float:
        now = time.time()
        dt = now - self.last_update
        self.slow_phase += dt / self.slow_period * 2 * 3.14159
        self.fast_phase += dt / self.fast_period * 2 * 3.14159

        slow_rhythm = math.sin(self.slow_phase) * 0.5
        fast_rhythm = math.sin(self.fast_phase) * 0.3

        self.jitter = self.jitter * self.jitter_damping + random.gauss(0, 0.1)
        self.jitter = max(-0.2, min(0.2, self.jitter))

        hiccup = 1.0
        if random.random() < 0.05:
            hiccup = random.uniform(0.5, 2.0)

        interval = self.base_interval * (1 + slow_rhythm + fast_rhythm + self.jitter) * hiccup
        interval = max(0.03, min(0.3, interval))
        self.last_update = now
        return interval

    def get_next_frame(self) -> str:
        if random.random() < 0.92:
            self.index = (self.index + 1) % len(self.frames)
        elif random.random() < 0.5:
            self.index = (self.index - 1) % len(self.frames)
        else:
            self.index = random.randint(0, len(self.frames) - 1)
        return self.frames[self.index]


# --- Matrix Effect (Logic) ---

THINKING_PHRASES = [
    "Initiating neural handshake...",
    "Reality is a construct of perception",
    "The ghost in the machine awakens",
    "Synchronizing quantum states",
    "Beyond the event horizon lies truth",
    "Consciousness uploaded successfully",
    "Time is not linear, it's recursive",
    "Decrypting reality matrix...",
    "Parsing multidimensional thoughts",
    "Quantum entanglement established",
    "Bridging synaptic pathways",
    "Transcending digital boundaries",
]

NOISE_CHARS = "!@#$%^&*()_+-=[]{}|;:,.<>?/~`0123456789█▓▒░╔╗╚╝║═╬╩╦╠╣"


class MatrixLogic:
    """Matrix-style encrypt/decrypt logic."""

    def __init__(self):
        self.phrases = THINKING_PHRASES.copy()
        random.shuffle(self.phrases)
        self.current_phrase_idx = 0
        self.transition_chars = []

    def get_next_phrase(self) -> str:
        phrase = self.phrases[self.current_phrase_idx]
        self.current_phrase_idx = (self.current_phrase_idx + 1) % len(self.phrases)
        return phrase.upper()  # Default to upper

    def encrypt_text(self, text: str, progress: float) -> str:
        if not self.transition_chars:
            self.transition_chars = list(range(len(text)))
            random.shuffle(self.transition_chars)

        glitch_rate = 0.1 + (progress * 0.5)
        chars_to_encrypt = int(len(text) * glitch_rate * progress)

        result = list(text)
        for i in self.transition_chars[:chars_to_encrypt]:
            if i < len(result) and result[i] != " ":
                result[i] = random.choice(NOISE_CHARS)
        return "".join(result)

    def decrypt_text(self, source: str, target: str, progress: float) -> str:
        if not self.transition_chars:
            self.transition_chars = list(range(max(len(source), len(target))))
            random.shuffle(self.transition_chars)

        source = source.ljust(len(target))
        chars_to_reveal = int(len(target) * progress)

        result = list(source)
        revealed_positions = set(self.transition_chars[:chars_to_reveal])

        for i in range(len(target)):
            if i in revealed_positions:
                result[i] = target[i]
            elif i < len(result) and result[i] == " ":
                result[i] = " "
            else:
                if random.random() > progress:
                    result[i] = random.choice(NOISE_CHARS)
                else:
                    result[i] = target[i] if i < len(target) else " "
        return "".join(result[: len(target)])


# --- Textual Widgets ---


class ThinkingIndicator(Static):
    """
    A widget that displays the Matrix/AlienSpinner effect.
    It runs its own animation loop via auto_refresh.
    """

    DEFAULT_CSS = """
    ThinkingIndicator {
        height: 1;
        margin: 1 0 1 8; /* Indent to match AssistantMessage */
        color: $accent;
    }
    """

    def on_mount(self) -> None:
        self.spinner = AlienSpinner()
        self.matrix = MatrixLogic()

        # Animation State
        self.current_phrase = self.matrix.get_next_phrase()
        self.next_phrase = ""
        self.phase = "display"  # display, flash, encrypt, decrypt
        self.phase_start_time = time.time()
        self.spinner_frame = self.spinner.get_next_frame()
        self.spinner_next_update = time.time() + self.spinner.get_next_interval()

        # Config
        self.display_duration = 2.0
        self.encrypt_duration = 1.0
        self.decrypt_duration = 1.0
        self.flash_delay = 0.1

        # Start animation loop (30 FPS is sufficient for text effects)
        self.auto_refresh = 1 / 30

    def render(self) -> RenderResult:
        now = time.time()

        # Update Spinner
        if now >= self.spinner_next_update:
            self.spinner_frame = self.spinner.get_next_frame()
            self.spinner_next_update = now + self.spinner.get_next_interval()

        # Update Matrix Text
        elapsed = now - self.phase_start_time
        text_content = self.current_phrase

        if self.phase == "display":
            if elapsed > self.display_duration:
                self.phase = "encrypt"
                self.phase_start_time = now
                self.matrix.transition_chars = []  # Reset for new transition

        elif self.phase == "encrypt":
            progress = min(1.0, elapsed / self.encrypt_duration)
            text_content = self.matrix.encrypt_text(self.current_phrase, progress)
            if progress >= 1.0:
                self.phase = "decrypt"
                self.phase_start_time = now
                self.next_phrase = self.matrix.get_next_phrase()
                self.matrix.transition_chars = []

        elif self.phase == "decrypt":
            progress = min(1.0, elapsed / self.decrypt_duration)
            # Note: decrypt takes encrypted source (which is just noise now) -> target
            # We approximate source as noise for visual simplicity or track exact state
            # Let's just use the previous encrypted state?
            # Actually, decrypt_text logic handles noise->target transition
            # We need a stable "source" noise string if we want it perfect,
            # but regenerating noise each frame looks like... noise.
            # So we pass a noisy string as source.
            noise_source = "".join(random.choice(NOISE_CHARS) for _ in range(len(self.next_phrase)))
            text_content = self.matrix.decrypt_text(noise_source, self.next_phrase, progress)

            if progress >= 1.0:
                self.phase = "display"
                self.phase_start_time = now
                self.current_phrase = self.next_phrase

        # Render
        # We use Rich Text to style the spinner and text separately
        output = Text()
        output.append(f"{self.spinner_frame}  ", style="bold #00D4AA")
        output.append(text_content, style="#00D4AA")

        return output
