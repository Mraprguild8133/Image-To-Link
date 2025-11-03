import os
from dataclasses import dataclass

@dataclass
class Config:
    BOT_TOKEN: str
    IMGBB_API_KEY: str
    MAX_SIZE_MB: int = 10
    IMGBB_UPLOAD_URL: str = "https://api.imgbb.com/1/upload"
    FLASK_PORT: int = 8000
    FLASK_HOST: str = "0.0.0.0"
    
    @property
    def MAX_SIZE_BYTES(self) -> int:
        return self.MAX_SIZE_MB * 1024 * 1024

# Load configuration
config = Config(
    BOT_TOKEN=os.getenv("BOT_TOKEN", ""),
    IMGBB_API_KEY=os.getenv("IMGBB_API_KEY", "")
)

if not config.BOT_TOKEN or not config.IMGBB_API_KEY:
    raise ValueError("BOT_TOKEN and IMGBB_API_KEY must be set")
