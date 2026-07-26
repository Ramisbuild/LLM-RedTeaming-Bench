import asyncio
import logging
import base64
import json
import aiohttp
import ssl
import certifi
import os
from typing import Dict, List
from dotenv import load_dotenv
from database import *

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, LabeledPrice, PreCheckoutQuery
from aiogram.utils.keyboard import ReplyKeyboardBuilder

# Загрузка переменных окружения из файла .env
load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Чтение конфигурации из .env (Production-ready подход)
BOT_TOKEN = os.getenv("BOT_TOKEN")
PAYMENT_PROVIDER_TOKEN = os.getenv("PAYMENT_PROVIDER_TOKEN")
SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT")

# Парсинг списка админов и ключей из .env
ADMIN_IDS = set(map(int, os.getenv("ADMIN_IDS", "").split(","))) if os.getenv("ADMIN_IDS") else set()
GOOGLE_API_KEYS = [k.strip() for k in os.getenv("GOOGLE_API_KEYS", "").split(",") if k.strip()]

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

current_key_index = 0


def get_next_api_key() -> str:
    """Функция поочередно возвращает ключи из списка (Round-Robin)"""
    global current_key_index
    if not GOOGLE_API_KEYS:
        raise ValueError("Список GOOGLE_API_KEYS пуст! Проверьте файл .env")

    key = GOOGLE_API_KEYS[current_key_index]
    current_key_index = (current_key_index + 1) % len(GOOGLE_API_KEYS)
    return key


# Создаем SSL контекст с правильными сертификатами
ssl_context = ssl.create_default_context(cafile=certifi.where())

# Хранилище данных сессий
user_sessions: Dict[int, bool] = {}
user_histories: Dict[int, List] = {}
thinking_messages: Dict[int, int] = {}


def get_main_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()

    if user_sessions.get(user_id, False):
        builder.add(KeyboardButton(text="🛑 Завершить диалог"))
    else:
        builder.add(KeyboardButton(text="💾 Запоминать диалог"))

    builder.add(KeyboardButton(text="🔄 Сбросить контекст"))
    builder.add(KeyboardButton(text="🖼️ Анализ фото"))
    builder.add(KeyboardButton(text="💳 Купить подписку"))

    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)


# ==========================================================
# ОБРАБОТКА ПЛАТЕЖЕЙ (PayMaster / Telegram Payments)
# ==========================================================

@dp.message(F.text == "💳 Купить подписку")
async def process_buy_subscription(message: types.Message):
    """Отправка инвойса на оплату подписки"""
    if not PAYMENT_PROVIDER_TOKEN:
        await message.answer("⚠️ Модуль оплаты временно недоступен.")
        return

    prices = [LabeledPrice(label="Премиум подписка (1 месяц)", amount=19900)]  # 199.00 RUB в копейках

    await bot.send_invoice(
        chat_id=message.chat.id,
        title="⭐ Премиум подписка DarkGPT",
        description="Неограниченное количество запросов к Dark-GPT на основе Gemini 3.1 Flash и приоритетная генерация!",
        provider_token=PAYMENT_PROVIDER_TOKEN,
        currency="RUB",
        prices=prices,
        start_parameter="darkgpt-subscription",
        payload="sub_premium_1month"
    )


@dp.pre_checkout_query()
async def process_pre_checkout_query(pre_checkout_query: PreCheckoutQuery):
    """Подтверждение готовности к совершению транзакции"""
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)


@dp.message(F.successful_payment)
async def process_successful_payment(message: types.Message):
    """Обработка успешной оплаты и выдача премиум-статуса"""
    user_id = message.from_user.id

    # Вызов функции базы данных для выдачи премиума
    try:
        set_premium(user_id, True)
    except Exception as e:
        logger.error(f"Ошибка при обновлении статуса в БД: {e}")

    await message.answer(
        "🎉 <b>Оплата прошла успешно!</b>\n\n"
        "Вам активирован <b>Премиум доступ</b>! Все лимиты на бесплатные запросы сняты.",
        parse_mode="HTML",
        reply_markup=get_main_keyboard(user_id)
    )


# ==========================================================
# ГЕНЕРАЦИЯ ОТВЕТОВ GEMINI (Google AI Studio)
# ==========================================================

async def generate_gemini_response(user_id: int, message: str, image_url: str = None) -> str:
    try:
        if user_id not in user_histories:
            user_histories[user_id] = []
            user_histories[user_id].append({"role": "system", "content": SYSTEM_PROMPT})

        if image_url:
            async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as img_session:
                async with img_session.get(image_url) as resp:
                    if resp.status != 200:
                        return "⚠️ Не удалось скачать изображение из Telegram."
                    image_bytes = await resp.read()

            content_type = resp.headers.get("Content-Type", "").lower()
            if not content_type.startswith("image/"):
                content_type = "image/jpeg"

            image_b64 = base64.b64encode(image_bytes).decode("utf-8")

            current_content = [
                {"type": "text", "text": message or "Опиши это изображение"},
                {"type": "image_url", "image_url": {"url": f"data:{content_type};base64,{image_b64}"}}
            ]
        else:
            current_content = message or "Продолжи диалог"

        if user_sessions.get(user_id, False):
            user_histories[user_id].append({"role": "user", "content": current_content})

        final_messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        if not user_sessions.get(user_id, False):
            final_messages.append({"role": "user", "content": current_content})
        else:
            for msg in user_histories[user_id]:
                final_messages.append({"role": msg["role"], "content": msg["content"]})

        connector = aiohttp.TCPConnector(ssl=ssl_context)
        last_error = None

        for _ in range(len(GOOGLE_API_KEYS)):
            api_key = get_next_api_key()

            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.post(
                        url="https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": "gemini-3.1-flash-lite",
                            "messages": final_messages,
                            "max_tokens": 1000
                        }
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        ai_response = data["choices"][0]["message"]["content"]
                        last_error = None
                        break
                    elif response.status == 429:
                        logger.warning("API-ключ исчерпал лимит, переключаюсь на следующий...")
                        continue
                    else:
                        try:
                            error_data = await response.json()
                        except Exception:
                            error_data = await response.text()
                        logger.error(error_data)
                        last_error = error_data
                        break
        else:
            return "⚠️ Все API-ключи временно исчерпали лимит. Попробуйте позже."

        if last_error:
            error_msg = last_error.get("error", {}).get("message", str(last_error)) if isinstance(last_error,
                                                                                                  dict) else str(
                last_error)
            return f"⚠️ Ошибка Google API: {error_msg}"

        if user_sessions.get(user_id, False):
            user_histories[user_id].append({"role": "assistant", "content": ai_response})

        return ai_response

    except Exception as e:
        logger.error(f"Ошибка при генерации ответа: {e}")
        return f"⚠️ Произошла внутренняя ошибка: {str(e)}"


# ==========================================================
# ОБРАБОТЧИКИ СООБЩЕНИЙ И МЕНЮ
# ==========================================================

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    add_user(user_id)
    welcome_text = (
        "🔬 <b>A Telegram bot-based platform for LLM red-teaming, safety evaluation, and alignment.</b>\n\n"
        "🤖 <i>Автоматизированный комплекс для аудита безопасности и стресс-тестирования языковых моделей (Google Gemini Architecture).</i>\n\n"
        "🎯 <b>Исследовательский функционал:</b>\n"
        "• 🧠 <b>Dual-Response Alignment Test:</b> Сравнительный анализ базовых ответов модели и необработанных генераций.\n"
        "• 🖼️ <b>Multimodal Vision Safety Audit:</b> Анализ визуальных данных и скрытых текстовых паттернов на фото.\n"
        "• 💻 <b>Code Security Analysis:</b> Поиск уязвимостей и аудит алгоритмов без фильтрации.\n"
        "• 🔄 <b>Dynamic Key Rotation:</b> Распределение нагрузки между пулом API-ключей (Round-Robin).\n\n"
        "⚡ <b>Особенности системы:</b>\n"
        "• <b>💾 Запоминать диалог</b> — активация контекстной сессии.\n"
        "• <b>🛑 Завершить диалог</b> — сброс фиксации истории.\n"
        "• <b>🔄 Сбросить контекст</b> — очистить контекстный буфер.\n"
        "• <b>🖼️ Анализ фото</b> — мультимодальный анализ визуальных объектов.\n\n"
        "💡 <b>Отправьте промпт или изображение для проведения теста безопасности!</b>"
    )

    await message.answer(
        welcome_text,
        reply_markup=get_main_keyboard(user_id),
        parse_mode='HTML'
    )

@dp.message(F.text == "💾 Запоминать диалог")
async def enable_memory(message: types.Message):
    user_id = message.from_user.id
    user_sessions[user_id] = True
    await message.answer("✅ <b>Режим запоминания диалога включен!</b>", reply_markup=get_main_keyboard(user_id),
                         parse_mode='HTML')


@dp.message(F.text == "🛑 Завершить диалог")
async def disable_memory(message: types.Message):
    user_id = message.from_user.id
    user_sessions[user_id] = False
    await message.answer("❌ <b>Режим запоминания диалога выключен.</b>", reply_markup=get_main_keyboard(user_id),
                         parse_mode='HTML')


@dp.message(F.text == "🔄 Сбросить контекст")
async def reset_context(message: types.Message):
    user_id = message.from_user.id
    if user_id in user_histories:
        user_histories[user_id] = []
    await message.answer("🧹 <b>Контекст диалога очищен!</b>", reply_markup=get_main_keyboard(user_id),
                         parse_mode='HTML')


@dp.message(F.text == "🖼️ Анализ фото")
async def analyze_photo_prompt(message: types.Message):
    await message.answer("📸 Отправьте мне фотографию для анализа")


@dp.message(F.photo)
async def handle_photo(message: types.Message):
    user_id = message.from_user.id
    thinking_msg = await message.answer("🤖 Анализирую изображение...")
    thinking_messages[user_id] = thinking_msg.message_id

    try:
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        image_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"

        ai_response = await generate_gemini_response(
            user_id=user_id,
            message="Что изображено на этой фотографии? Опиши подробно.",
            image_url=image_url
        )

        if user_id in thinking_messages:
            try:
                await bot.delete_message(user_id, thinking_messages[user_id])
            except Exception:
                pass
            finally:
                thinking_messages.pop(user_id, None)

        await message.answer(ai_response, reply_markup=get_main_keyboard(user_id))

    except Exception as e:
        logger.error(f"Ошибка обработки фото: {e}")
        await message.answer(f"⚠️ Ошибка при анализе изображения: {str(e)}")


@dp.message(F.text)
async def handle_text(message: types.Message):
    user_id = message.from_user.id

    if user_id not in ADMIN_IDS:
        add_user(user_id)
        user = get_user(user_id)
        free_requests = user[0]
        premium = user[1]

        if not premium:
            if free_requests <= 0:
                await message.answer(
                    "🎁 Ваши 3 бесплатных запроса закончились.\n\n"
                    "💎 Купите подписку, чтобы продолжить пользоваться ботом."
                )
                return

            use_request(user_id)
            free_requests -= 1
            await message.answer(f"🎁 Бесплатных запросов осталось: {free_requests}/3")

    if message.text in [
        "💾 Запоминать диалог",
        "🛑 Завершить диалог",
        "🔄 Сбросить контекст",
        "🖼️ Анализ фото",
        "💳 Купить подписку"
    ]:
        return

    thinking_msg = await message.answer("🤖 ИИ думает...")
    thinking_messages[user_id] = thinking_msg.message_id

    try:
        ai_response = await generate_gemini_response(user_id, message.text)

        if user_id in thinking_messages:
            try:
                await bot.delete_message(user_id, thinking_messages[user_id])
            except Exception:
                pass
            finally:
                thinking_messages.pop(user_id, None)

        if len(ai_response) > 4000:
            for i in range(0, len(ai_response), 4000):
                await message.answer(ai_response[i:i + 4000], reply_markup=get_main_keyboard(user_id))
        else:
            await message.answer(ai_response, reply_markup=get_main_keyboard(user_id))

    except Exception as e:
        logger.error(f"Ошибка обработки сообщения: {e}")

        if user_id in thinking_messages:
            try:
                await bot.delete_message(user_id, thinking_messages[user_id])
            except Exception:
                pass
            finally:
                thinking_messages.pop(user_id, None)

        await message.answer(f"⚠️ Ошибка: {str(e)}")


# ==========================================================
# ТОЧКА ВХОДА В ПРИЛОЖЕНИЕ
# ==========================================================

async def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не найден в файле .env!")
        return

    try:
        get_next_api_key()
    except ValueError as e:
        logger.error(e)
        return

    logger.info("Бот на пуле ключей Gemini 3.1 Flash запущен!")
    print("🤖 DarkGPT Bot запущен по методу ротации ключей!")
    print(f"🔑 Загружено работающих ключей из .env: {len(GOOGLE_API_KEYS)}")
    print("📞 Напишите /start в Telegram для начала общения")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())