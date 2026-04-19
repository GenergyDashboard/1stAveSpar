import os
import json
import random
import time
import re
from datetime import datetime
from playwright.sync_api import sync_playwright


def human_delay(min_seconds=5, max_seconds=10):
    """Random delay between actions."""
    delay = random.uniform(min_seconds, max_seconds)
    print(f"  Waiting {delay:.1f} seconds...")
    time.sleep(delay)


def random_mouse_movement(page):
    """Move mouse to a random viewport position."""
    try:
        viewport_size = page.viewport_size
        if viewport_size:
            x = random.randint(100, viewport_size['width'] - 100)
            y = random.randint(100, viewport_size['height'] - 100)
            page.mouse.move(x, y)
    except Exception:
        pass


def save_debug_screenshot(page, path):
    """Screenshot to path and log whether the file was actually written."""
    try:
        page.screenshot(path=path, full_page=True)
        if os.path.exists(path):
            size_kb = os.path.getsize(path) / 1024
            print(f"  📸 Screenshot saved: {path} ({size_kb:.1f} KB)")
            return True
        print(f"  ⚠️  Screenshot call returned but file missing: {path}")
        return False
    except Exception as e:
        print(f"  ⚠️  Screenshot failed for {path}: {e}")
        return False


def detect_captcha(page):
    """Return list of CAPTCHA frameworks visible on the page."""
    probes = {
        'Cloudflare Turnstile (iframe)': 'iframe[src*="turnstile"]',
        'Cloudflare Turnstile (div)': '.cf-turnstile',
        'reCAPTCHA (iframe)': 'iframe[src*="recaptcha"]',
        'reCAPTCHA (div)': '.g-recaptcha',
        'hCaptcha (iframe)': 'iframe[src*="hcaptcha"]',
        'hCaptcha (div)': '.h-captcha',
        'Slider CAPTCHA': '[class*="slider-captcha"], [class*="slide-verify"], [class*="verify-slider"]',
        'Cloudflare challenge': '#challenge-form, #cf-challenge-running',
    }
    hits = []
    for label, selector in probes.items():
        try:
            if page.locator(selector).count() > 0:
                hits.append(label)
        except Exception:
            continue
    return hits


def accept_privacy_policy(page):
    """Tick the 'I have agreed Privacy Policy' checkbox. Returns True on success."""
    print("✅ Accepting privacy policy...")

    # Element UI toggles is-checked on the label wrapper when active
    try:
        already = page.locator('label.el-checkbox.is-checked, .el-checkbox.is-checked').count()
        if already > 0:
            print("  ✅ Privacy checkbox already checked")
            return True
    except Exception:
        pass

    selectors = [
        ('text regex', lambda: page.locator("div").filter(
            has_text=re.compile(r"^I have agreedPrivacy Policy$")
        ).locator("span").nth(1)),
        ('el-checkbox__inner', lambda: page.locator('span.el-checkbox__inner').first),
        ('generic checkbox', lambda: page.locator('input[type="checkbox"]').first),
        ('label text', lambda: page.get_by_text("I have agreed", exact=False).first),
    ]

    for label, locator_fn in selectors:
        try:
            loc = locator_fn()
            if loc.is_visible(timeout=2000):
                loc.click()
                print(f"  ✅ Privacy checkbox clicked via: {label}")
                return True
        except Exception as e:
            print(f"  · selector '{label}' did not match ({type(e).__name__})")
            continue

    print("  ❌ Could not find the privacy policy checkbox")
    return False


def scrape_solar_data():
    """Scrape 1st Ave Spar solar data from SolisCloud."""

    username = os.environ.get('SOLIS_USERNAME')
    password = os.environ.get('SOLIS_PASSWORD')

    if not username or not password:
        raise ValueError("SOLIS_USERNAME and SOLIS_PASSWORD must be set")

    print(f"🔐 Using username: {username[:3]}***")

    os.makedirs('data', exist_ok=True)
    os.makedirs('data/daily', exist_ok=True)

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

        context_kwargs = {
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/120.0.0.0 Safari/537.36',
            'viewport': {'width': 1920, 'height': 1080},
            'locale': 'en-ZA',
            'timezone_id': 'Africa/Johannesburg',
        }

        if use_auth_state and os.path.exists('auth_state_temp.json'):
            print("🔓 Loading saved session...")
            context_kwargs['storage_state'] = 'auth_state_temp.json'

        context = browser.new_context(**context_kwargs)

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
                print("📱 Navigating to login page...")
                page.goto("https://www.soliscloud.com/login?redirect=/station",
                          wait_until="networkidle",
                          timeout=60000)

                human_delay(3, 6)
                random_mouse_movement(page)

                pre_hits = detect_captcha(page)
                if pre_hits:
                    print(f"  🛑 CAPTCHA detected on login page load: {pre_hits}")
                    save_debug_screenshot(page, "data/debug_captcha_preload.png")
                    raise Exception(f"CAPTCHA present before login: {pre_hits}")

                print("👤 Entering username...")
                username_field = page.get_by_role("textbox", name="Username/Email")
                username_field.click()
                human_delay(1, 2)

                for char in username:
                    username_field.type(char, delay=random.randint(50, 150))

                human_delay(5, 8)
                random_mouse_movement(page)

                print("🔑 Entering password...")
                password_field = page.get_by_role("textbox", name="Password")
                password_field.click()
                human_delay(1, 2)

                for char in password:
                    password_field.type(char, delay=random.randint(50, 150))

                human_delay(5, 8)
                random_mouse_movement(page)

                if not accept_privacy_policy(page):
                    save_debug_screenshot(page, "data/debug_no_checkbox.png")
                    raise Exception("Privacy policy checkbox not found")

                human_delay(6, 9)
                random_mouse_movement(page)

                print("🔐 Logging in...")
                login_clicked = False
                login_selectors = [
                    'button[name="Login"]',
                    'button:has-text("Login")',
                    'button:has-text("Log In")',
                    'button[type="submit"]',
                    '.login-btn',
                    '.login-button',
                ]

                for selector in login_selectors:
                    try:
                        login_btn = page.locator(selector).first
                        if login_btn.is_visible(timeout=2000):
                            login_btn.click()
                            login_clicked = True
                            print(f"  ✅ Clicked login using: {selector}")
                            break
                    except Exception:
                        continue

                if not login_clicked:
                    try:
                        page.get_by_role("button", name="Login").click()
                        login_clicked = True
                    except Exception:
                        save_debug_screenshot(page, "data/debug_no_login_btn.png")
                        raise Exception("Could not find login button")

                print("🔎 Checking for post-submit CAPTCHA...")
                page.wait_for_timeout(2500)
                post_hits = detect_captcha(page)
                if post_hits:
                    print(f"  🛑 CAPTCHA appeared after login submit: {post_hits}")
                    save_debug_screenshot(page, "data/debug_captcha_postlogin.png")
                    raise Exception(f"CAPTCHA blocking login: {post_hits}")

                print("⏳ Waiting for redirect...")
                try:
                    page.wait_for_url(lambda url: "login" not in url, timeout=15000)
                    print(f"  ✅ Redirected to: {page.url}")
                except Exception:
                    current_url = page.url
                    print(f"  ❌ Still on login page: {current_url}")

                    late_hits = detect_captcha(page)
                    if late_hits:
                        print(f"  🛑 CAPTCHA detected on late re-check: {late_hits}")

                    try:
                        error_selectors = [
                            '.el-message--error',
                            '.el-form-item__error',
                            '.error', '.alert',
                            '[class*="error"]', '.message',
                        ]
                        for sel in error_selectors:
                            errors = page.locator(sel).all_text_contents()
                            errors = [e.strip() for e in errors if e.strip()]
                            if errors:
                                print(f"  🔴 Error messages from '{sel}': {errors}")
                    except Exception:
                        pass

                    save_debug_screenshot(page, "data/debug_login_failed.png")
                    raise Exception("Login failed — credentials, CAPTCHA, or site changes")

                page.wait_for_load_state("networkidle", timeout=60000)
                human_delay(5, 7)

            print(f"📍 Current URL: {page.url}")
            random_mouse_movement(page)

            print("🔍 Searching for plant...")
            search_box = page.get_by_role("textbox", name="Search for Plant/Address/ID")
            search_box.wait_for(state="visible", timeout=30000)
            search_box.click()
            human_delay(2, 4)

            for char in "1st":
                search_box.type(char, delay=random.randint(100, 200))

            human_delay(5, 8)
            random_mouse_movement(page)

            search_box.press("Enter")

            human_delay(6, 10)
            random_mouse_movement(page)

            print("📊 Opening plant details...")
            with page.expect_popup(timeout=30000) as page1_info:
                page.locator("td:nth-child(2) > .cell").first.click()

            page1 = page1_info.value

            print("⏳ Waiting for plant details to load...")
            page1.wait_for_load_state("networkidle", timeout=60000)

            human_delay(7, 10)

            print(f"📍 Popup URL: {page1.url}")

            print("💾 Clicking export button...")
            with page1.expect_download(timeout=30000) as download_info:
                page1.get_by_role("button", name="Export").click()

            download = download_info.value

            date_str = datetime.now().strftime("%Y-%m-%d")
            file_extension = (
                download.suggested_filename.split('.')[-1]
                if '.' in download.suggested_filename else 'xls'
            )

            daily_path = f"data/daily/{date_str}.{file_extension}"
            download.save_as(daily_path)

            latest_path = f"data/solar_export_latest.{file_extension}"
            download.save_as(latest_path)

            print(f"✅ Download saved to: {daily_path}")
            print(f"✅ Latest copy saved to: {latest_path}")

            if not use_auth_state:
                try:
                    import base64

                    auth_json = context.storage_state()
                    encoded = base64.b64encode(
                        json.dumps(auth_json).encode()
                    ).decode()

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
                "used_saved_auth": use_auth_state,
            }

            with open('data/last_scrape.json', 'w') as f:
                json.dump(metadata, f, indent=2)

            print("✅ Scraping completed successfully!")

        except Exception as e:
            print(f"❌ Error occurred: {str(e)}")
            print(f"📍 Last known URL: {page.url if page else 'unknown'}")

            save_debug_screenshot(page, "data/debug_error.png")

            metadata = {
                "success": False,
                "timestamp": datetime.now().isoformat(),
                "error": str(e),
                "last_url": page.url if page else 'unknown',
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
