import asyncio
import os
import shutil
import subprocess
import time
from playwright.async_api import async_playwright
import imageio_ffmpeg
from generate_lofi import generate_lofi_track

ARTIFACT_DIR = "/config/.gemini/antigravity/brain/e9aea601-cb8e-4fa5-a8b2-dcce549afeb4"
TEMP_VIDEO_DIR = os.path.join(ARTIFACT_DIR, "video_temp")
SILENT_VIDEO_PATH = os.path.join(TEMP_VIDEO_DIR, "silent_demo.webm")
AUDIO_PATH = "upbeat_lofi.wav"
FINAL_WEBM_PATH = os.path.join(ARTIFACT_DIR, "demo_video.webm")
FINAL_MP4_PATH = os.path.join(ARTIFACT_DIR, "demo_video.mp4")

async def record_demo():
    os.makedirs(TEMP_VIDEO_DIR, exist_ok=True)
    os.makedirs(ARTIFACT_DIR, exist_ok=True)

    # 1. Generate Upbeat Lo-Fi Audio Track
    print("Generating upbeat lo-fi background music track...")
    generate_lofi_track(AUDIO_PATH)

    # 2. Record Browser Demo Video via Playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path="/usr/bin/google-chrome",
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 850},
            record_video_dir=TEMP_VIDEO_DIR,
            record_video_size={"width": 1280, "height": 850}
        )
        page = await context.new_page()

        print("Navigating to NovaSmart Travel Concierge frontend...")
        await page.goto("https://travel-planner-frontend-771704089299.us-east1.run.app", wait_until="networkidle")
        await page.wait_for_timeout(2500)

        # Prompt 1: Click Example Prompt Chip for 3-day Tokyo trip
        print("Submitting Prompt 1 (Tokyo 3-day trip itinerary)...")
        chips = await page.query_selector_all(".chip")
        if chips and len(chips) > 0:
            await chips[0].click()
        else:
            await page.fill("#input", "Plan a 3-day Tokyo trip with budget")
            await page.click("button[type='submit']")

        print("Waiting for Agent response to Prompt 1...")
        await page.wait_for_selector(".msg.agent", timeout=120000)
        await page.wait_for_selector(".typing-indicator", state="detached", timeout=120000)
        print("Prompt 1 finished. Pausing video...")
        await page.wait_for_timeout(4000)

        # Prompt 2: Richer prompt showing tool calls (weather & image generation)
        prompt_2 = "Generate a postcard image of Mt Fuji with cherry blossoms and show current weather in Tokyo"
        print(f"Submitting Prompt 2: '{prompt_2}'...")
        await page.fill("#input", prompt_2)
        await page.wait_for_timeout(1000)
        await page.click("button[type='submit']")

        print("Waiting for Agent response to Prompt 2...")
        await page.wait_for_function("document.querySelectorAll('.msg.agent').length >= 2", timeout=120000)
        await page.wait_for_selector(".typing-indicator", state="detached", timeout=120000)
        print("Prompt 2 finished. Scrolling to view rendered postcard image card...")
        await page.evaluate("window.scrollTo({top: document.body.scrollHeight, behavior: 'smooth'})")
        await page.wait_for_timeout(6000)

        video_path_obj = page.video
        await context.close()
        await browser.close()

        if video_path_obj:
            saved_raw_video = await video_path_obj.path()
            shutil.copy(saved_raw_video, SILENT_VIDEO_PATH)

    # 3. Merge Recorded Video + Upbeat Lo-Fi Audio with FFmpeg
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    print("Muxing recorded demo video with upbeat lo-fi background music...")

    # Output WEBM with Vorbis/Opus audio
    cmd_webm = [
        ffmpeg_exe, "-y",
        "-i", SILENT_VIDEO_PATH,
        "-i", AUDIO_PATH,
        "-c:v", "copy",
        "-c:a", "libopus",
        "-b:a", "128k",
        "-shortest",
        FINAL_WEBM_PATH
    ]
    res_webm = subprocess.run(cmd_webm, capture_output=True, text=True)
    if res_webm.returncode != 0:
        print("FFmpeg webm warning:", res_webm.stderr[:300])

    # Output MP4 with AAC audio for broad compatibility
    cmd_mp4 = [
        ffmpeg_exe, "-y",
        "-i", SILENT_VIDEO_PATH,
        "-i", AUDIO_PATH,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "22",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        FINAL_MP4_PATH
    ]
    res_mp4 = subprocess.run(cmd_mp4, capture_output=True, text=True)
    if res_mp4.returncode != 0:
        print("FFmpeg mp4 warning:", res_mp4.stderr[:300])

    shutil.rmtree(TEMP_VIDEO_DIR, ignore_errors=True)

    if os.path.exists(FINAL_WEBM_PATH):
        print(f"Final WebM demo video with lo-fi audio saved to: {FINAL_WEBM_PATH} ({os.path.getsize(FINAL_WEBM_PATH)} bytes)")
    if os.path.exists(FINAL_MP4_PATH):
        print(f"Final MP4 demo video with lo-fi audio saved to: {FINAL_MP4_PATH} ({os.path.getsize(FINAL_MP4_PATH)} bytes)")

if __name__ == "__main__":
    asyncio.run(record_demo())
