print("Loading integrated_token_analyzer.py...")

SCRIPT_VERSION = "1.6"
print(f"Running script version: {SCRIPT_VERSION}")

import httpx
from bs4 import BeautifulSoup
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import requests
import time
import os
import json
from dotenv import load_dotenv

load_dotenv()
print("Loaded environment variables using load_dotenv()")

class TokenAnalyzer:
    def __init__(self, telegram_bot_token, telegram_chat_id):
        print("Initializing TokenAnalyzer...")
        print(f"Telegram bot token: {'Set' if telegram_bot_token else 'Not set'}")
        print(f"Telegram chat ID: {'Set' if telegram_chat_id else 'Not set'}")
        if not telegram_bot_token or not telegram_chat_id:
            raise ValueError("Telegram bot token or chat ID not provided in environment variables")
        self.bot_token = telegram_bot_token
        self.chat_id = str(telegram_chat_id)
        self.bot_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        self.gmgn_url = "https://gmgn.ai/?chain=sol"
        self.all_tokens = []
        # Use GITHUB_WORKSPACE if available, otherwise default to local path
        github_workspace = os.getenv('GITHUB_WORKSPACE', '')
        print(f"GITHUB_WORKSPACE: {github_workspace}")
        self.repeat_history_file = os.path.join(github_workspace, 'repeat_history.json')
        print(f"Repeat history file path: {self.repeat_history_file}")
        # Create an empty repeat_history.json if it doesn't exist
        if not os.path.exists(self.repeat_history_file):
            print(f"Creating empty repeat_history.json at {self.repeat_history_file}")
            with open(self.repeat_history_file, 'w') as f:
                json.dump({}, f, indent=4)
        else:
            print(f"repeat_history.json already exists at {self.repeat_history_file}")
        self.repeat_history = self.load_repeat_history()
        self.sent_tokens = {}  # Reset for each run
        print("Finished initializing TokenAnalyzer")

    def load_repeat_history(self):
        """Load repeat history from a JSON file."""
        if os.path.exists(self.repeat_history_file):
            try:
                with open(self.repeat_history_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading repeat history: {e}")
        return {}

    def save_repeat_history(self):
        """Save repeat history to a JSON file."""
        try:
            with open(self.repeat_history_file, 'w') as f:
                json.dump(self.repeat_history, f, indent=4)
            print(f"Saved repeat history to {self.repeat_history_file}")
        except Exception as e:
            print(f"Error saving repeat history: {e}")

    def update_repeat_history(self, token_data):
        """Update the repeat history for a token."""
        contract_address = token_data['full_ca']
        current_time = int(time.time())
        
        if contract_address in self.repeat_history:
            self.repeat_history[contract_address]['count'] += 1
            self.repeat_history[contract_address]['last_seen'] = current_time
        else:
            self.repeat_history[contract_address] = {
                'name': token_data.get('baseToken', {}).get('name', 'Unknown'),
                'count': 1,
                'last_seen': current_time
            }
        self.save_repeat_history()
        return self.repeat_history[contract_address]['count'], self.repeat_history[contract_address]['last_seen']

    def send_to_telegram(self, token_data):
        try:
            repeat_count, last_seen = self.update_repeat_history(token_data)
            contract_address = token_data['full_ca']
            
            # Update sent_tokens for tracking
            if contract_address in self.sent_tokens:
                self.sent_tokens[contract_address]['count'] += 1
            else:
                self.sent_tokens[contract_address] = {
                    'name': token_data.get('baseToken', {}).get('name', 'Unknown'),
                    'count': repeat_count,
                    'short_ca': contract_address[:6] + '...' + contract_address[-3:]
                }
            
            # Determine emoji and repeat alert
            if repeat_count == 1:
                emoji = "🟢"
                repeat_alert = ""
            elif repeat_count == 2:
                emoji = "🟡"  # Yellow for 2 repeaters
                repeat_alert = f"⚠️ Repeat Alert: Seen {repeat_count - 1} time(s) before"
            elif repeat_count == 3:
                emoji = "🟠"  # Orange for 3 repeaters
                repeat_alert = f"❗ Repeat Alert: Seen {repeat_count - 1} time(s) before"
            else:
                emoji = "🔴"  # Red for 4 or more repeaters
                repeat_alert = f"🚨 Repeat Alert: Seen {repeat_count - 1} time(s) before"
            
            if repeat_count > 1:
                time_diff = int(time.time()) - last_seen
                hours_ago = time_diff // 3600
                minutes_ago = (time_diff % 3600) // 60
                if hours_ago > 0:
                    repeat_alert += f" (last seen {hours_ago} hour{'s' if hours_ago != 1 else ''} ago)"
                else:
                    repeat_alert += f" (last seen {minutes_ago} minute{'s' if minutes_ago != 1 else ''} ago)"

            # Construct the message
            message_lines = []
            message_lines.append(f"{emoji} 🚀 Filtered Token! #{repeat_count}")
            if repeat_alert:
                message_lines.append(repeat_alert)
            message_lines.append(f"Contract: <code>{token_data['full_ca']}</code>")
            message_lines.append(f"Name: <b>{token_data.get('baseToken', {}).get('name', 'Unknown')}</b>")
            message_lines.append(f"Market Cap: ${token_data.get('marketCap', 0):,.2f}")
            message_lines.append(f"Liquidity: ${token_data.get('liquidity', {}).get('usd', 0):,.2f}")
            message_lines.append(f"24h Volume: ${token_data.get('volume', {}).get('h24', 0):,.2f}")
            message_lines.append(f"Age: {(int(time.time()) - token_data.get('pairCreatedAt', 0) // 1000) / 3600:.2f} hours")
            if repeat_count > 1:
                message_lines.append(f"Repeat Summary: Seen {repeat_count} times")

            message = "\n".join(message_lines)

            # Prepare the payload (no reply_markup since removing Copy CA button)
            payload = {
                'chat_id': self.chat_id,
                'text': message,
                'parse_mode': 'HTML'
            }

            with httpx.Client() as client:
                response = client.post(self.bot_url, data=payload)
            if response.status_code == 200:
                print(f"✅ Sent {token_data['full_ca'][:6]}...{token_data['full_ca'][-3:]} to Telegram")
            else:
                print(f"❌ Telegram send failed: {response.status_code} - {response.text}")
                print("Falling back to console output:")
                print(message)
        except Exception as e:
            print(f"❌ Telegram error: {e}")
            print("Falling back to console output:")
            message = (
                f"{emoji} 🚀 Filtered Token! #{repeat_count}\n"
                f"{repeat_alert}\n" if repeat_alert else ""
                f"Contract: <code>{token_data.get('full_ca', 'Unknown')}</code>\n"
                f"Name: <b>{token_data.get('baseToken', {}).get('name', 'Unknown')}</b>\n"
                f"Market Cap: ${token_data.get('marketCap',
