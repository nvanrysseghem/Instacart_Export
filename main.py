#!/usr/bin/env python3
import os
import json
from dotenv import load_dotenv
from datetime import datetime
import argparse
import random
import time
import getpass
import platform
import sys

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium_stealth import stealth

# Try to import webdriver_manager for automatic driver management
try:
    from webdriver_manager.chrome import ChromeDriverManager
    from webdriver_manager.core.os_manager import ChromeType
    HAS_WEBDRIVER_MANAGER = True
except ImportError:
    HAS_WEBDRIVER_MANAGER = False
    print("Note: webdriver-manager not installed. Install with: pip3 install webdriver-manager")

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Function to get ChromeDriver for Raspberry Pi
def get_chrome_driver(options):
    """Create Chrome driver with Raspberry Pi compatibility"""
    
    # Detect if running on Raspberry Pi
    is_raspberry_pi = 'arm' in platform.machine().lower() or 'aarch' in platform.machine().lower()
    
    if is_raspberry_pi:
        print("Detected Raspberry Pi (ARM architecture)")
        
        # Method 1: Try using webdriver-manager (recommended)
        if HAS_WEBDRIVER_MANAGER:
            try:
                print("Attempting to use webdriver-manager...")
                service = Service(ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install())
                return webdriver.Chrome(service=service, options=options)
            except Exception as e:
                print(f"webdriver-manager failed: {e}")
        
        # Method 2: Try using system chromium directly
        try:
            print("Attempting to use system Chromium as driver...")
            
            # For Raspberry Pi, we can try to use chromium-browser directly with Selenium
            # This works if chromedriver is integrated into chromium
            options.binary_location = '/usr/bin/chromium-browser'
            
            # Try without specifying driver path (Selenium 4.6+ can find it automatically)
            try:
                return webdriver.Chrome(options=options)
            except:
                pass
            
            # Try with explicit service
            possible_drivers = [
                '/usr/lib/chromium-browser/chromedriver',
                '/usr/bin/chromedriver',
                '/usr/local/bin/chromedriver',
                '/snap/bin/chromium.chromedriver'
            ]
            
            for driver_path in possible_drivers:
                if os.path.exists(driver_path):
                    print(f"Found driver at: {driver_path}")
                    service = Service(driver_path)
                    return webdriver.Chrome(service=service, options=options)
        
        except Exception as e:
            print(f"System chromium approach failed: {e}")
        
        # Method 3: Final fallback - let Selenium try to figure it out
        print("Attempting default Selenium driver discovery...")
        return webdriver.Chrome(options=options)
    
    else:
        # For non-Raspberry Pi systems, use standard approach
        if HAS_WEBDRIVER_MANAGER:
            service = Service(ChromeDriverManager().install())
            return webdriver.Chrome(service=service, options=options)
        else:
            return webdriver.Chrome(options=options)

# Configure headless options for Chrome
def get_headless_options():
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    
    # Additional options for Raspberry Pi
    if 'arm' in platform.machine().lower():
        options.add_argument('--disable-software-rasterizer')
        options.add_argument('--disable-features=VizDisplayCompositor')
    
    return options

# Function to get default screen dimensions (optimized for headless Raspberry Pi)
def get_screen_dimensions():
    return 1920, 1080  # Default full HD resolution for headless use

# Convert a date/time string from 'Jan 30' or 'Jan 30, 2024' format to '2024-01-30 00:00' format.
def convert_datetime(input_string):
    current_year = datetime.now().year
    date_format = '%b %d, %Y'
    if ',' not in input_string:
        input_string += f", {current_year}"  # Add the current year
    input_datetime = datetime.strptime(input_string, date_format)
    output_string = input_datetime.strftime('%Y-%m-%d %H:%M')
    return output_string

# Return true if the second date (of format '2024-01-30 18:23') is greater than the first one (of format '2024-01-30-18-23').
def is_web_date_greater(date_str_from_arg, date_str_from_web):
    format_a = '%Y-%m-%d %H:%M'
    format_b = '%Y-%m-%d %H:%M'
    date_a = datetime.strptime(date_str_from_arg, format_a)
    date_b = datetime.strptime(date_str_from_web, format_b)
    if date_b > date_a:
        return True
    else:
        return False

def login(driver: webdriver.Chrome):
    driver.get("https://www.instacart.ca/store/account")
    time.sleep(5)
    if (driver.current_url == "https://www.instacart.ca/store/account"):
        return
    email = os.getenv("INSTACART_EMAIL")
    if (email): # If not defined, you can login manually
        email_input = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, "//input[@placeholder='Email']")))
        continue_button = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, "//button/span[text()='Continue']")))
        email_input.send_keys(email)
        continue_button.click()
    WebDriverWait(driver, 3600).until(EC.url_changes(driver.current_url)) # Long timeout needed for the rest of the login process to be done manually

def get_orders_list(driver: webdriver.Chrome, after_str=None):
    driver.get("https://www.instacart.ca/store/account/orders")
    # Keep clicking "load more orders" until no more can be loaded    
    while click_load_more(driver):
        if after_str is not None:
            last_item_date = order_info_div_to_dict(driver.find_elements(By.XPATH, "//div[@class=\"e-undqvw\"]").pop())["dateTime"]
            if not is_web_date_greater(after_str, last_item_date):
                break
    # Find all 'li' elements with 'data-radium' attribute equal to 'true' and save their inner HTML to an array
    items = list(map(order_info_div_to_dict, driver.find_elements(By.XPATH, "//li/div[1]/div[1]/div[2]/a/../..")))
    if after_str is not None:
        items = list(filter(lambda x: is_web_date_greater(after_str, x["dateTime"]), items))
    items.reverse() # Oldest first
    return items

# Function to find and click the "load more orders" button
def click_load_more(driver):
    try:
        load_more_button = WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located((By.XPATH, "//button/span[text()='Load more orders']"))
        )
        load_more_button.click()
        return True
    except:
        return False

def order_info_div_to_dict(order_info_div):
    order_url_p = order_info_div.find_element(By.XPATH, "./div[2]/a")
    order_url = order_url_p.get_attribute("href")
    order_details_div = order_url_p.find_element(By.XPATH, '../../div[1]')
    order_date_text = convert_datetime(' '.join(order_details_div.find_element(By.XPATH, "./div[1]/p[1]").text.split()[1:]))
    order_item_count_text = order_details_div.find_element(By.XPATH, "./div[2]/p[1]").text
    cancelled = False
    try:
        order_details_div.find_element(By.XPATH, "./div[1]/p[3]").text
        cancelled = True
    except:
        pass
    order_total_text = order_details_div.find_element(By.XPATH, "./div[3]/p[1]").text[1:]
    return {
        "dateTime": order_date_text,
        "itemCount": order_item_count_text,
        "total": order_total_text,
        "url": order_url,
        "cancelled": cancelled
    }

def get_order_details(driver: webdriver.Chrome, order_url: str):
    driver.get(order_url)
    show_items_button = WebDriverWait(driver, 3600).until( # A very long wait to allow CloudFlare bot detection time to finish
        EC.element_to_be_clickable((By.ID, "order-status-items-card"))
    )
    show_items_button.click()
    delivery_photo_url = None
    try:
        delivery_photo_url = driver.find_element(By.XPATH, "//img[contains(@src, 'orderdeliveryphoto')]").get_attribute("src")
    except:
        pass
    return {
        "delivery_photo_url": delivery_photo_url,
        "items": list(map(item_info_div_to_dict, driver.find_elements(By.XPATH, "//div[@id='items-card-expanded']/ul/li/div")))
    }

def item_info_div_to_dict(item_info_div):
    item_thumbnail_url = item_info_div.find_element(By.XPATH, "./div[1]/div[1]/button/span/img").get_attribute("src")
    item_name = item_info_div.find_element(By.XPATH, "./div[1]/div[1]/div/div/button/span").text
    item_unit_info = [s.strip() for s in item_info_div.find_element(By.XPATH, "./div[1]/div[1]/div/p").text.split("•")]
    item_quantity = item_info_div.find_element(By.XPATH, "./div[1]/div[1]/div/div/div/div/p").text
    item_unit_price = item_unit_info[0][1:]
    item_unit_description = item_unit_info[1]
    return {
        "name": item_name,
        "unitPrice": item_unit_price,
        "unitDescription": item_unit_description,
        "quantity": item_quantity,
        "thumbnailUrl": item_thumbnail_url
    }

# Main function
if __name__ == "__main__":
    # Validate arguments
    output_path=""
    after_str=None
    parser = argparse.ArgumentParser()
    parser.add_argument('--file', help='Where to save the output (can be an existing file for incremental scraping)')
    parser.add_argument('--after', help='A \'Y-m-d H:M\' string to filter out orders older than a certain date/time')
    args = parser.parse_args()
    if args.file:
        output_path = args.file
    if args.after:
        after_str = args.after

    # Check for required dependencies on Raspberry Pi
    if 'arm' in platform.machine().lower() and not HAS_WEBDRIVER_MANAGER:
        print("\n" + "="*60)
        print("RASPBERRY PI DETECTED - IMPORTANT SETUP REQUIRED")
        print("="*60)
        print("\nThe chromium-chromedriver package on Raspberry Pi doesn't include")
        print("the actual driver binary. Please install webdriver-manager:")
        print("\n  pip3 install webdriver-manager\n")
        print("This will automatically download and manage ChromeDriver for you.")
        print("="*60 + "\n")
        
        response = input("Would you like to continue anyway? (y/n): ")
        if response.lower() != 'y':
            sys.exit(1)

    # Grab existing data if any and ensure you don't repeat orders
    existing_orders=[]
    if (output_path):
        if os.path.exists(output_path):
            with open(output_path, 'r') as file:
                json_array = json.load(file)
                existing_orders += json_array
    if (len(existing_orders) > 0):
        if after_str is not None:
            raise Exception("You can't use the '--after' argument with an existing orders list!")
        after_str = existing_orders[len(existing_orders) - 1]["dateTime"]
        print("You have pointed to an existing orders list. Only orders after " + after_str + " will be scraped.")

    # Setup Webdriver and load env. vars.
    load_dotenv()
    screen_width, screen_height = get_screen_dimensions()
    window_width = screen_width // 2
    window_height = screen_height
    options = Options()
    options.add_argument(f"window-size={window_width},{window_height}")
    options.add_argument(f"window-position={screen_width},0")
    
    # User data directory
    dataDir = f"/home/{getpass.getuser()}/.config/chromium"
    if not os.path.isdir(dataDir):
        dataDir = f"/home/{getpass.getuser()}/.config/google-chrome"
    if os.path.isdir(dataDir):
        options.add_argument(f"--user-data-dir={dataDir}")
        options.add_argument(f"--profile-directory=Default")
    
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    # Create driver using our compatibility function
    try:
        driver = get_chrome_driver(options)
    except Exception as e:
        print(f"\nError creating Chrome driver: {e}")
        print("\nTroubleshooting steps:")
        print("1. Install webdriver-manager: pip3 install webdriver-manager")
        print("2. Make sure Chromium is installed: sudo apt install chromium-browser")
        print("3. Try running with --headless flag")
        sys.exit(1)
    
    # Apply stealth settings
    stealth(driver,
        languages=["en-US", "en"],
        vendor="Google Inc.",
        platform="Win32",
        webgl_vendor="Intel Inc.",
        renderer="Intel Iris OpenGL Engine",
        fix_hairline=True,
    )

    # Scrape data
    try:
        login(driver=driver)
        time.sleep(random.randint(5, 15))
        orders = get_orders_list(driver=driver, after_str=after_str)
        for order in orders:
            time.sleep(random.randint(5, 15)) # Helps with bot detection
            order_details = get_order_details(driver=driver, order_url=order["url"])
            order["items"] = order_details["items"]
            order["deliveryPhotoUrl"] = order_details["delivery_photo_url"]
        driver.quit()
        orders = existing_orders + orders

        # Output
        report = json.dumps(orders, indent=4)
        print(report)
        if output_path:
            with open(output_path, 'w') as f:
                f.write(report)
    except Exception as e:
        print(f"Error during scraping: {e}")
        driver.quit()
        raise
