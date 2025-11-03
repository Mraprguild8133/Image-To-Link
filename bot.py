import logging
import requests
from io import BytesIO
from telegram import Update, constants
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from flask import Flask, render_template, jsonify
import threading

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

@flask_app.route("/")
def index():
    return render_template("index.html")

@flask_app.route("/health")
def health():
    return jsonify({"status": "ok"})

def run_flask():
    """Run Flask app in a separate thread"""
    flask_app.run(host="0.0.0.0", port=8000, debug=False)

# --- HANDLERS ---

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

    await message.reply_text(f"Uploading file ({file.file_size / (1024 * 1024):.2f}MB)... Please wait.")

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
        else:
            error_message = data.get('error', 'Unknown upload error.')
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

# --- MAIN FUNCTION ---

def main() -> None:
    """Start the bot and Flask server."""
    
    # Start Flask in a separate thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("Flask server started on http://0.0.0.0:8000")
    
    # Create the Application and pass your bot's token.
    application = Application.builder().token(config.BOT_TOKEN).build()

    # Register handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, handle_photo))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, fallback_text))

    # Start the Bot
    logger.info("Starting polling...")
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
