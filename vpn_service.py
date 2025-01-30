# vpn_service.py

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from py3xui import AsyncApi, Client

from config import Config
from json_utils import JSONDataStore
from promocode import PromocodeService, Promocode
from request_service import RequestService, Request
from client import ClientData  # Предполагается, что этот файл содержит класс ClientData

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
        request_service: RequestService
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

            # Поскольку у вас только один inbound, лимит IP фиксирован
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

        :param user: Объект User.
        :param devices: Количество устройств.
        :param duration: Длительность в днях.
        :param enable: Включен ли клиент.
        :param flow: Протокол.
        :param total_gb: Общий трафик в ГБ.
        :return: True если успешно, иначе False.
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

        :param user: Объект User.
        :param devices: Количество устройств.
        :param duration: Длительность в днях.
        :param replace_devices: Заменить количество устройств.
        :param replace_duration: Заменить длительность.
        :param enable: Включен ли клиент.
        :param flow: Протокол.
        :param total_gb: Общий трафик в ГБ.
        :return: True если успешно, иначе False.
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

            # Обновляем поля клиента
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

        :param user_id: ID пользователя.
        :param devices: Количество устройств.
        :param duration: Длительность в днях.
        :return: True если успешно, иначе False.
        """
        user = await self.get_user(user_id)
        if not user:
            # Если пользователя нет, создаём нового
            user = User(user_id=user_id, vpn_id=f"vpn_{user_id}")
            await self.save_user(user)
            logger.debug(f"User {user_id} created and saved to users.json.")

        client_exists = await self.is_client_exists(user.user_id)
        if not client_exists:
            # Создаём нового клиента
            success = await self.create_client(user, devices, duration)
            return success
        else:
            # Обновляем существующего клиента
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

        :param user_id: ID пользователя.
        :param devices: Количество устройств.
        :param duration: Длительность в днях.
        :return: True если успешно, иначе False.
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
            replace_duration=False,  # Продление без замены длительности
        )
        return success

    async def apply_promocode(self, user_id: int, promocode_code: str) -> bool:
        """
        Применяет промокод для пользователя, продлевая его подписку.

        :param user_id: ID пользователя.
        :param promocode_code: Код промокода.
        :return: True если успешно, иначе False.
        """
        promocode = await self.promocode_service.get_promocode(promocode_code)
        if not promocode:
            logger.warning(f"Promocode {promocode_code} не найден или уже использован.")
            return False

        user = await self.get_user(user_id)
        if not user:
            # Создаём нового пользователя, если его нет
            user = User(user_id=user_id, vpn_id=f"vpn_{user_id}")
            await self.save_user(user)
            logger.debug(f"User {user_id} created and saved to users.json.")

        if await self.is_client_exists(user_id):
            # Продлеваем существующую подписку без изменения количества устройств
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
            # Создаём нового клиента с количеством устройств по умолчанию
            success = await self.create_client(
                user,
                devices=1,  # По умолчанию 1 устройство при использовании промокода
                duration=promocode.duration_days,
            )
            if success:
                await self.promocode_service.use_promocode(promocode_code)
                logger.info(f"Promocode {promocode_code} применён для нового пользователя {user_id}.")
                return True

        # Если что-то пошло не так, возвращаем False
        logger.warning(f"Не удалось применить промокод {promocode_code} для пользователя {user_id}.")
        return False

    async def handle_user_request(self, user_id: int, details: dict) -> bool:
        """
        Обрабатывает заявку пользователя на оформление подписки через администратора.

        :param user_id: ID пользователя.
        :param details: Детали заявки.
        :return: True если успешно, иначе False.
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

        :param request_id: ID заявки.
        :param message: Сообщение для пользователя.
        :return: True если успешно, иначе False.
        """
        try:
            request = await self.request_service.get_request(request_id)
            if not request:
                logger.warning(f"Заявка с ID {request_id} не найдена.")
                return False

            user_id = request.user_id
            # Отправляем сообщение пользователю через Telegram-бота
            await self.send_message_to_user(user_id, message)

            # Обновляем статус заявки
            await self.request_service.update_request_status(request_id, "completed")
            logger.info(f"Заявка {request_id} обработана и пользователь {user_id} уведомлён.")
            return True
        except Exception as e:
            logger.error(f"Ошибка при ответе на заявку {request_id}: {e}")
            return False

    async def send_message_to_user(self, user_id: int, message: str) -> bool:
        """
        Отправляет сообщение пользователю через Telegram-бота.

        :param user_id: ID пользователя.
        :param message: Сообщение для отправки.
        :return: True если успешно, иначе False.
        """
        try:
            from bot_vpn_manager import bot  # Импортируем бот из основного файла
            await bot.send_message(chat_id=user_id, text=message)
            logger.info(f"Сообщение пользователю {user_id} успешно отправлено.")
            return True
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение пользователю {user_id}: {e}")
            return False

    def _current_timestamp(self) -> int:
        """
        Возвращает текущий временной штамп в миллисекундах.

        :return: Временной штамп.
        """
        return int(datetime.now(timezone.utc).timestamp() * 1000)

    def _add_days_to_timestamp(self, timestamp: int, days: int) -> int:
        """
        Добавляет дни к временном штампу.

        :param timestamp: Исходный временной штамп.
        :param days: Количество дней.
        :return: Обновлённый временной штамп.
        """
        current_datetime = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
        new_datetime = current_datetime + timedelta(days=days)
        return int(new_datetime.timestamp() * 1000)

    def _days_to_timestamp(self, days: int) -> int:
        """
        Конвертирует дни в временной штамп.

        :param days: Количество дней.
        :return: Временной штамп.
        """
        current_time = self._current_timestamp()
        return self._add_days_to_timestamp(current_time, days)
