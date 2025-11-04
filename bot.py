import logging
import requests
from io import BytesIO
from telegram import Update, constants
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from flask import Flask, render_template_string, jsonify, request
import threading
import time
import os
from collections import defaultdict
from datetime import datetime, timedelta

# Import configuration
try:
    from config import config
except ImportError:
    # Fallback configuration
    class Config:
        BOT_TOKEN = os.getenv('BOT_TOKEN', 'your_bot_token_here')
        IMGBB_API_KEY = os.getenv('IMGBB_API_KEY', 'your_imgbb_api_key_here')
        MAX_SIZE_MB = int(os.getenv('MAX_SIZE_MB', 5))
        FLASK_HOST = os.getenv('FLASK_HOST', '0.0.0.0')
        FLASK_PORT = int(os.getenv('FLASK_PORT', 8080))
        MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024
        IMGBB_UPLOAD_URL = "https://api.imgbb.com/1/upload"
    
    config = Config()

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Rate Limiter Class
class RateLimiter:
    def __init__(self):
        self.user_requests = defaultdict(list)
    
    def is_limited(self, user_id: int, limit: int = 10, window: int = 60) -> bool:
        """Check if user has exceeded rate limit."""
        now = datetime.now()
        # Clean old requests
        self.user_requests[user_id] = [
            req_time for req_time in self.user_requests[user_id] 
            if now - req_time < timedelta(seconds=window)
        ]
        
        if len(self.user_requests[user_id]) >= limit:
            return True
        
        self.user_requests[user_id].append(now)
        return False

# Initialize rate limiter
rate_limiter = RateLimiter()

# Flask App - Use simple Flask without template folder
flask_app = Flask(__name__)

# Add startup time for health checks
STARTUP_TIME = time.time()
UPLOAD_COUNTER = 0

# HTML Template as string to avoid file issues
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Telegram Image Uploader Bot</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
        }

        .header {
            text-align: center;
            color: white;
            margin-bottom: 3rem;
            padding: 2rem 0;
        }

        .header h1 {
            font-size: 2.5rem;
            margin-bottom: 1rem;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }

        .header p {
            font-size: 1.2rem;
            opacity: 0.9;
            max-width: 600px;
            margin: 0 auto;
        }

        .main-content {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 2rem;
            margin-bottom: 3rem;
        }

        @media (max-width: 768px) {
            .main-content {
                grid-template-columns: 1fr;
            }
        }

        .card {
            background: white;
            border-radius: 15px;
            padding: 2rem;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        }

        .card h2 {
            color: #667eea;
            margin-bottom: 1.5rem;
            font-size: 1.5rem;
        }

        .features-list, .steps-list {
            list-style: none;
        }

        .features-list li, .steps-list li {
            padding: 0.8rem 0;
            border-bottom: 1px solid #eee;
        }

        .features-list li:last-child, .steps-list li:last-child {
            border-bottom: none;
        }

        .steps-list {
            counter-reset: step-counter;
        }

        .steps-list li {
            padding-left: 2.5rem;
            position: relative;
        }

        .steps-list li::before {
            content: counter(step-counter);
            counter-increment: step-counter;
            position: absolute;
            left: 0;
            top: 50%;
            transform: translateY(-50%);
            width: 1.8rem;
            height: 1.8rem;
            background: #667eea;
            color: white;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            font-size: 0.9rem;
        }

        .stats-section {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1.5rem;
            margin-bottom: 3rem;
        }

        .stat-card {
            background: rgba(255,255,255,0.1);
            border-radius: 10px;
            padding: 1.5rem;
            text-align: center;
            color: white;
            border: 1px solid rgba(255,255,255,0.2);
        }

        .stat-number {
            font-size: 2rem;
            font-weight: bold;
            margin-bottom: 0.5rem;
            display: block;
        }

        .stat-label {
            opacity: 0.9;
            font-size: 0.9rem;
        }

        .api-section {
            background: white;
            border-radius: 15px;
            padding: 2rem;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            margin-bottom: 2rem;
        }

        .endpoint {
            background: #f8f9fa;
            padding: 1rem;
            border-radius: 8px;
            border-left: 4px solid #667eea;
            margin: 0.5rem 0;
        }

        .endpoint-method {
            display: inline-block;
            padding: 0.3rem 0.8rem;
            background: #667eea;
            color: white;
            border-radius: 4px;
            font-weight: bold;
            font-size: 0.8rem;
            margin-right: 0.5rem;
        }

        .endpoint-path {
            font-family: 'Courier New', monospace;
            font-weight: bold;
            margin: 0.5rem 0;
        }

        .footer {
            text-align: center;
            color: white;
            padding: 2rem 0;
            margin-top: 3rem;
        }

        .service-status {
            display: inline-block;
            padding: 0.5rem 1rem;
            background: #28a745;
            color: white;
            border-radius: 25px;
            font-weight: bold;
            margin-top: 1rem;
        }
    </style>
</head>
<body>
    <div class="container">
        <header class="header">
            <h1>🤖 Image Uploader Bot</h1>
            <p>Upload images to ImgBB directly through Telegram. Fast, secure, and free!</p>
            <div class="service-status" id="serviceStatus">● Service Online</div>
        </header>

        <section class="stats-section">
            <div class="stat-card">
                <span class="stat-number" id="uptime">0</span>
                <span class="stat-label">Uptime (seconds)</span>
            </div>
            <div class="stat-card">
                <span class="stat-number">{{ max_size_mb }}</span>
                <span class="stat-label">Max File Size (MB)</span>
            </div>
            <div class="stat-card">
                <span class="stat-number" id="uploadCount">0</span>
                <span class="stat-label">Uploads Processed</span>
            </div>
            <div class="stat-card">
                <span class="stat-number">24/7</span>
                <span class="stat-label">Availability</span>
            </div>
        </section>

        <section class="main-content">
            <div class="card">
                <h2>🤖 Bot Features</h2>
                <ul class="features-list">
                    <li><strong>Easy Uploads:</strong> Just send photos directly to the bot</li>
                    <li><strong>Secure:</strong> Your images are uploaded directly to ImgBB</li>
                    <li><strong>Direct Links:</strong> Get instant ImgBB URLs for sharing</li>
                    <li><strong>File Management:</strong> Delete links provided for each upload</li>
                    <li><strong>Quality Preserved:</strong> Original image quality maintained</li>
                    <li><strong>Rate Limited:</strong> 10 uploads per minute per user</li>
                </ul>
            </div>

            <div class="card">
                <h2>📱 How to Use</h2>
                <ol class="steps-list">
                    <li>Start a chat with our Telegram bot</li>
                    <li>Send any image as a photo (not document)</li>
                    <li>Wait for the upload process to complete</li>
                    <li>Receive your ImgBB direct link instantly</li>
                    <li>Share the link or use the delete link to remove</li>
                </ol>
            </div>
        </section>

        <section class="api-section">
            <h2>⚡ API Endpoints</h2>
            <div class="endpoints">
                <div class="endpoint">
                    <span class="endpoint-method">GET</span>
                    <div class="endpoint-path">/health</div>
                    <div class="endpoint-description">Health check and service status with uptime and statistics</div>
                </div>
                <div class="endpoint">
                    <span class="endpoint-method">GET</span>
                    <div class="endpoint-path">/info</div>
                    <div class="endpoint-description">Service information and configuration details</div>
                </div>
                <div class="endpoint">
                    <span class="endpoint-method">GET</span>
                    <div class="endpoint-path">/</div>
                    <div class="endpoint-description">This information page</div>
                </div>
            </div>
        </section>

        <footer class="footer">
            <p>&copy; 2024 Telegram Image Uploader Bot. All rights reserved.</p>
            <p>Service powered by ImgBB API and Python Telegram Bot</p>
            <p style="margin-top: 1rem; font-size: 0.9rem;">
                Status: <span id="statusText">Checking...</span>
            </p>
        </footer>
    </div>

    <script>
        function updateStats() {
            fetch('/health')
                .then(response => {
                    if (!response.ok) throw new Error('Network error');
                    return response.json();
                })
                .then(data => {
                    document.getElementById('uptime').textContent = Math.round(data.uptime);
                    document.getElementById('uploadCount').textContent = data.uploads_processed || 0;
                    document.getElementById('statusText').textContent = 'Online - ' + Math.round(data.uptime) + ' seconds uptime';
                    
                    const statusElement = document.getElementById('serviceStatus');
                    if (data.status === 'ok') {
                        statusElement.style.background = '#28a745';
                        statusElement.textContent = '● Service Online';
                    }
                })
                .catch(error => {
                    document.getElementById('statusText').textContent = 'Offline - Unable to connect';
                    document.getElementById('serviceStatus').style.background = '#dc3545';
                    document.getElementById('serviceStatus').textContent = '● Service Offline';
                });
        }

        document.addEventListener('DOMContentLoaded', function() {
            updateStats();
            setInterval(updateStats, 10000);
        });
    </script>
</body>
</html>
'''

@flask_app.before_request
def before_request():
    """Log all requests for debugging."""
    logger.debug(f"Flask request: {request.method} {request.path}")

@flask_app.route("/", methods=['GET', 'HEAD', 'OPTIONS'])
def index():
    """Handle multiple request methods for the root route."""
    try:
        if request.method == 'HEAD':
            return '', 200
        elif request.method == 'OPTIONS':
            return '', 200
        
        # Use render_template_string instead of render_template
        return render_template_string(
            HTML_TEMPLATE, 
            max_size_mb=getattr(config, 'MAX_SIZE_MB', 5)
        )
    except Exception as e:
        logger.error(f"Error rendering index: {e}")
        # Fallback JSON response
        return jsonify({
            "name": "Telegram Image Uploader Bot",
            "status": "running",
            "message": "Bot is running successfully",
            "max_file_size_mb": getattr(config, 'MAX_SIZE_MB', 5),
            "endpoints": {
                "/health": "Health check",
                "/info": "Service information"
            }
        })

@flask_app.route("/health", methods=['GET', 'HEAD'])
def health():
    """Comprehensive health check endpoint."""
    if request.method == 'HEAD':
        return '', 200
    
    health_data = {
        "status": "ok",
        "service": "telegram-image-bot",
        "timestamp": time.time(),
        "uptime": round(time.time() - STARTUP_TIME, 2),
        "version": "1.0.0",
        "uploads_processed": UPLOAD_COUNTER
    }
    return jsonify(health_data)

@flask_app.route("/info")
def info():
    """Service information endpoint."""
    return jsonify({
        "name": "Telegram Image Uploader Bot",
        "description": "Upload images to ImgBB via Telegram",
        "version": "1.0.0",
        "max_file_size_mb": getattr(config, 'MAX_SIZE_MB', 5),
        "rate_limit": "10 uploads per minute per user",
        "supported_formats": "JPEG, PNG, GIF, WEBP"
    })

@flask_app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint not found"}), 404

@flask_app.errorhandler(405)
def method_not_allowed(error):
    return jsonify({"error": "Method not allowed"}), 405

@flask_app.errorhandler(500)
def internal_error(error):
    logger.error(f"Flask internal error: {error}")
    return jsonify({"error": "Internal server error"}), 500

@flask_app.after_request
def set_security_headers(response):
    """Add security headers to Flask responses."""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response

def run_flask():
    """Run Flask app in a separate thread"""
    logger.info(f"Starting Flask server on {config.FLASK_HOST}:{config.FLASK_PORT}")
    try:
        flask_app.run(
            host=config.FLASK_HOST, 
            port=config.FLASK_PORT, 
            debug=False,
            use_reloader=False
        )
    except Exception as e:
        logger.error(f"Flask server failed: {e}")

# --- TELEGRAM BOT HANDLERS ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message and instructions on /start."""
    welcome_message = (
        "🤖 *Welcome to Image Uploader Bot!*\n\n"
        "I can upload your images to ImgBB and provide you with direct links for sharing.\n\n"
        "✨ *Features:*\n"
        "• Fast image uploads to ImgBB\n"
        "• Direct URLs for easy sharing\n"
        "• Delete links for image management\n"
        "• Quality preservation\n\n"
        f"📁 *File Limit:* Max {getattr(config, 'MAX_SIZE_MB', 5)}MB per image\n"
        "⚡ *Rate Limit:* 10 uploads per minute\n\n"
        "📸 *How to use:* Just send me an image as a photo!\n"
        "Use /help for detailed instructions."
    )
    await update.message.reply_text(
        welcome_message,
        parse_mode=constants.ParseMode.MARKDOWN,
        disable_web_page_preview=True
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends help instructions."""
    help_message = (
        "📖 *How to Use This Bot*\n\n"
        "1. *Send an Image:* Take a photo or choose one from your gallery\n"
        "2. *Wait for Upload:* I'll process and upload it to ImgBB\n"
        "3. *Get Your Links:* Receive direct URL and delete link\n\n"
        "⚠️ *Important Notes:*\n"
        "• Send images as *Photos* (not documents)\n"
        f"• Maximum file size: {getattr(config, 'MAX_SIZE_MB', 5)}MB\n"
        "• Rate limit: 10 uploads per minute\n"
        "• Supported formats: JPEG, PNG, GIF, WEBP\n\n"
        "🔧 *Commands:*\n"
        "/start - Show welcome message\n"
        "/help - Show this help message\n"
        "/status - Check bot status\n\n"
        "Need help? Contact the administrator."
    )
    await update.message.reply_text(
        help_message,
        parse_mode=constants.ParseMode.MARKDOWN,
        disable_web_page_preview=True
    )

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Check bot status and statistics."""
    uptime = time.time() - STARTUP_TIME
    hours, remainder = divmod(int(uptime), 3600)
    minutes, seconds = divmod(remainder, 60)
    
    status_message = (
        "📊 *Bot Status*\n\n"
        f"• 🟢 Online\n"
        f"• ⏰ Uptime: {hours}h {minutes}m {seconds}s\n"
        f"• 📈 Uploads Processed: {UPLOAD_COUNTER}\n"
        f"• 📁 Max File Size: {getattr(config, 'MAX_SIZE_MB', 5)}MB\n"
        f"• 🚦 Rate Limit: 10/min per user\n"
        f"• 🔄 Service: Operational\n\n"
        "_All systems normal_"
    )
    await update.message.reply_text(
        status_message,
        parse_mode=constants.ParseMode.MARKDOWN
    )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles incoming photo messages, checks size, and uploads to ImgBB."""
    global UPLOAD_COUNTER
    message = update.message
    user_id = message.from_user.id
    
    # Check rate limiting
    if rate_limiter.is_limited(user_id):
        await message.reply_text(
            "🚫 *Rate Limit Exceeded*\n\n"
            "You've made too many upload requests. Please wait a minute before trying again.\n"
            "Limit: 10 uploads per minute.",
            parse_mode=constants.ParseMode.MARKDOWN
        )
        return
    
    # 1. Get the largest photo available
    photo_file = message.photo[-1]
    chat_id = message.chat_id
    
    # Send initial loading message
    await context.bot.send_chat_action(chat_id=chat_id, action=constants.ChatAction.UPLOAD_PHOTO)
    
    # 2. Get the file object to check size and download
    try:
        file = await context.bot.get_file(photo_file.file_id)
    except Exception as e:
        logger.error(f"Error retrieving file object for user {user_id}: {e}")
        await message.reply_text(
            "❌ *Error*: Could not retrieve the file details from Telegram.\n"
            "Please try again or send a different image.",
            parse_mode=constants.ParseMode.MARKDOWN
        )
        return
    
    # 3. Check the file size limit
    file_size_mb = file.file_size / (1024 * 1024)
    max_size_bytes = getattr(config, 'MAX_SIZE_BYTES', 5 * 1024 * 1024)
    if file.file_size > max_size_bytes:
        await message.reply_text(
            f"🚫 *File Too Large*\n\n"
            f"Your image is {file_size_mb:.2f}MB, but the maximum allowed is {getattr(config, 'MAX_SIZE_MB', 5)}MB.\n"
            f"Please send a smaller image.",
            parse_mode=constants.ParseMode.MARKDOWN
        )
        return

    # Send upload progress message
    progress_msg = await message.reply_text(
        f"📤 *Uploading Image*\n\n"
        f"• Size: {file_size_mb:.2f}MB\n"
        f"• Status: Downloading from Telegram...",
        parse_mode=constants.ParseMode.MARKDOWN
    )

    # 4. Download the file contents into memory
    file_bytes = BytesIO()
    try:
        await file.download_to_memory(file_bytes)
        file_bytes.seek(0)
    except Exception as e:
        logger.error(f"Error downloading photo for user {user_id}: {e}")
        await progress_msg.edit_text(
            "❌ *Download Failed*\n\n"
            "Could not download the image from Telegram servers.\n"
            "Please check your connection and try again.",
            parse_mode=constants.ParseMode.MARKDOWN
        )
        return

    # Update progress message
    await progress_msg.edit_text(
        f"📤 *Uploading Image*\n\n"
        f"• Size: {file_size_mb:.2f}MB\n"
        f"• Status: Uploading to ImgBB...",
        parse_mode=constants.ParseMode.MARKDOWN
    )

    # 5. Prepare and send the image to ImgBB
    payload = {
        'key': getattr(config, 'IMGBB_API_KEY', '')
    }
    
    files = {
        'image': ('image.jpg', file_bytes, 'image/jpeg')
    }

    try:
        # Perform the HTTP POST request to ImgBB
        imgbb_response = requests.post(
            getattr(config, 'IMGBB_UPLOAD_URL', 'https://api.imgbb.com/1/upload'), 
            data=payload, 
            files=files,
            timeout=30
        )
        imgbb_response.raise_for_status()
        
        data = imgbb_response.json()

        # 6. Process ImgBB response
        if data.get('success') and data.get('data'):
            image_data = data['data']
            image_url = image_data['url']
            delete_url = image_data['delete_url']
            image_title = image_data.get('title', 'Uploaded Image')
            
            # Update upload counter
            UPLOAD_COUNTER += 1
            
            # Send the result back to the user
            success_message = (
                "✅ *Upload Successful!*\n\n"
                f"📷 *Title:* {image_title}\n"
                f"📏 *Size:* {file_size_mb:.2f}MB\n"
                f"🔗 *Direct URL:* `{image_url}`\n\n"
                f"🗑️ *Delete URL:* `{delete_url}`\n\n"
                "_You can use the delete link to remove the image from ImgBB later._"
            )
            await progress_msg.edit_text(
                success_message,
                parse_mode=constants.ParseMode.MARKDOWN
            )
            logger.info(f"Successfully uploaded image for user {user_id}, size: {file_size_mb:.2f}MB")
            
        else:
            error_message = data.get('error', {}).get('message', 'Unknown upload error.')
            logger.error(f"ImgBB API error for user {user_id}: {error_message}")
            await progress_msg.edit_text(
                f"❌ *Upload Failed*\n\n"
                f"ImgBB returned an error:\n`{error_message}`\n\n"
                f"Please try again with a different image.",
                parse_mode=constants.ParseMode.MARKDOWN
            )

    except requests.exceptions.Timeout:
        logger.error(f"ImgBB upload timeout for user {user_id}")
        await progress_msg.edit_text(
            "❌ *Upload Timeout*\n\n"
            "The upload took too long to complete.\n"
            "Please try again with a smaller image or check your connection.",
            parse_mode=constants.ParseMode.MARKDOWN
        )
    except requests.exceptions.HTTPError as http_err:
        logger.error(f"HTTP error for user {user_id}: {http_err}")
        await progress_msg.edit_text(
            f"❌ *Upload Failed*\n\n"
            f"HTTP Error: {http_err.response.status_code}\n"
            f"Please try again later.",
            parse_mode=constants.ParseMode.MARKDOWN
        )
    except requests.exceptions.RequestException as req_err:
        logger.error(f"Request error for user {user_id}: {req_err}")
        await progress_msg.edit_text(
            "❌ *Upload Failed*\n\n"
            "Could not connect to the ImgBB server.\n"
            "Please check your internet connection and try again.",
            parse_mode=constants.ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Unexpected error during upload for user {user_id}: {e}")
        await progress_msg.edit_text(
            "❌ *Unexpected Error*\n\n"
            "An unexpected error occurred during the upload process.\n"
            "Please try again or contact support if the problem persists.",
            parse_mode=constants.ParseMode.MARKDOWN
        )
    finally:
        # Always close the BytesIO object
        file_bytes.close()

async def handle_document_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle images sent as documents."""
    document = update.message.document
    
    # Check if it's an image
    if document.mime_type and document.mime_type.startswith('image/'):
        await update.message.reply_text(
            "📎 *Image Sent as Document*\n\n"
            "I see you sent an image as a document. While I can process it, "
            "for best results please send images as *Photos* (using the gallery option).\n\n"
            "_Processing your document image..._",
            parse_mode=constants.ParseMode.MARKDOWN
        )
        
        # Use the same processing logic as handle_photo
        await handle_photo(update, context)
    else:
        await update.message.reply_text(
            "📎 *Document Received*\n\n"
            "I only process image files. Please send an image as a photo or an image document.\n\n"
            "Supported formats: JPEG, PNG, GIF, WEBP",
            parse_mode=constants.ParseMode.MARKDOWN
        )

async def fallback_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles any non-photo messages."""
    await update.message.reply_text(
        "🤖 *Hello!*\n\n"
        "I'm an image uploader bot. Send me a *photo* and I'll upload it to ImgBB for you!\n\n"
        "Use /help for instructions or /start for a proper introduction.",
        parse_mode=constants.ParseMode.MARKDOWN
    )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors in the telegram bot."""
    logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)
    
    # Try to notify user about the error if possible
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ *An unexpected error occurred*\n\n"
                "Please try again or contact support if the problem persists.",
                parse_mode=constants.ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Could not send error message to user: {e}")

def validate_config():
    """Validate that all required configuration variables are present."""
    required_vars = ['BOT_TOKEN', 'IMGBB_API_KEY']
    
    for var in required_vars:
        if not hasattr(config, var):
            raise ValueError(f"Missing required configuration: {var}")
        
        value = getattr(config, var)
        if not value or value == f'your_{var.lower()}_here':
            raise ValueError(f"Please set the {var} in your configuration")
    
    logger.info("Configuration validation passed")

def main() -> None:
    """Start the bot and Flask server."""
    
    # Validate configuration first
    try:
        validate_config()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        raise
    
    # Start Flask in a separate thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info(f"Flask server started on http://{config.FLASK_HOST}:{config.FLASK_PORT}")
    
    # Create the Application and pass your bot's token
    application = Application.builder().token(config.BOT_TOKEN).build()

    # Register handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, handle_photo))
    application.add_handler(MessageHandler(filters.Document.IMAGE & ~filters.COMMAND, handle_document_image))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fallback_text))
    
    # Register error handler
    application.add_error_handler(error_handler)

    # Start the Bot
    logger.info("Starting Telegram bot polling...")
    logger.info(f"Bot is ready! Maximum file size: {getattr(config, 'MAX_SIZE_MB', 5)}MB")
    
    try:
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
    except Exception as e:
        logger.error(f"Bot polling failed: {e}")
        raise

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
