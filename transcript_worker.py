import asyncio
import re
from pathlib import Path
from playwright.async_api import async_playwright, TimeoutError

def parse_vtt(vtt_content: str) -> str:
    lines = vtt_content.strip().split('\n')
    transcript_lines = []
    seen_lines = set()

    for line in lines:
        if not line.strip() or "WEBVTT" in line or "-->" in line or line.strip().isdigit():
            continue
        cleaned_line = re.sub(r'>>\s*', '', line).strip()
        if cleaned_line and cleaned_line not in seen_lines:
            transcript_lines.append(cleaned_line)
            seen_lines.add(cleaned_line)

    return "\n".join(transcript_lines)

def sanitize_filename(name: str) -> str:
    sanitized = re.sub(r'[\\/*?:"<>|]', "", name).strip()
    return (sanitized[:150] + '...') if len(sanitized) > 150 else sanitized

async def handle_granicus_url(page: 'Page'):
    print("  - Detected Granicus platform. Executing trigger sequence...")

    try:
        # Wait for the player to exist at all (even if hidden)
        await page.wait_for_selector(".flowplayer", timeout=15000)
        player_locator = page.locator(".flowplayer")
        await player_locator.scroll_into_view_if_needed()
        await page.mouse.move(100, 100)
        await page.wait_for_timeout(1000)

        # Click to start the player even if it's not visible
        await page.evaluate("""
            () => {
                const player = document.querySelector('.flowplayer');
                if (player) player.click();
            }
        """)
        await page.wait_for_timeout(1000)

        # Try toggling captions
        cc_button = page.locator(".fp-cc").first
        if await cc_button.is_visible(timeout=5000):
            await cc_button.click()
            await page.locator(".fp-menu").get_by_text("On", exact=True).click(timeout=10000)
        else:
            print("  - ⚠️ Captions button not visible — continuing anyway.")

    except Exception as e:
        print(f"  - ❌ Could not complete Granicus interaction: {e}")


async def handle_viebit_url(page: 'Page'):
    print("  - Detected Viebit platform. Executing trigger sequence...")
    try:
        # These may not be needed if VTT file is intercepted early
        play_button = page.locator(".vjs-big-play-button")
        if await play_button.is_visible(timeout=5000):
            await play_button.click()
            await page.wait_for_timeout(500)

        cc_button = page.locator("button.vjs-subs-caps-button")
        if await cc_button.is_visible(timeout=5000):
            await cc_button.click()
            await page.locator('.vjs-menu-item:has-text("English")').click(timeout=10000)

    except Exception as e:
        print(f"  - ⚠️ Non-critical error during Viebit interaction: {e}")


async def process_url(url: str):
    print(f"\n▶️ Processing: {url}")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        vtt_future = asyncio.Future()

        async def handle_response(response):
            if ".vtt" in response.url and not vtt_future.done():
                print(f"  - ✅ Intercepted VTT file: {response.url}")
                try:
                    vtt_future.set_result(await response.text())
                except Exception as e:
                    vtt_future.set_exception(e)

        page.on("response", handle_response)

        try:
            print("  - Navigating and listening for network traffic...")
            await page.goto(url, wait_until="load", timeout=45000)

            if "granicus.com" in url:
                await handle_granicus_url(page)
            elif "viebit.com" in url:
                await handle_viebit_url(page)
            else:
                print(f"  - ❌ FAILED: Unknown platform. Could not process URL.")
                await browser.close()
                return

            print("  - Waiting for VTT file to be captured by network listener...")
            vtt_content = await asyncio.wait_for(vtt_future, timeout=20)
            print("  - VTT content captured successfully!")

            transcript = parse_vtt(vtt_content)
            print(f"✅ Transcript returned")
            return transcript

        except asyncio.TimeoutError:
            print("  - ❌ FAILED: Timed out waiting for VTT file.")
        except Exception as e:
            print(f"  - ❌ An unexpected error occurred: {e}")
        finally:
            await browser.close()
