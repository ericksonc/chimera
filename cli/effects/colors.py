"""Color system for CLI v2 with gray scale brightness levels."""

def get_gray(brightness: int) -> str:
    """Get gray color from brightness level.
    
    Args:
        brightness: -5 (black) to 5 (white)
        
    Returns:
        Hex color string
    """
    # Clamp to valid range
    brightness = max(-5, min(5, brightness))
    
    # Map brightness to 0-255 range
    # -5 = black (0)
    # 0 = dark gray but readable (~64, which is ~25% brightness)
    # 5 = white (255)
    
    if brightness == -5:
        value = 0
    elif brightness == 5:
        value = 255
    else:
        # Linear interpolation
        # -4 to 0: maps to 16 to 64 (dark but visible range)
        # 0 to 4: maps to 64 to 230 (readable to bright range)
        if brightness < 0:
            # -4 to 0 maps to 16 to 64
            value = int(16 + (brightness + 4) * 12)  # 48 spread over 4 steps
        else:
            # 0 to 4 maps to 64 to 230
            value = int(64 + brightness * 41.5)  # 166 spread over 4 steps
    
    return f"#{value:02x}{value:02x}{value:02x}"


def get_brand_color(brightness: int = 7) -> str:
    """Calculate brand color based on brightness level.
    
    Args:
        brightness: 0-10 where 0 is black, 10 is full electric teal
        
    Returns:
        Hex color string
    """
    # Base electric teal RGB values
    base_r, base_g, base_b = 0x00, 0xD4, 0xAA
    
    # Calculate factor (0.0 to 1.0)
    factor = brightness / 10.0
    
    # Apply brightness factor
    r = int(base_r * factor)
    g = int(base_g * factor)
    b = int(base_b * factor)
    
    return f"#{r:02x}{g:02x}{b:02x}"


def interpolate_gray(from_brightness: int, to_brightness: int, progress: float) -> str:
    """Interpolate between two gray brightness levels.
    
    Args:
        from_brightness: Starting brightness (-5 to 5)
        to_brightness: Ending brightness (-5 to 5)
        progress: 0.0 to 1.0
        
    Returns:
        Hex color string for interpolated gray
    """
    # Get actual RGB values
    from_hex = get_gray(from_brightness)
    to_hex = get_gray(to_brightness)
    
    # Extract values (they're all the same for grays)
    from_val = int(from_hex[1:3], 16)
    to_val = int(to_hex[1:3], 16)
    
    # Interpolate
    current_val = int(from_val + (to_val - from_val) * progress)
    
    return f"#{current_val:02x}{current_val:02x}{current_val:02x}"


# Pre-computed gray scale for quick access
GRAYS = {
    -5: get_gray(-5),  # Black
    -4: get_gray(-4),  # Very dark
    -3: get_gray(-3),  # Dark
    -2: get_gray(-2),  # Medium dark
    -1: get_gray(-1),  # Slightly dark
    0: get_gray(0),    # Readable dark gray
    1: get_gray(1),    # Light gray
    2: get_gray(2),    # Lighter gray
    3: get_gray(3),    # Medium light
    4: get_gray(4),    # Bright
    5: get_gray(5),    # White
}

# Common semantic mappings
BLACK = GRAYS[-5]
DARK_READABLE = GRAYS[0]
DIM = GRAYS[1]
NORMAL = GRAYS[3]
BRIGHT = GRAYS[4]
WHITE = GRAYS[5]