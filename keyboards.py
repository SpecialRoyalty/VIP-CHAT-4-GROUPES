from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

GROUP_TYPES = [
    ('PUBLICITE', '📢 Publicité'),
    ('VIP_PREVIEW', '👀 VIP Preview / Démo'),
    ('VIP_NON_TELECHARGEABLE', '🔒 VIP non téléchargeable'),
    ('VIP_TELECHARGEABLE', '⬇️ VIP téléchargeable'),
    ('REDIFFUSION', '🔁 Rediffusion'),
]

def admin_panel():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='📢 Publicités', callback_data='admin:ads'), InlineKeyboardButton(text='👥 Groupes', callback_data='admin:groups')],
        [InlineKeyboardButton(text='💳 Paiement', callback_data='admin:payment'), InlineKeyboardButton(text='📦 Commandes', callback_data='admin:orders')],
        [InlineKeyboardButton(text='📊 Statistiques', callback_data='admin:stats'), InlineKeyboardButton(text='ℹ️ Infos système', callback_data='admin:info')],
        [InlineKeyboardButton(text='🔧 Réparer / Revérifier', callback_data='admin:repair')],
    ])

def group_type_keyboard(chat_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, callback_data=f'group:set:{chat_id}:{typ}')]
        for typ, label in GROUP_TYPES
    ])

def ad_button():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🔥 Accès VIP', url='https://t.me/YOUR_BOT_USERNAME?start=vip')]
    ])

def offer_keyboard(selected_vip: str | None = None, rediffusion: bool = False):
    def box(v): return '✅' if v else '☐'
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f'{box(selected_vip=="VIP_NON_TELECHARGEABLE")} VIP non téléchargeable — 25€', callback_data='offer:vip_non')],
        [InlineKeyboardButton(text=f'{box(selected_vip=="VIP_TELECHARGEABLE")} VIP téléchargeable — 30€', callback_data='offer:vip_tel')],
        [InlineKeyboardButton(text=f'{box(rediffusion)} Groupe rediffusion — 10€', callback_data='offer:rediff')],
        [InlineKeyboardButton(text='➡️ Suivant', callback_data='offer:next')],
    ])

def admin_order_keyboard(order_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='✅ Valider', callback_data=f'order:approve:{order_id}'), InlineKeyboardButton(text='❌ Refuser', callback_data=f'order:reject:{order_id}')],
        [InlineKeyboardButton(text='✉️ Demander nouvelle capture', callback_data=f'order:rescreen:{order_id}')],
    ])


def groups_list_keyboard(rows):
    keyboard = []
    for r in rows:
        title = str(r["title"] or r["chat_id"])[:28]
        typ = r["type"] or "UNASSIGNED"
        keyboard.append([InlineKeyboardButton(
            text=f'⚙️ {title} → {typ}',
            callback_data=f'group:choose:{r["chat_id"]}'
        )])
    keyboard.append([InlineKeyboardButton(text='🔧 Revérifier', callback_data='admin:repair')])
    keyboard.append([InlineKeyboardButton(text='⬅️ Retour panel', callback_data='admin:panel')])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
