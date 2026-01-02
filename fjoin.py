# -*- coding: utf-8 -*-
import telebot
import subprocess
import os
import zipfile
import tempfile
import shutil
from telebot import types
import time
from datetime import datetime, timedelta
import psutil
import sqlite3
import logging
import threading
import re
import sys
import atexit
import requests
import random
import string

# --- Flask Keep Alive ---
from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "Galaxy File Host - Premium File Hosting Service"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    print("Flask Keep-Alive server started.")
# --- End Flask Keep Alive ---

# --- Configuration ---
TOKEN = '8215316739:AAG0o3thu0j2jQQNIWSrlRyIfSvg8IirifE'
OWNER_ID = 7785120391
ADMIN_ID = 7785120391
YOUR_USERNAME = '@GALAXYxIGL'

# Force Join Settings
FORCE_CHANNEL = '@xclusor'  # Your channel username
FORCE_GROUP = '@xclusorotp'  # Your group username

# Folder setup
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_BOTS_DIR = os.path.join(BASE_DIR, 'upload_bots')
GALAXY_DIR = os.path.join(BASE_DIR, 'galaxy_data')
DATABASE_PATH = os.path.join(GALAXY_DIR, 'galaxy_host.db')

# File upload limits
FREE_USER_LIMIT = 1
PREMIUM_USER_LIMIT = 999
ADMIN_LIMIT = 999
OWNER_LIMIT = float('inf')

# Create necessary directories
os.makedirs(UPLOAD_BOTS_DIR, exist_ok=True)
os.makedirs(GALAXY_DIR, exist_ok=True)

# Initialize bot with increased timeout
bot = telebot.TeleBot(TOKEN, threaded=True, num_threads=10)

# --- Data structures ---
bot_scripts = {}
user_subscriptions = {}
user_files = {}
active_users = set()
admin_ids = {ADMIN_ID, OWNER_ID}
bot_locked = False
force_join_enabled = True  # Enable force join by default

# Supported file extensions
SUPPORTED_EXTENSIONS = {
    '.py': 'python', '.java': 'java', '.html': 'html', '.htm': 'html',
    '.js': 'javascript', '.css': 'css', '.txt': 'text', '.json': 'json',
    '.xml': 'xml', '.php': 'php', '.c': 'c', '.cpp': 'c++', '.cs': 'c#',
    '.rb': 'ruby', '.go': 'go', '.rs': 'rust', '.md': 'markdown',
    '.yaml': 'yaml', '.yml': 'yaml', '.sql': 'sql', '.sh': 'shell',
    '.bat': 'batch', '.ps1': 'powershell', '.r': 'r', '.swift': 'swift',
    '.kt': 'kotlin', '.scala': 'scala', '.pl': 'perl', '.lua': 'lua',
    '.ts': 'typescript', '.jsx': 'react jsx', '.tsx': 'react tsx',
    '.vue': 'vue', '.svelte': 'svelte', '.dart': 'dart', '.scss': 'scss',
    '.less': 'less', '.styl': 'stylus', '.coffee': 'coffeescript'
}

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Database Setup ---
def init_db():
    """initialize the database with required tables"""
    logger.info(f"initializing database at: {DATABASE_PATH}")
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        
        # users table
        c.execute('''create table if not exists users
                     (user_id integer primary key, username text, 
                      first_name text, last_name text, join_date timestamp default current_timestamp,
                      verified integer default 0)''')
        
        # subscriptions table
        c.execute('''create table if not exists subscriptions
                     (user_id integer primary key, expiry text, 
                      redeemed_date timestamp default current_timestamp)''')
        
        # user files table
        c.execute('''create table if not exists user_files
                     (user_id integer, file_name text, file_type text, file_path text,
                      upload_date timestamp default current_timestamp,
                      primary key (user_id, file_name))''')
        
        # active users table
        c.execute('''create table if not exists active_users
                     (user_id integer primary key)''')
        
        # admins table
        c.execute('''create table if not exists admins
                     (user_id integer primary key)''')
        
        # subscription keys table
        c.execute('''create table if not exists subscription_keys
                     (key_value text primary key, days_valid integer, 
                      max_uses integer, used_count integer default 0,
                      created_date timestamp default current_timestamp)''')
        
        # key usage table
        c.execute('''create table if not exists key_usage
                     (key_value text, user_id integer, used_date timestamp default current_timestamp,
                      primary key (key_value, user_id))''')
        
        # bot settings table
        c.execute('''create table if not exists bot_settings
                     (setting_key text primary key, setting_value text)''')
        
        # insert default settings
        c.execute('insert or ignore into bot_settings (setting_key, setting_value) values (?, ?)', 
                 ('free_user_limit', str(FREE_USER_LIMIT)))
        c.execute('insert or ignore into bot_settings (setting_key, setting_value) values (?, ?)', 
                 ('force_join_enabled', '1'))
        
        # ensure owner and initial admin are in admins table
        c.execute('insert or ignore into admins (user_id) values (?)', (OWNER_ID,))
        if ADMIN_ID != OWNER_ID:
            c.execute('insert or ignore into admins (user_id) values (?)', (ADMIN_ID,))
        
        conn.commit()
        conn.close()
        logger.info("database initialized successfully.")
    except Exception as e:
        logger.error(f"database initialization error: {e}", exc_info=True)

def load_data():
    """load data from database into memory"""
    logger.info("loading data from database...")
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()

        # load subscriptions
        c.execute('select user_id, expiry from subscriptions')
        for user_id, expiry in c.fetchall():
            try:
                user_subscriptions[user_id] = {'expiry': datetime.fromisoformat(expiry)}
            except ValueError:
                logger.warning(f"invalid expiry date format for user {user_id}: {expiry}. skipping.")

        # load user files
        c.execute('select user_id, file_name, file_type, file_path from user_files')
        for user_id, file_name, file_type, file_path in c.fetchall():
            if user_id not in user_files:
                user_files[user_id] = []
            user_files[user_id].append((file_name, file_type, file_path))

        # load active users
        c.execute('select user_id from active_users')
        active_users.update(user_id for (user_id,) in c.fetchall())

        # load admins
        c.execute('select user_id from admins')
        admin_ids.update(user_id for (user_id,) in c.fetchall())

        # load bot settings
        c.execute('select setting_key, setting_value from bot_settings')
        for key, value in c.fetchall():
            if key == 'free_user_limit':
                global FREE_USER_LIMIT
                FREE_USER_LIMIT = int(value) if value.isdigit() else 1
            elif key == 'force_join_enabled':
                global force_join_enabled
                force_join_enabled = value == '1'

        conn.close()
        logger.info(f"data loaded: {len(active_users)} users, {len(user_subscriptions)} subscriptions, {len(admin_ids)} admins.")
    except Exception as e:
        logger.error(f"error loading data: {e}", exc_info=True)

# initialize db and load data at startup
init_db()
load_data()

# --- Helper Functions ---
def to_small_caps(text):
    """convert text to small caps style"""
    small_caps_map = {
        'A': 'ᴀ', 'B': 'ʙ', 'C': 'ᴄ', 'D': 'ᴅ', 'E': 'ᴇ', 'F': 'ғ', 'G': 'ɢ', 'H': 'ʜ',
        'I': 'ɪ', 'J': 'ᴊ', 'K': 'ᴋ', 'L': 'ʟ', 'M': 'ᴍ', 'N': 'ɴ', 'O': 'ᴏ', 'P': 'ᴘ',
        'Q': 'ǫ', 'R': 'ʀ', 'S': 's', 'T': 'ᴛ', 'U': 'ᴜ', 'V': 'ᴠ', 'W': 'ᴡ', 'X': 'x',
        'Y': 'ʏ', 'Z': 'ᴢ',
        'a': 'ᴀ', 'b': 'ʙ', 'c': 'ᴄ', 'd': 'ᴅ', 'e': 'ᴇ', 'f': 'ғ', 'g': 'ɢ', 'h': 'ʜ',
        'i': 'ɪ', 'j': 'ᴊ', 'k': 'ᴋ', 'l': 'ʟ', 'm': 'ᴍ', 'n': 'ɴ', 'o': 'ᴏ', 'p': 'ᴘ',
        'q': 'ǫ', 'r': 'ʀ', 's': 's', 't': 'ᴛ', 'u': 'ᴜ', 'v': 'ᴠ', 'w': 'ᴡ', 'x': 'x',
        'y': 'ʏ', 'z': 'ᴢ'
    }
    return ''.join(small_caps_map.get(char, char) for char in text)

def check_force_join(user_id):
    """check if user is member of required channel and group"""
    if user_id in admin_ids:
        return True
    
    if not force_join_enabled:
        return True
    
    try:
        # Check channel membership
        channel_member = bot.get_chat_member(FORCE_CHANNEL, user_id)
        if channel_member.status not in ['member', 'administrator', 'creator']:
            return False
        
        # Check group membership
        group_member = bot.get_chat_member(FORCE_GROUP, user_id)
        if group_member.status not in ['member', 'administrator', 'creator']:
            return False
        
        return True
    except Exception as e:
        logger.error(f"error checking membership for user {user_id}: {e}")
        return False

def create_force_join_message():
    """create force join message with beautiful UI"""
    return to_small_caps(f"""
🔒 **ᴍᴇᴍʙᴇʀsʜɪᴘ ʀᴇǫᴜɪʀᴇᴅ!** 🔒

📢 **ᴛᴏ ᴜsᴇ ᴛʜɪs ʙᴏᴛ, ʏᴏᴜ ᴍᴜsᴛ ᴊᴏɪɴ ᴏᴜʀ ᴄʜᴀɴɴᴇʟ & ɢʀᴏᴜᴘ:**

━━━━━━━━━━━━━━━━━━━━
📢 **ᴄʜᴀɴɴᴇʟ:** {FORCE_CHANNEL}
👥 **ɢʀᴏᴜᴘ:** {FORCE_GROUP}
━━━━━━━━━━━━━━━━━━━━

📋 **ɪɴsᴛʀᴜᴄᴛɪᴏɴs:**

1️⃣ ᴄʟɪᴄᴋ ᴛʜᴇ ʙᴜᴛᴛᴏɴs ʙᴇʟᴏᴡ ᴛᴏ ᴊᴏɪɴ
2️⃣ ᴡᴀɪᴛ ғᴏʀ ғᴇᴡ sᴇᴄᴏɴᴅs
3️⃣ ᴄʟɪᴄᴋ "✅ ᴄᴏɴғɪʀᴍ ᴍᴇᴍʙᴇʀsʜɪᴘ"
4️⃣ ʏᴏᴜ'ʟʟ ʙᴇ ʀᴇᴅɪʀᴇᴄᴛᴇᴅ ᴛᴏ ʙᴏᴛ

⚠️ **ɴᴏᴛᴇ:** ʏᴏᴜ ᴍᴜsᴛ ᴊᴏɪɴ ʙᴏᴛʜ ᴄʜᴀɴɴᴇʟ & ɢʀᴏᴜᴘ
🎁 **ʙᴇɴᴇғɪᴛs:** ᴇxᴄʟᴜsɪᴠᴇ ᴄᴏɴᴛᴇɴᴛ & sᴜᴘᴘᴏʀᴛ
    """)

def create_force_join_keyboard():
    """create force join keyboard with buttons"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    # Channel and Group buttons
    markup.add(
        types.InlineKeyboardButton("📢 ᴊᴏɪɴ ᴄʜᴀɴɴᴇʟ", url=f"https://t.me/{FORCE_CHANNEL[1:]}"),
        types.InlineKeyboardButton("👥 ᴊᴏɪɴ ɢʀᴏᴜᴘ", url=f"https://t.me/{FORCE_GROUP[1:]}")
    )
    
    # Refresh/Check membership button
    markup.add(types.InlineKeyboardButton("🔄 ᴄʜᴇᴄᴋ ᴍᴇᴍʙᴇʀsʜɪᴘ", callback_data='check_membership'))
    
    return markup

def mark_user_verified(user_id, verified=True):
    """mark user as verified in database"""
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    c = conn.cursor()
    try:
        c.execute('update users set verified = ? where user_id = ?', 
                 (1 if verified else 0, user_id))
        conn.commit()
    except Exception as e:
        logger.error(f"error marking user verified: {e}")
    finally:
        conn.close()

def is_user_verified(user_id):
    """check if user is verified in database"""
    if user_id in admin_ids:
        return True
    
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    c = conn.cursor()
    try:
        c.execute('select verified from users where user_id = ?', (user_id,))
        result = c.fetchone()
        return result and result[0] == 1
    except Exception as e:
        logger.error(f"error checking user verification: {e}")
        return False
    finally:
        conn.close()

def get_user_folder(user_id):
    """get or create user's folder for storing files"""
    user_folder = os.path.join(UPLOAD_BOTS_DIR, str(user_id))
    os.makedirs(user_folder, exist_ok=True)
    return user_folder

def get_user_file_limit(user_id):
    """get the file upload limit for a user"""
    if user_id == OWNER_ID: return OWNER_LIMIT
    if user_id in admin_ids: return ADMIN_LIMIT
    if is_premium_user(user_id): return PREMIUM_USER_LIMIT
    return FREE_USER_LIMIT

def get_user_file_count(user_id):
    """get the number of files uploaded by a user"""
    return len(user_files.get(user_id, []))

def is_premium_user(user_id):
    """check if user has active subscription"""
    if user_id in user_subscriptions:
        expiry = user_subscriptions[user_id]['expiry']
        return expiry > datetime.now()
    return False

def get_user_status(user_id):
    """get user status with emoji"""
    if user_id == OWNER_ID: return "👑 OWNER"
    if user_id in admin_ids: return "🛡️ ADMIN"
    if is_premium_user(user_id): return "🎯 PREMIUM"
    return "🐢 FREE"

def get_premium_users_details():
    """get detailed information about premium users"""
    premium_users = []
    for user_id in active_users:
        if is_premium_user(user_id):
            try:
                chat = bot.get_chat(user_id)
                user_files_list = user_files.get(user_id, [])
                running_files = sum(1 for file_name, _, _ in user_files_list if is_bot_running(user_id, file_name))
                
                premium_users.append({
                    'user_id': user_id,
                    'first_name': chat.first_name,
                    'username': chat.username,
                    'file_count': len(user_files_list),
                    'running_files': running_files,
                    'expiry': user_subscriptions[user_id]['expiry']
                })
            except Exception as e:
                logger.error(f"error getting user details for {user_id}: {e}")
    
    return premium_users

def generate_subscription_key(days, max_uses):
    """generate subscription key in GALAXY-XXXX-XXXX format"""
    part1 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    part2 = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    key = f"GALAXY-{part1}-{part2}"
    
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute('insert into subscription_keys (key_value, days_valid, max_uses) values (?, ?, ?)',
              (key, days, max_uses))
    conn.commit()
    conn.close()
    
    return key

def redeem_subscription_key(key_value, user_id):
    """redeem subscription key for user"""
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    c = conn.cursor()
    
    try:
        # check if key exists and is valid
        c.execute('select days_valid, max_uses, used_count from subscription_keys where key_value = ?', (key_value,))
        key_data = c.fetchone()
        
        if not key_data:
            return False, "❌ ɪɴᴠᴀʟɪᴅ ᴋᴇʏ! ᴘʟᴇᴀsᴇ ᴇɴᴛᴇʀ ᴀ ᴠᴀʟɪᴅ ɢᴀʟᴀxʏ ᴋᴇʏ."
        
        days_valid, max_uses, used_count = key_data
        
        # check if key usage limit reached
        if used_count >= max_uses:
            return False, "❌ ᴋᴇʏ ᴜsᴀɢᴇ ʟɪᴍɪᴛ ʀᴇᴀᴄʜᴇᴅ! ᴛʜɪs ᴋᴇʏ ʜᴀs ʙᴇᴇɴ ᴜsᴇᴅ ᴛᴏ ᴍᴀxɪᴍᴜᴍ ᴛɪᴍᴇs."
        
        # check if user already used this key
        c.execute('select * from key_usage where key_value = ? and user_id = ?', (key_value, user_id))
        if c.fetchone():
            return False, "❌ ʏᴏᴜ ʜᴀᴠᴇ ᴀʟʀᴇᴀᴅʏ ᴜsᴇᴅ ᴛʜɪs ᴋᴇʏ!"
        
        # calculate new expiry date
        current_expiry = user_subscriptions.get(user_id, {}).get('expiry', datetime.now())
        if current_expiry < datetime.now():
            current_expiry = datetime.now()
        
        new_expiry = current_expiry + timedelta(days=days_valid)
        
        # update subscription
        save_subscription(user_id, new_expiry)
        
        # update key usage
        c.execute('update subscription_keys set used_count = used_count + 1 where key_value = ?', (key_value,))
        c.execute('insert into key_usage (key_value, user_id) values (?, ?)', (key_value, user_id))
        
        # save redemption date
        c.execute('update subscriptions set redeemed_date = current_timestamp where user_id = ?', (user_id,))
        
        conn.commit()
        
        # notify admin about key redemption
        try:
            user_info = bot.get_chat(user_id)
            admin_msg = to_small_caps(f"""
🔔 **ɴᴇᴡ ᴋᴇʏ ʀᴇᴅᴇᴇᴍᴇᴅ!** 🎉

👤 **ᴜsᴇʀ ɪɴғᴏʀᴍᴀᴛɪᴏɴ:**
   ├─ 🤖 **ɪᴅ:** `{user_id}`
   ├─ 👤 **ɴᴀᴍᴇ:** {user_info.first_name}
   ├─ 👁️ **ᴜsᴇʀɴᴀᴍᴇ:** @{user_info.username if user_info.username else 'N/A'}
   └─ 📅 **ᴛɪᴍᴇ:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

🔑 **ᴋᴇʏ ᴅᴇᴛᴀɪʟs:**
   ├─ 🔐 **ᴋᴇʏ:** `{key_value}`
   ├─ 📅 **ᴠᴀʟɪᴅɪᴛʏ:** {days_valid} ᴅᴀʏs
   ├─ 🔢 **ᴍᴀx ᴜsᴇs:** {max_uses}
   └─ 📊 **ᴜsᴇᴅ:** {used_count + 1}/{max_uses}

📈 **sᴜʙsᴄʀɪᴘᴛɪᴏɴ:**
   ├─ 🕐 **sᴛᴀʀᴛ:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
   ├─ 📅 **ᴇxᴘɪʀᴇs:** {new_expiry.strftime('%Y-%m-%d %H:%M:%S')}
   └─ ⏳ **ᴅᴜʀᴀᴛɪᴏɴ:** {days_valid} ᴅᴀʏs

🎊 **ᴀᴄᴄᴇss ᴜᴘɢʀᴀᴅᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ!** 🚀
            """)
            bot.send_message(OWNER_ID, admin_msg, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"failed to notify admin: {e}")
        
        return True, to_small_caps(f"""
🎊 **ᴀᴄᴄᴇss ᴜᴘɢʀᴀᴅᴇᴅ!** 🎉

✅ **sᴜʙsᴄʀɪᴘᴛɪᴏɴ ᴀᴄᴛɪᴠᴀᴛᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ!**

🔑 **sᴜʙsᴄʀɪᴘᴛɪᴏɴ ᴅᴇᴛᴀɪʟs:**
   ├─ 🔐 **ᴋᴇʏ ᴜsᴇᴅ:** `{key_value}`
   ├─ 📅 **ᴠᴀʟɪᴅɪᴛʏ:** {days_valid} ᴅᴀʏs
   ├─ 🕐 **sᴛᴀʀᴛ ᴅᴀᴛᴇ:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
   ├─ 📅 **ᴇxᴘɪʀʏ ᴅᴀᴛᴇ:** {new_expiry.strftime('%Y-%m-%d %H:%M:%S')}
   └─ ⏳ **ᴅᴜʀᴀᴛɪᴏɴ:** {days_valid} ᴅᴀʏs

🌟 **ᴘʀᴇᴍɪᴜᴍ ғᴇᴀᴛᴜʀᴇs ᴜɴʟᴏᴄᴋᴇᴅ:**

   🔓 **ᴜɴʟɪᴍɪᴛᴇᴅ ʜᴏsᴛɪɴɢ**
   ├─ 🎯 ᴜɴʟɪᴍɪᴛᴇᴅ ғɪʟᴇ ʜᴏsᴛɪɴɢ
   ├─ 🔢 ɴᴏ ғɪʟᴇ ʟɪᴍɪᴛs
   └─ 📊 ᴘʀɪᴏʀɪᴛʏ ғɪʟᴇ ʜᴀɴᴅʟɪɴɢ

   ⚡ **ᴘʀᴇᴍɪᴜᴍ sᴜᴘᴘᴏʀᴛ**
   ├─ 🚀 ғᴀsᴛᴇʀ ʀᴇsᴘᴏɴsᴇ ᴛɪᴍᴇs
   ├─ 🔧 ᴇxᴄʟᴜsɪᴠᴇ sᴜᴘᴘᴏʀᴛ
   └─ 🛡️ ᴘʀɪᴏʀɪᴛʏ sᴜᴘᴘᴏʀᴛ

   🔧 **ᴀᴅᴠᴀɴᴄᴇᴅ sᴇᴛᴛɪɴɢs**
   ├─ 🛡️ ɴᴏ ᴀᴅᴍɪɴ ʀᴇsᴛʀɪᴄᴛɪᴏɴs
   ├─ 🔧 ᴇxᴛᴇɴᴅᴇᴅ sᴇᴛᴛɪɴɢs
   └─ ⚙️ ᴄᴜsᴛᴏᴍ sᴛᴏʀᴀɢᴇ

   🔥 **ᴇxᴄʟᴜsɪᴠᴇ ғᴇᴀᴛᴜʀᴇs**
   ├─ 🎯 ᴀᴅᴠᴀɴᴄᴇᴅ ғᴇᴀᴛᴜʀᴇs
   ├─ 🛡️ ᴇᴀʀʟʏ ᴀᴄᴄᴇss ғᴇᴀᴛᴜʀᴇs
   └─ 🎁 ᴄᴜsᴛᴏᴍ ʙᴏᴛ ᴄᴜsᴛᴏᴍɪᴢᴀᴛɪᴏɴ

📋 **ɴᴇxᴛ sᴛᴇᴘs:**
   1. 📁 **ᴜᴘʟᴏᴀᴅ** ʏᴏᴜʀ ғɪʟᴇs
   2. 🚀 **sᴛᴀʀᴛ ʜᴏsᴛɪɴɢ** ʏᴏᴜʀ sᴄʀɪᴘᴛs
   3. ⚡ **ᴇɴᴊᴏʏ** ᴜɴʟɪᴍɪᴛᴇᴅ ᴀᴄᴄᴇss!

🎯 **ɴᴏᴡ ʏᴏᴜ ᴄᴀɴ ʜᴏsᴛ ᴜɴʟɪᴍɪᴛᴇᴅ ғɪʟᴇs ʟɪᴋᴇ ᴀ ᴘʀᴏ!**
   🚀 ʏᴏᴜʀ ᴅɪɢɪᴛᴀʟ ᴊᴏᴜʀɴᴇʏ ᴊᴜsᴛ ɢᴏᴛ ᴜᴘɢʀᴀᴅᴇᴅ!
        """)
    
    except Exception as e:
        return False, f"❌ ᴇʀʀᴏʀ ʀᴇᴅᴇᴇᴍɪɴɢ ᴋᴇʏ: {str(e)}"
    finally:
        conn.close()

def get_all_subscription_keys():
    """get all subscription keys with details"""
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute('select key_value, days_valid, max_uses, used_count, created_date from subscription_keys order by created_date desc')
    keys = c.fetchall()
    conn.close()
    return keys

def delete_subscription_key(key_value):
    """delete subscription key and remove premium status from users"""
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    c = conn.cursor()
    
    # find all users who used this key
    c.execute('select user_id from key_usage where key_value = ?', (key_value,))
    users_affected = c.fetchall()
    
    # remove premium status from affected users
    for (user_id,) in users_affected:
        if user_id in user_subscriptions:
            del user_subscriptions[user_id]
        # remove from active premium users
        c.execute('delete from subscriptions where user_id = ?', (user_id,))
        
        # notify user
        try:
            bot.send_message(user_id, "❌ **ʏᴏᴜʀ ᴘʀᴇᴍɪᴜᴍ ᴀᴄᴄᴇss ʜᴀs ʙᴇᴇɴ ʀᴇᴍᴏᴠᴇᴅ!**\n\n❗ ᴛʜᴇ sᴜʙsᴄʀɪᴘᴛɪᴏɴ ᴋᴇʏ ʏᴏᴜ ᴜsᴇᴅ ʜᴀs ʙᴇᴇɴ ʀᴇᴠᴏᴋᴇᴅ ʙʏ ᴀᴅᴍɪɴ.\n\n📅 ʏᴏᴜʀ ᴘʀᴇᴍɪᴜᴍ ғᴇᴀᴛᴜʀᴇs ᴀʀᴇ ɴᴏ ʟᴏɴɢᴇʀ ᴀᴠᴀɪʟᴀʙʟᴇ. ᴄᴏɴᴛᴀᴄᴛ ᴀᴅᴍɪɴ ғᴏʀ ᴍᴏʀᴇ ɪɴғᴏʀᴍᴀᴛɪᴏɴ.")
        except Exception as e:
            logger.error(f"failed to notify user {user_id}: {e}")
    
    # delete the key
    c.execute('delete from subscription_keys where key_value = ?', (key_value,))
    c.execute('delete from key_usage where key_value = ?', (key_value,))
    conn.commit()
    conn.close()

def update_file_limit(new_limit):
    """update free user file limit"""
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute('insert or replace into bot_settings (setting_key, setting_value) values (?, ?)', 
              ('free_user_limit', str(new_limit)))
    conn.commit()
    conn.close()
    
    global FREE_USER_LIMIT
    FREE_USER_LIMIT = new_limit

def update_force_join_status(enabled):
    """update force join status"""
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute('insert or replace into bot_settings (setting_key, setting_value) values (?, ?)', 
              ('force_join_enabled', '1' if enabled else '0'))
    conn.commit()
    conn.close()
    
    global force_join_enabled
    force_join_enabled = enabled

def get_bot_statistics():
    """get comprehensive bot statistics"""
    total_users = len(active_users)
    total_files = sum(len(files) for files in user_files.values())
    
    # count active files (running scripts)
    active_files = 0
    for script_key in bot_scripts:
        if is_bot_running(int(script_key.split('_')[0]), bot_scripts[script_key]['file_name']):
            active_files += 1
    
    # count premium users
    premium_users = sum(1 for user_id in active_users if is_premium_user(user_id))
    
    return {
        'total_users': total_users,
        'total_files': total_files,
        'active_files': active_files,
        'premium_users': premium_users
    }

def get_all_users_details():
    """get details of all bot users"""
    users_list = []
    for user_id in active_users:
        try:
            chat = bot.get_chat(user_id)
            users_list.append({
                'user_id': user_id,
                'first_name': chat.first_name,
                'username': chat.username,
                'is_premium': is_premium_user(user_id)
            })
        except:
            users_list.append({
                'user_id': user_id,
                'first_name': 'unknown',
                'username': 'unknown',
                'is_premium': is_premium_user(user_id)
            })
    return users_list

def is_bot_running(script_owner_id, file_name):
    """check if a bot script is currently running"""
    script_key = f"{script_owner_id}_{file_name}"
    script_info = bot_scripts.get(script_key)
    if script_info and script_info.get('process'):
        try:
            proc = psutil.Process(script_info['process'].pid)
            return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
        except psutil.NoSuchProcess:
            return False
    return False

def kill_process_tree(process_info):
    """kill a process and all its children"""
    try:
        process = process_info.get('process')
        if process and hasattr(process, 'pid'):
            pid = process.pid
            parent = psutil.Process(pid)
            children = parent.children(recursive=True)
            
            for child in children:
                try:
                    child.kill()
                except psutil.NoSuchProcess:
                    pass
            
            try:
                parent.kill()
                parent.wait(timeout=5)
            except psutil.NoSuchProcess:
                pass
            
            # close log file if exists
            if process_info.get('log_file'):
                try:
                    process_info['log_file'].close()
                except:
                    pass
                
    except Exception as e:
        logger.error(f"error killing process: {e}")

# --- Automatic Package Installation & Script Running ---
TELEGRAM_MODULES = {
    'telebot': 'pyTelegramBotAPI',
    'telegram': 'python-telegram-bot',
    'python_telegram_bot': 'python-telegram-bot',
    'aiogram': 'aiogram',
    'pyrogram': 'pyrogram',
    'telethon': 'telethon',
    'requests': 'requests',
    'bs4': 'beautifulsoup4',
    'pillow': 'Pillow',
    'cv2': 'opencv-python',
    'yaml': 'PyYAML',
    'dotenv': 'python-dotenv',
    'dateutil': 'python-dateutil',
    'pandas': 'pandas',
    'numpy': 'numpy',
    'flask': 'Flask',
    'django': 'Django',
    'sqlalchemy': 'SQLAlchemy',
    'psutil': 'psutil',
    'asyncio': None, 'json': None, 'datetime': None, 'os': None, 'sys': None, 're': None,
    'time': None, 'math': None, 'random': None, 'logging': None, 'threading': None,
    'subprocess': None, 'zipfile': None, 'tempfile': None, 'shutil': None, 'sqlite3': None
}

def attempt_install_pip(module_name, message):
    package_name = TELEGRAM_MODULES.get(module_name.lower(), module_name) 
    if package_name is None: 
        logger.info(f"module '{module_name}' is core. skipping pip install.")
        return False 
    try:
        bot.reply_to(message, f"⚙️ ɪɴsᴛᴀʟʟɪɴɢ `{package_name}`...", parse_mode='Markdown')
        command = [sys.executable, '-m', 'pip', 'install', package_name, '--timeout', '60', '--retries', '3']
        logger.info(f"running install: {' '.join(command)}")
        result = subprocess.run(command, capture_output=True, text=True, check=False, encoding='utf-8', errors='ignore', timeout=120)
        if result.returncode == 0:
            logger.info(f"installed {package_name}. output:\n{result.stdout}")
            bot.reply_to(message, f"✅ sᴜᴄᴄᴇssғᴜʟʟʏ ɪɴsᴛᴀʟʟᴇᴅ `{package_name}`.", parse_mode='Markdown')
            return True
        else:
            error_msg = f"❌ ғᴀɪʟᴇᴅ ᴛᴏ ɪɴsᴛᴀʟʟ `{package_name}`.\nᴇʀʀᴏʀ:\n```\n{result.stderr or result.stdout}\n```"
            logger.error(error_msg)
            if len(error_msg) > 4000: error_msg = error_msg[:4000] + "\n... (ᴇʀʀᴏʀ ᴛʀᴜɴᴄᴀᴛᴇᴅ)"
            bot.reply_to(message, error_msg, parse_mode='Markdown')
            return False
    except subprocess.TimeoutExpired:
        error_msg = f"❌ ᴛɪᴍᴇᴏᴜᴛ ɪɴsᴛᴀʟʟɪɴɢ `{package_name}`. ᴛʀʏ ᴀɢᴀɪɴ ʟᴀᴛᴇʀ."
        logger.error(error_msg)
        bot.reply_to(message, error_msg)
        return False
    except Exception as e:
        error_msg = f"❌ ᴇʀʀᴏʀ ɪɴsᴛᴀʟʟɪɴɢ `{package_name}`: {str(e)}"
        logger.error(error_msg, exc_info=True)
        bot.reply_to(message, error_msg)
        return False

def attempt_install_npm(module_name, user_folder, message):
    try:
        bot.reply_to(message, f"📦 ɪɴsᴛᴀʟʟɪɴɢ ɴᴏᴅᴇ ᴘᴀᴄᴋᴀɢᴇ `{module_name}`...", parse_mode='Markdown')
        command = ['npm', 'install', module_name, '--timeout=60000']
        logger.info(f"running npm install: {' '.join(command)} in {user_folder}")
        result = subprocess.run(command, capture_output=True, text=True, check=False, cwd=user_folder, encoding='utf-8', errors='ignore', timeout=120)
        if result.returncode == 0:
            logger.info(f"installed {module_name}. output:\n{result.stdout}")
            bot.reply_to(message, f"✅ sᴜᴄᴄᴇssғᴜʟʟʏ ɪɴsᴛᴀʟʟᴇᴅ ɴᴏᴅᴇ ᴘᴀᴄᴋᴀɢᴇ `{module_name}`.", parse_mode='Markdown')
            return True
        else:
            error_msg = f"❌ ғᴀɪʟᴇᴅ ᴛᴏ ɪɴsᴛᴀʟʟ ɴᴏᴅᴇ ᴘᴀᴄᴋᴀɢᴇ `{module_name}`.\nᴇʀʀᴏʀ:\n```\n{result.stderr or result.stdout}\n```"
            logger.error(error_msg)
            if len(error_msg) > 4000: error_msg = error_msg[:4000] + "\n... (ᴇʀʀᴏʀ ᴛʀᴜɴᴄᴀᴛᴇᴅ)"
            bot.reply_to(message, error_msg, parse_mode='Markdown')
            return False
    except FileNotFoundError:
         error_msg = "❌ ᴇʀʀᴏʀ: 'npm' ɴᴏᴛ ғᴏᴜɴᴅ. ᴇɴsᴜʀᴇ ɴᴏᴅᴇ.js/npm ɪs ɪɴsᴛᴀʟʟᴇᴅ."
         logger.error(error_msg)
         bot.reply_to(message, error_msg)
         return False
    except subprocess.TimeoutExpired:
        error_msg = f"❌ ᴛɪᴍᴇᴏᴜᴛ ɪɴsᴛᴀʟʟɪɴɢ ɴᴏᴅᴇ ᴘᴀᴄᴋᴀɢᴇ `{module_name}`. ᴛʀʏ ᴀɢᴀɪɴ ʟᴀᴛᴇʀ."
        logger.error(error_msg)
        bot.reply_to(message, error_msg)
        return False
    except Exception as e:
        error_msg = f"❌ ᴇʀʀᴏʀ ɪɴsᴛᴀʟʟɪɴɢ ɴᴏᴅᴇ ᴘᴀᴄᴋᴀɢᴇ `{module_name}`: {str(e)}"
        logger.error(error_msg, exc_info=True)
        bot.reply_to(message, error_msg)
        return False

def run_script(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply, attempt=1):
    """run python script with automatic dependency installation"""
    max_attempts = 2 
    if attempt > max_attempts:
        bot.reply_to(message_obj_for_reply, f"❌ ғᴀɪʟᴇᴅ ᴛᴏ ʀᴜɴ '{file_name}' ᴀғᴛᴇʀ {max_attempts} ᴀᴛᴛᴇᴍᴘᴛs.")
        return

    script_key = f"{script_owner_id}_{file_name}"
    logger.info(f"attempt {attempt} to run python script: {script_path}")

    try:
        if not os.path.exists(script_path):
             bot.reply_to(message_obj_for_reply, f"❌ ᴇʀʀᴏʀ: sᴄʀɪᴘᴛ '{file_name}' ɴᴏᴛ ғᴏᴜɴᴅ!")
             return

        if attempt == 1:
            check_command = [sys.executable, script_path]
            logger.info(f"running python pre-check: {' '.join(check_command)}")
            check_proc = None
            try:
                check_proc = subprocess.Popen(check_command, cwd=user_folder, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore')
                stdout, stderr = check_proc.communicate(timeout=10)
                return_code = check_proc.returncode
                logger.info(f"python pre-check. rc: {return_code}. stderr: {stderr[:200]}...")
                if return_code != 0 and stderr:
                    match_py = re.search(r"ModuleNotFoundError: No module named '(.+?)'", stderr)
                    if match_py:
                        module_name = match_py.group(1).strip().strip("'\"")
                        logger.info(f"detected missing python module: {module_name}")
                        if attempt_install_pip(module_name, message_obj_for_reply):
                            logger.info(f"install ok for {module_name}. retrying run_script...")
                            bot.reply_to(message_obj_for_reply, f"🔧 ɪɴsᴛᴀʟʟ sᴜᴄᴄᴇssғᴜʟ. ʀᴇsᴛᴀʀᴛɪɴɢ '{file_name}'...")
                            time.sleep(2)
                            threading.Thread(target=run_script, args=(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply, attempt + 1)).start()
                            return
                        else:
                            bot.reply_to(message_obj_for_reply, f"❌ ɪɴsᴛᴀʟʟ ғᴀɪʟᴇᴅ. ᴄᴀɴɴᴏᴛ ʀᴜɴ '{file_name}'.")
                            return
            except subprocess.TimeoutExpired:
                logger.info("python pre-check timed out, imports likely ok.")
                if check_proc and check_proc.poll() is None: 
                    check_proc.kill()
                    check_proc.communicate()
            except Exception as e:
                 logger.error(f"error in python pre-check: {e}")
                 return

        logger.info(f"starting python process for {script_key}")
        log_file_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        log_file = None; process = None
        try: 
            log_file = open(log_file_path, 'w', encoding='utf-8', errors='ignore')
        except Exception as e:
             logger.error(f"failed to open log file: {e}")
             bot.reply_to(message_obj_for_reply, f"❌ ғᴀɪʟᴇᴅ ᴛᴏ ᴏᴘᴇɴ ʟᴏɢ ғɪʟᴇ: {e}")
             return
        try:
            startupinfo = None; creationflags = 0
            if os.name == 'nt':
                 startupinfo = subprocess.STARTUPINFO(); startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                 startupinfo.wShowWindow = subprocess.SW_HIDE
            process = subprocess.Popen(
                [sys.executable, script_path], 
                cwd=user_folder, 
                stdout=log_file, 
                stderr=log_file,
                stdin=subprocess.PIPE, 
                startupinfo=startupinfo, 
                creationflags=creationflags,
                encoding='utf-8', 
                errors='ignore',
                bufsize=1
            )
            logger.info(f"started python process {process.pid} for {script_key}")
            bot_scripts[script_key] = {
                'process': process, 
                'log_file': log_file, 
                'file_name': file_name,
                'chat_id': message_obj_for_reply.chat.id,
                'script_owner_id': script_owner_id,
                'start_time': datetime.now(), 
                'user_folder': user_folder, 
                'type': 'py', 
                'script_key': script_key
            }
            bot.reply_to(message_obj_for_reply, f"✅ ʏᴏᴜʀ sᴄʀɪᴘᴛ '{file_name}' sᴛᴀʀᴛᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ! (ᴘɪᴅ: {process.pid})")
        except Exception as e:
            if log_file and not log_file.closed: 
                log_file.close()
            error_msg = f"❌ ᴇʀʀᴏʀ sᴛᴀʀᴛɪɴɢ ʏᴏᴜʀ sᴄʀɪᴘᴛ '{file_name}': {str(e)}"
            logger.error(error_msg, exc_info=True)
            bot.reply_to(message_obj_for_reply, error_msg)
            if script_key in bot_scripts: 
                del bot_scripts[script_key]
    except Exception as e:
        error_msg = f"❌ ᴜɴᴇxᴘᴇᴄᴛᴇᴅ ᴇʀʀᴏʀ ʀᴜɴɴɪɴɢ ʏᴏᴜʀ sᴄʀɪᴘᴛ '{file_name}': {str(e)}"
        logger.error(error_msg, exc_info=True)
        bot.reply_to(message_obj_for_reply, error_msg)

def run_js_script(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply, attempt=1):
    """run js script with automatic dependency installation"""
    max_attempts = 2
    if attempt > max_attempts:
        bot.reply_to(message_obj_for_reply, f"❌ ғᴀɪʟᴇᴅ ᴛᴏ ʀᴜɴ '{file_name}' ᴀғᴛᴇʀ {max_attempts} ᴀᴛᴛᴇᴍᴘᴛs.")
        return

    script_key = f"{script_owner_id}_{file_name}"
    logger.info(f"attempt {attempt} to run js script: {script_path}")

    try:
        if not os.path.exists(script_path):
             bot.reply_to(message_obj_for_reply, f"❌ ᴇʀʀᴏʀ: sᴄʀɪᴘᴛ '{file_name}' ɴᴏᴛ ғᴏᴜɴᴅ!")
             return

        if attempt == 1:
            check_command = ['node', script_path]
            logger.info(f"running js pre-check: {' '.join(check_command)}")
            check_proc = None
            try:
                check_proc = subprocess.Popen(check_command, cwd=user_folder, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore')
                stdout, stderr = check_proc.communicate(timeout=10)
                return_code = check_proc.returncode
                logger.info(f"js pre-check. rc: {return_code}. stderr: {stderr[:200]}...")
                if return_code != 0 and stderr:
                    match_js = re.search(r"Cannot find module '(.+?)'", stderr)
                    if match_js:
                        module_name = match_js.group(1).strip().strip("'\"")
                        if not module_name.startswith('.') and not module_name.startswith('/'):
                             logger.info(f"detected missing node module: {module_name}")
                             if attempt_install_npm(module_name, user_folder, message_obj_for_reply):
                                 logger.info(f"npm install ok for {module_name}. retrying run_js_script...")
                                 bot.reply_to(message_obj_for_reply, f"🔧 ɴᴘᴍ ɪɴsᴛᴀʟʟ sᴜᴄᴄᴇssғᴜʟ. ʀᴇsᴛᴀʀᴛɪɴɢ '{file_name}'...")
                                 time.sleep(2)
                                 threading.Thread(target=run_js_script, args=(script_path, script_owner_id, user_folder, file_name, message_obj_for_reply, attempt + 1)).start()
                                 return
            except subprocess.TimeoutExpired:
                logger.info("js pre-check timed out, imports likely ok.")
                if check_proc and check_proc.poll() is None: 
                    check_proc.kill()
                    check_proc.communicate()
            except Exception as e:
                 logger.error(f"error in js pre-check: {e}")
                 return

        logger.info(f"starting js process for {script_key}")
        log_file_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        log_file = None; process = None
        try: 
            log_file = open(log_file_path, 'w', encoding='utf-8', errors='ignore')
        except Exception as e:
            logger.error(f"failed to open log file: {e}")
            bot.reply_to(message_obj_for_reply, f"❌ ғᴀɪʟᴇᴅ ᴛᴏ ᴏᴘᴇɴ ʟᴏɢ ғɪʟᴇ: {e}")
            return
        try:
            startupinfo = None; creationflags = 0
            if os.name == 'nt':
                 startupinfo = subprocess.STARTUPINFO(); startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                 startupinfo.wShowWindow = subprocess.SW_HIDE
            process = subprocess.Popen(
                ['node', script_path], 
                cwd=user_folder, 
                stdout=log_file, 
                stderr=log_file,
                stdin=subprocess.PIPE, 
                startupinfo=startupinfo, 
                creationflags=creationflags,
                encoding='utf-8', 
                errors='ignore',
                bufsize=1
            )
            logger.info(f"started js process {process.pid} for {script_key}")
            bot_scripts[script_key] = {
                'process': process, 
                'log_file': log_file, 
                'file_name': file_name,
                'chat_id': message_obj_for_reply.chat.id,
                'script_owner_id': script_owner_id,
                'start_time': datetime.now(), 
                'user_folder': user_folder, 
                'type': 'js', 
                'script_key': script_key
            }
            bot.reply_to(message_obj_for_reply, f"✅ ʏᴏᴜʀ ᴊs sᴄʀɪᴘᴛ '{file_name}' sᴛᴀʀᴛᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ! (ᴘɪᴅ: {process.pid})")
        except Exception as e:
            if log_file and not log_file.closed: 
                log_file.close()
            error_msg = f"❌ ᴇʀʀᴏʀ sᴛᴀʀᴛɪɴɢ ʏᴏᴜʀ ᴊs sᴄʀɪᴘᴛ '{file_name}': {str(e)}"
            logger.error(error_msg, exc_info=True)
            bot.reply_to(message_obj_for_reply, error_msg)
            if script_key in bot_scripts: 
                del bot_scripts[script_key]
    except Exception as e:
        error_msg = f"❌ ᴜɴᴇxᴘᴇᴄᴛᴇᴅ ᴇʀʀᴏʀ ʀᴜɴɴɪɴɢ ʏᴏᴜʀ ᴊs sᴄʀɪᴘᴛ '{file_name}': {str(e)}"
        logger.error(error_msg, exc_info=True)
        bot.reply_to(message_obj_for_reply, error_msg)

# --- Database Operations ---
DB_LOCK = threading.Lock()

def save_user(user_id, username, first_name, last_name):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('insert or replace into users (user_id, username, first_name, last_name) values (?, ?, ?, ?)',
                      (user_id, username, first_name, last_name))
            conn.commit()
        except Exception as e:
            logger.error(f"error saving user: {e}")
        finally:
            conn.close()

def save_user_file(user_id, file_name, file_type='unknown', file_path=''):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('insert or replace into user_files (user_id, file_name, file_type, file_path) values (?, ?, ?, ?)',
                      (user_id, file_name, file_type, file_path))
            conn.commit()
            if user_id not in user_files:
                user_files[user_id] = []
            # remove existing file with same name
            user_files[user_id] = [(fn, ft, fp) for fn, ft, fp in user_files[user_id] if fn != file_name]
            user_files[user_id].append((file_name, file_type, file_path))
        except Exception as e:
            logger.error(f"error saving file: {e}")
        finally:
            conn.close()

def remove_user_file_db(user_id, file_name):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('delete from user_files where user_id = ? and file_name = ?', (user_id, file_name))
            conn.commit()
            if user_id in user_files:
                user_files[user_id] = [f for f in user_files[user_id] if f[0] != file_name]
        except Exception as e:
            logger.error(f"error removing file: {e}")
        finally:
            conn.close()

def add_active_user(user_id):
    active_users.add(user_id)
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            c.execute('insert or ignore into active_users (user_id) values (?)', (user_id,))
            conn.commit()
        except Exception as e:
            logger.error(f"error adding active user: {e}")
        finally:
            conn.close()

def save_subscription(user_id, expiry):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        try:
            expiry_str = expiry.isoformat()
            c.execute('insert or replace into subscriptions (user_id, expiry) values (?, ?)', (user_id, expiry_str))
            conn.commit()
            user_subscriptions[user_id] = {'expiry': expiry}
        except Exception as e:
            logger.error(f"error saving subscription: {e}")
        finally:
            conn.close()

# --- Menu Creation ---
def create_main_menu_keyboard(user_id):
    """create main menu keyboard with buttons"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    # base buttons for all users
    buttons = [
        '📤 ᴜᴘʟᴏᴀᴅ ғɪʟᴇ',
        '📁 ᴍᴀɴᴀɢᴇ ғɪʟᴇs', 
        '🔑 ʀᴇᴅᴇᴇᴍ ᴋᴇʏ',
        '💎 ʙᴜʏ sᴜʙsᴄʀɪᴘᴛɪᴏɴ',
        '👤 ᴍʏ ɪɴғᴏ',
        '📊 sᴛᴀᴛᴜs'
    ]
    
    if user_id in admin_ids:
        # add only admin panel button in main menu
        buttons.append('👑 ᴀᴅᴍɪɴ ᴘᴀɴᴇʟ')
    
    # arrange buttons in rows
    for i in range(0, len(buttons), 2):
        if i + 1 < len(buttons):
            markup.row(buttons[i], buttons[i+1])
        else:
            markup.row(buttons[i])
    
    return markup

def create_start_hosting_keyboard():
    """create keyboard with start hosting button (for after file upload)"""
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton('🚀 sᴛᴀʀᴛ ʜᴏsᴛɪɴɢ', callback_data='start_hosting'))
    return markup

def create_manage_files_keyboard(user_id):
    """create inline keyboard for managing files"""
    user_files_list = user_files.get(user_id, [])
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    if not user_files_list:
        markup.add(types.InlineKeyboardButton("📭 ɴᴏ ғɪʟᴇs ғᴏᴜɴᴅ", callback_data='no_files'))
    else:
        for file_name, file_type, file_path in user_files_list:
            is_running = is_bot_running(user_id, file_name)
            status_emoji = "🟢" if is_running else "🔴"
            button_text = f"{status_emoji} {file_name}"
            markup.add(types.InlineKeyboardButton(button_text, callback_data=f'file_{user_id}_{file_name}'))
    
    markup.add(types.InlineKeyboardButton("🔙 ʙᴀᴄᴋ ᴛᴏ ᴍᴀɪɴ", callback_data='back_to_main'))
    return markup

def create_file_management_buttons(user_id, file_name, is_running=True):
    markup = types.InlineKeyboardMarkup(row_width=2)
    if is_running:
        markup.row(
            types.InlineKeyboardButton("⏹️ sᴛᴏᴘ", callback_data=f'stop_{user_id}_{file_name}'),
            types.InlineKeyboardButton("🔄 ʀᴇsᴛᴀʀᴛ", callback_data=f'restart_{user_id}_{file_name}')
        )
    else:
        markup.row(
            types.InlineKeyboardButton("🚀 sᴛᴀʀᴛ", callback_data=f'start_{user_id}_{file_name}'),
        )
    markup.row(
        types.InlineKeyboardButton("🗑️ ᴅᴇʟᴇᴛᴇ", callback_data=f'delete_{user_id}_{file_name}'),
        types.InlineKeyboardButton("📋 ʟᴏɢs", callback_data=f'logs_{user_id}_{file_name}')
    )
    markup.add(types.InlineKeyboardButton("🔙 ʙᴀᴄᴋ ᴛᴏ ғɪʟᴇs", callback_data='manage_files'))
    return markup

def create_admin_panel_keyboard():
    """create admin panel keyboard with all admin buttons"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        '📊 ʙᴏᴛ sᴛᴀᴛɪsᴛɪᴄs',
        '👥 ᴀʟʟ ᴜsᴇʀs',
        '🎯 ᴘʀᴇᴍɪᴜᴍ ᴜsᴇʀs',
        '📢 ʙʀᴏᴀᴅᴄᴀsᴛ',
        '🔑 ɢᴇɴᴇʀᴀᴛᴇ ᴋᴇʏ', 
        '🗑️ ᴅᴇʟᴇᴛᴇ ᴋᴇʏ',
        '🔢 ᴛᴏᴛᴀʟ ᴋᴇʏs',
        '📈 ғɪʟᴇ ʟɪᴍɪᴛ',
        '⚙️ ʙᴏᴛ sᴇᴛᴛɪɴɢs',
        '🔙 ʙᴀᴄᴋ ᴛᴏ ᴍᴀɪɴ'
    ]
    
    for i in range(0, len(buttons), 2):
        if i + 1 < len(buttons):
            markup.row(buttons[i], buttons[i+1])
        else:
            markup.row(buttons[i])
    
    return markup

# --- Command Handlers ---
@bot.message_handler(commands=['start', 'help'])
def command_send_welcome(message):
    user_id = message.from_user.id
    
    # check if bot is locked
    if bot_locked and user_id not in admin_ids:
        bot.send_message(message.chat.id, 
                        to_small_caps("""
🔒 *ʙᴏᴛ ɪs ᴜɴᴅᴇʀ ᴍᴀɪɴᴛᴇɴᴀɴᴄᴇ*

❗ ᴛʜɪs ʙᴏᴛ ɪs ᴄᴜʀʀᴇɴᴛʟʏ ᴜɴᴅᴇʀ ᴍᴀɪɴᴛᴇɴᴀɴᴄᴇ ᴍᴏᴅᴇ.
📅 ᴘʟᴇᴀsᴇ ᴛʀʏ ᴀɢᴀɪɴ ʟᴀᴛᴇʀ.

👑 *ᴄᴏɴᴛᴀᴄᴛ ᴏᴡɴᴇʀ:* @GALAXYxIGL
📞 ғᴏʀ ᴀɴʏ ᴜʀɢᴇɴᴛ ǫᴜᴇʀɪᴇs ᴏʀ sᴜᴘᴘᴏʀᴛ
                        """),
                        parse_mode='Markdown')
        return
    
    # Check force join for non-admin users
    if force_join_enabled and user_id not in admin_ids and not check_force_join(user_id):
        force_message = create_force_join_message()
        force_markup = create_force_join_keyboard()
        bot.send_message(message.chat.id, force_message, reply_markup=force_markup, parse_mode='Markdown')
        return
    
    # user is verified or admin, show main menu
    add_active_user(user_id)
    save_user(user_id, message.from_user.username, message.from_user.first_name, message.from_user.last_name)
    
    welcome_text = to_small_caps(f"""
🎊 *ᴡᴇʟᴄᴏᴍᴇ ᴛᴏ ɢᴀʟᴀxʏ ғɪʟᴇ ʜᴏsᴛ ʙᴏᴛ* 🎊

👋 ʜᴇʟʟᴏ {message.from_user.first_name}!

🌟 *ᴘʀᴇᴍɪᴜᴍ ғɪʟᴇ ʜᴏsᴛɪɴɢ sᴇʀᴠɪᴄᴇ*
✅ ғᴜʟʟ ᴀᴄᴄᴇss ᴘʀᴇᴍɪᴜᴍ

📋 *ᴀᴠᴀɪʟᴀʙʟᴇ ғᴇᴀᴛᴜʀᴇs:*
• 📁 ғʀᴇᴇ ʜᴏsᴛɪɴɢ: {FREE_USER_LIMIT} ғɪʟᴇs
• 🎯 ᴘʀᴇᴍɪᴜᴍ: ᴜɴʟɪᴍɪᴛᴇᴅ ғɪʟᴇs  
• 📤 ғɪʟᴇ ᴜᴘʟᴏᴀᴅ + ᴀᴜᴛᴏ ʜᴏsᴛɪɴɢ
• ⚡ ᴀᴜᴛᴏ ᴅᴇᴘᴇɴᴅᴇɴᴄʏ ɪɴsᴛᴀʟʟᴀᴛɪᴏɴ
• 📊 ғɪʟᴇ ᴍᴀɴᴀɢᴇᴍᴇɴᴛ sʏsᴛᴇᴍ
• 🔧 30+ ғɪʟᴇ ғᴏʀᴍᴀᴛs sᴜᴘᴘᴏʀᴛᴇᴅ

💎 *ᴘʀᴇᴍɪᴜᴍ ᴘʟᴀɴs:*
• 7 ᴅᴀʏs: $2.99
• 30 ᴅᴀʏs: $9.99  
• 90 ᴅᴀʏs: $24.99
• ʟɪғᴇᴛɪᴍᴇ: $49.99

🛠️ *sᴜᴘᴘᴏʀᴛᴇᴅ ғɪʟᴇs:* ᴘʏᴛʜᴏɴ, ᴊᴀᴠᴀsᴄʀɪᴘᴛ, ʜᴛᴍʟ, ᴄss, ᴛxᴛ, ᴊsᴏɴ, ᴘʜᴘ, ᴄ, ᴄ++, ᴄ#, ʀᴜʙʏ, ɢᴏ, ʀᴜsᴛ ᴀɴᴅ 20+ ᴍᴏʀᴇ!

👑 *ᴏᴡɴᴇʀ:* @GALAXYxIGL

📊 *ʏᴏᴜʀ sᴛᴀᴛᴜs:* {get_user_status(user_id)}
📁 *ғɪʟᴇs ᴜᴘʟᴏᴀᴅᴇᴅ:* {get_user_file_count(user_id)}/{get_user_file_limit(user_id) if get_user_file_limit(user_id) != float('inf') else 'ᴜɴʟɪᴍɪᴛᴇᴅ'}

👉 *ᴜsᴇ ʙᴜᴛᴛᴏɴs ʙᴇʟᴏᴡ ᴛᴏ ɴᴀᴠɪɢᴀᴛᴇ!*
    """)
    
    markup = create_main_menu_keyboard(user_id)
    bot.send_message(message.chat.id, welcome_text, reply_markup=markup, parse_mode='Markdown')

# --- Text Message Handlers ---
@bot.message_handler(func=lambda message: True)
def handle_text_messages(message):
    user_id = message.from_user.id
    
    # check if bot is locked for non-admin users
    if bot_locked and user_id not in admin_ids:
        bot.send_message(message.chat.id, 
                        to_small_caps("""
🔒 *ʙᴏᴛ ɪs ᴜɴᴅᴇʀ ᴍᴀɪɴᴛᴇɴᴀɴᴄᴇ*

❗ ᴛʜɪs ʙᴏᴛ ɪs ᴄᴜʀʀᴇɴᴛʟʏ ᴜɴᴅᴇʀ ᴍᴀɪɴᴛᴇɴᴀɴᴄᴇ ᴍᴏᴅᴇ.
📅 ᴘʟᴇᴀsᴇ ᴛʀʏ ᴀɢᴀɪɴ ʟᴀᴛᴇʀ.

👑 *ᴄᴏɴᴛᴀᴄᴛ ᴏᴡɴᴇʀ:* @GALAXYxIGL
📞 ғᴏʀ ᴀɴʏ ᴜʀɢᴇɴᴛ ǫᴜᴇʀɪᴇs ᴏʀ sᴜᴘᴘᴏʀᴛ
                        """),
                        parse_mode='Markdown')
        return
    
    # Check force join for non-admin users
    if force_join_enabled and user_id not in admin_ids and not check_force_join(user_id):
        force_message = create_force_join_message()
        force_markup = create_force_join_keyboard()
        bot.send_message(message.chat.id, force_message, reply_markup=force_markup, parse_mode='Markdown')
        return
    
    text = message.text
    
    if text == '📤 ᴜᴘʟᴏᴀᴅ ғɪʟᴇ':
        handle_upload_file_text(message)
    elif text == '📁 ᴍᴀɴᴀɢᴇ ғɪʟᴇs':
        handle_manage_files_text(message)
    elif text == '🔑 ʀᴇᴅᴇᴇᴍ ᴋᴇʏ':
        handle_redeem_key_text(message)
    elif text == '💎 ʙᴜʏ sᴜʙsᴄʀɪᴘᴛɪᴏɴ':
        handle_buy_subscription_text(message)
    elif text == '👤 ᴍʏ ɪɴғᴏ':
        handle_my_info_text(message)
    elif text == '📊 sᴛᴀᴛᴜs':
        handle_status_text(message)
    elif text == '👑 ᴀᴅᴍɪɴ ᴘᴀɴᴇʟ' and user_id in admin_ids:
        handle_admin_panel_text(message)
    elif text == '📊 ʙᴏᴛ sᴛᴀᴛɪsᴛɪᴄs' and user_id in admin_ids:
        handle_bot_statistics_text(message)
    elif text == '👥 ᴀʟʟ ᴜsᴇʀs' and user_id in admin_ids:
        handle_all_users_text(message)
    elif text == '🎯 ᴘʀᴇᴍɪᴜᴍ ᴜsᴇʀs' and user_id in admin_ids:
        handle_premium_users_text(message)
    elif text == '📢 ʙʀᴏᴀᴅᴄᴀsᴛ' and user_id in admin_ids:
        handle_broadcast_text(message)
    elif text == '🔑 ɢᴇɴᴇʀᴀᴛᴇ ᴋᴇʏ' and user_id in admin_ids:
        handle_generate_key_text(message)
    elif text == '🗑️ ᴅᴇʟᴇᴛᴇ ᴋᴇʏ' and user_id in admin_ids:
        handle_delete_key_text(message)
    elif text == '🔢 ᴛᴏᴛᴀʟ ᴋᴇʏs' and user_id in admin_ids:
        handle_total_keys_text(message)
    elif text == '📈 ғɪʟᴇ ʟɪᴍɪᴛ' and user_id in admin_ids:
        handle_file_limit_text(message)
    elif text == '⚙️ ʙᴏᴛ sᴇᴛᴛɪɴɢs' and user_id in admin_ids:
        handle_bot_settings_text(message)
    elif text == '🔙 ʙᴀᴄᴋ ᴛᴏ ᴍᴀɪɴ':
        handle_back_to_main_text(message)
    else:
        bot.send_message(message.chat.id, "❌ ɪɴᴠᴀʟɪᴅ ᴄᴏᴍᴍᴀɴᴅ! ᴜsᴇ ᴛʜᴇ ʙᴜᴛᴛᴏɴs ʙᴇʟᴏᴡ.")

def handle_upload_file_text(message):
    user_id = message.from_user.id
    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    
    if current_files >= file_limit and not is_premium_user(user_id):
        bot.send_message(message.chat.id, f"❌ ғɪʟᴇ ʟɪᴍɪᴛ ʀᴇᴀᴄʜᴇᴅ! ғʀᴇᴇ ᴜsᴇʀs ᴄᴀɴ ᴏɴʟʏ ʜᴏsᴛ {FREE_USER_LIMIT} ғɪʟᴇs. ᴜᴘɢʀᴀᴅᴇ ᴛᴏ ᴘʀᴇᴍɪᴜᴍ ғᴏʀ ᴜɴʟɪᴍɪᴛᴇᴅ ʜᴏsᴛɪɴɢ.")
        return
    
    supported_files = ", ".join([ext for ext in SUPPORTED_EXTENSIONS.keys()])
    bot.send_message(message.chat.id, 
                    to_small_caps(f"""
📤 **ᴜᴘʟᴏᴀᴅ ʏᴏᴜʀ ғɪʟᴇ**

sᴜᴘᴘᴏʀᴛᴇᴅ ғᴏʀᴍᴀᴛs: `{supported_files}`

ᴜᴘʟᴏᴀᴅ ʏᴏᴜʀ ғɪʟᴇ ɴᴏᴡ, ᴛʜᴇɴ ᴄʟɪᴄᴋ '🚀 sᴛᴀʀᴛ ʜᴏsᴛɪɴɢ' ᴛᴏ ʀᴜɴ ɪᴛ!
✅ ᴀᴜᴛᴏ ᴅᴇᴘᴇɴᴅᴇɴᴄʏ ɪɴsᴛᴀʟʟᴀᴛɪᴏɴ
✅ ᴀᴜᴛᴏ sᴛᴀʀᴛ ʜᴏsᴛɪɴɢ
                    """),
                    parse_mode='Markdown')

def handle_manage_files_text(message):
    user_id = message.from_user.id
    user_files_list = user_files.get(user_id, [])
    
    if not user_files_list:
        bot.send_message(message.chat.id, "📭 ɴᴏ ғɪʟᴇs ᴜᴘʟᴏᴀᴅᴇᴅ ʏᴇᴛ!")
        return
    
    files_text = to_small_caps("📁 **ʏᴏᴜʀ ᴜᴘʟᴏᴀᴅᴇᴅ ғɪʟᴇs:**\n\n")
    
    for file_name, file_type, file_path in user_files_list:
        is_running = is_bot_running(user_id, file_name)
        status = "🟢 ʀᴜɴɴɪɴɢ" if is_running else "🔴 sᴛᴏᴘᴘᴇᴅ"
        files_text += f"• `{file_name}` ({file_type}) - {status}\n"
    
    files_text += "\nᴄʟɪᴄᴋ ᴏɴ ᴀ ғɪʟᴇ ʙᴇʟᴏᴡ ᴛᴏ ᴍᴀɴᴀɢᴇ ɪᴛ:"
    
    markup = create_manage_files_keyboard(user_id)
    bot.send_message(message.chat.id, files_text, reply_markup=markup, parse_mode='Markdown')

def handle_redeem_key_text(message):
    msg = bot.send_message(message.chat.id, "🔑 ᴇɴᴛᴇʀ ʏᴏᴜʀ sᴜʙsᴄʀɪᴘᴛɪᴏɴ ᴋᴇʏ (ғᴏʀᴍᴀᴛ: GALAXY-XXXX-XXXX):")
    bot.register_next_step_handler(msg, process_redeem_key)

def handle_buy_subscription_text(message):
    plans_text = to_small_caps(f"""
💎 **ᴘʀᴇᴍɪᴜᴍ sᴜʙsᴄʀɪᴘᴛɪᴏɴ ᴘʟᴀɴs**

• 🟢 7 ᴅᴀʏs: $2.99
  - ᴜɴʟɪᴍɪᴛᴇᴅ ғɪʟᴇ ʜᴏsᴛɪɴɢ
  - ᴘʀᴇᴍɪᴜᴍ sᴜᴘᴘᴏʀᴛ
  - ɴᴏ ᴀᴅᴍɪɴ ʀᴇsᴛʀɪᴄᴛɪᴏɴs
  - ғᴀsᴛᴇʀ ᴜᴘʟᴏᴀᴅs
  
• 🔵 30 ᴅᴀʏs: $9.99
  - ᴀʟʟ 7-ᴅᴀʏ ғᴇᴀᴛᴜʀᴇs
  - ᴀᴅᴠᴀɴᴄᴇᴅ ғᴇᴀᴛᴜʀᴇs
  - ᴇᴀʀʟʏ ᴀᴄᴄᴇss ᴛᴏ ɴᴇᴡ ғᴇᴀᴛᴜʀᴇs
  - ᴘʀɪᴏʀɪᴛʏ sᴜᴘᴘᴏʀᴛ
  
• 🟣 90 ᴅᴀʏs: $24.99
  - ᴀʟʟ 30-ᴅᴀʏ ғᴇᴀᴛᴜʀᴇs
  - ᴇxᴄʟᴜsɪᴠᴇ sᴜᴘᴘᴏʀᴛ
  - ᴄᴜsᴛᴏᴍ ʙᴏᴛ ᴄᴜsᴛᴏᴍɪᴢᴀᴛɪᴏɴ
  - ᴘʀɪᴏʀɪᴛʏ sᴛᴏʀᴀɢᴇ
  
• 🟡 ʟɪғᴇᴛɪᴍᴇ: $49.99
  - ᴀʟʟ ғᴇᴀᴛᴜʀᴇs ғᴏʀᴇᴠᴇʀ
  - ʟɪғᴇᴛɪᴍᴇ ᴜᴘᴅᴀᴛᴇs
  - ᴠɪᴘ sᴜᴘᴘᴏʀᴛ
  - ᴘʀᴇᴍɪᴜᴍ sᴇʀᴠᴇʀ ᴀᴄᴄᴇss

💳 **ᴄᴏɴᴛᴀᴄᴛ @GALAXYxIGL ᴛᴏ ᴘᴜʀᴄʜᴀsᴇ!**

ᴘᴀʏᴍᴇɴᴛ ᴍᴇᴛʜᴏᴅs: ᴘʏᴍᴇɴᴛʜᴏɴ, ᴄʀʏᴘᴛᴏ, ᴜᴘɪ, ᴡᴀʟʟᴇᴛ ᴏʀ ᴀɴʏ ᴅɪɢɪᴛᴀʟ ᴘᴀʏᴍᴇɴᴛ
    """)
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💳 ᴄᴏɴᴛᴀᴄᴛ ᴏᴡɴᴇʀ", url="https://t.me/GALAXYxIGL"))
    markup.add(types.InlineKeyboardButton("🔑 ʀᴇᴅᴇᴇᴍ ᴋᴇʏ", callback_data='redeem_key'))
    
    bot.send_message(message.chat.id, plans_text, reply_markup=markup, parse_mode='Markdown')

def handle_admin_panel_text(message):
    if message.from_user.id not in admin_ids:
        bot.send_message(message.chat.id, "❌ ᴀᴅᴍɪɴ ᴀᴄᴄᴇss ʀᴇǫᴜɪʀᴇᴅ!")
        return
    
    admin_text = to_small_caps("👑 **ɢᴀʟᴀxʏ ᴀᴅᴍɪɴ ᴘᴀɴᴇʟ**\n\nsᴇʟᴇᴄᴛ ᴀɴ ᴏᴘᴛɪᴏɴ ғʀᴏᴍ ʙᴜᴛᴛᴏɴs:")
    markup = create_admin_panel_keyboard()
    bot.send_message(message.chat.id, admin_text, reply_markup=markup, parse_mode='Markdown')

def handle_bot_statistics_text(message):
    if message.from_user.id not in admin_ids:
        bot.send_message(message.chat.id, "❌ ᴀᴅᴍɪɴ ᴀᴄᴄᴇss ʀᴇǫᴜɪʀᴇᴅ!")
        return
    
    stats = get_bot_statistics()
    stats_text = to_small_caps(f"""
📊 **ɢᴀʟᴀxʏ ʙᴏᴛ sᴛᴀᴛɪsᴛɪᴄs**

👥 ᴛᴏᴛᴀʟ ᴜsᴇʀs: `{stats['total_users']}`
🎯 ᴘʀᴇᴍɪᴜᴍ ᴜsᴇʀs: `{stats['premium_users']}`
📁 ᴛᴏᴛᴀʟ ғɪʟᴇs: `{stats['total_files']}`
🟢 ᴀᴄᴛɪᴠᴇ ғɪʟᴇs: `{stats['active_files']}`
🔴 ɪɴᴀᴄᴛɪᴠᴇ ғɪʟᴇs: `{stats['total_files'] - stats['active_files']}`

📈 sʏsᴛᴇᴍ sᴛᴀᴛᴜs: 🟢 ᴏɴʟɪɴᴇ
🔧 ʙᴏᴛ sᴛᴀᴛᴜs: {'🔒 ʟᴏᴄᴋᴇᴅ' if bot_locked else '🔓 ᴜɴʟᴏᴄᴋᴇᴅ'}
📈 ғʀᴇᴇ ᴜsᴇʀ ʟɪᴍɪᴛ: {FREE_USER_LIMIT} ғɪʟᴇs
🔒 ғᴏʀᴄᴇ ᴊᴏɪɴ: {'✅ ᴇɴᴀʙʟᴇᴅ' if force_join_enabled else '❌ ᴅɪsᴀʙʟᴇᴅ'}
    """)
    
    bot.send_message(message.chat.id, stats_text, parse_mode='Markdown')

def handle_premium_users_text(message):
    if message.from_user.id not in admin_ids:
        bot.send_message(message.chat.id, "❌ ᴀᴅᴍɪɴ ᴀᴄᴄᴇss ʀᴇǫᴜɪʀᴇᴅ!")
        return
    
    premium_users = get_premium_users_details()
    if not premium_users:
        bot.send_message(message.chat.id, "❌ ɴᴏ ᴘʀᴇᴍɪᴜᴍ ᴜsᴇʀs ғᴏᴜɴᴅ!")
        return
    
    premium_text = to_small_caps("🎯 **ᴘʀᴇᴍɪᴜᴍ ᴜsᴇʀs ᴅᴇᴛᴀɪʟs**\n\n")
    
    for user in premium_users:
        days_left = (user['expiry'] - datetime.now()).days
        premium_text += f"""
👤 **ᴜsᴇʀ:** {user['first_name']} (@{user['username']})
🤖 **ɪᴅ:** `{user['user_id']}`
📁 **ғɪʟᴇs:** {user['file_count']} (🟢 {user['running_files']} ʀᴜɴɴɪɴɢ)
📅 **ᴇxᴘɪʀᴇs:** {user['expiry'].strftime('%Y-%m-%d')}
⏳ **ᴅᴀʏs ʟᴇғᴛ:** {days_left} ᴅᴀʏs
────────────────────
        """
    
    bot.send_message(message.chat.id, premium_text, parse_mode='Markdown')

def handle_broadcast_text(message):
    if message.from_user.id not in admin_ids:
        bot.send_message(message.chat.id, "❌ ᴀᴅᴍɪɴ ᴀᴄᴄᴇss ʀᴇǫᴜɪʀᴇᴅ!")
        return
    
    msg = bot.send_message(message.chat.id, "📢 ᴇɴᴛᴇʀ ʙʀᴏᴀᴅᴄᴀsᴛ ᴍᴇssᴀɢᴇ:")
    bot.register_next_step_handler(msg, process_broadcast_message)

def process_broadcast_message(message):
    broadcast_text = message.text
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✅ ᴄᴏɴғɪʀᴍ ʙʀᴏᴀᴅᴄᴀsᴛ", callback_data=f'confirm_broadcast_{message.message_id}'),
        types.InlineKeyboardButton("❌ ᴄᴀɴᴄᴇʟ", callback_data='cancel_broadcast')
    )
    
    bot.send_message(message.chat.id, 
                    to_small_caps(f"📢 **ʙʀᴏᴀᴅᴄᴀsᴛ ᴘʀᴇᴠɪᴇᴡ:**\n\n{broadcast_text}\n\nᴄᴏɴғɪʀᴍ sᴇɴᴅɪɴɢ ᴛᴏ ᴀʟʟ ᴜsᴇʀs?"),
                    reply_markup=markup, parse_mode='Markdown')

def handle_generate_key_text(message):
    if message.from_user.id not in admin_ids:
        bot.send_message(message.chat.id, "❌ ᴀᴅᴍɪɴ ᴀᴄᴄᴇss ʀᴇǫᴜɪʀᴇᴅ!")
        return
    
    msg = bot.send_message(message.chat.id, "🔑 ᴇɴᴛᴇʀ ᴅᴀʏs ᴠᴀʟɪᴅɪᴛʏ:")
    bot.register_next_step_handler(msg, process_generate_key_days)

def process_generate_key_days(message):
    try:
        days = int(message.text.strip())
        if days <= 0:
            bot.send_message(message.chat.id, "❌ ᴅᴀʏs ᴍᴜsᴛ ʙᴇ ᴘᴏsɪᴛɪᴠᴇ ɴᴜᴍʙᴇʀ!")
            return
        
        # store days in user data and ask for max uses
        bot.send_message(message.chat.id, f"✅ ᴅᴀʏs sᴇᴛ ᴛᴏ: {days}\n\nɴᴏᴡ ᴇɴᴛᴇʀ ᴍᴀxɪᴍᴜᴍ ᴜsᴇs:")
        bot.register_next_step_handler(message, process_generate_key_uses, days)
        
    except ValueError:
        bot.send_message(message.chat.id, "❌ ᴘʟᴇᴀsᴇ ᴇɴᴛᴇʀ ᴀ ᴠᴀʟɪᴅ ɴᴜᴍʙᴇʀ!")

def process_generate_key_uses(message, days):
    try:
        max_uses = int(message.text.strip())
        if max_uses <= 0:
            bot.send_message(message.chat.id, "❌ ᴍᴀx ᴜsᴇs ᴍᴜsᴛ ʙᴇ ᴘᴏsɪᴛɪᴠᴇ ɴᴜᴍʙᴇʀ!")
            return
        
        # generate the key
        key = generate_subscription_key(days, max_uses)
        bot.send_message(message.chat.id, 
                        f"""
✅ **ᴋᴇʏ ɢᴇɴᴇʀᴀᴛᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ!**

🔑 **ᴋᴇʏ:** `{key}`
📅 **ᴅᴀʏs:** {days}
🔢 **ᴍᴀx ᴜsᴇs:** {max_uses}

ᴜsᴇʀs ᴄᴀɴ ʀᴇᴅᴇᴇᴍ ᴛʜɪs ᴋᴇʏ ᴜsɪɴɢ 🔑 ʀᴇᴅᴇᴇᴍ ᴋᴇʏ ʙᴜᴛᴛᴏɴ.
                        """,
                        parse_mode='Markdown')
        
    except ValueError:
        bot.send_message(message.chat.id, "❌ ᴘʟᴇᴀsᴇ ᴇɴᴛᴇʀ ᴀ ᴠᴀʟɪᴅ ɴᴜᴍʙᴇʀ!")
def handle_delete_key_text(message):
    if message.from_user.id not in admin_ids:
        bot.send_message(message.chat.id, "❌ ᴀᴅᴍɪɴ ᴀᴄᴄᴇss ʀᴇǫᴜɪʀᴇᴅ!")
        return
    
    keys = get_all_subscription_keys()
    if not keys:
        bot.send_message(message.chat.id, "❌ ɴᴏ ᴀᴄᴛɪᴠᴇ ᴋᴇʏs ғᴏᴜɴᴅ!")
        return
    
    keys_text = to_small_caps("🗑️ **ᴀᴄᴛɪᴠᴇ sᴜʙsᴄʀɪᴘᴛɪᴏɴ ᴋᴇʏs:**\n\n")
    for key in keys:
        keys_text += f"• `{key[0]}` - {key[1]} ᴅᴀʏs, {key[3]}/{key[2]} ᴜsᴇs\n"
    
    keys_text += "\nᴇɴᴛᴇʀ ᴛʜᴇ ᴋᴇʏ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴅᴇʟᴇᴛᴇ:"
    bot.send_message(message.chat.id, keys_text, parse_mode='Markdown')
    
    msg = bot.send_message(message.chat.id, "🔑 ᴇɴᴛᴇʀ ᴋᴇʏ ᴛᴏ ᴅᴇʟᴇᴛᴇ:")
    bot.register_next_step_handler(msg, process_delete_key)

def process_delete_key(message):
    key_value = message.text.strip().upper()
    
    # check if key exists
    keys = get_all_subscription_keys()
    key_exists = any(key[0] == key_value for key in keys)
    
    if not key_exists:
        bot.send_message(message.chat.id, f"❌ ᴋᴇʏ `{key_value}` ɴᴏᴛ ғᴏᴜɴᴅ!")
        return
    
    delete_subscription_key(key_value)
    bot.send_message(message.chat.id, f"✅ ᴋᴇʏ `{key_value}` ᴅᴇʟᴇᴛᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ!", parse_mode='Markdown')

def handle_total_keys_text(message):
    if message.from_user.id not in admin_ids:
        bot.send_message(message.chat.id, "❌ ᴀᴅᴍɪɴ ᴀᴄᴄᴇss ʀᴇǫᴜɪʀᴇᴅ!")
        return
    
    keys = get_all_subscription_keys()
    if not keys:
        bot.send_message(message.chat.id, "❌ ɴᴏ ᴋᴇʏs ғᴏᴜɴᴅ!")
        return
    
    keys_text = to_small_caps("🔢 **ᴀʟʟ sᴜʙsᴄʀɪᴘᴛɪᴏɴ ᴋᴇʏs:**\n\n")
    for key in keys:
        keys_text += f"• `{key[0]}`\n  📅 ᴅᴀʏs: {key[1]}, 🔢 ᴜsᴇs: {key[3]}/{key[2]}\n  🕐 ᴄʀᴇᴀᴛᴇᴅ: {key[4][:16]}\n\n"
    
    bot.send_message(message.chat.id, keys_text, parse_mode='Markdown')

def handle_file_limit_text(message):
    if message.from_user.id not in admin_ids:
        bot.send_message(message.chat.id, "❌ ᴀᴅᴍɪɴ ᴀᴄᴄᴇss ʀᴇǫᴜɪʀᴇᴅ!")
        return
    
    current_limit = FREE_USER_LIMIT
    msg = bot.send_message(message.chat.id, f"📈 ᴄᴜʀʀᴇɴᴛ ғʀᴇᴇ ᴜsᴇʀ ʟɪᴍɪᴛ: {current_limit} ғɪʟᴇs\n\nᴇɴᴛᴇʀ ɴᴇᴡ ʟɪᴍɪᴛ (1-100):")
    bot.register_next_step_handler(msg, process_file_limit)

def process_file_limit(message):
    try:
        new_limit = int(message.text.strip())
        if 1 <= new_limit <= 100:
            update_file_limit(new_limit)
            bot.send_message(message.chat.id, f"✅ ғʀᴇᴇ ᴜsᴇʀ ғɪʟᴇ ʟɪᴍɪᴛ ᴜᴘᴅᴀᴛᴇᴅ ᴛᴏ: {new_limit} ғɪʟᴇs")
        else:
            bot.send_message(message.chat.id, "❌ ʟɪᴍɪᴛ ᴍᴜsᴛ ʙᴇ ʙᴇᴛᴡᴇᴇɴ 1 ᴀɴᴅ 100!")
    except ValueError:
        bot.send_message(message.chat.id, "❌ ᴘʟᴇᴀsᴇ ᴇɴᴛᴇʀ ᴀ ᴠᴀʟɪᴅ ɴᴜᴍʙᴇʀ!")

def handle_bot_settings_text(message):
    if message.from_user.id not in admin_ids:
        bot.send_message(message.chat.id, "❌ ᴀᴅᴍɪɴ ᴀᴄᴄᴇss ʀᴇǫᴜɪʀᴇᴅ!")
        return
    
    settings_text = to_small_caps(f"""
⚙️ **ʙᴏᴛ sᴇᴛᴛɪɴɢs**

🔧 **ʙᴏᴛ sᴛᴀᴛᴜs:** {'🔒 ʟᴏᴄᴋᴇᴅ' if bot_locked else '🔓 ᴜɴʟᴏᴄᴋᴇᴅ'}
📁 **ᴜᴘʟᴏᴀᴅ ᴅɪʀ:** `{UPLOAD_BOTS_DIR}`
🗄️ **ᴅᴀᴛᴀʙᴀsᴇ:** `{DATABASE_PATH}`
👑 **ᴏᴡɴᴇʀ ɪᴅ:** `{OWNER_ID}`
🛡️ **ᴀᴅᴍɪɴ ɪᴅ:** `{ADMIN_ID}`

**ʟɪᴍɪᴛs:**
• 🐢 ғʀᴇᴇ ᴜsᴇʀs: {FREE_USER_LIMIT} ғɪʟᴇ
• 🎯 ᴘʀᴇᴍɪᴜᴍ ᴜsᴇʀs: {PREMIUM_USER_LIMIT} ғɪʟᴇs
• 🛡️ ᴀᴅᴍɪɴs: {ADMIN_LIMIT} ғɪʟᴇs
• 👑 ᴏᴡɴᴇʀ: ᴜɴʟɪᴍɪᴛᴇᴅ

**sᴜᴘᴘᴏʀᴛᴇᴅ ғɪʟᴇs:** {len(SUPPORTED_EXTENSIONS)} ғᴏʀᴍᴀᴛs
🔒 **ғᴏʀᴄᴇ ᴊᴏɪɴ:** {'✅ ᴇɴᴀʙʟᴇᴅ' if force_join_enabled else '❌ ᴅɪsᴀʙʟᴇᴅ'}
📢 **ᴄʜᴀɴɴᴇʟ:** {FORCE_CHANNEL}
👥 **ɢʀᴏᴜᴘ:** {FORCE_GROUP}
    """)
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    if bot_locked:
        markup.add(types.InlineKeyboardButton("🔓 ᴜɴʟᴏᴄᴋ ʙᴏᴛ", callback_data='unlock_bot'))
    else:
        markup.add(types.InlineKeyboardButton("🔒 ʟᴏᴄᴋ ʙᴏᴛ", callback_data='lock_bot'))
    
    if force_join_enabled:
        markup.add(types.InlineKeyboardButton("❌ ᴅɪsᴀʙʟᴇ ғᴏʀᴄᴇ ᴊᴏɪɴ", callback_data='disable_force_join'))
    else:
        markup.add(types.InlineKeyboardButton("✅ ᴇɴᴀʙʟᴇ ғᴏʀᴄᴇ ᴊᴏɪɴ", callback_data='enable_force_join'))
    
    bot.send_message(message.chat.id, settings_text, reply_markup=markup, parse_mode='Markdown')

def handle_all_users_text(message):
    if message.from_user.id not in admin_ids:
        bot.send_message(message.chat.id, "❌ ᴀᴅᴍɪɴ ᴀᴄᴄᴇss ʀᴇǫᴜɪʀᴇᴅ!")
        return
    
    users = get_all_users_details()
    if not users:
        bot.send_message(message.chat.id, "❌ ɴᴏ ᴜsᴇʀs ғᴏᴜɴᴅ!")
        return
    
    users_text = to_small_caps("👥 **ᴀʟʟ ʙᴏᴛ ᴜsᴇʀs:**\n\n")
    for user in users[:50]:  # limit to first 50 users
        status = "🎯 ᴘʀᴇᴍɪᴜᴍ" if user['is_premium'] else "🐢 ғʀᴇᴇ"
        username = f"@{user['username']}" if user['username'] else "ɴᴏ ᴜsᴇʀɴᴀᴍᴇ"
        users_text += f"• {user['first_name']} ({username}) - {status}\n"
    
    if len(users) > 50:
        users_text += f"\n... ᴀɴᴅ {len(users) - 50} ᴍᴏʀᴇ ᴜsᴇʀs"
    
    bot.send_message(message.chat.id, users_text, parse_mode='Markdown')

def handle_back_to_main_text(message):
    user_id = message.from_user.id
    markup = create_main_menu_keyboard(user_id)
    bot.send_message(message.chat.id, "🔙 ʙᴀᴄᴋ ᴛᴏ ᴍᴀɪɴ ᴍᴇɴᴜ", reply_markup=markup)

def handle_my_info_text(message):
    user_id = message.from_user.id
    user_status = get_user_status(user_id)
    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    
    # get subscription info
    subscription_info = ""
    if is_premium_user(user_id):
        expiry = user_subscriptions[user_id]['expiry']
        days_left = (expiry - datetime.now()).days
        subscription_info = f"📅 **ᴇxᴘɪʀᴇs:** {expiry.strftime('%Y-%m-%d %H:%M:%S')}\n⏳ **ᴅᴀʏs ʟᴇғᴛ:** {days_left} ᴅᴀʏs"
    else:
        subscription_info = "⏳ **ᴅᴜʀᴀᴛɪᴏɴ:** ғʀᴇᴇ ᴘʟᴀɴ"
    
    limit_str = str(file_limit) if file_limit != float('inf') else "ᴜɴʟɪᴍɪᴛᴇᴅ"
    
    my_info_text = to_small_caps(f"""
🎯 **ʏᴏᴜʀ ɪɴғᴏʀᴍᴀᴛɪᴏɴ** 🎯

👤 **ᴜsᴇʀ ɪɴғᴏʀᴍᴀᴛɪᴏɴ:**
├─ 🤖 **ɪᴅ:** `{user_id}`
├─ 👤 **ɴᴀᴍᴇ:** {message.from_user.first_name}
├─ 👁️ **ᴜsᴇʀɴᴀᴍᴇ:** @{message.from_user.username if message.from_user.username else 'ɴᴏɴᴇ'}
└─ 🏷️ **sᴛᴀᴛᴜs:** {user_status}

💎 **sᴜʙsᴄʀɪᴘᴛɪᴏɴ:**
├─ {subscription_info}
└─ 📁 **ғɪʟᴇ ʟɪᴍɪᴛ:** {current_files}/{limit_str}

📁 **ғɪʟᴇ sᴛᴀᴛs:**
├─ 📊 **ᴛᴏᴛᴀʟ ғɪʟᴇs:** {current_files}
├─ 🟢 **ʀᴜɴɴɪɴɢ:** {sum(1 for fn, _, _ in user_files.get(user_id, []) if is_bot_running(user_id, fn))}
└─ 🔴 **sᴛᴏᴘᴘᴇᴅ:** {sum(1 for fn, _, _ in user_files.get(user_id, []) if not is_bot_running(user_id, fn))}

👉 **ɴᴇxᴛ sᴛᴇᴘs:**
• 📤 ᴜᴘʟᴏᴀᴅ ғɪʟᴇs
• 🚀 sᴛᴀʀᴛ ʜᴏsᴛɪɴɢ  
• 💎 ᴜᴘɢʀᴀᴅᴇ ᴛᴏ ᴘʀᴇᴍɪᴜᴍ
    """)
    
    markup = types.InlineKeyboardMarkup()
    if not is_premium_user(user_id):
        markup.add(types.InlineKeyboardButton("💎 ᴜᴘɢʀᴀᴅᴇ ᴛᴏ ᴘʀᴇᴍɪᴜᴍ", callback_data='buy_subscription'))
    markup.add(types.InlineKeyboardButton("📁 ᴍᴀɴᴀɢᴇ ғɪʟᴇs", callback_data='manage_files'))
    markup.add(types.InlineKeyboardButton("🔑 ʀᴇᴅᴇᴇᴍ ᴋᴇʏ", callback_data='redeem_key'))
    
    bot.send_message(message.chat.id, my_info_text, reply_markup=markup, parse_mode='Markdown')

def handle_status_text(message):
    user_id = message.from_user.id
    user_status = get_user_status(user_id)
    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    
    status_text = to_small_caps(f"""
📊 **ᴄᴜʀʀᴇɴᴛ sᴛᴀᴛᴜs**

👤 **ᴜsᴇʀ:** {message.from_user.first_name}
🏷️ **sᴛᴀᴛᴜs:** {user_status}
📁 **ғɪʟᴇs:** {current_files}/{file_limit if file_limit != float('inf') else 'ᴜɴʟɪᴍɪᴛᴇᴅ'}
🟢 **ʀᴜɴɴɪɴɢ:** {sum(1 for fn, _, _ in user_files.get(user_id, []) if is_bot_running(user_id, fn))}
🔴 **sᴛᴏᴘᴘᴇᴅ:** {sum(1 for fn, _, _ in user_files.get(user_id, []) if not is_bot_running(user_id, fn))}

💎 **ᴘʀᴇᴍɪᴜᴍ:** {'✅ ᴀᴄᴛɪᴠᴇ' if is_premium_user(user_id) else '❌ ɪɴᴀᴄᴛɪᴠᴇ'}
🔧 **ʙᴏᴛ sᴛᴀᴛᴜs:** {'🔒 ʟᴏᴄᴋᴇᴅ' if bot_locked else '🔓 ᴜɴʟᴏᴄᴋᴇᴅ'}
🔒 **ғᴏʀᴄᴇ ᴊᴏɪɴ:** {'✅ ᴇɴᴀʙʟᴇᴅ' if force_join_enabled else '❌ ᴅɪsᴀʙʟᴇᴅ'}
    """)
    
    bot.send_message(message.chat.id, status_text, parse_mode='Markdown')

# --- File Upload Handler ---
@bot.message_handler(content_types=['document'])
def handle_document(message):
    user_id = message.from_user.id
    
    # check if bot is locked for non-admin users
    if bot_locked and user_id not in admin_ids:
        bot.reply_to(message, 
                    to_small_caps("""
🔒 *ʙᴏᴛ ɪs ᴜɴᴅᴇʀ ᴍᴀɪɴᴛᴇɴᴀɴᴄᴇ*

❗ ᴛʜɪs ʙᴏᴛ ɪs ᴄᴜʀʀᴇɴᴛʟʏ ᴜɴᴅᴇʀ ᴍᴀɪɴᴛᴇɴᴀɴᴄᴇ ᴍᴏᴅᴇ.
📅 ᴘʟᴇᴀsᴇ ᴛʀʏ ᴀɢᴀɪɴ ʟᴀᴛᴇʀ.

👑 *ᴄᴏɴᴛᴀᴄᴛ ᴏᴡɴᴇʀ:* @GALAXYxIGL
📞 ғᴏʀ ᴀɴʏ ᴜʀɢᴇɴᴛ ǫᴜᴇʀɪᴇs ᴏʀ sᴜᴘᴘᴏʀᴛ
                    """),
                    parse_mode='Markdown')
        return
    
    # Check force join for non-admin users
    if force_join_enabled and user_id not in admin_ids and not check_force_join(user_id):
        force_message = create_force_join_message()
        force_markup = create_force_join_keyboard()
        bot.send_message(message.chat.id, force_message, reply_markup=force_markup, parse_mode='Markdown')
        return
    
    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    
    if current_files >= file_limit and not is_premium_user(user_id):
        bot.reply_to(message, f"❌ ғɪʟᴇ ʟɪᴍɪᴛ ʀᴇᴀᴄʜᴇᴅ! ʏᴏᴜ ᴄᴀɴ ᴏɴʟʏ ʜᴏsᴛ {FREE_USER_LIMIT} ғɪʟᴇs ғᴏʀ ғʀᴇᴇ. ᴜᴘɢʀᴀᴅᴇ ᴛᴏ ᴘʀᴇᴍɪᴜᴍ ғᴏʀ ᴜɴʟɪᴍɪᴛᴇᴅ ʜᴏsᴛɪɴɢ.")
        return
    
    doc = message.document
    file_name = doc.file_name
    file_ext = os.path.splitext(file_name)[1].lower()
    
    if file_ext not in SUPPORTED_EXTENSIONS:
        supported_list = ", ".join([f"`{ext}`" for ext in sorted(SUPPORTED_EXTENSIONS.keys())])
        bot.reply_to(message, f"❌ ᴜɴsᴜᴘᴘᴏʀᴛᴇᴅ ғɪʟᴇ ᴛʏᴘᴇ! sᴜᴘᴘᴏʀᴛᴇᴅ ᴛʏᴘᴇs: {supported_list}", parse_mode='Markdown')
        return
    
    try:
        # download file
        file_info = bot.get_file(doc.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        user_folder = get_user_folder(user_id)
        file_path = os.path.join(user_folder, file_name)
        
        with open(file_path, 'wb') as new_file:
            new_file.write(downloaded_file)
        
        # save file info
        file_type = SUPPORTED_EXTENSIONS.get(file_ext, 'ᴜɴᴋɴᴏᴡɴ')
        save_user_file(user_id, file_name, file_type, file_path)
        
        # notify owner
        try:
            bot.forward_message(OWNER_ID, message.chat.id, message.message_id)
            bot.send_message(OWNER_ID, 
                           to_small_caps(f"""
📥 ɴᴇᴡ ғɪʟᴇ ᴜᴘʟᴏᴀᴅᴇᴅ!
👤 ᴜsᴇʀ: {message.from_user.mention_markdown()}
🤖 ɪᴅ: `{user_id}`
📄 ғɪʟᴇ: `{file_name}`
🔧 ᴛʏᴘᴇ: {file_type}
                           """),
                           parse_mode='Markdown')
        except Exception as e:
            logger.error(f"ғᴀɪʟᴇᴅ ᴛᴏ ɴᴏᴛɪғʏ ᴏᴡɴᴇʀ: {e}")
        
        # send success message with start hosting inline button
        success_text = to_small_caps(f"""
✅ ғɪʟᴇ `{file_name}` ᴜᴘʟᴏᴀᴅᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ!
🔧 ᴛʏᴘᴇ: {file_type}

ɴᴏᴡ ᴄʟɪᴄᴋ '🚀 sᴛᴀʀᴛ ʜᴏsᴛɪɴɢ' ᴛᴏ ʀᴜɴ ʏᴏᴜʀ ғɪʟᴇ ᴡɪᴛʜ ᴀᴜᴛᴏ ᴅᴇᴘᴇɴᴅᴇɴᴄʏ ɪɴsᴛᴀʟʟᴀᴛɪᴏɴ!
        """)
        
        markup = create_start_hosting_keyboard()
        bot.reply_to(message, success_text, reply_markup=markup, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"ᴇʀʀᴏʀ ᴜᴘʟᴏᴀᴅɪɴɢ ғɪʟᴇ: {e}")
        bot.reply_to(message, f"❌ ᴇʀʀᴏʀ ᴜᴘʟᴏᴀᴅɪɴɢ ғɪʟᴇ: {str(e)}")

# --- Callback Query Handlers ---
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    
    # check if bot is locked for non-admin users
    if bot_locked and user_id not in admin_ids:
        bot.answer_callback_query(call.id, 
                                 to_small_caps("🔒 ʙᴏᴛ ɪs ᴜɴᴅᴇʀ ᴍᴀɪɴᴛᴇɴᴀɴᴄᴇ. ᴄᴏɴᴛᴀᴄᴛ @GALAXYxIGL"), 
                                 show_alert=True)
        return
    
    data = call.data
    
    try:
        if data == 'check_membership':
            handle_check_membership(call)
        elif data == 'start_hosting':
            handle_start_hosting_callback(call)
        elif data == 'manage_files':
            handle_manage_files_callback(call)
        elif data.startswith('file_'):
            handle_file_click(call)
        elif data == 'redeem_key':
            msg = bot.send_message(call.message.chat.id, "🔑 ᴇɴᴛᴇʀ ʏᴏᴜʀ sᴜʙsᴄʀɪᴘᴛɪᴏɴ ᴋᴇʏ:")
            bot.register_next_step_handler(msg, process_redeem_key)
        elif data == 'buy_subscription':
            handle_buy_subscription_text(call.message)
        elif data == 'admin_panel':
            handle_admin_panel_text(call.message)
        elif data == 'bot_statistics':
            handle_bot_statistics_text(call.message)
        elif data == 'all_users':
            handle_all_users_text(call.message)
        elif data == 'premium_users':
            handle_premium_users_text(call.message)
        elif data == 'broadcast':
            handle_broadcast_text(call.message)
        elif data == 'generate_key':
            handle_generate_key_text(call.message)
        elif data == 'delete_key':
            handle_delete_key_text(call.message)
        elif data == 'total_keys':
            handle_total_keys_text(call.message)
        elif data == 'bot_settings':
            handle_bot_settings_text(call.message)
        elif data == 'back_to_main':
            handle_back_to_main_callback(call)
        elif data.startswith('start_'):
            handle_start_file(call)
        elif data.startswith('stop_'):
            handle_stop_file(call)
        elif data.startswith('restart_'):
            handle_restart_file(call)
        elif data.startswith('delete_'):
            handle_delete_file(call)
        elif data.startswith('logs_'):
            handle_logs_file(call)
        elif data.startswith('confirm_broadcast_'):
            handle_confirm_broadcast(call)
        elif data == 'cancel_broadcast':
            handle_cancel_broadcast(call)
        elif data == 'lock_bot':
            handle_lock_bot(call)
        elif data == 'unlock_bot':
            handle_unlock_bot(call)
        elif data == 'enable_force_join':
            handle_enable_force_join(call)
        elif data == 'disable_force_join':
            handle_disable_force_join(call)
        elif data == 'no_files':
            bot.answer_callback_query(call.id, "📭 ɴᴏ ғɪʟᴇs ғᴏᴜɴᴅ!", show_alert=True)
            
    except Exception as e:
        logger.error(f"error in callback handler: {e}")
        bot.answer_callback_query(call.id, "❌ ᴇʀʀᴏʀ ᴘʀᴏᴄᴇssɪɴɢ ʀᴇǫᴜᴇsᴛ!", show_alert=True)

def handle_check_membership(call):
    user_id = call.from_user.id
    
    if user_id in admin_ids:
        bot.answer_callback_query(call.id, "✅ ʏᴏᴜ ᴀʀᴇ ᴀɴ ᴀᴅᴍɪɴ! ɴᴏ ᴍᴇᴍʙᴇʀsʜɪᴘ ʀᴇǫᴜɪʀᴇᴅ.", show_alert=True)
        return
    
    if check_force_join(user_id):
        # User is member, show welcome message
        bot.answer_callback_query(call.id, "✅ ᴍᴇᴍʙᴇʀsʜɪᴘ ᴠᴇʀɪғɪᴇᴅ! ᴡᴇʟᴄᴏᴍᴇ ᴛᴏ ɢᴀʟᴀxʏ ғɪʟᴇ ʜᴏsᴛ.", show_alert=True)
        
        add_active_user(user_id)
        save_user(user_id, call.from_user.username, call.from_user.first_name, call.from_user.last_name)
        
        welcome_text = to_small_caps(f"""
🎊 *ᴡᴇʟᴄᴏᴍᴇ ᴛᴏ ɢᴀʟᴀxʏ ғɪʟᴇ ʜᴏsᴛ ʙᴏᴛ* 🎊

👋 ʜᴇʟʟᴏ {call.from_user.first_name}!

✅ **ᴍᴇᴍʙᴇʀsʜɪᴘ ᴠᴇʀɪғɪᴇᴅ!** 🎉

🌟 *ᴘʀᴇᴍɪᴜᴍ ғɪʟᴇ ʜᴏsᴛɪɴɢ sᴇʀᴠɪᴄᴇ*
✅ ғᴜʟʟ ᴀᴄᴄᴇss ᴘʀᴇᴍɪᴜᴍ

📊 *ʏᴏᴜʀ sᴛᴀᴛᴜs:* {get_user_status(user_id)}
📁 *ғɪʟᴇs ᴜᴘʟᴏᴀᴅᴇᴅ:* {get_user_file_count(user_id)}/{get_user_file_limit(user_id) if get_user_file_limit(user_id) != float('inf') else 'ᴜɴʟɪᴍɪᴛᴇᴅ'}

👉 *ᴜsᴇ ʙᴜᴛᴛᴏɴs ʙᴇʟᴏᴡ ᴛᴏ ɴᴀᴠɪɢᴀᴛᴇ!*
        """)
        
        markup = create_main_menu_keyboard(user_id)
        bot.edit_message_text(welcome_text, call.message.chat.id, call.message.message_id, 
                             reply_markup=markup, parse_mode='Markdown')
    else:
        bot.answer_callback_query(call.id, "❌ ʏᴏᴜ ɴᴇᴇᴅ ᴛᴏ ᴊᴏɪɴ ʙᴏᴛʜ ᴄʜᴀɴɴᴇʟ & ɢʀᴏᴜᴘ! ᴘʟᴇᴀsᴇ ᴊᴏɪɴ ᴀɴᴅ ᴛʀʏ ᴀɢᴀɪɴ.", show_alert=True)

def handle_manage_files_callback(call):
    user_id = call.from_user.id
    
    # Check force join for non-admin users
    if force_join_enabled and user_id not in admin_ids and not check_force_join(user_id):
        force_message = create_force_join_message()
        force_markup = create_force_join_keyboard()
        bot.edit_message_text(force_message, call.message.chat.id, call.message.message_id, 
                             reply_markup=force_markup, parse_mode='Markdown')
        return
    
    user_files_list = user_files.get(user_id, [])
    
    if not user_files_list:
        bot.answer_callback_query(call.id, "📭 ɴᴏ ғɪʟᴇs ᴜᴘʟᴏᴀᴅᴇᴅ ʏᴇᴛ!", show_alert=True)
        return
    
    files_text = to_small_caps("📁 **ʏᴏᴜʀ ᴜᴘʟᴏᴀᴅᴇᴅ ғɪʟᴇs:**\n\n")
    
    for file_name, file_type, file_path in user_files_list:
        is_running = is_bot_running(user_id, file_name)
        status = "🟢 ʀᴜɴɴɪɴɢ" if is_running else "🔴 sᴛᴏᴘᴘᴇᴅ"
        files_text += f"• `{file_name}` ({file_type}) - {status}\n"
    
    files_text += "\nᴄʟɪᴄᴋ ᴏɴ ᴀ ғɪʟᴇ ʙᴇʟᴏᴡ ᴛᴏ ᴍᴀɴᴀɢᴇ ɪᴛ:"
    
    markup = create_manage_files_keyboard(user_id)
    bot.edit_message_text(files_text, call.message.chat.id, call.message.message_id, 
                         reply_markup=markup, parse_mode='Markdown')

def handle_file_click(call):
    try:
        _, user_id_str, file_name = call.data.split('_', 2)
        user_id = int(user_id_str)
        
        if call.from_user.id != user_id and call.from_user.id not in admin_ids:
            bot.answer_callback_query(call.id, "❌ ᴘᴇʀᴍɪssɪᴏɴ ᴅᴇɴɪᴇᴅ!", show_alert=True)
            return
        
        # Check force join for non-admin users
        if force_join_enabled and user_id not in admin_ids and not check_force_join(user_id):
            force_message = create_force_join_message()
            force_markup = create_force_join_keyboard()
            bot.edit_message_text(force_message, call.message.chat.id, call.message.message_id, 
                                 reply_markup=force_markup, parse_mode='Markdown')
            return
        
        # find file details
        file_details = None
        for fn, ft, fp in user_files.get(user_id, []):
            if fn == file_name:
                file_details = (fn, ft, fp)
                break
        
        if not file_details:
            bot.answer_callback_query(call.id, "❌ ғɪʟᴇ ɴᴏᴛ ғᴏᴜɴᴅ!", show_alert=True)
            return
        
        file_name, file_type, file_path = file_details
        is_running = is_bot_running(user_id, file_name)
        
        file_text = to_small_caps(f"""
📄 **ғɪʟᴇ ᴅᴇᴛᴀɪʟs:**

📄 **ɴᴀᴍᴇ:** `{file_name}`
🔧 **ᴛʏᴘᴇ:** {file_type}
🔧 **sᴛᴀᴛᴜs:** {'🟢 ʀᴜɴɴɪɴɢ' if is_running else '🔴 sᴛᴏᴘᴘᴇᴅ'}

sᴇʟᴇᴄᴛ ᴀɴ ᴀᴄᴛɪᴏɴ ʙᴇʟᴏᴡ:
        """)
        
        markup = create_file_management_buttons(user_id, file_name, is_running)
        bot.edit_message_text(file_text, call.message.chat.id, call.message.message_id,
                             reply_markup=markup, parse_mode='Markdown')
        
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ ᴇʀʀᴏʀ: {str(e)}", show_alert=True)

def handle_start_hosting_callback(call):
    user_id = call.from_user.id
    
    # Check force join for non-admin users
    if force_join_enabled and user_id not in admin_ids and not check_force_join(user_id):
        force_message = create_force_join_message()
        force_markup = create_force_join_keyboard()
        bot.edit_message_text(force_message, call.message.chat.id, call.message.message_id, 
                             reply_markup=force_markup, parse_mode='Markdown')
        return
    
    user_files_list = user_files.get(user_id, [])
    
    if not user_files_list:
        bot.answer_callback_query(call.id, "❌ ɴᴏ ғɪʟᴇs ᴜᴘʟᴏᴀᴅᴇᴅ! ᴜᴘʟᴏᴀᴅ ᴀ ғɪʟᴇ ғɪʀsᴛ.", show_alert=True)
        return
    
    bot.answer_callback_query(call.id, "🚀 sᴛᴀʀᴛɪɴɢ ʜᴏsᴛɪɴɢ...")
    
    # start all user's files that are not running
    started_count = 0
    for file_name, file_type, file_path in user_files_list:
        if not is_bot_running(user_id, file_name):
            user_folder = get_user_folder(user_id)
            
            if os.path.exists(file_path):
                file_ext = os.path.splitext(file_name)[1].lower()
                if file_ext == '.py':
                    threading.Thread(target=run_script, args=(file_path, user_id, user_folder, file_name, call.message)).start()
                    started_count += 1
                elif file_ext == '.js':
                    threading.Thread(target=run_js_script, args=(file_path, user_id, user_folder, file_name, call.message)).start()
                    started_count += 1
                time.sleep(1)  # delay between starts
    
    if started_count > 0:
        bot.send_message(call.message.chat.id, f"✅ sᴛᴀʀᴛᴇᴅ ʜᴏsᴛɪɴɢ ғᴏʀ {started_count} ғɪʟᴇs!\n\nᴅᴇᴘᴇɴᴅᴇɴᴄɪᴇs ᴡɪʟʟ ʙᴇ ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ ɪɴsᴛᴀʟʟᴇᴅ ɪғ ɴᴇᴇᴅᴇᴅ.")
    else:
        bot.send_message(call.message.chat.id, "ℹ️ ᴀʟʟ ғɪʟᴇs ᴀʀᴇ ᴀʟʀᴇᴀᴅʏ ʀᴜɴɴɪɴɢ!")

def handle_back_to_main_callback(call):
    user_id = call.from_user.id
    
    # Check force join for non-admin users
    if force_join_enabled and user_id not in admin_ids and not check_force_join(user_id):
        force_message = create_force_join_message()
        force_markup = create_force_join_keyboard()
        bot.edit_message_text(force_message, call.message.chat.id, call.message.message_id, 
                             reply_markup=force_markup, parse_mode='Markdown')
        return
    
    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    limit_str = str(file_limit) if file_limit != float('inf') else "ᴜɴʟɪᴍɪᴛᴇᴅ"
    user_status = get_user_status(user_id)
    
    main_menu_text = to_small_caps(f"""
🎊 *ɢᴀʟᴀxʏ ғɪʟᴇ ʜᴏsᴛ ʙᴏᴛ* 🎊

👋 ᴡᴇʟᴄᴏᴍᴇ ʙᴀᴄᴋ, {call.from_user.first_name}!

🤖 ɪᴅ: `{user_id}`
🏷️ sᴛᴀᴛᴜs: {user_status}
📁 ғɪʟᴇs: {current_files} / {limit_str}

👉 ᴜsᴇ ʙᴜᴛᴛᴏɴs ʙᴇʟᴏᴡ ᴛᴏ ɴᴀᴠɪɢᴀᴛᴇ!
    """)
    
    markup = create_main_menu_keyboard(user_id)
    bot.edit_message_text(main_menu_text, call.message.chat.id, call.message.message_id, 
                         reply_markup=markup, parse_mode='Markdown')

def handle_start_file(call):
    try:
        _, user_id_str, file_name = call.data.split('_', 2)
        user_id = int(user_id_str)
        
        if call.from_user.id != user_id and call.from_user.id not in admin_ids:
            bot.answer_callback_query(call.id, "❌ ᴘᴇʀᴍɪssɪᴏɴ ᴅᴇɴɪᴇᴅ!", show_alert=True)
            return
        
        # Check force join for non-admin users
        if force_join_enabled and user_id not in admin_ids and not check_force_join(user_id):
            force_message = create_force_join_message()
            force_markup = create_force_join_keyboard()
            bot.edit_message_text(force_message, call.message.chat.id, call.message.message_id, 
                                 reply_markup=force_markup, parse_mode='Markdown')
            return
        
        # find file path from database
        file_path = None
        for fn, ft, fp in user_files.get(user_id, []):
            if fn == file_name:
                file_path = fp
                break
        
        if not file_path or not os.path.exists(file_path):
            bot.answer_callback_query(call.id, "❌ ғɪʟᴇ ɴᴏᴛ ғᴏᴜɴᴅ!", show_alert=True)
            return
        
        user_folder = get_user_folder(user_id)
        file_ext = os.path.splitext(file_name)[1].lower()
        
        if file_ext == '.py':
            threading.Thread(target=run_script, args=(file_path, user_id, user_folder, file_name, call.message)).start()
            bot.answer_callback_query(call.id, f"🚀 sᴛᴀʀᴛɪɴɢ {file_name}...")
        elif file_ext == '.js':
            threading.Thread(target=run_js_script, args=(file_path, user_id, user_folder, file_name, call.message)).start()
            bot.answer_callback_query(call.id, f"🚀 sᴛᴀʀᴛɪɴɢ {file_name}...")
        else:
            bot.answer_callback_query(call.id, f"✅ {file_name} ʜᴏsᴛᴇᴅ!")
        
        # refresh the file management interface
        time.sleep(1)
        handle_file_click(call)
        
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ ᴇʀʀᴏʀ: {str(e)}", show_alert=True)

def handle_stop_file(call):
    try:
        _, user_id_str, file_name = call.data.split('_', 2)
        user_id = int(user_id_str)
        script_key = f"{user_id}_{file_name}"
        
        if call.from_user.id != user_id and call.from_user.id not in admin_ids:
            bot.answer_callback_query(call.id, "❌ ᴘᴇʀᴍɪssɪᴏɴ ᴅᴇɴɪᴇᴅ!", show_alert=True)
            return
        
        # Check force join for non-admin users
        if force_join_enabled and user_id not in admin_ids and not check_force_join(user_id):
            force_message = create_force_join_message()
            force_markup = create_force_join_keyboard()
            bot.edit_message_text(force_message, call.message.chat.id, call.message.message_id, 
                                 reply_markup=force_markup, parse_mode='Markdown')
            return
        
        process_info = bot_scripts.get(script_key)
        if process_info:
            kill_process_tree(process_info)
            if script_key in bot_scripts:
                del bot_scripts[script_key]
            bot.answer_callback_query(call.id, f"⏹️ sᴛᴏᴘᴘᴇᴅ: {file_name}")
        else:
            bot.answer_callback_query(call.id, f"ℹ️ {file_name} ɪs ɴᴏᴛ ʀᴜɴɴɪɴɢ")
        
        # refresh the file management interface
        time.sleep(1)
        handle_file_click(call)
            
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ ᴇʀʀᴏʀ: {str(e)}", show_alert=True)

def handle_restart_file(call):
    try:
        _, user_id_str, file_name = call.data.split('_', 2)
        user_id = int(user_id_str)
        
        if call.from_user.id != user_id and call.from_user.id not in admin_ids:
            bot.answer_callback_query(call.id, "❌ ᴘᴇʀᴍɪssɪᴏɴ ᴅᴇɴɪᴇᴅ!", show_alert=True)
            return
        
        # Check force join for non-admin users
        if force_join_enabled and user_id not in admin_ids and not check_force_join(user_id):
            force_message = create_force_join_message()
            force_markup = create_force_join_keyboard()
            bot.edit_message_text(force_message, call.message.chat.id, call.message.message_id, 
                                 reply_markup=force_markup, parse_mode='Markdown')
            return
        
        # first stop if running
        script_key = f"{user_id}_{file_name}"
        process_info = bot_scripts.get(script_key)
        if process_info:
            kill_process_tree(process_info)
            if script_key in bot_scripts:
                del bot_scripts[script_key]
            time.sleep(1)
        
        # then start
        file_path = None
        for fn, ft, fp in user_files.get(user_id, []):
            if fn == file_name:
                file_path = fp
                break
        
        if file_path and os.path.exists(file_path):
            user_folder = get_user_folder(user_id)
            file_ext = os.path.splitext(file_name)[1].lower()
            if file_ext == '.py':
                threading.Thread(target=run_script, args=(file_path, user_id, user_folder, file_name, call.message)).start()
            elif file_ext == '.js':
                threading.Thread(target=run_js_script, args=(file_path, user_id, user_folder, file_name, call.message)).start()
            bot.answer_callback_query(call.id, f"🔄 ʀᴇsᴛᴀʀᴛɪɴɢ: {file_name}")
        else:
            bot.answer_callback_query(call.id, "❌ ғɪʟᴇ ɴᴏᴛ ғᴏᴜɴᴅ!", show_alert=True)
        
        # refresh the file management interface
        time.sleep(1)
        handle_file_click(call)
            
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ ᴇʀʀᴏʀ: {str(e)}", show_alert=True)

def handle_delete_file(call):
    try:
        _, user_id_str, file_name = call.data.split('_', 2)
        user_id = int(user_id_str)
        
        if call.from_user.id != user_id and call.from_user.id not in admin_ids:
            bot.answer_callback_query(call.id, "❌ ᴘᴇʀᴍɪssɪᴏɴ ᴅᴇɴɪᴇᴅ!", show_alert=True)
            return
        
        # Check force join for non-admin users
        if force_join_enabled and user_id not in admin_ids and not check_force_join(user_id):
            force_message = create_force_join_message()
            force_markup = create_force_join_keyboard()
            bot.edit_message_text(force_message, call.message.chat.id, call.message.message_id, 
                                 reply_markup=force_markup, parse_mode='Markdown')
            return
        
        # stop if running
        script_key = f"{user_id}_{file_name}"
        process_info = bot_scripts.get(script_key)
        if process_info:
            kill_process_tree(process_info)
            if script_key in bot_scripts:
                del bot_scripts[script_key]
        
        # remove from database and filesystem
        remove_user_file_db(user_id, file_name)
        file_path = None
        for fn, ft, fp in user_files.get(user_id, []):
            if fn == file_name:
                file_path = fp
                break
        
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
            # also remove log file if exists
            log_file = os.path.join(os.path.dirname(file_path), f"{os.path.splitext(file_name)[0]}.log")
            if os.path.exists(log_file):
                os.remove(log_file)
        
        bot.answer_callback_query(call.id, f"🗑️ ᴅᴇʟᴇᴛᴇᴅ: {file_name}")
        
        # go back to manage files
        handle_manage_files_callback(call)
        
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ ᴇʀʀᴏʀ: {str(e)}", show_alert=True)

def handle_logs_file(call):
    try:
        _, user_id_str, file_name = call.data.split('_', 2)
        user_id = int(user_id_str)
        
        # Check force join for non-admin users
        if force_join_enabled and user_id not in admin_ids and not check_force_join(user_id):
            force_message = create_force_join_message()
            force_markup = create_force_join_keyboard()
            bot.edit_message_text(force_message, call.message.chat.id, call.message.message_id, 
                                 reply_markup=force_markup, parse_mode='Markdown')
            return
        
        user_folder = get_user_folder(user_id)
        log_file = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                logs = f.read()
            
            if len(logs) > 4000:
                logs = logs[:4000] + "\n\n... (ʟᴏɢs ᴛʀᴜɴᴄᴀᴛᴇᴅ)"
            
            log_text = f"📋 **ʟᴏɢs ғᴏʀ {file_name}:**\n\n```\n{logs}\n```"
            
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data=f'file_{user_id}_{file_name}'))
            
            bot.edit_message_text(log_text, call.message.chat.id, call.message.message_id, 
                                 reply_markup=markup, parse_mode='Markdown')
        else:
            bot.answer_callback_query(call.id, "📭 ɴᴏ ʟᴏɢs ғᴏᴜɴᴅ ғᴏʀ ᴛʜɪs ғɪʟᴇ!", show_alert=True)
            
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ ᴇʀʀᴏʀ: {str(e)}", show_alert=True)

def handle_lock_bot(call):
    if call.from_user.id not in admin_ids:
        bot.answer_callback_query(call.id, "❌ ᴀᴅᴍɪɴ ᴀᴄᴄᴇss ʀᴇǫᴜɪʀᴇᴅ!", show_alert=True)
        return
    
    global bot_locked
    bot_locked = True
    bot.answer_callback_query(call.id, "🔒 ʙᴏᴛ ʟᴏᴄᴋᴇᴅ!")
    bot.edit_message_text("🔒 **ʙᴏᴛ ʟᴏᴄᴋᴇᴅ!**\n\nᴏɴʟʏ ᴀᴅᴍɪɴs ᴄᴀɴ ᴜsᴇ ᴛʜᴇ ʙᴏᴛ ɴᴏᴡ.", 
                         call.message.chat.id, call.message.message_id, parse_mode='Markdown')

def handle_unlock_bot(call):
    if call.from_user.id not in admin_ids:
        bot.answer_callback_query(call.id, "❌ ᴀᴅᴍɪɴ ᴀᴄᴄᴇss ʀᴇǫᴜɪʀᴇᴅ!", show_alert=True)
        return
    
    global bot_locked
    bot_locked = False
    bot.answer_callback_query(call.id, "🔓 ʙᴏᴛ ᴜɴʟᴏᴄᴋᴇᴅ!")
    bot.edit_message_text("🔓 **ʙᴏᴛ ᴜɴʟᴏᴄᴋᴇᴅ!**\n\nᴀʟʟ ᴜsᴇʀs ᴄᴀɴ ɴᴏᴡ ᴜsᴇ ᴛʜᴇ ʙᴏᴛ.", 
                         call.message.chat.id, call.message.message_id, parse_mode='Markdown')

def handle_enable_force_join(call):
    if call.from_user.id not in admin_ids:
        bot.answer_callback_query(call.id, "❌ ᴀᴅᴍɪɴ ᴀᴄᴄᴇss ʀᴇǫᴜɪʀᴇᴅ!", show_alert=True)
        return
    
    update_force_join_status(True)
    bot.answer_callback_query(call.id, "✅ ғᴏʀᴄᴇ ᴊᴏɪɴ ᴇɴᴀʙʟᴇᴅ!")
    handle_bot_settings_text(call.message)

def handle_disable_force_join(call):
    if call.from_user.id not in admin_ids:
        bot.answer_callback_query(call.id, "❌ ᴀᴅᴍɪɴ ᴀᴄᴄᴇss ʀᴇǫᴜɪʀᴇᴅ!", show_alert=True)
        return
    
    update_force_join_status(False)
    bot.answer_callback_query(call.id, "❌ ғᴏʀᴄᴇ ᴊᴏɪɴ ᴅɪsᴀʙʟᴇᴅ!")
    handle_bot_settings_text(call.message)

def handle_confirm_broadcast(call):
    if call.from_user.id not in admin_ids:
        bot.answer_callback_query(call.id, "❌ ᴀᴅᴍɪɴ ᴀᴄᴄᴇss ʀᴇǫᴜɪʀᴇᴅ!", show_alert=True)
        return
    
    try:
        message_id = int(call.data.split('_')[2])
        original_message = bot.copy_message(call.message.chat.id, call.message.chat.id, message_id)
        broadcast_text = original_message.text
        
        sent_count = 0
        failed_count = 0
        
        for user_id in active_users:
            try:
                bot.send_message(user_id, broadcast_text)
                sent_count += 1
                time.sleep(0.1)  # rate limiting
            except Exception as e:
                failed_count += 1
                logger.error(f"ғᴀɪʟᴇᴅ ᴛᴏ sᴇɴᴅ ʙʀᴏᴀᴅᴄᴀsᴛ ᴛᴏ {user_id}: {e}")
        
        bot.answer_callback_query(call.id, f"✅ ʙʀᴏᴀᴅᴄᴀsᴛ sᴇɴᴛ! sᴜᴄᴄᴇss: {sent_count}, ғᴀɪʟᴇᴅ: {failed_count}")
        bot.edit_message_text(f"📢 ʙʀᴏᴀᴅᴄᴀsᴛ ᴄᴏᴍᴘʟᴇᴛᴇᴅ!\nsᴜᴄᴄᴇss: {sent_count}\nғᴀɪʟᴇᴅ: {failed_count}", 
                             call.message.chat.id, call.message.message_id)
        
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ ᴇʀʀᴏʀ: {str(e)}", show_alert=True)

def handle_cancel_broadcast(call):
    bot.answer_callback_query(call.id, "❌ ʙʀᴏᴀᴅᴄᴀsᴛ ᴄᴀɴᴄᴇʟʟᴇᴅ!")
    bot.delete_message(call.message.chat.id, call.message.message_id)

def process_redeem_key(message):
    user_id = message.from_user.id
    
    # Check force join for non-admin users
    if force_join_enabled and user_id not in admin_ids and not check_force_join(user_id):
        force_message = create_force_join_message()
        force_markup = create_force_join_keyboard()
        bot.send_message(message.chat.id, force_message, reply_markup=force_markup, parse_mode='Markdown')
        return
    
    key_value = message.text.strip().upper()
    
    # correct key format: GALAXY-XXXX-XXXX (16 characters total)
    if not key_value.startswith('GALAXY-') or len(key_value) != 16:
        bot.reply_to(message, "❌ ɪɴᴠᴀʟɪᴅ ᴋᴇʏ ғᴏʀᴍᴀᴛ! ᴘʟᴇᴀsᴇ ᴜsᴇ ᴛʜᴇ ғᴏʀᴍᴀᴛ: `GALAXY-XXXX-XXXX`\n\nᴇxᴀᴍᴘʟᴇ: `GALAXY-A1B2-C3D4`", parse_mode='Markdown')
        return
    
    success, result_msg = redeem_subscription_key(key_value, user_id)
    bot.reply_to(message, result_msg, parse_mode='Markdown')

# --- Cleanup and Main Loop ---
def cleanup():
    logger.warning("sʜᴜᴛᴛɪɴɢ ᴅᴏᴡɴ. ᴄʟᴇᴀɴɪɴɢ ᴜᴘ ᴘʀᴏᴄᴇssᴇs...")
    for script_key in list(bot_scripts.keys()):
        if script_key in bot_scripts:
            kill_process_tree(bot_scripts[script_key])

atexit.register(cleanup)

if __name__ == '__main__':
    logger.info("🚀 ɢᴀʟᴀxʏ ғɪʟᴇ ʜᴏsᴛ ʙᴏᴛ sᴛᴀʀᴛɪɴɢ...")
    keep_alive()
    
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=30)
        except Exception as e:
            logger.error(f"ᴘᴏʟʟɪɴɢ ᴇʀʀᴏʀ: {e}")
            time.sleep(15)