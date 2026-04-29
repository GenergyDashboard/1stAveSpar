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


# The EXACT selector for the privacy checkbox, captured via Playwright codegen.
# The ".el-tooltip__trigger" class is the key discriminator — only the privacy
# checkbox has a tooltip attached ("Please read and agree..."), not the Remember one.
PRIVACY_CHECKBOX_SELECTOR = (
    '.el-checkbox.el-checkbox--default.el-tooltip__trigger '
    '> .el-checkbox__input > .el-checkbox__inner'
)
PRIVACY_CHECKBOX_LABEL = (
    '.el-checkbox.el-checkbox--default.el-tooltip__trigger'
)


def clear_and_type(page, locator, value, label="field"):
    """
    Bulletproof field clearing + human-like typing.
    Handles autocomplete dropdowns and pre-filled values from saved state.
    """
    locator.click()
    human_delay(0.3, 0.7)

    # Dismiss any autocomplete dropdown FIRST so it can't re-insert text while we type
    page.keyboard.press("Escape")
    human_delay(0.2, 0.5)

    locator.click()
    human_delay(0.2, 0.4)

    # Select all then delete
    page.keyboard.press("Control+A")
    human_delay(0.1, 0.3)
    page.keyboard.press("Delete")
    human_delay(0.3, 0.6)

    # Verify empty - if not, force-clear via JS with proper Vue events
    current = locator.input_value()
    if current:
        print(f"  ⚠️ {label} still had content after clear, force-clearing")
        locator.evaluate("""
            el => {
                el.value = '';
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
            }
        """)
        human_delay(0.3, 0.6)

    # Type character-by-character
    for char in value:
        locator.type(char, delay=random.randint(50, 150))

    # Dismiss any autocomplete that appeared during typing
    page.keyboard.press("Escape")
    human_delay(0.5, 1)

    # Final check
    final = locator.input_value()
    if final != value:
        print(f"  ⚠️ {label} mismatch! Expected {len(value)} chars, got {len(final)}")
    else:
        print(f"  ✅ {label} entered correctly ({len(final)} chars)")


def click_privacy_checkbox(page):
    """
    Click the privacy checkbox using the exact selector captured from
    Playwright codegen. The .el-tooltip__trigger class uniquely identifies
    the privacy checkbox (it has a tooltip; Remember doesn't).
    """
    print("✅ Clicking privacy policy checkbox...")

    try:
        checkbox = page.locator(PRIVACY_CHECKBOX_SELECTOR)
        checkbox.wait_for(state="visible", timeout=10000)
        checkbox.click()
        human_delay(1, 2)

        # Verify the specific privacy checkbox is now checked
        is_checked = page.locator(PRIVACY_CHECKBOX_LABEL).first.evaluate(
            "el => el.classList.contains('is-checked')"
        )
        if is_checked:
            print("  ✅ Privacy checkbox checked")
            return True
        else:
            print("  ⚠️ Click registered but checkbox still unchecked")
            return False
    except Exception as e:
        print(f"  ❌ Privacy checkbox click failed: {e}")
        return False


def get_checkbox_state(page, label_text):
    """Diagnostic: read is-checked class from a checkbox by its label text"""
    try:
        return page.locator(
            f'label.el-checkbox:has-text("{label_text}")'
        ).first.evaluate("el => el.classList.contains('is-checked')")
    except Exception:
        return None


def is_any_dialog_visible(page):
    """
    Return True if any Element-UI dialog wrapper is actually visible
    (display != 'none' AND has dimensions). Element UI keeps the wrapper
    in the DOM with display:none when closed, so .is_visible() alone
    can give false positives.
    """
    try:
        return page.evaluate("""
            () => {
                const wrappers = document.querySelectorAll('.el-dialog__wrapper');
                for (const w of wrappers) {
                    const cs = window.getComputedStyle(w);
                    if (cs.display !== 'none'
                        && cs.visibility !== 'hidden'
                        && w.offsetParent !== null
                        && w.getBoundingClientRect().height > 0) {
                        return true;
                    }
                }
                return false;
            }
        """)
    except Exception:
        return False


def dismiss_blocking_dialogs(page, max_attempts=4):
    """
    SolisCloud sometimes pops a modal dialog (announcements, T&C updates,
    "what's new", etc.) on the station page that intercepts pointer events
    and blocks the search box click.

    This function detects any visible .el-dialog__wrapper and tries multiple
    strategies to close it: clicking the X button, clicking common confirm
    buttons by text, and finally pressing Escape.
    """
    print("🪟 Checking for blocking dialogs...")

    if not is_any_dialog_visible(page):
        print("  ✅ No blocking dialogs detected")
        return True

    # Ordered close strategies — most specific first
    close_strategies = [
        # Element UI native close button (X in top-right)
        '.el-dialog__wrapper .el-dialog__headerbtn',
        '.el-dialog__wrapper .el-dialog__close',
        # Common confirm/dismiss buttons by visible text
        '.el-dialog__wrapper button:has-text("I Know")',
        '.el-dialog__wrapper button:has-text("I know")',
        '.el-dialog__wrapper button:has-text("Got it")',
        '.el-dialog__wrapper button:has-text("Got It")',
        '.el-dialog__wrapper button:has-text("Confirm")',
        '.el-dialog__wrapper button:has-text("Agree")',
        '.el-dialog__wrapper button:has-text("Accept")',
        '.el-dialog__wrapper button:has-text("OK")',
        '.el-dialog__wrapper button:has-text("Ok")',
        '.el-dialog__wrapper button:has-text("Close")',
        '.el-dialog__wrapper button:has-text("Skip")',
        '.el-dialog__wrapper button:has-text("Later")',
        '.el-dialog__wrapper button:has-text("Cancel")',
        # Last-resort: any primary button inside the dialog
        '.el-dialog__wrapper .el-button--primary',
        '.el-dialog__wrapper button',
    ]

    for attempt in range(max_attempts):
        if not is_any_dialog_visible(page):
            print(f"  ✅ All dialogs dismissed after {attempt} attempt(s)")
            return True

        print(f"  ⚠️  Blocking dialog detected (attempt {attempt + 1}/{max_attempts})")
        dismissed = False

        for selector in close_strategies:
            try:
                btns = page.locator(selector)
                count = btns.count()
                for i in range(count):
                    btn = btns.nth(i)
                    try:
                        if btn.is_visible():
                            btn.click(timeout=3000)
                            print(f"  🖱️  Clicked: {selector}")
                            human_delay(1, 2)
                            dismissed = True
                            break
                    except Exception:
                        continue
                if dismissed:
                    break
            except Exception:
                continue

        # Fallback: press Escape
        if not dismissed:
            try:
                page.keyboard.press("Escape")
                print("  ⌨️  Pressed Escape")
                human_delay(1, 2)
            except Exception:
                pass

        # Last-ditch: hide all visible dialog wrappers via JS
        if attempt == max_attempts - 2 and is_any_dialog_visible(page):
            try:
                hidden = page.evaluate("""
                    () => {
                        let n = 0;
                        document.querySelectorAll('.el-dialog__wrapper').forEach(w => {
                            const cs = window.getComputedStyle(w);
                            if (cs.display !== 'none') {
                                w.style.display = 'none';
                                n++;
                            }
                        });
                        // Also remove modal backdrop if present
                        document.querySelectorAll('.v-modal').forEach(m => m.remove());
                        document.body.style.overflow = '';
                        return n;
                    }
                """)
                if hidden:
                    print(f"  🧹 Force-hid {hidden} dialog(s) via JS")
                    human_delay(1, 2)
            except Exception as e:
                print(f"  (force-hide failed: {e})")

    still_visible = is_any_dialog_visible(page)
    if still_visible:
        print("  ⚠️  Could not dismiss all dialogs after max attempts")
        try:
            page.screenshot(path="data/debug_dialog_stuck.png", full_page=True)
            print("  📸 Saved data/debug_dialog_stuck.png")
        except Exception:
            pass
        return False

    print("  ✅ Dialogs cleared")
    return True


def scrape_solar_data():
    """Scrape solar generation data from Soliscloud"""

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
                print("📱 Navigating to login page...")
                page.goto("https://www.soliscloud.com/login?redirect=/station",
                          wait_until="networkidle",
                          timeout=60000)

                human_delay(3, 6)
                random_mouse_movement(page)

                # Username with bulletproof clearing (fixes the "Ross SaundersRoss Saunders" bug)
                print("👤 Entering username...")
                username_field = page.get_by_role("textbox", name="Username/Email")
                username_field.wait_for(state="visible", timeout=15000)
                clear_and_type(page, username_field, username, label="Username")

                human_delay(3, 5)
                random_mouse_movement(page)

                # Password
                print("🔑 Entering password...")
                password_field = page.get_by_role("textbox", name="Password")
                password_field.wait_for(state="visible", timeout=15000)
                clear_and_type(page, password_field, password, label="Password")

                human_delay(3, 5)
                random_mouse_movement(page)

                # Privacy checkbox - exact selector from codegen
                checkbox_ok = click_privacy_checkbox(page)
                if not checkbox_ok:
                    page.screenshot(path="data/debug_checkbox_failed.png", full_page=True)
                    raise Exception("Could not check privacy policy checkbox")

                human_delay(2, 3)
                random_mouse_movement(page)

                # Click login
                print("🔐 Clicking Login button...")
                page.get_by_role("button", name="Login").click()

                # Wait for redirect - STRICT pathname check
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

                    try:
                        error_msgs = page.locator(
                            '.el-message, .el-form-item__error, .el-tooltip__popper, .error-message'
                        ).all_inner_texts()
                        error_msgs = [m.strip() for m in error_msgs if m.strip()]
                        if error_msgs:
                            print(f"  🔴 On-page messages: {error_msgs}")

                        privacy_checked = get_checkbox_state(page, "I have read and agree")
                        if privacy_checked is None:
                            print(f"  📋 Privacy checkbox: could not read state")
                        else:
                            mark = "checked ✅" if privacy_checked else "UNCHECKED ❌"
                            print(f"  📋 Privacy checkbox: {mark}")

                        remember_checked = get_checkbox_state(page, "Remember")
                        if remember_checked is not None:
                            mark = "checked" if remember_checked else "unchecked"
                            print(f"  📋 Remember checkbox: {mark}")

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

            # Should be on station page now
            print(f"📍 Current URL: {page.url}")
            random_mouse_movement(page)

            # Dismiss any blocking modal dialogs (announcements, T&C updates, etc.)
            # SolisCloud started showing these and they intercept pointer events,
            # blocking the search box click.
            dismiss_blocking_dialogs(page)
            human_delay(1, 2)

            # Search for plant
            print("🔍 Searching for plant...")
            search_box = page.get_by_role("textbox", name="Search for Plant/Address/ID")
            search_box.wait_for(state="visible", timeout=30000)

            # Click with dialog-recovery: if a dialog re-appears between dismissal
            # and click, retry once after dismissing again, then force-click as
            # a last resort so we never get stuck.
            try:
                search_box.click(timeout=10000)
            except Exception as click_err:
                print(f"  ⚠️  Search click failed: {click_err}")
                print("  🔁 Re-checking for dialogs and retrying...")
                dismiss_blocking_dialogs(page)
                human_delay(1, 2)
                try:
                    search_box.click(timeout=10000)
                except Exception as click_err2:
                    print(f"  ⚠️  Second click failed: {click_err2}")
                    print("  💪 Force-clicking search box (bypassing pointer-event check)")
                    search_box.click(force=True, timeout=10000)

            human_delay(2, 4)

            for char in "1st":
                search_box.type(char, delay=random.randint(100, 200))

            human_delay(5, 8)
            random_mouse_movement(page)

            search_box.press("Enter")

            human_delay(6, 10)
            random_mouse_movement(page)

            # Click first result, wait for popup
            print("📊 Opening plant details...")
            with page.expect_popup(timeout=30000) as page1_info:
                page.locator("td:nth-child(2) > .cell").first.click()

            page1 = page1_info.value

            print("⏳ Waiting for plant details to load...")
            page1.wait_for_load_state("networkidle", timeout=60000)

            human_delay(7, 10)

            print(f"📍 Popup URL: {page1.url}")

            # Dismiss any dialogs on the popup window too, just in case
            dismiss_blocking_dialogs(page1)
            human_delay(1, 2)

            # Download export
            print("💾 Clicking export button...")
            export_btn = page1.get_by_role("button", name="Export")
            with page1.expect_download(timeout=30000) as download_info:
                try:
                    export_btn.click(timeout=10000)
                except Exception as exp_err:
                    print(f"  ⚠️  Export click failed: {exp_err}")
                    print("  🔁 Dismissing dialogs on popup and retrying...")
                    dismiss_blocking_dialogs(page1)
                    human_delay(1, 2)
                    try:
                        export_btn.click(timeout=10000)
                    except Exception:
                        print("  💪 Force-clicking export button")
                        export_btn.click(force=True, timeout=10000)

            download = download_info.value

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            date_str = datetime.now().strftime("%Y-%m-%d")
            file_extension = download.suggested_filename.split('.')[-1] if '.' in download.suggested_filename else 'xls'

            daily_path = f"data/daily/{date_str}.{file_extension}"
            download.save_as(daily_path)

            latest_path = f"data/solar_export_latest.{file_extension}"
            download.save_as(latest_path)

            print(f"✅ Download saved to: {daily_path}")
            print(f"✅ Latest copy saved to: {latest_path}")

            # Save auth state for next time
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
