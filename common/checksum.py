import hashlib

import common.config as config


def calculate_checksum(file_path: str, algorithm: str = 'sha256', chunk_size: int = config.CHUNK_SIZE) -> str:
    """Calculates the checksum of a file efficiently without loading it all into memory."""
    hash_obj = hashlib.new(algorithm)
    try:
        with open(file_path, 'rb') as f:
            # Read the file in chunks to handle large files
            for chunk in iter(lambda: f.read(chunk_size), b''):
                hash_obj.update(chunk)
        return hash_obj.hexdigest()
    except FileNotFoundError:
        return ""