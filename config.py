import os
import json
from datetime import datetime, timedelta
import logging

# ============ CONFIG FROM ENVIRONMENT ============
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_ID = os.environ.get("ADMIN_ID", "")
LOG_CHANNEL = os.environ.get("LOG_CHANNEL", "")
SUPPORT_USERNAME = os.environ.get("SUPPORT_USERNAME", "support")
DEMO_CHANNEL_LINK = os.environ.get("DEMO_CHANNEL_LINK", "https://t.me/your_demo_channel")
UPI_ID = os.environ.get("UPI_ID", "your_upi@okhdfcbank")
UPI_NAME = os.environ.get("UPI_NAME", "Your Name")

# Channel IDs for auto invite links
MONTHLY_CHANNEL_ID = os.environ.get("MONTHLY_CHANNEL_ID", "")  # e.g., -100123456789
LIFETIME_CHANNEL_ID = os.environ.get("LIFETIME_CHANNEL_ID", "")  # e.g., -100987654321

# Railway persistent volume - CHANGE THIS:
# Railway provides /data directory for persistent storage
DATA_DIR = "/data"  # ✅ Railway ka persistent volume
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR, exist_ok=True)
    print(f"✅ Created data directory: {DATA_DIR}")

# Rest of your config.py remains the SAME...
