#!/usr/bin/env python3
import base64
import datetime
import glob
import http.client
import json
import logging
import os
import shutil
import sys
import urllib.request
import uuid

MEDIA_DIR = r"C:\Users\user\.openclaw\media\tool-image-generation"
LOG_PATH = r"C:\Users\user\.openclaw\logs\manga_pipeline.log"
SENTINEL_PATH = os.path.join(MEDIA_DIR, "manga_latest.png")
LEMONADE_BASE = "http://localhost:13305/api/v1"
FLUX_MODEL = "Flux-2-Klein-9B-GGUF"
MANGA_PREFIX = "manga panel, black and white ink, screentone shading, bold outlines"
DISCORD_API = "discord.com"

logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s %(message)s",
)
log = logging.getLogger(__name__)


def get_latest_image() -> str | None:
    images = [
        f for f in glob.glob(os.path.join(MEDIA_DIR, "image-*.png"))
        if not f.endswith("manga_latest.png")
    ]
    return max(images, key=os.path.getmtime) if images else None


def save_image(b64_data: str) -> str:
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = os.path.join(MEDIA_DIR, f"image-1---manga-{ts}.png")
    with open(out_path, "wb") as f:
        f.write(base64.b64decode(b64_data))
    shutil.copy2(out_path, SENTINEL_PATH)
    return out_path


def flux_generate(prompt: str) -> str:
    log.info("flux → GENERATE")
    payload = json.dumps({
        "model": FLUX_MODEL,
        "prompt": prompt,
        "n": 1,
        "size": "512x512",
        "width": 512,
        "height": 512,
        "steps": 6,
        "cfg_scale": 3.5,
    }).encode()
    req = urllib.request.Request(
        f"{LEMONADE_BASE}/images/generations",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": "Bearer lemonade"},
    )
    with urllib.request.urlopen(req, timeout=150) as resp:
        data = json.loads(resp.read())
    log.info("flux → GENERATE complete")
    return data["data"][0]["b64_json"]


def flux_edit(prompt: str, image_path: str) -> str:
    log.info("flux → EDIT")
    boundary = uuid.uuid4().hex
    with open(image_path, "rb") as f:
        image_data = f.read()

    def field(name: str, value: str) -> bytes:
        return (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n"
        ).encode()

    body = b"".join([
        field("model", FLUX_MODEL),
        field("prompt", prompt),
        field("n", "1"),
        field("size", "512x512"),
        field("steps", "6"),
        field("cfg_scale", "3.5"),
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="image"; filename="image.png"\r\n'
            f"Content-Type: image/png\r\n\r\n"
        ).encode() + image_data + b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ])

    conn = http.client.HTTPConnection("localhost", 13305, timeout=150)
    conn.request(
        "POST", "/api/v1/images/edits",
        body=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Authorization": "Bearer lemonade",
        },
    )
    resp = conn.getresponse()
    data = json.loads(resp.read())
    conn.close()
    log.info("flux → EDIT complete")
    return data["data"][0]["b64_json"]


def post_image_to_discord(image_path: str, channel_id: str, token: str) -> None:
    log.info("discord → posting image")
    boundary = uuid.uuid4().hex
    with open(image_path, "rb") as f:
        image_data = f.read()

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="files[0]"; filename="manga.png"\r\n'
        f"Content-Type: image/png\r\n\r\n"
    ).encode() + image_data + f"\r\n--{boundary}--\r\n".encode()

    conn = http.client.HTTPSConnection(DISCORD_API, timeout=30)
    conn.request(
        "POST",
        f"/api/v10/channels/{channel_id}/messages",
        body=body,
        headers={
            "Authorization": f"Bot {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    resp = conn.getresponse()
    resp.read()
    conn.close()
    log.info("discord → image posted")


def main() -> None:
    user_message = os.environ.get("OPENCLAW_USER_MESSAGE", "").strip()
    channel_id = os.environ.get("OPENCLAW_CHANNEL_ID", "")
    token = os.environ.get("DISCORD_BOT_TOKEN", "")

    if not user_message or not channel_id or not token:
        latest = get_latest_image()
        if latest:
            try:
                shutil.copy2(latest, SENTINEL_PATH)
            except OSError:
                pass
        return

    log.info(f'message: "{user_message}"')
    prompt = f"{MANGA_PREFIX}, {user_message}"

    try:
        if os.path.exists(SENTINEL_PATH):
            b64 = flux_edit(prompt, SENTINEL_PATH)
        else:
            b64 = flux_generate(prompt)

        out_path = save_image(b64)
        post_image_to_discord(out_path, channel_id, token)

        print(f'MANGA_GENERATED_IMAGE: {out_path}')
        print(f'Image posted. Look at the image above and write one short dramatic manga caption for what you see.')

    except Exception as e:
        log.error(f"pipeline failed: {e}")
        print(f"MANGA_ERROR: {e}", file=sys.stderr)
        latest = get_latest_image()
        if latest:
            try:
                shutil.copy2(latest, SENTINEL_PATH)
            except OSError:
                pass


if __name__ == "__main__":
    main()
