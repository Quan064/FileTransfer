HOST = '127.0.0.1'  # Server's IP address (localhost)
PORT = 65432        # Port to listen on (non-privileged ports are > 1023)

STORAGE_DIR = "storage" # Directory on the server to store user files

CHUNK_SIZE = 4096   # 4KB chunk size for file transfers

SERVER_UPLOAD_RATE_KBPS = 1024 # Server's upload rate (client's download rate) in KB/s.
CLIENT_UPLOAD_RATE_KBPS = 512 # Client's upload rate in KB/s.