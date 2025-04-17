import logging
import random
import json
import os
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ParseMode,
)
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    Filters,
    CallbackContext,
)
from flask import Flask
from threading import Thread

# ----------------------------- Logging Setup ----------------------------- #
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ----------------------------- Load Questions from JSON ----------------------------- #
def load_questions():
    try:
        with open('questions.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        valid_questions = []
        for q in data:
            if isinstance(q, dict) and "question" in q and "options" in q and isinstance(q["options"], list):
                valid_questions.append(q)
            else:
                logger.warning(f"Invalid question format skipped: {q}")
        logger.info(f"Loaded {len(valid_questions)} valid questions from JSON file.")
        return valid_questions
    except Exception as e:
        logger.error(f"Failed to load questions from JSON: {e}")
        return []

questions = load_questions()

# ------------------------- Persistent Chat Configuration ------------------------- #
CONFIG_FILE = 'chat_config.json'
chat_config = {}

def load_chat_config():
    global chat_config
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                chat_config = json.load(f)
            logger.info("Chat configuration loaded from file.")
        except Exception as e:
            logger.error(f"Failed to load chat config: {e}")
            chat_config = {}
    else:
        chat_config = {}

def save_chat_config():
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(chat_config, f)
    except Exception as e:
        logger.error(f"Failed to save chat config: {e}")

def ensure_chat_config(chat_id: int):
    if str(chat_id) not in chat_config:
        chat_config[str(chat_id)] = {
            "language": "English",
            "auto_delete": True,
            "auto_pin": False,
            "last_quiz_id": None,
            "active": True
        }
        save_chat_config()
    return chat_config[str(chat_id)]

# ----------------------------- Utility Functions ----------------------------- #

def get_random_question():
    if not questions:
        return None
    return random.choice(questions)

def get_valid_random_question():
    if not questions:
        return None
    valid_questions = [q for q in questions if len(q["question"].split()) <= 100]
    if valid_questions:
        return random.choice(valid_questions)
    else:
        logger.warning("No valid questions with 100 words or less available.")
        return None

def is_user_admin(update: Update, context: CallbackContext) -> bool:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    try:
        member = context.bot.get_chat_member(chat_id, user_id)
        if member.status in ["administrator", "creator"]:
            return True
    except Exception as e:
        logger.warning(f"Admin check failed: {e}")
    return False

def has_pin_permission(chat_id: int, context: CallbackContext) -> bool:
    try:
        bot_member = context.bot.get_chat_member(chat_id, context.bot.id)
        if hasattr(bot_member, "can_pin_messages") and bot_member.can_pin_messages:
            return True
    except Exception as e:
        logger.warning(f"Failed to check pin permission in chat {chat_id}: {e}")
    return False

def send_nonadmin_error(query, context: CallbackContext):
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Close", callback_data="close")]])
    query.edit_message_text(text="You don't have admin right to perform this action.", reply_markup=keyboard)

# ----------------------------- Command Handlers ----------------------------- #

def start(update: Update, context: CallbackContext) -> None:
    chat_id = update.effective_chat.id
    user_first = update.effective_user.first_name

    if update.effective_chat.type in ["group", "supergroup"]:
        text = (f"Hi {user_first} !!\n\nThanks for starting me !!\n"
                "Chess quizzes will now be sent to this group.\n\n"
                "To change bot settings\nJust hit /settings")
        keyboard = [
            [InlineKeyboardButton("Start Me", url="https://t.me/ThinkChessyBot")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
        config = ensure_chat_config(chat_id)
        config["active"] = True
        save_chat_config()
        schedule_quiz(context.job_queue, chat_id)
    else:
        welcome_text = (
            "♟️ Welcome to ThinkChessy Bot! 🧠\n"
            "Your ultimate Chess Quiz companion for group battles!\n\n"
            "👥 Add me to your group and I will:\n\n"
            "🔁 Drop a new chess question every 30 minutes\n\n"
            "♟️ Sharpen your skills with fun and tricky puzzles\n\n"
            "🧠 Make your group smarter, one move at a time!\n\n"
            "🏁 Ready to play? Just add me to your group now!"
        )
        keyboard = [
            [InlineKeyboardButton("➕ᴀᴅᴅ ᴍᴇ ᴛᴏ ʏᴏᴜʀ ɢʀᴏᴜᴘ➕", url="https://t.me/ThinkChessyBot?startgroup=true")],
            [InlineKeyboardButton("🔧 Support", url="https://t.me/ThinkChessySupport")],
            [InlineKeyboardButton("📝 About", callback_data="about")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.message.reply_text(welcome_text, reply_markup=reply_markup)

def settings(update: Update, context: CallbackContext) -> None:
    if update.effective_chat.type not in ["group", "supergroup"]:
        update.message.reply_text("⚠️ Oops! This command is only for groups.")
        return

    chat_id = update.effective_chat.id
    config = ensure_chat_config(chat_id)
    settings_text = (
        "🔩 Setup Zone\n\n"
        f"🌐 Language : {config.get('language', 'English')}\n"
        f"🗑️ Auto-Delete : {'ON' if config.get('auto_delete', True) else 'OFF'}\n"
        f"📌 Auto-Pin : {'ON' if config.get('auto_pin', False) else 'OFF'}\n\n"
        "Select an option:"
    )
    keyboard = [
        [InlineKeyboardButton("🌐 Language", callback_data="change_language")],
        [InlineKeyboardButton("🗑️ Auto-Delete", callback_data="toggle_autodelete")],
        [InlineKeyboardButton("📌 Auto-Pin", callback_data="toggle_autopin")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text(settings_text, reply_markup=reply_markup)

def about(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    about_text = (
        "🧠 About ThinkChessy Bot (@ThinkChessyBot)\n\n"
        "Welcome to ThinkChessy, your ultimate chess quiz companion ♟️\n"
        "We bring the world of chess to life through fun, engaging, and challenging quizzes — "
        "perfect for casual players, learners, and chess masters alike!\n\n"
        "➤ Sends automatic chess quizzes every 30 minutes in group chats\n"
        "➤ Covers everything from classic tactics to modern legends\n"
        "➤ Easy to set up with the /settings command\n\n"
        "Challenge your friends, sharpen your skills, and rule the 64 squares with brains and strategy.\n"
        "Let the game begin!"
    )
    keyboard = [
        [InlineKeyboardButton("↩️ Back", callback_data="back_from_about")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    query.edit_message_text(text=about_text, reply_markup=reply_markup)

def back_from_about(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    chat_type = update.effective_chat.type
    welcome_text = (
        "♟️ Welcome to ThinkChessy Bot! 🧠\n"
        "Your ultimate Chess Quiz companion for group battles!\n\n"
        "👥 Add me to your group and I will:\n\n"
        "🔁 Drop a new chess question every 30 minutes\n\n"
        "♟️ Sharpen your skills with fun and tricky puzzles\n\n"
        "🧠 Make your group smarter, one move at a time!\n\n"
        "🏁 Ready to play? Just add me to your group now!"
    )
    if chat_type in ["group", "supergroup"]:
        keyboard = [
            [InlineKeyboardButton("🔧 Support", url="https://t.me/ThinkChessySupport")],
            [InlineKeyboardButton("📝 About", callback_data="about")]
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("➕ᴀᴅᴅ ᴍᴇ ᴛᴏ ʏᴏᴜʀ ɢʀᴏᴜᴘ➕", url="https://t.me/ThinkChessyBot?startgroup=true")],
            [InlineKeyboardButton("🔧 Support", url="https://t.me/ThinkChessySupport")],
            [InlineKeyboardButton("📝 About", callback_data="about")]
        ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    query.edit_message_text(text=welcome_text, reply_markup=reply_markup)

# ----------------------------- Settings Callback Handlers ----------------------------- #

def change_language(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    if not is_user_admin(update, context):
        send_nonadmin_error(query, context)
        return
    query.answer()
    chat_id = update.effective_chat.id
    config = ensure_chat_config(chat_id)
    current_language = config.get("language", "English")
    text = f"🌐 Current Language: {current_language}\n\nSelect your preferred language:"
    keyboard = [
        [InlineKeyboardButton("English", callback_data="lang_English")],
        [InlineKeyboardButton("Hindi", callback_data="lang_Hindi")],
        [InlineKeyboardButton("↩️ Back", callback_data="back_to_settings")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    query.edit_message_text(text=text, reply_markup=reply_markup)

def toggle_autodelete(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    if not is_user_admin(update, context):
        send_nonadmin_error(query, context)
        return
    query.answer()
    chat_id = update.effective_chat.id
    config = ensure_chat_config(chat_id)
    current_status = config.get("auto_delete", True)
    text = (
        f"🛠️ Auto-Delete is: {'✅ ON' if current_status else '❌ OFF'}\n\n"
        "ℹ️ What it means:\n"
        "• ✅ ON: Old quiz will be auto-deleted\n"
        "• ❌ OFF: Old quiz will stay in the chat\n\n"
        "Tap below to toggle this setting 🔄"
    )
    keyboard = [
        [InlineKeyboardButton("ON", callback_data="autodelete_ON"),
         InlineKeyboardButton("OFF", callback_data="autodelete_OFF")],
        [InlineKeyboardButton("↩️ Back", callback_data="back_to_settings")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    query.edit_message_text(text=text, reply_markup=reply_markup)

def toggle_autopin(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    if not is_user_admin(update, context):
        send_nonadmin_error(query, context)
        return
    query.answer()
    chat_id = update.effective_chat.id
    config = ensure_chat_config(chat_id)
    current_status = config.get("auto_pin", False)
    text = (
        f"📌 Auto-Pin is: {'✅ ON' if current_status else '❌ OFF'}\n\n"
        "ℹ️ What it means:\n"
        "• ✅ ON: Auto-pins each quiz message.\n"
        "• ❌ OFF: Quiz messages won't be pinned.\n\n"
        "Tap below to toggle this setting 🔄"
    )
    keyboard = [
        [InlineKeyboardButton("ON", callback_data="autopin_ON"),
         InlineKeyboardButton("OFF", callback_data="autopin_OFF")],
        [InlineKeyboardButton("↩️ Back", callback_data="back_to_settings")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    query.edit_message_text(text=text, reply_markup=reply_markup)

def autopin_selection(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    if not is_user_admin(update, context):
        send_nonadmin_error(query, context)
        return
    query.answer()
    data_parts = query.data.split("_")
    if len(data_parts) < 2:
        logger.error("Invalid callback data format for auto-pin selection.")
        return
    selection = data_parts[1]
    chat_id = update.effective_chat.id
    config = ensure_chat_config(chat_id)
    if selection == "ON":
        if not has_pin_permission(chat_id, context):
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Close", callback_data="close")]])
            query.edit_message_text(
                text="To perform this action, please make me admin with pin messages permission.",
                reply_markup=keyboard
            )
            return
        new_status = True
    else:
        new_status = False
    config["auto_pin"] = new_status
    save_chat_config()
    query.edit_message_text(
        text=f"Auto-Pin set to {'ON' if new_status else 'OFF'}.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Back", callback_data="back_to_settings")]])
    )

def language_selection(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    if not is_user_admin(update, context):
        send_nonadmin_error(query, context)
        return
    query.answer()
    data_parts = query.data.split("_")
    if len(data_parts) < 2:
        logger.error("Invalid callback data format for language selection.")
        return
    lang = data_parts[1]
    chat_id = update.effective_chat.id
    config = ensure_chat_config(chat_id)
    config["language"] = lang
    save_chat_config()
    query.edit_message_text(
        text=f"Language set to {lang}.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Back", callback_data="back_to_settings")]])
    )

def autodelete_selection(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    if not is_user_admin(update, context):
        send_nonadmin_error(query, context)
        return
    query.answer()
    data_parts = query.data.split("_")
    if len(data_parts) < 2:
        logger.error("Invalid callback data format for auto-delete selection.")
        return
    setting = data_parts[1]
    new_status = True if setting == "ON" else False
    chat_id = update.effective_chat.id
    config = ensure_chat_config(chat_id)
    config["auto_delete"] = new_status
    save_chat_config()
    query.edit_message_text(
        text=f"Auto-Delete set to {'ON' if new_status else 'OFF'}.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Back", callback_data="back_to_settings")]])
    )

def back_to_settings(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    chat_id = update.effective_chat.id
    config = ensure_chat_config(chat_id)
    settings_text = (
        "🔩 Setup Zone\n\n"
        f"🌐 Language : {config.get('language', 'English')}\n"
        f"🗑️ Auto-Delete : {'ON' if config.get('auto_delete', True) else 'OFF'}\n"
        f"📌 Auto-Pin : {'ON' if config.get('auto_pin', False) else 'OFF'}\n\n"
        "Select an option:"
    )
    keyboard = [
        [InlineKeyboardButton("🌐 Language", callback_data="change_language")],
        [InlineKeyboardButton("🗑️ Auto-Delete", callback_data="toggle_autodelete")],
        [InlineKeyboardButton("📌 Auto-Pin", callback_data="toggle_autopin")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    query.edit_message_text(text=settings_text, reply_markup=reply_markup)

def close_message(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    try:
        query.message.delete()
    except Exception as e:
        logger.warning(f"Failed to delete message on close: {e}")

# ----------------------------- Quiz Scheduling and Sending ----------------------------- #

def send_quiz(context: CallbackContext) -> None:
    job = context.job
    chat_id = job.context
    config = ensure_chat_config(chat_id)

    question_data = get_valid_random_question()
    if question_data is None:
        logger.error(f"No valid questions to send in chat {chat_id}.")
        return

    question_text = question_data["question"]
    options = question_data["options"]
    safe_options = [opt if len(opt) <= 100 else opt[:100] for opt in options]
    answer_letter = question_data.get("answer", "A").upper()
    mapping = {"A": 0, "B": 1, "C": 2, "D": 3}
    correct_option_id = mapping.get(answer_letter, 0)

    if config.get("auto_delete", True) and config.get("last_quiz_id"):
        try:
            context.bot.delete_message(chat_id=chat_id, message_id=config["last_quiz_id"])
        except Exception as e:
            logger.warning(f"Failed to delete previous quiz in chat {chat_id}: {e}")

    try:
        poll = context.bot.send_poll(
            chat_id=chat_id,
            question=question_text,
            options=safe_options,
            type="quiz",
            correct_option_id=correct_option_id,
            is_anonymous=False
        )
        config["last_quiz_id"] = poll.message_id
        config["active"] = True
        save_chat_config()

        if config.get("auto_pin", False):
            try:
                context.bot.pin_chat_message(chat_id=chat_id, message_id=poll.message_id, disable_notification=True)
            except Exception as e:
                error_message = str(e)
                logger.warning(f"Failed to pin message in chat {chat_id}: {error_message}")
                if "Not enough rights" in error_message or "not enough rights" in error_message:
                    config["auto_pin"] = False
                    save_chat_config()
                    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Back", callback_data="close")]])
                    context.bot.send_message(
                        chat_id=chat_id,
                        text="Auto-Pin feature has been turned off because I do not have the required permission to pin messages.",
                        reply_markup=keyboard
                    )
    except Exception as e:
        logger.warning(f"Failed to send quiz in chat {chat_id}: {e}")
        config["active"] = False
        save_chat_config()
        return

def schedule_quiz(job_queue, chat_id: int) -> None:
    current_jobs = job_queue.get_jobs_by_name(str(chat_id))
    for job in current_jobs:
        job.schedule_removal()
    job_queue.run_repeating(send_quiz, interval=1800, first=0, context=chat_id, name=str(chat_id))
    logger.info(f"Scheduled quiz for chat {chat_id}.")

def new_chat_member(update: Update, context: CallbackContext) -> None:
    for member in update.message.new_chat_members:
        if member.username == "ThinkChessyBot":
            chat_id = update.effective_chat.id
            ensure_chat_config(chat_id)
            update.message.reply_text(
                "Hi everyone! I'm ThinkChessyBot. I will now start sending chess quizzes every 30 minutes.\n"
                "Use /settings to customize the settings."
            )
            schedule_quiz(context.job_queue, chat_id)

# ----------------------------- Error Handler ----------------------------- #

def error_handler(update: object, context: CallbackContext) -> None:
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

# ----------------------------- Bot Start ----------------------------- #

def main() -> None:
    load_chat_config()
    TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not TOKEN:
        logger.error("Bot token not found! Please set the TELEGRAM_BOT_TOKEN environment variable.")
        return

    updater = Updater(TOKEN, use_context=True)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("settings", settings))
    dispatcher.add_handler(CallbackQueryHandler(about, pattern="^about$"))
    dispatcher.add_handler(CallbackQueryHandler(back_from_about, pattern="^back_from_about$"))
    dispatcher.add_handler(CallbackQueryHandler(change_language, pattern="^change_language$"))
    dispatcher.add_handler(CallbackQueryHandler(toggle_autodelete, pattern="^toggle_autodelete$"))
    dispatcher.add_handler(CallbackQueryHandler(toggle_autopin, pattern="^toggle_autopin$"))
    dispatcher.add_handler(CallbackQueryHandler(back_to_settings, pattern="^back_to_settings$"))
    dispatcher.add_handler(CallbackQueryHandler(language_selection, pattern="^lang_"))
    dispatcher.add_handler(CallbackQueryHandler(autodelete_selection, pattern="^autodelete_"))
    dispatcher.add_handler(CallbackQueryHandler(autopin_selection, pattern="^autopin_"))
    dispatcher.add_handler(CallbackQueryHandler(close_message, pattern="^close$"))
    dispatcher.add_handler(MessageHandler(Filters.status_update.new_chat_members, new_chat_member))

    dispatcher.add_error_handler(error_handler)

    updater.start_polling()
    logger.info("Bot started polling.")

    for chat_id in chat_config.keys():
        try:
            schedule_quiz(updater.job_queue, int(chat_id))
        except Exception as e:
            logger.warning(f"Failed to schedule quiz for chat {chat_id}: {e}")

    updater.idle()

if __name__ == '__main__':
    # Start the Telegram bot in a separate thread
    bot_thread = Thread(target=main)
    bot_thread.start()

    # ----------------------------- Flask Web Server to Keep the App Alive ----------------------------- #
    app = Flask('')

    @app.route('/')
    def home():
        return "Bot is running!"

    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
