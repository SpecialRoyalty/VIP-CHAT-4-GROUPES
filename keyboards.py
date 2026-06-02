from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

GROUP_TYPES = {
    'PUBLICITE': '📢 Publicité',
    'VIP_PREVIEW': '👀 VIP Preview',
    'VIP_NON_TELECHARGEABLE': '🔒 VIP non téléchargeable',
    'VIP_TELECHARGEABLE': '⬇️ VIP téléchargeable',
    'REDIFFUSION': '🔁 Rediffusion',
}

PRICES = {
    'VIP_NON_TELECHARGEABLE': 8,
    'VIP_TELECHARGEABLE': 10,
    'REDIFFUSION': 10,
}


def admin_panel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='👥 Groupes', callback_data='admin:groups'), InlineKeyboardButton(text='ℹ️ Infos système', callback_data='admin:info')],
        [InlineKeyboardButton(text='💳 Paiement PayPal', callback_data='admin:paypal'), InlineKeyboardButton(text='📦 Commandes', callback_data='admin:orders')],
        [InlineKeyboardButton(text='📢 Publicités', callback_data='admin:ads')],
    ])


def group_list(groups) -> InlineKeyboardMarkup:
    rows = []
    for g in groups:
        rows.append([InlineKeyboardButton(text=f"{g['title']} — {g['type'] or 'UNASSIGNED'}", callback_data=f"group:{g['chat_id']}")])
    rows.append([InlineKeyboardButton(text='🔙 Retour', callback_data='admin:panel')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def assign_group(chat_id: int) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=f'assign:{chat_id}:{typ}')] for typ, label in GROUP_TYPES.items()]
    rows.append([InlineKeyboardButton(text='🔙 Retour groupes', callback_data='admin:groups')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def access_vip() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='🔥 Accès VIP', url='https://t.me/PLACEHOLDER_BOT?start=vip')]])


def offer_keyboard(selection: set[str] | None = None) -> InlineKeyboardMarkup:
    selection = selection or set()
    def box(k): return '✅' if k in selection else '☐'
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{box('VIP_NON_TELECHARGEABLE')} VIP non téléchargeable — 8€/mois", callback_data='offer:toggle:VIP_NON_TELECHARGEABLE')],
        [InlineKeyboardButton(text=f"{box('VIP_TELECHARGEABLE')} VIP téléchargeable — 10€/mois", callback_data='offer:toggle:VIP_TELECHARGEABLE')],
        [InlineKeyboardButton(text=f"{box('REDIFFUSION')} Rediffusion — 10€/mois", callback_data='offer:toggle:REDIFFUSION')],
        [InlineKeyboardButton(text='➡️ Suivant', callback_data='offer:next')],
    ])


def validate_keyboard(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='✅ Valider', callback_data=f'order:approve:{order_id}'), InlineKeyboardButton(text='❌ Refuser / nouvelle capture', callback_data=f'order:reject:{order_id}')],
        [InlineKeyboardButton(text='📸 Demander une nouvelle capture', callback_data=f'order:resend:{order_id}')]
    ])


def payment_wait_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='❌ Annuler et changer d’offre', callback_data='order:cancel_current')]
    ])



def ads_panel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='✏️ Modifier texte', callback_data='ad:set_text'), InlineKeyboardButton(text='🖼 Modifier image', callback_data='ad:set_photo')],
        [InlineKeyboardButton(text='👁 Prévisualiser', callback_data='ad:preview')],
        [InlineKeyboardButton(text='📤 Choisir les groupes et envoyer', callback_data='ad:choose_groups')],
        [InlineKeyboardButton(text='🗑 Retirer image', callback_data='ad:clear_photo')],
        [InlineKeyboardButton(text='🔙 Retour', callback_data='admin:panel')],
    ])


def ad_groups(groups, selected: set[int] | None = None) -> InlineKeyboardMarkup:
    selected = selected or set()
    rows = []
    for g in groups:
        mark = '✅' if int(g['chat_id']) in selected else '☐'
        rows.append([InlineKeyboardButton(text=f"{mark} {g['title']}", callback_data=f"ad:toggle_group:{g['chat_id']}")])
    rows.append([InlineKeyboardButton(text='📤 Envoyer aux groupes cochés', callback_data='ad:send_selected')])
    rows.append([InlineKeyboardButton(text='🔙 Retour publicités', callback_data='admin:ads')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def orders_panel(orders) -> InlineKeyboardMarkup:
    rows = []
    for o in orders:
        rows.append([InlineKeyboardButton(text=f"Commande #{o['id']} — {o['status']} — {o['amount']}€", callback_data=f"order:view:{o['id']}")])
    rows.append([InlineKeyboardButton(text='🔙 Retour', callback_data='admin:panel')])
    return InlineKeyboardMarkup(inline_keyboard=rows)
