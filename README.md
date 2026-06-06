# Bot Telegram VIP mensuel

Version avec migrations compatibles ancienne base : aucune table n'est supprimée. Au démarrage, le bot ajoute les colonnes nécessaires à `orders`, `subscriptions`, `demos` et crée `admin_notifications` / `admin_actions`.

## Nouveautés

- Paiement en 3 étapes : capture unique, email PayPal, référence PayPal.
- Tous les admins reçoivent le dossier complet.
- Dès qu'un admin valide/refuse, les messages de notification sont supprimés ou neutralisés chez les autres admins.
- Refus avec motif obligatoire via boutons.
- Une seule preuve par commande.
- Bouton `📒 Comptabilité` : montants encaissés, commandes, abonnements, cohérence globale.
- Bouton `📦 Suivi commandes (X)` : commandes récentes, à traiter, validées, refusées.
- Bouton `👤 Abonnements` : actifs, expirent bientôt, expirés, renouvellements, date d'expiration.
- Sécurité démo : kick après 4 minutes, pas de `kicked_at` si Telegram refuse, alertes admin en cas d'échec.

## Variables Railway

```env
BOT_TOKEN=
DATABASE_URL=
ADMIN_IDS=123456789,987654321
PAYPAL_LINK=https://paypal.me/...
DEMO_DURATION_MINUTES=4
SUBSCRIPTION_DAYS=30
INVITE_EXPIRE_MINUTES=60
TIMEZONE=Europe/Paris
```

## Déploiement Railway

1. Uploader le projet.
2. Renseigner les variables d'environnement.
3. Déployer.
4. Lancer `/admin` dans Telegram.
5. Aller dans `👥 Groupes` et associer les groupes.
6. Vérifier `ℹ️ Infos système` puis `📒 Comptabilité`.

## Important

Le bot doit être admin dans les groupes VIP avec les droits :
- créer/inviter via des liens,
- bannir/restreindre des membres.
