from datetime import datetime, timedelta, timezone
from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
import db

VALID_ITEMS = {'VIP_NON_TELECHARGEABLE', 'VIP_TELECHARGEABLE', 'REDIFFUSION'}
LABELS = {
    'VIP_NON_TELECHARGEABLE': 'VIP non téléchargeable',
    'VIP_TELECHARGEABLE': 'VIP téléchargeable',
    'REDIFFUSION': 'Rediffusion téléchargeable',
}
PRICES = {'VIP_NON_TELECHARGEABLE': 8, 'VIP_TELECHARGEABLE': 10, 'REDIFFUSION': 10}


def validate_items(items: set[str]) -> tuple[bool, str]:
    if not items:
        return False, 'Choisis au moins une offre.'
    if 'VIP_NON_TELECHARGEABLE' in items and 'VIP_TELECHARGEABLE' in items:
        return False, 'Choisis un seul VIP : non téléchargeable OU téléchargeable.'
    if not items <= VALID_ITEMS:
        return False, 'Choix invalide.'
    return True, ''


def amount(items: set[str]) -> int:
    # Offres mensuelles. Le bundle VIP téléchargeable + rediffusion est plafonné à 18€.
    if items == {'VIP_TELECHARGEABLE', 'REDIFFUSION'}:
        return 18
    return sum(PRICES[i] for i in items)


def item_text(items) -> str:
    return ' + '.join(LABELS[i] for i in items)


def group_types_for_items(items) -> list[str]:
    mapping = {
        'VIP_NON_TELECHARGEABLE': 'VIP_NON_TELECHARGEABLE',
        'VIP_TELECHARGEABLE': 'VIP_TELECHARGEABLE',
        'REDIFFUSION': 'REDIFFUSION',
    }
    return [mapping[i] for i in items]

async def configured_group(bot: Bot, group_type: str):
    gs = await db.group_by_type(group_type)
    if not gs:
        raise RuntimeError(f'Groupe {group_type} non configuré')
    return gs[0]

async def create_unique_invite(bot: Bot, chat_id: int, minutes: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    link = await bot.create_chat_invite_link(chat_id=chat_id, expire_date=expire, member_limit=1, creates_join_request=False)
    return link.invite_link

async def grant_access(bot: Bot, user_id: int, items: list[str], invite_expire_minutes: int) -> list[str]:
    links = []
    for typ in group_types_for_items(items):
        group = await configured_group(bot, typ)
        links.append(await create_unique_invite(bot, group['chat_id'], invite_expire_minutes))
    await bot.send_message(user_id, '✅ Paiement validé. Voici tes accès uniques :\n\n' + '\n'.join(links) + '\n\nTon abonnement est valable 30 jours.')
    return links

async def kick_user_from_groups(bot: Bot, user_id: int, items: list[str]):
    for typ in group_types_for_items(items):
        gs = await db.group_by_type(typ)
        for g in gs:
            try:
                await bot.ban_chat_member(g['chat_id'], user_id)
                await bot.unban_chat_member(g['chat_id'], user_id, only_if_banned=True)
            except Exception as e:
                await db.log('ERROR', f'Kick impossible user={user_id} group={g["chat_id"]}: {e}')

async def verify_group(bot: Bot, chat_id: int) -> tuple[bool, str]:
    try:
        me = await bot.get_me()
        member = await bot.get_chat_member(chat_id, me.id)
        if member.status not in {'administrator', 'creator'}:
            return False, 'bot non admin'
        rights = getattr(member, 'can_invite_users', False) and getattr(member, 'can_restrict_members', False)
        if not rights:
            return False, 'droits manquants: inviter/bannir'
        return True, 'OK'
    except (TelegramForbiddenError, TelegramBadRequest) as e:
        await db.mark_group_bad(chat_id)
        return False, str(e)
    except Exception as e:
        return False, str(e)

async def safe_send(bot: Bot, user_id: int, text: str, **kwargs) -> bool:
    try:
        await bot.send_message(user_id, text, **kwargs)
        return True
    except TelegramForbiddenError:
        await db.mark_bot_blocked(user_id)
        return False
