print("Loading integrated_token_analyzer.py...")

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

class TokenAnalyzer:
    def __init__(self, telegram_bot_token, telegram_chat_id):
        print("Initializing TokenAnalyzer...")
        self.bot_token = telegram_bot_token
        self.chat_id = str(telegram_chat_id)
        self.bot_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        self.gmgn_url = "https://gmgn.ai/?chain=sol"
        self.all_tokens = []
        print("Finished initializing TokenAnalyzer")

    def send_to_telegram(self, token_data):
        try:
            message = (
                f"🚀 Filtered Token!\n"
                f"Contract: <code>{token_data['full_ca']}</code>\n"
                f"Name: <b>{token_data.get('baseToken', {}).get('name', 'Unknown')}</b>\n"
                f"Market Cap: ${token_data.get('marketCap', 0):,.2f}\n"
                f"Liquidity: ${token_data.get('liquidity', {}).get('usd', 0):,.2f}\n"
                f"24h Volume: ${token_data.get('volume', {}).get('h24', 0):,.2f}\n"
                f"Age: {(int(time.time()) - token_data.get('pairCreatedAt', 0) // 1000) / 3600:.2f} hours\n"
                f"Source: DexScreener (via gmgn.ai)"
            )
            payload = {'chat_id': self.chat_id, 'text': message, 'parse_mode': 'HTML'}
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
                f"🚀 Filtered Token!\n"
                f"Contract: <code>{token_data.get('full_ca', 'Unknown')}</code>\n"
                f"Name: <b>{token_data.get('baseToken', {}).get('name', 'Unknown')}</b>\n"
                f"Market Cap: ${token_data.get('marketCap', 0):,.2f}\n"
                f"Liquidity: ${token_data.get('liquidity', {}).get('usd', 0):,.2f}\n"
                f"24h Volume: ${token_data.get('volume', {}).get('h24', 0):,.2f}\n"
                f"Age: {(int(time.time()) - token_data.get('pairCreatedAt', 0) // 1000) / 3600:.2f} hours\n"
                f"Source: DexScreener (via gmgn.ai)"
            )
            print(message)

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
            options = Options()
            options.add_argument('--headless=new')
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
            driver.get(url)
            WebDriverWait(driver, 60).until(
                EC.presence_of_element_located((By.CLASS_NAME, 'g-table-row'))
            )
            page_source = driver.page_source
        except Exception as e:
            print(f"{source_name} scrape error: {e}")
            return tokens
        finally:
            if driver:
                driver.quit()

        soup = BeautifulSoup(page_source, 'html.parser')
        token_elements = soup.select('.g-table-row[data-row-key^="sol_"]')
        print(f"{source_name} found {len(token_elements)} token elements")
        for token in token_elements[:12]:
            row_key = token.get('data-row-key', '')
            row_ca = row_key.replace('sol_', '') if row_key.startswith('sol_') else ''
            link_elem = token.select_one('a[href*="/sol/token/"]') or token.select_one('a[href*="/solana/"]')
            full_ca = link_elem['href'].split('/')[-1] if link_elem else row_ca
            ca_elem = token.select_one(ca_selector)
            ca_display = ca_elem.text.strip() if ca_elem else ''
            print(f"Found CA from {source_name}: {ca_display[:6]}...{ca_display[-3:]} (Full: {full_ca})")
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
                        print(f"Invalid volume format for {full_ca[:6]}...{full_ca[-3:]}: {volume_text}")
                else:
                    print(f"Missing data for {full_ca[:6]}...{full_ca[-3:]} in {source_name}")
        return tokens

    def scrape_all(self):
        print("Scraping tokens...")
        self.all_tokens.extend(self.scrape_source(
            self.gmgn_url, "GMGN", ".css-13rmpsu", ".css-9enbzl", ".css-j2at52"
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
                print(f"Raw response for {pair}: {data}")
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
                print(f"Raw profile response: {response.text}")
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
        print(f"gmgn.ai CAs: {gmgn_ca_set}")
        print(f"Profile CAs: {[token.get('baseToken', {}).get('address', '') for token in token_profiles]}")
        for token in token_profiles:
            ca = token.get('baseToken', {}).get('address', '')
            if ca not in gmgn_ca_set:
                print(f"Skipping {ca} - not in gmgn.ai list")
                continue
            market_cap = token.get('marketCap', 0)
            liquidity = token.get('liquidity', {}).get('usd', 0)
            volume_24h = token.get('volume', {}).get('h24', 0)
            name = token.get('baseToken', {}).get('name', '')
            created_timestamp = token.get('pairCreatedAt', 0) // 1000
            age_seconds = current_time - created_timestamp
            
            print(f"Token: {name}, Market Cap: {market_cap}, Liquidity: {liquidity}, Volume: {volume_24h}, Age: {age_seconds}s, Created: {token.get('pairCreatedAt', 0)}")
            if (market_cap < 150000 and
                liquidity >= 11000 and
                volume_24h >= 100000 and
                3600 < age_seconds < 2419200):
                if not token_name or token_name.lower() in name.lower():
                    token['full_ca'] = ca
                    filtered_tokens.append(token)
                    self.send_to_telegram(token)
            else:
                print(f"Failed criteria - Market Cap: {market_cap < 150000}, Liquidity: {liquidity >= 11000}, Volume: {volume_24h >= 100000}, Age: {3600 < age_seconds < 2419200}")
        return filtered_tokens

    def run_analysis(self):
        print("Running gmgn.ai scrape...")
        gmgn_tokens = self.scrape_all()
        if not gmgn_tokens:
            print("No tokens found from gmgn.ai")
            return None

        print("\nFetching DexScreener data...")
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
        
        if not filtered_tokens:
            print("\nNo tokens met all criteria.")
        return filtered_tokens

def main():
    telegram_bot_token = '7153885229:AAFho6grVBCi9vuGNnczNRw5QwSOtERsAd0'
    telegram_chat_id = '5305709800'
    analyzer = TokenAnalyzer(telegram_bot_token, telegram_chat_id)
    tokens = analyzer.run_analysis()
    if tokens:
        print("\nTokens Found:")
        for token in tokens:
            print(f"Name: {token.get('baseToken', {}).get('name', 'Unknown')}, Contract: {token['full_ca']}, Market Cap: ${token.get('marketCap', 0):,.2f}")

if __name__ == "__main__":
    main()

# Launch command:
# python C:\Users\fonsw\OneDrive\Desktop\TokenFinder\integrated_token_analyzer.py