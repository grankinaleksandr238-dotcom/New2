import asyncio
import logging
import random
import html
from datetime import datetime, timedelta
from typing import List, Tuple, Optional, Dict, Any

from aiogram import types
from aiogram.utils.exceptions import (
    BotBlocked, UserDeactivated, ChatNotFound, RetryAfter, TelegramAPIError
)

from bot_instance import bot
from utils.db import (
    db_pool, get_setting, get_setting_int, get_setting_float,
    get_confirmed_chats, get_media_file_id
)

async def safe_send_message(user_id: int, text: str, **kwargs):
    if kwargs.get('parse_mode') == 'HTML':
        text = html.escape(text)
    try:
        await bot.send_message(user_id, text, **kwargs)
    except BotBlocked:
        logging.warning(f"Bot blocked by user {user_id}")
    except UserDeactivated:
        logging.warning(f"User {user_id} deactivated")
    except ChatNotFound:
        logging.warning(f"Chat {user_id} not found")
    except RetryAfter as e:
        logging.warning(f"Flood limit exceeded. Retry after {e.timeout} seconds")
        await asyncio.sleep(e.timeout)
        try:
            await bot.send_message(user_id, text, **kwargs)
        except Exception as ex:
            logging.warning(f"Still failed after retry: {ex}")
    except TelegramAPIError as e:
        logging.warning(f"Telegram API error for user {user_id}: {e}")
    except Exception as e:
        logging.warning(f"Failed to send message to {user_id}: {e}")

def safe_send_message_task(user_id: int, text: str, **kwargs):
    asyncio.create_task(safe_send_message(user_id, text, **kwargs))

async def safe_send_chat(chat_id: int, text: str, **kwargs):
    try:
        await bot.send_message(chat_id, text, **kwargs)
    except Exception as e:
        logging.error(f"Failed to send to chat {chat_id}: {e}")

async def can_delete_message(chat_id: int, message: types.Message) -> bool:
    try:
        if chat_id > 0:
            return message.from_user.id == bot.id
        else:
            member = await bot.get_chat_member(chat_id, bot.id)
            return member.status in ['administrator', 'creator']
    except:
        return False

async def delete_after(message: types.Message, seconds: int):
    await asyncio.sleep(seconds)
    if await can_delete_message(message.chat.id, message):
        try:
            await message.delete()
        except Exception:
            pass

async def auto_delete_reply(message: types.Message, text: str, delete_seconds: int = None, **kwargs):
    if delete_seconds is None:
        delete_seconds = int(await get_setting("auto_delete_commands_seconds"))
    sent = await message.reply(text, **kwargs)
    if message.chat.type != 'private':
        confirmed = await get_confirmed_chats()
        chat_data = confirmed.get(message.chat.id)
        if chat_data and not chat_data.get('auto_delete_enabled', True):
            return
    asyncio.create_task(delete_after(sent, delete_seconds))

async def auto_delete_message(message: types.Message, delete_seconds: int = None):
    if message.chat.type == 'private':
        return
    if delete_seconds is None:
        delete_seconds = int(await get_setting("auto_delete_commands_seconds"))
    confirmed = await get_confirmed_chats()
    chat_data = confirmed.get(message.chat.id)
    if chat_data and not chat_data.get('auto_delete_enabled', True):
        return
    asyncio.create_task(delete_after(message, delete_seconds))

def progress_bar(current: int, total: int, length: int = 10) -> str:
    if total <= 0:
        return "⬜" * length
    filled = int(current / total * length)
    return "🟩" * filled + "⬜" * (length - filled)

def format_time_remaining(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} сек"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} мин"
    hours = minutes // 60
    minutes %= 60
    if minutes == 0:
        return f"{hours} ч"
    return f"{hours} ч {minutes} мин"

def get_random_phrase(phrase_list: List[str], **kwargs) -> str:
    phrase = random.choice(phrase_list)
    return phrase.format(**kwargs)

async def notify_chats(message_text: str):
    confirmed = await get_confirmed_chats()
    for chat_id, data in confirmed.items():
        if not data.get('notify_enabled', True):
            continue
        await safe_send_chat(chat_id, message_text)

async def is_banned(user_id: int) -> bool:
    async with db_pool.acquire() as conn:
        row = await conn.fetchval("SELECT user_id FROM banned_users WHERE user_id=$1", user_id)
    return row is not None

async def find_user_by_input(input_str: str) -> Optional[Dict]:
    input_str = input_str.strip()
    try:
        uid = int(input_str)
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM users WHERE user_id=$1", uid)
            return dict(row) if row else None
    except ValueError:
        username = input_str.lower()
        if username.startswith('@'):
            username = username[1:]
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM users WHERE LOWER(username)=$1", username)
            return dict(row) if row else None

async def send_with_media(chat_id: int, text: str, media_key: str = None, **kwargs):
    if media_key:
        try:
            file_id = await get_media_file_id(media_key)
            if file_id:
                await bot.send_photo(chat_id, file_id, caption=text, **kwargs)
                return
            else:
                logging.warning(f"Media key '{media_key}' not found in database")
        except Exception as e:
            logging.error(f"Ошибка отправки фото с ключом {media_key}: {e}", exc_info=True)
