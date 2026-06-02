import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Settings:
    bot_token: str
    database_url: str
    admin_ids: set[int]
    paypal_link: str
    paypal_email: str
    demo_duration_minutes: int
    ad_default_interval_minutes: int


def _ids(value: str) -> set[int]:
    return {int(x.strip()) for x in value.split(',') if x.strip()}


def load_settings() -> Settings:
    return Settings(
        bot_token=os.environ['BOT_TOKEN'],
        database_url=os.environ['DATABASE_URL'],
        admin_ids=_ids(os.getenv('ADMIN_IDS', '')),
        paypal_link=os.getenv('PAYPAL_LINK', ''),
        paypal_email=os.getenv('PAYPAL_EMAIL', ''),
        demo_duration_minutes=int(os.getenv('DEMO_DURATION_MINUTES', '4')),
        ad_default_interval_minutes=int(os.getenv('AD_DEFAULT_INTERVAL_MINUTES', '60')),
    )
