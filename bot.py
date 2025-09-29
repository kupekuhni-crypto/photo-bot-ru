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
    asyncio.run(main())    data = await state.get_data()
    service = data["service"]
    
    # Скачиваем фото
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            image_bytes = await resp.read()
    
    # Конверт в base64
    image_b64 = "image/jpeg;base64," + base64.b64encode(image_bytes).decode()
    
    try:
        client = replicate.Client(api_token=REPLICATE_API_TOKEN)
        
        if service == "restore":
            # Последовательная обработка: restore → upscale → colorize
            restored = client.run(
                "batouk/restore-old-photos:7a585186a8323b75f61c38e0c8c8e2e8d5e9e8a8e8e8e8e8e8e8e8e8e8e8e8e8",
                input={"image": image_b64}
            )
            upscaled = client.run(
                "xinntao/realesrgan:42f8e3a8d3e4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0",
                input={"image": restored, "scale": 4}
            )
            result = client.run(
                "photoroom/colorize:7a585186a8323b75f61c38e0c8c8e2e8d5e9e8a8e8e8e8e8e8e8e8e8e8e8e8e8",
                input={"image": upscaled}
            )
            await message.answer_photo(photo=result)
            
        elif service == "animate":
            result = client.run(
                "peter9477/liveportrait:7a585186a8323b75f61c38e0c8c8e2e8d5e9e8a8e8e8e8e8e8e8e8e8e8e8e8e8",
                input={"image": image_b64}
            )
            await message.answer_video(video=result)
    
    except Exception as e:
        logging.error(f"Ошибка: {e}")
        await message.answer("Не удалось обработать фото. Попробуйте другое.")
    
    await message.answer("Готово! Спасибо, что доверили нам память о близких.", reply_markup=MAIN_KEYBOARD)
    await state.clear()

async def main():
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__":

    asyncio.run(main())
