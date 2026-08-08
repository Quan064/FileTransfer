import socket
import struct
import time
from protocol.packet import Packet

class RateLimiter:
    """
    Implements the "token bucket" algorithm for rate limiting.
    
    This class enables data transmission rate limiting. It works by
    continuously "refilling" a "bucket" with tokens at a constant rate. Whenever
    data needs to be sent, it "consumes" a corresponding number of tokens. If
    there are insufficient tokens, it pauses (sleeps) until enough are available.
    """
    def __init__(self, rate_kbps: float):
        self.rate_bytes_per_sec = rate_kbps * 1024
        self.bucket_size = max(self.rate_bytes_per_sec, 64 * 1024)  # Allow bursts, at least 64KB
        self.current_tokens = self.bucket_size
        self.last_refill_time = time.monotonic()
    
    def _refill_bucket(self):
        """Refills the token bucket based on the elapsed time."""
        now = time.monotonic()
        elapsed = now - self.last_refill_time
        if elapsed > 0:
            new_tokens = elapsed * self.rate_bytes_per_sec
            self.current_tokens = min(self.bucket_size, self.current_tokens + new_tokens)
            self.last_refill_time = now
    
    def consume(self, amount: int):
        """Consumes a number of tokens, sleeping if necessary to maintain the rate limit."""
        if self.rate_bytes_per_sec <= 0: return
        self._refill_bucket()
        if amount <= self.current_tokens: self.current_tokens -= amount; return
        required_wait = (amount - self.current_tokens) / self.rate_bytes_per_sec
        time.sleep(required_wait); self.current_tokens = 0

# Format for the 4-byte length prefix.
# >: Big-endian
# I: Unsigned integer (4 bytes)
LENGTH_PREFIX_FORMAT = '>I'
LENGTH_PREFIX_SIZE = struct.calcsize(LENGTH_PREFIX_FORMAT)
DEFAULT_CHUNK_SIZE = 64 * 1024  # 64 KB per network chunk


def split_payload_into_chunks(payload: bytes, chunk_size: int = DEFAULT_CHUNK_SIZE) -> list[bytes]:
    """Split a byte payload into bounded chunks to avoid large temporary buffers."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")
    
    return [payload[index:index + chunk_size] for index in range(0, len(payload), chunk_size)]


def send_packet(sock: socket.socket, packet: Packet, chunk_size: int = DEFAULT_CHUNK_SIZE, limiter: RateLimiter | None = None):
    """
    Sends a Packet object over a socket, prefixed with its length.
    
    The payload is streamed in bounded chunks so large packets do not create a
    single huge temporary buffer on either side of the connection.
    """
    packed_data = packet.pack()
    length_prefix = struct.pack(LENGTH_PREFIX_FORMAT, len(packed_data))
    
    try:
        if limiter:
            limiter.consume(len(length_prefix))
        sock.sendall(length_prefix)
        for chunk in split_payload_into_chunks(packed_data, chunk_size=chunk_size):
            if limiter:
                limiter.consume(len(chunk))
            sock.sendall(chunk)
    except (BrokenPipeError, ConnectionResetError) as e:
        raise ConnectionError("Socket connection is broken") from e


def recv_packet(sock: socket.socket, chunk_size: int = DEFAULT_CHUNK_SIZE):
    """
    Receives a length-prefixed packet from a socket and unpacks it.
    
    The body is read in bounded chunks to prevent one large recv() from buffering
    an excessively large amount of data at once.
    """
    length_prefix_data = b''
    while len(length_prefix_data) < LENGTH_PREFIX_SIZE:
        chunk = sock.recv(LENGTH_PREFIX_SIZE - len(length_prefix_data))
        if not chunk:
            return None  # Connection closed
        length_prefix_data += chunk
    
    if len(length_prefix_data) < LENGTH_PREFIX_SIZE:
        raise ConnectionError("Connection reset while reading packet length")
    
    total_packet_size: int = struct.unpack(LENGTH_PREFIX_FORMAT, length_prefix_data)[0]
    
    packet_data = bytearray()
    while len(packet_data) < total_packet_size:
        remaining_bytes = total_packet_size - len(packet_data)
        chunk = sock.recv(min(chunk_size, remaining_bytes))
        if not chunk:
            raise ConnectionError("Connection reset while reading packet data")
        packet_data.extend(chunk)
    
    return Packet.unpack(bytes(packet_data))
