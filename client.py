# client.py

from dataclasses import dataclass

@dataclass
class ClientData:
    """
    Класс для хранения информации о клиенте VPN.
    """
    max_devices: int            # Максимальное количество устройств
    traffic_total: int          # Общий лимит трафика (в ГБ)
    traffic_remaining: int      # Оставшийся трафик (в ГБ)
    traffic_used: int           # Использованный трафик (в ГБ)
    traffic_up: int             # Загруженный трафик (в ГБ)
    traffic_down: int           # Скачанный трафик (в ГБ)
    expiry_time: int            # Время истечения подписки (Unix timestamp в миллисекундах)
