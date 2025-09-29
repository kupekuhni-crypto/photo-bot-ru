import os
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Получение переменных окружения
BOT_TOKEN = os.getenv('BOT_TOKEN')
YOOMONEY_RESTORE_URL = os.getenv('YOOMONEY_RESTORE_URL')
YOOMONEY_ANIMATE_URL = os.getenv('YOOMONEY_ANIMATE_URL')

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Состояния FSM
class ServiceStates(StatesGroup):
    choosing_service = State()
    waiting_payment = State()

# Главное меню
def get_main_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Восстановить и раскрасить фото")],
            [KeyboardButton(text="Оживить лицо на фото")]
        ],
        resize_keyboard=True
    )
    return keyboard

# Обработчик команды /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Привет! Я бот для обработки фотографий.\n\n"
        "Выберите услугу:",
        reply_markup=get_main_keyboard()
    )
    await state.set_state(ServiceStates.choosing_service)

# Обработчик выбора услуги восстановления
@dp.message(lambda message: message.text == "Восстановить и раскрасить фото", ServiceStates.choosing_service)
async def restore_photo(message: types.Message, state: FSMContext):
    await message.answer(
        f"Услуга: Восстановление и раскрашивание фото\n\n"
        f"Для оплаты перейдите по ссылке:\n{YOOMONEY_RESTORE_URL}\n\n"
        f"После оплаты напишите «Готово»",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.update_data(service="restore")
    await state.set_state(ServiceStates.waiting_payment)

# Обработчик выбора услуги анимации
@dp.message(lambda message: message.text == "Оживить лицо на фото", ServiceStates.choosing_service)
async def animate_photo(message: types.Message, state: FSMContext):
    await message.answer(
        f"Услуга: Оживление лица на фото\n\n"
        f"Для оплаты перейдите по ссылке:\n{YOOMONEY_ANIMATE_URL}\n\n"
        f"После оплаты напишите «Готово»",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.update_data(service="animate")
    await state.set_state(ServiceStates.waiting_payment)

# Обработчик подтверждения оплаты
@dp.message(lambda message: message.text.lower() == "готово", ServiceStates.waiting_payment)
async def payment_done(message: types.Message, state: FSMContext):
    await message.answer("✅ Обработка завершена")
    await message.answer(
        "Выберите следующую услугу:",
        reply_markup=get_main_keyboard()
    )
    await state.set_state(ServiceStates.choosing_service)

# Обработчик всех остальных сообщений в состоянии ожидания оплаты
@dp.message(ServiceStates.waiting_payment)
async def waiting_payment_other(message: types.Message):
    await message.answer("Пожалуйста, напишите «Готово» после оплаты.")

# Обработчик всех остальных сообщений
@dp.message()
async def echo(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None or current_state == ServiceStates.choosing_service:
        await message.answer(
            "Пожалуйста, выберите услугу из меню:",
            reply_markup=get_main_keyboard()
        )
        await state.set_state(ServiceStates.choosing_service)

# Запуск бота
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    
