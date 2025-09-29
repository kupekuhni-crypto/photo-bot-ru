import os
import asyncio
import aiohttp
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

from aiogram import Bot, Dispatcher, F, types
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, LabeledPrice
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiohttp import web

# --- Конфиги ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
PAYMENT_PROVIDER_TOKEN = os.getenv("YOOMONEY_PROVIDER", "TEST")  # если TEST — будет заглушка оплаты
REPLICATE_TOKEN = os.getenv("REPLICATE_API_TOKEN")

if not BOT_TOKEN or not REPLICATE_TOKEN:
    raise RuntimeError("BOT_TOKEN и REPLICATE_API_TOKEN обязательны!")

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# --- FSM ---
class OrderState(StatesGroup):
    waiting_demo_photo = State()
    waiting_payment = State()

# --- Цены (копейки RUB) ---
PRICES = {
    "restore": 19900,
    "colorize": 19900,
    "upscale": 14900,
    "animate": 24900,
    "pack3": 49900,
    "pack5": 79900,
}

# --- Модели Replicate (замени version-id на реальные) ---
MODELS = {
    "restore": "sczhou/codeformer:version-id",
    "colorize": "jantic/deoldify:version-id",
    "upscale": "xinntao/realesrgan:version-id",
    "animate": "albarji/face-vid2vid:version-id",
}

# --- Главное меню ---
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🖼 Восстановить фото (199₽)")],
        [KeyboardButton(text="🎨 Сделать цветным (199₽)")],
        [KeyboardButton(text="🔎 Увеличить качество (149₽)")],
        [KeyboardButton(text="😊 Оживить лицо (249₽)")],
        [KeyboardButton(text="📦 Пакет 3 фото (499₽)"), KeyboardButton(text="📦 Пакет 5 фото (799₽)")],
        [KeyboardButton(text="✨ Попробовать демо бесплатно")],
        [KeyboardButton(text="ℹ️ Инструкция")],
    ],
    resize_keyboard=True
)

# --- Водяной знак ---
def add_watermark(image_bytes: bytes, text: str = "DEMO") -> bytes:
    img = Image.open(BytesIO(image_bytes)).convert("RGBA")
    watermark = Image.new("RGBA", img.size, (0,0,0,0))
    draw = ImageDraw.Draw(watermark)
    w, h = img.size
    font_size = max(30, w // 10)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
    except:
        font = ImageFont.load_default()
    text_w, text_h = draw.textsize(text, font)
    draw.text(((w-text_w)//2, (h-text_h)//2), text, (255,255,255,180), font=font)
    out = Image.alpha_composite(img, watermark)
    buffer = BytesIO()
    out.convert("RGB").save(buffer, format="JPEG")
    return buffer.getvalue()

# --- Replicate API ---
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

        while True:
            rr = await session.get(f"https://api.replicate.com/v1/predictions/{pred_id}", headers=headers)
            dd = await rr.json()
            if dd["status"] == "succeeded":
                return dd["output"][0]
            if dd["status"] in ["failed", "canceled"]:
                return None
            await asyncio.sleep(2)

# --- Старт ---
@dp.message(F.text.in_(['/start', '/help']))
async def start(m: Message, state: FSMContext):
    await state.clear()
    await m.answer(
        "👋 Привет! Я помогу восстановить, раскрасить и оживить ваши фото.\n\n"
        "Выберите услугу:", reply_markup=main_kb
    )

# --- Инструкция ---
@dp.message(F.text == "ℹ️ Инструкция")
async def instructions(m: Message, state: FSMContext):
    await state.clear()
    await m.answer(
        "📌 Как это работает:\n\n"
        "1️⃣ Выберите услугу или пакет.\n"
        "2️⃣ Оплатите (сейчас работает ТЕСТ режим — деньги не списываются).\n"
        "3️⃣ Загрузите фото.\n"
        "4️⃣ Получите готовый результат ✅",
        reply_markup=main_kb
    )

# --- Демо ---
@dp.message(F.text == "✨ Попробовать демо бесплатно")
async def demo_start(m: Message, state: FSMContext):
    await state.set_state(OrderState.waiting_demo_photo)
    await m.answer("Пришлите фото, я обработаю его и добавлю водяной знак 💧.")

@dp.message(OrderState.waiting_demo_photo, F.photo)
async def handle_demo(m: Message, state: FSMContext):
    file = await bot.get_file(m.photo[-1].file_id)
    photo_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"
    result_url = await process_replicate(photo_url, MODELS["restore"])
    if not result_url:
        await m.answer("⚠️ Ошибка при обработке.")
        return
    async with aiohttp.ClientSession() as session:
        async with session.get(result_url) as resp:
            img_bytes = await resp.read()
    marked = add_watermark(img_bytes, "DEMO")
    await bot.send_photo(m.chat.id, marked, caption="Это демо ✨ Оплатите услугу, чтобы получить результат без водяного знака.")
    await state.update_data(original_photo_url=photo_url)

# --- Универсальная функция оплаты (с заглушкой) ---
async def send_invoice(m: Message, service: str, title: str, desc: str):
    # Если режим TEST -> делаем заглушку
    if PAYMENT_PROVIDER_TOKEN == "TEST":
        await m.answer(f"💳 Оплата услуги «{title}» (ТЕСТ) прошла успешно ✅")
        fake_message = m
        fake_message.successful_payment = types.SuccessfulPayment(
            currency="RUB",
            total_amount=PRICES[service],
            invoice_payload=service,
            shipping_option_id=None,
            telegram_payment_charge_id="TEST",
            provider_payment_charge_id="TEST"
        )
        await payment_ok(fake_message, dp.fsm.get_context(bot, m.chat.id, m.from_user.id))
    else:
        prices = [LabeledPrice(label=title, amount=PRICES[service])]
        await bot.send_invoice(
            chat_id=m.chat.id,
            title=title,
            description=desc,
            provider_token=PAYMENT_PROVIDER_TOKEN,
            currency="RUB",
            prices=prices,
            payload=service
        )

# --- Хэндлеры услуг ---
@dp.message(F.text.startswith("🖼"))
async def pay_restore(m: Message): await send_invoice(m,"restore","Восстановление фото","Реставрация фото ИИ")

@dp.message(F.text.startswith("🎨"))
async def pay_colorize(m: Message): await send_invoice(m,"colorize","Раскрашивание фото","Раскрасим ч/б фото")

@dp.message(F.text.startswith("🔎"))
async def pay_upscale(m: Message): await send_invoice(m,"upscale","Апскейл","Повысим чёткость фото")

@dp.message(F.text.startswith("😊"))
async def pay_animate(m: Message): await send_invoice(m,"animate","Оживление лица","Сделаем анимацию лица")

@dp.message(F.text.startswith("📦 Пакет 3"))
async def pay_pack3(m: Message): await send_invoice(m,"pack3","Пакет 3 фото","Обработка трёх фото")

@dp.message(F.text.startswith("📦 Пакет 5"))
async def pay_pack5(m: Message): await send_invoice(m,"pack5","Пакет 5 фото","Обработка пяти фото")

# --- Pre-checkout (нужен только для реальной оплаты) ---
@dp.pre_checkout_query()
async def pcq(pre: types.PreCheckoutQuery):
    if PAYMENT_PROVIDER_TOKEN != "TEST":
        await bot.answer_pre_checkout_query(pre.id, ok=True)

# --- Обработка оплаты ---
@dp.message(F.successful_payment)
async def payment_ok(m: Message, state: FSMContext):
    service = m.successful_payment.invoice_payload
    data = await state.get_data()
    photo_url = data.get("original_photo_url")

    if photo_url:
        await m.answer("✅ Оплата прошла! Обрабатываю ваше фото...")
        result = await process_replicate(photo_url, MODELS.get(service, MODELS["restore"]))
        if not result:
            await m.answer("⚠️ Ошибка при обработке фото.")
            return
        if service == "animate":
            await m.answer_video(result, caption="😊 Вот оживлённое фото!")
        else:
            await m.answer_photo(result, caption="✅ Ваш результат готов!")
        await state.clear()
    else:
        await m.answer("✅ Оплата прошла! Теперь пришлите фото для обработки.")

# --- Healthcheck ---
async def handle_health(request): return web.Response(text="OK", status=200)
async def start_webserver():
    app = web.Application()
    app.router.add_get("/", handle_health)
    runner = web.AppRunner(app); await runner.setup()
    site = web.TCPSite(runner,"0.0.0.0",int(os.getenv("PORT",10000)))
    await site.start()

# --- Main ---
async def main():
    asyncio.create_task(start_webserver())
    await dp.start_polling(bot)

if __name__=="__main__":
    asyncio.run(main())
