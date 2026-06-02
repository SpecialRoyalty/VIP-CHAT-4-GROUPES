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
admin_modes: dict[int, str] = {}
ad_group_selection: dict[int, set[int]] = {}


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
        await db.create_demo(user_id, gs[0]['chat_id'], link)
        await message.answer('✅ Voici ton accès démo unique :\n' + link)
    except Exception as e:
        await message.answer('Erreur lors de la création du lien démo. Un admin a été prévenu.')
        await notify_admins(f'❌ Erreur lien démo : {e}')

@r.chat_member()
async def user_joined_group(event: ChatMemberUpdated):
    if event.new_chat_member.status in {'member', 'administrator'}:
        gs = await db.group_by_type('VIP_PREVIEW')
        if gs and event.chat.id == gs[0]['chat_id']:
            user_id = event.new_chat_member.user.id
            demo = await db.demo_for_user(user_id)
            if demo and demo['kicked_at'] is None:
                await db.set_demo_joined(user_id)
            else:
                # Sécurité : toute entrée dans le groupe démo sans session active est expulsée.
                try:
                    await bot.ban_chat_member(event.chat.id, user_id)
                    await bot.unban_chat_member(event.chat.id, user_id, only_if_banned=True)
                    await db.log('WARNING', f'Entrée preview non autorisée expulsée user={user_id} group={event.chat.id}')
                except Exception as e:
                    err = str(e)
                    await db.log('ERROR', f'Kick entrée preview non autorisée impossible user={user_id} group={event.chat.id}: {err}')
                    await notify_admins(
                        '🚨 Échec expulsion entrée non autorisée\n\n'
                        f'Utilisateur ID : {user_id}\n'
                        f'Groupe : {event.chat.title or event.chat.id}\n'
                        f'ID Groupe : {event.chat.id}\n\n'
                        f'Erreur Telegram : {err}\n\n'
                        'Vérifie que le bot est admin et possède le droit “Bannir des membres”.'
                    )

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


async def get_ad_config():
    text = await db.get_setting('ad_text', '🔥 Accès VIP\n\nDémo gratuite puis abonnement mensuel. Clique ici :')
    photo = await db.get_setting('ad_photo_file_id', '')
    return text, photo

async def send_ad_to_group(chat_id: int) -> bool:
    me = await bot.get_me()
    text, photo = await get_ad_config()
    markup = kb.access_vip()
    markup.inline_keyboard[0][0].url = f'https://t.me/{me.username}?start=vip'
    try:
        if photo:
            await bot.send_photo(chat_id, photo, caption=text, reply_markup=markup)
        else:
            await bot.send_message(chat_id, text, reply_markup=markup)
        return True
    except Exception as e:
        await db.log('ERROR', f'Pub impossible groupe={chat_id}: {e}')
        return False

@r.callback_query(F.data == 'admin:send_ad')
async def cb_send_ad(c: CallbackQuery):
    if not is_admin(c.from_user.id): return await c.answer()
    await c.message.edit_text('📢 Publicités', reply_markup=kb.ads_panel())
    await c.answer()

@r.callback_query(F.data == 'admin:ads')
async def cb_ads(c: CallbackQuery):
    if not is_admin(c.from_user.id): return await c.answer()
    await c.message.edit_text('📢 Publicités', reply_markup=kb.ads_panel())
    await c.answer()

@r.callback_query(F.data == 'ad:set_text')
async def cb_ad_set_text(c: CallbackQuery):
    if not is_admin(c.from_user.id): return await c.answer()
    admin_modes[c.from_user.id] = 'ad_text'
    await c.message.answer('✏️ Envoie maintenant le nouveau texte de publicité.')
    await c.answer()

@r.callback_query(F.data == 'ad:set_photo')
async def cb_ad_set_photo(c: CallbackQuery):
    if not is_admin(c.from_user.id): return await c.answer()
    admin_modes[c.from_user.id] = 'ad_photo'
    await c.message.answer('🖼 Envoie maintenant la photo/image de publicité.')
    await c.answer()

@r.callback_query(F.data == 'ad:clear_photo')
async def cb_ad_clear_photo(c: CallbackQuery):
    if not is_admin(c.from_user.id): return await c.answer()
    await db.set_setting('ad_photo_file_id', '')
    await c.message.answer('✅ Image de publicité retirée.')
    await c.answer()

@r.callback_query(F.data == 'ad:preview')
async def cb_ad_preview(c: CallbackQuery):
    if not is_admin(c.from_user.id): return await c.answer()
    text, photo = await get_ad_config()
    me = await bot.get_me()
    markup = kb.access_vip()
    markup.inline_keyboard[0][0].url = f'https://t.me/{me.username}?start=vip'
    if photo:
        await c.message.answer_photo(photo, caption=text, reply_markup=markup)
    else:
        await c.message.answer(text, reply_markup=markup)
    await c.answer()

@r.callback_query(F.data == 'ad:choose_groups')
async def cb_ad_choose_groups(c: CallbackQuery):
    if not is_admin(c.from_user.id): return await c.answer()
    pubs = await db.group_by_type('PUBLICITE')
    ad_group_selection[c.from_user.id] = set()
    if not pubs:
        await c.message.answer('Aucun groupe de publicité configuré. Va dans 👥 Groupes et associe au moins un groupe en PUBLICITE.')
    else:
        await c.message.edit_text('Choisis un ou plusieurs groupes de publicité :', reply_markup=kb.ad_groups(pubs, set()))
    await c.answer()

@r.callback_query(F.data.startswith('ad:toggle_group:'))
async def cb_ad_toggle_group(c: CallbackQuery):
    if not is_admin(c.from_user.id): return await c.answer()
    chat_id = int(c.data.split(':')[2])
    sel = ad_group_selection.setdefault(c.from_user.id, set())
    if chat_id in sel: sel.remove(chat_id)
    else: sel.add(chat_id)
    pubs = await db.group_by_type('PUBLICITE')
    await c.message.edit_reply_markup(reply_markup=kb.ad_groups(pubs, sel))
    await c.answer()

@r.callback_query(F.data == 'ad:send_selected')
async def cb_ad_send_selected(c: CallbackQuery):
    if not is_admin(c.from_user.id): return await c.answer()
    selected = ad_group_selection.get(c.from_user.id, set())
    if not selected:
        return await c.answer('Coche au moins un groupe.', show_alert=True)
    sent = 0
    for chat_id in selected:
        if await send_ad_to_group(chat_id):
            sent += 1
    await c.message.answer(f'📢 Publicité envoyée dans {sent}/{len(selected)} groupe(s).')
    await c.answer()


@r.callback_query(F.data == 'admin:orders')
async def cb_orders(c: CallbackQuery):
    if not is_admin(c.from_user.id): return await c.answer()
    orders = await db.recent_orders(15)
    if not orders:
        await c.message.answer('📦 Aucune commande pour le moment.')
    else:
        await c.message.edit_text('📦 Commandes récentes', reply_markup=kb.orders_panel(orders))
    await c.answer()

@r.callback_query(F.data.startswith('order:view:'))
async def cb_order_view(c: CallbackQuery):
    if not is_admin(c.from_user.id): return await c.answer()
    oid = int(c.data.split(':')[2])
    order = await db.get_order(oid)
    if not order:
        return await c.answer('Commande introuvable.', show_alert=True)
    txt = f"📦 Commande #{order['id']}\nStatut : {order['status']}\nUtilisateur : {order['user_id']}\nChoix : {svc.item_text(order['items'])}\nMontant : {order['amount']}€/mois"
    if order['screenshot_file_id']:
        await c.message.answer_photo(order['screenshot_file_id'], caption=txt, reply_markup=kb.validate_keyboard(order['id']))
    else:
        await c.message.answer(txt)
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
    try:
        await c.message.edit_reply_markup(reply_markup=kb.offer_keyboard(sel))
    except Exception as e:
        if 'message is not modified' not in str(e):
            raise
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
    await c.message.answer(f'💳 Montant mensuel : {total}€\n\nPayPal :\n{settings.paypal_link}\n\nAprès paiement, envoie ici une capture d’écran.\nCommande #{order_id}', reply_markup=kb.payment_wait_keyboard())
    await c.answer()


@r.message(F.chat.type == ChatType.PRIVATE, F.text)
async def admin_text_inputs(message: Message):
    if not is_admin(message.from_user.id):
        return
    mode = admin_modes.get(message.from_user.id)
    if mode == 'ad_text':
        await db.set_setting('ad_text', message.text)
        admin_modes.pop(message.from_user.id, None)
        await message.answer('✅ Texte de publicité enregistré.', reply_markup=kb.ads_panel())

@r.message(F.photo | F.document)
async def screenshot(message: Message):
    if is_admin(message.from_user.id) and admin_modes.get(message.from_user.id) == 'ad_photo':
        file_id = None
        if message.photo:
            file_id = message.photo[-1].file_id
        elif message.document and message.document.mime_type and message.document.mime_type.startswith('image/'):
            file_id = message.document.file_id
        if not file_id:
            await message.answer('Image illisible. Envoie une photo ou un document image.')
            return
        await db.set_setting('ad_photo_file_id', file_id)
        admin_modes.pop(message.from_user.id, None)
        await message.answer('✅ Image de publicité enregistrée.', reply_markup=kb.ads_panel())
        return
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


@r.callback_query(F.data == 'order:cancel_current')
async def cb_cancel_current_order(c: CallbackQuery):
    await db.upsert_user(c.from_user)
    order = await db.cancel_current_order(c.from_user.id)
    if order:
        user_selection[c.from_user.id] = set(order['items'])
        await c.message.answer('❌ Commande annulée. Tu peux choisir une nouvelle offre :', reply_markup=kb.offer_keyboard(set(order['items'])))
    else:
        await c.message.answer('Aucune commande active à annuler. Voici les offres :', reply_markup=kb.offer_keyboard())
    await c.answer()

@r.callback_query(F.data.startswith('order:'))
async def cb_order(c: CallbackQuery):
    if not is_admin(c.from_user.id): return await c.answer()
    _, action, oid = c.data.split(':')
    order_id = int(oid)
    if action == 'approve':
        order = await db.decide_order(order_id, c.from_user.id, 'APPROVED')
        if not order:
            return await c.answer('Commande déjà traitée.', show_alert=True)
        old_sub = await db.active_subscription(order['user_id'])
        old_items = set(old_sub['items']) if old_sub else set()
        new_items = set(order['items'])
        removed_items = list(old_items - new_items)
        await db.activate_subscription(order['user_id'], list(order['items']), order_id, settings.subscription_days)
        if removed_items:
            await svc.kick_user_from_groups(bot, order['user_id'], removed_items)
        try:
            await svc.grant_access(bot, order['user_id'], list(order['items']), settings.invite_expire_minutes)
        except Exception as e:
            await notify_admins(f'❌ Paiement validé mais accès non envoyé pour commande #{order_id}: {e}')
        await c.message.edit_caption((c.message.caption or '') + '\n\n✅ Validée')
        await c.answer('Validé')
    elif action == 'reject':
        order = await db.decide_order(order_id, c.from_user.id, 'AWAITING_NEW_PROOF')
        if not order:
            return await c.answer('Commande déjà traitée ou pas encore vérifiable.', show_alert=True)
        await svc.safe_send(bot, order['user_id'], '❌ Paiement refusé. Envoie une nouvelle capture valide, ou annule pour changer d’offre.', reply_markup=kb.payment_wait_keyboard())
        await c.message.edit_caption((c.message.caption or '') + '\n\n❌ Refusée — attente nouvelle capture')
        await c.answer('Nouvelle capture demandée')
    elif action == 'resend':
        order = await db.decide_order(order_id, c.from_user.id, 'AWAITING_NEW_PROOF')
        if order:
            await svc.safe_send(bot, order['user_id'], '📸 Merci de renvoyer une capture plus lisible du paiement, ou annule pour changer d’offre.', reply_markup=kb.payment_wait_keyboard())
            await c.message.edit_caption((c.message.caption or '') + '\n\n📸 Nouvelle capture demandée')
            await c.answer('Demande envoyée')
        else:
            await c.answer('Commande déjà traitée ou pas encore vérifiable.', show_alert=True)

async def kick_expired_demos():
    gs = await db.group_by_type('VIP_PREVIEW')
    if not gs:
        return
    fallback_chat_id = gs[0]['chat_id']
    for demo in await db.demos_to_kick(settings.demo_duration_minutes):
        user_id = demo['user_id']
        chat_id = demo['chat_id'] or fallback_chat_id
        try:
            await db.log('INFO', f'Tentative kick demo user={user_id} group={chat_id}')
            await bot.ban_chat_member(chat_id, user_id)
            await bot.unban_chat_member(chat_id, user_id, only_if_banned=True)
            if demo['invite_link']:
                try:
                    await bot.revoke_chat_invite_link(chat_id, demo['invite_link'])
                    await db.mark_demo_invite_revoked(user_id)
                except Exception as revoke_error:
                    await db.log('WARNING', f'Revocation lien demo impossible user={user_id}: {revoke_error}')
            await db.mark_demo_kicked(user_id)
            await db.log('INFO', f'Kick demo réussi user={user_id} group={chat_id}')
            await svc.safe_send(bot, user_id, '⏱️ Ta démo est terminée. Tu peux maintenant choisir ton accès mensuel.', reply_markup=kb.offer_keyboard())
        except Exception as e:
            # IMPORTANT : on ne met PAS kicked_at si Telegram refuse le kick.
            err = str(e)
            failed_demo = await db.mark_demo_kick_failed(user_id, err)
            attempts = failed_demo['kick_attempts'] if failed_demo and 'kick_attempts' in failed_demo else 1
            await db.log('ERROR', f'Kick demo impossible user={user_id} group={chat_id} attempt={attempts}: {err}')

            # Alerte admin immédiate, puis rappel toutes les 5 tentatives pour éviter le spam.
            if attempts == 1 or attempts % 5 == 0:
                await db.mark_demo_kick_alerted(user_id)
                await notify_admins(
                    '🚨 Échec expulsion démo\n\n'
                    f'Utilisateur ID : {user_id}\n'
                    f'Groupe Preview ID : {chat_id}\n'
                    f'Tentative : {attempts}\n\n'
                    f'Erreur Telegram : {err}\n\n'
                    'Le bot va réessayer automatiquement. Vérifie dans le groupe Preview que le bot a bien le droit “Bannir des membres”.'
                )

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
