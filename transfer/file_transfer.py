import hashlib
import os

import common.config as config
from common.checksum import calculate_checksum

from protocol.framing import RateLimiter, recv_packet, send_packet
from protocol.opcode import Opcode
from protocol.packet import Packet
from protocol.payloads import decode_file_chunk, encode_file_chunk, encode_file_metadata


def build_file_metadata_payload(path: str, filename: str) -> tuple[bytes, int, str]:
    total_size = os.path.getsize(path)
    checksum = calculate_checksum(path)
    return encode_file_metadata(filename, total_size, checksum), total_size, checksum


def _default_progress_callback(bytes_processed: int, total_size: int):
    """A simple default callback to print progress to the console."""
    if total_size == 0:
        return
    percentage = (bytes_processed / total_size) * 100
    print(f"\rProgress: {bytes_processed}/{total_size} bytes ({percentage:.2f}%)", end="")
    if bytes_processed == total_size:
        print()


def send_file_chunks(sock, user_id: int, path: str, offset: int = 0, chunk_size: int = config.CHUNK_SIZE, progress_callback = _default_progress_callback, limiter: RateLimiter | None = None) -> int:
    total_size = os.path.getsize(path)
    with open(path, "rb") as handle:
        handle.seek(offset)
        current_pos = offset
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            send_packet(sock, Packet(Opcode.FILE_CHUNK, user_id, encode_file_chunk(current_pos, chunk)), limiter=limiter)
            current_pos += len(chunk)
            if progress_callback:
                progress_callback(current_pos, total_size)
    return current_pos


def receive_file_chunks(sock, target_path: str, total_size: int, expected_checksum: str, offset: int = 0, progress_callback = _default_progress_callback) -> tuple[int, str]:
    received = offset
    hash_obj = hashlib.sha256()
    
    if offset > 0 and os.path.exists(target_path):
        with open(target_path, "rb") as f:
            if os.path.getsize(target_path) > offset:
                raise ValueError("Existing file is larger than resume offset")
            hash_obj.update(f.read(offset))
    
    with open(target_path, "r+b" if offset > 0 else "wb") as handle:
        handle.seek(offset)
        while received < total_size:
            chunk_packet = recv_packet(sock)
            if chunk_packet is None:
                raise ConnectionError("Connection closed during file transfer")
            if chunk_packet.opcode != Opcode.FILE_CHUNK:
                raise ValueError(f"Expected FILE_CHUNK, got {chunk_packet.opcode.name}")
            
            offset, chunk = decode_file_chunk(chunk_packet.payload)
            handle.write(chunk)
            hash_obj.update(chunk)
            received += len(chunk)
            if progress_callback:
                progress_callback(received, total_size)
    
    actual_checksum = hash_obj.hexdigest()
    if actual_checksum != expected_checksum:
        raise ValueError(f"Checksum mismatch: expected {expected_checksum}, got {actual_checksum}")
    return received, actual_checksum
