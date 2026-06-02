from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, ChatMemberUpdated
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import load_settings
from db import Database
from keyboards import admin_panel, group_type_keyboard, offer_keyboard, admin_order_keyboard
from services import (
    upsert_user, create_demo, calculate_amount, kick_expired_demos,
    system_check, grant_accesses, reject_order
)

settings = load_settings()
bot = Bot(settings.bot_token)
dp = Dispatcher()
db = Database(settings.database_url)
scheduler = AsyncIOScheduler(timezone='UTC')

# Mémoire temporaire. Les commandes importantes sont en DB.
user_cart: dict[int, dict] = {}


def is_admin(user_id: int) -> bool:
    return user_id in settings.admin_ids


def bot_username_placeholder_warning() -> str:
    return "⚠️ Pense à remplacer YOUR_BOT_USERNAME dans keyboards.py par le username réel du bot pour le bouton publicitaire."


@dp.message(CommandStart())
async def start(message: Message):
    await upsert_user(db, message.from_user)
    if is_admin(message.from_user.id):
        await message.answer('👑 Panel admin', reply_markup=admin_panel())
        return

    arg = message.text.split(maxsplit=1)[1] if message.text and len(message.text.split()) > 1 else ''
    if arg == 'vip':
        try:
            link = await create_demo(db, bot, message.from_user.id, settings.demo_duration_minutes)
            await message.answer(
                '🔥 Voici ton accès démo VIP. Ce lien est unique et utilisable une seule fois :\n\n' + link
            )
        except RuntimeError as e:
            if str(e) == 'DEMO_ALREADY_USED':
                await message.answer('Tu as déjà utilisé ta démo. Voici les offres VIP :', reply_markup=offer_keyboard())
            elif str(e) == 'VIP_PREVIEW_MISSING':
                await message.answer('La démo est temporairement indisponible. Un admin doit configurer le groupe VIP Preview.')
            else:
                await message.answer('Erreur temporaire. Réessaie plus tard.')
        return

    await message.answer('Bienvenue. Clique sur une publicité VIP pour recevoir ton accès démo.')


@dp.message(Command('admin'))
async def admin(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer('👑 Panel admin', reply_markup=admin_panel())


@dp.my_chat_member()
async def bot_added_or_removed(event: ChatMemberUpdated):
    chat = event.chat
    if chat.type not in ('group', 'supergroup', 'channel'):
        return
    status = event.new_chat_member.status
    if str(status).lower().endswith('left') or str(status).lower().endswith('kicked'):
        await db.execute('UPDATE groups SET active=false, updated_at=now() WHERE chat_id=$1', chat.id)
        return

    await db.execute('''
    INSERT INTO groups(chat_id,title,type,active)
    VALUES($1,$2,'UNASSIGNED',true)
    ON CONFLICT(chat_id) DO UPDATE SET title=$2, active=true, updated_at=now()
    ''', chat.id, chat.title or str(chat.id))

    for admin_id in settings.admin_ids:
        try:
            await bot.send_message(
                admin_id,
                f'🆕 Nouveau groupe détecté :\n{chat.title}\nID : {chat.id}\n\nChoisis son type :',
                reply_markup=group_type_keyboard(chat.id)
            )
        except TelegramForbiddenError:
            await db.log('Admin inaccessible', 'WARNING', {'admin_id': admin_id})


@dp.callback_query(F.data.startswith('group:set:'))
async def set_group_type(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer('Accès refusé', show_alert=True)
    _, _, chat_id, typ = call.data.split(':')
    await db.execute('UPDATE groups SET type=$2, active=true, updated_at=now() WHERE chat_id=$1', int(chat_id), typ)
    await call.message.edit_text(f'✅ Groupe configuré en : {typ}')


@dp.callback_query(F.data.startswith('admin:'))
async def admin_buttons(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer('Accès refusé', show_alert=True)
    action = call.data.split(':')[1]

    if action == 'info':
        await call.message.answer(await system_check(db, bot, settings))
    elif action == 'repair':
        await repair_groups(call.message)
    elif action == 'payment':
        await call.message.answer(
            f'💳 Paiement configuré :\nPayPal link : {settings.paypal_link or "NON CONFIGURÉ"}\nPayPal email : {settings.paypal_email or "NON CONFIGURÉ"}\n\nPour modifier : change PAYPAL_LINK / PAYPAL_EMAIL dans Railway puis redéploie.'
        )
    elif action == 'groups':
        rows = await db.fetch('SELECT chat_id,title,type,active FROM groups ORDER BY created_at DESC LIMIT 50')
        if not rows:
            await call.message.answer('Aucun groupe détecté.')
        else:
            txt = '👥 Groupes détectés\n\n' + '\n'.join([f'{"✅" if r["active"] else "❌"} {r["title"]} — {r["type"]} — {r["chat_id"]}' for r in rows])
            await call.message.answer(txt)
    elif action == 'orders':
        rows = await db.fetch("SELECT id,user_id,username,selected_vip,rediffusion,amount,status FROM orders ORDER BY created_at DESC LIMIT 20")
        if not rows:
            await call.message.answer('Aucune commande.')
        else:
            await call.message.answer('\n\n'.join([f'#{r["id"]} @{r["username"]} {r["selected_vip"] or ""} rediff={r["rediffusion"]} {r["amount"]}€ — {r["status"]}' for r in rows]))
    elif action == 'stats':
        users = await db.fetchval('SELECT count(*) FROM users')
        demos = await db.fetchval('SELECT count(*) FROM users WHERE demo_used=true')
        sales = await db.fetchval("SELECT count(*) FROM orders WHERE status='APPROVED'")
        revenue = await db.fetchval("SELECT coalesce(sum(amount),0) FROM orders WHERE status='APPROVED'")
        pending = await db.fetchval("SELECT count(*) FROM orders WHERE status='PENDING_ADMIN'")
        await call.message.answer(f'📊 Stats\nUtilisateurs : {users}\nDémos : {demos}\nVentes validées : {sales}\nCA validé : {revenue}€\nEn attente : {pending}')
    else:
        await call.message.answer('Fonction à développer dans le panel détaillé. Le cœur du bot est prêt.')
    await call.answer()


async def repair_groups(message: Message):
    rows = await db.fetch('SELECT chat_id,title,type FROM groups WHERE active=true')
    fixed = []
    for r in rows:
        try:
            await bot.get_chat(r['chat_id'])
            fixed.append(f'✅ {r["title"]}')
        except Exception as e:
            await db.execute('UPDATE groups SET active=false, updated_at=now() WHERE chat_id=$1', r['chat_id'])
            fixed.append(f'❌ {r["title"]} désactivé ({e})')
    await message.answer('🔧 Revérification terminée\n\n' + ('\n'.join(fixed) if fixed else 'Aucun groupe à vérifier.'))


@dp.callback_query(F.data.startswith('offer:'))
async def offers(call: CallbackQuery):
    uid = call.from_user.id
    await upsert_user(db, call.from_user)
    cart = user_cart.setdefault(uid, {'vip': None, 'rediffusion': False})
    action = call.data.split(':')[1]

    if action == 'vip_non':
        cart['vip'] = None if cart['vip'] == 'VIP_NON_TELECHARGEABLE' else 'VIP_NON_TELECHARGEABLE'
    elif action == 'vip_tel':
        cart['vip'] = None if cart['vip'] == 'VIP_TELECHARGEABLE' else 'VIP_TELECHARGEABLE'
    elif action == 'rediff':
        cart['rediffusion'] = not cart['rediffusion']
    elif action == 'next':
        if not cart['vip'] and not cart['rediffusion']:
            return await call.answer('Choisis au moins une offre.', show_alert=True)
        amount = calculate_amount(cart['vip'], cart['rediffusion'])
        order_id = await db.fetchval('''
        INSERT INTO orders(user_id, username, selected_vip, rediffusion, amount)
        VALUES($1,$2,$3,$4,$5) RETURNING id
        ''', uid, call.from_user.username, cart['vip'], cart['rediffusion'], amount)
        await call.message.answer(
            f'💳 Montant final : {amount}€\n\nPayPal : {settings.paypal_link or settings.paypal_email}\n\nAprès paiement, envoie une capture d’écran ici.\nCommande #{order_id}'
        )
        return await call.answer()

    amount = calculate_amount(cart['vip'], cart['rediffusion'])
    await call.message.edit_text(f'Choisissez vos accès :\n\nTotal actuel : {amount}€', reply_markup=offer_keyboard(cart['vip'], cart['rediffusion']))
    await call.answer()


@dp.message(F.photo | F.document)
async def receive_screenshot(message: Message):
    if is_admin(message.from_user.id):
        return
    await upsert_user(db, message.from_user)
    order = await db.fetchrow("SELECT * FROM orders WHERE user_id=$1 AND status='WAITING_SCREENSHOT' ORDER BY id DESC LIMIT 1", message.from_user.id)
    if not order:
        return await message.answer('Je n’ai pas trouvé de commande en attente. Clique d’abord sur une offre puis Suivant.')

    file_id = None
    if message.photo:
        file_id = message.photo[-1].file_id
    elif message.document and (message.document.mime_type or '').startswith('image/'):
        file_id = message.document.file_id
    else:
        return await message.answer('Capture illisible : envoie une image/photo claire du paiement.')

    await db.execute("UPDATE orders SET screenshot_file_id=$2, status='PENDING_ADMIN' WHERE id=$1", order['id'], file_id)
    await message.answer('✅ Capture reçue. Un admin va vérifier ton paiement.')

    text = (
        f'🧾 Nouvelle demande VIP #{order["id"]}\n\n'
        f'Utilisateur : @{message.from_user.username or "sans_username"}\nID : {message.from_user.id}\n'
        f'Choix : {order["selected_vip"] or ""} {"+ REDIFFUSION" if order["rediffusion"] else ""}\n'
        f'Montant : {order["amount"]}€\n\n'
        'Valider uniquement si le paiement est correct.'
    )
    for admin_id in settings.admin_ids:
        try:
            sent_photo = await bot.send_photo(admin_id, file_id, caption=text, reply_markup=admin_order_keyboard(order['id']))
            await db.execute('UPDATE orders SET admin_message_chat_id=$2, admin_message_id=$3 WHERE id=$1', order['id'], admin_id, sent_photo.message_id)
        except TelegramForbiddenError:
            await db.log('Admin inaccessible pour validation', 'WARNING', {'admin_id': admin_id, 'order_id': order['id']})


@dp.callback_query(F.data.startswith('order:'))
async def order_actions(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer('Accès refusé', show_alert=True)
    _, action, order_id_s = call.data.split(':')
    order_id = int(order_id_s)
    order = await db.fetchrow('SELECT * FROM orders WHERE id=$1', order_id)
    if not order:
        return await call.answer('Commande introuvable', show_alert=True)

    if action == 'approve':
        if order['status'] == 'APPROVED':
            return await call.answer('Déjà validée.', show_alert=True)
        if order['status'] != 'PENDING_ADMIN':
            return await call.answer(f'Commande non validable : {order["status"]}', show_alert=True)
        try:
            links = await grant_accesses(db, bot, order_id)
            await bot.send_message(order['user_id'], '✅ Paiement validé. Voici tes accès uniques :\n\n' + '\n'.join(links))
            await call.message.edit_caption((call.message.caption or '') + '\n\n✅ VALIDÉ')
        except TelegramForbiddenError:
            await db.execute('UPDATE users SET blocked_bot=true WHERE user_id=$1', order['user_id'])
            await call.answer('Utilisateur bloque le bot. Validation enregistrée, mais impossible de lui envoyer le lien.', show_alert=True)
        except Exception as e:
            await db.log('Erreur validation commande', 'ERROR', {'order_id': order_id, 'error': str(e)})
            await call.answer(f'Erreur : {e}', show_alert=True)
    elif action == 'reject':
        ok = await reject_order(db, order_id, 'REJECTED')
        if not ok:
            return await call.answer('Déjà traitée ou non rejetable.', show_alert=True)
        try:
            await bot.send_message(order['user_id'], '❌ Paiement refusé. Merci de renvoyer une capture valide ou de contacter un admin.')
        except TelegramForbiddenError:
            await db.execute('UPDATE users SET blocked_bot=true WHERE user_id=$1', order['user_id'])
        await call.message.edit_caption((call.message.caption or '') + '\n\n❌ REFUSÉ')
    elif action == 'rescreen':
        await db.execute("UPDATE orders SET status='WAITING_SCREENSHOT' WHERE id=$1 AND status='PENDING_ADMIN'", order_id)
        try:
            await bot.send_message(order['user_id'], '✉️ Capture illisible ou incomplète. Merci d’envoyer une nouvelle capture claire du paiement.')
        except TelegramForbiddenError:
            await db.execute('UPDATE users SET blocked_bot=true WHERE user_id=$1', order['user_id'])
        await call.message.edit_caption((call.message.caption or '') + '\n\n✉️ Nouvelle capture demandée')
    await call.answer()


@dp.chat_member()
async def member_updates(event: ChatMemberUpdated):
    # Cas utilisateur quitte un groupe VIP : on garde l'accès en DB, il pourra recevoir un nouveau lien via admin si besoin.
    if event.chat.type not in ('group', 'supergroup', 'channel'):
        return
    if str(event.new_chat_member.status).lower().endswith('left'):
        await db.log('Utilisateur a quitté un groupe', 'INFO', {'chat_id': event.chat.id, 'user_id': event.from_user.id})


async def send_due_ads():
    # Base prête pour campagnes programmées. À brancher sur un écran admin de création détaillé.
    rows = await db.fetch('''
    SELECT * FROM ad_campaigns
    WHERE active=true AND interval_minutes IS NOT NULL
      AND (last_sent_at IS NULL OR last_sent_at <= now() - (interval_minutes || ' minutes')::interval)
    LIMIT 10
    ''')
    me = await bot.get_me()
    from keyboards import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='🔥 Accès VIP', url=f'https://t.me/{me.username}?start=vip')]])
    for camp in rows:
        for chat_id in camp['target_chat_ids']:
            try:
                if camp['photo_file_id']:
                    await bot.send_photo(chat_id, camp['photo_file_id'], caption=camp['text'], reply_markup=kb)
                else:
                    await bot.send_message(chat_id, camp['text'], reply_markup=kb)
            except Exception as e:
                await db.log('Erreur envoi publicité', 'ERROR', {'campaign_id': camp['id'], 'chat_id': chat_id, 'error': str(e)})
        await db.execute('UPDATE ad_campaigns SET last_sent_at=now() WHERE id=$1', camp['id'])


async def main():
    await db.connect()
    scheduler.add_job(kick_expired_demos, 'interval', seconds=30, args=[db, bot], id='kick_expired_demos')
    scheduler.add_job(send_due_ads, 'interval', minutes=1, id='send_due_ads')
    scheduler.start()
    me = await bot.get_me()
    print(f'Bot lancé : @{me.username}')
    print(bot_username_placeholder_warning())
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())
