import os
import socket
import logging
import os
import socket
import threading
import time

import common.config as config
from common.logger import setup_server_logger
from protocol.framing import recv_packet, send_packet
from protocol.opcode import Opcode
from protocol.packet import Packet
from protocol.payloads import decode_file_metadata
from transfer.file_transfer import build_file_metadata_payload, receive_file_chunks, send_file_chunks


class UserStorage:
    """File-system namespace for one logged-in user."""
    
    def __init__(self, root_dir: str, username: str):
        self.root_dir = root_dir
        self.username = username
        self.path = os.path.join(root_dir, username)
        os.makedirs(self.path, exist_ok=True)
    
    def safe_path(self, filename: str) -> str:
        safe_name = os.path.basename(filename)
        if not safe_name:
            raise ValueError("Invalid filename")
        return os.path.join(self.path, safe_name)
    
    def list_files(self) -> list[str]:
        return [
            name for name in sorted(os.listdir(self.path))
            if os.path.isfile(os.path.join(self.path, name))
        ]
    
    def delete_file(self, filename: str) -> None:
        os.remove(self.safe_path(filename))

class ClientHandler(threading.Thread):
    """Receives packets from one client and dispatches them by opcode."""
    
    def __init__(self, sock: socket.socket, addr: tuple, logger: logging.Logger):
        super().__init__()
        self.sock = sock
        self.addr = addr
        self.log = logger
        self.user_id = 0
        self.username = ""
        self.storage = None
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
        except ConnectionError as exc:
            self.log.error(f"Connection error with {self.addr}: {exc}")
        finally:
            self.sock.close()
            self.log.info(f"Connection closed for {self.addr}")
    
    def process_packet(self, packet: Packet):
        """Processes a received packet based on its opcode."""
        COMMANDS = {
            Opcode.LOGIN: self.handle_login,
            Opcode.LOGOUT: self.handle_logout,
            Opcode.FILE_LIST: self.handle_file_list,
            Opcode.FILE_UPLOAD: self.handle_file_upload,
            Opcode.FILE_DOWNLOAD: self.handle_file_download,
            Opcode.FILE_DELETE: self.handle_file_delete,
        }
        
        self.log.debug(f"Received from {self.addr}: {packet}")
        handler = COMMANDS[packet.opcode]
        if handler is None:
            self.log.warning(f"Unknown or out-of-order opcode from {self.addr}: {packet.opcode.name}")
            self._send_error(self, "Invalid operation")
            return
        handler(packet)
    
    def handle_login(self, packet: Packet):
        try:
            self.username = packet.payload.decode("utf-8")
            self.user_id = packet.user_id
            self.storage = UserStorage(config.STORAGE_DIR, self.username)
            
            self.log.info(f"User '{self.username}' (ID: {self.user_id}) logged in from {self.addr}.")
            send_packet(self.sock, Packet(Opcode.ACK, self.user_id, Opcode.LOGIN.to_bytes(2, "big")))
        except Exception as exc:
            self.log.error(f"Error during login for {self.addr}: {exc}")
            self._send_error(str(exc))
    
    def handle_logout(self, packet: Packet):
        self.log.info(f"User '{self.username}' logged out from {self.addr}.")
        send_packet(self.sock, Packet(Opcode.ACK, self.user_id, b"logout"))
    
    def handle_file_list(self, packet: Packet):
        if not self._require_login():
            return
        
        start_time = time.perf_counter()
        payload = "\n".join(self.storage.list_files()).encode("utf-8")
        send_packet(self.sock, Packet(Opcode.FILE_LIST_RESP, self.user_id, payload))
        self._log_transfer("LIST", "-", 0, start_time)
    
    def handle_file_upload(self, packet: Packet):
        if not self._require_login():
            return
        
        start_time = time.perf_counter()
        filename = ""
        received = 0
        try:
            filename, total_size, expected_checksum = decode_file_metadata(packet.payload)
            target_path = self.storage.safe_path(filename)
            send_packet(self.sock, Packet(Opcode.ACK, self.user_id, Opcode.FILE_UPLOAD.to_bytes(2, "big")))
            
            received, actual_checksum = receive_file_chunks(
                self.sock,
                target_path,
                total_size,
                expected_checksum,
            )
            
            self._log_transfer("UPLOAD", filename, received, start_time)
            ack_payload = f"uploaded:{filename}:sha256:{actual_checksum}".encode("utf-8")
            send_packet(self.sock, Packet(Opcode.ACK, self.user_id, ack_payload))
        except Exception as exc:
            self.log.error(f"Upload failed for {self.addr}: {exc}")
            self._log_transfer("UPLOAD_FAILED", filename or "-", received, start_time)
            self._send_error(str(exc))
    
    def handle_file_download(self, packet: Packet):
        if not self._require_login():
            return
        
        start_time = time.perf_counter()
        filename = ""
        sent = 0
        try:
            filename = packet.payload.decode("utf-8")
            target_path = self.storage.safe_path(filename)
            metadata_payload, _, _ = build_file_metadata_payload(target_path, filename)
            send_packet(self.sock, Packet(Opcode.FILE_UPLOAD, self.user_id, metadata_payload))
            
            sent = send_file_chunks(self.sock, self.user_id, target_path)
            self._log_transfer("DOWNLOAD", filename, sent, start_time)
        except FileNotFoundError:
            self._send_error(f"File '{filename}' not found")
            self._log_transfer("DOWNLOAD_FAILED", filename or "-", sent, start_time)
        except Exception as exc:
            self.log.error(f"Download failed for {self.addr}: {exc}")
            self._log_transfer("DOWNLOAD_FAILED", filename or "-", sent, start_time)
            self._send_error(str(exc))
    
    def handle_file_delete(self, packet: Packet):
        if not self._require_login():
            return
        
        try:
            filename = packet.payload.decode("utf-8")
            self.storage.delete_file(filename)
            self.log.info(f"Deleted '{filename}' for user '{self.username}'.")
            send_packet(self.sock, Packet(Opcode.ACK, self.user_id, f"deleted:{filename}".encode("utf-8")))
        except FileNotFoundError:
            self._send_error(f"File '{filename}' not found")
        except Exception as exc:
            self.log.error(f"Delete failed for {self.addr}: {exc}")
            self._send_error(str(exc))
    
    def _send_error(self, message: str):
        try:
            send_packet(self.sock, Packet(Opcode.ERROR, self.user_id, message.encode("utf-8")))
        except ConnectionError:
            self.log.warning(f"Could not send error to disconnected client {self.addr}: {message}")
    
    def _log_transfer(self, command: str, filename: str, byte_count: int, start_time: float):
        elapsed = max(time.perf_counter() - start_time, 0.000001)
        speed_kbps = (byte_count / 1024) / elapsed
        self.log.info(
            "client=%s:%s user=%s command=%s file=%s bytes=%s elapsed=%.3fs speed=%.2fKB/s",
            self.addr[0],
            self.addr[1],
            self.username or "-",
            command,
            filename,
            byte_count,
            elapsed,
            speed_kbps,
        )
    
    def _require_login(self) -> bool:
        if self.username:
            return True
        self._send_error("Please login first")
        return False


if __name__ == "__main__":
    os.makedirs(config.STORAGE_DIR, exist_ok=True)
    
    # Starts the server and listens for incoming connections.
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