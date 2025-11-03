import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Telegram Bot Token
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    
    # ImgBB API Configuration
    IMGBB_API_KEY = os.getenv('IMGBB_API_KEY')
    IMGBB_UPLOAD_URL = "https://api.imgbb.com/1/upload"
    
    # File size limits
    MAX_SIZE_MB = 10
    MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024
    
    # Status server
    STATUS_SERVER_URL = "http://localhost:8000"

# Validate required configuration
def validate_config():
    required_vars = ['BOT_TOKEN', 'IMGBB_API_KEY']
    missing = [var for var in required_vars if not getattr(Config, var)]
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

config = Config
