import logging
import requests
from io import BytesIO
from telegram import Update, constants
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from flask import Flask, render_template, jsonify, request
import threading
import time
import os

# Import configuration
from config import config

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Flask App
flask_app = Flask(__name__, template_folder="templates")

# Add startup time for health checks
STARTUP_TIME = time.time()

@flask_app.before_request
def before_request():
    """Log all requests for debugging."""
    logger.debug(f"Flask request: {request.method} {request.path}")

@flask_app.route("/", methods=['GET', 'HEAD', 'OPTIONS'])
def index():
    """Handle multiple request methods for the root route."""
    if request.method == 'HEAD':
        return '', 200
    elif request.method == 'OPTIONS':
        return '', 200
    return render_template("index.html")

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
        "version": "1.0.0"
    }
    return jsonify(health_data)

@flask_app.route("/info")
def info():
    """Service information endpoint."""
    return jsonify({
        "name": "Telegram Image Uploader Bot",
        "description": "Upload images to ImgBB via Telegram",
        "version": "1.0.0",
        "max_file_size_mb": config.MAX_SIZE_MB
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

def run_flask():
    """Run Flask app in a separate thread"""
    logger.info(f"Starting Flask server on {config.FLASK_HOST}:{config.FLASK_PORT}")
    flask_app.run(host=config.FLASK_HOST, port=config.FLASK_PORT, debug=False)

# --- TELEGRAM BOT HANDLERS ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message and instructions on /start."""
    welcome_message = (
        "Hello! I'm your Image Uploader Bot. 📸\n\n"
        "Just send me an image (as a *photo*, not a document) and I will "
        "upload it to ImgBB and send you the direct URL.\n\n"
        f"🚨 *File Limit:* Images must be under {config.MAX_SIZE_MB}MB."
    )
    await update.message.reply_text(
        welcome_message,
        parse_mode=constants.ParseMode.MARKDOWN
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends help instructions."""
    help_message = (
        "How to use:\n"
        "1. Send a single image to this chat.\n"
        "2. Ensure the image is sent as a *Photo* (not compressed as a file).\n"
        f"3. The file size limit is {config.MAX_SIZE_MB}MB.\n"
        "I will reply with the ImgBB link upon successful upload."
    )
    await update.message.reply_text(help_message)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles incoming photo messages, checks size, and uploads to ImgBB."""
    message = update.message
    
    # 1. Get the largest photo available
    photo_file = message.photo[-1]
    chat_id = message.chat_id
    
    # Send initial loading message
    await context.bot.send_chat_action(chat_id=chat_id, action=constants.ChatAction.UPLOAD_PHOTO)
    
    # 2. Get the file object to check size and download
    try:
        file = await context.bot.get_file(photo_file.file_id)
    except Exception as e:
        logger.error(f"Error retrieving file object: {e}")
        await message.reply_text("❌ Error: Could not retrieve the file details from Telegram. Please try again.")
        return
    
    # 3. Check the file size limit
    if file.file_size > config.MAX_SIZE_BYTES:
        await message.reply_text(
            f"🚫 *Error*: The image is too large ({file.file_size / (1024 * 1024):.2f}MB). "
            f"The limit is {config.MAX_SIZE_MB}MB.",
            parse_mode=constants.ParseMode.MARKDOWN
        )
        return

    await message.reply_text(f"📤 Uploading file ({file.file_size / (1024 * 1024):.2f}MB)... Please wait.")

    # 4. Download the file contents into memory
    file_bytes = BytesIO()
    try:
        await file.download_to_memory(file_bytes)
        file_bytes.seek(0)
    except Exception as e:
        logger.error(f"Error downloading photo: {e}")
        await message.reply_text("❌ Error: Could not download the image from Telegram servers.")
        return

    # 5. Prepare and send the image to ImgBB
    payload = {
        'key': config.IMGBB_API_KEY
    }
    
    files = {
        'image': ('image.jpg', file_bytes, 'image/jpeg')
    }

    try:
        # Perform the HTTP POST request to ImgBB
        imgbb_response = requests.post(config.IMGBB_UPLOAD_URL, data=payload, files=files)
        imgbb_response.raise_for_status()
        
        data = imgbb_response.json()

        # 6. Process ImgBB response
        if data.get('success') and data.get('data'):
            image_url = data['data']['url']
            delete_url = data['data']['delete_url']
            
            # Send the result back to the user
            success_message = (
                "✅ *Upload Successful!*\n\n"
                f"*Direct URL:* `{image_url}`\n\n"
                f"You can delete this image later using this link: `{delete_url}`"
            )
            await message.reply_text(
                success_message,
                parse_mode=constants.ParseMode.MARKDOWN
            )
            logger.info(f"Successfully uploaded image for user {message.from_user.id}")
        else:
            error_message = data.get('error', {}).get('message', 'Unknown upload error.')
            logger.error(f"ImgBB API error: {error_message}")
            await message.reply_text(f"❌ ImgBB Upload Failed: {error_message}")

    except requests.exceptions.HTTPError as http_err:
        logger.error(f"HTTP error occurred: {http_err}")
        await message.reply_text(f"❌ Upload Failed due to HTTP Error: {http_err.response.status_code}")
    except requests.exceptions.RequestException as req_err:
        logger.error(f"Request error occurred: {req_err}")
        await message.reply_text("❌ Upload Failed: Could not connect to the ImgBB server.")
    except Exception as e:
        logger.error(f"An unexpected error occurred during upload: {e}")
        await message.reply_text("❌ An unexpected error occurred during the upload process.")

async def fallback_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles any non-photo messages."""
    await update.message.reply_text(
        "I only handle image uploads. Please send me a *photo* to upload."
    )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors in the telegram bot."""
    logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)

# --- MAIN FUNCTION ---

def main() -> None:
    """Start the bot and Flask server."""
    
    # Start Flask in a separate thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info(f"Flask server started on http://{config.FLASK_HOST}:{config.FLASK_PORT}")
    
    # Create the Application and pass your bot's token.
    application = Application.builder().token(config.BOT_TOKEN).build()

    # Register handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, handle_photo))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fallback_text))
    
    # Register error handler
    application.add_error_handler(error_handler)

    # Start the Bot
    logger.info("Starting Telegram bot polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    try:
        main()
    except ValueError as e:
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print(f"Configuration Error: {e}")
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
