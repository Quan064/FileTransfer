import hashlib

def calculate_checksum(file_path: str, algorithm: str = 'sha256', chunk_size: int = 8192) -> str:
    """
    Calculates the checksum of a file efficiently without loading it all into memory.
    
    Args:
        file_path: The path to the file.
        algorithm: The hash algorithm to use (e.g., 'md5', 'sha256'). Defaults to 'sha256' as it's more secure than MD5.
        chunk_size: The size of chunks to read from the file at a time.
    
    Returns:
        The hexadecimal representation of the file's checksum.
        Returns an empty string if the file is not found.
    """
    hash_obj = hashlib.new(algorithm)
    try:
        with open(file_path, 'rb') as f:
            # Read the file in chunks to handle large files
            for chunk in iter(lambda: f.read(chunk_size), b''):
                hash_obj.update(chunk)
        return hash_obj.hexdigest()
    except FileNotFoundError:
        return ""