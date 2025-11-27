import os
import json
import random
import time
from datetime import datetime
from playwright.sync_api import sync_playwright

def human_delay(min_seconds=5, max_seconds=10):
    """Random delay to mimic human behavior"""
    delay = random.uniform(min_seconds, max_seconds)
    print(f"  Waiting {delay:.1f} seconds...")
    time.sleep(delay)

def random_mouse_movement(page):
    """Simulate natural mouse movement"""
    try:
        viewport_size = page.viewport_size
        if viewport_size:
            x = random.randint(100, viewport_size['width'] - 100)
            y = random.randint(100, viewport_size['height'] - 100)
            page.mouse.move(x, y)
    except:
        pass

def scrape_solar_data():
    """
    Scrape solar generation data from Soliscloud with human-like behavior
    """
    
    username = os.environ.get('SOLIS_USERNAME')
    password = os.environ.get('SOLIS_PASSWORD')
    
    if not username or not password:
        raise ValueError("SOLIS_USERNAME and SOLIS_PASSWORD must be set")
    
    os.makedirs('data', exist_ok=True)
    os.makedirs('data/daily', exist_ok=True)  # Store daily files separately
    
    with sync_playwright() as playwright:
        print("🌐 Launching browser...")
        
        # Use more human-like browser settings
        browser = playwright.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-blink-features=AutomationControlled'
            ]
        )
        
        # Create context with realistic settings
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='en-ZA',
            timezone_id='Africa/Johannesburg',
            extra_http_headers={
                'Accept-Language': 'en-ZA,en;q=0.9',
            }
        )
        
        # Remove webdriver detection
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)
        
        page = context.new_page()
        
        try:
            # Navigate to login page
            print("📱 Navigating to Soliscloud...")
            page.goto("https://www.soliscloud.com/login?redirect=/station", 
                      wait_until="networkidle", 
                      timeout=60000)
            
            human_delay(3, 6)
            random_mouse_movement(page)
            
            # Fill username with human-like typing
            print("👤 Entering username...")
            username_field = page.get_by_role("textbox", name="Username/Email")
            username_field.click()
            human_delay(1, 2)
            
            # Type with realistic delays
            for char in username:
                username_field.type(char, delay=random.randint(50, 150))
            
            human_delay(5, 8)
            random_mouse_movement(page)
            
            # Fill password
            print("🔑 Entering password...")
            password_field = page.get_by_role("textbox", name="Password")
            password_field.click()
            human_delay(1, 2)
            
            for char in password:
                password_field.type(char, delay=random.randint(50, 150))
            
            human_delay(5, 8)
            random_mouse_movement(page)
            
            # Accept privacy policy
            print("✅ Accepting privacy policy...")
            page.locator("div").filter(has_text="I have agreedPrivacy Policy").locator("span").nth(1).click()
            
            human_delay(6, 9)
            random_mouse_movement(page)
            
            # Click login
            print("🔐 Logging in...")
            page.get_by_role("button", name="Login").click()
            page.wait_for_load_state("networkidle", timeout=60000)
            
            human_delay(7, 10)
            random_mouse_movement(page)
            
            # Search for plant
            print("🔍 Searching for plant...")
            search_box = page.get_by_role("textbox", name="Search for Plant/Address/ID")
            search_box.click()
            human_delay(2, 4)
            
            for char in "1st":
                search_box.type(char, delay=random.randint(100, 200))
            
            human_delay(5, 8)
            search_box.press("Enter")
            
            human_delay(6, 10)
            random_mouse_movement(page)
            
            # Click on first result
            print("📊 Opening plant details...")
            with page.expect_popup(timeout=30000) as page1_info:
                page.locator("td:nth-child(2) > .cell").first.click()
            
            page1 = page1_info.value
            page1.wait_for_load_state("networkidle", timeout=60000)
            
            human_delay(7, 10)
            
            # Move mouse on new page
            try:
                page1.mouse.move(random.randint(200, 600), random.randint(200, 400))
            except:
                pass
            
            human_delay(5, 8)
            
            # Download export
            print("💾 Downloading export...")
            with page1.expect_download(timeout=30000) as download_info:
                page1.get_by_role("button", name="Export").click()
            
            download = download_info.value
            
            # Save with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            date_str = datetime.now().strftime("%Y-%m-%d")
            file_extension = download.suggested_filename.split('.')[-1] if '.' in download.suggested_filename else 'xls'
            
            # Save to daily folder with date
            daily_path = f"data/daily/{date_str}.{file_extension}"
            download.save_as(daily_path)
            
            # Also save as "latest" for easy access
            latest_path = f"data/solar_export_latest.{file_extension}"
            download.save_as(latest_path)
            
            print(f"✅ Download saved to: {daily_path}")
            print(f"✅ Latest copy saved to: {latest_path}")
            
            # Save metadata
            metadata = {
                "success": True,
                "timestamp": datetime.now().isoformat(),
                "date": date_str,
                "daily_path": daily_path,
                "latest_path": latest_path,
                "file_extension": file_extension,
                "scrape_time": datetime.now().strftime("%H:%M:%S")
            }
            
            with open('data/last_scrape.json', 'w') as f:
                json.dump(metadata, f, indent=2)
            
            print("✅ Scraping completed successfully!")
            
        except Exception as e:
            print(f"❌ Error occurred: {str(e)}")
            
            metadata = {
                "success": False,
                "timestamp": datetime.now().isoformat(),
                "error": str(e)
            }
            
            with open('data/last_scrape.json', 'w') as f:
                json.dump(metadata, f, indent=2)
            
            raise
            
        finally:
            human_delay(2, 4)
            context.close()
            browser.close()
            print("🔒 Browser closed")


if __name__ == "__main__":
    scrape_solar_data()
