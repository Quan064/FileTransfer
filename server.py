import socket
import threading
import os
import logging

import config
from protocol.opcode import Opcode
from protocol.packet import Packet
from protocol.framing import recv_packet, send_packet
from common.logger import setup_server_logger


class ClientHandler(threading.Thread):
    """
    Handles a single client connection.
    Each client is managed in its own thread.
    """
    def __init__(self, sock: socket.socket, addr: tuple, logger: logging.Logger):
        super().__init__()
        self.sock = sock
        self.addr = addr
        self.log = logger
        self.user_id = 0
        self.username = ""
        self.user_storage_path = ""
        self.log.info(f"New connection from {self.addr}")
    
    def run(self):
        """Main loop to receive and process packets from the client."""
        try:
            while True:
                packet = recv_packet(self.sock)
                if packet is None:
                    self.log.info(f"Client {self.addr} disconnected.")
                    break
                self.process_packet(packet)
        except ConnectionError as e:
            self.log.error(f"Connection error with {self.addr}: {e}")
        finally:
            self.sock.close()
            self.log.info(f"Connection closed for {self.addr}")
    
    def process_packet(self, packet: Packet):
        """Processes a received packet based on its opcode."""
        self.log.debug(f"Received from {self.addr}: {packet}")
        
        if packet.opcode == Opcode.LOGIN:
            self.handle_login(packet)
        elif packet.opcode == Opcode.LOGOUT:
            pass
        elif packet.opcode == Opcode.FILE_LIST:
            pass
        elif packet.opcode == Opcode.FILE_UPLOAD:
            pass
        elif packet.opcode == Opcode.FILE_DOWNLOAD:
            pass
        elif packet.opcode == Opcode.FILE_DELETE:
            pass
        else:
            self.log.warning(f"Unknown or out-of-order opcode from {self.addr}: {packet.opcode.name}")
            # Optionally send an ERROR packet back
            error_packet = Packet(Opcode.ERROR, self.user_id, b"Invalid operation")
            send_packet(self.sock, error_packet)
    
    def handle_login(self, packet: Packet):
        """Handles a LOGIN request."""
        try:
            self.username = packet.payload.decode('utf-8')
            self.user_id = packet.user_id # Or generate a new one
            
            # Create a dedicated storage folder for the user
            self.user_storage_path = os.path.join(config.STORAGE_DIR, self.username)
            os.makedirs(self.user_storage_path, exist_ok=True)
            
            self.log.info(f"User '{self.username}' (ID: {self.user_id}) logged in from {self.addr}.")
            
            # Send ACK for successful login
            ack_packet = Packet(Opcode.ACK, self.user_id, Opcode.LOGIN.to_bytes(2, 'big'))
            send_packet(self.sock, ack_packet)
        except Exception as e:
            self.log.error(f"Error during login for {self.addr}: {e}")
            error_packet = Packet(Opcode.ERROR, 0, str(e).encode('utf-8'))
            send_packet(self.sock, error_packet)

def main():
    """Starts the server and listens for incoming connections."""
    # Setup logger
    server_log = setup_server_logger()
    server_log.info("Server starting...")

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((config.HOST, config.PORT))
    server_socket.listen()
    server_log.info(f"Server listening on {config.HOST}:{config.PORT}")
    
    while True:
        client_sock, client_addr = server_socket.accept()
        handler = ClientHandler(client_sock, client_addr, server_log)
        handler.start()

if __name__ == "__main__":
    os.makedirs(config.STORAGE_DIR, exist_ok=True)
    main()