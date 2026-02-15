"""
telegram_bot.py - Kalshi Markets Telegram Bot

A Telegram bot that provides Kalshi prediction market data in group chats.
Shows top 5 events in Politics and Economics by 24h volume or biggest movers.

Usage:
    1. Get a bot token from @BotFather on Telegram
    2. Set the TELEGRAM_BOT_TOKEN environment variable
    3. Run: python telegram_bot.py
    4. Add the bot to your group chat
    5. Use /topvolume or /topmovers commands
"""

import os
import json
import asyncio
from datetime import datetime, time, timezone, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from kalshi_client import get_client, EventData, MarketOption


# =============================================================================
# TIMEZONE CONFIGURATION
# =============================================================================

# Singapore Time (UTC+8)
SGT = timezone(timedelta(hours=8))


# =============================================================================
# SUBSCRIPTION STORAGE
# =============================================================================

# File to persist subscribed chat data (survives bot restarts)
# Format: {chat_id: {"hour": 16}, ...}
SUBSCRIPTIONS_FILE = os.path.join(os.path.dirname(__file__), "subscribed_chats.json")

# Default update hour for new subscriptions (8:00 AM SGT)
DEFAULT_UPDATE_HOUR = 8

def load_subscriptions() -> dict:
    """Load subscribed chat data from file."""
    if os.path.exists(SUBSCRIPTIONS_FILE):
        try:
            with open(SUBSCRIPTIONS_FILE, "r") as f:
                data = json.load(f)
                # Migration: convert old format (list of chat_ids) to new format (dict with hour)
                if isinstance(data, list):
                    return {str(chat_id): {"hour": DEFAULT_UPDATE_HOUR} for chat_id in data}
                # Ensure all keys are strings (JSON converts int keys to strings)
                return {str(k): v for k, v in data.items()}
        except (json.JSONDecodeError, IOError):
            return {}
    return {}

def save_subscriptions(chat_data: dict):
    """Save subscribed chat data to file."""
    with open(SUBSCRIPTIONS_FILE, "w") as f:
        json.dump(chat_data, f, indent=2)

def get_chat_ids() -> set:
    """Get set of all subscribed chat IDs."""
    return set(int(chat_id) for chat_id in subscribed_chats.keys())

def get_chats_for_hour(hour: int) -> list:
    """Get list of chat IDs that should receive updates at the given hour."""
    return [int(chat_id) for chat_id, data in subscribed_chats.items() if data.get("hour") == hour]

def format_hour_display(hour: int) -> str:
    """Format hour as 12-hour time string (e.g., '4:00 PM')."""
    if hour == 0:
        return "12:00 AM"
    elif hour < 12:
        return f"{hour}:00 AM"
    elif hour == 12:
        return "12:00 PM"
    else:
        return f"{hour - 12}:00 PM"

# Global dict of subscribed chats {chat_id_str: {"hour": int}}
subscribed_chats = load_subscriptions()


# =============================================================================
# CONFIGURATION
# =============================================================================

# Bot token from @BotFather - set via environment variable for security
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")

# Categories to display
CATEGORIES = ["Politics", "Economics"]

# Number of events to show per category
TOP_N = 5

# Number of options to show per event
MAX_OPTIONS_PER_EVENT = 4


# =============================================================================
# MESSAGE FORMATTING
# =============================================================================

def format_event_message(events: list[EventData], category: str, sort_type: str) -> str:
    """
    Format events into a readable Telegram message.
    
    Args:
        events: List of EventData objects
        category: Category name (Politics/Economics)
        sort_type: "volume" or "price_change"
        
    Returns:
        Formatted message string with Markdown
    """
    emoji = "🏛️" if category == "Politics" else "💰"
    sort_label = "24h Volume" if sort_type == "volume" else "24h Movers"
    
    lines = [f"{emoji} *Top {len(events)} {category}* \\(by {sort_label}\\)\n"]
    
    if not events:
        lines.append("_No events found\\._")
        return "\n".join(lines)
    
    for i, event in enumerate(events, 1):
        # Event title
        # Escape special markdown characters in title
        title = escape_markdown(event.title)
        lines.append(f"*{i}\\. {title}*")
        
        # Show top options for each event
        for option in event.options[:MAX_OPTIONS_PER_EVENT]:
            option_name = escape_markdown(option.name)
            
            if sort_type == "price_change" and option.price_change_24h != 0:
                change_sign = "\\+" if option.price_change_24h > 0 else "\\-"
                # Use abs() since we already have the sign prefix
                change_str = f"{change_sign}{abs(option.price_change_24h)}%"
                lines.append(f"  • {option_name}: {option.probability}% \\({change_str}\\)")
            else:
                lines.append(f"  • {option_name}: {option.probability}%")
        
        # Show if there are more options
        remaining = len(event.options) - MAX_OPTIONS_PER_EVENT
        if remaining > 0:
            lines.append(f"  _\\.\\.\\.and {remaining} more options_")
        
        # Volume info
        lines.append(f"  📊 Vol: {event.total_volume:,}\n")
    
    return "\n".join(lines)


def escape_markdown(text: str) -> str:
    """
    Escape special Markdown characters for Telegram.
    
    Args:
        text: Raw text string
        
    Returns:
        Escaped text safe for Markdown parsing
    """
    # Characters that need escaping in Telegram Markdown
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    
    return text


def format_full_update(politics: list[EventData], economics: list[EventData], sort_type: str) -> str:
    """
    Format a complete market update message.
    
    Args:
        politics: Politics events
        economics: Economics events
        sort_type: "volume" or "price_change"
        
    Returns:
        Complete formatted message
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    # Escape special characters in timestamp (hyphens and colons)
    escaped_timestamp = escape_markdown(timestamp)
    sort_label = "24h Volume" if sort_type == "volume" else "Biggest Movers"
    
    header = f"📊 *Kalshi Markets Update*\n_{escaped_timestamp}_ \\| Sorted by {sort_label}\n\n"
    
    politics_section = format_event_message(politics, "Politics", sort_type)
    economics_section = format_event_message(economics, "Economics", sort_type)
    
    return header + politics_section + "\n" + economics_section


# =============================================================================
# COMMAND HANDLERS
# =============================================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler for /start and /help commands.
    Shows available commands and usage info.
    """
    help_text = """🎯 *Kalshi Markets Bot*

Get real\\-time prediction market data from Kalshi\\.

*Commands:*
/topvolume \\- Top 5 Politics & Economics by 24h volume
/topmovers \\- Top 5 biggest price movers in 24h
/politics \\- Top 5 Politics markets only
/economics \\- Top 5 Economics markets only

*Daily Updates:*
/subscribe \\- Get daily updates \\(default: 8:00 AM SGT\\)
/settime \\- Choose your preferred update time
/unsubscribe \\- Stop daily updates
/status \\- Check subscription status

/help \\- Show this message
"""
    await update.message.reply_text(help_text, parse_mode="MarkdownV2")


async def top_volume_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler for /topvolume command.
    Shows top 5 events by 24h volume for Politics and Economics.
    """
    loading_msg = await update.message.reply_text("📊 Fetching top markets by volume...")
    
    try:
        client = get_client()
        
        # Fetch data for both categories
        politics = client.get_top_events_by_category("Politics", top_n=TOP_N, sort_by="volume")
        economics = client.get_top_events_by_category("Economics", top_n=TOP_N, sort_by="volume")
        
        # Delete loading message
        await loading_msg.delete()
        
        # Send formatted messages
        politics_msg = format_event_message(politics, "Politics", "volume")
        economics_msg = format_event_message(economics, "Economics", "volume")
        
        await update.message.reply_text(politics_msg, parse_mode="MarkdownV2")
        await update.message.reply_text(economics_msg, parse_mode="MarkdownV2")
        
    except Exception as e:
        await loading_msg.edit_text(f"❌ Error fetching data: {str(e)}")


async def top_movers_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler for /topmovers command.
    Shows top 5 events by biggest 24h price changes for Politics and Economics.
    Note: This is slower due to additional API calls for price history.
    """
    loading_msg = await update.message.reply_text(
        "📈 Fetching biggest movers (this takes a moment due to price history lookups)..."
    )
    
    try:
        client = get_client()
        
        # Fetch data - price_change sort is slower due to extra API calls
        politics = client.get_top_events_by_category("Politics", top_n=TOP_N, sort_by="price_change")
        economics = client.get_top_events_by_category("Economics", top_n=TOP_N, sort_by="price_change")
        
        # Delete loading message
        await loading_msg.delete()
        
        # Send formatted messages
        politics_msg = format_event_message(politics, "Politics", "price_change")
        economics_msg = format_event_message(economics, "Economics", "price_change")
        
        await update.message.reply_text(politics_msg, parse_mode="MarkdownV2")
        await update.message.reply_text(economics_msg, parse_mode="MarkdownV2")
        
    except Exception as e:
        await loading_msg.edit_text(f"❌ Error fetching data: {str(e)}")


async def politics_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler for /politics command.
    Shows top 5 Politics events by 24h volume.
    """
    loading_msg = await update.message.reply_text("🏛️ Fetching Politics markets...")
    
    try:
        client = get_client()
        politics = client.get_top_events_by_category("Politics", top_n=TOP_N, sort_by="volume")
        
        await loading_msg.delete()
        
        politics_msg = format_event_message(politics, "Politics", "volume")
        await update.message.reply_text(politics_msg, parse_mode="MarkdownV2")
        
    except Exception as e:
        await loading_msg.edit_text(f"❌ Error fetching data: {str(e)}")


async def economics_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler for /economics command.
    Shows top 5 Economics events by 24h volume.
    """
    loading_msg = await update.message.reply_text("💰 Fetching Economics markets...")
    
    try:
        client = get_client()
        economics = client.get_top_events_by_category("Economics", top_n=TOP_N, sort_by="volume")
        
        await loading_msg.delete()
        
        economics_msg = format_event_message(economics, "Economics", "volume")
        await update.message.reply_text(economics_msg, parse_mode="MarkdownV2")
        
    except Exception as e:
        await loading_msg.edit_text(f"❌ Error fetching data: {str(e)}")


# =============================================================================
# SUBSCRIPTION COMMANDS
# =============================================================================

async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler for /subscribe command.
    Subscribes the current chat to daily market updates.
    """
    chat_id = update.effective_chat.id
    chat_id_str = str(chat_id)
    chat_title = update.effective_chat.title or "this chat"
    
    if chat_id_str in subscribed_chats:
        current_hour = subscribed_chats[chat_id_str].get("hour", DEFAULT_UPDATE_HOUR)
        time_display = escape_markdown(format_hour_display(current_hour))
        await update.message.reply_text(
            f"ℹ️ {escape_markdown(chat_title)} is already subscribed to daily updates\\!\n"
            f"Updates are sent at *{time_display} SGT*\\.\n\n"
            f"Use /settime to change the update time\\.",
            parse_mode="MarkdownV2"
        )
        return
    
    subscribed_chats[chat_id_str] = {"hour": DEFAULT_UPDATE_HOUR}
    save_subscriptions(subscribed_chats)
    
    time_display = escape_markdown(format_hour_display(DEFAULT_UPDATE_HOUR))
    await update.message.reply_text(
        f"✅ *Subscribed\\!*\n\n"
        f"📍 Chat: {escape_markdown(chat_title)}\n"
        f"🆔 Chat ID: `{chat_id}`\n"
        f"⏰ Daily updates at: *{time_display} SGT*\n\n"
        f"You'll receive the top 5 markets by 24h volume in Politics & Economics\\.\n"
        f"Use /settime to change the update time\\.\n"
        f"Use /unsubscribe to stop\\.",
        parse_mode="MarkdownV2"
    )


async def unsubscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler for /unsubscribe command.
    Unsubscribes the current chat from daily updates.
    """
    chat_id = update.effective_chat.id
    chat_id_str = str(chat_id)
    
    if chat_id_str not in subscribed_chats:
        await update.message.reply_text("ℹ️ This chat is not subscribed to daily updates\\.", parse_mode="MarkdownV2")
        return
    
    del subscribed_chats[chat_id_str]
    save_subscriptions(subscribed_chats)
    
    await update.message.reply_text("✅ Unsubscribed from daily updates\\.", parse_mode="MarkdownV2")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler for /status command.
    Shows subscription status and chat info.
    """
    chat_id = update.effective_chat.id
    chat_id_str = str(chat_id)
    chat_type = update.effective_chat.type
    chat_title = update.effective_chat.title or "Private Chat"
    is_subscribed = chat_id_str in subscribed_chats
    
    status_emoji = "✅" if is_subscribed else "❌"
    status_text = "Subscribed" if is_subscribed else "Not subscribed"
    
    if is_subscribed:
        current_hour = subscribed_chats[chat_id_str].get("hour", DEFAULT_UPDATE_HOUR)
        time_display = escape_markdown(format_hour_display(current_hour))
        time_line = f"⏰ Update time: *{time_display} SGT*\n"
        footer = "_Use /settime to change update time_"
    else:
        time_line = ""
        footer = "_Use /subscribe to get daily updates_"
    
    await update.message.reply_text(
        f"📊 *Chat Status*\n\n"
        f"📍 Chat: {escape_markdown(chat_title)}\n"
        f"🆔 Chat ID: `{chat_id}`\n"
        f"📝 Type: {chat_type}\n"
        f"{status_emoji} Status: {status_text}\n"
        f"{time_line}\n"
        f"{footer}",
        parse_mode="MarkdownV2"
    )


async def settime_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler for /settime command.
    Shows an inline keyboard for users to select their preferred update time.
    """
    chat_id = update.effective_chat.id
    chat_id_str = str(chat_id)
    
    if chat_id_str not in subscribed_chats:
        await update.message.reply_text(
            "⚠️ You need to subscribe first\\!\n"
            "Use /subscribe to enable daily updates, then /settime to choose your preferred time\\.",
            parse_mode="MarkdownV2"
        )
        return
    
    # Create inline keyboard with 24 hour options (4 columns x 6 rows)
    keyboard = []
    for row in range(6):  # 6 rows
        row_buttons = []
        for col in range(4):  # 4 columns
            hour = row * 4 + col  # 0-23
            label = format_hour_display(hour)
            row_buttons.append(InlineKeyboardButton(label, callback_data=f"settime_{hour}"))
        keyboard.append(row_buttons)
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    current_hour = subscribed_chats[chat_id_str].get("hour", DEFAULT_UPDATE_HOUR)
    current_time = escape_markdown(format_hour_display(current_hour))
    
    await update.message.reply_text(
        f"⏰ *Choose Your Daily Update Time*\n\n"
        f"Current time: *{current_time} SGT*\n\n"
        f"Select a new time below:",
        reply_markup=reply_markup,
        parse_mode="MarkdownV2"
    )


async def settime_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler for settime inline keyboard button presses.
    Updates the user's preferred update time.
    """
    query = update.callback_query
    await query.answer()  # Acknowledge the button press
    
    chat_id = update.effective_chat.id
    chat_id_str = str(chat_id)
    
    # Parse the hour from callback data (format: "settime_HH")
    try:
        hour = int(query.data.split("_")[1])
        if hour < 0 or hour > 23:
            raise ValueError("Invalid hour")
    except (IndexError, ValueError):
        await query.edit_message_text("❌ Invalid selection. Please try /settime again.")
        return
    
    if chat_id_str not in subscribed_chats:
        await query.edit_message_text(
            "⚠️ You're no longer subscribed. Use /subscribe first.",
        )
        return
    
    # Update the hour
    subscribed_chats[chat_id_str]["hour"] = hour
    save_subscriptions(subscribed_chats)
    
    time_display = format_hour_display(hour)
    
    await query.edit_message_text(
        f"✅ *Update Time Changed\\!*\n\n"
        f"⏰ New time: *{escape_markdown(time_display)} SGT*\n\n"
        f"You'll receive daily market updates at this time\\.",
        parse_mode="MarkdownV2"
    )


# =============================================================================
# SCHEDULED DAILY UPDATE
# =============================================================================

async def send_hourly_update(context: ContextTypes.DEFAULT_TYPE):
    """
    Scheduled job that runs every hour and sends updates to chats
    that have selected this hour for their daily update.
    """
    current_hour = datetime.now(SGT).hour
    
    # Get chats that should receive updates at this hour
    chats_to_update = get_chats_for_hour(current_hour)
    
    if not chats_to_update:
        print(f"[{datetime.now(SGT)}] No chats scheduled for {format_hour_display(current_hour)} SGT update.")
        return
    
    print(f"[{datetime.now(SGT)}] Sending {format_hour_display(current_hour)} SGT update to {len(chats_to_update)} chat(s)...")
    
    try:
        client = get_client()
        
        # Fetch top markets by 24h volume
        politics = client.get_top_events_by_category("Politics", top_n=TOP_N, sort_by="volume")
        economics = client.get_top_events_by_category("Economics", top_n=TOP_N, sort_by="volume")
        
        # Format the message
        message = format_full_update(politics, economics, "volume")
        header = "📊 *Daily Market Update*\n\n"
        full_message = header + message
        
        # Send to chats scheduled for this hour
        failed_chats = []
        for chat_id in chats_to_update:
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=full_message,
                    parse_mode="MarkdownV2"
                )
                print(f"  ✓ Sent to chat {chat_id}")
            except Exception as e:
                print(f"  ✗ Failed to send to chat {chat_id}: {e}")
                failed_chats.append(chat_id)
        
        # Optionally remove chats that consistently fail (e.g., bot was removed)
        # For now, just log them
        if failed_chats:
            print(f"[{datetime.now(SGT)}] Failed to send to {len(failed_chats)} chat(s): {failed_chats}")
        
        print(f"[{datetime.now(SGT)}] Hourly update complete.")
        
    except Exception as e:
        print(f"[{datetime.now(SGT)}] Error in hourly update: {e}")


# =============================================================================
# MAIN APPLICATION
# =============================================================================

def main():
    """
    Initialize and run the Telegram bot.
    """
    # Validate bot token
    if not BOT_TOKEN:
        print("=" * 60)
        print("ERROR: TELEGRAM_BOT_TOKEN environment variable not set!")
        print()
        print("To get a bot token:")
        print("  1. Open Telegram and search for @BotFather")
        print("  2. Send /newbot and follow the prompts")
        print("  3. Copy the token BotFather gives you")
        print()
        print("Then set the environment variable:")
        print("  export TELEGRAM_BOT_TOKEN='your_token_here'")
        print()
        print("Or run directly:")
        print("  TELEGRAM_BOT_TOKEN='your_token' python telegram_bot.py")
        print("=" * 60)
        return
    
    # Build the application
    print("🚀 Starting Kalshi Markets Telegram Bot...")
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Register command handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", start_command))
    app.add_handler(CommandHandler("topvolume", top_volume_command))
    app.add_handler(CommandHandler("topmovers", top_movers_command))
    app.add_handler(CommandHandler("politics", politics_command))
    app.add_handler(CommandHandler("economics", economics_command))
    
    # Subscription commands
    app.add_handler(CommandHandler("subscribe", subscribe_command))
    app.add_handler(CommandHandler("unsubscribe", unsubscribe_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("settime", settime_command))
    
    # Callback handler for settime inline keyboard
    app.add_handler(CallbackQueryHandler(settime_callback, pattern="^settime_"))
    
    # Schedule hourly job to check and send updates
    # Runs at the start of every hour (XX:00:00 SGT)
    job_queue = app.job_queue
    
    # Calculate time until next hour
    now = datetime.now(SGT)
    next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    seconds_until_next_hour = (next_hour - now).total_seconds()
    
    job_queue.run_repeating(
        send_hourly_update,
        interval=3600,  # Every hour (3600 seconds)
        first=seconds_until_next_hour,  # Start at the next hour mark
        name="hourly_market_update"
    )
    
    print("✅ Bot is running! Press Ctrl+C to stop.")
    print()
    print("Available commands:")
    print("  /topvolume   - Top 5 Politics & Economics by 24h volume")
    print("  /topmovers   - Top 5 biggest price movers in 24h")
    print("  /politics    - Top 5 Politics markets only")
    print("  /economics   - Top 5 Economics markets only")
    print("  /subscribe   - Subscribe to daily updates")
    print("  /settime     - Choose preferred update time (12 AM - 11 PM)")
    print("  /unsubscribe - Unsubscribe from daily updates")
    print("  /status      - Check subscription status")
    print("  /help        - Show help message")
    print()
    print(f"📅 Hourly job scheduled (checks each hour for chats to update)")
    print(f"📋 Currently {len(subscribed_chats)} chat(s) subscribed")
    if subscribed_chats:
        # Show breakdown by hour
        hours_breakdown = {}
        for chat_id, data in subscribed_chats.items():
            hour = data.get("hour", DEFAULT_UPDATE_HOUR)
            hours_breakdown[hour] = hours_breakdown.get(hour, 0) + 1
        for hour in sorted(hours_breakdown.keys()):
            print(f"   - {format_hour_display(hour)} SGT: {hours_breakdown[hour]} chat(s)")
    print()
    
    # Start polling for updates
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
