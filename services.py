from __future__ import annotations
from datetime import datetime, timedelta, timezone
from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from db import Database

PRICES = {
    'VIP_NON_TELECHARGEABLE': 25,
    'VIP_TELECHARGEABLE': 30,
    'REDIFFUSION': 10,
}

VIP_GROUPS = ['VIP_PREVIEW', 'VIP_NON_TELECHARGEABLE', 'VIP_TELECHARGEABLE', 'REDIFFUSION']


def calculate_amount(selected_vip: str | None, rediffusion: bool) -> int:
    total = 0
    if selected_vip:
        total += PRICES[selected_vip]
    if rediffusion:
        total += PRICES['REDIFFUSION']
    return total

async def upsert_user(db: Database, user):
    await db.execute('''
    INSERT INTO users(user_id, username, first_name, blocked_bot)
    VALUES($1,$2,$3,false)
    ON CONFLICT(user_id) DO UPDATE SET username=$2, first_name=$3, blocked_bot=false, updated_at=now()
    ''', user.id, user.username, user.first_name)

async def get_group_id(db: Database, group_type: str) -> int | None:
    row = await db.fetchrow('SELECT chat_id FROM groups WHERE type=$1 AND active=true LIMIT 1', group_type)
    return int(row['chat_id']) if row else None

async def make_unique_invite(bot: Bot, db: Database, group_type: str, member_limit: int = 1, minutes: int = 60) -> str:
    chat_id = await get_group_id(db, group_type)
    if not chat_id:
        raise RuntimeError(f'Groupe {group_type} non configuré')
    expire_date = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    link = await bot.create_chat_invite_link(
        chat_id=chat_id,
        member_limit=member_limit,
        expire_date=expire_date,
        creates_join_request=False,
    )
    return link.invite_link

async def create_demo(db: Database, bot: Bot, user_id: int, demo_minutes: int) -> str:
    used = await db.fetchval('SELECT demo_used FROM users WHERE user_id=$1', user_id)
    if used:
        raise RuntimeError('DEMO_ALREADY_USED')
    preview_chat_id = await get_group_id(db, 'VIP_PREVIEW')
    if not preview_chat_id:
        raise RuntimeError('VIP_PREVIEW_MISSING')
    invite = await make_unique_invite(bot, db, 'VIP_PREVIEW', member_limit=1, minutes=15)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=demo_minutes)
    await db.execute('UPDATE users SET demo_used=true, updated_at=now() WHERE user_id=$1', user_id)
    await db.execute('''
    INSERT INTO demo_sessions(user_id, preview_chat_id, invite_link, expires_at)
    VALUES($1,$2,$3,$4)
    ''', user_id, preview_chat_id, invite, expires_at)
    return invite

async def kick_expired_demos(db: Database, bot: Bot):
    rows = await db.fetch('''
    SELECT id, user_id, preview_chat_id FROM demo_sessions
    WHERE kicked=false AND expires_at <= now()
    LIMIT 50
    ''')
    for r in rows:
        try:
            await bot.ban_chat_member(r['preview_chat_id'], r['user_id'])
            await bot.unban_chat_member(r['preview_chat_id'], r['user_id'], only_if_banned=True)
            await db.execute('UPDATE demo_sessions SET kicked=true WHERE id=$1', r['id'])
            try:
                await bot.send_message(r['user_id'], '⏱️ Ta démo est terminée. Le VIP contient +50.000 médias avec plusieurs options. Choisis ton accès ci-dessous.')
            except TelegramForbiddenError:
                await db.execute('UPDATE users SET blocked_bot=true WHERE user_id=$1', r['user_id'])
        except Exception as e:
            await db.log('Erreur kick demo', 'ERROR', {'demo_id': r['id'], 'error': str(e)})

async def system_check(db: Database, bot: Bot, settings) -> str:
    lines = ['ℹ️ Infos système']
    errors = 0
    try:
        await db.fetchval('SELECT 1')
        await db.execute("INSERT INTO settings(key,value) VALUES('healthcheck', now()::text) ON CONFLICT(key) DO UPDATE SET value=excluded.value")
        lines.append('✅ Base de données : lecture/écriture OK')
    except Exception as e:
        errors += 1
        lines.append(f'❌ Base de données : {e}')

    for typ in VIP_GROUPS:
        row = await db.fetchrow('SELECT chat_id,title FROM groups WHERE type=$1 AND active=true LIMIT 1', typ)
        if not row:
            errors += 1
            lines.append(f'❌ {typ} : non configuré')
            continue
        try:
            me = await bot.get_me()
            member = await bot.get_chat_member(row['chat_id'], me.id)
            status = getattr(member, 'status', '')
            if str(status).lower().endswith('administrator') or str(status).lower() == 'chatmemberstatus.ADMINISTRATOR'.lower():
                lines.append(f'✅ {typ} : bot admin dans {row["title"]}')
            else:
                errors += 1
                lines.append(f'❌ {typ} : bot non admin dans {row["title"]}')
        except Exception as e:
            errors += 1
            lines.append(f'❌ {typ} : groupe inaccessible ({e})')

    pub_count = await db.fetchval("SELECT count(*) FROM groups WHERE type='PUBLICITE' AND active=true")
    lines.append(f'✅ Groupes publicité configurés : {pub_count}')
    if settings.paypal_link or settings.paypal_email:
        lines.append('✅ PayPal configuré')
    else:
        errors += 1
        lines.append('❌ PayPal non configuré')
    pending = await db.fetchval("SELECT count(*) FROM orders WHERE status='PENDING_ADMIN'")
    lines.append(f'📦 Commandes en attente : {pending}')
    lines.append('\n🟢 Système opérationnel' if errors == 0 else f'\n🔴 {errors} problème(s) détecté(s)')
    return '\n'.join(lines)

async def grant_accesses(db: Database, bot: Bot, order_id: int) -> list[str]:
    order = await db.fetchrow('SELECT * FROM orders WHERE id=$1', order_id)
    if not order:
        raise RuntimeError('ORDER_NOT_FOUND')
    if order['status'] == 'APPROVED':
        raise RuntimeError('ORDER_ALREADY_APPROVED')
    if order['status'] not in ('PENDING_ADMIN', 'WAITING_SCREENSHOT'):
        raise RuntimeError(f'ORDER_NOT_APPROVABLE:{order["status"]}')

    group_types = []
    if order['selected_vip']:
        group_types.append(order['selected_vip'])
    if order['rediffusion']:
        group_types.append('REDIFFUSION')
    links = []
    for typ in group_types:
        exists = await db.fetchval('SELECT active FROM accesses WHERE user_id=$1 AND group_type=$2', order['user_id'], typ)
        if not exists:
            await db.execute('INSERT INTO accesses(user_id, group_type, order_id) VALUES($1,$2,$3) ON CONFLICT DO NOTHING', order['user_id'], typ, order_id)
        link = await make_unique_invite(bot, db, typ, member_limit=1, minutes=180)
        links.append(f'- {typ} : {link}')
    await db.execute("UPDATE orders SET status='APPROVED', decided_at=now() WHERE id=$1 AND status <> 'APPROVED'", order_id)
    return links

async def reject_order(db: Database, order_id: int, status: str = 'REJECTED') -> bool:
    res = await db.execute('UPDATE orders SET status=$2, decided_at=now() WHERE id=$1 AND status=$3', order_id, status, 'PENDING_ADMIN')
    return res.endswith('1')

async def mark_group_deleted_or_inactive(db: Database, chat_id: int):
    await db.execute('UPDATE groups SET active=false, updated_at=now() WHERE chat_id=$1', chat_id)
