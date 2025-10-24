\
import asyncio
import os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import FSInputFile
from dotenv import load_dotenv
from sources import build_rich_list
from utils import chunked, format_btc, to_csv_bytes

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise SystemExit("Please set TELEGRAM_BOT_TOKEN in .env")

dp = Dispatcher()
bot = Bot(token=TOKEN, parse_mode="HTML")

def format_rows_for_message(rows):
    lines = []
    for rank, (addr, sats) in enumerate(rows, start=1):
        lines.append(f"{rank:>3}. <code>{addr}</code> — <b>{format_btc(sats)}</b> BTC")
    return "\n".join(lines)

@dp.message(Command(commands=["start", "help"]))
async def help_cmd(message: types.Message):
    text = (
        "Привет! Я бот, который показывает <b>актуальный Топ-200 BTC адресов</b> по балансу.\n\n"
        "Команды:\n"
        "• /top200btc — собрать и показать топ-200 прямо сейчас\n"
        "• /csv — прислать CSV-файл с текущим топ-200\n"
    )
    await message.answer(text)

@dp.message(Command(commands=["top200btc"]))
async def top200_cmd(message: types.Message):
    await message.answer("Собираю данные из нескольких источников и обновляю балансы… Это может занять 1–3 минуты.")
    try:
        pairs = await build_rich_list(limit=200)  # [(address, sats), ...]
        # format and send in chunks (Telegram limit ~4096 chars)
        # Make display tuples: (addr, sats)
        # Chunk by 25 entries per message, roughly
        for part in chunked(pairs, 25):
            msg_text = format_rows_for_message(part)
            await message.answer(msg_text)
        await message.answer("Готово ✅")
    except Exception as e:
        await message.answer(f"Ошибка: {e}")

@dp.message(Command(commands=["csv"]))
async def csv_cmd(message: types.Message):
    await message.answer("Готовлю CSV…")
    try:
        pairs = await build_rich_list(limit=200)
        rows = list(enumerate(pairs, start=1))  # [(rank, (addr, sats))...]
        csv_bytes = to_csv_bytes([(r, a, s) for r, (a, s) in rows])
        path = "/mnt/data/top200_btc.csv"
        with open(path, "wb") as f:
            f.write(csv_bytes)
        await message.answer_document(FSInputFile(path, filename="top200_btc.csv"), caption="Текущий топ-200 BTC адресов")
    except Exception as e:
        await message.answer(f"Ошибка: {e}")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
