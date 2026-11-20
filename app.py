#!/usr/bin/env python3
"""
System One Image Sorter - Web UI Server
A lightweight, dependency-free Python web server providing an interactive GUI
for organizing and classifying images using the TypeSafe System One (Jev) model.
"""

import os
import sys
import json
import base64
import shutil
import mimetypes
import subprocess
from io import BytesIO
from pathlib import Path
from http import HTTPStatus
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# Import sorter logic
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sorter import (
    PRESETS,
    load_env_file,
    get_config,
    classify_image,
    test_api_connection,
    prepare_image
)

try:
    from PIL import Image
except ImportError:
    print("Error: Pillow is required. Run: pip install pillow")
    sys.exit(1)


SCRIPT_DIR = Path(__file__).resolve().parent
INPUT_DIR = SCRIPT_DIR / "input_images"
OUTPUT_DIR = SCRIPT_DIR / "sorted_output"
STATIC_DIR = SCRIPT_DIR / "static"

# Ensure directories exist
INPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR.mkdir(parents=True, exist_ok=True)


class SorterServerHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler for Sorter UI & API."""

    def log_message(self, format, *args):
        # Override to keep terminal clean; only log errors
        if args and str(args[1]).startswith("5"):
            super().log_message(format, *args)

    def send_json(self, data: dict, status: int = 200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/config":
            self.handle_get_config()
        elif path == "/api/images":
            self.handle_get_images()
        elif path.startswith("/api/thumbnail/"):
            self.handle_get_thumbnail(path.replace("/api/thumbnail/", ""))
        elif path == "/" or path == "/index.html":
            self.serve_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
        else:
            # Serve static files if they exist
            static_file = STATIC_DIR / path.lstrip("/")
            if static_file.exists() and static_file.is_file():
                mime, _ = mimetypes.guess_type(str(static_file))
                self.serve_file(static_file, mime or "application/octet-stream")
            else:
                self.send_error(404, "File not found")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length > 0 else b"{}"

        try:
            data = json.loads(body.decode("utf-8")) if body else {}
        except Exception:
            data = {}

        if path == "/api/test-connection":
            self.handle_test_connection(data)
        elif path == "/api/sort":
            self.handle_sort(data)
        elif path == "/api/upload":
            self.handle_upload(data)
        elif path == "/api/open-folder":
            self.handle_open_folder(data)
        else:
            self.send_error(404, "Endpoint not found")

    def handle_get_config(self):
        api_key, api_url, model = get_config(SCRIPT_DIR)
        masked_key = ""
        if api_key:
            masked_key = api_key[:10] + "..." + api_key[-6:] if len(api_key) > 16 else "***"
        self.send_json({
            "has_api_key": bool(api_key),
            "masked_key": masked_key,
            "api_url": api_url,
            "model": model or "dec-1",
            "provider": "Articul8 Bivia",
            "presets": PRESETS,
            "input_dir": str(INPUT_DIR),
            "output_dir": str(OUTPUT_DIR)
        })

    def handle_get_images(self):
        supported_exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tiff"}
        images = []
        for f in sorted(INPUT_DIR.iterdir()):
            if f.is_file() and f.suffix.lower() in supported_exts:
                images.append({
                    "name": f.name,
                    "size_bytes": f.stat().st_size,
                    "ext": f.suffix.lower()
                })
        self.send_json({"images": images, "total": len(images)})

    def handle_get_thumbnail(self, filename: str):
        target = INPUT_DIR / filename
        if not target.exists() or not target.is_file():
            self.send_error(404, "Image not found")
            return
        try:
            with Image.open(target) as img:
                img.thumbnail((240, 240))
                if img.mode not in ("RGB", "RGBA"):
                    img = img.convert("RGB")
                buf = BytesIO()
                img.save(buf, format="JPEG", quality=85)
                thumb_bytes = buf.getvalue()
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(thumb_bytes)))
                self.send_header("Cache-Control", "max-age=300")
                self.end_headers()
                self.wfile.write(thumb_bytes)
        except Exception as e:
            self.send_error(500, f"Thumbnail generation failed: {e}")

    def handle_test_connection(self, data: dict):
        api_key, api_url, model = get_config(SCRIPT_DIR)
        override_key = data.get("api_key")
        if override_key:
            api_key = override_key
        success = test_api_connection(api_key, api_url, model)
        self.send_json({"success": success})

    def handle_upload(self, data: dict):
        # Expects: {"filename": "pic.png", "base64_data": "..."}
        filename = data.get("filename", "upload.png")
        b64_str = data.get("base64_data", "")
        if not b64_str:
            self.send_json({"error": "No base64 data provided"}, 400)
            return

        # Strip any data URI prefix
        if "," in b64_str:
            b64_str = b64_str.split(",", 1)[1]

        target_path = INPUT_DIR / filename
        try:
            raw_bytes = base64.b64decode(b64_str)
            with open(target_path, "wb") as f:
                f.write(raw_bytes)
            self.send_json({"success": True, "filename": filename})
        except Exception as e:
            self.send_json({"error": str(e)}, 500)

    def handle_open_folder(self, data: dict):
        target = data.get("folder", "output")
        folder_path = OUTPUT_DIR if target == "output" else INPUT_DIR
        try:
            if sys.platform == "win32":
                os.startfile(folder_path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder_path)])
            else:
                subprocess.Popen(["xdg-open", str(folder_path)])
            self.send_json({"success": True, "path": str(folder_path)})
        except Exception as e:
            self.send_json({"error": str(e)}, 500)

    def handle_sort(self, data: dict):
        # Configuration
        api_key, api_url, model = get_config(SCRIPT_DIR)
        if not api_key:
            self.send_json({"error": "No API key configured in .env"}, 400)
            return

        categories = data.get("categories", {})
        if not categories:
            preset = data.get("preset", "general")
            categories = PRESETS.get(preset, PRESETS["general"])["categories"]

        mode = data.get("mode", "copy")
        dry_run = data.get("dry_run", False)
        context_guidance = data.get("context", "")

        selected_files = data.get("files", [])
        if not selected_files:
            # Process all in INPUT_DIR
            supported_exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tiff"}
            selected_files = [
                f.name for f in sorted(INPUT_DIR.iterdir())
                if f.is_file() and f.suffix.lower() in supported_exts
            ]

        results = []
        for filename in selected_files:
            file_path = INPUT_DIR / filename
            if not file_path.exists():
                results.append({"filename": filename, "error": "File not found"})
                continue

            try:
                res = classify_image(
                    image_path=file_path,
                    categories=categories,
                    api_key=api_key,
                    api_url=api_url,
                    model=model,
                    context_note=context_guidance
                )
                cat = res["category"]
                conf = res["confidence"]
                dest_dir = OUTPUT_DIR / cat
                dest_file = dest_dir / filename

                if not dry_run:
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    if mode == "move":
                        shutil.move(str(file_path), str(dest_file))
                        action_taken = "moved"
                    else:
                        shutil.copy2(str(file_path), str(dest_file))
                        action_taken = "copied"
                else:
                    action_taken = "dry_run"

                results.append({
                    "filename": filename,
                    "category": cat,
                    "confidence": conf,
                    "action": action_taken,
                    "destination": str(dest_file),
                    "probabilities": res["probabilities"],
                    "dimensions": res["dimensions"]
                })
            except Exception as e:
                results.append({
                    "filename": filename,
                    "error": str(e)
                })

        self.send_json({
            "success": True,
            "total_processed": len(results),
            "results": results
        })

    def serve_file(self, file_path: Path, content_type: str):
        try:
            with open(file_path, "rb") as f:
                content = f.read()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_error(500, f"Error reading file: {e}")


def run_server(port=5050):
    server_address = ("", port)
    httpd = HTTPServer(server_address, SorterServerHandler)
    print("=" * 65)
    print(" 🚀 System One Image Sorter UI Server")
    print("=" * 65)
    print(f" Web UI is live at: http://localhost:{port}")
    print(f" Input Images Directory:  {INPUT_DIR}")
    print(f" Sorted Output Directory: {OUTPUT_DIR}")
    print(" Press Ctrl+C to stop the server.")
    print("=" * 65)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
        httpd.server_close()


if __name__ == "__main__":
    port = 5050
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        port = int(sys.argv[1])
    run_server(port)
