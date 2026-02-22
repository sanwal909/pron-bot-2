import json
import os
import time
from datetime import datetime, timedelta
import logging

# ============ CONFIG FROM ENVIRONMENT ============
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = os.environ.get("ADMIN_ID", "")
LOG_CHANNEL = os.environ.get("LOG_CHANNEL", "")
SUPPORT_USERNAME = os.environ.get("SUPPORT_USERNAME", "")
DEMO_CHANNEL_LINK = os.environ.get("DEMO_CHANNEL_LINK", "")
UPI_ID = os.environ.get("UPI_ID", "")
UPI_NAME = os.environ.get("UPI_NAME", "")

# Channel IDs for auto invite links
MONTHLY_CHANNEL_ID = os.environ.get("MONTHLY_CHANNEL_ID", "")
LIFETIME_CHANNEL_ID = os.environ.get("LIFETIME_CHANNEL_ID", "")

# Spam protection settings
MAX_SPAM_COUNT = int(os.environ.get("MAX_SPAM_COUNT", "5"))
SPAM_TIME_WINDOW = int(os.environ.get("SPAM_TIME_WINDOW", "10"))
WARNING_MESSAGES = ["⚠️ Please don't spam!", "⚠️ This is your last warning!", "⛔ You are being blocked for spamming!"]
BLOCK_DURATIONS = [300, 900, 1800]  # 5min, 15min, 30min (seconds)

# ============ DATA DIRECTORY ============
DATA_DIR = "/data"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR, exist_ok=True)
    print(f"✅ Created data directory: {DATA_DIR}")

# Data files
USERS_DATA_FILE = os.path.join(DATA_DIR, "users_data.json")
SPAM_DATA_FILE = os.path.join(DATA_DIR, "spam_data.json")
START_MESSAGE_FILE = os.path.join(DATA_DIR, "start_message.json")
PENDING_VERIF_FILE = os.path.join(DATA_DIR, "pending_verifications.json")
INVITE_LINKS_FILE = os.path.join(DATA_DIR, "invite_links.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")

# ============ DEFAULT SETTINGS ============
DEFAULT_SETTINGS = {
    "log_channel": LOG_CHANNEL,
    "support_username": SUPPORT_USERNAME,
    "demo_channel_link": DEMO_CHANNEL_LINK,
    "upi_id": UPI_ID,
    "upi_name": UPI_NAME,
    "monthly_channel_id": MONTHLY_CHANNEL_ID,
    "lifetime_channel_id": LIFETIME_CHANNEL_ID,
    "monthly_amount": "99",
    "lifetime_amount": "149",
    "monthly_name": "1 Month Premium",
    "lifetime_name": "Lifetime Premium"
}

# ============ DATA LOAD/SAVE FUNCTIONS ============
def load_json_file(filepath, default=None):
    """Load JSON file with error handling"""
    if default is None:
        default = {}
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                return json.load(f)
        else:
            with open(filepath, 'w') as f:
                json.dump(default, f)
            return default
    except Exception as e:
        logging.error(f"Error loading {filepath}: {e}")
        return default

def save_json_file(filepath, data):
    """Save JSON file with error handling"""
    try:
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=4)
        return True
    except Exception as e:
        logging.error(f"Error saving {filepath}: {e}")
        return False

# ============ LOAD ALL DATA ============
users_data = load_json_file(USERS_DATA_FILE, {})
spam_data = load_json_file(SPAM_DATA_FILE, {})
start_message_data = load_json_file(START_MESSAGE_FILE, {})
pending_verifications = load_json_file(PENDING_VERIF_FILE, {})

# FIXED: Load invite_links and ensure all values are LISTS
invite_links = load_json_file(INVITE_LINKS_FILE, {})
for user_id in invite_links:
    if not isinstance(invite_links[user_id], list):
        # If it's not a list, convert to list or create new list
        if isinstance(invite_links[user_id], dict):
            # Old format - convert dict to list with one item
            old_data = invite_links[user_id]
            invite_links[user_id] = [old_data]
        else:
            # Unknown format - create empty list
            invite_links[user_id] = []

settings = load_json_file(SETTINGS_FILE, DEFAULT_SETTINGS)

# Update PLANS with settings
PLANS = {
    "monthly": {
        "name": settings.get("monthly_name", "1 Month Premium"),
        "amount": settings.get("monthly_amount", "99"),
        "duration": "30 days",
        "channel_id": settings.get("monthly_channel_id", "")
    },
    "lifetime": {
        "name": settings.get("lifetime_name", "Lifetime Premium"),
        "amount": settings.get("lifetime_amount", "149"),
        "duration": "Lifetime",
        "channel_id": settings.get("lifetime_channel_id", "")
    }
}

# Individual save functions
def save_users_data():
    """Save users data"""
    save_json_file(USERS_DATA_FILE, users_data)

def save_spam_data():
    """Save spam data"""
    save_json_file(SPAM_DATA_FILE, spam_data)

def save_start_message():
    """Save start message"""
    save_json_file(START_MESSAGE_FILE, start_message_data)

def save_settings():
    """Save settings"""
    save_json_file(SETTINGS_FILE, settings)
    # Update PLANS with new settings
    global PLANS
    PLANS = {
        "monthly": {
            "name": settings.get("monthly_name", "1 Month Premium"),
            "amount": settings.get("monthly_amount", "99"),
            "duration": "30 days",
            "channel_id": settings.get("monthly_channel_id", "")
        },
        "lifetime": {
            "name": settings.get("lifetime_name", "Lifetime Premium"),
            "amount": settings.get("lifetime_amount", "149"),
            "duration": "Lifetime",
            "channel_id": settings.get("lifetime_channel_id", "")
        }
    }

def save_all_data():
    """Save all data at once"""
    save_json_file(USERS_DATA_FILE, users_data)
    save_json_file(SPAM_DATA_FILE, spam_data)
    save_json_file(START_MESSAGE_FILE, start_message_data)
    save_json_file(PENDING_VERIF_FILE, pending_verifications)
    save_json_file(INVITE_LINKS_FILE, invite_links)
    save_json_file(SETTINGS_FILE, settings)
    print("💾 All data saved")

# Initialize spam data for existing users
def initialize_spam_data():
    """Ensure all existing users have spam_data entries"""
    initialized = 0
    for user_id_str in users_data.keys():
        if user_id_str not in spam_data:
            spam_data[user_id_str] = {
                "requests": [],
                "warnings": 0,
                "blocked_until": 0,
                "block_level": 0,
                "ban_reason": "",
                "banned_by": 0
            }
            initialized += 1
    if initialized > 0:
        print(f"✅ Initialized spam data for {initialized} users")

initialize_spam_data()
