import sqlite3, os

db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aquarium.db")
conn = sqlite3.connect(db_path)
cur = conn.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
print("Existing tables:", cur.fetchall())

cur.execute("""
    CREATE TABLE IF NOT EXISTS feeding_schedules (
        id      INTEGER PRIMARY KEY AUTOINCREMENT,
        name    TEXT NOT NULL,
        time    TEXT NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 1
    )
""")

cur.execute("""
    CREATE TABLE IF NOT EXISTS light_schedule (
        id       INTEGER PRIMARY KEY,
        on_time  TEXT NOT NULL DEFAULT '08:00',
        off_time TEXT NOT NULL DEFAULT '22:00'
    )
""")

cur.execute("""
    CREATE TABLE IF NOT EXISTS allowed_ranges (
        key   TEXT PRIMARY KEY,
        value REAL NOT NULL
    )
""")

cur.execute("INSERT OR IGNORE INTO light_schedule (id, on_time, off_time) VALUES (1, '08:00', '22:00')")

conn.commit()
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
print("Tables after init:", cur.fetchall())
conn.close()
print("Done.")
