# promocode.py

import logging
from typing import Optional, List, Dict, Any

from json_utils import JSONDataStore
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

@dataclass
class Promocode:
    """
    Класс для представления промокода.
    """
    code: str
    duration_days: int
    active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """
        Конвертирует объект Promocode в словарь для хранения в JSON.
        """
        return asdict(self)

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'Promocode':
        """
        Создаёт объект Promocode из словаря.
        """
        return Promocode(
            code=data["code"],
            duration_days=data["duration_days"],
            active=data.get("active", True)
        )

class PromocodeService:
    """
    Сервис для управления промокодами.
    """

    def __init__(self, promocodes_store: JSONDataStore) -> None:
        """
        Инициализирует сервис промокодов с указанным хранилищем данных.

        :param promocodes_store: Объект JSONDataStore для работы с promocodes.json.
        """
        self.promocodes_store = promocodes_store
        logger.info("PromocodeService initialized.")

    async def get_promocode(self, code: str) -> Optional[Promocode]:
        """
        Получает промокод по его коду, если он активен.

        :param code: Код промокода.
        :return: Объект Promocode или None, если промокод не найден или не активен.
        """
        promocodes = await self.promocodes_store.read_data()
        for promo_data in promocodes:
            if promo_data["code"] == code and promo_data.get("active", True):
                logger.debug(f"Promocode {code} найден и активен.")
                return Promocode.from_dict(promo_data)
        logger.debug(f"Promocode {code} не найден или не активен.")
        return None

    async def use_promocode(self, code: str) -> bool:
        """
        Применяет промокод, деактивируя его после использования.

        :param code: Код промокода.
        :return: True если промокод успешно применён, иначе False.
        """
        promocodes = await self.promocodes_store.read_data()
        for promo_data in promocodes:
            if promo_data["code"] == code and promo_data.get("active", True):
                promo_data["active"] = False  # Деактивируем промокод после использования
                await self.promocodes_store.write_data(promocodes)
                logger.info(f"Promocode {code} успешно применён и деактивирован.")
                return True
        logger.warning(f"Не удалось применить промокод {code}. Он может быть неактивным или не существовать.")
        return False

    async def add_promocode(self, code: str, duration_days: int) -> bool:
        """
        Добавляет новый промокод в хранилище.

        :param code: Уникальный код промокода.
        :param duration_days: Длительность действия промокода в днях.
        :return: True если промокод успешно добавлен, иначе False.
        """
        promocodes = await self.promocodes_store.read_data()
        # Проверяем уникальность кода
        if any(promo["code"] == code for promo in promocodes):
            logger.warning(f"Попытка добавить существующий промокод {code}.")
            return False

        new_promocode = Promocode(code=code, duration_days=duration_days)
        promocodes.append(new_promocode.to_dict())
        await self.promocodes_store.write_data(promocodes)
        logger.info(f"Новый промокод {code} добавлен с длительностью {duration_days} дней.")
        return True

    async def remove_promocode(self, code: str) -> bool:
        """
        Удаляет промокод из хранилища.

        :param code: Код промокода для удаления.
        :return: True если промокод успешно удалён, иначе False.
        """
        promocodes = await self.promocodes_store.read_data()
        updated_promocodes = [promo for promo in promocodes if promo["code"] != code]
        if len(updated_promocodes) == len(promocodes):
            logger.warning(f"Попытка удалить несуществующий промокод {code}.")
            return False
        await self.promocodes_store.write_data(updated_promocodes)
        logger.info(f"Промокод {code} успешно удалён.")
        return True

    async def list_promocodes(self) -> List[Promocode]:
        """
        Возвращает список всех промокодов.

        :return: Список объектов Promocode.
        """
        promocodes = await self.promocodes_store.read_data()
        return [Promocode.from_dict(promo) for promo in promocodes]

    async def deactivate_promocode(self, code: str) -> bool:
        """
        Деактивирует промокод без его применения.

        :param code: Код промокода.
        :return: True если промокод успешно деактивирован, иначе False.
        """
        promocodes = await self.promocodes_store.read_data()
        for promo_data in promocodes:
            if promo_data["code"] == code and promo_data.get("active", True):
                promo_data["active"] = False
                await self.promocodes_store.write_data(promocodes)
                logger.info(f"Promocode {code} деактивирован.")
                return True
        logger.warning(f"Не удалось деактивировать промокод {code}. Он может быть уже неактивным или не существовать.")
        return False
