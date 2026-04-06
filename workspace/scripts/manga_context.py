#!/usr/bin/env python3
"""
manga_context.py - Injects the latest generated manga image path into MangaBot context.

Runs as a preRunScript before every message in the manga channel.
Finds the most recently modified PNG in the image-generation media folder
and prints it to stdout so OpenClaw can inject it into the model's context.

If no images exist yet (first generation ever), prints nothing.
"""

import os
import glob

MEDIA_DIR = r"C:\Users\user\.openclaw\media\tool-image-generation"


def get_latest_image():
    pattern = os.path.join(MEDIA_DIR, "*.png")
    images = glob.glob(pattern)
    if not images:
        return None
    return max(images, key=os.path.getmtime)


def main():
    latest = get_latest_image()
    if latest:
        # Normalize to forward slashes for consistency
        path = os.path.normpath(latest)
        print(f"MANGA_LATEST_IMAGE: {path}")
    # If no image exists, print nothing — Qwen will generate from scratch


if __name__ == "__main__":
    main()
