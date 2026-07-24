import struct
from protocol.opcode import Opcode

# Define the header format for struct packing/unpacking.
# >: Big-endian byte order
# H: Unsigned short (2 bytes) for Opcode
# H: Unsigned short (2 bytes) for User ID
HEADER_FORMAT = '>HH'
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

class Packet:
    """Represents a single protocol packet."""
    def __init__(self, opcode: Opcode, user_id: int = 0, payload: bytes = b''):
        """
        Initializes a Packet object.
        
        Args:
            opcode: The operation code from the Opcode enum.
            user_id: The ID of the user associated with the packet.
            payload: The binary data payload of the packet.
        """
        self.opcode = opcode
        self.user_id = user_id
        self.payload = payload
    
    def __repr__(self) -> str:
        """Provides a developer-friendly representation of the packet."""
        return f"Packet(opcode={self.opcode.name}, user_id={self.user_id}, payload_len={len(self.payload)}, payload={self.payload[:64]})"
    
    def pack(self) -> bytes:
        """Packs the packet object into a byte string for transmission."""
        header = struct.pack(HEADER_FORMAT, self.opcode.value, self.user_id)
        return header + self.payload
    
    @classmethod
    def unpack(cls, data: bytes) -> 'Packet':
        """
        Unpacks a byte string into a Packet object.
        Assumes `data` contains the header and payload, but not the 4-byte length prefix.
        """
        header_data = data[:HEADER_SIZE]
        payload = data[HEADER_SIZE:]
        opcode_val, user_id = struct.unpack(HEADER_FORMAT, header_data)
        return cls(Opcode(opcode_val), user_id, payload)
