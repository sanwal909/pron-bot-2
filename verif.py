import telebot
from telebot import types
import time
import threading
from datetime import datetime, timedelta
import logging

from config import *

logger = logging.getLogger(__name__)

class VerificationSystem:
    def __init__(self, bot):
        self.bot = bot
        self.pending = pending_verifications
    
    def save_pending(self):
        """Save pending verifications"""
        save_json_file(PENDING_VERIF_FILE, self.pending)
    
    def create_invite_link(self, user_id, plan_type):
        """Create unique invite link for specific channel based on plan"""
        try:
            plan = PLANS[plan_type]
            channel_id = plan.get('channel_id', '')
            
            if not channel_id:
                return f"Channel ID not configured for {plan['name']}. Contact admin."
            
            # Create expire date (30 days for monthly, 1 year for lifetime)
            if plan_type == "monthly":
                expire_date = datetime.now() + timedelta(days=30)
            else:
                expire_date = datetime.now() + timedelta(days=365)
            
            # Create invite link
            invite = self.bot.create_chat_invite_link(
                chat_id=channel_id,
                member_limit=1,  # Single use
                expire_date=expire_date
            )
            
            # Store link info
            if str(user_id) not in invite_links:
                invite_links[str(user_id)] = []
            
            invite_links[str(user_id)].append({
                "link": invite.invite_link,
                "plan": plan_type,
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "expires_at": expire_date.strftime("%Y-%m-%d %H:%M:%S"),
                "used": False
            })
            save_json_file(INVITE_LINKS_FILE, invite_links)
            
            return invite.invite_link
        except Exception as e:
            logger.error(f"Error creating invite link: {e}")
            return f"Error creating link: {str(e)}"
    
    def plan_selection_keyboard(self):
        """Show plan selection buttons"""
        keyboard = types.InlineKeyboardMarkup(row_width=2)
        btn1 = types.InlineKeyboardButton(
            f"📅 {PLANS['monthly']['name']} - ₹{PLANS['monthly']['amount']}", 
            callback_data="plan_monthly"
        )
        btn2 = types.InlineKeyboardButton(
            f"♾️ {PLANS['lifetime']['name']} - ₹{PLANS['lifetime']['amount']}", 
            callback_data="plan_lifetime"
        )
        btn3 = types.InlineKeyboardButton("❓ How To Get", callback_data="how_to_get")
        btn4 = types.InlineKeyboardButton("📞 Support", url=f"https://t.me/{settings['support_username']}")
        keyboard.add(btn1, btn2)
        keyboard.add(btn3, btn4)
        return keyboard
    
    def main_menu_keyboard(self):
        """Main menu with demo button"""
        keyboard = types.InlineKeyboardMarkup(row_width=1)
        btn1 = types.InlineKeyboardButton("📢 Premium Demo", url=settings['demo_channel_link'])
        btn2 = types.InlineKeyboardButton("💰 Get Premium", callback_data="get_premium")
        btn3 = types.InlineKeyboardButton("❓ How To Get", callback_data="how_to_get")
        keyboard.add(btn1, btn2, btn3)
        return keyboard
    
    def ask_for_screenshot(self, chat_id, user_id, plan_type):
        """Ask user to send payment screenshot"""
        plan = PLANS[plan_type]
        msg = self.bot.send_message(
            chat_id,
            f"""
<b>📸 SEND PAYMENT SCREENSHOT</b>

<b>Plan Selected:</b> {plan['name']}
<b>Amount to Pay:</b> ₹{plan['amount']}
<b>UPI ID:</b> <code>{settings['upi_id']}</code>

✅ <b>Payment Done!</b>

Now please send the <b>payment screenshot</b> for verification.

<b>Instructions:</b>
1. Take screenshot of UPI payment
2. Send it here as photo
3. Admin will verify within few minutes
4. You'll receive unique join link after verification

⏳ <i>Please wait for admin verification...</i>
            """,
            parse_mode="HTML"
        )
        return msg
    
    def handle_screenshot(self, message):
        """Handle payment screenshot from user"""
        user_id = str(message.from_user.id)
        
        # Check if user has pending verification
        if user_id not in self.pending:
            return False
        
        if not message.photo:
            self.bot.reply_to(
                message,
                "❌ Please send a PHOTO (screenshot) of your payment."
            )
            return True
        
        pending_data = self.pending[user_id]
        plan_type = pending_data['plan']
        plan = PLANS[plan_type]
        
        # Get the largest photo
        photo = message.photo[-1]
        file_id = photo.file_id
        
        # Store screenshot info
        pending_data['screenshot_file_id'] = file_id
        pending_data['screenshot_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        pending_data['screenshot_msg_id'] = message.message_id
        self.save_pending()
        
        # Create verification buttons for admin
        keyboard = types.InlineKeyboardMarkup(row_width=2)
        verify_btn = types.InlineKeyboardButton(
            "✅ Verify Payment", 
            callback_data=f"verify_{user_id}"
        )
        reject_btn = types.InlineKeyboardButton(
            "❌ Reject", 
            callback_data=f"reject_{user_id}"
        )
        keyboard.add(verify_btn, reject_btn)
        
        # Forward screenshot to admin log channel
        caption = f"""
📸 <b>PAYMENT SCREENSHOT RECEIVED</b>

👤 User: @{message.from_user.username or 'N/A'}
🆔 User ID: <code>{user_id}</code>
📅 Plan: {plan['name']}
💰 Amount: ₹{plan['amount']}
⏰ Time: {pending_data['screenshot_time']}

<b>Verify payment and send join link:</b>
        """
        
        try:
            # Send screenshot to log channel
            sent_msg = self.bot.send_photo(
                settings['log_channel'],
                photo=file_id,
                caption=caption,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            
            # Store admin message ID
            pending_data['admin_msg_id'] = sent_msg.message_id
            pending_data['admin_chat_id'] = settings['log_channel']
            self.save_pending()
            
            # Notify user
            self.bot.reply_to(
                message,
                f"""
✅ <b>Screenshot received!</b>

Admin will verify your payment soon.
You'll receive unique join link within few minutes.

⏳ <i>Thank you for your patience!</i>
                """,
                parse_mode="HTML"
            )
            
        except Exception as e:
            logger.error(f"Error forwarding screenshot: {e}")
            self.bot.reply_to(
                message,
                f"❌ Error sending screenshot. Please contact @{settings['support_username']}"
            )
        
        return True
    
    def verify_payment(self, user_id, admin_id):
        """Verify payment and send unique invite link"""
        user_id = str(user_id)
        
        if user_id not in self.pending:
            return False, "User not found in pending verifications"
        
        pending_data = self.pending[user_id]
        plan_type = pending_data['plan']
        plan = PLANS[plan_type]
        
        # Create unique invite link for specific channel
        invite_link = self.create_invite_link(user_id, plan_type)
        
        # Send join link to user
        try:
            join_msg = f"""
🎉 <b>PAYMENT VERIFIED SUCCESSFULLY!</b>

<b>Plan:</b> {plan['name']}
<b>Amount Paid:</b> ₹{plan['amount']}

<b>👇 Your Unique Invite Link (Single Use):</b>
{invite_link}

⚠️ <b>Note:</b> This link can only be used ONCE and is personal to you.
📅 <b>Access Duration:</b> {plan['duration']}

<b>Welcome to Premium Family! 🎊</b>
            """
            
            self.bot.send_message(
                int(user_id),
                join_msg,
                parse_mode="HTML"
            )
            
            # Log verification
            log_msg = f"""
✅ <b>PAYMENT VERIFIED</b>

👤 User ID: <code>{user_id}</code>
📅 Plan: {plan['name']}
💰 Amount: ₹{plan['amount']}
👮 Verified By: Admin
🔗 Invite Link: {invite_link}
⏰ Time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
            """
            
            self.bot.send_message(
                settings['log_channel'],
                log_msg,
                parse_mode="HTML"
            )
            
            # Update user data to mark as premium
            if user_id in users_data:
                users_data[user_id]['is_premium'] = True
                users_data[user_id]['premium_plan'] = plan_type
                users_data[user_id]['premium_until'] = (
                    "lifetime" if plan_type == "lifetime" 
                    else (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
                )
                users_data[user_id]['invite_link'] = invite_link
                save_users_data()
            
            # Remove from pending
            del self.pending[user_id]
            self.save_pending()
            
            return True, "User verified and unique join link sent"
            
        except Exception as e:
            logger.error(f"Error sending join link: {e}")
            return False, f"Error sending message: {str(e)}"
    
    def reject_payment(self, user_id, admin_id):
        """Reject payment and notify user"""
        user_id = str(user_id)
        
        if user_id not in self.pending:
            return False, "User not found in pending verifications"
        
        pending_data = self.pending[user_id]
        
        # Notify user
        try:
            reject_msg = f"""
❌ <b>PAYMENT VERIFICATION FAILED</b>

Your payment screenshot could not be verified.

<b>Possible reasons:</b>
• Screenshot not clear
• Wrong amount paid
• Payment not received

<b>Please try again or contact support:</b>
📞 @{settings['support_username']}
            """
            
            self.bot.send_message(
                int(user_id),
                reject_msg,
                parse_mode="HTML"
            )
            
            # Log rejection
            log_msg = f"""
❌ <b>PAYMENT REJECTED</b>

👤 User ID: <code>{user_id}</code>
👮 Rejected By: Admin
⏰ Time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
            """
            
            self.bot.send_message(
                settings['log_channel'],
                log_msg,
                parse_mode="HTML"
            )
            
            # Remove from pending
            del self.pending[user_id]
            self.save_pending()
            
            return True, "Payment rejected and user notified"
            
        except Exception as e:
            logger.error(f"Error rejecting payment: {e}")
            return False, f"Error: {str(e)}"

# Initialize verification system
verification = None

def init_verification(bot_instance):
    global verification
    verification = VerificationSystem(bot_instance)
    return verification
