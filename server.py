import socket
import logging
import os
import threading
import time
import csv

import common.config as config
from common.storage import UserStorage
from common.logger import setup_server_logger

from protocol.framing import RateLimiter, recv_packet, send_packet
from protocol.opcode import Opcode
from protocol.packet import Packet
from protocol.payload import decode_file_metadata, encode_struct_data

from transfer.file_transfer import build_file_metadata_payload, receive_file_chunks, send_file_chunks


class ClientHandler(threading.Thread):
    """Receives packets from one client and dispatches them by opcode."""
    
    def __init__(self, sock: socket.socket, addr: tuple, logger: logging.Logger, semaphore: threading.Semaphore | None = None):
        super().__init__()
        self.sock = sock
        self.addr = addr
        self.log = logger
        self.semaphore = semaphore
        self.user_id = 0
        self.username = ""
        self.storage = None
        self.log.info(f"New connection from {self.addr}")
    
    def run(self):
        """
        Main loop to receive and process packets from the client.
        Releases the semaphore when the connection is closed.
        """
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
            if self.semaphore:
                self.semaphore.release()
    
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
        handler = COMMANDS.get(packet.opcode)
        if handler is None:
            self.log.warning(f"Unknown or out-of-order opcode from {self.addr}: {packet.opcode.name}")
            self._send_error("Invalid operation")
            return
        handler(packet)
    
    def handle_login(self, packet: Packet):
        try:
            self.username = packet.payload.decode("utf-8")
            self.storage = UserStorage(config.STORAGE_DIR, self.username)
            self.log.info(f"User '{self.username}' logged in from {self.addr}.")
            
            users_data = []
            with open(config.USER_INFO, "a+", newline="", encoding="utf-8") as f:
                f.seek(0)
                reader = csv.reader(f)
                
                for row in reader:
                    if not row: continue
                    username, user_id = row[0], int(row[1])
                    users_data.append([username, user_id])
                    
                    if username == self.username:
                        self.user_id = user_id
                        break
                else:
                    existing_ids = {user[1] for user in users_data}
                    new_id = 1
                    
                    while new_id in existing_ids:
                        new_id += 1
                    
                    self.user_id = new_id
                    users_data.append([self.username, self.user_id])
                    users_data.sort(key=lambda x: x[1])
                    
                    f.seek(0)
                    f.truncate()
                    writer = csv.writer(f)
                    writer.writerows(users_data)
            
            ack_payload = encode_struct_data(">HQ", Opcode.LOGIN.value, self.user_id)
            send_packet(self.sock, Packet(Opcode.ACK, self.user_id, ack_payload))
        
        except Exception as exc:
            self.log.error(f"Error during login for {self.addr}: {exc}")
            self._send_error(str(exc))
    
    def handle_logout(self, packet: Packet):
        if not self._require_login():
            return
        
        try:
            logged_out_user = self.username
            logged_out_user_id = self.user_id
            
            users_data = []
            with open(config.USER_INFO, "a+", newline="", encoding="utf-8") as f:
                f.seek(0)
                reader = csv.reader(f)
                
                for row in reader:
                    if not row: continue
                    if row[0] != logged_out_user:
                        users_data.append(row)
                
                f.seek(0)
                f.truncate()
                writer = csv.writer(f)
                writer.writerows(users_data)
            
            self.log.info(f"User '{logged_out_user}' logged out from {self.addr}.")
            send_packet(self.sock, Packet(Opcode.ACK, logged_out_user_id, b"logout"))
            
            self.username = ""
            self.user_id = 0
            self.storage = None
        
        except Exception as exc:
            self.log.error(f"Error during logout for {self.addr}: {exc}")
            self._send_error(str(exc))
    
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
            # Decode the initial metadata packet from the client (filename, total size, checksum).
            filename, total_size, expected_checksum = decode_file_metadata(packet.payload)
            target_path = self.storage.safe_path(filename)
            
            # Check for an existing partial file to support upload resuming.
            offset = 0
            if os.path.exists(target_path):
                current_size = os.path.getsize(target_path)
                if current_size == total_size:
                    self._send_error(f"File '{filename}' with the same size already exists.")
                    return
                elif current_size > total_size:
                    self._send_error(f"Existing file '{filename}' is larger than the new file.")
                    return
                offset = current_size
            
            # Send an ACK packet which contains offset.
            ack_payload = encode_struct_data('>HQ', Opcode.FILE_UPLOAD.value, offset)
            send_packet(self.sock, Packet(Opcode.ACK, self.user_id, ack_payload))
            
            # Receiving file chunks from the client, starting from the specified offset.
            start_time = time.perf_counter()
            received, actual_checksum = receive_file_chunks(
                self.sock,
                target_path,
                total_size,
                expected_checksum,
                offset=offset,
                progress_callback=None
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
            # Get the requested filename from the client's packet.
            filename = packet.payload.decode("utf-8")
            target_path = self.storage.safe_path(filename)
            
            # Send a metadata packet to the client so it knows the file's name, size, and checksum.
            metadata_payload, _, _ = build_file_metadata_payload(target_path, filename)
            send_packet(self.sock, Packet(Opcode.FILE_UPLOAD, self.user_id, metadata_payload))
            
            # Create a rate limiter to throttle the server's upload speed (client's download speed).
            limiter = RateLimiter(config.SERVER_UPLOAD_RATE_KBPS)
            
            # Start streaming the file chunks to the client.
            start_time = time.perf_counter()
            sent = send_file_chunks(self.sock, self.user_id, target_path, limiter=limiter, progress_callback=None)
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
        elapsed = max(time.perf_counter() - start_time, 1e-7)
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
    server_socket.bind(("0.0.0.0", config.PORT))
    server_socket.listen(5)
    
    HOST = socket.gethostbyname(socket.gethostname())
    server_log.info(f"Server listening on {HOST}:{config.PORT}")
    
    # Create a semaphore to limit the number of concurrent clients
    client_semaphore = threading.Semaphore(config.MAX_CONCURRENT_CLIENTS)
    
    while True:
        client_sock, client_addr = server_socket.accept()
        
        # Try to acquire a semaphore slot without blocking.
        if client_semaphore.acquire(blocking=False):
            handler = ClientHandler(client_sock, client_addr, server_log, semaphore=client_semaphore)
            handler.start()
        
        # If no slots are available, reject the connection.
        else:
            server_log.warning(f"Connection rejected from {client_addr}: server at full capacity.")
            try:
                error_packet = Packet(Opcode.ERROR, 0, b"Server at full capacity. Please try again later.")
                send_packet(client_sock, error_packet)
            finally:
                client_sock.close()
