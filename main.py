import asyncio
from datetime import datetime
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ChatType
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, ChatMemberUpdated
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

from config import load_settings
import db
import keyboards as kb
import services as svc

load_dotenv()
settings = load_settings()
bot = Bot(settings.bot_token)
dp = Dispatcher()
r = Router()
dp.include_router(r)
user_selection: dict[int, set[str]] = {}


def is_admin(user_id: int) -> bool:
    return user_id in settings.admin_ids

async def notify_admins(text: str, **kwargs):
    for admin_id in settings.admin_ids:
        try:
            await bot.send_message(admin_id, text, **kwargs)
        except Exception:
            pass

@r.message(CommandStart())
async def start(message: Message):
    await db.upsert_user(message.from_user)
    if is_admin(message.from_user.id):
        await message.answer('👑 Panel admin', reply_markup=kb.admin_panel())
        return
    args = (message.text or '').split(maxsplit=1)
    if len(args) > 1 and args[1] == 'vip':
        await give_demo(message)
    else:
        await message.answer('Bienvenue. Clique sur une publicité VIP pour recevoir ton accès démo.')

@r.message(Command('admin'))
async def admin_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer('👑 Panel admin', reply_markup=kb.admin_panel())

@r.message(Command('groupes'))
async def groupes_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return
    groups = await db.groups()
    if not groups:
        await message.answer('Aucun groupe détecté. Ajoute le bot dans les groupes puis donne-lui les droits admin.')
        return
    await message.answer('👥 Groupes détectés', reply_markup=kb.group_list(groups))

@r.my_chat_member()
async def bot_joined(event: ChatMemberUpdated):
    chat = event.chat
    if chat.type in {ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL}:
        status = event.new_chat_member.status
        if status in {'member', 'administrator'}:
            await db.upsert_group(chat.id, chat.title or str(chat.id))
            await notify_admins(f'Nouveau groupe détecté :\n{chat.title}\nID : {chat.id}\n\nVa dans 👥 Groupes pour l’associer.')
        elif status in {'left', 'kicked'}:
            await db.mark_group_bad(chat.id)

@r.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def detect_group_message(message: Message):
    await db.upsert_group(message.chat.id, message.chat.title or str(message.chat.id))

async def give_demo(message: Message):
    user_id = message.from_user.id
    if await db.has_demo_used(user_id):
        await message.answer('Tu as déjà utilisé ta démo. Voici les offres mensuelles :', reply_markup=kb.offer_keyboard())
        return
    gs = await db.group_by_type('VIP_PREVIEW')
    if not gs:
        await message.answer('La démo est temporairement indisponible. Un admin doit configurer le groupe VIP Preview.')
        await notify_admins('❌ VIP_PREVIEW non configuré : impossible de donner une démo.')
        return
    try:
        link = await svc.create_unique_invite(bot, gs[0]['chat_id'], settings.invite_expire_minutes)
        await db.create_demo(user_id, link)
        await message.answer('✅ Voici ton accès démo unique :\n' + link)
    except Exception as e:
        await message.answer('Erreur lors de la création du lien démo. Un admin a été prévenu.')
        await notify_admins(f'❌ Erreur lien démo : {e}')

@r.chat_member()
async def user_joined_group(event: ChatMemberUpdated):
    if event.new_chat_member.status in {'member', 'administrator'}:
        gs = await db.group_by_type('VIP_PREVIEW')
        if gs and event.chat.id == gs[0]['chat_id']:
            await db.set_demo_joined(event.from_user.id)

@r.callback_query(F.data == 'admin:panel')
async def cb_panel(c: CallbackQuery):
    if is_admin(c.from_user.id):
        await c.message.edit_text('👑 Panel admin', reply_markup=kb.admin_panel())
    await c.answer()

@r.callback_query(F.data == 'admin:groups')
async def cb_groups(c: CallbackQuery):
    if not is_admin(c.from_user.id): return await c.answer()
    await c.message.edit_text('👥 Groupes détectés', reply_markup=kb.group_list(await db.groups()))
    await c.answer()

@r.callback_query(F.data.startswith('group:'))
async def cb_group(c: CallbackQuery):
    if not is_admin(c.from_user.id): return await c.answer()
    chat_id = int(c.data.split(':')[1])
    await c.message.edit_text(f'Associer le groupe {chat_id}', reply_markup=kb.assign_group(chat_id))
    await c.answer()

@r.callback_query(F.data.startswith('assign:'))
async def cb_assign(c: CallbackQuery):
    if not is_admin(c.from_user.id): return await c.answer()
    _, chat_id, typ = c.data.split(':')
    await db.set_group_type(int(chat_id), typ)
    await c.message.edit_text(f'✅ Groupe associé à {typ}', reply_markup=kb.group_list(await db.groups()))
    await c.answer('Groupe associé')

@r.callback_query(F.data == 'admin:info')
async def cb_info(c: CallbackQuery):
    if not is_admin(c.from_user.id): return await c.answer()
    lines = ['ℹ️ Infos système']
    problems = 0
    try:
        ok = await db.test_rw()
        lines.append('✅ Base de données : lecture/écriture OK' if ok else '❌ Base de données : erreur')
        problems += 0 if ok else 1
    except Exception as e:
        lines.append(f'❌ Base de données : {e}')
        problems += 1
    all_groups = await db.groups()
    types = {g['type'] for g in all_groups if g['type']}
    for required in ['VIP_PREVIEW','VIP_NON_TELECHARGEABLE','VIP_TELECHARGEABLE','REDIFFUSION']:
        if required in types:
            gs = [g for g in all_groups if g['type'] == required]
            ok, reason = await svc.verify_group(bot, gs[0]['chat_id'])
            lines.append(('✅' if ok else '❌') + f' {required} : {reason}')
            problems += 0 if ok else 1
        else:
            lines.append(f'❌ {required} : non configuré')
            problems += 1
    pub_count = len([g for g in all_groups if g['type'] == 'PUBLICITE'])
    lines.append(f"{'✅' if pub_count else '⚠️'} Groupes publicité configurés : {pub_count}")
    lines.append('✅ PayPal configuré' if settings.paypal_link else '❌ PayPal non configuré')
    if not settings.paypal_link: problems += 1
    lines.append(f"📦 Commandes en attente : {len(await db.pending_orders())}")
    lines.append(('🟢 Aucun problème' if problems == 0 else f'🔴 {problems} problème(s) détecté(s)'))
    await c.message.answer('\n'.join(lines))
    await c.answer()

@r.callback_query(F.data == 'admin:paypal')
async def cb_paypal(c: CallbackQuery):
    if not is_admin(c.from_user.id): return await c.answer()
    await c.message.answer('💳 PayPal actuel :\n' + (settings.paypal_link or 'Non configuré') + '\n\nPour modifier : change PAYPAL_LINK dans Railway puis redémarre.')
    await c.answer()

@r.callback_query(F.data == 'admin:send_ad')
async def cb_send_ad(c: CallbackQuery):
    if not is_admin(c.from_user.id): return await c.answer()
    pubs = await db.group_by_type('PUBLICITE')
    me = await bot.get_me()
    sent = 0
    for g in pubs:
        try:
            markup = kb.access_vip()
            markup.inline_keyboard[0][0].url = f'https://t.me/{me.username}?start=vip'
            await bot.send_message(g['chat_id'], '🔥 Accès VIP\n\nDémo gratuite puis abonnement mensuel. Clique ici :', reply_markup=markup)
            sent += 1
        except Exception as e:
            await db.log('ERROR', f'Pub impossible groupe={g["chat_id"]}: {e}')
    await c.message.answer(f'📢 Publicité envoyée dans {sent} groupe(s).')
    await c.answer()

@r.callback_query(F.data.startswith('offer:toggle:'))
async def cb_offer_toggle(c: CallbackQuery):
    item = c.data.split(':')[2]
    sel = user_selection.setdefault(c.from_user.id, set())
    if item in sel: sel.remove(item)
    else:
        if item == 'VIP_NON_TELECHARGEABLE': sel.discard('VIP_TELECHARGEABLE')
        if item == 'VIP_TELECHARGEABLE': sel.discard('VIP_NON_TELECHARGEABLE')
        sel.add(item)
    await c.message.edit_reply_markup(reply_markup=kb.offer_keyboard(sel))
    await c.answer()

@r.callback_query(F.data == 'offer:next')
async def cb_offer_next(c: CallbackQuery):
    await db.upsert_user(c.from_user)
    sel = user_selection.get(c.from_user.id, set())
    ok, err = svc.validate_items(sel)
    if not ok:
        return await c.answer(err, show_alert=True)
    total = svc.amount(sel)
    order_id = await db.create_order(c.from_user.id, list(sel), total)
    await c.message.answer(f'💳 Montant mensuel : {total}€\n\nPayPal :\n{settings.paypal_link}\n\nAprès paiement, envoie ici une capture d’écran.\nCommande #{order_id}')
    await c.answer()

@r.message(F.photo | F.document)
async def screenshot(message: Message):
    await db.upsert_user(message.from_user)
    file_id = None
    if message.photo:
        file_id = message.photo[-1].file_id
    elif message.document and message.document.mime_type and message.document.mime_type.startswith('image/'):
        file_id = message.document.file_id
    if not file_id:
        await message.answer('Capture illisible. Envoie une image ou une photo claire du paiement.')
        return
    order = await db.attach_screenshot(message.from_user.id, file_id)
    if not order:
        await message.answer('Aucune commande en attente. Choisis une offre avant d’envoyer une capture.')
        return
    caption = f"📦 Nouvelle commande #{order['id']}\nUtilisateur : @{message.from_user.username or 'sans_username'}\nID : {message.from_user.id}\nChoix : {svc.item_text(order['items'])}\nMontant : {order['amount']}€/mois"
    for admin_id in settings.admin_ids:
        try:
            await bot.send_photo(admin_id, file_id, caption=caption, reply_markup=kb.validate_keyboard(order['id']))
        except Exception:
            pass
    await message.answer('✅ Capture reçue. Un admin va vérifier ton paiement.')

@r.callback_query(F.data.startswith('order:'))
async def cb_order(c: CallbackQuery):
    if not is_admin(c.from_user.id): return await c.answer()
    _, action, oid = c.data.split(':')
    order_id = int(oid)
    if action == 'approve':
        order = await db.decide_order(order_id, c.from_user.id, 'APPROVED')
        if not order:
            return await c.answer('Commande déjà traitée.', show_alert=True)
        await db.activate_subscription(order['user_id'], list(order['items']), order_id, settings.subscription_days)
        try:
            await svc.grant_access(bot, order['user_id'], list(order['items']), settings.invite_expire_minutes)
        except Exception as e:
            await notify_admins(f'❌ Paiement validé mais accès non envoyé pour commande #{order_id}: {e}')
        await c.message.edit_caption((c.message.caption or '') + '\n\n✅ Validée')
        await c.answer('Validé')
    elif action == 'reject':
        order = await db.decide_order(order_id, c.from_user.id, 'REJECTED')
        if not order:
            return await c.answer('Commande déjà traitée.', show_alert=True)
        await svc.safe_send(bot, order['user_id'], '❌ Paiement refusé. Envoie une capture valide ou contacte un admin.')
        await c.message.edit_caption((c.message.caption or '') + '\n\n❌ Refusée')
        await c.answer('Refusé')
    elif action == 'resend':
        order = await db.get_order(order_id)
        if order:
            await svc.safe_send(bot, order['user_id'], '📸 Merci de renvoyer une capture plus lisible du paiement.')
        await c.answer('Demande envoyée')

async def kick_expired_demos():
    gs = await db.group_by_type('VIP_PREVIEW')
    if not gs: return
    chat_id = gs[0]['chat_id']
    for demo in await db.demos_to_kick(settings.demo_duration_minutes):
        try:
            await bot.ban_chat_member(chat_id, demo['user_id'])
            await bot.unban_chat_member(chat_id, demo['user_id'], only_if_banned=True)
            await svc.safe_send(bot, demo['user_id'], '⏱️ Ta démo est terminée. Tu peux maintenant choisir ton accès mensuel.', reply_markup=kb.offer_keyboard())
        except Exception as e:
            await db.log('ERROR', f'Kick demo impossible user={demo["user_id"]}: {e}')
        finally:
            await db.mark_demo_kicked(demo['user_id'])

async def monthly_reminders_and_expiry():
    for days in (10, 5, 3):
        for sub in await db.subscriptions_for_reminders(days):
            if days == 3:
                await svc.safe_send(bot, sub['user_id'], '📦 Ton abonnement expire dans 3 jours. Tu peux renouveler ou changer de formule :', reply_markup=kb.offer_keyboard(set(sub['items'])))
            else:
                await svc.safe_send(bot, sub['user_id'], f'⏳ Ton accès VIP expire dans {days} jours. Pense à renouveler pour garder ton accès.')
            await db.mark_reminded(sub['id'], days)
    for sub in await db.expired_subscriptions():
        await svc.kick_user_from_groups(bot, sub['user_id'], list(sub['items']))
        await db.deactivate_subscription(sub['id'])
        await svc.safe_send(bot, sub['user_id'], '🔒 Ton abonnement a expiré. Tu as été retiré des groupes. Renouvelle pour récupérer un accès.')

async def main():
    await db.connect(settings.database_url)
    scheduler = AsyncIOScheduler(timezone=settings.timezone)
    scheduler.add_job(kick_expired_demos, 'interval', minutes=1, id='kick_demos', replace_existing=True)
    scheduler.add_job(monthly_reminders_and_expiry, 'interval', hours=6, id='monthly', replace_existing=True)
    scheduler.start()
    await notify_admins('✅ Bot démarré sur Railway.')
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
