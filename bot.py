# bot.py
import os
import logging
from aiogram import Bot, Dispatcher, Router, types
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import replicate
import asyncio
import tempfile
import aiohttp
import base64
from PIL import Image
import io

logging.basicConfig(level=logging.INFO)
BOT_TOKEN = os.getenv("BOT_TOKEN")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
YOOMONEY_PACK1 = os.getenv("YOOMONEY_PACK1_URL", "https://yoomoney.ru")
YOOMONEY_PACK3 = os.getenv("YOOMONEY_PACK3_URL", "https://yoomoney.ru")
YOOMONEY_PACK5 = os.getenv("YOOMONEY_PACK5_URL", "https://yoomoney.ru")
YOOMONEY_ANIMATE = os.getenv("YOOMONEY_ANIMATE_URL", "https://yoomoney.ru")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()

class UserState(StatesGroup):
    service = State()
    photos = State()

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Восстановить и раскрасить фото")],
        [KeyboardButton(text="Оживить лицо на фото")],
        [KeyboardButton(text="❓ Инструкция и цены")]
    ],
    resize_keyboard=True
)

@router.message(Command("start"))
async def start(message: Message, state: FSMContext):
    await message.answer(
        "Здравствуйте!\n\n"
        "Этот бот поможет бережно восстановить старые фотографии ваших близких:\n"
        "✨ Уберём царапины и пятна\n"
        "✨ Увеличим качество в 4 раза\n"
        "✨ Вернём естественные цвета\n"
        "🎥 Оживим лицо на фото (лёгкая анимация)\n\n"
        "Нажмите кнопку и отправьте фото.",
        reply_markup=MAIN_KEYBOARD
    )

@router.message(lambda m: m.text == "Восстановить и раскрасить фото")
async def restore_start(message: Message, state: FSMContext):
    await state.set_state(UserState.photos)
    await state.update_data(service="restore")
    pay_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1 фото — 110 ₽", url=YOOMONEY_PACK1)],
        [InlineKeyboardButton(text="3 фото — 280 ₽", url=YOOMONEY_PACK3)],
        [InlineKeyboardButton(text="5 фото — 420 ₽", url=YOOMONEY_PACK5)]
    ])
    await message.answer("Выберите пакет:", reply_markup=pay_kb)
    await message.answer("После оплаты отправьте фото(а).")

@router.message(lambda m: m.text == "Оживить лицо на фото")
async def animate_start(message: Message, state: FSMContext):
    await state.set_state(UserState.photos)
    await state.update_data(service="animate")
    pay_btn = InlineKeyboardButton(text="Оживление — 130 ₽", url=YOOMONEY_ANIMATE)
    await message.answer(
        "Оплатите обработку:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[pay_btn]])
    )
    await message.answer("После оплаты отправьте фото.")

@router.message(lambda m: m.text == "❓ Инструкция и цены")
async def help(message: Message):
    await message.answer(
        "💰 Цены:\n"
        "• 1 фото — 110 ₽\n"
        "• 3 фото — 280 ₽ (экономия 50 ₽)\n"
        "• 5 фото — 420 ₽ (экономия 130 ₽)\n"
        "• Оживление лица — 130 ₽\n\n"
        "🔒 Все фото удаляются после обработки.\n"
        "📩 Поддержка: @ваш_ник_в_телеграме",
        reply_markup=MAIN_KEYBOARD
    )

@router.message(UserState.photos, lambda m: m.photo)
async def process_photos(message: Message, state: FSMContext):
    await message.answer("Обрабатываем... Это займёт 20–60 секунд.")
    
    # Получаем данные
    data = await state.get_data()
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