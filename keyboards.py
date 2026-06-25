from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import services as svc

GROUP_TYPES = {
    'PUBLICITE': '📢 Publicité',
    'VIP_PREVIEW': '👀 VIP Preview',
    'VIP_NON_TELECHARGEABLE': '🔒 VIP non téléchargeable',
    'VIP_TELECHARGEABLE': '⬇️ VIP téléchargeable',
    'REDIFFUSION': '🔁 Rediffusion',
}



def admin_panel(pending_count: int = 0) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='👥 Groupes', callback_data='admin:groups'), InlineKeyboardButton(text='ℹ️ Infos système', callback_data='admin:info')],
        [InlineKeyboardButton(text='💳 Paiement PayPal', callback_data='admin:paypal'), InlineKeyboardButton(text=f'📦 Suivi commandes ({pending_count})', callback_data='admin:orders')],
        [InlineKeyboardButton(text='📒 Comptabilité', callback_data='admin:accounting'), InlineKeyboardButton(text='👤 Abonnements', callback_data='admin:subscriptions')],
        [InlineKeyboardButton(text='💰 Tarification', callback_data='admin:pricing'), InlineKeyboardButton(text='🎯 Campagnes promo', callback_data='admin:promos')],
        [InlineKeyboardButton(text='📢 Publicités', callback_data='admin:ads'), InlineKeyboardButton(text='🛠 Réparation', callback_data='admin:repair')],
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


def offer_text(prefix: str = '') -> str:
    p = svc.PRICES
        return (
            f"{prefix}Choisis ton accès :\n\n"
        
            f"🔒 VIP non téléchargeable — {svc.eur(p['VIP_NON_TELECHARGEABLE'])}/mois\n"
            "• Accès au VIP principal\n"
            "• +45 000 médias exclusifs\n"
            "• Consultation directement dans Telegram\n"
            "• Contenu ajouté régulièrement\n"
            "• Téléchargement non inclus\n\n"
        
            f"⬇️ VIP téléchargeable — {svc.eur(p['VIP_TELECHARGEABLE'])}/mois\n"
            "• Accès au VIP principal\n"
            "• +55 000 médias disponibles\n"
            "• De nouveaux médias sont ajoutés progressivement par nos bots\n"
            "• Téléchargement autorisé\n"
            "• Accès complet aux médias\n\n"
        
            f"🔁 Rediffusion — {svc.eur(p['REDIFFUSION'])}/mois\n"
            "• Médias rediffusés chaque jour depuis les groupes sources\n"
            "• Contenu provenant des groupes de JAVANA, L'Olivette et de nombreux autres groupes Telegram\n"
            "• +60 000 médias différents\n"
            "• Mise à jour tous les soirs\n"
            "• Téléchargement partiel autorisé\n\n"
        
            "ℹ️ Les 3 VIP sont différents mais tous très intéressants et complémentaires.\n\n"
        
            "📩 Pour tout souci ou pour payer via Revolut ou crypto, contactez : @op75x15"
        )

def offer_keyboard(selection: set[str] | None = None, promo: str | None = None) -> InlineKeyboardMarkup:
    selection = selection or set()
    def box(k): return '✅' if k in selection else '☐'
    def price(k):
        return svc.eur(svc.promo_price(k, promo))
    rows = [
        [InlineKeyboardButton(text=f"{box('VIP_NON_TELECHARGEABLE')} VIP non téléchargeable — {price('VIP_NON_TELECHARGEABLE')}/mois", callback_data='offer:toggle:VIP_NON_TELECHARGEABLE')],
        [InlineKeyboardButton(text=f"{box('VIP_TELECHARGEABLE')} VIP téléchargeable — {price('VIP_TELECHARGEABLE')}/mois", callback_data='offer:toggle:VIP_TELECHARGEABLE')],
        [InlineKeyboardButton(text=f"{box('REDIFFUSION')} Rediffusion — {price('REDIFFUSION')}/mois", callback_data='offer:toggle:REDIFFUSION')],
    ]
    rows.append([InlineKeyboardButton(text='➡️ Suivant', callback_data='offer:next')])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def discovery_offer_keyboard(selection: set[str] | None = None) -> InlineKeyboardMarkup:
    selection = selection or set()
    def box(k): return '✅' if k in selection else '☐'
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{box('VIP_NON_TELECHARGEABLE')} VIP non téléchargeable — {svc.eur(svc.promo_price('VIP_NON_TELECHARGEABLE', 'DISCOVERY_6D'))}/6 jours", callback_data='offer6:toggle:VIP_NON_TELECHARGEABLE')],
        [InlineKeyboardButton(text=f"{box('REDIFFUSION')} Rediffusion — {svc.eur(svc.promo_price('REDIFFUSION', 'DISCOVERY_6D'))}/6 jours", callback_data='offer6:toggle:REDIFFUSION')],
        [InlineKeyboardButton(text='➡️ Suivant', callback_data='offer6:next')],
    ])

def second_demo_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Accéder à la démo', callback_data='demo:second')]])


def promo_panel(enabled_50: bool, enabled_2plus1: bool, enabled_reactivation: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{'🟢 ON' if enabled_50 else '⚪ OFF'} -{svc.eur(svc.DISCOUNTS['FIRST_50']).replace('€','%')} premiers entrants", callback_data='promo:toggle:FIRST_50')],
        [InlineKeyboardButton(text=f"{'🟢 ON' if enabled_2plus1 else '⚪ OFF'} 2 mois achetés = 1 mois offert", callback_data='promo:toggle:FIRST_2PLUS1')],
        [InlineKeyboardButton(text=f"{'🟢 ON' if enabled_reactivation else '⚪ OFF'} Relance anciens -{svc.eur(svc.DISCOUNTS['REACTIVATION_30']).replace('€','%')}", callback_data='promo:toggle:REACTIVATION_30')],
        [InlineKeyboardButton(text='🔍 Scanner les anciens utilisateurs', callback_data='promo:scan_old_users')],
        [InlineKeyboardButton(text='📣 Envoyer relance anciens maintenant', callback_data='promo:send_reactivation')],
        [InlineKeyboardButton(text='🔙 Retour', callback_data='admin:panel')],
    ])


def pricing_panel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"VIP non téléchargeable : {svc.eur(svc.PRICES['VIP_NON_TELECHARGEABLE'])}", callback_data='pricing:edit:price_VIP_NON_TELECHARGEABLE')],
        [InlineKeyboardButton(text=f"VIP téléchargeable : {svc.eur(svc.PRICES['VIP_TELECHARGEABLE'])}", callback_data='pricing:edit:price_VIP_TELECHARGEABLE')],
        [InlineKeyboardButton(text=f"Rediffusion : {svc.eur(svc.PRICES['REDIFFUSION'])}", callback_data='pricing:edit:price_REDIFFUSION')],
        [InlineKeyboardButton(text=f"Promo premiers entrants : -{svc.eur(svc.DISCOUNTS['FIRST_50']).replace('€','%')}", callback_data='pricing:edit:discount_FIRST_50')],
        [InlineKeyboardButton(text=f"Offre découverte : -{svc.eur(svc.DISCOUNTS['DISCOVERY_6D']).replace('€','%')}", callback_data='pricing:edit:discount_DISCOVERY_6D')],
        [InlineKeyboardButton(text=f"Relance anciens : -{svc.eur(svc.DISCOUNTS['REACTIVATION_30']).replace('€','%')}", callback_data='pricing:edit:discount_REACTIVATION_30')],
        [InlineKeyboardButton(text='🔙 Retour', callback_data='admin:panel')],
    ])


def validate_keyboard(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='✅ Valider', callback_data=f'order:approve:{order_id}'), InlineKeyboardButton(text='❌ Refuser', callback_data=f'order:reject_menu:{order_id}')],
    ])


def refusal_reasons_keyboard(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='Référence introuvable', callback_data=f'order:reject_reason:{order_id}:REFERENCE_INTROUVABLE')],
        [InlineKeyboardButton(text='Mauvais montant', callback_data=f'order:reject_reason:{order_id}:MAUVAIS_MONTANT')],
        [InlineKeyboardButton(text='Capture illisible', callback_data=f'order:reject_reason:{order_id}:CAPTURE_ILLISIBLE')],
        [InlineKeyboardButton(text='Paiement non reçu', callback_data=f'order:reject_reason:{order_id}:PAIEMENT_NON_RECU')],
        [InlineKeyboardButton(text='Autre motif', callback_data=f'order:reject_reason:{order_id}:AUTRE')],
        [InlineKeyboardButton(text='🔙 Retour commande', callback_data=f'order:view:{order_id}')],
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
    rows.append([InlineKeyboardButton(text='🕐 À traiter', callback_data='orders:pending')])
    rows.append([InlineKeyboardButton(text='✅ Validées', callback_data='orders:approved'), InlineKeyboardButton(text='❌ Refusées', callback_data='orders:rejected')])
    rows.append([InlineKeyboardButton(text='🔙 Retour', callback_data='admin:panel')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def accounting_panel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🔍 Vérifier cohérence globale', callback_data='accounting:check')],
        [InlineKeyboardButton(text='🔍 Vérifier les accès', callback_data='accounting:check_access')],
        [InlineKeyboardButton(text='🔙 Retour', callback_data='admin:panel')],
    ])


def access_anomalies_panel(rows) -> InlineKeyboardMarkup:
    buttons = []
    for r in rows[:10]:
        label = r.get('username') or str(r['user_id'])
        buttons.append([InlineKeyboardButton(text=f"Expulser #{r['id']} — {label}", callback_data=f"accounting:expel_sub:{r['id']}")])
    buttons.append([InlineKeyboardButton(text='🔙 Comptabilité', callback_data='admin:accounting')])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def subscriptions_panel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='Actifs', callback_data='subs:active'), InlineKeyboardButton(text='Expirent bientôt', callback_data='subs:expiring')],
        [InlineKeyboardButton(text='Expirés', callback_data='subs:expired')],
        [InlineKeyboardButton(text='🔙 Retour', callback_data='admin:panel')],
    ])


def repair_panel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🔍 Diagnostic', callback_data='repair:diagnostic')],
        [InlineKeyboardButton(text='🚑 Réparer les accès', callback_data='repair:run')],
        [InlineKeyboardButton(text='🎁 Compensation +2 jours', callback_data='repair:compensate2')],
        [InlineKeyboardButton(text='📊 Rapport accès', callback_data='repair:report')],
        [InlineKeyboardButton(text='🔙 Retour', callback_data='admin:panel')],
    ])

def repair_user_access() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🔗 Recevoir mon accès VIP', callback_data='user:get_access')]
    ])
