import socket
import sys

import config
from protocol.opcode import Opcode
from protocol.packet import Packet
from protocol.framing import send_packet, recv_packet

class Client:
    """Manages the connection and communication with the server."""
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.sock = None
        self.user_id = 0 # Will be set by the user
    
    def connect(self):
        """Connects to the server."""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
            print(f"[*] Connected to server at {self.host}:{self.port}")
            return True
        except ConnectionRefusedError:
            print("[!] Connection refused. Is the server running?")
            return False
    
    def login(self, username: str, user_id: int):
        """Sends a LOGIN packet to the server."""
        if not self.sock:
            print("[!] Not connected to the server.")
            return
        
        self.user_id = user_id
        payload = username.encode('utf-8')
        login_packet = Packet(Opcode.LOGIN, self.user_id, payload)
        
        print(f"[<-] Sending: {login_packet}")
        send_packet(self.sock, login_packet)
        
        # Wait for ACK
        response = recv_packet(self.sock)
        if response and response.opcode == Opcode.ACK:
            print(f"[->] Received: {response}")
            print(f"[*] Login successful as '{username}'.")
        else:
            print("[!] Login failed. Server response:", response)
    
    def close(self):
        """Closes the connection to the server."""
        if self.sock:
            self.sock.close()
            print("[*] Connection closed.")

def main():
    """Main function to run the client CLI."""
    client = Client(config.HOST, config.PORT)
    if not client.connect():
        sys.exit(1)
    
    # Example usage: python client.py login my_username 123
    if len(sys.argv) > 2 and sys.argv[1].lower() == 'login':
        username = sys.argv[2]
        user_id = int(sys.argv[3]) if len(sys.argv) > 3 else 1 # Simple user ID for now
        client.login(username, user_id)
    else:
        print("Usage: python client.py login <username> [user_id]")
    
    # The client will do more in a real command loop
    client.close()

if __name__ == "__main__":
    main()