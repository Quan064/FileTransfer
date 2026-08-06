import os


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
