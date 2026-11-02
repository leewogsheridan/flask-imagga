"""Assignment 2: simulated IoT camera starter.

TODO: send randomly selected local images to the REST server using
multipart/form-data. This starter intentionally does not perform uploads.
Run: python device.py
"""

import os
import random
import time
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent
IMAGE_DIR = BASE_DIR / "images"
SERVER_URL = os.getenv("SERVER_URL", "http://127.0.0.1:5000")
INTERVAL_SECONDS = int(os.getenv("UPLOAD_INTERVAL_SECONDS", "10"))


def select_image():
    candidates = [
        path for path in IMAGE_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png"}
    ]
    return random.choice(candidates) if candidates else None


def upload_image(image_path):
    """TODO: POST image as multipart/form-data to SERVER_URL + '/api/image'.

    Handle timeouts and report HTTP status and JSON response. Example:
    use requests.post(..., files={'image': (...)}, timeout=...).
    """
    url = f"{SERVER_URL}/api/image"
    print(f"\n[Camera] Selecting image: {image_path.name}")
    print(f"[Camera] Uploading to {url}...")

    try:
        # Open the image file in binary read mode
        with open(image_path, "rb") as image_file:
            files = {"image": (image_path.name, image_file)}
            
            # Send HTTP POST request with a timeout to prevent hanging
            response = requests.post(url, files=files, timeout=15)

        # Check if the upload was successful (Status 200 or 201)
        if response.status_code in (200, 201):
            print(f"Success! Uploaded {image_path.name}.")
            try:
                data = response.json()
                print(f"Server Response / Tags: {data}")
            except ValueError:
                print(f"Server Response (Text): {response.text}")
        else:
            print(f"Upload failed with HTTP status {response.status_code}: {response.text}")

    except requests.Timeout:
        print(f"Error: Upload timed out while sending {image_path.name}.")
    except requests.ConnectionError:
        print(f"Error: Could not connect to the server at {SERVER_URL}. Is your Flask app running?")
    except requests.RequestException as exc:
        print(f"Network error during upload: {exc}")


def main():
    if INTERVAL_SECONDS <= 0:
        raise ValueError("UPLOAD_INTERVAL_SECONDS must be positive")
    if not IMAGE_DIR.is_dir():
        raise FileNotFoundError(f"Missing images directory: {IMAGE_DIR}")

    print(f"Simulated camera started; interval = {INTERVAL_SECONDS}s")
    try:
        while True:
            image_path = select_image()
            if image_path is None:
                print("Place .jpg or .png files in the images folder first.")
                break
            try:
                upload_image(image_path)
            except requests.RequestException as exc:
                print("Network error:", exc)
            time.sleep(INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print("\nCamera simulator stopped by user")


if __name__ == "__main__":
    main()
