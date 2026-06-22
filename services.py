from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
import db

VALID_ITEMS = {'VIP_NON_TELECHARGEABLE', 'VIP_TELECHARGEABLE', 'REDIFFUSION'}
LABELS = {
    'VIP_NON_TELECHARGEABLE': 'VIP non téléchargeable',
    'VIP_TELECHARGEABLE': 'VIP téléchargeable',
    'REDIFFUSION': 'Rediffusion téléchargeable',
}

PRICES = {'VIP_NON_TELECHARGEABLE': Decimal('10'), 'VIP_TELECHARGEABLE': Decimal('16'), 'REDIFFUSION': Decimal('15')}
DISCOUNTS = {'FIRST_50': Decimal('50'), 'DISCOVERY_6D': Decimal('50'), 'REACTIVATION_30': Decimal('30')}

def money(v) -> Decimal:
    return Decimal(str(v)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

def eur(v) -> str:
    d = money(v)
    if d == d.to_integral_value():
        return f"{int(d)}€"
    return f"{str(d).replace('.', ',')}€"

async def refresh_pricing():
    data = await db.pricing_settings()
    PRICES['VIP_NON_TELECHARGEABLE'] = money(data.get('price_VIP_NON_TELECHARGEABLE', '10'))
    PRICES['VIP_TELECHARGEABLE'] = money(data.get('price_VIP_TELECHARGEABLE', '16'))
    PRICES['REDIFFUSION'] = money(data.get('price_REDIFFUSION', '15'))
    DISCOUNTS['FIRST_50'] = money(data.get('discount_FIRST_50', '50'))
    DISCOUNTS['DISCOVERY_6D'] = money(data.get('discount_DISCOVERY_6D', '50'))
    DISCOUNTS['REACTIVATION_30'] = money(data.get('discount_REACTIVATION_30', '30'))
    return PRICES

def discounted(price: Decimal, percent: Decimal) -> Decimal:
    return money(price * (Decimal('100') - percent) / Decimal('100'))

def promo_price(item: str, promo_code: str | None = None) -> Decimal:
    base = PRICES[item]
    if promo_code == 'FIRST_50':
        return discounted(base, DISCOUNTS['FIRST_50'])
    if promo_code == 'DISCOVERY_6D':
        return discounted(base, DISCOUNTS['DISCOVERY_6D'])
    if promo_code == 'REACTIVATION_30':
        return discounted(base, DISCOUNTS['REACTIVATION_30'])
    return base

def validate_items(items: set[str]) -> tuple[bool, str]:
    if not items:
        return False, 'Choisis au moins une offre.'
    if 'VIP_NON_TELECHARGEABLE' in items and 'VIP_TELECHARGEABLE' in items:
        return False, 'Choisis un seul VIP : non téléchargeable OU téléchargeable.'
    if not items <= VALID_ITEMS:
        return False, 'Choix invalide.'
    return True, ''

def validate_discovery_items(items: set[str]) -> tuple[bool, str]:
    ok, msg = validate_items(items)
    if not ok:
        return ok, msg
    if 'VIP_TELECHARGEABLE' in items:
        return False, "L'offre découverte ne contient pas le VIP téléchargeable."
    return True, ''

def amount(items: set[str], promo_code: str | None = None) -> Decimal:
    if promo_code == 'FIRST_2PLUS1':
        return money(sum(PRICES[i] for i in items) * 2)
    return money(sum(promo_price(i, promo_code) for i in items))

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

async def kick_user_from_groups(bot: Bot, user_id: int, items: list[str]) -> tuple[bool, list[str]]:
    """Expulse un utilisateur des groupes liés à ses items.

    Retourne (ok, errors). On ne doit marquer l'abonnement terminé
    que si tous les kicks Telegram nécessaires ont réussi.
    """
    errors: list[str] = []
    attempted = 0
    for typ in group_types_for_items(items):
        gs = await db.group_by_type(typ)
        if not gs:
            errors.append(f'Groupe {typ} non configuré')
            continue
        for g in gs:
            attempted += 1
            try:
                await bot.ban_chat_member(g['chat_id'], user_id)
                await bot.unban_chat_member(g['chat_id'], user_id, only_if_banned=True)
            except Exception as e:
                msg = f'Kick impossible user={user_id} group={g["chat_id"]} ({g.get("title", typ)}): {e}'
                errors.append(msg)
                await db.log('ERROR', msg)
    if attempted == 0:
        errors.append('Aucun groupe cible trouvé')
    return (len(errors) == 0), errors

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
