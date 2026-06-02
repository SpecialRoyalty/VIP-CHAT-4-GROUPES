from __future__ import annotations
import asyncpg
from typing import Any

SCHEMA = r'''
CREATE TABLE IF NOT EXISTS groups (
  chat_id BIGINT PRIMARY KEY,
  title TEXT NOT NULL,
  type TEXT NOT NULL DEFAULT 'UNASSIGNED',
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS users (
  user_id BIGINT PRIMARY KEY,
  username TEXT,
  first_name TEXT,
  demo_used BOOLEAN NOT NULL DEFAULT FALSE,
  blocked_bot BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS orders (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(user_id),
  username TEXT,
  selected_vip TEXT,
  rediffusion BOOLEAN NOT NULL DEFAULT FALSE,
  amount INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'WAITING_SCREENSHOT',
  screenshot_file_id TEXT,
  admin_message_chat_id BIGINT,
  admin_message_id BIGINT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  decided_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS accesses (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(user_id),
  group_type TEXT NOT NULL,
  order_id BIGINT REFERENCES orders(id),
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(user_id, group_type)
);

CREATE TABLE IF NOT EXISTS demo_sessions (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(user_id),
  preview_chat_id BIGINT NOT NULL,
  invite_link TEXT,
  joined BOOLEAN NOT NULL DEFAULT FALSE,
  kicked BOOLEAN NOT NULL DEFAULT FALSE,
  expires_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ad_campaigns (
  id BIGSERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  text TEXT NOT NULL,
  photo_file_id TEXT,
  target_chat_ids BIGINT[] NOT NULL DEFAULT '{}',
  interval_minutes INTEGER,
  active BOOLEAN NOT NULL DEFAULT FALSE,
  last_sent_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS logs (
  id BIGSERIAL PRIMARY KEY,
  level TEXT NOT NULL DEFAULT 'INFO',
  message TEXT NOT NULL,
  meta JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
'''

class Database:
    def __init__(self, dsn: str):
        self.dsn = dsn
        self.pool: asyncpg.Pool | None = None

    async def connect(self):
        self.pool = await asyncpg.create_pool(self.dsn, min_size=1, max_size=5)
        await self.execute(SCHEMA)

    async def close(self):
        if self.pool:
            await self.pool.close()

    async def execute(self, query: str, *args: Any):
        assert self.pool
        async with self.pool.acquire() as con:
            return await con.execute(query, *args)

    async def fetch(self, query: str, *args: Any):
        assert self.pool
        async with self.pool.acquire() as con:
            return await con.fetch(query, *args)

    async def fetchrow(self, query: str, *args: Any):
        assert self.pool
        async with self.pool.acquire() as con:
            return await con.fetchrow(query, *args)

    async def fetchval(self, query: str, *args: Any):
        assert self.pool
        async with self.pool.acquire() as con:
            return await con.fetchval(query, *args)

    async def log(self, message: str, level: str = 'INFO', meta: dict | None = None):
        await self.execute(
            'INSERT INTO logs(level, message, meta) VALUES($1,$2,$3)',
            level, message, meta or {}
        )
