"""Enhanced display module with status bars and visual elements."""

import asyncio
import random
import time
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from enum import Enum
import shutil

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live
from rich.layout import Layout
from rich.align import Align
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.columns import Columns
from rich.rule import Rule

# Import our color system
from .colors import get_gray, get_brand_color, interpolate_gray, GRAYS


# Matrix Effect Configuration
MIN_PHRASE_DISPLAY_TIME = 1.2    # Minimum time to show clear phrase
MAX_PHRASE_DISPLAY_TIME = 3.0    # Maximum time (set to 0 or None for fixed time)
ENCRYPT_DURATION = 1.0        # Time to encrypt to noise
DECRYPT_DURATION = 1.0        # Time to decrypt to next phrase
FLASH_DELAY = 0.1            # Time before flash sweep starts
FLASH_FPS = 60              # Frames per second for flash sweep

CAPITALIZATION = "upper"      # Options: "upper", "lower", "normal"
BRIGHTNESS = 7               # 0 = black, 10 = full electric teal (#00D4AA)

# Sci-fi phrases to cycle through while agent is processing
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

# Characters for the noise effect
NOISE_CHARS = '!@#$%^&*()_+-=[]{}|;:,.<>?/~`0123456789█▓▒░╔╗╚╝║═╬╩╦╠╣'


class SpinnerStyle(Enum):
    """Different spinner styles for variety."""
    DOTS = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    DOTS_ALT = "⣾⣽⣻⢿⡿⣟⣯⣷"
    MINIMAL = "⠁⠂⠄⡀⢀⠠⠐⠈"
    BLOCKS = "▁▂▃▄▅▆▇█▇▆▅▄▃▂"
    ARROWS = "←↖↑↗→↘↓↙"


class AlienSpinner:
    """Algorithmic rhythm spinner with organic feel."""
    
    def __init__(self, style: SpinnerStyle = SpinnerStyle.DOTS):
        """Initialize alien spinner.
        
        Args:
            style: Spinner style to use
        """
        self.frames = style.value
        self.index = 0
        self.base_interval = 0.08  # 80ms base
        
        # Rhythm components
        self.slow_phase = 0.0
        self.fast_phase = 0.0
        self.jitter = 0.0
        self.last_update = time.time()
        
        # Wave parameters
        self.slow_period = 3.7  # seconds
        self.fast_period = 1.3  # seconds
        self.jitter_damping = 0.8
    
    def get_next_interval(self) -> float:
        """Calculate next frame interval with algorithmic rhythm.
        
        Returns:
            Interval in seconds until next frame
        """
        now = time.time()
        dt = now - self.last_update
        
        # Update wave phases
        self.slow_phase += dt / self.slow_period * 2 * 3.14159
        self.fast_phase += dt / self.fast_period * 2 * 3.14159
        
        # Calculate rhythm components
        import math
        slow_rhythm = math.sin(self.slow_phase) * 0.5
        fast_rhythm = math.sin(self.fast_phase) * 0.3
        
        # Random walk jitter
        self.jitter = self.jitter * self.jitter_damping + random.gauss(0, 0.1)
        self.jitter = max(-0.2, min(0.2, self.jitter))
        
        # Occasional hiccups
        hiccup = 1.0
        if random.random() < 0.05:  # 5% chance
            hiccup = random.uniform(0.5, 2.0)
        
        # Combine all factors
        interval = self.base_interval * (1 + slow_rhythm + fast_rhythm + self.jitter) * hiccup
        
        # Clamp to reasonable bounds
        interval = max(0.03, min(0.3, interval))
        
        self.last_update = now
        return interval
    
    def get_next_frame(self) -> str:
        """Get next spinner frame with occasional reversals.
        
        Returns:
            Next frame character
        """
        if random.random() < 0.92:  # 92% normal progression
            self.index = (self.index + 1) % len(self.frames)
        elif random.random() < 0.5:  # 4% reverse
            self.index = (self.index - 1) % len(self.frames)
        else:  # 4% jump
            self.index = random.randint(0, len(self.frames) - 1)
        
        return self.frames[self.index]


# get_brand_color is now imported from colors.py


class Display:
    """Enhanced display with status bars and visual elements."""
    
    # Brand color calculated from brightness setting
    BRAND_COLOR = get_brand_color(BRIGHTNESS)
    
    def __init__(self):
        """Initialize enhanced display."""
        self.console = Console()
        self.spinner = AlienSpinner()
        self.status_data = {
            "model": "claude-3-sonnet",
            "context": 0,
            "tokens": 0,
            "connection": "connected",
            "git_branch": None,
            "current_dir": "~"
        }
    
    def get_terminal_size(self) -> Tuple[int, int]:
        """Get terminal width and height.
        
        Returns:
            Tuple of (width, height)
        """
        size = shutil.get_terminal_size(fallback=(80, 24))
        return size.columns, size.lines
    
    def format_relative_time(self, dt: datetime) -> str:
        """Format datetime as relative time.
        
        Args:
            dt: Datetime to format
            
        Returns:
            Relative time string
        """
        now = datetime.now(dt.tzinfo)
        delta = now - dt
        
        if delta.total_seconds() < 60:
            return "just now"
        elif delta.total_seconds() < 3600:
            minutes = int(delta.total_seconds() / 60)
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        elif delta.total_seconds() < 86400:
            hours = int(delta.total_seconds() / 3600)
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        elif delta.days < 7:
            return f"{delta.days} day{'s' if delta.days != 1 else ''} ago"
        else:
            return dt.strftime("%b %d, %Y")
    
    def create_status_bar(self) -> Panel:
        """Create bottom status bar.
        
        Returns:
            Status bar panel
        """
        parts = []
        
        # Model
        parts.append(f"Model: {self.status_data['model']}")
        
        # Context usage
        if self.status_data['context'] > 0:
            ctx_pct = self.status_data['context']
            if ctx_pct > 80:
                ctx_color = "red"
            elif ctx_pct > 60:
                ctx_color = "yellow"
            else:
                ctx_color = "green"
            parts.append(f"Context: [{ctx_color}]{ctx_pct}%[/{ctx_color}]")
        
        # Tokens
        if self.status_data['tokens'] > 0:
            parts.append(f"Tokens: {self.status_data['tokens']:,}")
        
        # Connection
        conn = self.status_data['connection']
        if conn == "connected":
            parts.append("[green]● Connected[/green]")
        else:
            parts.append("[red]○ Disconnected[/red]")
        
        # Git branch
        if self.status_data.get('git_branch'):
            parts.append(f"git:{self.status_data['git_branch']}")
        
        status_text = " | ".join(parts)
        
        return Panel(
            status_text,
            height=1,
            style="dim",
            border_style="dim"
        )
    
    def show_conversation_list(self, conversations: List[Dict[str, Any]]) -> Optional[int]:
        """Display conversation list with numbered selection.
        
        Args:
            conversations: List of conversation dicts
            
        Returns:
            Selected index or None
        """
        if not conversations:
            self.console.print("[yellow]No conversations found.[/yellow]")
            return None
        
        # Create table
        table = Table(show_header=False, show_lines=True, expand=True)
        table.add_column("", width=4, style="cyan")
        table.add_column("Time", width=15)
        table.add_column("Messages", width=10, justify="right")
        table.add_column("Preview")
        
        for idx, conv in enumerate(conversations, 1):
            # Format time
            created = datetime.fromisoformat(conv['created_at'])
            time_str = self.format_relative_time(created)
            
            # Message count
            msg_count = f"({conv.get('message_count', 0)} msgs)"
            
            # Preview
            preview = conv.get('preview', 'No messages yet')
            if len(preview) > 50:
                preview = preview[:47] + "..."
            
            table.add_row(
                f"[{idx}]",
                time_str,
                msg_count,
                preview
            )
        
        self.console.print(table)
        self.console.print("\n[dim]Enter number to select, arrow keys to navigate, 'b' to go back[/dim]")
        
        # Get selection (simplified for now - would use prompt_toolkit in full impl)
        from rich.prompt import Prompt
        choice = Prompt.ask("Select conversation")
        
        if choice.lower() == 'b':
            return None
        
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(conversations):
                return idx
        except ValueError:
            pass
        
        self.console.print("[red]Invalid selection[/red]")
        return None
    
    def show_scenario_list(self, scenarios: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Display scenario list with numbered selection.
        
        Args:
            scenarios: List of scenario dicts
            
        Returns:
            Selected scenario dict or None
        """
        if not scenarios:
            self.console.print("[yellow]No scenarios found.[/yellow]")
            return None
        
        # Sort scenarios by last usage (most recent first)
        def get_last_used(scenario):
            processes = scenario.get('processes', [])
            if processes:
                return datetime.fromisoformat(processes[0]['created_at'].replace('Z', '+00:00'))
            return datetime.min.replace(tzinfo=datetime.now().astimezone().tzinfo)
        
        sorted_scenarios = sorted(scenarios, key=get_last_used, reverse=True)
        
        # Create table
        table = Table(title="Available Scenarios", show_lines=True, expand=True)
        table.add_column("#", width=4, style="cyan")
        table.add_column("Name", style="green")
        table.add_column("Version", width=10)
        table.add_column("Last Used", width=12)
        table.add_column("Runs", width=6, justify="right")
        table.add_column("Description")
        
        for idx, scenario in enumerate(sorted_scenarios, 1):
            # Get last used time
            processes = scenario.get('processes', [])
            if processes:
                last_used_dt = datetime.fromisoformat(processes[0]['created_at'].replace('Z', '+00:00'))
                last_used = self.format_relative_time(last_used_dt)
            else:
                last_used = "[dim]never[/dim]"
            
            # Get run count
            run_count = scenario.get('processes_aggregate', {}).get('aggregate', {}).get('count', 0)
            
            # Truncate description if too long
            desc = scenario.get('description', '')
            if len(desc) > 40:
                desc = desc[:37] + "..."
            
            table.add_row(
                f"[{idx}]",
                scenario.get('name', 'Unknown'),
                scenario.get('version', ''),
                last_used,
                str(run_count) if run_count > 0 else "[dim]0[/dim]",
                desc
            )
        
        self.console.print(table)
        self.console.print("\n[dim]Enter number to select, 'b' to go back[/dim]")
        
        # Get selection
        from rich.prompt import Prompt
        choice = Prompt.ask("Select scenario")
        
        if choice.lower() == 'b':
            return None
        
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(sorted_scenarios):
                return sorted_scenarios[idx]
        except ValueError:
            pass
        
        self.console.print("[red]Invalid selection[/red]")
        return None
    
    def show_thinking(self, agent_name: str = "Agent") -> 'ThinkingIndicator':
        """Show thinking indicator with alien spinner.
        
        Args:
            agent_name: Name of thinking agent
            
        Returns:
            ThinkingIndicator context manager
        """
        return ThinkingIndicator(self, agent_name)
    
    def format_text_message(self, content: str, sender: str = "Agent", border_style: str = None) -> Panel:
        """Format a simple text message for display.

        Args:
            content: Message content
            sender: Sender name
            border_style: Optional border style override

        Returns:
            Formatted panel
        """
        if border_style is None:
            border_style = self.BRAND_COLOR

        return Panel(
            content,
            title=f"🤖 {sender}",
            border_style=border_style,
            padding=(0, 1)
        )
    
    def show_error(self, error: str, suggestion: Optional[str] = None):
        """Display error message without swallowing.
        
        Args:
            error: Error message
            suggestion: Optional suggestion for fixing
        """
        error_text = f"[red]❌ Error: {error}[/red]"
        
        if suggestion:
            error_text += f"\n[yellow]   Try: {suggestion}[/yellow]"
        
        self.console.print(Panel(
            error_text,
            border_style="red",
            padding=(0, 1)
        ))
        
        # Don't swallow - let it propagate if needed
        raise RuntimeError(error)
    
    def show_success(self, message: str):
        """Display success message.
        
        Args:
            message: Success message
        """
        self.console.print(f"[green]✓[/green] {message}")
    
    def show_info(self, message: str):
        """Display info message.
        
        Args:
            message: Info message
        """
        self.console.print(f"[cyan]ℹ[/cyan] {message}")
    
    def clear(self):
        """Clear the console."""
        self.console.clear()
    
    def show_header(self, blueprint_name: Optional[str] = None, blueprint_file: Optional[str] = None):
        """Display application header.

        Args:
            blueprint_name: Optional blueprint name to display
            blueprint_file: Optional blueprint filename to display
        """
        header_text = Text()
        header_text.append("Chimera v4 CLI", style=f"bold {self.BRAND_COLOR}")
        header_text.append("\n", style="")

        if blueprint_name and blueprint_file:
            header_text.append(f"Blueprint: {blueprint_name} ({blueprint_file})", style="dim")
            header_text.append("\n", style="")

        header_text.append("Multi-Agent Conversation System", style="dim")

        self.console.print(Panel(
            Align.center(header_text),
            border_style=self.BRAND_COLOR,
            padding=(1, 2)
        ))
    
    def show_separator(self, style: str = "normal"):
        """Show a separator line.
        
        Args:
            style: Separator style (heavy, normal, dotted)
        """
        if style == "heavy":
            self.console.print("═" * self.console.width, style="dim")
        elif style == "dotted":
            self.console.print("·" * self.console.width, style="dim")
        else:
            self.console.print("─" * self.console.width, style="dim")
    
    def get_box_width(self) -> int:
        """Get consistent box width for input.
        
        Returns:
            Width for the input box (interior width, not including borders)
        """
        # Get actual terminal width
        import shutil
        terminal_width = shutil.get_terminal_size().columns
        # Subtract 2 for the left/right margins we want
        width = terminal_width - 2
        return width
    
    def print_box_top(self, brightness: int = 1):
        """Print just the top line of the rounded box.
        
        Args:
            brightness: Gray brightness level for the box
        """
        width = self.get_box_width()
        box_color = get_gray(brightness)
        
        top = Text()
        top.append(" ")  # Left margin
        top.append("╭" + "─" * (width - 2) + "╮", style=box_color)
        self.console.print(top, end="")  # Don't add extra newline
    
    def print_box_bottom(self, brightness: int = 1):
        """Print just the bottom line of the rounded box.
        
        Args:
            brightness: Gray brightness level for the box
        """
        width = self.get_box_width()
        box_color = get_gray(brightness)
        
        bottom = Text()
        bottom.append(" ")  # Left margin
        bottom.append("╰" + "─" * (width - 2) + "╯", style=box_color)
        self.console.print(bottom)
    
    def create_input_box(self, text: str = "", brightness: float = 1.0, 
                        cursor_visible: bool = True, width: int = None) -> Text:
        """Create a rounded input box.
        
        Args:
            text: Current input text
            brightness: -5 to 5 (can be float for animation)
            cursor_visible: Whether to show cursor
            width: Box width (None for terminal width)
            
        Returns:
            Rich Text object
        """
        # Get box color (handle interpolation for animation)
        if brightness != int(brightness):
            # Interpolating
            if brightness > 1:
                box_color = get_gray(1)
            elif brightness < -5:
                box_color = get_gray(-5)
            else:
                # Map brightness to progress between 1 and -5
                progress = (1 - brightness) / 6  # 1 to -5 is 6 steps
                box_color = interpolate_gray(1, -5, progress)
        else:
            box_color = get_gray(int(brightness))
        
        text_color = get_gray(5)  # White
        
        # Terminal width
        if width is None:
            width = self.get_box_width()
        
        result = Text()
        
        # Top line with margin
        result.append(" ")  # Left margin
        result.append("╭" + "─" * (width - 2) + "╮\n", style=box_color)
        
        # Middle line with text and margin
        result.append(" ")  # Left margin
        result.append("│", style=box_color)
        result.append(" > ", style=text_color)  # Space before prompt
        
        # Add text with optional cursor
        display_text = text
        if cursor_visible and len(text) < width - 5:  # Room for cursor
            display_text = text + "│"
        
        result.append(display_text, style=text_color)
        
        # Padding
        used_width = len(" > ") + len(display_text)
        padding = width - used_width - 2  # -2 for the box sides
        if padding > 0:
            result.append(" " * padding, style=text_color)
        
        result.append("│\n", style=box_color)
        
        # Bottom line with margin
        result.append(" ")  # Left margin
        result.append("╰" + "─" * (width - 2) + "╯", style=box_color)
        
        return result
    
    async def animate_input_fade(self, text: str, duration: float = 0.3):
        """Animate the input box fading from brightness 1 to -5.
        
        Args:
            text: Text that was submitted
            duration: Animation duration in seconds
        """
        fps = 60
        start_time = time.time()
        
        with Live(
            self.create_input_box(text, brightness=1.0, cursor_visible=False),
            console=self.console,
            refresh_per_second=fps,
            transient=False  # Keep final frame
        ) as live:
            while True:
                elapsed = time.time() - start_time
                if elapsed >= duration:
                    break
                
                # Calculate progress with smoothstep easing
                progress = elapsed / duration
                progress = progress * progress * (3 - 2 * progress)
                
                # Interpolate brightness from 1 to -5
                current_brightness = 1 + (-5 - 1) * progress
                
                live.update(self.create_input_box(
                    text, 
                    brightness=current_brightness, 
                    cursor_visible=False
                ))
                await asyncio.sleep(1/fps)
        
        # Show final black box
        self.console.print(self.create_input_box(text, brightness=-5, cursor_visible=False))


class MatrixEffect:
    """Matrix-style encrypt/decrypt effect for thinking indicator."""
    
    def __init__(self, brand_color: str = "#00D4AA"):
        """Initialize Matrix effect.
        
        Args:
            brand_color: Color for the text
        """
        self.brand_color = brand_color
        self.phrases = THINKING_PHRASES.copy()
        self.current_phrase_idx = 0
        self.current_text = ""
        self.target_text = ""
        self.transition_chars = []
        random.shuffle(self.phrases)  # Randomize order
    
    def get_next_phrase(self) -> str:
        """Get the next phrase to display.
        
        Returns:
            Next phrase from the list
        """
        phrase = self.phrases[self.current_phrase_idx]
        self.current_phrase_idx = (self.current_phrase_idx + 1) % len(self.phrases)
        
        # Apply capitalization
        if CAPITALIZATION == "upper":
            return phrase.upper()
        elif CAPITALIZATION == "lower":
            return phrase.lower()
        return phrase
    
    def encrypt_text(self, text: str, progress: float) -> str:
        """Encrypt text progressively to noise.
        
        Args:
            text: Original text
            progress: 0.0 to 1.0 (0 = clear, 1 = fully encrypted)
            
        Returns:
            Partially encrypted text
        """
        if not self.transition_chars:
            # Create random order for character positions
            self.transition_chars = list(range(len(text)))
            random.shuffle(self.transition_chars)
        
        # Calculate how many chars to encrypt (with acceleration)
        glitch_rate = 0.1 + (progress * 0.5)  # 10% to 60%
        chars_to_encrypt = int(len(text) * glitch_rate * progress)
        
        result = list(text)
        for i in self.transition_chars[:chars_to_encrypt]:
            if i < len(result) and result[i] != ' ':
                result[i] = random.choice(NOISE_CHARS)
        
        return ''.join(result)
    
    def decrypt_text(self, source: str, target: str, progress: float) -> str:
        """Decrypt from noise to target text.
        
        Args:
            source: Starting noisy text
            target: Target clear text
            progress: 0.0 to 1.0 (0 = noisy, 1 = clear)
            
        Returns:
            Partially decrypted text
        """
        if not self.transition_chars:
            # Create random order for character positions
            self.transition_chars = list(range(max(len(source), len(target))))
            random.shuffle(self.transition_chars)
        
        # Ensure both strings are same length
        source = source.ljust(len(target))
        
        # Calculate how many chars to reveal (with acceleration)
        glitch_rate = 0.6 - (progress * 0.5)  # 60% to 10%
        chars_to_reveal = int(len(target) * progress)
        
        result = list(source)
        revealed_positions = set(self.transition_chars[:chars_to_reveal])
        
        for i in range(len(target)):
            if i in revealed_positions:
                result[i] = target[i]
            elif i < len(result) and result[i] == ' ':
                result[i] = ' '
            else:
                # Still noisy
                if random.random() > progress:
                    result[i] = random.choice(NOISE_CHARS)
                else:
                    result[i] = target[i] if i < len(target) else ' '
        
        return ''.join(result[:len(target)])


class ThinkingIndicator:
    """Context manager for thinking indicator with Matrix effect."""
    
    def __init__(self, display: Display, agent_name: str):
        """Initialize thinking indicator.
        
        Args:
            display: Display instance
            agent_name: Name of thinking agent
        """
        self.display = display
        self.agent_name = agent_name
        self.task = None
        self._stop = False
        self.matrix = MatrixEffect(display.BRAND_COLOR)
    
    async def _run_matrix_effect(self):
        """Run the Matrix decrypt effect animation."""
        # Get flash color (brightness + 4 for good contrast, capped at 10)
        flash_brightness = min(10, BRIGHTNESS + 4)
        flash_color = get_brand_color(flash_brightness)
        
        # Initialize spinner
        spinner = AlienSpinner()
        spinner_brightness = min(10, BRIGHTNESS + 3)  # Slightly brighter than text
        spinner_color = get_brand_color(spinner_brightness)
        spinner_frame = spinner.get_next_frame()
        spinner_interval = spinner.get_next_interval()
        spinner_last_update = time.time()
        
        with Live(
            Text(""),
            console=self.display.console,
            refresh_per_second=30,  # Higher FPS for smooth animation
            transient=True  # This should clear the line when done
        ) as live:
            # Start with first phrase
            current_phrase = self.matrix.get_next_phrase()
            current_phase = 1  # Track phase for spinner encryption
            
            while not self._stop:
                self.matrix.transition_chars = []
                
                # Calculate random display time
                if MAX_PHRASE_DISPLAY_TIME and MAX_PHRASE_DISPLAY_TIME > MIN_PHRASE_DISPLAY_TIME:
                    # Random time between min and max
                    time_range = MAX_PHRASE_DISPLAY_TIME - MIN_PHRASE_DISPLAY_TIME
                    random_multiplier = random.random()
                    phrase_display_time = MIN_PHRASE_DISPLAY_TIME + (time_range * random_multiplier)
                    
                    # Check if we should do the flash effect (top 50% of range)
                    should_flash = random_multiplier >= 0.5
                else:
                    # Fixed time
                    phrase_display_time = MIN_PHRASE_DISPLAY_TIME
                    should_flash = False
                
                # Phase 1: Display clear phrase with spinner
                current_phase = 1
                
                # Update spinner if needed
                now = time.time()
                if now - spinner_last_update >= spinner_interval:
                    spinner_frame = spinner.get_next_frame()
                    spinner_interval = spinner.get_next_interval()
                    spinner_last_update = now
                
                text = Text()
                text.append(f"{spinner_frame}  ", style=spinner_color)
                text.append(current_phrase, style=self.display.BRAND_COLOR)
                live.update(text)
                
                # Wait before flash
                await asyncio.sleep(FLASH_DELAY)
                
                if self._stop:
                    break
                
                # Flash effect - sweep left to right then back
                # Forward sweep
                for i in range(len(current_phrase)):
                    if self._stop:
                        break
                    
                    # Update spinner during flash
                    now = time.time()
                    if now - spinner_last_update >= spinner_interval:
                        spinner_frame = spinner.get_next_frame()
                        spinner_interval = spinner.get_next_interval()
                        spinner_last_update = now
                    
                    if current_phrase[i] != ' ':
                        # Create text with one character flashed
                        flash_text = Text()
                        flash_text.append(f"{spinner_frame}  ", style=spinner_color)
                        flash_text.append(current_phrase[:i], style=self.display.BRAND_COLOR)
                        flash_text.append(current_phrase[i], style=flash_color)
                        flash_text.append(current_phrase[i+1:], style=self.display.BRAND_COLOR)
                        live.update(flash_text)
                        await asyncio.sleep(1/FLASH_FPS)  # Flash sweep speed
                
                # Reverse sweep (twice as fast)
                for i in range(len(current_phrase) - 1, -1, -1):
                    if self._stop:
                        break
                    
                    # Update spinner during reverse flash
                    now = time.time()
                    if now - spinner_last_update >= spinner_interval:
                        spinner_frame = spinner.get_next_frame()
                        spinner_interval = spinner.get_next_interval()
                        spinner_last_update = now
                    
                    if current_phrase[i] != ' ':
                        # Create text with one character flashed
                        flash_text = Text()
                        flash_text.append(f"{spinner_frame}  ", style=spinner_color)
                        flash_text.append(current_phrase[:i], style=self.display.BRAND_COLOR)
                        flash_text.append(current_phrase[i], style=flash_color)
                        flash_text.append(current_phrase[i+1:], style=self.display.BRAND_COLOR)
                        live.update(flash_text)
                        await asyncio.sleep(1/(FLASH_FPS * 2))  # Double speed for reverse
                
                # Back to normal and wait remaining time
                text = Text()
                text.append(f"{spinner_frame}  ", style=spinner_color)
                text.append(current_phrase, style=self.display.BRAND_COLOR)
                live.update(text)
                
                # Calculate remaining display time (total - flash_delay - forward flash - reverse flash)
                non_space_chars = len([c for c in current_phrase if c != ' '])
                forward_flash_duration = non_space_chars / FLASH_FPS
                reverse_flash_duration = non_space_chars / (FLASH_FPS * 2)  # Reverse is twice as fast
                total_flash_duration = forward_flash_duration + reverse_flash_duration
                remaining_time = max(0, phrase_display_time - FLASH_DELAY - total_flash_duration)
                await asyncio.sleep(remaining_time)
                
                if self._stop:
                    break
                
                # Phase 2: Encrypt to noise
                current_phase = 2
                start_time = time.time()
                encrypted_text = current_phrase
                while time.time() - start_time < ENCRYPT_DURATION:
                    if self._stop:
                        break
                    progress = (time.time() - start_time) / ENCRYPT_DURATION
                    encrypted_text = self.matrix.encrypt_text(current_phrase, progress)
                    
                    # Update spinner
                    now = time.time()
                    if now - spinner_last_update >= spinner_interval:
                        spinner_frame = spinner.get_next_frame()
                        spinner_interval = spinner.get_next_interval()
                        spinner_last_update = now
                    
                    # Spinner encrypts too with increasing probability
                    display_spinner = spinner_frame
                    if random.random() < progress * 0.8:  # Up to 80% chance at full encryption
                        display_spinner = random.choice(NOISE_CHARS)
                    
                    text = Text()
                    text.append(f"{display_spinner}  ", style=spinner_color)
                    text.append(encrypted_text, style=self.display.BRAND_COLOR)
                    live.update(text)
                    await asyncio.sleep(0.03)  # ~30 FPS
                
                if self._stop:
                    break
                
                # Now at maximum encryption, switch to next phrase
                next_phrase = self.matrix.get_next_phrase()
                self.matrix.transition_chars = []
                
                # Phase 3: Decrypt from noise to next phrase
                current_phase = 3
                start_time = time.time()
                while time.time() - start_time < DECRYPT_DURATION:
                    if self._stop:
                        break
                    progress = (time.time() - start_time) / DECRYPT_DURATION
                    decrypted_text = self.matrix.decrypt_text(encrypted_text, next_phrase, progress)
                    
                    # Update spinner
                    now = time.time()
                    if now - spinner_last_update >= spinner_interval:
                        spinner_frame = spinner.get_next_frame()
                        spinner_interval = spinner.get_next_interval()
                        spinner_last_update = now
                    
                    # Spinner decrypts too with decreasing noise
                    display_spinner = spinner_frame
                    if random.random() < (1 - progress) * 0.8:  # Decreasing chance as we decrypt
                        display_spinner = random.choice(NOISE_CHARS)
                    
                    text = Text()
                    text.append(f"{display_spinner}  ", style=spinner_color)
                    text.append(decrypted_text, style=self.display.BRAND_COLOR)
                    live.update(text)
                    await asyncio.sleep(0.03)  # ~30 FPS
                
                # Next phrase becomes current for next cycle
                current_phrase = next_phrase
    
    def __enter__(self):
        """Start Matrix effect on enter."""
        self.task = asyncio.create_task(self._run_matrix_effect())
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop Matrix effect on exit."""
        self._stop = True
        if self.task:
            self.task.cancel()
        # The Live display with transient=True handles cleanup