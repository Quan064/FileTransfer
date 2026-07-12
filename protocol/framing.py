import socket
import struct
from protocol.packet import Packet

# Format for the 4-byte length prefix.
# >: Big-endian
# I: Unsigned integer (4 bytes)
LENGTH_PREFIX_FORMAT = '>I'
LENGTH_PREFIX_SIZE = struct.calcsize(LENGTH_PREFIX_FORMAT)

def send_packet(sock: socket.socket, packet: Packet):
    """
    Sends a Packet object over a socket, prefixed with its length.
    
    Args:
        sock: The socket to send data through.
        packet: The Packet object to send.
    
    Raises:
        ConnectionError: If the socket connection is closed or broken.
    """
    packed_data = packet.pack()
    length_prefix = struct.pack(LENGTH_PREFIX_FORMAT, len(packed_data))
    message = length_prefix + packed_data
    
    try:
        sock.sendall(message)
    except (BrokenPipeError, ConnectionResetError) as e:
        raise ConnectionError("Socket connection is broken") from e

def recv_packet(sock: socket.socket):
    """
    Receives a length-prefixed packet from a socket and unpacks it.
    
    Args:
        sock: The socket to receive data from.
    
    Returns:
        A Packet object if a full packet is received successfully.
        None if the connection is closed by the peer (received 0 bytes).
    
    Raises:
        ConnectionError: If the connection is reset during reception.
    """
    # Read the 4-byte length prefix first
    length_prefix_data = sock.recv(LENGTH_PREFIX_SIZE)
    if not length_prefix_data:
        return None  # Connection closed
    
    if len(length_prefix_data) < LENGTH_PREFIX_SIZE:
        raise ConnectionError("Connection reset while reading packet length")
    
    total_packet_size: int = struct.unpack(LENGTH_PREFIX_FORMAT, length_prefix_data)[0]
    
    # Now read the rest of the packet
    packet_data = b''
    while len(packet_data) < total_packet_size:
        remaining_bytes = total_packet_size - len(packet_data)
        chunk = sock.recv(remaining_bytes)
        if not chunk:
            raise ConnectionError("Connection reset while reading packet data")
        packet_data += chunk
    
    return Packet.unpack(packet_data)
