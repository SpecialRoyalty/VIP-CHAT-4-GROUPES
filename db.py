from __future__ import annotations
import asyncpg
from datetime import datetime, timezone, timedelta

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
  chat_id BIGINT,
  invite_link TEXT,
  joined_at TIMESTAMPTZ,
  kicked_at TIMESTAMPTZ,
  revoked_at TIMESTAMPTZ,
  kick_error TEXT,
  kick_attempts INTEGER NOT NULL DEFAULT 0,
  kick_alerted_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS orders (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(user_id),
  items TEXT[] NOT NULL,
  amount INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'WAITING_SCREEN',
  promo_code TEXT,
  duration_days INTEGER NOT NULL DEFAULT 30,
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
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events_log (
  id BIGSERIAL PRIMARY KEY,
  level TEXT NOT NULL,
  message TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS access_links (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  subscription_id BIGINT REFERENCES subscriptions(id) ON DELETE SET NULL,
  group_type TEXT NOT NULL,
  chat_id BIGINT NOT NULL,
  invite_link TEXT NOT NULL,
  sent_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL,
  joined_at TIMESTAMPTZ,
  used BOOLEAN NOT NULL DEFAULT FALSE,
  expired_alert_sent BOOLEAN NOT NULL DEFAULT FALSE,
  repair_batch_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_access_links_user_chat ON access_links(user_id, chat_id);
CREATE INDEX IF NOT EXISTS idx_access_links_pending ON access_links(expires_at) WHERE joined_at IS NULL;

CREATE TABLE IF NOT EXISTS repair_runs (
  id BIGSERIAL PRIMARY KEY,
  run_type TEXT NOT NULL,
  admin_id BIGINT,
  affected_count INTEGER NOT NULL DEFAULT 0,
  links_sent INTEGER NOT NULL DEFAULT 0,
  errors INTEGER NOT NULL DEFAULT 0,
  details TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- Migrations compatibles anciennes bases : ajout uniquement, jamais de DROP.
ALTER TABLE demos ADD COLUMN IF NOT EXISTS chat_id BIGINT;
ALTER TABLE demos ADD COLUMN IF NOT EXISTS invite_link TEXT;
ALTER TABLE demos ADD COLUMN IF NOT EXISTS revoked_at TIMESTAMPTZ;
ALTER TABLE demos ADD COLUMN IF NOT EXISTS kick_error TEXT;
ALTER TABLE demos ADD COLUMN IF NOT EXISTS kick_attempts INTEGER NOT NULL DEFAULT 0;
ALTER TABLE demos ADD COLUMN IF NOT EXISTS kick_alerted_at TIMESTAMPTZ;
ALTER TABLE demos ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();

ALTER TABLE orders ADD COLUMN IF NOT EXISTS paypal_email TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS paypal_reference TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS proof_locked BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS proof_submitted_at TIMESTAMPTZ;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS processed_by_admin_id BIGINT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS processed_by_admin_username TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS processed_at TIMESTAMPTZ;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS refusal_reason TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS promo_code TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS duration_days INTEGER NOT NULL DEFAULT 30;
ALTER TABLE orders ALTER COLUMN amount TYPE NUMERIC(10,2) USING amount::numeric;

ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS renewal_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS last_renewed_at TIMESTAMPTZ;
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS ended_at TIMESTAMPTZ;
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS last_kick_error TEXT;

ALTER TABLE users ADD COLUMN IF NOT EXISTS second_demo_sent_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS second_demo_used_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS discovery_offer_sent_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS discovery_offer_expires_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS discovery_offer_used_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS first_promo_sent_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS first_promo_used_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS reactivation_offer_sent_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS reactivation_offer_expires_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS reactivation_offer_used_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS admin_notifications (
  id BIGSERIAL PRIMARY KEY,
  order_id BIGINT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  admin_id BIGINT NOT NULL,
  chat_id BIGINT NOT NULL,
  message_id BIGINT NOT NULL,
  is_read BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  cleared_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_admin_notifications_order ON admin_notifications(order_id);

CREATE TABLE IF NOT EXISTS admin_actions (
  id BIGSERIAL PRIMARY KEY,
  order_id BIGINT REFERENCES orders(id) ON DELETE SET NULL,
  admin_id BIGINT NOT NULL,
  admin_username TEXT,
  action TEXT NOT NULL,
  details TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Tarification dynamique : valeurs par défaut si absentes.
INSERT INTO settings(key,value) VALUES
 ('price_VIP_NON_TELECHARGEABLE','10'),
 ('price_VIP_TELECHARGEABLE','16'),
 ('price_REDIFFUSION','15'),
 ('discount_FIRST_50','50'),
 ('discount_DISCOVERY_6D','50'),
 ('discount_REACTIVATION_30','30'),
 ('promo_FIRST_50','OFF'),
 ('promo_FIRST_2PLUS1','OFF'),
 ('promo_REACTIVATION_30','OFF')
ON CONFLICT(key) DO NOTHING;

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

async def create_demo(user_id: int, chat_id: int, invite_link: str):
    async with pool().acquire() as con:
        async with con.transaction():
            await con.execute('UPDATE users SET demo_used=true WHERE user_id=$1', user_id)
            await con.execute('''
                INSERT INTO demos(user_id, chat_id, invite_link)
                VALUES($1,$2,$3)
                ON CONFLICT(user_id) DO UPDATE SET
                  chat_id=EXCLUDED.chat_id, invite_link=EXCLUDED.invite_link,
                  joined_at=NULL, kicked_at=NULL, revoked_at=NULL,
                  kick_error=NULL, kick_attempts=0, kick_alerted_at=NULL, created_at=now()
            ''', user_id, chat_id, invite_link)

async def set_demo_joined(user_id: int):
    async with pool().acquire() as con:
        await con.execute('UPDATE demos SET joined_at=COALESCE(joined_at, now()) WHERE user_id=$1', user_id)

async def demos_to_kick(minutes: int):
    async with pool().acquire() as con:
        return await con.fetch("""SELECT * FROM demos WHERE kicked_at IS NULL AND COALESCE(joined_at, created_at) < now() - ($1 || ' minutes')::interval""", str(minutes))

async def mark_demo_kicked(user_id: int):
    async with pool().acquire() as con:
        await con.execute('UPDATE demos SET kicked_at=now(), kick_error=NULL WHERE user_id=$1', user_id)

async def mark_demo_kick_failed(user_id: int, error: str):
    async with pool().acquire() as con:
        return await con.fetchrow('UPDATE demos SET kick_error=$2, kick_attempts=kick_attempts+1 WHERE user_id=$1 RETURNING *', user_id, error[:1000])

async def mark_demo_kick_alerted(user_id: int):
    async with pool().acquire() as con:
        await con.execute('UPDATE demos SET kick_alerted_at=now() WHERE user_id=$1', user_id)

async def mark_demo_invite_revoked(user_id: int):
    async with pool().acquire() as con:
        await con.execute('UPDATE demos SET revoked_at=now() WHERE user_id=$1', user_id)

async def demo_for_user(user_id: int):
    async with pool().acquire() as con:
        return await con.fetchrow('SELECT * FROM demos WHERE user_id=$1', user_id)

OPEN_STATUSES = ('WAITING_SCREEN','WAITING_PAYPAL_EMAIL','WAITING_PAYPAL_REFERENCE','WAITING_ADMIN')

async def create_order(user_id: int, items: list[str], amount, promo_code: str | None = None, duration_days: int = 30) -> int:
    async with pool().acquire() as con:
        existing = await con.fetchval("SELECT id FROM orders WHERE user_id=$1 AND status = ANY($2::text[])", user_id, list(OPEN_STATUSES))
        if existing:
            return existing
        return await con.fetchval('INSERT INTO orders(user_id,items,amount,status,promo_code,duration_days) VALUES($1,$2,$3,\'WAITING_SCREEN\',$4,$5) RETURNING id', user_id, items, amount, promo_code, duration_days)

async def current_open_order(user_id: int):
    async with pool().acquire() as con:
        return await con.fetchrow("SELECT * FROM orders WHERE user_id=$1 AND status = ANY($2::text[]) ORDER BY created_at DESC LIMIT 1", user_id, list(OPEN_STATUSES))

async def attach_screenshot(user_id: int, file_id: str):
    async with pool().acquire() as con:
        async with con.transaction():
            order = await con.fetchrow("SELECT * FROM orders WHERE user_id=$1 AND status = ANY($2::text[]) ORDER BY created_at DESC LIMIT 1 FOR UPDATE", user_id, list(OPEN_STATUSES))
            if not order:
                return None
            if order['proof_locked'] or order['screenshot_file_id']:
                return 'LOCKED'
            return await con.fetchrow("""
                UPDATE orders
                SET screenshot_file_id=$2, status='WAITING_PAYPAL_EMAIL', proof_locked=true, proof_submitted_at=now()
                WHERE id=$1 RETURNING *
            """, order['id'], file_id)

async def save_paypal_email(user_id: int, email: str):
    async with pool().acquire() as con:
        return await con.fetchrow("""
            UPDATE orders SET paypal_email=$2, status='WAITING_PAYPAL_REFERENCE'
            WHERE id=(SELECT id FROM orders WHERE user_id=$1 AND status='WAITING_PAYPAL_EMAIL' ORDER BY created_at DESC LIMIT 1)
            RETURNING *
        """, user_id, email[:300])

async def save_paypal_reference(user_id: int, reference: str):
    async with pool().acquire() as con:
        return await con.fetchrow("""
            UPDATE orders SET paypal_reference=$2, status='WAITING_ADMIN'
            WHERE id=(SELECT id FROM orders WHERE user_id=$1 AND status='WAITING_PAYPAL_REFERENCE' ORDER BY created_at DESC LIMIT 1)
            RETURNING *
        """, user_id, reference[:300])

async def get_order(order_id: int):
    async with pool().acquire() as con:
        return await con.fetchrow('SELECT * FROM orders WHERE id=$1', order_id)

async def decide_order(order_id: int, admin_id: int, admin_username: str | None, status: str, refusal_reason: str | None = None):
    async with pool().acquire() as con:
        async with con.transaction():
            order = await con.fetchrow("SELECT * FROM orders WHERE id=$1 FOR UPDATE", order_id)
            if not order:
                return None
            if order['status'] != 'WAITING_ADMIN':
                return None
            await con.execute('''
                UPDATE orders
                SET status=$2, decided_at=now(), decided_by=$3,
                    processed_by_admin_id=$3, processed_by_admin_username=$4,
                    processed_at=now(), refusal_reason=$5
                WHERE id=$1
            ''', order_id, status, admin_id, admin_username, refusal_reason)
            await con.execute('INSERT INTO admin_actions(order_id,admin_id,admin_username,action,details) VALUES($1,$2,$3,$4,$5)', order_id, admin_id, admin_username, status, refusal_reason)
            return order

async def save_admin_notification(order_id: int, admin_id: int, chat_id: int, message_id: int):
    async with pool().acquire() as con:
        await con.execute('INSERT INTO admin_notifications(order_id,admin_id,chat_id,message_id) VALUES($1,$2,$3,$4)', order_id, admin_id, chat_id, message_id)

async def notifications_for_order(order_id: int):
    async with pool().acquire() as con:
        return await con.fetch('SELECT * FROM admin_notifications WHERE order_id=$1 AND cleared_at IS NULL', order_id)

async def clear_notification(notification_id: int):
    async with pool().acquire() as con:
        await con.execute('UPDATE admin_notifications SET cleared_at=now(), is_read=true WHERE id=$1', notification_id)

async def active_subscription(user_id: int):
    async with pool().acquire() as con:
        return await con.fetchrow('SELECT * FROM subscriptions WHERE user_id=$1 AND active=true ORDER BY expires_at DESC LIMIT 1', user_id)

async def activate_subscription(user_id: int, items: list[str], order_id: int, days: int):
    now = datetime.now(timezone.utc)
    async with pool().acquire() as con:
        async with con.transaction():
            current = await con.fetchrow('SELECT * FROM subscriptions WHERE user_id=$1 AND active=true ORDER BY expires_at DESC LIMIT 1 FOR UPDATE', user_id)
            base = current['expires_at'] if current and current['expires_at'] > now else now
            expires = base + timedelta(days=days)
            renewal_count = int(current['renewal_count'] or 0) + 1 if current else 0
            await con.execute('UPDATE subscriptions SET active=false, ended_at=now() WHERE user_id=$1 AND active=true', user_id)
            return await con.fetchrow('''
                INSERT INTO subscriptions(user_id,items,starts_at,expires_at,order_id,renewal_count,last_renewed_at)
                VALUES($1,$2,$3,$4,$5,$6,$7) RETURNING *
            ''', user_id, items, now if not current else current['starts_at'], expires, order_id, renewal_count, now)

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
        return await con.fetch('SELECT s.*, u.username, u.first_name FROM subscriptions s LEFT JOIN users u ON u.user_id=s.user_id WHERE s.active=true AND s.expires_at IS NOT NULL AND s.expires_at <= now()')

async def deactivate_subscription(sub_id: int):
    async with pool().acquire() as con:
        await con.execute('UPDATE subscriptions SET active=false, ended_at=now() WHERE id=$1', sub_id)

async def mark_subscription_kick_failed(sub_id: int, error: str):
    async with pool().acquire() as con:
        await con.execute('UPDATE subscriptions SET last_kick_error=$2 WHERE id=$1', sub_id, error[:1000])

async def malformed_active_subscriptions(limit: int = 30):
    async with pool().acquire() as con:
        return await con.fetch('''
            SELECT s.*, u.username, u.first_name
            FROM subscriptions s LEFT JOIN users u ON u.user_id=s.user_id
            WHERE s.active=true AND (s.starts_at IS NULL OR s.expires_at IS NULL)
            ORDER BY s.id DESC LIMIT $1
        ''', limit)

async def subscription_by_id(sub_id: int):
    async with pool().acquire() as con:
        return await con.fetchrow('SELECT s.*, u.username, u.first_name FROM subscriptions s LEFT JOIN users u ON u.user_id=s.user_id WHERE s.id=$1', sub_id)

async def expired_or_malformed_active_subscriptions(limit: int = 30):
    async with pool().acquire() as con:
        return await con.fetch('''
            SELECT s.*, u.username, u.first_name,
                   CASE
                     WHEN s.starts_at IS NULL OR s.expires_at IS NULL THEN 'DATES_MANQUANTES'
                     WHEN s.expires_at <= now() THEN 'EXPIRE'
                     ELSE 'OK'
                   END AS anomaly_reason
            FROM subscriptions s LEFT JOIN users u ON u.user_id=s.user_id
            WHERE s.active=true AND ((s.starts_at IS NULL OR s.expires_at IS NULL) OR s.expires_at <= now())
            ORDER BY COALESCE(s.expires_at, s.starts_at, now()) ASC
            LIMIT $1
        ''', limit)

async def cancel_current_order(user_id: int):
    async with pool().acquire() as con:
        return await con.fetchrow("""
            UPDATE orders SET status='CANCELLED', decided_at=now()
            WHERE id=(SELECT id FROM orders WHERE user_id=$1 AND status = ANY($2::text[]) ORDER BY created_at DESC LIMIT 1)
            RETURNING *
        """, user_id, list(OPEN_STATUSES))

async def pending_orders():
    async with pool().acquire() as con:
        return await con.fetch("SELECT * FROM orders WHERE status='WAITING_ADMIN' ORDER BY created_at")

async def unread_pending_count() -> int:
    async with pool().acquire() as con:
        return int(await con.fetchval("SELECT COUNT(*) FROM orders WHERE status='WAITING_ADMIN'") or 0)

async def get_setting(key: str, default: str | None = None):
    async with pool().acquire() as con:
        val = await con.fetchval('SELECT value FROM settings WHERE key=$1', key)
        return default if val is None else val

async def set_setting(key: str, value: str):
    async with pool().acquire() as con:
        await con.execute('INSERT INTO settings(key,value) VALUES($1,$2) ON CONFLICT(key) DO UPDATE SET value=$2', key, value)


PRICE_KEYS = ['VIP_NON_TELECHARGEABLE','VIP_TELECHARGEABLE','REDIFFUSION']
DEFAULT_PRICING = {
    'price_VIP_NON_TELECHARGEABLE': '10',
    'price_VIP_TELECHARGEABLE': '16',
    'price_REDIFFUSION': '15',
    'discount_FIRST_50': '50',
    'discount_DISCOVERY_6D': '50',
    'discount_REACTIVATION_30': '30',
}

async def pricing_settings():
    async with pool().acquire() as con:
        rows = await con.fetch("SELECT key,value FROM settings WHERE key LIKE 'price_%' OR key LIKE 'discount_%'")
        data = dict(DEFAULT_PRICING)
        data.update({r['key']: r['value'] for r in rows})
        return data

async def set_pricing_value(key: str, value: str):
    if not (key.startswith('price_') or key.startswith('discount_')):
        raise ValueError('Clé tarification invalide')
    async with pool().acquire() as con:
        await con.execute('INSERT INTO settings(key,value) VALUES($1,$2) ON CONFLICT(key) DO UPDATE SET value=$2', key, value)

async def recent_orders(limit: int = 10):
    async with pool().acquire() as con:
        return await con.fetch('SELECT * FROM orders ORDER BY created_at DESC LIMIT $1', limit)

async def orders_by_status(status: str, limit: int = 20):
    async with pool().acquire() as con:
        return await con.fetch('SELECT * FROM orders WHERE status=$1 ORDER BY created_at DESC LIMIT $2', status, limit)

async def accounting_summary():
    async with pool().acquire() as con:
        return {
            'total_amount': await con.fetchval("SELECT COALESCE(SUM(amount),0) FROM orders WHERE status='APPROVED'") or 0,
            'today_amount': await con.fetchval("SELECT COALESCE(SUM(amount),0) FROM orders WHERE status='APPROVED' AND processed_at::date = now()::date") or 0,
            'month_amount': await con.fetchval("SELECT COALESCE(SUM(amount),0) FROM orders WHERE status='APPROVED' AND date_trunc('month', processed_at)=date_trunc('month', now())") or 0,
            'approved': int(await con.fetchval("SELECT COUNT(*) FROM orders WHERE status='APPROVED'") or 0),
            'rejected': int(await con.fetchval("SELECT COUNT(*) FROM orders WHERE status='REJECTED'") or 0),
            'pending': int(await con.fetchval("SELECT COUNT(*) FROM orders WHERE status='WAITING_ADMIN'") or 0),
            'active_subs': int(await con.fetchval("SELECT COUNT(*) FROM subscriptions WHERE active=true AND expires_at > now()") or 0),
            'expired_not_kicked': int(await con.fetchval("SELECT COUNT(*) FROM subscriptions WHERE active=true AND expires_at <= now()") or 0),
            'vip_ndl': int(await con.fetchval("SELECT COUNT(*) FROM subscriptions WHERE active=true AND 'VIP_NON_TELECHARGEABLE'=ANY(items)") or 0),
            'vip_dl': int(await con.fetchval("SELECT COUNT(*) FROM subscriptions WHERE active=true AND 'VIP_TELECHARGEABLE'=ANY(items)") or 0),
            'rediff': int(await con.fetchval("SELECT COUNT(*) FROM subscriptions WHERE active=true AND 'REDIFFUSION'=ANY(items)") or 0),
        }

async def accounting_anomalies():
    async with pool().acquire() as con:
        rows = []
        rows += [f"Commande #{r['id']} validée sans abonnement" for r in await con.fetch("""
            SELECT o.id FROM orders o LEFT JOIN subscriptions s ON s.order_id=o.id
            WHERE o.status='APPROVED' AND s.id IS NULL ORDER BY o.id DESC LIMIT 10
        """)]
        # Les anciens paiements peuvent avoir été validés avec une ancienne tarification.
        # On évite donc de les marquer comme anomalies après un changement de prix.
        rows += [f"Commande #{r['id']} en attente sans email/référence PayPal" for r in await con.fetch("SELECT id FROM orders WHERE status='WAITING_ADMIN' AND (paypal_email IS NULL OR paypal_reference IS NULL) ORDER BY id DESC LIMIT 10")]
        rows += [f"Abonnement #{r['id']} actif sans date complète user {r['user_id']}" for r in await con.fetch("SELECT id,user_id FROM subscriptions WHERE active=true AND (starts_at IS NULL OR expires_at IS NULL) ORDER BY id DESC LIMIT 10")]
        rows += [f"Abonnement #{r['id']} expiré mais encore actif en base user {r['user_id']}" for r in await con.fetch("SELECT id,user_id FROM subscriptions WHERE active=true AND expires_at IS NOT NULL AND expires_at <= now() ORDER BY expires_at LIMIT 10")]
        return rows[:30]

async def subscriptions_list(filter_name: str = 'active', limit: int = 20):
    where = "active=true AND expires_at > now()"
    if filter_name == 'expiring':
        where = "active=true AND expires_at > now() AND expires_at <= now() + interval '7 days'"
    elif filter_name == 'expired':
        where = "expires_at <= now()"
    async with pool().acquire() as con:
        return await con.fetch(f'''SELECT s.*, u.username, u.first_name FROM subscriptions s LEFT JOIN users u ON u.user_id=s.user_id WHERE {where} ORDER BY expires_at ASC LIMIT $1''', limit)


async def approved_order_count(user_id: int) -> int:
    async with pool().acquire() as con:
        return int(await con.fetchval("SELECT COUNT(*) FROM orders WHERE user_id=$1 AND status='APPROVED'", user_id) or 0)

async def mark_first_promo_sent(user_id: int):
    async with pool().acquire() as con:
        await con.execute('UPDATE users SET first_promo_sent_at=COALESCE(first_promo_sent_at, now()) WHERE user_id=$1', user_id)

async def first_promo_active_for_user(user_id: int) -> bool:
    async with pool().acquire() as con:
        row = await con.fetchrow('SELECT first_promo_sent_at, first_promo_used_at FROM users WHERE user_id=$1', user_id)
        paid = int(await con.fetchval("SELECT COUNT(*) FROM orders WHERE user_id=$1 AND status='APPROVED'", user_id) or 0)
        return bool(row and row['first_promo_sent_at'] and not row['first_promo_used_at'] and not paid)

async def eligible_first_promo(user_id: int) -> bool:
    async with pool().acquire() as con:
        paid = int(await con.fetchval("SELECT COUNT(*) FROM orders WHERE user_id=$1 AND status='APPROVED'", user_id) or 0)
        if paid:
            return False
        row = await con.fetchrow('SELECT demo_used, first_promo_used_at FROM users WHERE user_id=$1', user_id)
        return bool(row and not row['demo_used'] and row['first_promo_used_at'] is None)

async def mark_first_promo_used(user_id: int):
    async with pool().acquire() as con:
        await con.execute('UPDATE users SET first_promo_used_at=COALESCE(first_promo_used_at, now()) WHERE user_id=$1', user_id)

async def mark_second_demo_sent(user_id: int):
    async with pool().acquire() as con:
        await con.execute('UPDATE users SET second_demo_sent_at=now() WHERE user_id=$1', user_id)

async def mark_second_demo_used(user_id: int):
    async with pool().acquire() as con:
        await con.execute('UPDATE users SET second_demo_used_at=now() WHERE user_id=$1', user_id)

async def can_use_second_demo(user_id: int) -> bool:
    async with pool().acquire() as con:
        row = await con.fetchrow('SELECT second_demo_sent_at, second_demo_used_at FROM users WHERE user_id=$1', user_id)
        paid = int(await con.fetchval("SELECT COUNT(*) FROM orders WHERE user_id=$1 AND status='APPROVED'", user_id) or 0)
        return bool(row and row['second_demo_sent_at'] and not row['second_demo_used_at'] and not paid)

async def second_demo_candidates():
    async with pool().acquire() as con:
        return await con.fetch("""
            SELECT u.* FROM users u
            JOIN demos d ON d.user_id=u.user_id
            WHERE u.demo_used=true
              AND u.second_demo_sent_at IS NULL
              AND NOT EXISTS (SELECT 1 FROM orders o WHERE o.user_id=u.user_id AND o.status='APPROVED')
              AND COALESCE(d.joined_at, d.created_at) <= now() - interval '5 days'
        """)

async def discovery_offer_candidates():
    async with pool().acquire() as con:
        return await con.fetch("""
            SELECT u.* FROM users u
            WHERE u.second_demo_sent_at IS NOT NULL
              AND u.discovery_offer_sent_at IS NULL
              AND NOT EXISTS (SELECT 1 FROM orders o WHERE o.user_id=u.user_id AND o.status='APPROVED')
              AND u.second_demo_sent_at <= now() - interval '2 days'
        """)

async def mark_discovery_offer_sent(user_id: int):
    async with pool().acquire() as con:
        await con.execute("UPDATE users SET discovery_offer_sent_at=now(), discovery_offer_expires_at=now()+interval '24 hours' WHERE user_id=$1", user_id)

async def discovery_offer_active(user_id: int) -> bool:
    async with pool().acquire() as con:
        row = await con.fetchrow('SELECT discovery_offer_expires_at, discovery_offer_used_at FROM users WHERE user_id=$1', user_id)
        paid = int(await con.fetchval("SELECT COUNT(*) FROM orders WHERE user_id=$1 AND status='APPROVED'", user_id) or 0)
        return bool(row and row['discovery_offer_expires_at'] and row['discovery_offer_expires_at'] > datetime.now(timezone.utc) and not row['discovery_offer_used_at'] and not paid)

async def mark_discovery_offer_used(user_id: int):
    async with pool().acquire() as con:
        await con.execute('UPDATE users SET discovery_offer_used_at=COALESCE(discovery_offer_used_at, now()) WHERE user_id=$1', user_id)

async def reactivation_candidates():
    async with pool().acquire() as con:
        return await con.fetch("""
            SELECT DISTINCT u.user_id, u.username, u.first_name
            FROM users u
            JOIN subscriptions s ON s.user_id=u.user_id
            WHERE s.active=false
              AND s.ended_at <= now() - interval '10 days'
              AND u.reactivation_offer_sent_at IS NULL
              AND NOT EXISTS (SELECT 1 FROM subscriptions s2 WHERE s2.user_id=u.user_id AND s2.active=true)
        """)

async def mark_reactivation_offer_sent(user_id: int):
    async with pool().acquire() as con:
        await con.execute("UPDATE users SET reactivation_offer_sent_at=now(), reactivation_offer_expires_at=now()+interval '24 hours' WHERE user_id=$1", user_id)

async def reactivation_offer_active(user_id: int) -> bool:
    async with pool().acquire() as con:
        row = await con.fetchrow('SELECT reactivation_offer_expires_at, reactivation_offer_used_at FROM users WHERE user_id=$1', user_id)
        return bool(row and row['reactivation_offer_expires_at'] and row['reactivation_offer_expires_at'] > datetime.now(timezone.utc) and not row['reactivation_offer_used_at'])

async def mark_reactivation_offer_used(user_id: int):
    async with pool().acquire() as con:
        await con.execute('UPDATE users SET reactivation_offer_used_at=COALESCE(reactivation_offer_used_at, now()) WHERE user_id=$1', user_id)


async def active_subscriptions_all(limit: int = 5000):
    async with pool().acquire() as con:
        return await con.fetch("""
            SELECT s.*, u.username, u.first_name, u.bot_blocked
            FROM subscriptions s LEFT JOIN users u ON u.user_id=s.user_id
            WHERE s.active=true AND s.expires_at IS NOT NULL AND s.expires_at > now()
            ORDER BY s.expires_at ASC LIMIT $1
        """, limit)

async def compensate_active_subscriptions(days: int, admin_id: int | None = None):
    async with pool().acquire() as con:
        rows = await con.fetch("""
            UPDATE subscriptions
            SET expires_at = expires_at + ($1 || ' days')::interval
            WHERE active=true AND expires_at IS NOT NULL AND expires_at > now()
            RETURNING *
        """, str(days))
        await con.execute("""INSERT INTO repair_runs(run_type, admin_id, affected_count, details)
                             VALUES('COMPENSATION', $1, $2, $3)""", admin_id, len(rows), f'+{days} jours')
        return rows

async def record_access_link(user_id: int, subscription_id: int | None, group_type: str, chat_id: int, invite_link: str, expires_at, repair_batch_id: str | None = None):
    async with pool().acquire() as con:
        return await con.fetchrow("""
            INSERT INTO access_links(user_id, subscription_id, group_type, chat_id, invite_link, expires_at, repair_batch_id)
            VALUES($1,$2,$3,$4,$5,$6,$7) RETURNING *
        """, user_id, subscription_id, group_type, chat_id, invite_link, expires_at, repair_batch_id)

async def mark_access_link_joined(user_id: int, chat_id: int):
    async with pool().acquire() as con:
        await con.execute("""
            UPDATE access_links
            SET joined_at=COALESCE(joined_at, now()), used=true
            WHERE id = (
                SELECT id FROM access_links
                WHERE user_id=$1 AND chat_id=$2 AND joined_at IS NULL
                ORDER BY sent_at DESC LIMIT 1
            )
        """, user_id, chat_id)

async def expired_unused_access_links(limit: int = 50):
    async with pool().acquire() as con:
        return await con.fetch("""
            SELECT al.*, u.username, u.first_name
            FROM access_links al LEFT JOIN users u ON u.user_id=al.user_id
            WHERE al.joined_at IS NULL AND al.expires_at <= now() AND al.expired_alert_sent=false
            ORDER BY al.expires_at ASC LIMIT $1
        """, limit)

async def mark_access_link_alerted(link_id: int):
    async with pool().acquire() as con:
        await con.execute('UPDATE access_links SET expired_alert_sent=true WHERE id=$1', link_id)

async def recent_access_stats():
    async with pool().acquire() as con:
        return await con.fetch("""
            SELECT group_type,
                   COUNT(*) AS sent,
                   COUNT(*) FILTER (WHERE joined_at IS NOT NULL) AS joined,
                   COUNT(*) FILTER (WHERE joined_at IS NULL AND expires_at > now()) AS pending,
                   COUNT(*) FILTER (WHERE joined_at IS NULL AND expires_at <= now()) AS expired_unused
            FROM access_links
            WHERE sent_at >= now() - interval '7 days'
            GROUP BY group_type
            ORDER BY group_type
        """)

async def create_repair_run(run_type: str, admin_id: int | None, affected_count: int = 0, links_sent: int = 0, errors: int = 0, details: str | None = None):
    async with pool().acquire() as con:
        return await con.fetchrow("""
            INSERT INTO repair_runs(run_type, admin_id, affected_count, links_sent, errors, details)
            VALUES($1,$2,$3,$4,$5,$6) RETURNING *
        """, run_type, admin_id, affected_count, links_sent, errors, details)
