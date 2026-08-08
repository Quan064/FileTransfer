import socket
import time
import os
from common import config
from protocol.framing import recv_packet
from protocol.packet import Opcode


def main():
    """A simple client that connects and sleeps to occupy a server slot."""
    
    client_id = os.getpid()
    print(f"Client {client_id}: Attempting to connect to {config.HOST}:{config.PORT}...")
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect((config.HOST, config.PORT))
            print(f"[*] Client {client_id}: TCP connection established. Waiting for server response...")
            
            # If the server doesn't reject within timeout, we assume the connection is accepted.
            sock.settimeout(2.0)
            try:
                response = recv_packet(sock)
                if response and response.opcode == Opcode.ERROR:
                    print(f"[!] Client {client_id}: Connection rejected by server: {response.payload.decode()}")
                    return
                elif response is None:
                    print(f"[!] Client {client_id}: Server closed connection unexpectedly.")
                    return
            
            except socket.timeout:
                print(f"[*] Client {client_id}: Connection accepted. Occupying slot. Press Ctrl+C to exit.")
                sock.settimeout(None) # Remove timeout to keep the connection open
                while True:
                    time.sleep(10)
    
    except ConnectionRefusedError:
        print(f"[!] Client {client_id}: Connection refused. Is the server running or backlog full?")
    
    except Exception as e:
        print(f"[!] Client {client_id}: An error occurred: {e}")

if __name__ == "__main__":
    main()
