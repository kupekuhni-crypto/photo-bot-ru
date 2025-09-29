import os
import asyncio
import aiohttp
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

from aiogram import Bot, Dispatcher, F, types
from aiogram.types import Message, LabeledPrice, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# --- Конфиги ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
PAYMENT_PROVIDER_TOKEN = os.getenv("YOOMONEY_PROVIDER")
REPLICATE_TOKEN = os.getenv("REPLICATE_API_TOKEN")

if not BOT_TOKEN or not PAYMENT_PROVIDER_TOKEN or not REPLICATE_TOKEN:
    raise RuntimeError("Необходимо указать BOT_TOKEN, YOOMONEY_PROVIDER и REPLICATE_API_TOKEN!")

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# --- FSM ---
class OrderState(StatesGroup):
    waiting_photo_demo = State()   # ждём фото для пробного демо
    waiting_photo_paid = State()   # ждём фото после оплаты

# --- Главное меню ---
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🖼 Восстановление фото")],
        [KeyboardButton(text="🎨 Раскрашивание фото")],
        [KeyboardButton(text="🔎 Увеличение качества")],
        [KeyboardButton(text="😊 Оживление лица")],
        [KeyboardButton(text="📦 Попробовать бесплатно (демо)")],
    ],
    resize_keyboard=True
)

# --- Цены ---
PRICES = {
    "restore": 19900,    # в копейках
    "colorize": 19900,
    "upscale": 14900,
    "animate": 24900,
}

# --- Модели Replicate (замени version-id на реальные) ---
MODELS = {
    "restore": "sczhou/codeformer:version-id",
    "colorize": "jantic/deoldify:version-id",
    "upscale": "xinntao/realesrgan:version-id",
    "animate": "albarji/face-vid2vid:version-id",
}

# --- Водяной знак ---
def add_watermark(image_bytes: bytes, text: str = "DEMO") -> bytes:
    img = Image.open(BytesIO(image_bytes)).convert("RGBA")
    watermark = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(watermark)

    w, h = img.size
    font_size = max(30, w // 10)
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size
        )
    except:
        font = ImageFont.load_default()

    text_w, text_h = draw.textsize(text, font)
    draw.text(
        ((w - text_w) // 2, (h - text_h) // 2),
        text,
        (255, 255, 255, 180),
        font=font,
    )

    out = Image.alpha_composite(img, watermark)
    buffer = BytesIO()
    out.convert("RGB").save(buffer, format="JPEG")
    return buffer.getvalue()

# --- Работа с Replicate ---
async def process_replicate(image_url: str, model: str) -> str:
    headers = {"Authorization": f"Token {REPLICATE_TOKEN}"}
    async with aiohttp.ClientSession() as session:
        r = await session.post(
            "https://api.replicate.com/v1/predictions",
            headers=headers,
            json={"version": model, "input": {"image": image_url}}
        )
        data = await r.json()
        pred_id = data["id"]

        # ждём завершения
        while True:
            rr = await session.get(f"https://api.replicate.com/v1/predictions/{pred_id}", headers=headers)
            dd = await rr.json()
            status = dd["status"]
            if status == "succeeded":
                return dd["output"][0]
            elif status in ["failed", "canceled"]:
                return None
            await asyncio.sleep(2)

# === Хэндлеры ===
@dp.message(F.text.in_(["/start", "/help"]))
async def start_handler(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("👋 Привет! Я помогу восстановить, раскрасить и оживить ваши фото.\nВыберите услугу:", reply_markup=main_kb)

# Пробное демо
@dp.message(F.text == "📦 Попробовать бесплатно (демо)")
async def demo_start(message: Message, state: FSMContext):
    await state.set_state(OrderState.waiting_photo_demo)
    await message.answer("📷 Пришлите фото для демо. Я обработаю его и наложу водяной знак.")

@dp.message(OrderState.waiting_photo_demo, F.photo)
async def handle_demo(message: Message, state: FSMContext):
    file = await bot.get_file(message.photo[-1].file_id)
    photo_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"

    # берём модель восстановления "restore" для демо
    model_ver = MODELS["restore"]
    result = await process_replicate(photo_url, model_ver)
    if not result:
        await message.answer("⚠️ Ошибка обработки.")
        return

    # накладываем watermark
    async with aiohttp.ClientSession() as session:
        async with session.get(result) as resp:
            img = await resp.read()
    marked = add_watermark(img, "DEMO")

    await bot.send_photo(
        chat_id=message.chat.id,
        photo=marked,
        caption="Это демо-результат с водяным знаком. Оплатите услугу, чтобы получить результат без ограничений."
    )

# Универсальный сервис → отправляем счёт
async def send_service_invoice(message: Message, service: str, title: str, desc: str):
    prices = [LabeledPrice(label=title, amount=PRICES[service])]
    await bot.send_invoice(
        chat_id=message.chat.id,
        title=title,
        description=desc,
        provider_token=PAYMENT_PROVIDER_TOKEN,
        currency="RUB",
        prices=prices,
        payload=service
    )

# Кнопки для услуг
@dp.message(F.text == "🖼 Восстановление фото")
async def service_restore(m: Message): 
    await send_service_invoice(m, "restore", "Восстановление фото", "Профессиональная реставрация старых снимков ИИ")

@dp.message(F.text == "🎨 Раскрашивание фото")
async def service_color(m: Message): 
    await send_service_invoice(m, "colorize", "Раскрашивание фото", "Цветизация ч/б фотографий")

@dp.message(F.text == "🔎 Увеличение качества")
async def service_upscale(m: Message): 
    await send_service_invoice(m, "upscale", "Увеличение качества", "Повышение чёткости изображения (апскейл)")

@dp.message(F.text == "😊 Оживление лица")
async def service_animate(m: Message): 
    await send_service_invoice(m, "animate", "Оживление лица", "Анимация фотографии лица")

# обязательный pre_checkout
@dp.pre_checkout_query()
async def pcq(pre: types.PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre.id, ok=True)

# успешная оплата
@dp.message(F.successful_payment)
async def payment(message: Message, state: FSMContext):
    service = message.successful_payment.invoice_payload
    await state.set_state(OrderState.waiting_photo_paid)
    await state.update_data(service=service)
    await message.answer("✅ Оплата прошла! Пришлите фото для обработки.")

# Приём фото после оплаты
@dp.message(OrderState.waiting_photo_paid, F.photo)
async def process_paid_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    service = data.get("service")

    file = await bot.get_file(message.photo[-1].file_id)
    photo_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"

    model_ver = MODELS[service]
    result = await process_replicate(photo_url, model_ver)

    if not result:
        await message.answer("⚠️ Не удалось обработать фото.")
        return

    # Анимация даёт видео → проверим
    if service == "animate":
        await message.answer_video(result, caption="✅ Ваш результат готов!")
    else:
        await message.answer_photo(result, caption="✅ Ваш результат готов!")

    await state.clear()

# --- main ---
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
