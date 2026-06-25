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

## Mise à jour marketing / promotions

Cette version ajoute, sans supprimer les anciennes données :

- Texte explicatif au-dessus des offres mensuelles.
- Deuxième relance démo après 5 jours si la personne n'a jamais payé.
- Offre découverte 6 jours envoyée 2 jours après la relance démo, valable 24h et une seule fois.
- Bouton admin `🎯 Campagnes promo` avec ON/OFF :
  - `-50% premiers entrants` : 4€/mois, 5€/mois, 5€/mois pour les nouveaux prospects éligibles.
  - `2 mois achetés = 1 mois offert` : le client paie bien 2 mois et reçoit 3 mois d'accès.
  - `Relance anciens -30%` : anciens abonnés expirés depuis au moins 10 jours, valable 24h.
- Aucun client ayant déjà payé au moins une fois ne reçoit les promos nouveaux prospects.

Les migrations sont additives : nouvelles colonnes dans `users` et `orders`, aucun DROP.

## Module réparation / reprise après incident

Nouveau menu admin : `🛠 Réparation`.

Fonctions ajoutées :

- `🔍 Diagnostic` : vérifie les abonnés actifs, les groupes configurés et les accès manquants.
- `🚑 Réparer les accès` : renvoie des liens frais, valables 24h et utilisables une seule fois, uniquement aux abonnés actifs qui ne sont pas dans les groupes correspondant à leur offre.
- `🎁 Compensation +2 jours` : ajoute 2 jours uniquement aux abonnements actifs non expirés et envoie un message avec les jours restants et la nouvelle date d'expiration.
- `📊 Rapport accès` : affiche les liens envoyés, rejoints, en attente et expirés sans utilisation.

Le bot surveille aussi les liens VIP envoyés : si un lien expire sans que l'utilisateur rejoigne le groupe, les admins reçoivent une alerte.

Variables optionnelles :

```env
DEMO_INVITE_EXPIRE_MINUTES=5
VIP_INVITE_EXPIRE_MINUTES=1440
```

`VIP_INVITE_EXPIRE_MINUTES=1440` correspond à 24h.
