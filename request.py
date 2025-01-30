# request.py

import logging
from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional
import uuid

from json_utils import JSONDataStore

logger = logging.getLogger(__name__)

@dataclass
class Request:
    """
    Класс для представления заявки пользователя на оформление подписки.
    """
    request_id: str          # Уникальный идентификатор заявки
    user_id: int             # ID пользователя Telegram
    details: Dict[str, Any]  # Детали заявки (например, количество устройств, предпочтительная длительность и т.д.)
    status: str              # Статус заявки (например, "pending", "completed", "rejected")
    timestamp: int           # Временной штамп создания заявки (Unix timestamp в миллисекундах)

    def to_dict(self) -> Dict[str, Any]:
        """
        Конвертирует объект Request в словарь для хранения в JSON.
        """
        return asdict(self)

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'Request':
        """
        Создаёт объект Request из словаря.
        """
        return Request(
            request_id=data["request_id"],
            user_id=data["user_id"],
            details=data["details"],
            status=data.get("status", "pending"),
            timestamp=data["timestamp"]
        )

class RequestService:
    """
    Сервис для управления заявками пользователей на оформление подписки.
    """

    def __init__(self, requests_store: JSONDataStore) -> None:
        """
        Инициализирует сервис заявок с указанным хранилищем данных.

        :param requests_store: Объект JSONDataStore для работы с requests.json.
        """
        self.requests_store = requests_store
        logger.info("RequestService initialized.")

    async def create_request(self, request: Request) -> bool:
        """
        Создаёт новую заявку и сохраняет её в хранилище.

        :param request: Объект Request для сохранения.
        :return: True если успешно, иначе False.
        """
        try:
            requests = await self.requests_store.read_data()
            requests.append(request.to_dict())
            await self.requests_store.write_data(requests)
            logger.info(f"Заявка {request.request_id} от пользователя {request.user_id} успешно создана.")
            return True
        except Exception as e:
            logger.error(f"Ошибка при создании заявки {request.request_id}: {e}")
            return False

    async def get_request(self, request_id: str) -> Optional[Request]:
        """
        Получает заявку по её уникальному идентификатору.

        :param request_id: Уникальный идентификатор заявки.
        :return: Объект Request или None, если заявка не найдена.
        """
        try:
            requests = await self.requests_store.read_data()
            for req_data in requests:
                if req_data["request_id"] == request_id:
                    logger.debug(f"Заявка {request_id} найдена.")
                    return Request.from_dict(req_data)
            logger.debug(f"Заявка {request_id} не найдена.")
            return None
        except Exception as e:
            logger.error(f"Ошибка при получении заявки {request_id}: {e}")
            return None

    async def update_request_status(self, request_id: str, new_status: str) -> bool:
        """
        Обновляет статус существующей заявки.

        :param request_id: Уникальный идентификатор заявки.
        :param new_status: Новый статус заявки (например, "completed", "rejected").
        :return: True если успешно обновлено, иначе False.
        """
        try:
            requests = await self.requests_store.read_data()
            for req_data in requests:
                if req_data["request_id"] == request_id:
                    req_data["status"] = new_status
                    await self.requests_store.write_data(requests)
                    logger.info(f"Статус заявки {request_id} обновлён на {new_status}.")
                    return True
            logger.warning(f"Заявка {request_id} не найдена для обновления статуса.")
            return False
        except Exception as e:
            logger.error(f"Ошибка при обновлении статуса заявки {request_id}: {e}")
            return False

    async def list_requests(self, status_filter: Optional[str] = None) -> List[Request]:
        """
        Возвращает список всех заявок, с возможностью фильтрации по статусу.

        :param status_filter: Статус для фильтрации заявок (например, "pending").
        :return: Список объектов Request.
        """
        try:
            requests = await self.requests_store.read_data()
            if status_filter:
                filtered_requests = [Request.from_dict(req) for req in requests if req.get("status") == status_filter]
                logger.debug(f"Получено {len(filtered_requests)} заявок с статусом '{status_filter}'.")
                return filtered_requests
            all_requests = [Request.from_dict(req) for req in requests]
            logger.debug(f"Получено {len(all_requests)} всех заявок.")
            return all_requests
        except Exception as e:
            logger.error(f"Ошибка при получении списка заявок: {e}")
            return []

    async def generate_new_request_id(self) -> str:
        """
        Генерирует уникальный идентификатор для новой заявки.

        :return: Уникальный идентификатор заявки.
        """
        return str(uuid.uuid4())
