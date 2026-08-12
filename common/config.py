HOST = '127.0.0.1'  # Server's IP address (localhost)
PORT = 65432        # Port to listen on (non-privileged ports are > 1023)

STORAGE_DIR = "interface_server/storage" # Directory on the server to store user files
USER_INFO = "interface_server/user_info.csv" # File containing user information
LOGIN_STATE_FILE = "interface_client/login_state.json" # File to store login state information

CHUNK_SIZE = 4096   # 4KB chunk size for file transfers

SERVER_UPLOAD_RATE_KBPS = 1024 # Server's upload rate (client's download rate) in KB/s.
CLIENT_UPLOAD_RATE_KBPS = 512  # Client's upload rate in KB/s.

MAX_CONCURRENT_CLIENTS = 50 # Maximum number of clients the server can handle simultaneously.