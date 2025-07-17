#!/usr/bin/env python3
import os
import json
import logging
import argparse
import random
import time
import getpass
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from contextlib import contextmanager

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium_stealth import stealth
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class InstacartScraper:
    """Optimized Instacart order scraper for Raspberry Pi"""
    
    def __init__(self, headless: bool = True, user_data_dir: Optional[str] = None):
        self.headless = headless
        self.user_data_dir = user_data_dir
        self.driver = None
        self.wait_times = {
            'min': 3,
            'max': 10,
            'page_load': 30,
            'element': 10
        }
    
    @contextmanager
    def get_driver(self):
        """Context manager for WebDriver with proper cleanup"""
        try:
            self.driver = self._create_driver()
            yield self.driver
        finally:
            if self.driver:
                self.driver.quit()
    
    def _create_driver(self) -> webdriver.Chrome:
        """Create optimized Chrome driver for Raspberry Pi"""
        options = webdriver.ChromeOptions()
        
        # Performance optimizations for Raspberry Pi
        if self.headless:
            options.add_argument('--headless')
        
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-images')  # Don't load images during scraping
        options.add_argument('--disable-javascript')  # Disable JS where possible
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        # Window size
        options.add_argument('window-size=1280,720')
        
        # User data directory for session persistence
        if self.user_data_dir and os.path.isdir(self.user_data_dir):
            options.add_argument(f"--user-data-dir={self.user_data_dir}")
            options.add_argument("--profile-directory=Default")
        
        # Memory optimizations
        prefs = {
            'profile.default_content_setting_values': {
                'images': 2,  # Block images
                'plugins': 2,  # Block plugins
                'popups': 2,  # Block popups
                'geolocation': 2,  # Block location
                'notifications': 2,  # Block notifications
                'media_stream': 2,  # Block media stream
            },
            'profile.managed_default_content_settings': {
                'images': 2
            }
        }
        options.add_experimental_option('prefs', prefs)
        
        driver = webdriver.Chrome(options=options)
        
        # Apply stealth settings
        stealth(driver,
            languages=["en-US", "en"],
            vendor="Google Inc.",
            platform="Linux armv7l",  # Correct platform for Pi
            webgl_vendor="Broadcom",
            renderer="VideoCore IV",
            fix_hairline=True,
        )
        
        # Set page load strategy
        driver.set_page_load_timeout(self.wait_times['page_load'])
        
        return driver
    
    def _smart_wait(self) -> None:
        """Intelligent wait with randomization for bot detection avoidance"""
        wait_time = random.uniform(self.wait_times['min'], self.wait_times['max'])
        time.sleep(wait_time)
    
    def _wait_for_element(self, by: By, value: str, timeout: Optional[int] = None) -> any:
        """Wait for element with proper error handling"""
        timeout = timeout or self.wait_times['element']
        try:
            element = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((by, value))
            )
            return element
        except TimeoutException:
            logger.warning(f"Element not found: {by}={value}")
            return None
    
    def login(self, email: Optional[str] = None) -> bool:
        """Optimized login process"""
        logger.info("Starting login process")
        self.driver.get("https://www.instacart.ca/store/account")
        
        # Check if already logged in
        time.sleep(3)
        if self.driver.current_url == "https://www.instacart.ca/store/account":
            logger.info("Already logged in")
            return True
        
        # Auto-fill email if provided
        if email:
            try:
                email_input = self._wait_for_element(By.XPATH, "//input[@placeholder='Email']")
                if email_input:
                    email_input.clear()
                    email_input.send_keys(email)
                    
                    continue_button = self._wait_for_element(
                        By.XPATH, "//button/span[text()='Continue']"
                    )
                    if continue_button:
                        continue_button.click()
                        logger.info("Email submitted, waiting for manual authentication")
            except Exception as e:
                logger.error(f"Error during email submission: {e}")
        
        # Wait for manual login completion
        try:
            WebDriverWait(self.driver, 3600).until(
                lambda driver: driver.current_url == "https://www.instacart.ca/store/account"
            )
            logger.info("Login successful")
            return True
        except TimeoutException:
            logger.error("Login timeout")
            return False
    
    def get_orders_list(self, after_date: Optional[str] = None) -> List[Dict]:
        """Optimized order list retrieval"""
        logger.info("Fetching orders list")
        self.driver.get("https://www.instacart.ca/store/account/orders")
        self._smart_wait()
        
        orders = []
        last_count = 0
        
        while True:
            # Get current orders
            order_elements = self.driver.find_elements(
                By.XPATH, "//li/div[1]/div[1]/div[2]/a/../.."
            )
            
            # Parse new orders
            for element in order_elements[last_count:]:
                try:
                    order = self._parse_order_element(element)
                    if after_date and not self._is_date_after(order["dateTime"], after_date):
                        continue
                    orders.append(order)
                except Exception as e:
                    logger.warning(f"Error parsing order: {e}")
            
            last_count = len(order_elements)
            
            # Check if we should stop loading more
            if after_date and orders and not self._is_date_after(orders[-1]["dateTime"], after_date):
                break
            
            # Try to load more
            if not self._click_load_more():
                break
            
            self._smart_wait()
        
        logger.info(f"Found {len(orders)} orders")
        return list(reversed(orders))  # Return oldest first
    
    def _parse_order_element(self, element) -> Dict:
        """Parse order element with error handling"""
        order_link = element.find_element(By.XPATH, "./div[2]/a")
        order_url = order_link.get_attribute("href")
        
        details_div = element.find_element(By.XPATH, "./div[1]")
        
        # Parse date
        date_text = details_div.find_element(By.XPATH, "./div[1]/p[1]").text
        date_parts = date_text.split()[1:]
        order_date = self._convert_datetime(' '.join(date_parts))
        
        # Parse other details
        item_count = details_div.find_element(By.XPATH, "./div[2]/p[1]").text
        total = details_div.find_element(By.XPATH, "./div[3]/p[1]").text[1:]
        
        # Check if cancelled
        cancelled = False
        try:
            details_div.find_element(By.XPATH, "./div[1]/p[3]")
            cancelled = True
        except NoSuchElementException:
            pass
        
        return {
            "dateTime": order_date,
            "itemCount": item_count,
            "total": total,
            "url": order_url,
            "cancelled": cancelled
        }
    
    def _click_load_more(self) -> bool:
        """Click load more button with error handling"""
        try:
            button = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//button/span[text()='Load more orders']"))
            )
            self.driver.execute_script("arguments[0].click();", button)  # JavaScript click
            return True
        except (TimeoutException, Exception):
            return False
    
    def get_order_details(self, order_url: str) -> Dict:
        """Get order details with optimizations"""
        logger.debug(f"Fetching details for: {order_url}")
        self.driver.get(order_url)
        
        # Wait for and click items button
        try:
            show_items = WebDriverWait(self.driver, 30).until(
                EC.element_to_be_clickable((By.ID, "order-status-items-card"))
            )
            self.driver.execute_script("arguments[0].click();", show_items)
            time.sleep(2)  # Wait for expansion
        except TimeoutException:
            logger.error(f"Failed to load order details: {order_url}")
            return {"items": [], "delivery_photo_url": None}
        
        # Get delivery photo
        delivery_photo_url = None
        try:
            photo_element = self.driver.find_element(
                By.XPATH, "//img[contains(@src, 'orderdeliveryphoto')]"
            )
            delivery_photo_url = photo_element.get_attribute("src")
        except NoSuchElementException:
            pass
        
        # Get items
        items = []
        item_elements = self.driver.find_elements(
            By.XPATH, "//div[@id='items-card-expanded']/ul/li/div"
        )
        
        for element in item_elements:
            try:
                item = self._parse_item_element(element)
                items.append(item)
            except Exception as e:
                logger.warning(f"Error parsing item: {e}")
        
        return {
            "delivery_photo_url": delivery_photo_url,
            "items": items
        }
    
    def _parse_item_element(self, element) -> Dict:
        """Parse item element with error handling"""
        # Get thumbnail
        thumbnail_url = element.find_element(
            By.XPATH, "./div[1]/div[1]/button/span/img"
        ).get_attribute("src")
        
        # Get name
        name = element.find_element(
            By.XPATH, "./div[1]/div[1]/div/div/button/span"
        ).text
        
        # Get unit info
        unit_info_text = element.find_element(
            By.XPATH, "./div[1]/div[1]/div/p"
        ).text
        unit_parts = [s.strip() for s in unit_info_text.split("•")]
        
        # Get quantity
        quantity = element.find_element(
            By.XPATH, "./div[1]/div[1]/div/div/div/div/p"
        ).text
        
        return {
            "name": name,
            "unitPrice": unit_parts[0][1:] if unit_parts else "",
            "unitDescription": unit_parts[1] if len(unit_parts) > 1 else "",
            "quantity": quantity,
            "thumbnailUrl": thumbnail_url
        }
    
    @staticmethod
    def _convert_datetime(date_str: str) -> str:
        """Convert date format with current year handling"""
        current_year = datetime.now().year
        if ',' not in date_str:
            date_str += f", {current_year}"
        
        try:
            dt = datetime.strptime(date_str, '%b %d, %Y')
            return dt.strftime('%Y-%m-%d %H:%M')
        except ValueError as e:
            logger.error(f"Date parsing error: {e}")
            return date_str
    
    @staticmethod
    def _is_date_after(date1: str, date2: str) -> bool:
        """Compare dates safely"""
        try:
            dt1 = datetime.strptime(date1, '%Y-%m-%d %H:%M')
            dt2 = datetime.strptime(date2, '%Y-%m-%d %H:%M')
            return dt1 > dt2
        except ValueError:
            return False
    
    def scrape_orders(self, output_path: str, after_date: Optional[str] = None) -> List[Dict]:
        """Main scraping orchestration"""
        # Load existing orders if any
        existing_orders = []
        if os.path.exists(output_path):
            with open(output_path, 'r') as f:
                existing_orders = json.load(f)
                if existing_orders and not after_date:
                    after_date = existing_orders[-1]["dateTime"]
                    logger.info(f"Incremental scraping after: {after_date}")
        
        with self.get_driver():
            # Login
            email = os.getenv("INSTACART_EMAIL")
            if not self.login(email):
                raise Exception("Login failed")
            
            self._smart_wait()
            
            # Get orders list
            orders = self.get_orders_list(after_date)
            
            # Get details for each order
            for i, order in enumerate(orders):
                if order["cancelled"]:
                    logger.info(f"Skipping cancelled order: {order['dateTime']}")
                    continue
                
                logger.info(f"Processing order {i+1}/{len(orders)}: {order['dateTime']}")
                self._smart_wait()
                
                try:
                    details = self.get_order_details(order["url"])
                    order.update(details)
                except Exception as e:
                    logger.error(f"Error getting order details: {e}")
                    order["items"] = []
                    order["deliveryPhotoUrl"] = None
            
            # Combine with existing orders
            all_orders = existing_orders + orders
            
            # Save results
            with open(output_path, 'w') as f:
                json.dump(all_orders, f, indent=4)
            
            logger.info(f"Saved {len(all_orders)} total orders to {output_path}")
            
            return all_orders

def main():
    parser = argparse.ArgumentParser(description='Scrape Instacart orders')
    parser.add_argument('--file', required=True, help='Output JSON file path')
    parser.add_argument('--after', help='Date filter (Y-m-d H:M format)')
    parser.add_argument('--headless', action='store_true', help='Run in headless mode')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Load environment variables
    load_dotenv()
    
    # Determine Chrome user data directory
    user = getpass.getuser()
    user_data_dir = None
    
    for path in [f"/home/{user}/.config/chromium", f"/home/{user}/.config/google-chrome"]:
        if os.path.isdir(path):
            user_data_dir = path
            break
    
    # Create scraper and run
    scraper = InstacartScraper(headless=args.headless, user_data_dir=user_data_dir)
    
    try:
        scraper.scrape_orders(args.file, args.after)
    except Exception as e:
        logger.error(f"Scraping failed: {e}")
        raise

if __name__ == "__main__":
    main()
