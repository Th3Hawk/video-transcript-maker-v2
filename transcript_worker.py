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
    player_locator = page.locator(".flowplayer")
    cc_button_locator = page.locator(".fp-cc").first

    await player_locator.scroll_into_view_if_needed()
    await page.wait_for_selector(".flowplayer", state="visible", timeout=20000)
    await player_locator.click()
    await page.wait_for_timeout(500)
    await cc_button_locator.scroll_into_view_if_needed()
    await page.wait_for_selector(".fp-cc", state="visible", timeout=20000)
    await cc_button_locator.click()
    await page.wait_for_timeout(500)
    await player_locator.hover(timeout=5000)
    await cc_button_locator.click(timeout=20000)
    await page.wait_for_timeout(500)
    await page.locator(".fp-menu").get_by_text("On", exact=True).click(timeout=20000)

async def handle_viebit_url(page: 'Page'):
    print("  - Detected Viebit platform. Executing trigger sequence...")
    await page.locator(".vjs-big-play-button").click(timeout=20000)
    await page.locator(".vjs-play-control").click(timeout=20000)
    await page.wait_for_timeout(500)
    await page.locator("button.vjs-subs-caps-button").click(timeout=20000)
    await page.locator('.vjs-menu-item:has-text("English")').click(timeout=20000)

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
