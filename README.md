# Bot Telegram VIP mensuel pour Railway

## Fonctions

- Panel admin automatique via `ADMIN_IDS`.
- Détection automatique des groupes où le bot est ajouté.
- Association des groupes : publicité, preview, VIP non téléchargeable, VIP téléchargeable, rediffusion.
- Bouton `Accès VIP` dans les groupes publicité.
- Démo unique : lien Telegram 1 utilisation, puis kick après 4 minutes.
- Offres mensuelles :
  - VIP non téléchargeable : 8€/mois
  - VIP téléchargeable : 10€/mois
  - Rediffusion : 10€/mois
  - VIP non téléchargeable + rediffusion : 18€/mois
  - VIP téléchargeable + rediffusion : 18€/mois
- Paiement PayPal via lien configurable dans Railway.
- Capture envoyée aux admins.
- Validation/refus admin.
- Abonnement de 30 jours après validation.
- Relances automatiques J-10, J-5, J-3.
- À expiration : kick des groupes concernés.
- Infos système : base de données, groupes, permissions, PayPal, commandes.

## Installation Railway

1. Créer un projet Railway.
2. Ajouter PostgreSQL.
3. Déployer ce dossier.
4. Ajouter les variables d'environnement :

```env
BOT_TOKEN=...
DATABASE_URL=...
ADMIN_IDS=123456789,987654321
PAYPAL_LINK=https://paypal.me/...
DEMO_DURATION_MINUTES=4
SUBSCRIPTION_DAYS=30
INVITE_EXPIRE_MINUTES=60
TIMEZONE=Europe/Paris
```

## Droits nécessaires du bot dans les groupes

Le bot doit être administrateur avec :

- Inviter des utilisateurs
- Bannir/restreindre des utilisateurs
- Créer des liens d'invitation

## Commandes

- `/start` : panel admin si admin, sinon message utilisateur.
- `/admin` : panel admin.
- `/groupes` : liste des groupes détectés et association.

## Configuration après déploiement

1. Parler au bot en privé avec `/start`.
2. Ajouter le bot dans tous les groupes.
3. Donner les droits admin au bot.
4. Faire `/groupes`.
5. Associer chaque groupe.
6. Cliquer sur `ℹ️ Infos système`.
7. Vérifier que tout est vert.
8. Cliquer sur `📢 Envoyer publicité`.

## Cas prévus

- Utilisateur bloque le bot : marqué en base, le bot continue.
- Utilisateur quitte un groupe : à expiration il est quand même kick/neutralisé si possible.
- Groupe supprimé ou bot retiré : groupe marqué inactif.
- Admin retire les droits : Infos système affiche l'erreur.
- Lien expiré : l'utilisateur doit repasser par le bot.
- Redémarrage Railway : la base conserve groupes, commandes, démos, abonnements.
- Base indisponible : le bot ne démarre pas et Railway redémarre.
- Capture illisible : demande de nouvelle capture.
- Double paiement : une seule commande active par utilisateur.
- Double validation : verrou SQL `FOR UPDATE`, une commande déjà traitée ne peut plus être revalidée.

## Note importante

Utilise uniquement du contenu légal, autorisé et conforme aux règles Telegram et PayPal.
