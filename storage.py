"""SQLite 持久化及 PBKDF2 密码验证。所有业务查询均限制到当前用户。"""
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import os
from contextlib import contextmanager
from pathlib import Path

DB = Path(os.environ.get('APP_DATA_DIR', str(Path(__file__).parent / 'data'))) / 'app.sqlite3'


@contextmanager
def connect():
    DB.parent.mkdir(parents=True,exist_ok=True)
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init():
    with connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS users(
          id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, salt TEXT NOT NULL, password TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS portfolios(
          id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
          name TEXT NOT NULL, config TEXT NOT NULL, updated TEXT DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(user_id,name));
        CREATE TABLE IF NOT EXISTS analyses(
          id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
          name TEXT NOT NULL, config TEXT NOT NULL, result TEXT NOT NULL, created TEXT DEFAULT CURRENT_TIMESTAMP);
        ''')


def password_hash(password, salt):
    return hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 260000).hex()


def register(username, password):
    username = username.strip()
    if not re.fullmatch(r'[A-Za-z0-9_\u4e00-\u9fff]{3,24}', username):
        raise ValueError('用户名需为 3～24 位中文、字母、数字或下划线。')
    if not 8 <= len(password) <= 128:
        raise ValueError('密码长度需为 8～128 位。')
    salt = secrets.token_hex(16)
    with connect() as c:
        try:
            c.execute('INSERT INTO users(username,salt,password) VALUES(?,?,?)',
                      (username, salt, password_hash(password, salt)))
        except sqlite3.IntegrityError:
            raise ValueError('该用户名已存在。') from None


def login(username, password):
    with connect() as c:
        row = c.execute('SELECT * FROM users WHERE username=?', (username.strip(),)).fetchone()
    if row and hmac.compare_digest(row['password'], password_hash(password, row['salt'])):
        return row['id']
    return None


def save_portfolio(user_id, name, config):
    if not name.strip() or len(name.strip()) > 60:
        raise ValueError('组合名称须为 1～60 个字符。')
    with connect() as c:
        c.execute('''INSERT INTO portfolios(user_id,name,config) VALUES(?,?,?)
          ON CONFLICT(user_id,name) DO UPDATE SET config=excluded.config,updated=CURRENT_TIMESTAMP''',
                  (user_id, name.strip(), json.dumps(config, ensure_ascii=False)))


def portfolios(user_id):
    with connect() as c:
        return [dict(r) for r in c.execute('SELECT * FROM portfolios WHERE user_id=? ORDER BY id', (user_id,))]


def delete_portfolio(user_id, portfolio_id):
    with connect() as c:
        c.execute('DELETE FROM portfolios WHERE id=? AND user_id=?', (portfolio_id, user_id))


def save_analysis(user_id, name, config, result):
    payload = {'metrics': result['metrics'], 'start': result['start'], 'end': result['end'],
               'observations': result['observations']}
    with connect() as c:
        c.execute('INSERT INTO analyses(user_id,name,config,result) VALUES(?,?,?,?)',
                  (user_id, name, json.dumps(config, ensure_ascii=False), json.dumps(payload, ensure_ascii=False)))


def history(user_id):
    with connect() as c:
        return [dict(r) for r in c.execute('SELECT * FROM analyses WHERE user_id=? ORDER BY id DESC LIMIT 50', (user_id,))]
