import sqlite3

conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users(
    user_id INTEGER PRIMARY KEY,
    free_requests INTEGER DEFAULT 3,
    premium INTEGER DEFAULT 0
)
""")

conn.commit()


def add_user(user_id):
    cursor.execute(
        "INSERT OR IGNORE INTO users(user_id) VALUES(?)",
        (user_id,)
    )
    conn.commit()


def get_user(user_id):
    cursor.execute(
        "SELECT free_requests,premium FROM users WHERE user_id=?",
        (user_id,)
    )
    return cursor.fetchone()


def use_request(user_id):
    cursor.execute("""
        UPDATE users
        SET free_requests=free_requests-1
        WHERE user_id=? AND free_requests>0
    """,(user_id,))
    conn.commit()


def set_premium(user_id):
    cursor.execute("""
        UPDATE users
        SET premium=1
        WHERE user_id=?
    """,(user_id,))
    conn.commit()