import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = Path("/home/jewboy420/.terminus.env")
LEGACY_ENV_FILE = Path("/home/jewboy420/.antigravity_dashboard.env")

# App Brand
APP_NAME = "Terminus"
APP_TAGLINE = "The terminal you can reach from anywhere"

# Default network settings
HOST = "0.0.0.0"
PORT = 9120

# Authentication
AUTH_ENABLED = True
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "terminus"
SECRET_KEY = "terminus-secure-control-plane-key-2026"

# Shell & Directories
DEFAULT_SHELL = os.environ.get("SHELL", "/bin/bash")
WORKING_DIRECTORY = "/home/jewboy420"

# Load overrides
for ef in [LEGACY_ENV_FILE, ENV_FILE]:
    if ef.exists():
        with open(ef, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("\"'")
                    if key == "PORT":
                        try:
                            PORT = int(val)
                        except ValueError:
                            pass
                    elif key == "HOST":
                        HOST = val
                    elif key == "AUTH_ENABLED":
                        AUTH_ENABLED = val.lower() in ("true", "1", "yes")
                    elif key == "USERNAME":
                        DEFAULT_USERNAME = val
                    elif key == "PASSWORD":
                        DEFAULT_PASSWORD = val
                    elif key == "SECRET_KEY":
                        SECRET_KEY = val
