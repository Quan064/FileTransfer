import struct


def encode_file_metadata(filename: str, total_size: int, checksum: str) -> bytes:
    filename_bytes = filename.encode("utf-8")
    checksum_bytes = checksum.encode("ascii")
    return (
        struct.pack(">H", len(filename_bytes))
        + filename_bytes
        + struct.pack(">QH", total_size, len(checksum_bytes))
        + checksum_bytes
    )


def decode_file_metadata(payload: bytes):
    if len(payload) < 2:
        raise ValueError("Missing filename length")
    filename_len = struct.unpack(">H", payload[:2])[0]
    header_end = 2 + filename_len
    if len(payload) < header_end + 10:
        raise ValueError("File metadata is truncated")
    
    filename = payload[2:header_end].decode("utf-8")
    total_size, checksum_len = struct.unpack(">QH", payload[header_end:header_end + 10])
    checksum_start = header_end + 10
    checksum_end = checksum_start + checksum_len
    if len(payload) != checksum_end:
        raise ValueError("Checksum metadata is truncated")
    
    checksum = payload[checksum_start:checksum_end].decode("ascii")
    return filename, total_size, checksum


def encode_file_chunk(offset: int, chunk: bytes) -> bytes:
    return struct.pack(">Q", offset) + chunk


def decode_file_chunk(payload: bytes):
    if len(payload) < 8:
        raise ValueError("Chunk payload is missing offset")
    return struct.unpack(">Q", payload[:8])[0], payload[8:]
