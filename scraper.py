import os
import json
import random
import time
import re
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
    
    print(f"🔐 Using username: {username[:3]}***")
    
    os.makedirs('data', exist_ok=True)
    os.makedirs('data/daily', exist_ok=True)
    
    # Check if we have saved auth state in repository
    use_auth_state = False
    auth_state_file = 'data/auth_state_encoded.txt'
    
    if os.path.exists(auth_state_file):
        try:
            print("🔓 Found saved authentication state")
            import base64
            
            # Read and decode the auth state
            with open(auth_state_file, 'r') as f:
                encoded = f.read()
            
            auth_data = base64.b64decode(encoded).decode()
            
            # Save to temp file
            with open('auth_state_temp.json', 'w') as f:
                f.write(auth_data)
            
            use_auth_state = True
            print("✅ Using saved authentication state from repository")
        except Exception as e:
            print(f"⚠️  Could not use auth state: {e}")
            print("   Will login normally")
    else:
        print("ℹ️  No saved auth state found, will login normally")
    
    with sync_playwright() as playwright:
        print("🌐 Launching browser...")
        
        browser = playwright.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-blink-features=AutomationControlled',
            ]
        )
        
        # Create context with or without saved state
        if use_auth_state and os.path.exists('auth_state_temp.json'):
            print("🔓 Loading saved session...")
            context = browser.new_context(
                storage_state='auth_state_temp.json',
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080},
            )
        else:
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080},
                locale='en-US',
                timezone_id='America/New_York',
            )
        
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)
        
        page = context.new_page()
        
        try:
            if use_auth_state:
                # If using saved auth, go directly to station page
                print("📱 Navigating to station page (using saved session)...")
                page.goto("https://www.soliscloud.com/station", 
                          wait_until="networkidle", 
                          timeout=60000)
                
                human_delay(3, 5)
                
                # Check if we're actually logged in
                current_url = page.url
                if "login" in current_url:
                    print("⚠️  Saved session expired, logging in normally...")
                    use_auth_state = False
                    page.goto("https://www.soliscloud.com/login?redirect=/station", 
                              wait_until="networkidle", 
                              timeout=60000)
                else:
                    print("✅ Session still valid, skipping login")
            
            if not use_auth_state:
                # Normal login process
                print("📱 Navigating to login page...")
                page.goto("https://www.soliscloud.com/login?redirect=/station", 
                          wait_until="networkidle", 
                          timeout=60000)
                
                human_delay(3, 6)
                random_mouse_movement(page)
                
                # Fill username
                print("👤 Entering username...")
                username_field = page.get_by_role("textbox", name="Username/Email")
                username_field.click()
                human_delay(1, 2)
                
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
                try:
                    page.locator("div").filter(has_text=re.compile(r"^I have agreedPrivacy Policy$")).locator("span").nth(1).click()
                except:
                    print("  Privacy policy already accepted")
                
                human_delay(6, 9)
                random_mouse_movement(page)
                
                # Click login
                print("🔐 Logging in...")
                page.get_by_role("button", name="Login").click()
                
                # Wait for navigation
                print("⏳ Waiting for redirect...")
                try:
                    page.wait_for_url("**/station**", timeout=30000)
                except:
                    # Check if we're stuck on login
                    if "login" in page.url:
                        page.screenshot(path="data/debug_login_failed.png")
                        raise Exception("Login failed - still on login page. Check for captcha or wrong credentials.")
                
                page.wait_for_load_state("networkidle", timeout=60000)
                human_delay(7, 10)
            
            # At this point we should be on the station page
            print(f"📍 Current URL: {page.url}")
            random_mouse_movement(page)
            
            # Search for plant
            print("🔍 Searching for plant...")
            search_box = page.get_by_role("textbox", name="Search for Plant/Address/ID")
            search_box.wait_for(state="visible", timeout=30000)
            search_box.click()
            human_delay(2, 4)
            
            # Type search query
            for char in "1st":
                search_box.type(char, delay=random.randint(100, 200))
            
            human_delay(5, 8)
            random_mouse_movement(page)
            
            # Press Enter
            search_box.press("Enter")
            
            human_delay(6, 10)
            random_mouse_movement(page)
            
            # Click on first result and wait for popup
            print("📊 Opening plant details...")
            with page.expect_popup(timeout=30000) as page1_info:
                page.locator("td:nth-child(2) > .cell").first.click()
            
            page1 = page1_info.value
            
            # Wait for popup to fully load
            print("⏳ Waiting for plant details to load...")
            page1.wait_for_load_state("networkidle", timeout=60000)
            
            human_delay(7, 10)
            
            print(f"📍 Popup URL: {page1.url}")
            
            # Download export
            print("💾 Clicking export button...")
            with page1.expect_download(timeout=30000) as download_info:
                page1.get_by_role("button", name="Export").click()
            
            download = download_info.value
            
            # Save files
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            date_str = datetime.now().strftime("%Y-%m-%d")
            file_extension = download.suggested_filename.split('.')[-1] if '.' in download.suggested_filename else 'xls'
            
            daily_path = f"data/daily/{date_str}.{file_extension}"
            download.save_as(daily_path)
            
            latest_path = f"data/solar_export_latest.{file_extension}"
            download.save_as(latest_path)
            
            print(f"✅ Download saved to: {daily_path}")
            print(f"✅ Latest copy saved to: {latest_path}")
            
            # Save the current auth state for next time
            if not use_auth_state:
                try:
                    import base64
                    
                    # Save as encoded text file
                    auth_json = context.storage_state()
                    encoded = base64.b64encode(json.dumps(auth_json).encode()).decode()
                    
                    with open('data/auth_state_encoded.txt', 'w') as f:
                        f.write(encoded)
                    
                    print("💾 Saved authentication state for next run")
                except Exception as e:
                    print(f"⚠️  Could not save auth state: {e}")
            
            metadata = {
                "success": True,
                "timestamp": datetime.now().isoformat(),
                "date": date_str,
                "daily_path": daily_path,
                "latest_path": latest_path,
                "file_extension": file_extension,
                "scrape_time": datetime.now().strftime("%H:%M:%S"),
                "used_saved_auth": use_auth_state
            }
            
            with open('data/last_scrape.json', 'w') as f:
                json.dump(metadata, f, indent=2)
            
            print("✅ Scraping completed successfully!")
            
        except Exception as e:
            print(f"❌ Error occurred: {str(e)}")
            print(f"📍 Last known URL: {page.url if page else 'unknown'}")
            
            try:
                page.screenshot(path="data/debug_error.png")
                print("📸 Error screenshot saved")
            except:
                pass
            
            metadata = {
                "success": False,
                "timestamp": datetime.now().isoformat(),
                "error": str(e),
                "last_url": page.url if page else 'unknown'
            }
            
            with open('data/last_scrape.json', 'w') as f:
                json.dump(metadata, f, indent=2)
            
            raise
            
        finally:
            # Cleanup temp file
            if os.path.exists('auth_state_temp.json'):
                os.remove('auth_state_temp.json')
            
            human_delay(2, 4)
            context.close()
            browser.close()
            print("🔒 Browser closed")


if __name__ == "__main__":
    scrape_solar_data()
