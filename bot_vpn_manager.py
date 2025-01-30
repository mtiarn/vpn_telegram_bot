# bot_vpn_manager.py

import logging
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

from config import Config
from vpn_service import VPNService, User
from promocode import PromocodeService
from request_service import RequestService, Request
from json_utils import JSONDataStore

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Загрузка конфигурации
config = Config()

# Инициализация бота и диспетчера
bot = Bot(token=config.TELEGRAM_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# Инициализация хранилищ данных
users_store = JSONDataStore(config.USERS_FILE)
promocodes_store = JSONDataStore(config.PROMOCODES_FILE)
requests_store = JSONDataStore(config.REQUESTS_FILE)

# Инициализация сервисов
promocode_service = PromocodeService(promocodes_store)
request_service = RequestService(requests_store)
vpn_service = VPNService(
    users_store=users_store,
    promocodes_store=promocodes_store,
    requests_store=requests_store,
    config=config,
    promocode_service=promocode_service,
    request_service=request_service
)

# Состояния для отправки заявки
class SendRequestForm(StatesGroup):
    waiting_for_details = State()

# Клавиатуры
def get_user_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(
        KeyboardButton("📄 Оформить через Промокод"),
        KeyboardButton("✉️ Отправить Заявку Администратору")
    )
    keyboard.add(KeyboardButton("📊 Статус Подписки"))
    return keyboard

def get_admin_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(
        KeyboardButton("🔍 Просмотреть Заявки"),
        KeyboardButton("💬 Ответить на Заявку")
    )
    keyboard.add(KeyboardButton("⬅️ Назад"))
    return keyboard

# Функция проверки администратора
def is_admin(user_id: int) -> bool:
    return user_id in config.BOT_ADMINS

# Обработчик команды /start
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    if is_admin(user_id):
        await message.reply("👋 Привет, администратор! Выберите действие:", reply_markup=get_admin_keyboard())
    else:
        await message.reply("👋 Привет! Выберите способ оформления подписки:", reply_markup=get_user_keyboard())

# Обработчик кнопки "Оформить через Промокод"
@dp.message_handler(lambda message: message.text == "📄 Оформить через Промокод")
async def cmd_subscribe_promo(message: types.Message):
    await message.reply("📩 Пожалуйста, введите ваш промокод:", reply_markup=ReplyKeyboardRemove())

    @dp.message_handler()
    async def process_promo_code(message: types.Message):
        promo_code = message.text.strip()
        user_id = message.from_user.id

        # Применение промокода
        success = await vpn_service.apply_promocode(user_id, promo_code)
        if success:
            await message.reply("✅ Ваш промокод успешно применён! Подписка активирована на 30 дней.", reply_markup=get_user_keyboard())
        else:
            await message.reply("❌ Неверный или уже использованный промокод. Пожалуйста, попробуйте снова или выберите другой способ оформления подписки.", reply_markup=get_user_keyboard())

# Обработчик кнопки "Отправить Заявку Администратору"
@dp.message_handler(lambda message: message.text == "✉️ Отправить Заявку Администратору")
async def cmd_send_request(message: types.Message):
    await SendRequestForm.waiting_for_details.set()
    await message.reply("📝 Пожалуйста, введите детали вашей заявки (например, количество устройств и предпочтительная длительность):", reply_markup=ReplyKeyboardRemove())

@dp.message_handler(state=SendRequestForm.waiting_for_details, content_types=types.ContentTypes.TEXT)
async def process_request_details(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    details = {"message": message.text.strip()}  # Можно расширить, чтобы парсить конкретные поля

    # Генерация уникального ID заявки
    request_id = await request_service.generate_new_request_id()
    timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
    new_request = Request(
        request_id=request_id,
        user_id=user_id,
        details=details,
        status="pending",
        timestamp=timestamp
    )

    # Создание заявки
    success = await request_service.create_request(new_request)
    if success:
        await message.reply("✅ Ваша заявка успешно отправлена администратору. Ожидайте ответа.", reply_markup=get_user_keyboard())
        logger.info(f"Новая заявка {request_id} от пользователя {user_id} создана.")
    else:
        await message.reply("❌ Произошла ошибка при отправке заявки. Пожалуйста, попробуйте позже.", reply_markup=get_user_keyboard())

    await state.finish()

# Обработчик кнопки "Статус Подписки"
@dp.message_handler(lambda message: message.text == "📊 Статус Подписки")
async def cmd_status(message: types.Message):
    user_id = message.from_user.id
    client_data = await vpn_service.get_client_data(user_id)
    if client_data:
        expiry_datetime = datetime.fromtimestamp(client_data.expiry_time / 1000).strftime('%Y-%m-%d %H:%M:%S')
        status_message = (
            f"🔹 **Статус Подписки** 🔹\n"
            f"Максимальное количество устройств: {client_data.max_devices}\n"
            f"Общий трафик: {client_data.traffic_total} GB\n"
            f"Оставшийся трафик: {client_data.traffic_remaining} GB\n"
            f"Использовано трафика: {client_data.traffic_used} GB\n"
            f"Трафик вверх: {client_data.traffic_up} GB\n"
            f"Трафик вниз: {client_data.traffic_down} GB\n"
            f"Время истечения подписки: {expiry_datetime}"
        )
        await message.reply(status_message, parse_mode='Markdown', reply_markup=get_user_keyboard())
    else:
        await message.reply("❌ У вас нет активной подписки или произошла ошибка при получении данных.", reply_markup=get_user_keyboard())

# Обработчик кнопки "Просмотреть Заявки" для администраторов
@dp.message_handler(lambda message: message.text == "🔍 Просмотреть Заявки")
async def cmd_view_requests(message: types.Message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        await message.reply("❌ У вас нет прав для использования этой команды.")
        return

    # Получение всех заявок с статусом "pending"
    pending_requests = await request_service.list_requests(status_filter="pending")
    if not pending_requests:
        await message.reply("📭 Нет новых заявок для обработки.", reply_markup=get_admin_keyboard())
        return

    response = "📄 **Список Новых Заявок:**\n\n"
    for req in pending_requests:
        response += (
            f"🔹 **ID заявки:** {req.request_id}\n"
            f"👤 **Пользователь ID:** {req.user_id}\n"
            f"📋 **Детали:** {req.details.get('message', 'Нет деталей')}\n"
            f"📅 **Время создания:** {datetime.fromtimestamp(req.timestamp / 1000).strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        )

    await message.reply(response, parse_mode='Markdown', reply_markup=get_admin_keyboard())

# Обработчик кнопки "Ответить на Заявку" для администраторов
@dp.message_handler(lambda message: message.text == "💬 Ответить на Заявку")
async def cmd_respond_request(message: types.Message):
    user_id = message.from_user.id
    if not is_admin(user_id):
        await message.reply("❌ У вас нет прав для использования этой команды.")
        return

    await RespondRequest.waiting_for_request_id.set()
    await message.reply("🔍 Пожалуйста, введите ID заявки, на которую хотите ответить:", reply_markup=ReplyKeyboardRemove())

# Состояния для ответа на заявку
class RespondRequest(StatesGroup):
    waiting_for_request_id = State()
    waiting_for_response_message = State()

@dp.message_handler(state=RespondRequest.waiting_for_request_id, content_types=types.ContentTypes.TEXT)
async def process_request_id(message: types.Message, state: FSMContext):
    request_id = message.text.strip()
    request = await request_service.get_request(request_id)
    if not request or request.status != "pending":
        await message.reply("❌ Заявка с таким ID не найдена или уже обработана. Пожалуйста, введите корректный ID заявки.", reply_markup=ReplyKeyboardRemove())
        return

    await RespondRequest.next()
    await state.update_data(request_id=request_id)
    await message.reply("💬 Пожалуйста, введите сообщение для пользователя:", reply_markup=ReplyKeyboardRemove())

@dp.message_handler(state=RespondRequest.waiting_for_response_message, content_types=types.ContentTypes.TEXT)
async def process_response_message(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    request_id = user_data.get("request_id")
    response_message = message.text.strip()

    # Отправка сообщения пользователю
    success = await vpn_service.respond_to_request(request_id, response_message)
    if success:
        await message.reply("✅ Сообщение пользователю успешно отправлено и заявка обновлена.", reply_markup=get_admin_keyboard())
    else:
        await message.reply("❌ Произошла ошибка при отправке сообщения пользователю или обновлении заявки.", reply_markup=get_admin_keyboard())

    await state.finish()

# Обработчик кнопки "Назад" для администраторов
@dp.message_handler(lambda message: message.text == "⬅️ Назад")
async def cmd_back_to_admin(message: types.Message):
    user_id = message.from_user.id
    if is_admin(user_id):
        await message.reply("👋 Вы вернулись в административное меню.", reply_markup=get_admin_keyboard())
    else:
        await message.reply("👋 Вы вернулись в главное меню.", reply_markup=get_user_keyboard())

# Запуск бота
async def main():
    # Инициализация сервисов и подключение к 3x-ui API
    await vpn_service.initialize()

    # Запуск polling
    try:
        logger.info("Бот запущен и готов к работе.")
        await dp.start_polling()
    finally:
        await bot.close()

if __name__ == '__main__':
    asyncio.run(main())
