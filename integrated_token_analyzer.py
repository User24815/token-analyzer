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

class TokenAnalyzer:
    def __init__(self, telegram_bot_token, telegram_chat_id):
        print("Initializing TokenAnalyzer...")
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
        self.repeat_history_file = os.path.join(os.getenv('GITHUB_WORKSPACE', ''), 'repeat_history.json')
        self.repeat_history = self.load_repeat_history()
        self.sent_tokens = {}  # Reset for each run
        print("Finished initializing TokenAnalyzer")

    def load_repeat_history(self):
        """Load repeat history from a JSON file."""
        print(f"Loading repeat history from {self.repeat_history_file}")
        if os.path.exists(self.repeat_history_file):
            try:
                with open(self.repeat_history_file, 'r') as f:
                    data = json.load(f)
                    print(f"Loaded repeat history: {data}")
                    return data
            except Exception as e:
                print(f"Error loading repeat history: {e}")
        else:
            print("Repeat history file does not exist, starting with empty dict")
        return {}

    def save_repeat_history(self):
        """Save repeat history to a JSON file."""
        print(f"Saving repeat history: {self.repeat_history}")
        try:
            with open(self.repeat_history_file, 'w') as f:
                json.dump(self.repeat_history, f, indent=4)
            print(f"Saved repeat history to {self.repeat_history_file}")
        except Exception as e:
            print(f"Error saving repeat history: {e}")

    def update_repeat_history(self, token_data):
        """Update the repeat history for a token."""
        contract_address = token_data['full_ca'].lower()
        current_time = int(time.time())
        print(f"Setting last_seen to current time: {current_time} (UTC: {datetime.utcfromtimestamp(current_time).strftime('%Y-%m-%d %H:%M:%S')})")
        print(f"Processing contract address: {contract_address}")
        
        if contract_address in self.repeat_history:
            self.repeat_history[contract_address]['count'] += 1
            self.repeat_history[contract_address]['last_seen'] = current_time
            print(f"Incremented count for {contract_address}: {self.repeat_history[contract_address]}")
        else:
            self.repeat_history[contract_address] = {
                'name': token_data.get('baseToken', {}).get('name', 'Unknown'),
                'count': 1,
                'last_seen': current_time
            }
            print(f"Added new token {contract_address} to repeat history: {self.repeat_history[contract_address]}")
        self.save_repeat_history()
        return self.repeat_history[contract_address]['count'], self.repeat_history[contract_address]['last_seen']

    def send_to_telegram(self, token_data):
        try:
            repeat_count, last_seen = self.update_repeat_history(token_data)
            contract_address = token_data['full_ca'].lower()
            
            if contract_address in self.sent_tokens:
                self.sent_tokens[contract_address]['count'] += 1
            else:
                self.sent_tokens[contract_address] = {
                    'name': token_data.get('baseToken', {}).get('name', 'Unknown'),
                    'count': repeat_count,
                    'short_ca': contract_address[:6] + '...' + contract_address[-3:]
                }
            
            if repeat_count == 1:
                emoji = "🟢"
                repeat_alert = ""
            elif repeat_count == 2:
                emoji = "🟡"
                repeat_alert = f"⚠️ Repeat Alert: Seen {repeat_count - 1} time(s) before"
            elif repeat_count == 3:
                emoji = "🟠"
                repeat_alert = f"❗ Repeat Alert: Seen {repeat_count - 1} time(s) before"
            else:
                emoji = "🔴"
                repeat_alert = f"🚨 Repeat Alert: Seen {repeat_count - 1} time(s) before"
            
            if repeat_count > 1:
                time_diff = int(time.time()) - last_seen
                hours_ago = time_diff // 3600
                minutes_ago = (time_diff % 3600) // 60
                if hours_ago > 0:
                    repeat_alert += f" (last seen {hours_ago} hour{'s' if hours_ago != 1 else ''} ago)"
                else:
                    repeat_alert += f" (last seen {minutes_ago} minute{'s' if minutes_ago != 1 else ''} ago)"

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

            payload = {
                'chat_id': self.chat_id,
                'text': message,
                'parse_mode': 'HTML'
            }

            with httpx.Client() as client:
                response = client.post(self.bot_url, data=payload)
            if response.status_code == 200:
                print(f"✅ Sent {token_data['full_ca'][:6]}... to Telegram")
            else:
                print(f"❌ Telegram send failed: {response.status_code} - {response.text}")
                print("Console output:", message)
        except Exception as e:
            print(f"❌ Telegram error: {e}")
            print("Console output:", message)

    def send_repeat_summary(self):
        repeats = {ca: info for ca, info in self.sent_tokens.items() if info['count'] > 1}
        if len(repeats) <= 1:
            return

        summary_lines = ["📊 Repeat Summary for This Run"]
        for ca, info in repeats.items():
            repeat_count = info['count']
            emoji = "🟡" if repeat_count == 2 else "🟠" if repeat_count == 3 else "🔴"
            summary_lines.append(f"{emoji} {info['name']} ({info['short_ca']}) - Seen {repeat_count} times")
        
        summary_message = "\n".join(summary_lines)
        payload = {
            'chat_id': self.chat_id,
            'text': summary_message,
            'parse_mode': 'HTML'
        }
        try:
            with httpx.Client() as client:
                response = client.post(self.bot_url, data=payload)
            if response.status_code == 200:
                print("✅ Sent repeat summary to Telegram")
            else:
                print(f"❌ Repeat summary send failed: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"❌ Repeat summary error: {e}")

    def parse_volume(self, volume_text):
        try:
            cleaned = ''.join(c for c in volume_text if c.isdigit() or c in '.KM')
            if 'K' in cleaned:
                return float(cleaned.replace('K', '')) * 1000
            elif 'M' in cleaned:
                return float(cleaned.replace('M', '')) * 1000000
            return float(cleaned)
        except ValueError:
            raise ValueError(f"Cannot parse volume: {volume_text}")

    def scrape_source(self, url, source_name, volume_selector, name_selector, ca_selector):
        tokens = []
        driver = None
        try:
            print(f"Starting scrape from {source_name} at {url}")
            options = Options()
            options.add_argument('--headless=new')
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            options.add_argument('--window-size=1920,1080')
            options.add_experimental_option('excludeSwitches', ['enable-automation'])
            options.add_experimental_option('useAutomationExtension', False)

            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
            driver.set_page_load_timeout(60)  # Set a 60-second timeout for page load
            driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': '''
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    })
                '''
            })

            driver.get(url)
            print(f"Waiting for elements on {source_name}...")
            WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.CLASS_NAME, 'g-table-row')))
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            print(f"Scraped {len(soup.select('.g-table-row'))} rows from {source_name}")
        except Exception as e:
            print(f"{source_name} scrape error: {e}")
            return tokens
        finally:
            if driver:
                driver.quit()
                print(f"Closed driver for {source_name}")

        token_elements = soup.select('.g-table-row[data-row-key^="sol_"]')
        print(f"{source_name} found {len(token_elements)} token elements")
        for token in token_elements[:20]:
            row_key = token.get('data-row-key', '')
            row_ca = row_key.replace('sol_', '') if row_key.startswith('sol_') else ''
            link_elem = token.select_one('a[href*="/sol/token/"]') or token.select_one('a[href*="/solana/"]')
            full_ca = link_elem['href'].split('/')[-1] if link_elem else row_ca
            ca_elem = token.select_one(ca_selector)
            ca_display = ca_elem.text.strip() if ca_elem else ''
            print(f"Found CA: {ca_display[:6]}... (Full: {full_ca})")
            if full_ca:
                name_elem = token.select_one(name_selector) or token.select_one('.css-b9ade')
                volume_elem = token.select_one(volume_selector)
                if volume_elem and name_elem:
                    volume_text = volume_elem.text.strip()
                    try:
                        volume = self.parse_volume(volume_text)
                        token_data = {
                            'name': name_elem.text.strip(),
                            'contract': ca_display or full_ca[:6] + '...' + full_ca[-3:],
                            'full_ca': full_ca,
                            'volume': volume,
                            'source': source_name
                        }
                        tokens.append(token_data)
                    except ValueError as e:
                        print(f"Invalid volume format for {full_ca[:6]}...: {volume_text}")
                else:
                    print(f"Missing data for {full_ca[:6]}...")
        return tokens

    def scrape_all(self):
        print("Scraping tokens...")
        self.all_tokens.extend(self.scrape_source(
            self.gmgn_url, "GMGN", ".css-13rmpsu, .css-1e617o2, .css-15y8kgm, .css-nxsojn", ".css-9enbzl", ".css-vps9hc"
        ))
        return self.all_tokens

    def get_dexscreener_pairs(self, chain, pair_addresses):
        all_pairs = []
        headers = {"User-Agent": "Mozilla/5.0 (compatible; TokenFilterBot/1.0)"}
        for pair in pair_addresses:
            url = f"https://api.dexscreener.com/latest/dex/pairs/{chain}/{pair}"
            print(f"Requesting DexScreener pair: {url}")
            try:
                response = requests.get(url, headers=headers)
                print(f"Status code for {pair}: {response.status_code}")
                if response.status_code != 200:
                    print(f"Error fetching pair: {response.status_code} - {response.text}")
                    continue
                data = response.json()
                pairs = data.get('pairs', []) or [data.get('pair')] if data.get('pair') else []
                if not pairs:
                    print(f"No pairs found for {pair}")
                    continue
                all_pairs.extend(pairs)
                time.sleep(1)
            except requests.exceptions.RequestException as e:
                print(f"Request failed for {pair}: {e}")
            except ValueError as e:
                print(f"JSON decode error for {pair}: {e} - Response: {response.text}")
        return all_pairs

    def get_token_profiles(self, chain_id, token_addresses):
        all_profiles = []
        headers = {"User-Agent": "Mozilla/5.0 (compatible; TokenFilterBot/1.0)"}
        for address in token_addresses:
            url = f"https://api.dexscreener.com/tokens/v1/{chain_id}/{address}"
            print(f"Fetching token profile: {url}")
            try:
                response = requests.get(url, headers=headers)
                print(f"Status code for {address}: {response.status_code}")
                if response.status_code != 200:
                    print(f"Error fetching profile: {response.status_code} - {response.text}")
                    continue
                data = response.json()
                if not data:
                    print("Empty profile response")
                    continue
                if isinstance(data, list):
                    all_profiles.extend(data)
                elif isinstance(data, dict):
                    all_profiles.append(data)
                time.sleep(1)
            except requests.exceptions.RequestException as e:
                print(f"Request failed: {e}")
            except ValueError as e:
                print(f"JSON decode error: {e} - Response: {response.text}")
        return all_profiles

    def filter_tokens(self, token_profiles, gmgn_tokens, token_name=""):
        current_time = int(time.time())
        filtered_tokens = []
        gmgn_ca_set = {token['full_ca'] for token in gmgn_tokens}
        for token in token_profiles:
            ca = token.get('baseToken', {}).get('address', '').lower()
            if ca not in gmgn_ca_set:
                continue
            market_cap = token.get('marketCap', 0)
            liquidity = token.get('liquidity', {}).get('usd', 0)
            volume_24h = token.get('volume', {}).get('h24', 0)
            name = token.get('baseToken', {}).get('name', '')
            created_timestamp = token.get('pairCreatedAt', 0) // 1000
            age_seconds = current_time - created_timestamp
            print(f"Token {ca}: Market Cap=${market_cap}, Liquidity=${liquidity}, 24h Volume=${volume_24h}, Age={age_seconds/3600:.2f} hours")
            
            if (market_cap < 150000 and liquidity >= 11000 and volume_24h >= 100000 and 3600 < age_seconds < 2419200):
                if not token_name or token_name.lower() in name.lower():
                    token['full_ca'] = ca
                    filtered_tokens.append(token)
                    self.send_to_telegram(token)
        return filtered_tokens

    def run_analysis(self):
        print("Running gmgn.ai scrape...")
        gmgn_tokens = self.scrape_all()
        if not gmgn_tokens:
            print("No tokens found from gmgn.ai")
            return None

        print("Fetching DexScreener data...")
        chain = "solana"
        known_pairs = ["58oQChx4yWmvKdwLLZzBi4ChoCc2fqCUWBkwMihLYQo2"]
        all_pairs = self.get_dexscreener_pairs(chain, known_pairs)

        token_addresses = set()
        for pair in all_pairs:
            token_addresses.add(pair['baseToken']['address'])
            token_addresses.add(pair['quoteToken']['address'])
        for token in gmgn_tokens:
            token_addresses.add(token['full_ca'])

        if not token_addresses:
            print("No token addresses collected")
            return None

        print(f"Total unique token addresses: {len(token_addresses)}")
        token_profiles = self.get_token_profiles(chain, list(token_addresses))
        print(f"Total token profiles fetched: {len(token_profiles)}")

        if not token_profiles:
            print("No token profiles fetched")
            return None

        print("Filtering tokens...")
        filtered_tokens = self.filter_tokens(token_profiles, gmgn_tokens)
        print(f"Filtered tokens count: {len(filtered_tokens)}")
        
        self.send_repeat_summary()
        return filtered_tokens

def main():
    print(f"Script run started at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    telegram_bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID')
    if not telegram_bot_token or not telegram_chat_id:
        raise ValueError("Telegram credentials not provided. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in environment variables or .env file.")
    analyzer = TokenAnalyzer(telegram_bot_token, telegram_chat_id)
    tokens = analyzer.run_analysis()
    if tokens:
        print("\nTokens Found:")
        for token in tokens:
            print(f"Name: {token.get('baseToken', {}).get('name', 'Unknown')}, Contract: {token['full_ca']}, Market Cap: ${token.get('marketCap', 0):,.2f}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Script failed: {e}")
        raise
