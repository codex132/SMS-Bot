"""
language: Python 3.10+
file: bot.py
target: Telegram Bot — Free Virtual Number SMS OTP Bot
run: python bot.py
requires: pip install aiogram requests beautifulsoup4 phonenumbers aiohttp
"""

import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from scraper import NumberScraper
from monitor import SMSMonitor

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")  # set via Railway env var
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable not set")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scraper = NumberScraper()
monitor = SMSMonitor()

# ── cache refreshed every 30 mins ──
number_cache: dict[str, list[str]] = {}  # country_code → [numbers]
cache_lock = asyncio.Lock()


async def refresh_cache():
    """Background task — keeps number pool fresh."""
    global number_cache
    while True:
        logging.info("Refreshing number pool...")
        fresh = await asyncio.to_thread(scraper.scrape_all)
        async with cache_lock:
            number_cache = fresh
        logging.info(f"Pool updated: {sum(len(v) for v in fresh.values())} numbers across {len(fresh)} countries")
        await asyncio.sleep(1800)  # refresh every 30 minutes


# ── /start ──
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇺🇸 USA", callback_data="country_US"),
         InlineKeyboardButton(text="🇬🇧 UK", callback_data="country_GB")],
        [InlineKeyboardButton(text="🇨🇦 Canada", callback_data="country_CA"),
         InlineKeyboardButton(text="🇦🇺 Australia", callback_data="country_AU")],
        [InlineKeyboardButton(text="🇩🇪 Germany", callback_data="country_DE"),
         InlineKeyboardButton(text="🇫🇷 France", callback_data="country_FR")],
        [InlineKeyboardButton(text="🇸🇪 Sweden", callback_data="country_SE"),
         InlineKeyboardButton(text="🇵🇱 Poland", callback_data="country_PL")],
        [InlineKeyboardButton(text="🇳🇬 Nigeria", callback_data="country_NG"),
         InlineKeyboardButton(text="🇮🇳 India", callback_data="country_IN")],
        [InlineKeyboardButton(text="🇧🇷 Brazil", callback_data="country_BR"),
         InlineKeyboardButton(text="🇲🇽 Mexico", callback_data="country_MX")],
        [InlineKeyboardButton(text="🇷🇺 Russia", callback_data="country_RU"),
         InlineKeyboardButton(text="🇺🇦 Ukraine", callback_data="country_UA")],
        [InlineKeyboardButton(text="🇳🇱 Netherlands", callback_data="country_NL"),
         InlineKeyboardButton(text="🇧🇪 Belgium", callback_data="country_BE")],
        [InlineKeyboardButton(text="🇮🇩 Indonesia", callback_data="country_ID"),
         InlineKeyboardButton(text="🇵🇭 Philippines", callback_data="country_PH")],
        [InlineKeyboardButton(text="🇻🇳 Vietnam", callback_data="country_VN"),
         InlineKeyboardButton(text="🇹🇭 Thailand", callback_data="country_TH")],
        [InlineKeyboardButton(text="🇰🇪 Kenya", callback_data="country_KE"),
         InlineKeyboardButton(text="🇬🇭 Ghana", callback_data="country_GH")],
        [InlineKeyboardButton(text="🇿🇦 South Africa", callback_data="country_ZA"),
         InlineKeyboardButton(text="🇪🇹 Ethiopia", callback_data="country_ET")],
        [InlineKeyboardButton(text="🔄 Refresh Pool", callback_data="refresh")],
    ])
    await message.answer(
        "📱 *Free Virtual Number Bot*\n\n"
        "Get a temporary number to receive OTP codes.\n"
        "Pick a country to see available numbers:",
        parse_mode="Markdown",
        reply_markup=kb
         )


# ── /numbers — alias ──
@dp.message(Command("numbers"))
async def cmd_numbers(message: types.Message):
    await cmd_start(message)


# ── /status ──
@dp.message(Command("status"))
async def cmd_status(message: types.Message):
    async with cache_lock:
        total = sum(len(v) for v in number_cache.values())
        countries = len(number_cache)
    await message.answer(
        f"📊 *Pool Status*\n\n"
        f"Numbers available: `{total}`\n"
        f"Countries covered: `{countries}`\n"
        f"Refresh cycle: every 30 minutes",
        parse_mode="Markdown"
    )


# ── country button ──
@dp.callback_query(lambda c: c.data.startswith("country_"))
async def pick_country(callback: types.CallbackQuery):
    code = callback.data.split("_")[1]
    async with cache_lock:
        nums = number_cache.get(code, [])

    if not nums:
        await callback.message.answer(
            f"⚠️ No numbers available for `{code}` right now.\n"
            f"Try another country or tap Refresh Pool.",
            parse_mode="Markdown"
        )
        await callback.answer()
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"📲 {n}",
            callback_data=f"use_{n}"
        )] for n in nums[:10]  # cap display at 10
    ])
    await callback.message.answer(
        f"📋 *Available numbers — {code}*\nTap a number to monitor for incoming SMS:",
        parse_mode="Markdown",
        reply_markup=kb
    )
    await callback.answer()


# ── number selected — start monitoring ──
@dp.callback_query(lambda c: c.data.startswith("use_"))
async def use_number(callback: types.CallbackQuery):
    number = callback.data[4:]
    user_id = callback.from_user.id

    await callback.message.answer(
        f"🔍 Monitoring `{number}` for incoming SMS...\n"
        f"Timeout: 10 minutes. I'll notify you when an OTP arrives.",
        parse_mode="Markdown"
    )
    await callback.answer()

    # spawn monitor task
    asyncio.create_task(
        watch_number(user_id, number, callback.message.chat.id)
    )


async def watch_number(user_id: int, number: str, chat_id: int):
    """Poll for new SMS on the given number, deliver to user."""
    result = await asyncio.to_thread(monitor.wait_for_sms, number, timeout=600)
    if result:
        await bot.send_message(
            chat_id,
            f"✅ *SMS received on* `{number}`\n\n"
            f"📩 *From:* `{result['sender']}`\n"
            f"💬 *Message:* `{result['text']}`",
            parse_mode="Markdown"
        )
    else:
        await bot.send_message(
            chat_id,
            f"⏱ *Timeout* — no SMS arrived on `{number}` within 10 minutes.\n"
            f"Try a different number.",
            parse_mode="Markdown"
        )


# ── refresh button ──
@dp.callback_query(lambda c: c.data == "refresh")
async def manual_refresh(callback: types.CallbackQuery):
    await callback.message.answer("🔄 Refreshing pool, give it 20-30 seconds...")
    fresh = await asyncio.to_thread(scraper.scrape_all)
    async with cache_lock:
        global number_cache
        number_cache = fresh
    total = sum(len(v) for v in fresh.values())
    await callback.message.answer(f"✅ Pool refreshed — `{total}` numbers loaded.")
    await callback.answer()


async def main():
    asyncio.create_task(refresh_cache())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
