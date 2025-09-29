import os
import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiohttp import web

# --- Переменные окружения ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
YOOMONEY_RESTORE_URL = os.getenv("YOOMONEY_RESTORE_URL")
YOOMONEY_ANIMATE_URL = os.getenv("YOOMONEY_ANIMATE_URL")

if not BOT_TOKEN:
    raise RuntimeError("Необходимо указать BOT_TOKEN в переменных окружения.")

# --- Создание бота и диспетчера ---
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# --- FSM ---
class ServiceChoice(StatesGroup):
    waiting_for_payment = State()

# --- Клавиатура ---
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Восстановить и раскрасить фото")],
        [KeyboardButton(text="Оживить лицо на фото")],
    ],
    resize_keyboard=True
)

# --- Хэндлеры ---
@dp.message(F.text.in_(["/start", "/help"]))
async def start_handler(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Привет! Я могу помочь с фото.\nВыберите услугу:",
        reply_markup=main_kb
    )

@dp.message(F.text == "Восстановить и раскрасить фото")
async def restore_handler(message: Message, state: FSMContext):
    if not YOOMONEY_RESTORE_URL:
        await message.answer("⚠️ Не задана ссылка YOOMONEY_RESTORE_URL.")
        return
    await state.set_state(ServiceChoice.waiting_for_payment)
    await message.answer(
        f"ℹ️ Для продолжения оплатите услугу по ссылке:\n{YOOMONEY_RESTORE_URL}\n\n"
        "После оплаты напишите: <b>Готово</b>"
    )

@dp.message(F.text == "Оживить лицо на фото")
async def animate_handler(message: Message, state: FSMContext):
    if not YOOMONEY_ANIMATE_URL:
        await message.answer("⚠️ Не задана ссылка YOOMONEY_ANIMATE_URL.")
        return
    await state.set_state(ServiceChoice.waiting_for_payment)
    await message.answer(
        f"ℹ️ Для продолжения оплатите услугу по ссылке:\n{YOOMONEY_ANIMATE_URL}\n\n"
        "После оплаты напишите: <b>Готово</b>"
    )

@dp.message(ServiceChoice.waiting_for_payment, F.text.lower() == "готово")
async def done_handler(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("✅ Обработка завершена", reply_markup=main_kb)

# --- Healthcheck endpoint для UptimeRobot ---
async def handle_health(request):
    return web.Response(text="OK", status=200)

async def start_webserver():
    app = web.Application()
    app.router.add_get("/", handle_health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 10000)))
    await site.start()

# --- Точка входа ---
async def main():
    # Запускаем healthcheck‑сервер
    asyncio.create_task(start_webserver())
    # Запускаем бота
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
