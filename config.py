# config.py

import os
from dataclasses import dataclass, field
from typing import List
from dotenv import load_dotenv

# Загрузка переменных окружения из .env
load_dotenv()

@dataclass
class XUIConfig:
    """
    Класс для хранения конфигурационных параметров панели 3x-ui.
    """
    HOST: str = os.getenv("XUI_HOST", "https://your-xui-host.com")
    USERNAME: str = os.getenv("XUI_USERNAME", "admin")
    PASSWORD: str = os.getenv("XUI_PASSWORD", "password")
    TOKEN: str = os.getenv("XUI_TOKEN", "your_api_token")
    SUBSCRIPTION_PREFIX: str = os.getenv("XUI_SUBSCRIPTION_PREFIX", "sub_")
    INBOUND_ID: int = int(os.getenv("INBOUND_ID", "1"))

@dataclass
class Config:
    """
    Основной класс конфигурации, объединяющий все конфигурационные параметры.
    """
    xui: XUIConfig = XUIConfig()
    USERS_FILE: str = os.getenv("USERS_FILE", "data/users.json")
    PROMOCODES_FILE: str = os.getenv("PROMOCODES_FILE", "data/promocodes.json")
    REQUESTS_FILE: str = os.getenv("REQUESTS_FILE", "data/requests.json")
    TELEGRAM_TOKEN: str = os.getenv("BOT_TOKEN", "your_telegram_bot_token")
    BOT_ADMINS: List[int] = field(default_factory=lambda: [
        int(admin_id) for admin_id in os.getenv("BOT_ADMINS", "").split(",") if admin_id.strip().isdigit()
    ])
