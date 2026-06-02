# Bot Telegram VIP Railway

Bot Telegram Python + aiogram 3 + PostgreSQL pour gérer :

- groupes publicité
- VIP preview / démo
- VIP non téléchargeable
- VIP téléchargeable
- groupe rediffusion
- liens uniques
- kick automatique après démo
- panier avec cases
- paiement PayPal manuel par capture
- validation/refus admin
- infos système
- redémarrage Railway sans perte grâce à PostgreSQL

## 1. Variables Railway

Créer ces variables dans Railway :

```env
BOT_TOKEN=token_botfather
DATABASE_URL=${{Postgres.DATABASE_URL}}
ADMIN_IDS=123456789,987654321
PAYPAL_LINK=https://paypal.me/votrecompte
PAYPAL_EMAIL=votre@email.com
DEMO_DURATION_MINUTES=4
AD_DEFAULT_INTERVAL_MINUTES=60
```

Railway permet d'ajouter PostgreSQL comme service séparé puis d'utiliser `DATABASE_URL`.

## 2. Déploiement Railway

1. Créer un projet Railway.
2. Ajouter PostgreSQL.
3. Ajouter ce repo/projet Python.
4. Ajouter les variables d'environnement.
5. Lancer le service avec le Procfile :

```txt
worker: python main.py
```

## 3. Droits Telegram obligatoires

Dans chaque groupe VIP, le bot doit être admin avec :

- créer des liens d'invitation
- bannir / exclure des membres
- inviter des utilisateurs
- envoyer des messages

## 4. Important

Dans `keyboards.py`, remplace `YOUR_BOT_USERNAME` par le username réel du bot si tu utilises la fonction pub statique. Les pubs programmées dans `main.py` récupèrent automatiquement le username.

## 5. Cas prévus

- utilisateur bloque le bot : marqué `blocked_bot=true`, log admin
- utilisateur quitte un groupe : log conservé, accès non supprimé
- groupe supprimé/inaccessible : revérification dans Infos système / Réparer
- droits admin retirés : Infos système indique l'erreur
- lien expiré : génération de liens à expiration courte, l'admin peut revalider/réenvoyer
- redémarrage Railway : commandes, groupes, démos et accès sont en base
- DB indisponible : le bot échoue explicitement, Infos système teste lecture/écriture
- capture illisible : bouton admin “Demander nouvelle capture”
- double paiement : commandes séparées, statut visible
- double validation : impossible car statut déjà APPROVED

## 6. Limite volontaire

Le panel de création détaillée des campagnes publicitaires est préparé côté base et scheduler, mais l'écran admin complet de création/modification des pubs est à compléter selon ton interface exacte.
