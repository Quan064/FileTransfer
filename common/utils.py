def format_bytes(size: int) -> str:
    """
    Formats a size in bytes into a human-readable string (KB, MB, GB, etc.).
    
    Args:
        size: The size in bytes.
    
    Returns:
        A human-readable string representation of the size.
    """
    if size == 0:
        return "0B"
    power = 1024
    n = 0
    power_labels = {0: '', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
    while size > power and n < len(power_labels):
        size /= power
        n += 1
    return f"{size:.2f} {power_labels[n]}B"