import os
import aiohttp
import asyncio
from aiogram import Bot, Dispatcher, F, types
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiohttp import web
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO

# --- Конфиги ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
REPLICATE_TOKEN = os.getenv("REPLICATE_API_TOKEN")

if not BOT_TOKEN or not REPLICATE_TOKEN:
    raise RuntimeError("BOT_TOKEN и REPLICATE_API_TOKEN обязательны!")

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# FSM
class OrderState(StatesGroup):
    waiting_photo = State()

# Главное меню
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="✨ Восстановить фото (249₽)")],
        [KeyboardButton(text="🎨 Сделать цветным (199₽)")],
        [KeyboardButton(text="😊 Оживить фото (249₽)")],
        [KeyboardButton(text="🆓 Попробовать бесплатно")],
        [KeyboardButton(text="📦 Дополнительно")],
        [KeyboardButton(text="ℹ️ Инструкция")],
    ],
    resize_keyboard=True
)

# Дополнительное меню
extra_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔎 Увеличить качество фото (149₽)")],
        [KeyboardButton(text="🎙 Говорящее фото (VIP, 349₽)")],
        [KeyboardButton(text="⬅️ Назад")],
    ],
    resize_keyboard=True
)

# --- Модели Replicate ---
MODELS = {
    "restore": "flux-kontext-apps/restore-image:9685836a-8c4d-4f5b-829d-a5df1a2b75c6",
    "colorize": "jantic/deoldify:a1557ee7f36c4edba5832252497a15cf63c01d10293fbe466fc8da4e1bdf8d6b",
    "upscale": "xinntao/realesrgan:1d6a2f505b2712369a6c0aaf9a2d95ea9325da1425ed638232a5edbde069d44e",
    "animate": "albarji/face-vid2vid:6c2cbe0abada4a249cfefeb0b13ab3ab911c2da6f0986d5f1fd5fef0429ae2d1",
    "talk": "camenduru/sadtalker:f650960fbc2b43d88fc4a08ecb15696ffc2c85d1396830e15787adfcd8734a09",
}

# --- Примерные фото (заглушки с Unsplash) ---
DEMO_IMAGES = {
    "restore": "https://images.unsplash.com/photo-1503023345310-bd7c1de61c7d",   # старое лицо
    "colorize": "https://images.unsplash.com/photo-1501594907352-04cda38ebc29",  # ч/б девушка
    "animate": "https://images.unsplash.com/photo-1500648767791-00dcc994a43e",   # портрет мужчины
    "upscale": "https://images.unsplash.com/photo-1504198453319-5ce911bafcde",   # природа
    "talk": "https://images.unsplash.com/photo-1544005313-94ddf0286df2",         # портрет женщины
}

# --- Replicate API ---
async def process_replicate(image_url: str, model: str, extra_input: dict = None) -> str:
    headers = {"Authorization": f"Token {REPLICATE_TOKEN}"}
    payload = {"version": model, "input": {"image": image_url}}
    if extra_input:
        payload["input"].update(extra_input)
    async with aiohttp.ClientSession() as session:
        r = await session.post("https://api.replicate.com/v1/predictions", headers=headers, json=payload)
        data = await r.json()
        pred_id = data.get("id")
        if not pred_id:
            return None
        while True:
            rr = await session.get(f"https://api.replicate.com/v1/predictions/{pred_id}", headers=headers)
            dd = await rr.json()
            if dd["status"] == "succeeded":
                return dd["output"][0] if isinstance(dd["output"], list) else dd["output"]
            if dd["status"] in ["failed", "canceled"]:
                return None
            await asyncio.sleep(2)

# --- Watermark ---
def add_watermark(image_bytes: bytes, text="DEMO") -> bytes:
    img = Image.open(BytesIO(image_bytes)).convert("RGBA")
    watermark = Image.new("RGBA", img.size, (0,0,0,0))
    draw = ImageDraw.Draw(watermark)
    w, h = img.size
    font_size = max(20, w//10)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
    except:
        font = ImageFont.load_default()
    text_w, text_h = draw.textsize(text, font)
    draw.text(((w - text_w)//2, (h - text_h)//2), text, fill=(255,255,255,180), font=font)
    out = Image.alpha_composite(img, watermark)
    buf = BytesIO(); out.convert("RGB").save(buf, "JPEG")
    return buf.getvalue()

# --- Старт ---
@dp.message(F.text.in_(['/start', '/help']))
async def start_handler(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("👋 Привет! Я помогу восстановить, раскрасить и оживить ваши фото.\n\nВыберите услугу:",
                   reply_markup=main_kb)

@dp.message(F.text == "ℹ️ Инструкция")
async def instructions(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("📌 Требования к фото:\n"
                   "✅ Фото ровное (не перевёрнуто)\n"
                   "✅ Лицо видно полностью\n"
                   "✅ Нет рук/лишних предметов\n"
                   "✅ Хорошее качество\n\n"
                   "⏳ Обработка: 30–40 секунд.\n\nВыберите услугу 👇",
                   reply_markup=main_kb)

@dp.message(F.text == "📦 Дополнительно")
async def extras_menu(m: Message):
    await m.answer("📦 Дополнительные возможности:", reply_markup=extra_kb)

@dp.message(F.text == "⬅️ Назад")
async def back_to_main(m: Message):
    await m.answer("⬅️ Возвращаемся в главное меню:", reply_markup=main_kb)

# --- Услуги с фото-примерами ---
@dp.message(F.text.startswith("✨"))
async def choose_restore(m: Message, state: FSMContext):
    await m.answer_photo(
        DEMO_IMAGES["restore"],
        caption="✨ Восстановление фото (249₽)\n\n📸 Уберём царапины, шум и трещины.\n🔎 Улучшим чёткость и разрешение.\n\nПришлите своё фото ⬇️"
    )
    await state.set_state(OrderState.waiting_photo)
    await state.update_data(service="restore")

@dp.message(F.text.startswith("🎨"))
async def choose_colorize(m: Message, state: FSMContext):
    await m.answer_photo(
        DEMO_IMAGES["colorize"],
        caption="🎨 Сделать цветным (199₽)\n\nДобавим яркие и естественные цвета к ч/б снимку.\n\nПришлите фото ⬇️"
    )
    await state.set_state(OrderState.waiting_photo)
    await state.update_data(service="colorize")

@dp.message(F.text.startswith("😊"))
async def choose_animate(m: Message, state: FSMContext):
    await m.answer_photo(
        DEMO_IMAGES["animate"],
        caption="😊 Оживить фото (249₽)\n\nПревратим статичное фото в короткое видео с движением.\n\nПришлите фото ⬇️"
    )
    await state.set_state(OrderState.waiting_photo)
    await state.update_data(service="animate")

@dp.message(F.text.startswith("🔎"))
async def choose_upscale(m: Message, state: FSMContext):
    await m.answer_photo(
        DEMO_IMAGES["upscale"],
        caption="🔎 Увеличить качество фото (149₽)\n\nПовысим чёткость и детализацию.\n\nПришлите фото ⬇️"
    )
    await state.set_state(OrderState.waiting_photo)
    await state.update_data(service="upscale")

@dp.message(F.text.startswith("🎙"))
async def choose_talk(m: Message, state: FSMContext):
    await m.answer_photo(
        DEMO_IMAGES["talk"],
        caption="🎙 Говорящее фото (VIP, 349₽)\n\nСделаем видео, где человек на фото открывает рот и говорит.\n\nПришлите фото ⬇️"
    )
    await state.set_state(OrderState.waiting_photo)
    await state.update_data(service="talk")

@dp.message(F.text == "🆓 Попробовать бесплатно")
async def demo_start(m: Message, state: FSMContext):
    await m.answer("🆓 Демо-режим: пришлите фото, результат будет с водяным знаком 💧.")
    await state.set_state(OrderState.waiting_photo)
    await state.update_data(service="demo")

# --- Обработка фото ---
@dp.message(OrderState.waiting_photo, F.photo)
async def process_photo(m: Message, state: FSMContext):
    data = await state.get_data()
    service = data.get("service")

    file = await bot.get_file(m.photo[-1].file_id)
    photo_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"

    await m.answer("⏳ Обрабатываю фото...")

    if service == "demo":
        result_url = await process_replicate(photo_url, MODELS["restore"])
        if result_url:
            async with aiohttp.ClientSession() as session:
                async with session.get(result_url) as resp:
                    raw = await resp.read()
            wm = add_watermark(raw, "DEMO")
            await bot.send_photo(m.chat.id, photo=wm, caption="💧 Это демо. Чтобы получить фото без водяного знака — выберите услугу из меню.")
        else:
            await m.answer("⚠️ Ошибка демо.")
        await state.clear()
        return

    model_ver = MODELS[service]
    result = await process_replicate(photo_url, model_ver)

    if result:
        if service in ["animate", "talk"]:
            await m.answer_video(result, caption="✅ Ваше видео готово!")
        else:
            await m.answer_photo(result, caption="✅ Вот результат!")
    else:
        await m.answer("⚠️ Ошибка обработки.")
    await state.clear()

# --- Healthcheck ---
async def handle_health(request): return web.Response(text="OK", status=200)
async def start_webserver():
    app = web.Application(); app.router.add_get("/", handle_health)
    runner = web.AppRunner(app); await runner.setup()
    site = web.TCPSite(runner,"0.0.0.0",int(os.getenv("PORT",10000))); await site.start()

# --- Main ---
async def main():
    asyncio.create_task(start_webserver())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
