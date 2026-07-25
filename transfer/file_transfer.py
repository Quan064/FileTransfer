import hashlib
import os
import time

import common.config as config
from common.checksum import calculate_checksum
from protocol.framing import recv_packet, send_packet
from protocol.opcode import Opcode
from protocol.packet import Packet
from protocol.payloads import decode_file_chunk, encode_file_chunk, encode_file_metadata


def build_file_metadata_payload(path: str, filename: str) -> tuple[bytes, int, str]:
    total_size = os.path.getsize(path)
    checksum = calculate_checksum(path)
    return encode_file_metadata(filename, total_size, checksum), total_size, checksum


def send_file_chunks(sock, user_id: int, path: str, chunk_size: int = config.CHUNK_SIZE) -> int:
    sent = 0
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            send_packet(sock, Packet(Opcode.FILE_CHUNK, user_id, encode_file_chunk(sent, chunk)))
            time.sleep(0)  # Yield CPU to other processes to prevent UI lag
            sent += len(chunk)
    return sent


def receive_file_chunks(sock, target_path: str, total_size: int, expected_checksum: str) -> tuple[int, str]:
    received = 0
    hash_obj = hashlib.sha256()
    with open(target_path, "wb") as handle:
        while received < total_size:
            chunk_packet = recv_packet(sock)
            if chunk_packet is None:
                raise ConnectionError("Connection closed during file transfer")
            if chunk_packet.opcode != Opcode.FILE_CHUNK:
                raise ValueError(f"Expected FILE_CHUNK, got {chunk_packet.opcode.name}")
            
            offset, chunk = decode_file_chunk(chunk_packet.payload)
            if offset != received:
                raise ValueError(f"Unexpected chunk offset: got {offset}, expected {received}")
            
            handle.write(chunk)
            hash_obj.update(chunk)
            received += len(chunk)
            time.sleep(0)  # Yield CPU to other processes to prevent UI lag
    
    actual_checksum = hash_obj.hexdigest()
    if actual_checksum != expected_checksum:
        raise ValueError(
            f"Checksum mismatch: expected {expected_checksum}, got {actual_checksum}"
        )
    return received, actual_checksum
