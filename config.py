import os
from dataclasses import dataclass


def _required(name: str) -> str:
    value = os.getenv(name, '').strip()
    if not value:
        raise RuntimeError(f"Variable d'environnement manquante: {name}")
    return value


def _admin_ids(raw: str) -> set[int]:
    ids: set[int] = set()
    for part in raw.replace(';', ',').split(','):
        part = part.strip()
        if part:
            ids.add(int(part))
    return ids

@dataclass(frozen=True)
class Settings:
    bot_token: str
    database_url: str
    admin_ids: set[int]
    paypal_link: str
    demo_duration_minutes: int = 4
    subscription_days: int = 30
    invite_expire_minutes: int = 60
    timezone: str = 'Europe/Paris'


def load_settings() -> Settings:
    return Settings(
        bot_token=_required('BOT_TOKEN'),
        database_url=_required('DATABASE_URL'),
        admin_ids=_admin_ids(_required('ADMIN_IDS')),
        paypal_link=os.getenv('PAYPAL_LINK', '').strip(),
        demo_duration_minutes=int(os.getenv('DEMO_DURATION_MINUTES', '4')),
        subscription_days=int(os.getenv('SUBSCRIPTION_DAYS', '30')),
        invite_expire_minutes=int(os.getenv('INVITE_EXPIRE_MINUTES', '60')),
        timezone=os.getenv('TIMEZONE', 'Europe/Paris'),
    )
