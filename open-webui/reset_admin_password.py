"""
Reset the Open WebUI admin password locally. Run it yourself so the new password never appears in any chat:

  ! ~/open-webui/venv/bin/python ~/open-webui/reset_admin_password.py

It backs up the database first, asks for the new password twice (hidden), and updates only the auth row for
admin@studio.local. No restart is needed.
"""
import getpass
import shutil
import sqlite3
import sys
import time
from pathlib import Path

import bcrypt

DB = Path.home() / "open-webui" / "data" / "webui.db"
EMAIL = "admin@studio.local"

if not DB.exists():
    sys.exit(f"Database not found: {DB}")
pw = getpass.getpass("New password (min 8 chars): ")
if len(pw) < 8:
    sys.exit("Too short; nothing changed.")
if pw != getpass.getpass("Repeat password: "):
    sys.exit("Passwords differ; nothing changed.")

backup = DB.with_name(f"webui.db.bak_{int(time.time())}")
shutil.copy2(DB, backup)
h = bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()
con = sqlite3.connect(DB)
n = con.execute("update auth set password=? where email=?", (h, EMAIL)).rowcount
con.commit()
con.close()
print(f"Updated {n} account ({EMAIL}). Backup: {backup}" if n else f"No account {EMAIL} found; nothing changed.")
