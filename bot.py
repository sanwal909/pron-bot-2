import telebot
from telebot import types
import qrcode
import time
import threading
from datetime import datetime, timedelta
import logging
from io import BytesIO
import json
import os
import sys
import requests

# Import config and verification
from config import *
from verif import init_verification

# Debug token loading
print("=" * 60)
print("🔍 DEBUGGING TOKEN LOADING")
print("=" * 60)
print(f"BOT_TOKEN from env: {'✅ FOUND' if BOT_TOKEN else '❌ NOT FOUND'}")
if BOT_TOKEN:
    print(f"Token starts with: {BOT_TOKEN[:10]}...")
    try:
        test_url = f"https://api.telegram.org/bot{BOT_TOKEN}/getMe"
        response = requests.get(test_url, timeout=10)
        if response.status_code == 200:
            bot_info = response.json()
            print(f"✅ Token VALID! Bot: @{bot_info['result']['username']}")
        else:
            print(f"❌ Token INVALID!")
    except Exception as e:
        print(f"❌ Error testing token: {e}")
print("=" * 60)

# Initialize bot
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# Initialize verification system
verif = init_verification(bot)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Auto-save thread
def auto_save_data():
    while True:
        time.sleep(30)
        save_all_data()

auto_save_thread = threading.Thread(target=auto_save_data, daemon=True)
auto_save_thread.start()

# ============ SPAM PROTECTION FUNCTIONS ============
def update_user_activity(user_id):
    user_id_str = str(user_id)
    current_time = time.time()
    
    if user_id_str not in spam_data:
        spam_data[user_id_str] = {
            "requests": [],
            "warnings": 0,
            "blocked_until": 0,
            "block_level": 0,
            "ban_reason": "",
            "banned_by": 0
        }
    
    if "requests" not in spam_data[user_id_str]:
        spam_data[user_id_str]["requests"] = []
    
    spam_data[user_id_str]["requests"] = [
        ts for ts in spam_data[user_id_str]["requests"] 
        if current_time - ts < SPAM_TIME_WINDOW
    ]
    
    spam_data[user_id_str]["requests"].append(current_time)
    return len(spam_data[user_id_str]["requests"])

def check_user_blocked(user_id):
    user_id_str = str(user_id)
    
    if user_id_str not in spam_data:
        return False, None
    
    user_data = spam_data[user_id_str]
    
    if "blocked_until" not in user_data:
        user_data["blocked_until"] = 0
    
    current_time = time.time()
    
    if user_data["blocked_until"] > current_time:
        time_left = int(user_data["blocked_until"] - current_time)
        minutes = time_left // 60
        seconds = time_left % 60
        hours = minutes // 60
        minutes = minutes % 60
        
        warning_msg = f"⛔ <b>YOU ARE BLOCKED!</b>\n\n"
        
        if user_data.get("ban_reason"):
            warning_msg += f"<b>Reason:</b> {user_data['ban_reason']}\n"
        
        if hours > 0:
            warning_msg += f"⏳ Please wait <b>{hours} hours {minutes} minutes</b>\n\n"
        else:
            warning_msg += f"⏳ Please wait <b>{minutes}:{seconds:02d}</b>\n\n"
        
        return True, warning_msg
    
    return False, None

def check_spam(user_id):
    user_id_str = str(user_id)
    
    is_blocked, block_msg = check_user_blocked(user_id)
    if is_blocked:
        return block_msg
    
    current_time = time.time()
    request_count = update_user_activity(user_id)
    
    if "warnings" not in spam_data[user_id_str]:
        spam_data[user_id_str]["warnings"] = 0
    if "block_level" not in spam_data[user_id_str]:
        spam_data[user_id_str]["block_level"] = 0
    if "blocked_until" not in spam_data[user_id_str]:
        spam_data[user_id_str]["blocked_until"] = 0
    
    if request_count >= MAX_SPAM_COUNT:
        user_data = spam_data[user_id_str]
        user_data["block_level"] = min(2, user_data.get("block_level", 0) + 1)
        block_duration = BLOCK_DURATIONS[user_data["block_level"]]
        user_data["blocked_until"] = current_time + block_duration
        user_data["requests"] = []
        user_data["warnings"] = 0
        
        # Notify admin
        try:
            admin_msg = f"""
🚨 <b>USER BLOCKED FOR SPAM</b>

👤 User ID: <code>{user_id}</code>
📛 Block Level: {user_data['block_level'] + 1}
⏰ Duration: {block_duration//60} minutes
🔢 Spam Count: {request_count}
            """
            bot.send_message(ADMIN_ID, admin_msg, parse_mode="HTML")
        except:
            pass
        
        minutes = block_duration // 60
        seconds = block_duration % 60
        
        return f"⛔ <b>BLOCKED FOR SPAM!</b>\n\n⏳ Wait {minutes}:{seconds:02d}"
    
    if request_count >= 3:
        warning_level = min(2, request_count - 3)
        if spam_data[user_id_str].get("warnings", 0) < warning_level + 1:
            spam_data[user_id_str]["warnings"] = warning_level + 1
            warning_msg = f"{WARNING_MESSAGES[warning_level]}\n\n⚠️ {MAX_SPAM_COUNT - request_count} attempts left!"
            try:
                bot.send_message(user_id, warning_msg, parse_mode="HTML")
            except:
                pass
    
    return None

def reset_spam_counter(user_id):
    user_id_str = str(user_id)
    if user_id_str in spam_data:
        if spam_data[user_id_str].get("blocked_until", 0) < time.time():
            spam_data[user_id_str]["requests"] = []
            spam_data[user_id_str]["warnings"] = 0

def ban_user(user_id, duration_seconds, reason="", banned_by=ADMIN_ID):
    user_id_str = str(user_id)
    current_time = time.time()
    
    if user_id_str not in spam_data:
        spam_data[user_id_str] = {
            "requests": [],
            "warnings": 0,
            "blocked_until": 0,
            "block_level": 0,
            "ban_reason": reason,
            "banned_by": banned_by
        }
    
    spam_data[user_id_str]["blocked_until"] = current_time + duration_seconds
    spam_data[user_id_str]["ban_reason"] = reason
    spam_data[user_id_str]["banned_by"] = banned_by
    spam_data[user_id_str]["block_level"] = 3
    
    try:
        if duration_seconds >= 3600:
            time_display = f"{int(duration_seconds/3600)} hours"
        elif duration_seconds >= 60:
            time_display = f"{int(duration_seconds/60)} minutes"
        else:
            time_display = f"{duration_seconds} seconds"
        
        bot.send_message(
            int(user_id),
            f"⛔ <b>BANNED</b>\n\nDuration: {time_display}\nReason: {reason}",
            parse_mode="HTML"
        )
    except:
        pass
    
    return True

# ============ PREMIUM BOT CLASS ============
class PremiumBot:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def generate_qr_code(self, upi_id, amount, name):
        try:
            upi_url = f"upi://pay?pa={upi_id}&pn={name}&am={amount}&cu=INR"
            qr = qrcode.QRCode(version=1, box_size=10, border=4)
            qr.add_data(upi_url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            img_bytes = BytesIO()
            img.save(img_bytes, format='PNG')
            img_bytes.seek(0)
            return img_bytes
        except Exception as e:
            self.logger.error(f"QR Error: {e}")
            return None

premium_bot = PremiumBot()

# ========== IMPORTANT LOGS ==========
def log_important_event(event_type, user_data=None, plan=None):
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if event_type == "new_user":
            log_msg = f"""
🆕 <b>NEW USER</b>
👤 Name: {user_data.get('first_name', 'N/A')}
👤 User: @{user_data.get('username' , 'N/A')}
🆔 ID: <code>{user_data.get('id', 'N/A')}</code>
⏰ Time: {timestamp}
📊 Total Users: {len(users_data)}
            """
        elif event_type == "payment_initiated":
            log_msg = f"""
💰 <b>PAYMENT INITIATED</b>
👤 Name: {user_data.get('first_name', 'N/A')}
👤 User: @{user_data.get('username', 'N/A')}
🆔 ID: <code>{user_data.get('id', 'N/A')}</code>
📅 Plan: {plan}
⏰ Time: {timestamp}
            """
        else:
            return
        
        bot.send_message(settings['log_channel'], log_msg, parse_mode="HTML")
    except Exception as e:
        logging.error(f"Log error: {e}")

# ========== /START COMMAND ==========
@bot.message_handler(commands=['start'])
def handle_start(message):
    try:
        user_id = message.from_user.id
        
        spam_result = check_spam(user_id)
        if spam_result:
            bot.send_message(message.chat.id, spam_result, parse_mode="HTML")
            return
        
        is_new_user = str(user_id) not in users_data
        
        users_data[str(user_id)] = {
            'id': user_id,
            'username': message.from_user.username,
            'first_name': message.from_user.first_name,
            'last_name': message.from_user.last_name or "",
            'start_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'is_premium': False
        }
        
        reset_spam_counter(user_id)
        
        if is_new_user:
            log_important_event("new_user", users_data[str(user_id)])
        
        # Check if custom start message exists
        if start_message_data and 'has_media' in start_message_data:
            text = start_message_data.get('text', "")
            
            if start_message_data['has_media']:
                media_type = start_message_data.get('media_type', '')
                file_id = start_message_data.get('file_id', '')
                
                if media_type == 'photo' and file_id:
                    bot.send_photo(
                        message.chat.id,
                        photo=file_id,
                        caption=text,
                        reply_markup=verif.main_menu_keyboard(),
                        parse_mode="HTML"
                    )
                elif media_type == 'video' and file_id:
                    bot.send_video(
                        message.chat.id,
                        video=file_id,
                        caption=text,
                        reply_markup=verif.main_menu_keyboard(),
                        parse_mode="HTML"
                    )
                else:
                    send_default_start(message)
            else:
                bot.send_message(
                    message.chat.id,
                    text,
                    reply_markup=verif.main_menu_keyboard(),
                    parse_mode="HTML"
                )
        else:
            send_default_start(message)
        
    except Exception as e:
        logging.error(f"Start error: {e}")

def send_default_start(message):
    welcome_text = f"""
<b>🔥 PREMIUM CONTENT 🔥</b>

<b>Membership Plans:</b>
📅 {PLANS['monthly']['name']} - ₹{PLANS['monthly']['amount']}
♾️ {PLANS['lifetime']['name']} - ₹{PLANS['lifetime']['amount']}

<b>Features:</b>
• 55k+ Premium Videos
• Lifetime Access (Lifetime plan)
• Fast Support
• Daily Updates

<b>👇 Choose your plan:</b>
    """
    
    bot.send_message(
        message.chat.id,
        welcome_text,
        reply_markup=verif.plan_selection_keyboard(),
        parse_mode="HTML"
    )

# ========== PLAN SELECTION ==========
@bot.callback_query_handler(func=lambda call: call.data.startswith('plan_'))
def handle_plan_selection(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    
    spam_result = check_spam(user_id)
    if spam_result:
        bot.send_message(chat_id, spam_result, parse_mode="HTML")
        bot.answer_callback_query(call.id)
        return
    
    reset_spam_counter(user_id)
    
    plan_type = call.data.split('_')[1]  # monthly or lifetime
    plan = PLANS[plan_type]
    
    # Store in pending verifications
    pending_verifications[str(user_id)] = {
        'plan': plan_type,
        'amount': plan['amount'],
        'initiated_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'username': call.from_user.username,
        'first_name': call.from_user.first_name
    }
    save_json_file(PENDING_VERIF_FILE, pending_verifications)
    
    # Log payment initiation
    if str(user_id) in users_data:
        log_important_event("payment_initiated", users_data[str(user_id)], plan['name'])
    
    # Delete previous message
    try:
        bot.delete_message(chat_id, call.message.message_id)
    except:
        pass
    
    # Generate QR code
    qr_image = premium_bot.generate_qr_code(settings['upi_id'], plan['amount'], settings['upi_name'])
    
    if qr_image:
        caption = f"""
<b>💰 PAY ₹{plan['amount']} FOR {plan['name'].upper()}</b>

<b>UPI Details:</b>
└ ID: <code>{settings['upi_id']}</code>
└ Name: {settings['upi_name']}
└ Amount: <b>₹{plan['amount']}</b>

<b>Instructions:</b>
1. Scan QR with any UPI app
2. Pay ₹{plan['amount']}
3. Click "✅ Payment Done" below
        """
        
        keyboard = types.InlineKeyboardMarkup(row_width=1)
        btn1 = types.InlineKeyboardButton("✅ Payment Done", callback_data="payment_done")
        btn2 = types.InlineKeyboardButton("📞 Support", url=f"https://t.me/{settings['support_username']}")
        keyboard.add(btn1, btn2)
        
        bot.send_photo(
            chat_id,
            photo=qr_image,
            caption=caption,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    else:
        manual_text = f"""
<b>💰 PAY ₹{plan['amount']} FOR {plan['name'].upper()}</b>

<b>UPI ID:</b> <code>{settings['upi_id']}</code>
<b>Amount:</b> ₹{plan['amount']}

<b>Steps:</b>
1. Send ₹{plan['amount']} to above UPI ID
2. Click "✅ Payment Done" below
        """
        
        keyboard = types.InlineKeyboardMarkup(row_width=1)
        btn1 = types.InlineKeyboardButton("✅ Payment Done", callback_data="payment_done")
        btn2 = types.InlineKeyboardButton("📞 Support", url=f"https://t.me/{settings['support_username']}")
        keyboard.add(btn1, btn2)
        
        bot.send_message(
            chat_id,
            manual_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    
    bot.answer_callback_query(call.id)

# ========== HOW TO GET ==========
@bot.callback_query_handler(func=lambda call: call.data == "how_to_get")
def handle_how_to_get(call):
    user_id = call.from_user.id
    
    spam_result = check_spam(user_id)
    if spam_result:
        bot.send_message(call.message.chat.id, spam_result, parse_mode="HTML")
        bot.answer_callback_query(call.id)
        return
    
    reset_spam_counter(user_id)
    
    instructions = f"""
<b>❓ HOW TO GET PREMIUM:</b>

1. Click "Get Premium" button
2. Choose your plan (Monthly/Lifetime)
3. Scan QR code and pay exact amount
4. Click "Payment Done" button
5. Send payment screenshot
6. Admin verifies within few minutes
7. Get unique join link after verification

<b>Support:</b> @{settings['support_username']}
    """
    
    try:
        bot.edit_message_text(
            instructions,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=verif.plan_selection_keyboard(),
            parse_mode="HTML"
        )
    except:
        bot.send_message(
            call.message.chat.id,
            instructions,
            reply_markup=verif.plan_selection_keyboard(),
            parse_mode="HTML"
        )
    
    bot.answer_callback_query(call.id)

# ========== GET PREMIUM ==========
@bot.callback_query_handler(func=lambda call: call.data == "get_premium")
def handle_get_premium(call):
    user_id = call.from_user.id
    
    spam_result = check_spam(user_id)
    if spam_result:
        bot.send_message(call.message.chat.id, spam_result, parse_mode="HTML")
        bot.answer_callback_query(call.id)
        return
    
    reset_spam_counter(user_id)
    
    try:
        bot.edit_message_text(
            "👇 <b>Choose your membership plan:</b>",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=verif.plan_selection_keyboard(),
            parse_mode="HTML"
        )
    except:
        bot.send_message(
            call.message.chat.id,
            "👇 <b>Choose your membership plan:</b>",
            reply_markup=verif.plan_selection_keyboard(),
            parse_mode="HTML"
        )
    
    bot.answer_callback_query(call.id)

# ========== PAYMENT DONE ==========
@bot.callback_query_handler(func=lambda call: call.data == "payment_done")
def handle_payment_done(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    
    spam_result = check_spam(user_id)
    if spam_result:
        bot.send_message(chat_id, spam_result, parse_mode="HTML")
        bot.answer_callback_query(call.id)
        return
    
    reset_spam_counter(user_id)
    
    # Check if user has selected a plan
    if str(user_id) not in pending_verifications:
        bot.answer_callback_query(
            call.id, 
            "Please select a plan first!", 
            show_alert=True
        )
        return
    
    # Delete previous message
    try:
        bot.delete_message(chat_id, call.message.message_id)
    except:
        pass
    
    # Ask for screenshot
    verif.ask_for_screenshot(chat_id, user_id, pending_verifications[str(user_id)]['plan'])
    
    bot.answer_callback_query(call.id)

# ========== HANDLE SCREENSHOTS ==========
@bot.message_handler(content_types=['photo'])
def handle_photos(message):
    # First check if this is a payment screenshot
    if verif.handle_screenshot(message):
        return
    
    # If not payment screenshot, ignore silently
    pass

# ========== VERIFICATION CALLBACKS ==========
@bot.callback_query_handler(func=lambda call: call.data.startswith('verify_'))
def handle_verify(call):
    if str(call.from_user.id) != ADMIN_ID:
        bot.answer_callback_query(call.id, "Admin only!")
        return
    
    user_id = call.data.split('_')[1]
    
    success, msg = verif.verify_payment(user_id, call.from_user.id)
    
    if success:
        bot.answer_callback_query(call.id, "✅ Payment verified! Unique join link sent to user.")
        
        # Update the admin message
        try:
            bot.edit_message_caption(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                caption=call.message.caption + "\n\n✅ <b>VERIFIED - UNIQUE LINK SENT</b>",
                parse_mode="HTML"
            )
        except:
            pass
    else:
        bot.answer_callback_query(call.id, f"❌ Error: {msg}", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith('reject_'))
def handle_reject(call):
    if str(call.from_user.id) != ADMIN_ID:
        bot.answer_callback_query(call.id, "Admin only!")
        return
    
    user_id = call.data.split('_')[1]
    
    success, msg = verif.reject_payment(user_id, call.from_user.id)
    
    if success:
        bot.answer_callback_query(call.id, "❌ Payment rejected. User notified.")
        
        # Update the admin message
        try:
            bot.edit_message_caption(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                caption=call.message.caption + "\n\n❌ <b>REJECTED</b>",
                parse_mode="HTML"
            )
        except:
            pass
    else:
        bot.answer_callback_query(call.id, f"❌ Error: {msg}", show_alert=True)

# ========== /VERIFY COMMAND ==========
@bot.message_handler(commands=['verify'])
def handle_manual_verify(message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    
    args = message.text.split()
    if len(args) != 2:
        bot.reply_to(
            message,
            "Usage: /verify [user_id]\nExample: /verify 123456789"
        )
        return
    
    user_id = args[1]
    
    if user_id not in pending_verifications:
        bot.reply_to(message, "❌ User not in pending verifications")
        return
    
    success, msg = verif.verify_payment(user_id, message.from_user.id)
    bot.reply_to(message, msg)

# ========== /SETTINGS COMMAND (FIXED HTML) ==========
@bot.message_handler(commands=['settings'])
def handle_settings(message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    
    text = f"""
<b>⚙️ CURRENT SETTINGS</b>

<b>📢 Demo Channel:</b> {settings['demo_channel_link']}
<b>📞 Support Username:</b> @{settings['support_username']}
<b>📋 Log Channel:</b> {settings['log_channel']}

<b>💰 UPI Settings:</b>
• UPI ID: <code>{settings['upi_id']}</code>
• UPI Name: {settings['upi_name']}

<b>📅 Monthly Plan:</b>
• Name: {settings['monthly_name']}
• Amount: ₹{settings['monthly_amount']}
• Channel ID: <code>{settings['monthly_channel_id']}</code>

<b>♾️ Lifetime Plan:</b>
• Name: {settings['lifetime_name']}
• Amount: ₹{settings['lifetime_amount']}
• Channel ID: <code>{settings['lifetime_channel_id']}</code>

<b>To change settings, use:</b>
/set [key] [value]

<b>Available keys:</b>
demo_channel, support, log_channel, upi_id, upi_name,
monthly_name, monthly_amount, monthly_channel,
lifetime_name, lifetime_amount, lifetime_channel
    """
    
    bot.reply_to(message, text, parse_mode="HTML")

# ========== /SET COMMAND (FIXED HTML) ==========
@bot.message_handler(commands=['set'])
def handle_set(message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        bot.reply_to(message, "Usage: /set [key] [value]\nExample: /set monthly_amount 129")
        return
    
    key = args[1].lower()
    value = args[2]
    
    # Map keys to settings
    key_map = {
        "demo_channel": "demo_channel_link",
        "support": "support_username",
        "log_channel": "log_channel",
        "upi_id": "upi_id",
        "upi_name": "upi_name",
        "monthly_name": "monthly_name",
        "monthly_amount": "monthly_amount",
        "monthly_channel": "monthly_channel_id",
        "lifetime_name": "lifetime_name",
        "lifetime_amount": "lifetime_amount",
        "lifetime_channel": "lifetime_channel_id"
    }
    
    if key not in key_map:
        bot.reply_to(message, f"❌ Invalid key. Available: {', '.join(key_map.keys())}")
        return
    
    settings[key_map[key]] = value
    save_settings()
    
    bot.reply_to(message, f"✅ Updated {key} to: {value}")

# ========== /BAN COMMAND (FIXED HTML) ==========
@bot.message_handler(commands=['ban'])
def handle_ban(message):
    """Ban a user manually"""
    if str(message.from_user.id) != ADMIN_ID:
        bot.reply_to(message, "⛔ Admin access required!")
        return
    
    args = message.text.split()
    if len(args) < 3:
        help_text = """
<b>❌ Invalid Command Format</b>

<code>/ban [user_id] [minutes] [reason]</code>

<b>Examples:</b>
• <code>/ban 123456789 30 spamming</code>
• <code>/ban 987654321 1440 payment fraud</code>
        """
        bot.reply_to(message, help_text, parse_mode="HTML")
        return
    
    try:
        user_id = args[1]
        minutes = int(args[2])
        reason = " ".join(args[3:]) if len(args) > 3 else "Admin ban"
        
        # Convert minutes to seconds
        duration_seconds = minutes * 60
        
        # Ban the user
        success = ban_user(user_id, duration_seconds, reason, message.from_user.id)
        
        if success:
            bot.reply_to(
                message, 
                f"✅ User <code>{user_id}</code> banned for {minutes} minutes\nReason: {reason}",
                parse_mode="HTML"
            )
            
            # Log to channel
            try:
                log_msg = f"""
🔨 <b>USER BANNED</b>
👤 User ID: <code>{user_id}</code>
⏰ Duration: {minutes} minutes
📝 Reason: {reason}
👮 Banned by: @{message.from_user.username}
                """
                bot.send_message(settings['log_channel'], log_msg, parse_mode="HTML")
            except:
                pass
        else:
            bot.reply_to(message, "❌ Failed to ban user")
            
    except ValueError:
        bot.reply_to(message, "❌ Invalid minutes value. Must be a number.")
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {str(e)}")

# ========== /UNBAN COMMAND (FIXED HTML) ==========
@bot.message_handler(commands=['unban'])
def handle_unban(message):
    """Unban a user"""
    if str(message.from_user.id) != ADMIN_ID:
        bot.reply_to(message, "⛔ Admin access required!")
        return
    
    args = message.text.split()
    if len(args) != 2:
        bot.reply_to(message, "Usage: /unban [user_id]\nExample: /unban 123456789", parse_mode="HTML")
        return
    
    try:
        user_id = args[1]
        
        if user_id in spam_data:
            # Remove ban
            spam_data[user_id]["blocked_until"] = 0
            spam_data[user_id]["ban_reason"] = ""
            spam_data[user_id]["block_level"] = 0
            save_spam_data()
            
            bot.reply_to(message, f"✅ User <code>{user_id}</code> unbanned successfully!", parse_mode="HTML")
            
            # Notify user
            try:
                bot.send_message(
                    int(user_id),
                    "✅ <b>You have been unbanned!</b>\nYou can now use the bot again.",
                    parse_mode="HTML"
                )
            except:
                pass
        else:
            bot.reply_to(message, f"❌ User <code>{user_id}</code> not found in ban list", parse_mode="HTML")
            
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {str(e)}")

# ========== /BANLIST COMMAND ==========
@bot.message_handler(commands=['banlist'])
def handle_banlist(message):
    """Show all banned users"""
    if str(message.from_user.id) != ADMIN_ID:
        bot.reply_to(message, "⛔ Admin access required!")
        return
    
    current_time = time.time()
    banned_users = []
    
    for user_id, data in spam_data.items():
        blocked_until = data.get("blocked_until", 0)
        if blocked_until > current_time:
            time_left = int(blocked_until - current_time)
            minutes_left = time_left // 60
            hours_left = minutes_left // 60
            minutes_left = minutes_left % 60
            
            if hours_left > 0:
                time_str = f"{hours_left}h {minutes_left}m"
            else:
                time_str = f"{minutes_left}m"
            
            reason = data.get('ban_reason', 'Spam')
            
            # Try to get username
            username = "Unknown"
            if user_id in users_data:
                username = users_data[user_id].get('username', 'N/A')
            
            banned_users.append(
                f"👤 <b>ID:</b> <code>{user_id}</code>\n"
                f"📛 <b>Username:</b> @{username}\n"
                f"⏰ <b>Time left:</b> {time_str}\n"
                f"📝 <b>Reason:</b> {reason}\n"
                f"─────────────"
            )
    
    if not banned_users:
        bot.reply_to(message, "✅ <b>No banned users found!</b>", parse_mode="HTML")
        return
    
    # Split into multiple messages if too long
    text = "<b>🚫 BANNED USERS LIST:</b>\n\n" + "\n".join(banned_users)
    
    if len(text) > 4000:
        parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
        for part in parts:
            bot.send_message(message.chat.id, part, parse_mode="HTML")
    else:
        bot.reply_to(message, text, parse_mode="HTML")

# ========== /BROADCAST COMMAND ==========
@bot.message_handler(commands=['broadcast'])
def handle_broadcast(message):
    """Broadcast message to all users"""
    if str(message.from_user.id) != ADMIN_ID:
        return
    
    if not message.reply_to_message:
        help_text = """
<b>📢 BROADCAST COMMAND</b>

<code>Reply to any message with /broadcast</code>

<b>Supported:</b> Text, Photos, Videos, Documents, GIFs

<b>How to use:</b>
1. Send the message you want to broadcast
2. Reply to it with <code>/broadcast</code>
        """
        bot.reply_to(message, help_text, parse_mode="HTML")
        return
    
    replied_msg = message.reply_to_message
    progress_msg = bot.reply_to(message, "📤 <b>Broadcast Starting...</b>", parse_mode="HTML")
    
    total_users = len(users_data)
    if total_users == 0:
        bot.edit_message_text("❌ No users to broadcast", chat_id=message.chat.id, message_id=progress_msg.message_id)
        return
    
    def broadcast_thread():
        sent = 0
        failed = 0
        skipped = 0
        user_ids = list(users_data.keys())
        
        for idx, user_id_str in enumerate(user_ids):
            try:
                user_id = int(user_id_str)
                
                # Skip if blocked
                if user_id_str in spam_data:
                    if spam_data[user_id_str].get("blocked_until", 0) > time.time():
                        skipped += 1
                        continue
                
                # Send based on type
                if replied_msg.photo:
                    bot.send_photo(
                        user_id, 
                        photo=replied_msg.photo[-1].file_id, 
                        caption=replied_msg.caption or "", 
                        parse_mode="HTML"
                    )
                elif replied_msg.video:
                    bot.send_video(
                        user_id, 
                        video=replied_msg.video.file_id, 
                        caption=replied_msg.caption or "", 
                        parse_mode="HTML"
                    )
                elif replied_msg.document:
                    bot.send_document(
                        user_id, 
                        document=replied_msg.document.file_id, 
                        caption=replied_msg.caption or "", 
                        parse_mode="HTML"
                    )
                elif replied_msg.animation:
                    bot.send_animation(
                        user_id, 
                        animation=replied_msg.animation.file_id, 
                        caption=replied_msg.caption or "", 
                        parse_mode="HTML"
                    )
                elif replied_msg.text:
                    bot.send_message(user_id, replied_msg.text, parse_mode="HTML")
                elif replied_msg.caption:
                    bot.send_message(user_id, replied_msg.caption, parse_mode="HTML")
                
                sent += 1
                
                # Update progress every 10 users
                if idx % 10 == 0:
                    percent = int((idx + 1) / total_users * 100)
                    try:
                        bot.edit_message_text(
                            f"📤 Broadcasting... {percent}% ({sent} sent, {failed} failed)", 
                            chat_id=message.chat.id, 
                            message_id=progress_msg.message_id
                        )
                    except:
                        pass
                
                time.sleep(0.1)  # Rate limit protection
                
            except Exception as e:
                failed += 1
        
        final_text = f"""
✅ <b>BROADCAST COMPLETE!</b>

📊 <b>Results:</b>
• ✅ Sent: {sent}
• ❌ Failed: {failed}
• ⏭️ Skipped: {skipped}
• 👥 Total: {total_users}
        """
        
        try:
            bot.edit_message_text(
                final_text, 
                chat_id=message.chat.id, 
                message_id=progress_msg.message_id, 
                parse_mode="HTML"
            )
        except:
            pass
    
    thread = threading.Thread(target=broadcast_thread)
    thread.start()
    
    bot.reply_to(message, f"📢 Broadcast started to {total_users} users!")

# ========== /STATS COMMAND ==========
@bot.message_handler(commands=['stats'])
def handle_stats(message):
    """Show bot statistics"""
    if str(message.from_user.id) != ADMIN_ID:
        return
    
    current_time = time.time()
    blocked_users = sum(1 for u in spam_data.values() if u.get("blocked_until", 0) > current_time)
    pending_count = len(pending_verifications)
    
    today = datetime.now().strftime('%Y-%m-%d')
    new_today = sum(1 for u in users_data.values() if u.get('start_time', '').startswith(today))
    
    # Count premium users
    premium_users = sum(1 for u in users_data.values() if u.get('is_premium', False))
    
    stats_text = f"""
<b>📊 BOT STATISTICS</b>

👥 <b>Users:</b>
• Total Users: {len(users_data)}
• Premium Users: {premium_users}
• New Today: {new_today}
• Pending Verification: {pending_count}

🛡️ <b>Spam Protection:</b>
• Currently Blocked: {blocked_users}
• Tracked Users: {len(spam_data)}

💰 <b>Payment Info:</b>
• Monthly: ₹{PLANS['monthly']['amount']}
• Lifetime: ₹{PLANS['lifetime']['amount']}

📁 <b>Storage:</b>
• Data Files: {len(os.listdir(DATA_DIR))}

🚀 <b>Status:</b> ✅ Running
    """
    bot.reply_to(message, stats_text, parse_mode="HTML")

# ========== /EXPORTDATA COMMAND ==========
@bot.message_handler(commands=['exportdata'])
def handle_export_data(message):
    """Export all data as JSON"""
    if str(message.from_user.id) != ADMIN_ID:
        return
    
    try:
        status_msg = bot.reply_to(message, "📥 Preparing export...", parse_mode="HTML")
        
        export_data = {
            "export_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_users": len(users_data),
            "users": users_data,
            "spam_data": spam_data,
            "pending": pending_verifications
        }
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"export_{timestamp}.json"
        filepath = os.path.join(DATA_DIR, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=4)
        
        with open(filepath, 'rb') as f:
            bot.send_document(
                message.chat.id,
                f,
                caption=f"📊 Export: {len(users_data)} users\n⏰ {timestamp}"
            )
        
        bot.delete_message(message.chat.id, status_msg.message_id)
        
    except Exception as e:
        bot.reply_to(message, f"❌ Export failed: {str(e)}")

# ========== /IMPDATA COMMAND ==========
@bot.message_handler(commands=['impdata'])
def handle_impdata(message):
    """Import data from JSON file"""
    if str(message.from_user.id) != ADMIN_ID:
        bot.reply_to(message, "⛔ Admin access required!")
        return
    
    if not message.reply_to_message or not message.reply_to_message.document:
        bot.reply_to(message, "❌ Reply to a JSON file with /impdata")
        return
    
    try:
        status_msg = bot.reply_to(message, "📥 Downloading file...", parse_mode="HTML")
        
        file_info = bot.get_file(message.reply_to_message.document.file_id)
        file_name = message.reply_to_message.document.file_name
        
        if not file_name.lower().endswith('.json'):
            bot.edit_message_text("❌ File must be JSON", chat_id=message.chat.id, message_id=status_msg.message_id)
            return
        
        downloaded_file = bot.download_file(file_info.file_path)
        
        temp_path = f"/tmp/{file_name}"
        with open(temp_path, 'wb') as f:
            f.write(downloaded_file)
        
        with open(temp_path, 'r', encoding='utf-8') as f:
            imported_data = json.load(f)
        
        users_before = len(users_data)
        imported_count = 0
        updated_count = 0
        
        # Handle different formats
        if "users" in imported_data:
            data_to_import = imported_data["users"]
        else:
            data_to_import = imported_data
        
        for user_id_str, user_data in data_to_import.items():
            if user_id_str in users_data:
                users_data[user_id_str].update(user_data)
                updated_count += 1
            else:
                users_data[user_id_str] = user_data
                imported_count += 1
        
        save_users_data()
        os.remove(temp_path)
        
        success_msg = f"""
✅ <b>IMPORT COMPLETE!</b>

• Before: {users_before}
• After: {len(users_data)}
• New: {imported_count}
• Updated: {updated_count}
        """
        
        bot.edit_message_text(
            success_msg, 
            chat_id=message.chat.id, 
            message_id=status_msg.message_id, 
            parse_mode="HTML"
        )
        
    except Exception as e:
        bot.edit_message_text(
            f"❌ Error: {str(e)}", 
            chat_id=message.chat.id, 
            message_id=status_msg.message_id
        )

# ========== /BACKUP COMMAND ==========
@bot.message_handler(commands=['backup'])
def handle_backup(message):
    """Create data backup"""
    if str(message.from_user.id) != ADMIN_ID:
        return
    
    try:
        backup_data = {
            "users": users_data,
            "spam": spam_data,
            "pending": pending_verifications,
            "backup_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = f"backup_{timestamp}.json"
        backup_path = os.path.join(DATA_DIR, backup_file)
        
        with open(backup_path, 'w') as f:
            json.dump(backup_data, f, indent=4)
        
        with open(backup_path, 'rb') as f:
            bot.send_document(
                message.chat.id, 
                f, 
                caption=f"📦 Backup: {len(users_data)} users\n⏰ {timestamp}"
            )
        
    except Exception as e:
        bot.reply_to(message, f"❌ Backup failed: {str(e)}")

# ========== /SAVEDATA COMMAND ==========
@bot.message_handler(commands=['savedata'])
def handle_save_data(message):
    """Force save all data"""
    if str(message.from_user.id) != ADMIN_ID:
        return
    
    try:
        save_all_data()
        bot.reply_to(
            message, 
            f"✅ All data saved!\n👥 Users: {len(users_data)}\n💾 Location: {DATA_DIR}",
            parse_mode="HTML"
        )
    except Exception as e:
        bot.reply_to(message, f"❌ Save failed: {str(e)}")

# ========== /CLEANBACKUPS COMMAND ==========
@bot.message_handler(commands=['cleanbackups'])
def handle_clean_backups(message):
    """Clean old backup files"""
    if str(message.from_user.id) != ADMIN_ID:
        return
    
    try:
        backup_files = [f for f in os.listdir(DATA_DIR) if f.startswith('backup_') and f.endswith('.json')]
        backup_files.sort(key=lambda x: os.path.getmtime(os.path.join(DATA_DIR, x)))
        
        if len(backup_files) <= 5:
            bot.reply_to(message, f"✅ Only {len(backup_files)} backups found (keeping all)")
            return
        
        files_to_delete = backup_files[:-5]
        deleted_count = 0
        deleted_size = 0
        
        for filename in files_to_delete:
            filepath = os.path.join(DATA_DIR, filename)
            file_size = os.path.getsize(filepath)
            os.remove(filepath)
            deleted_count += 1
            deleted_size += file_size
        
        result_msg = f"""
🧹 <b>CLEANUP COMPLETE</b>

📁 Deleted: {deleted_count} files
💾 Freed: {deleted_size//1024} KB
📊 Remaining: {len(backup_files) - deleted_count} backups
        """
        
        bot.reply_to(message, result_msg, parse_mode="HTML")
        
    except Exception as e:
        bot.reply_to(message, f"❌ Cleanup failed: {str(e)}")

# ========== /SETSTARTMSG COMMAND ==========
@bot.message_handler(commands=['setstartmsg'])
def handle_set_start_message(message):
    """Set custom start message"""
    if str(message.from_user.id) != ADMIN_ID:
        return
    
    if not message.reply_to_message:
        bot.reply_to(message, "❌ Reply to a message with /setstartmsg")
        return
    
    replied_msg = message.reply_to_message
    
    start_message_data['text'] = replied_msg.caption or replied_msg.text or ""
    start_message_data['has_media'] = False
    
    if replied_msg.photo:
        start_message_data['media_type'] = 'photo'
        start_message_data['file_id'] = replied_msg.photo[-1].file_id
        start_message_data['has_media'] = True
    elif replied_msg.video:
        start_message_data['media_type'] = 'video'
        start_message_data['file_id'] = replied_msg.video.file_id
        start_message_data['has_media'] = True
    elif replied_msg.document:
        start_message_data['media_type'] = 'document'
        start_message_data['file_id'] = replied_msg.document.file_id
        start_message_data['has_media'] = True
    
    save_start_message()
    bot.reply_to(message, "✅ Start message updated!")

# ========== /GETSTARTMSG COMMAND ==========
@bot.message_handler(commands=['getstartmsg'])
def handle_get_start_message(message):
    """View current start message"""
    if str(message.from_user.id) != ADMIN_ID:
        return
    
    if not start_message_data:
        bot.reply_to(message, "❌ No custom start message set")
        return
    
    media_type = start_message_data.get('media_type', 'text')
    has_media = start_message_data.get('has_media', False)
    text_preview = start_message_data.get('text', '')[:100]
    if len(start_message_data.get('text', '')) > 100:
        text_preview += "..."
    
    info_msg = f"""
<b>📋 CURRENT START MESSAGE</b>

<b>Type:</b> {media_type if has_media else 'Text Only'}
<b>Has Media:</b> {'✅ Yes' if has_media else '❌ No'}
<b>Preview:</b> {text_preview}
    """
    
    bot.reply_to(message, info_msg, parse_mode="HTML")

# ========== /CLEARSTARTMSG COMMAND ==========
@bot.message_handler(commands=['clearstartmsg'])
def handle_clear_start_message(message):
    """Clear custom start message"""
    if str(message.from_user.id) != ADMIN_ID:
        return
    
    global start_message_data
    start_message_data = {}
    save_start_message()
    bot.reply_to(message, "✅ Custom start message cleared")

# ========== /PENDING COMMAND ==========
@bot.message_handler(commands=['pending'])
def handle_pending(message):
    """Show pending verifications"""
    if str(message.from_user.id) != ADMIN_ID:
        return
    
    if not pending_verifications:
        bot.reply_to(message, "✅ No pending verifications")
        return
    
    text = "<b>⏳ PENDING VERIFICATIONS:</b>\n\n"
    for uid, data in pending_verifications.items():
        plan = PLANS[data['plan']]['name']
        text += f"👤 ID: <code>{uid}</code>\n"
        text += f"📅 Plan: {plan}\n"
        text += f"💰 Amount: ₹{data['amount']}\n"
        text += f"⏰ Time: {data['initiated_at']}\n"
        text += f"📸 Screenshot: {'✅' if 'screenshot_file_id' in data else '❌'}\n"
        text += "───────────────\n"
    
    # Split if too long
    if len(text) > 4000:
        parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
        for part in parts:
            bot.send_message(message.chat.id, part, parse_mode="HTML")
    else:
        bot.reply_to(message, text, parse_mode="HTML")

# ========== /HELP COMMAND (FIXED HTML) ==========
@bot.message_handler(commands=['help'])
def handle_help(message):
    """Show help message"""
    if str(message.from_user.id) != ADMIN_ID:
        # User help
        user_help = f"""
<b>🤖 Bot Commands:</b>

/start - Start the bot
/help - Show this help

For premium: Click "Get Premium" button

<b>Demo Channel:</b> {settings['demo_channel_link']}
<b>Support:</b> @{settings['support_username']}
        """
        bot.reply_to(message, user_help, parse_mode="HTML")
        return
    
    # Admin help
    admin_help = """
<b>👮 ADMIN COMMANDS</b>

<b>📋 VERIFICATION:</b>
/pending - Show pending verifications
/verify [user_id] - Manual verify

<b>⚙️ SETTINGS:</b>
/settings - View all settings
/set [key] [value] - Change setting

<b>🚫 USER MANAGEMENT:</b>
/ban [id] [min] [reason] - Ban user
/unban [id] - Unban user
/banlist - Show banned users

<b>📢 BROADCAST:</b>
/broadcast (reply) - Broadcast message

<b>📊 DATA:</b>
/stats - Bot statistics
/exportdata - Export users data
/impdata (reply) - Import data
/backup - Create backup
/savedata - Force save
/cleanbackups - Clean old backups

<b>✏️ START MESSAGE:</b>
/setstartmsg (reply) - Set custom start
/getstartmsg - View current
/clearstartmsg - Clear custom

<b>ℹ️ OTHER:</b>
/help - Show this help
    """
    
    # Split if too long
    if len(admin_help) > 4000:
        parts = [admin_help[i:i+4000] for i in range(0, len(admin_help), 4000)]
        for part in parts:
            bot.send_message(message.chat.id, part, parse_mode="HTML")
    else:
        bot.reply_to(message, admin_help, parse_mode="HTML")

# ========== SILENT HANDLER ==========
@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    # Ignore all other messages
    pass

# ========== START BOT ==========
if __name__ == "__main__":
    print("=" * 60)
    print("🤖 PREMIUM BOT - TWO CHANNELS + DYNAMIC CONFIG")
    print("=" * 60)
    
    print(f"✅ Bot Token: {BOT_TOKEN[:15]}...")
    print(f"✅ Admin ID: {ADMIN_ID}")
    print(f"✅ Users Loaded: {len(users_data)}")
    print(f"✅ Pending: {len(pending_verifications)}")
    print(f"✅ Monthly: ₹{PLANS['monthly']['amount']} - Channel: {PLANS['monthly']['channel_id']}")
    print(f"✅ Lifetime: ₹{PLANS['lifetime']['amount']} - Channel: {PLANS['lifetime']['channel_id']}")
    print("=" * 60)
    print("📋 Type /help for all commands")
    print("📋 Type /settings to view/edit config")
    print("=" * 60)
    
    try:
        bot.infinity_polling()
    except Exception as e:
        print(f"❌ Bot Error: {e}")
        time.sleep(10)
        sys.exit(1)
