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

# Load configuration from environment variables
config = Config(
    BOT_TOKEN=os.getenv("BOT_TOKEN", ""),
    IMGBB_API_KEY=os.getenv("IMGBB_API_KEY", ""),
    MAX_SIZE_MB=int(os.getenv("MAX_SIZE_MB", "10")),
    FLASK_PORT=int(os.getenv("FLASK_PORT", "8000")),
    FLASK_HOST=os.getenv("FLASK_HOST", "0.0.0.0")
)

# Validate required configuration
if not config.BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is required")
if not config.IMGBB_API_KEY:
    raise ValueError("IMGBB_API_KEY environment variable is required")
