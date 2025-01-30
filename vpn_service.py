 # vpn_service.py

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from py3xui import AsyncApi, Client

# Для aiogram 3.x импорт Bot по-прежнему доступен так:
from aiogram import Bot

from config import Config
from json_utils import JSONDataStore
from promocode import PromocodeService
from request_service import RequestService, Request
from client import ClientData

logger = logging.getLogger(__name__)


class User:
    """
    Класс для представления пользователя VPN.
    """
    def __init__(self, user_id: int, vpn_id: str):
        self.user_id = user_id
        self.vpn_id = vpn_id

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "vpn_id": self.vpn_id
        }

    @staticmethod
    def from_dict(data: dict):
        return User(user_id=data["user_id"], vpn_id=data["vpn_id"])


class VPNService:
    """
    Сервис для управления операциями клиентов VPN, включая создание, обновление и
    управление подписками через панель 3x-ui.
    """

    def __init__(
        self,
        users_store: JSONDataStore,
        promocodes_store: JSONDataStore,
        requests_store: JSONDataStore,
        config: Config,
        promocode_service: PromocodeService,
        request_service: RequestService,
        bot: Bot  # Объект Bot из aiogram 3.x
    ) -> None:
        self.users_store = users_store
        self.promocodes_store = promocodes_store
        self.requests_store = requests_store
        self.subscription_prefix = config.xui.SUBSCRIPTION_PREFIX
        self.api = AsyncApi(
            host=config.xui.HOST,
            username=config.xui.USERNAME,
            password=config.xui.PASSWORD,
            token=config.xui.TOKEN,
            use_tls_verify=False,
            logger=logging.getLogger("xui"),
        )
        self.promocode_service = promocode_service
        self.request_service = request_service
        self.inbound_id = config.xui.INBOUND_ID  # Единственный inbound ID
        self.bot = bot  # Сохраняем объект бота для отправки сообщений
        logger.info("VPNService initialized.")

    async def initialize(self) -> None:
        """
        Инициализирует сервис VPN и выполняет вход в API панели 3x-ui.
        """
        try:
            await self.api.login()
            logger.info("Successfully logged into 3x-ui API.")
        except Exception as e:
            logger.error(f"Failed to login to 3x-ui API: {e}")
            raise

    async def get_user(self, user_id: int) -> Optional[User]:
        """
        Получает пользователя по user_id из JSON-файла.

        :param user_id: ID пользователя.
        :return: Объект User или None, если не найден.
        """
        users = await self.users_store.read_data()
        for user_data in users:
            if user_data["user_id"] == user_id:
                logger.debug(f"User {user_id} found in users.json.")
                return User.from_dict(user_data)
        logger.debug(f"User {user_id} not found in users.json.")
        return None

    async def save_user(self, user: User) -> None:
        """
        Сохраняет пользователя в JSON-файл.

        :param user: Объект User для сохранения.
        """
        users = await self.users_store.read_data()
        for idx, user_data in enumerate(users):
            if user_data["user_id"] == user.user_id:
                users[idx] = user.to_dict()
                await self.users_store.write_data(users)
                logger.debug(f"User {user.user_id} updated in users.json.")
                return
        # Если пользователя нет, добавляем нового
        users.append(user.to_dict())
        await self.users_store.write_data(users)
        logger.debug(f"User {user.user_id} added to users.json.")

    async def is_client_exists(self, user_id: int) -> Optional[Client]:
        """
        Проверяет, существует ли клиент VPN по user_id через API 3x-ui.

        :param user_id: ID пользователя.
        :return: Объект Client или None.
        """
        try:
            client = await self.api.client.get_by_email(str(user_id))
            if client:
                logger.debug(f"Client {user_id} exists in 3x-ui.")
            else:
                logger.debug(f"Client {user_id} does not exist in 3x-ui.")
            return client
        except Exception as e:
            logger.error(f"Error checking client existence for {user_id}: {e}")
            return None

    async def get_client_data(self, user_id: int) -> Optional[ClientData]:
        """
        Получает данные клиента VPN по user_id через API 3x-ui.

        :param user_id: ID пользователя.
        :return: Объект ClientData или None.
        """
        try:
            client: Client = await self.api.client.get_by_email(str(user_id))
            if client is None:
                logger.debug(f"No client data found for user {user_id}.")
                return None

            limit_ip = client.limit_ip
            max_devices = -1 if limit_ip == 0 else limit_ip
            traffic_total = client.total
            expiry_time = -1 if client.expiry_time == 0 else client.expiry_time

            if traffic_total <= 0:
                traffic_remaining = -1
                traffic_total = -1
            else:
                traffic_remaining = traffic_total - (client.up + client.down)

            traffic_used = client.up + client.down

            client_data = ClientData(
                max_devices=max_devices,
                traffic_total=traffic_total,
                traffic_remaining=traffic_remaining,
                traffic_used=traffic_used,
                traffic_up=client.up,
                traffic_down=client.down,
                expiry_time=expiry_time,
            )
            logger.debug(f"Retrieved client data for user {user_id}: {client_data}.")
            return client_data
        except Exception as e:
            logger.error(f"Error retrieving client data for {user_id}: {e}")
            return None

    async def create_client(
        self,
        user: User,
        devices: int,
        duration: int,
        enable: bool = True,
        flow: str = "xtls-rprx-vision",
        total_gb: int = 0,
    ) -> bool:
        """
        Создаёт нового клиента VPN через API 3x-ui.
        """
        logger.info(f"Creating client for user {user.user_id} with {devices} devices for {duration} days.")
        new_client = Client(
            email=str(user.user_id),
            enable=enable,
            id=user.vpn_id,
            expiry_time=self._days_to_timestamp(duration),
            flow=flow,
            limit_ip=devices,
            sub_id=self.subscription_prefix + str(user.user_id),
            total_gb=total_gb,
        )
        try:
            await self.api.client.add(self.inbound_id, [new_client])
            logger.info(f"Successfully created client for user {user.user_id}.")
            return True
        except Exception as e:
            logger.error(f"Failed to create client for user {user.user_id}: {e}")
            return False

    async def update_client(
        self,
        user: User,
        devices: int,
        duration: int,
        replace_devices: bool = False,
        replace_duration: bool = False,
        enable: bool = True,
        flow: str = "xtls-rprx-vision",
        total_gb: int = 0,
    ) -> bool:
        """
        Обновляет существующего клиента VPN через API 3x-ui.
        """
        logger.info(f"Updating client for user {user.user_id} with {devices} devices for {duration} days.")
        try:
            client: Client = await self.api.client.get_by_email(str(user.user_id))
            if client is None:
                logger.debug(f"Client {user.user_id} not found for update.")
                return False

            if not replace_devices:
                current_device_limit = client.limit_ip
                devices = current_device_limit + devices

            current_time = self._current_timestamp()

            if not replace_duration:
                expiry_time_to_use = max(client.expiry_time, current_time)
            else:
                expiry_time_to_use = current_time

            expiry_time = self._add_days_to_timestamp(expiry_time_to_use, duration)

            client.enable = enable
            client.expiry_time = expiry_time
            client.flow = flow
            client.limit_ip = devices
            client.sub_id = self.subscription_prefix + str(user.user_id)
            client.total_gb = total_gb

            await self.api.client.update(self.inbound_id, client.id, client)
            logger.info(f"Successfully updated client for user {user.user_id}.")
            return True
        except Exception as e:
            logger.error(f"Failed to update client for user {user.user_id}: {e}")
            return False

    async def create_subscription(self, user_id: int, devices: int, duration: int) -> bool:
        """
        Создаёт новую подписку для пользователя. Если пользователь уже существует, обновляет её.
        """
        user = await self.get_user(user_id)
        if not user:
            user = User(user_id=user_id, vpn_id=f"vpn_{user_id}")
            await self.save_user(user)
            logger.debug(f"User {user_id} created and saved to users.json.")

        client_exists = await self.is_client_exists(user.user_id)
        if not client_exists:
            success = await self.create_client(user, devices, duration)
            return success
        else:
            success = await self.update_client(
                user,
                devices,
                duration,
                replace_devices=True,
                replace_duration=True,
            )
            return success

    async def extend_subscription(self, user_id: int, devices: int, duration: int) -> bool:
        """
        Продлевает подписку для существующего пользователя.
        """
        user = await self.get_user(user_id)
        if not user:
            logger.error(f"User {user_id} not found for extension.")
            return False
        success = await self.update_client(
            user,
            devices,
            duration,
            replace_devices=True,
            replace_duration=False,  # Продлеваем без замены всей длительности
        )
        return success

    async def apply_promocode(self, user_id: int, promocode_code: str) -> bool:
        """
        Применяет промокод для пользователя, продлевая его подписку.
        """
        promocode = await self.promocode_service.get_promocode(promocode_code)
        if not promocode:
            logger.warning(f"Promocode {promocode_code} не найден или уже использован.")
            return False

        user = await self.get_user(user_id)
        if not user:
            user = User(user_id=user_id, vpn_id=f"vpn_{user_id}")
            await self.save_user(user)
            logger.debug(f"User {user_id} created and saved to users.json.")

        if await self.is_client_exists(user_id):
            # Продлеваем существующую подписку
            success = await self.update_client(
                user,
                devices=0,  # Не изменяем количество устройств
                duration=promocode.duration_days,
                replace_devices=False,
                replace_duration=False,
            )
            if success:
                await self.promocode_service.use_promocode(promocode_code)
                logger.info(f"Promocode {promocode_code} применён для пользователя {user_id}.")
                return True
        else:
            # Создаём нового клиента с 1 устройством (пример)
            success = await self.create_client(
                user,
                devices=1,
                duration=promocode.duration_days,
            )
            if success:
                await self.promocode_service.use_promocode(promocode_code)
                logger.info(f"Promocode {promocode_code} применён для нового пользователя {user_id}.")
                return True

        logger.warning(f"Не удалось применить промокод {promocode_code} для пользователя {user_id}.")
        return False

    async def handle_user_request(self, user_id: int, details: dict) -> bool:
        """
        Обрабатывает заявку пользователя на оформление подписки через администратора.
        """
        try:
            request = Request(
                user_id=user_id,
                details=details,
                status="pending",
                timestamp=self._current_timestamp()
            )
            await self.request_service.create_request(request)
            logger.info(f"Заявка от пользователя {user_id} успешно создана.")
            return True
        except Exception as e:
            logger.error(f"Ошибка при создании заявки от пользователя {user_id}: {e}")
            return False

    async def respond_to_request(self, request_id: str, message: str) -> bool:
        """
        Отправляет ответ пользователю по поводу его заявки и обновляет статус заявки.
        """
        try:
            request = await self.request_service.get_request(request_id)
            if not request:
                logger.warning(f"Заявка с ID {request_id} не найдена.")
                return False

            user_id = request.user_id
            success = await self.send_message_to_user(user_id, message)
            if not success:
                return False

            await self.request_service.update_request_status(request_id, "completed")
            logger.info(f"Заявка {request_id} обработана и пользователь {user_id} уведомлён.")
            return True
        except Exception as e:
            logger.error(f"Ошибка при ответе на заявку {request_id}: {e}")
            return False

    async def send_message_to_user(self, user_id: int, message: str) -> bool:
        """
        Отправляет сообщение пользователю через Telegram-бота (aiogram 3.x).
        """
        try:
            # В aiogram 3.x метод send_message работает так же, parse_mode поддерживается
            await self.bot.send_message(
                chat_id=user_id,
                text=message,
                parse_mode="Markdown"  # при необходимости можете заменить на "MarkdownV2" или "HTML"
            )
            logger.info(f"Сообщение пользователю {user_id} успешно отправлено.")
            return True
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение пользователю {user_id}: {e}")
            return False

    def _current_timestamp(self) -> int:
        """
        Возвращает текущий временной штамп в миллисекундах.
        """
        return int(datetime.now(timezone.utc).timestamp() * 1000)

    def _add_days_to_timestamp(self, timestamp: int, days: int) -> int:
        """
        Добавляет дни к временному штампу.
        """
        current_datetime = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
        new_datetime = current_datetime + timedelta(days=days)
        return int(new_datetime.timestamp() * 1000)

    def _days_to_timestamp(self, days: int) -> int:
        """
        Конвертирует дни в временной штамп.
        """
        current_time = self._current_timestamp()
        return self._add_days_to_timestamp(current_time, days)
