import os
import tempfile
import zipfile
from datetime import datetime

import psycopg
from dotenv import load_dotenv

load_dotenv()


def make_backup_zip(db_url=None):
    url = db_url or os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")

    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    tmpdir = tempfile.mkdtemp(prefix="vpnbot-backup-")
    dump = os.path.join(tmpdir, f"vpnbot-{stamp}.sql")

    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
            """)
            tables = [r[0] for r in cur.fetchall()]

            with open(dump, "w", encoding="utf-8") as f:
                for table in tables:
                    f.write(f"-- TABLE: {table}\n")
                    cur.execute(f'SELECT * FROM "{table}"')
                    rows = cur.fetchall()
                    columns = [d.name for d in cur.description]

                    for row in rows:
                        values = []

                        for value in row:
                            if value is None:
                                values.append("NULL")
                            elif isinstance(value, bool):
                                values.append("TRUE" if value else "FALSE")
                            elif isinstance(value, (int, float)):
                                values.append(str(value))
                            else:
                                escaped = str(value).replace("'", "''")
                                values.append("'" + escaped + "'")

                        column_names = ", ".join(
                            '"' + c + '"' for c in columns
                        )

                        f.write(
                            f'INSERT INTO "{table}" ({column_names}) '
                            f'VALUES ({", ".join(values)});\n'
                        )

    zpath = os.path.join(tmpdir, f"vpnbot-backup-{stamp}.zip")

    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(dump, os.path.basename(dump))

    os.remove(dump)
    return zpath


def backup_due(now_local, hour, last_date):
    return now_local.hour >= hour and last_date != now_local.strftime("%Y-%m-%d")
