import logging
import os
import socket
import struct
import threading

import config
from common.logger import setup_server_logger
from protocol.framing import recv_packet, send_packet
from protocol.opcode import Opcode
from protocol.packet import Packet


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
            self.handle_logout(packet)
        elif packet.opcode == Opcode.FILE_LIST:
            self.handle_file_list(packet)
        elif packet.opcode == Opcode.FILE_UPLOAD:
            self.handle_file_upload(packet)
        elif packet.opcode == Opcode.FILE_DOWNLOAD:
            self.handle_file_download(packet)
        elif packet.opcode == Opcode.FILE_DELETE:
            self.handle_file_delete(packet)
        else:
            self.log.warning(f"Unknown or out-of-order opcode from {self.addr}: {packet.opcode.name}")
            self._send_error("Invalid operation")

    def handle_login(self, packet: Packet):
        """Handles a LOGIN request."""
        try:
            self.username = packet.payload.decode("utf-8")
            self.user_id = packet.user_id
            self.user_storage_path = os.path.join(config.STORAGE_DIR, self.username)
            os.makedirs(self.user_storage_path, exist_ok=True)
            
            self.log.info(f"User '{self.username}' (ID: {self.user_id}) logged in from {self.addr}.")
            ack_packet = Packet(Opcode.ACK, self.user_id, Opcode.LOGIN.to_bytes(2, "big"))
            send_packet(self.sock, ack_packet)
        except Exception as e:
            self.log.error(f"Error during login for {self.addr}: {e}")
            self._send_error(str(e))
    
    def handle_logout(self, packet: Packet):
        """Handles a LOGOUT request."""
        self.log.info(f"User '{self.username}' logged out from {self.addr}.")
        ack_packet = Packet(Opcode.ACK, self.user_id, b"logout")
        send_packet(self.sock, ack_packet)
    
    def handle_file_list(self, packet: Packet):
        """Returns a newline-delimited list of files for the current user."""
        if not self.username:
            self._send_error("Please login first")
            return
        
        files = [
            name for name in sorted(os.listdir(self.user_storage_path))
            if os.path.isfile(os.path.join(self.user_storage_path, name))
        ]
        payload = "\n".join(files).encode("utf-8")
        response = Packet(Opcode.FILE_LIST_RESP, self.user_id, payload)
        send_packet(self.sock, response)
    
    def handle_file_upload(self, packet: Packet):
        """Receives a file from the client and stores it in the user's folder."""
        if not self.username:
            self._send_error("Please login first")
            return
        
        try:
            filename, file_data = self._decode_file_payload(packet.payload)
            target_path = self._safe_path(filename)
            with open(target_path, "wb") as handle:
                handle.write(file_data)
            self.log.info(f"Uploaded '{filename}' for user '{self.username}'.")
            ack_packet = Packet(Opcode.ACK, self.user_id, f"uploaded:{filename}".encode("utf-8"))
            send_packet(self.sock, ack_packet)
        except Exception as e:
            self.log.error(f"Upload failed for {self.addr}: {e}")
            self._send_error(str(e))
    
    def handle_file_download(self, packet: Packet):
        """Sends a requested file back to the client."""
        if not self.username:
            self._send_error("Please login first")
            return
        
        try:
            filename = packet.payload.decode("utf-8")
            target_path = self._safe_path(filename)
            with open(target_path, "rb") as handle:
                file_data = handle.read()
            response = Packet(Opcode.FILE_CHUNK, self.user_id, file_data)
            send_packet(self.sock, response)
        except FileNotFoundError:
            self._send_error(f"File '{filename}' not found")
        except Exception as e:
            self.log.error(f"Download failed for {self.addr}: {e}")
            self._send_error(str(e))
    
    def handle_file_delete(self, packet: Packet):
        """Deletes a file from the user's storage folder."""
        if not self.username:
            self._send_error("Please login first")
            return
        
        try:
            filename = packet.payload.decode("utf-8")
            target_path = self._safe_path(filename)
            os.remove(target_path)
            self.log.info(f"Deleted '{filename}' for user '{self.username}'.")
            ack_packet = Packet(Opcode.ACK, self.user_id, f"deleted:{filename}".encode("utf-8"))
            send_packet(self.sock, ack_packet)
        except FileNotFoundError:
            self._send_error(f"File '{filename}' not found")
        except Exception as e:
            self.log.error(f"Delete failed for {self.addr}: {e}")
            self._send_error(str(e))
    
    def _safe_path(self, filename: str) -> str:
        safe_name = os.path.basename(filename)
        if not safe_name:
            raise ValueError("Invalid filename")
        return os.path.join(self.user_storage_path, safe_name)
    
    def _decode_file_payload(self, payload: bytes):
        if len(payload) < 4:
            raise ValueError("Missing filename length")
        filename_len = struct.unpack(">I", payload[:4])[0]
        if len(payload) < 4 + filename_len:
            raise ValueError("Payload truncated")
        filename = payload[4:4 + filename_len].decode("utf-8")
        file_data = payload[4 + filename_len:]
        return filename, file_data
    
    def _send_error(self, message: str):
        error_packet = Packet(Opcode.ERROR, self.user_id, message.encode("utf-8"))
        send_packet(self.sock, error_packet)


def main():
    """Starts the server and listens for incoming connections."""
    server_log = setup_server_logger()
    server_log.info("Server starting...")
    
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((config.HOST, config.PORT))
    server_socket.listen(5)
    server_log.info(f"Server listening on {config.HOST}:{config.PORT}")
    
    while True:
        client_sock, client_addr = server_socket.accept()
        handler = ClientHandler(client_sock, client_addr, server_log)
        handler.start()


if __name__ == "__main__":
    os.makedirs(config.STORAGE_DIR, exist_ok=True)
    main()