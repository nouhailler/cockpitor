"""Local-only launcher. Copy the displayed token into the interface, never into a URL."""

import os
import secrets
import sys
from pathlib import Path

import uvicorn

if os.geteuid() == 0:
    sys.exit("Lancer LocalCockpit avec un utilisateur non root.")
os.environ.setdefault("LOCALCOCKPIT_TOKEN", secrets.token_urlsafe(32))
print(
    "Jeton local (valable jusqu’au redémarrage) : " + os.environ["LOCALCOCKPIT_TOKEN"], flush=True
)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
uvicorn.run("app.main:app", host="127.0.0.1", port=8765, access_log=False)
