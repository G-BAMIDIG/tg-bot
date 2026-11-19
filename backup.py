"""Consistent SQLite snapshot -> zip, plus the 'is a daily backup due' rule."""
import os
import sqlite3
import tempfile
import zipfile
from datetime import datetime


def make_backup_zip(db_path):
    """Returns the path of a .zip containing a consistent copy of the database
    (uses SQLite's backup API, so it's safe while the bot is writing)."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    tmpdir = tempfile.mkdtemp(prefix="vpnbot-backup-")
    snap = os.path.join(tmpdir, f"vpnbot-{stamp}.db")
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(snap)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    zpath = os.path.join(tmpdir, f"vpnbot-backup-{stamp}.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(snap, os.path.basename(snap))
    os.remove(snap)
    return zpath


def backup_due(now_local, hour, last_date):
    """True if it's past `hour` today and today's backup hasn't run yet.
    Restart-safe: if the bot was down at the backup hour, it runs on startup."""
    return now_local.hour >= hour and last_date != now_local.strftime("%Y-%m-%d")
