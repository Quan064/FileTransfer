import shlex
import sys
import os
import json
import socket

import common.config as config

from protocol.framing import RateLimiter, recv_packet, send_packet
from protocol.opcode import Opcode
from protocol.packet import Packet
from protocol.payload import decode_file_metadata, decode_struct_data

from transfer.file_transfer import build_file_metadata_payload, receive_file_chunks, send_file_chunks

STATE_FILE = os.path.join(os.path.dirname(__file__), config.LOGIN_STATE_FILE)


class Client:
    """Manages the connection and communication with the server."""
    
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.sock = None
        self.user_id = 0
    
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
        if not self.sock and not self.connect():
            return False
        
        self.user_id = user_id
        send_packet(self.sock, Packet(Opcode.LOGIN, self.user_id, username.encode("utf-8")))
        
        response = recv_packet(self.sock)
        if response and response.opcode == Opcode.ACK:
            self._save_state(username, user_id)
            print(f"[*] Login successful as '{username}'.")
            return True
        
        print("[!] Login failed. Server response:", self._format_response(response))
        return False
    
    def logout(self, username: str | None = None, user_id: int | None = None):
        """Logs out from the server and closes the connection."""
        if not self._ensure_login(username, user_id):
            return False
        
        send_packet(self.sock, Packet(Opcode.LOGOUT, self.user_id, b""))
        response = recv_packet(self.sock)
        if response and response.opcode == Opcode.ACK:
            print("[*] Logged out.")
            return True
        
        print("[!] Logout failed.", self._format_response(response))
        return False
    
    def list_files(self, username: str | None = None, user_id: int | None = None):
        """Requests the file list from the server."""
        if not self._ensure_login(username, user_id):
            return False
        
        send_packet(self.sock, Packet(Opcode.FILE_LIST, self.user_id, b""))
        response = recv_packet(self.sock)
        if response and response.opcode == Opcode.FILE_LIST_RESP:
            payload = response.payload.decode("utf-8")
            print(payload if payload else "[+] No files found.")
            return True
        
        print("[!] Failed to retrieve file list.")
        return False
    
    def upload_file(self, local_path: str, remote_name: str | None = None, username: str | None = None, user_id: int | None = None):
        """Uploads a local file to the user's storage folder on the server."""
        if not self._ensure_login(username, user_id):
            print("[!] Please login first: python client.py login <username> <user_id>")
            return False
        
        # Check if the local file exists.
        if not os.path.isfile(local_path):
            print(f"[!] File not found: {local_path}")
            return False
        
        filename = remote_name or os.path.basename(local_path)
        if not filename:
            print("[!] Invalid filename.")
            return False
        
        # Build the metadata payload (filename, size, checksum) and initialize handshake.
        payload, _, checksum = build_file_metadata_payload(local_path, filename)
        send_packet(self.sock, Packet(Opcode.FILE_UPLOAD, self.user_id, payload))
        
        # Wait for the server's response which contains the offset for resuming a partial upload.
        response = recv_packet(self.sock)
        if not response or response.opcode != Opcode.ACK:
            print("[!] Upload failed.", self._format_response(response))
            return False
        
        acked_opcode_val, next_offset = decode_struct_data('>HQ', response.payload)
        if (acked_opcode := Opcode(acked_opcode_val)) != Opcode.FILE_UPLOAD:
            print(f"[!] Server acknowledged wrong opcode: {acked_opcode.name}")
            return False
        
        # Create RateLimiter to throttle the upload speed according to the configuration.
        limiter = RateLimiter(config.CLIENT_UPLOAD_RATE_KBPS)
        
        # Start sending file chunks, beginning from the received offset.
        print(f"[*] Server is ready. Starting upload from offset {next_offset}...")
        send_file_chunks(self.sock, self.user_id, local_path, offset=next_offset, limiter=limiter)
        
        response = recv_packet(self.sock)
        if response and response.opcode == Opcode.ACK:
            print(f"[*] Uploaded '{filename}'. Checksum OK: {checksum}")
            return True
        
        print("[!] Upload failed.", self._format_response(response))
        return False
    
    def download_file(self, remote_name: str, local_path: str, username: str | None = None, user_id: int | None = None):
        """Downloads a file from the server into a local path."""
        if not self._ensure_login(username, user_id):
            print("[!] Please login first: python client.py login <username> <user_id>")
            return False
        
        # Send a download request to the server with the remote filename.
        send_packet(self.sock, Packet(Opcode.FILE_DOWNLOAD, self.user_id, remote_name.encode("utf-8")))
        
        # Wait for the server's response, which should contain the file's metadata.
        response = recv_packet(self.sock)
        if not response or response.opcode != Opcode.FILE_UPLOAD:
            print("[!] Download failed.", self._format_response(response))
            return False
        
        try:
            # Decode the metadata to get the filename, total size, and expected checksum.
            filename, total_size, expected_checksum = decode_file_metadata(response.payload)
            target_path = self._resolve_download_path(local_path, filename or remote_name)
            target_dir = os.path.dirname(target_path)
            
            # Check if a partial file exists locally to support resuming the download.
            current_size = 0
            if os.path.exists(target_path):
                current_size = os.path.getsize(target_path)
            print(f"[*] Starting download to '{target_path}'. Resuming from {current_size} bytes.")
            
            # Start receiving file chunks from the server and writing them to the target path.
            if target_dir:
                os.makedirs(target_dir, exist_ok=True)
            _, actual_checksum = receive_file_chunks(
                self.sock,
                target_path,
                total_size,
                expected_checksum,
                offset=current_size,
            )
        except (ConnectionError, OSError, ValueError) as exc:
            print(f"[!] Download failed: {exc}")
            return False
        
        print(f"[*] Downloaded '{remote_name}' to '{target_path}'. Checksum OK: {actual_checksum}")
        return True
    
    def delete_file(self, remote_name: str, username: str | None = None, user_id: int | None = None):
        """Deletes a file from the server for the current user."""
        if not self._ensure_login(username, user_id):
            return False
        
        send_packet(self.sock, Packet(Opcode.FILE_DELETE, self.user_id, remote_name.encode("utf-8")))
        response = recv_packet(self.sock)
        if response and response.opcode == Opcode.ACK:
            print(f"[*] Deleted '{remote_name}'.")
            return True
        
        print("[!] Delete failed.", self._format_response(response))
        return False
    
    def close(self):
        """Closes the connection to the server."""
        if self.sock:
            self.sock.close()
            self.sock = None
            print("[*] Connection closed.")
    
    def _ensure_login(self, username: str | None, user_id: int | None):
        state = self._load_state()
        if username is None and state:
            username = state["username"]
            user_id = state["user_id"]
        
        if username is None or user_id is None:
            return False
        
        if not self.sock and not self.connect():
            return False
        
        if self.user_id == 0 and self.sock:
            return self.login(username, user_id)
        return True
    
    def _save_state(self, username: str, user_id: int):
        with open(STATE_FILE, "w", encoding="utf-8") as handle:
            json.dump({"username": username, "user_id": user_id}, handle)
    
    def _load_state(self):
        if not os.path.exists(STATE_FILE):
            print("[*] No previous login state found.")
            return None
        with open(STATE_FILE, "r", encoding="utf-8") as handle:
            return json.load(handle)
    
    def _resolve_download_path(self, local_path: str, remote_name: str) -> str:
        """Resolve the final file path for a download request."""
        if os.path.isdir(local_path) or local_path.endswith(os.path.sep) or local_path.endswith("/") or local_path.endswith("\\"):
            return os.path.join(local_path, os.path.basename(remote_name))
        return local_path
    
    def _format_response(self, response: Packet | None):
        if response and response.opcode == Opcode.ERROR:
            return response.payload.decode("utf-8", errors="replace")
        return response


def split_command(raw_command: str) -> list[str]:
    """Split interactive commands without treating Windows backslashes as escapes."""
    if os.name != "nt":
        return shlex.split(raw_command)
    return [part.strip("\"'") for part in shlex.split(raw_command, posix=False)]

def run_interactive_session(client: Client, username: str, user_id: int):
    """Keeps the connection open so the user can issue multiple commands in one session."""
    print(f"[*] Interactive session started for '{username}'. Type 'help' or 'exit'.")
    while True:
        try:
            raw_command = input("> ").strip()
        except EOFError:
            break
        
        if not raw_command:
            continue
        
        parts = split_command(raw_command)
        action = parts[0].lower()
        
        if action in {"exit", "quit"}:
            break
        
        if action == "help":
            print("Commands: list | upload <local_path> [remote_name] | download <remote_name> <local_path> | delete <remote_name> | logout | exit")
        
        elif action == "list":
            client.list_files(username=username, user_id=user_id)
        
        elif action == "upload":
            if len(parts) < 2:
                print("Usage: upload <local_path> [remote_name]")
                continue
            local_path = parts[1]
            remote_name = parts[2] if len(parts) > 2 else None
            client.upload_file(local_path, remote_name=remote_name, username=username, user_id=user_id)
        
        elif action == "download":
            if len(parts) < 3:
                print("Usage: download <remote_name> <local_path>")
                continue
            client.download_file(parts[1], parts[2], username=username, user_id=user_id)
        
        elif action == "delete":
            if len(parts) < 2:
                print("Usage: delete <remote_name>")
                continue
            client.delete_file(parts[1], username=username, user_id=user_id)
        
        elif action == "logout":
            client.logout(username=username, user_id=user_id)
            break
        
        else:
            print("Unknown command. Type 'help'.")
    
    client.close()

def print_usage():
    print("Usage: python client.py <login|upload|list|download|delete> ...           ")
    print("  login                               <username> [user_id] [--interactive]")
    print("  list                                [username] [user_id]                ")
    print("  upload   <local_path> [remote_name] [username] [user_id]                ")
    print("  download <remote_name> <local_path> [username] [user_id]                ")
    print("  delete   <remote_name>              [username] [user_id]                ")
    print("  logout                                                                  ")


if __name__ == "__main__":
    # Main function to run the client CLI.
    client = Client(config.HOST, config.PORT)
    
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)
    
    command = sys.argv[1].lower()
    try:
        if command == "login":
            if len(sys.argv) < 3:
                raise ValueError("[!] Usage: python client.py login <username> [user_id] [--interactive]")
            username = sys.argv[2]
            user_id = int(sys.argv[3]) if len(sys.argv) > 3 else None
            interactive = "--interactive" in sys.argv[4:]
            if client.login(username, user_id) and interactive:
                run_interactive_session(client, username, user_id)
        
        elif command == "upload":
            if len(sys.argv) < 3:
                raise ValueError("[!] Usage: python client.py upload <local_path> [remote_name] [username] [user_id]")
            local_path = sys.argv[2]
            remote_name = sys.argv[3] if len(sys.argv) > 3 else None
            username = sys.argv[4] if len(sys.argv) > 4 else None
            user_id = int(sys.argv[5]) if len(sys.argv) > 5 else None
            client.upload_file(local_path, remote_name=remote_name, username=username, user_id=user_id)
        
        elif command == "list":
            username = sys.argv[2] if len(sys.argv) > 2 else None
            user_id = int(sys.argv[3]) if len(sys.argv) > 3 else None
            client.list_files(username=username, user_id=user_id)
        
        elif command == "download":
            if len(sys.argv) < 4:
                raise ValueError("[!] Usage: python client.py download <remote_name> <local_path> [username] [user_id]")
            remote_name = sys.argv[2]
            local_path = sys.argv[3]
            username = sys.argv[4] if len(sys.argv) > 4 else None
            user_id = int(sys.argv[5]) if len(sys.argv) > 5 else None
            client.download_file(remote_name, local_path, username=username, user_id=user_id)
        
        elif command == "delete":
            if len(sys.argv) < 3:
                raise ValueError("[!] Usage: python client.py delete <remote_name> [username] [user_id]")
            remote_name = sys.argv[2]
            username = sys.argv[3] if len(sys.argv) > 3 else None
            user_id = int(sys.argv[4]) if len(sys.argv) > 4 else None
            client.delete_file(remote_name, username=username, user_id=user_id)
        
        else:
            print_usage()
    
    except Exception as error:
        print(error)

    finally:
        client.close()
