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
        [InlineKeyboardButton(text='📢 Envoyer publicité', callback_data='admin:send_ad')],
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
        [InlineKeyboardButton(text='✅ Valider', callback_data=f'order:approve:{order_id}'), InlineKeyboardButton(text='❌ Refuser', callback_data=f'order:reject:{order_id}')],
        [InlineKeyboardButton(text='📸 Nouvelle capture', callback_data=f'order:resend:{order_id}')]
    ])
