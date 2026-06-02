from __future__ import annotations
import asyncpg
from datetime import datetime, timezone, timedelta
from typing import Iterable

SCHEMA = r'''
CREATE TABLE IF NOT EXISTS groups (
  chat_id BIGINT PRIMARY KEY,
  title TEXT NOT NULL,
  type TEXT,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  bot_ok BOOLEAN NOT NULL DEFAULT TRUE,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS users (
  user_id BIGINT PRIMARY KEY,
  username TEXT,
  first_name TEXT,
  demo_used BOOLEAN NOT NULL DEFAULT FALSE,
  bot_blocked BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS demos (
  user_id BIGINT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
  invite_link TEXT,
  joined_at TIMESTAMPTZ,
  kicked_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS orders (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(user_id),
  items TEXT[] NOT NULL,
  amount INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'WAITING_SCREEN',
  screenshot_file_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  decided_at TIMESTAMPTZ,
  decided_by BIGINT
);
CREATE TABLE IF NOT EXISTS subscriptions (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(user_id),
  items TEXT[] NOT NULL,
  starts_at TIMESTAMPTZ NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  reminded_10 BOOLEAN NOT NULL DEFAULT FALSE,
  reminded_5 BOOLEAN NOT NULL DEFAULT FALSE,
  reminded_3 BOOLEAN NOT NULL DEFAULT FALSE,
  order_id BIGINT REFERENCES orders(id)
);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_subscription_per_user ON subscriptions(user_id) WHERE active=true;
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events_log (
  id BIGSERIAL PRIMARY KEY,
  level TEXT NOT NULL,
  message TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
'''

_pool: asyncpg.Pool | None = None

async def connect(database_url: str):
    global _pool
    _pool = await asyncpg.create_pool(database_url, min_size=1, max_size=5)
    async with _pool.acquire() as con:
        await con.execute(SCHEMA)


def pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError('DB non connectée')
    return _pool

async def test_rw() -> bool:
    async with pool().acquire() as con:
        await con.execute("INSERT INTO settings(key,value) VALUES('healthcheck', $1) ON CONFLICT(key) DO UPDATE SET value=$1", datetime.now(timezone.utc).isoformat())
        return await con.fetchval("SELECT value FROM settings WHERE key='healthcheck'") is not None

async def log(level: str, message: str):
    async with pool().acquire() as con:
        await con.execute('INSERT INTO events_log(level,message) VALUES($1,$2)', level, message[:2000])

async def upsert_user(user):
    async with pool().acquire() as con:
        await con.execute('''INSERT INTO users(user_id,username,first_name) VALUES($1,$2,$3)
        ON CONFLICT(user_id) DO UPDATE SET username=$2, first_name=$3, bot_blocked=false''', user.id, user.username, user.first_name)

async def mark_bot_blocked(user_id: int):
    async with pool().acquire() as con:
        await con.execute('UPDATE users SET bot_blocked=true WHERE user_id=$1', user_id)

async def upsert_group(chat_id: int, title: str):
    async with pool().acquire() as con:
        await con.execute('''INSERT INTO groups(chat_id,title,active,bot_ok,updated_at) VALUES($1,$2,true,true,now())
        ON CONFLICT(chat_id) DO UPDATE SET title=$2, active=true, bot_ok=true, updated_at=now()''', chat_id, title)

async def set_group_type(chat_id: int, typ: str):
    async with pool().acquire() as con:
        await con.execute('UPDATE groups SET type=$2, updated_at=now() WHERE chat_id=$1', chat_id, typ)

async def mark_group_bad(chat_id: int):
    async with pool().acquire() as con:
        await con.execute('UPDATE groups SET bot_ok=false, active=false WHERE chat_id=$1', chat_id)

async def groups():
    async with pool().acquire() as con:
        return await con.fetch('SELECT * FROM groups ORDER BY title')

async def group_by_type(typ: str):
    async with pool().acquire() as con:
        return await con.fetch('SELECT * FROM groups WHERE type=$1 AND active=true', typ)

async def has_demo_used(user_id: int) -> bool:
    async with pool().acquire() as con:
        return bool(await con.fetchval('SELECT demo_used FROM users WHERE user_id=$1', user_id))

async def create_demo(user_id: int, invite_link: str):
    async with pool().acquire() as con:
        async with con.transaction():
            await con.execute('UPDATE users SET demo_used=true WHERE user_id=$1', user_id)
            await con.execute('INSERT INTO demos(user_id, invite_link) VALUES($1,$2) ON CONFLICT(user_id) DO NOTHING', user_id, invite_link)

async def set_demo_joined(user_id: int):
    async with pool().acquire() as con:
        await con.execute('UPDATE demos SET joined_at=COALESCE(joined_at, now()) WHERE user_id=$1', user_id)

async def demos_to_kick(minutes: int):
    async with pool().acquire() as con:
        return await con.fetch("SELECT * FROM demos WHERE kicked_at IS NULL AND created_at < now() - ($1 || ' minutes')::interval", str(minutes))

async def mark_demo_kicked(user_id: int):
    async with pool().acquire() as con:
        await con.execute('UPDATE demos SET kicked_at=now() WHERE user_id=$1', user_id)

async def create_order(user_id: int, items: list[str], amount: int) -> int:
    async with pool().acquire() as con:
        existing = await con.fetchval("SELECT id FROM orders WHERE user_id=$1 AND status IN ('WAITING_SCREEN','WAITING_ADMIN')", user_id)
        if existing:
            return existing
        return await con.fetchval('INSERT INTO orders(user_id,items,amount) VALUES($1,$2,$3) RETURNING id', user_id, items, amount)

async def attach_screenshot(user_id: int, file_id: str):
    async with pool().acquire() as con:
        return await con.fetchrow("UPDATE orders SET screenshot_file_id=$2,status='WAITING_ADMIN' WHERE user_id=$1 AND status='WAITING_SCREEN' RETURNING *", user_id, file_id)

async def get_order(order_id: int):
    async with pool().acquire() as con:
        return await con.fetchrow('SELECT * FROM orders WHERE id=$1', order_id)

async def decide_order(order_id: int, admin_id: int, status: str):
    async with pool().acquire() as con:
        async with con.transaction():
            order = await con.fetchrow("SELECT * FROM orders WHERE id=$1 FOR UPDATE", order_id)
            if not order or order['status'] not in ('WAITING_ADMIN','WAITING_SCREEN'):
                return None
            await con.execute('UPDATE orders SET status=$2,decided_at=now(),decided_by=$3 WHERE id=$1', order_id, status, admin_id)
            return order

async def activate_subscription(user_id: int, items: list[str], order_id: int, days: int):
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=days)
    async with pool().acquire() as con:
        async with con.transaction():
            await con.execute('UPDATE subscriptions SET active=false WHERE user_id=$1 AND active=true', user_id)
            return await con.fetchrow('INSERT INTO subscriptions(user_id,items,starts_at,expires_at,order_id) VALUES($1,$2,$3,$4,$5) RETURNING *', user_id, items, now, expires, order_id)

async def subscriptions_for_reminders(days_left: int):
    flag = {10:'reminded_10',5:'reminded_5',3:'reminded_3'}[days_left]
    async with pool().acquire() as con:
        return await con.fetch(f"SELECT * FROM subscriptions WHERE active=true AND {flag}=false AND expires_at <= now() + ($1 || ' days')::interval", str(days_left))

async def mark_reminded(sub_id: int, days_left: int):
    flag = {10:'reminded_10',5:'reminded_5',3:'reminded_3'}[days_left]
    async with pool().acquire() as con:
        await con.execute(f'UPDATE subscriptions SET {flag}=true WHERE id=$1', sub_id)

async def expired_subscriptions():
    async with pool().acquire() as con:
        return await con.fetch('SELECT * FROM subscriptions WHERE active=true AND expires_at <= now()')

async def deactivate_subscription(sub_id: int):
    async with pool().acquire() as con:
        await con.execute('UPDATE subscriptions SET active=false WHERE id=$1', sub_id)

async def pending_orders():
    async with pool().acquire() as con:
        return await con.fetch("SELECT * FROM orders WHERE status='WAITING_ADMIN' ORDER BY created_at")
