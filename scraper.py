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


def clear_and_type(page, locator, value, label="field"):
    """
    Bulletproof field clearing + human-like typing.
    Handles autocomplete dropdowns and pre-filled values.
    """
    # Focus the field
    locator.click()
    human_delay(0.3, 0.7)

    # CRITICAL: Dismiss any autocomplete dropdown FIRST, before clearing
    # Otherwise the dropdown will re-insert the suggestion when we type
    page.keyboard.press("Escape")
    human_delay(0.2, 0.5)

    # Re-focus after Escape (Escape can blur some inputs)
    locator.click()
    human_delay(0.2, 0.4)

    # Select all existing content with Ctrl+A then delete it
    page.keyboard.press("Control+A")
    human_delay(0.1, 0.3)
    page.keyboard.press("Delete")
    human_delay(0.3, 0.6)

    # Verify the field is actually empty - if not, force-clear via JS
    current = locator.input_value()
    if current:
        print(f"  ⚠️ {label} still had '{current[:20]}...' after clear, force-clearing")
        # Set value to empty AND dispatch input event so Vue updates its model
        locator.evaluate("""
            el => {
                el.value = '';
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
            }
        """)
        human_delay(0.3, 0.6)

    # Now type character-by-character with human-like delays
    for char in value:
        locator.type(char, delay=random.randint(50, 150))

    # Dismiss any autocomplete that appeared during typing
    page.keyboard.press("Escape")
    human_delay(0.5, 1)

    # Final verification
    final = locator.input_value()
    if final != value:
        print(f"  ⚠️ {label} mismatch! Expected '{value[:3]}...', got '{final[:6]}...'")
    else:
        print(f"  ✅ {label} entered correctly ({len(final)} chars)")


def click_privacy_checkbox(page):
    """
    Click the Element-UI privacy checkbox properly so Vue's reactive state updates.
    Tries multiple selectors and verifies the checkbox is actually checked.
    """
    print("✅ Clicking privacy policy checkbox...")

    # Strategy 1: Click the visible checkbox inner span (Element-UI's clickable target)
    selectors_to_try = [
        '.el-checkbox__inner',
        '.el-checkbox__label',
        'label.el-checkbox',
        '.el-checkbox',
        'text=I have read and agree',
    ]

    for selector in selectors_to_try:
        try:
            element = page.locator(selector).first
            if element.is_visible(timeout=2000):
                element.click(timeout=3000)
                human_delay(1, 2)

                # Verify Vue actually updated the state by checking for is-checked class
                checked_count = page.locator('.el-checkbox.is-checked').count()
                if checked_count > 0:
                    print(f"  ✅ Checkbox checked via selector: {selector}")
                    return True
                else:
                    print(f"  ↻ Selector {selector} clicked but not checked, trying next")
        except Exception as e:
            print(f"  ↻ Selector {selector} failed: {str(e)[:60]}")
            continue

    # Strategy 2: Last-resort JS click on the underlying input + dispatch proper events
    print("  ↻ Falling back to JS click...")
    try:
        result = page.evaluate("""
            () => {
                const inner = document.querySelector('.el-checkbox__inner');
                if (inner) {
                    inner.click();
                    return { method: 'js-inner-click', success: true };
                }
                return { method: 'none', success: false };
            }
        """)
        human_delay(1, 2)

        checked_count = page.locator('.el-checkbox.is-checked').count()
        if checked_count > 0:
            print(f"  ✅ Checkbox checked via JS: {result}")
            return True
    except Exception as e:
        print(f"  ⚠️ JS fallback failed: {e}")

    print("  ❌ Could not check privacy checkbox")
    return False


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

            with open(auth_state_file, 'r') as f:
                encoded = f.read()

            auth_data = base64.b64decode(encoded).decode()

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
                print("📱 Navigating to station page (using saved session)...")
                page.goto("https://www.soliscloud.com/station",
                          wait_until="networkidle",
                          timeout=60000)

                human_delay(3, 5)

                # Strict check: are we on the station page or back on login?
                current_url = page.url
                if "/login" in current_url:
                    print("⚠️  Saved session expired, logging in normally...")
                    use_auth_state = False
                    page.goto("https://www.soliscloud.com/login?redirect=/station",
                              wait_until="networkidle",
                              timeout=60000)
                else:
                    print(f"✅ Session still valid: {current_url}")

            if not use_auth_state:
                # Normal login process
                print("📱 Navigating to login page...")
                page.goto("https://www.soliscloud.com/login?redirect=/station",
                          wait_until="networkidle",
                          timeout=60000)

                human_delay(3, 6)
                random_mouse_movement(page)

                # Fill username with bulletproof clearing
                print("👤 Entering username...")
                username_field = page.get_by_role("textbox", name="Username/Email")
                username_field.wait_for(state="visible", timeout=15000)
                clear_and_type(page, username_field, username, label="Username")

                human_delay(3, 5)
                random_mouse_movement(page)

                # Fill password with bulletproof clearing
                print("🔑 Entering password...")
                password_field = page.get_by_role("textbox", name="Password")
                password_field.wait_for(state="visible", timeout=15000)
                clear_and_type(page, password_field, password, label="Password")

                human_delay(3, 5)
                random_mouse_movement(page)

                # Properly click the privacy checkbox via real DOM event
                checkbox_ok = click_privacy_checkbox(page)
                if not checkbox_ok:
                    page.screenshot(path="data/debug_checkbox_failed.png", full_page=True)
                    raise Exception("Could not check privacy policy checkbox")

                human_delay(2, 3)
                random_mouse_movement(page)

                # Click login
                print("🔐 Clicking Login button...")
                page.get_by_role("button", name="Login").click()

                # Wait for redirect — STRICT check: pathname must leave /login
                # (the previous code matched **/station** which falsely matched
                # the ?redirect=/station query string)
                print("⏳ Waiting for redirect away from login page...")
                try:
                    page.wait_for_function(
                        "() => !window.location.pathname.includes('/login')",
                        timeout=30000
                    )
                    print(f"  ✅ Redirected to: {page.url}")
                except Exception:
                    current_url = page.url
                    print(f"  ❌ Still on login page: {current_url}")

                    # Diagnostic: capture what's blocking us
                    try:
                        # Check for visible Element-UI error/warning messages
                        error_msgs = page.locator(
                            '.el-message, .el-form-item__error, .el-tooltip__popper, .error-message'
                        ).all_inner_texts()
                        error_msgs = [m.strip() for m in error_msgs if m.strip()]
                        if error_msgs:
                            print(f"  🔴 On-page messages: {error_msgs}")

                        # Check checkbox state at moment of failure
                        is_checked = page.locator('.el-checkbox.is-checked').count() > 0
                        print(f"  📋 Privacy checkbox state at failure: {'checked' if is_checked else 'UNCHECKED'}")

                        # Capture username field value for diagnostics
                        try:
                            uname_value = page.get_by_role("textbox", name="Username/Email").input_value()
                            print(f"  📋 Username field value: '{uname_value}'")
                        except:
                            pass
                    except Exception as diag_err:
                        print(f"  (diagnostic error: {diag_err})")

                    page.screenshot(path="data/debug_login_failed.png", full_page=True)
                    raise Exception("Login failed - did not leave login page")

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
                page.screenshot(path="data/debug_error.png", full_page=True)
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
            if os.path.exists('auth_state_temp.json'):
                os.remove('auth_state_temp.json')

            human_delay(2, 4)
            context.close()
            browser.close()
            print("🔒 Browser closed")


if __name__ == "__main__":
    scrape_solar_data()
