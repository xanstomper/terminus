"""
Terminus Remote Access & Universal Tunnel Manager
Enables seamless zero-config access from anywhere on the internet
using Cloudflare Quick Tunnels with instant QR code generation.
"""

import os
import re
import time
import subprocess
import threading
import io
import base64
from typing import Dict, Any, Optional
import qrcode
from PIL import Image

CLOUDFLARED_BIN = "/home/jewboy420/.local/bin/cloudflared"

class TunnelManager:
    def __init__(self, port: int = 9120):
        self.port = port
        self.process: Optional[subprocess.Popen] = None
        self.public_url: Optional[str] = None
        self.started_at: Optional[float] = None
        self.is_running = False
        self.error: Optional[str] = None
        self.lock = threading.Lock()
        self._reader_thread: Optional[threading.Thread] = None

    def start_tunnel(self) -> Dict[str, Any]:
        with self.lock:
            if self.is_running and self.process and self.process.poll() is None:
                return self.get_status()

            if not os.path.exists(CLOUDFLARED_BIN):
                self.error = f"cloudflared binary not found at {CLOUDFLARED_BIN}"
                return self.get_status()

            self.public_url = None
            self.error = None
            self.started_at = time.time()
            self.is_running = True

            cmd = [
                CLOUDFLARED_BIN,
                "tunnel",
                "--url", f"http://127.0.0.1:{self.port}",
                "--no-autoupdate"
            ]

            try:
                self.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1
                )
            except Exception as e:
                self.is_running = False
                self.error = str(e)
                return self.get_status()

            self._reader_thread = threading.Thread(target=self._monitor_output, daemon=True)
            self._reader_thread.start()

        # Wait up to 8 seconds for URL discovery
        for _ in range(32):
            if self.public_url:
                break
            time.sleep(0.25)

        return self.get_status()

    def _monitor_output(self):
        if not self.process or not self.process.stderr:
            return

        url_regex = re.compile(r"(https://[a-zA-Z0-9-]+\.trycloudflare\.com)")
        for line in self.process.stderr:
            if not self.is_running:
                break
            match = url_regex.search(line)
            if match:
                self.public_url = match.group(1)

        with self.lock:
            self.is_running = False

    def stop_tunnel(self) -> Dict[str, Any]:
        with self.lock:
            self.is_running = False
            self.public_url = None
            if self.process:
                try:
                    self.process.terminate()
                    self.process.wait(timeout=2)
                except Exception:
                    try:
                        self.process.kill()
                    except Exception:
                        pass
                self.process = None
            self.started_at = None
            self.error = None
        return self.get_status()

    def get_qr_data_url(self, url: str) -> str:
        try:
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=6,
                border=2,
            )
            qr.add_data(url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="#ffffff", back_color="#101014")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            return f"data:image/png;base64,{b64}"
        except Exception:
            return ""

    def get_status(self) -> Dict[str, Any]:
        running = self.is_running and (self.process is not None and self.process.poll() is None)
        uptime = int(time.time() - self.started_at) if (running and self.started_at) else 0

        qr_code = ""
        if running and self.public_url:
            qr_code = self.get_qr_data_url(self.public_url)

        return {
            "is_running": running,
            "public_url": self.public_url,
            "port": self.port,
            "uptime_seconds": uptime,
            "error": self.error,
            "qr_code": qr_code
        }


# Global instance for Terminus
tunnel_instance = TunnelManager(port=9120)
