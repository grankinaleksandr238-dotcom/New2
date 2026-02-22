#!/usr/bin/env python3
import asyncio
import logging
import os

from aiogram import executor
from aiogram.types import BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeAllGroupChats

from bot_instance import dp, bot
from utils.db import create_db_pool, init_db
from utils.background import start_background_tasks
from handlers import common, games, multiplayer, economy, groups, admin

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)

async def on_startup(dp):
    await create_db_pool()
    await init_db()

    await bot.set_my_commands(
        [BotCommand("start", "🚀 Запустить бота")],
        scope=BotCommandScopeAllPrivateChats()
    )
    await bot.set_my_commands(
        [
            BotCommand("fight", "⚔️ Атаковать банду"),
            BotCommand("smuggle", "📦 Отправиться в контрабанду"),
            BotCommand("activate_chat", "🔔 Активировать чат"),
            BotCommand("top", "🏆 Топ чата"),
            BotCommand("mlb_help", "📚 Помощь в группе"),
        ],
        scope=BotCommandScopeAllGroupChats()
    )
    logging.info("Бот запущен!")

async def on_shutdown(dp):
    if db_pool:
        await db_pool.close()
    logging.info("Бот остановлен, соединения закрыты.")

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.create_task(start_background_tasks())
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup, on_shutdown=on_shutdown)
