from enum import IntEnum

class Opcode(IntEnum):
    """Enumeration of protocol opcodes."""
    # Client -> Server
    LOGIN = 0x01
    LOGOUT = 0x02
    FILE_LIST = 0x10
    FILE_UPLOAD = 0x12
    FILE_DOWNLOAD = 0x13
    FILE_DELETE = 0x15
    
    # Server -> Client
    FILE_LIST_RESP = 0x11
    FILE_CHUNK = 0x14
    ACK = 0x20
    ERROR = 0xFF