from functools import wraps
from aiogram import types
from db import is_banned, is_admin, has_permission

def check_ban():
    def decorator(func):
        @wraps(func)
        async def wrapper(message: types.Message, *args, **kwargs):
            if message.chat.type != 'private':
                return await func(message, *args, **kwargs)
            if await is_banned(message.from_user.id) and not await is_admin(message.from_user.id):
                await message.answer("⛔ Вы заблокированы в боте.")
                return
            return await func(message, *args, **kwargs)
        return wrapper
    return decorator

def admin_only():
    def decorator(func):
        @wraps(func)
        async def wrapper(message: types.Message, *args, **kwargs):
            if not await is_admin(message.from_user.id):
                await message.answer("❌ У вас нет прав администратора.")
                return
            return await func(message, *args, **kwargs)
        return wrapper
    return decorator

def permission_required(permission: str):
    def decorator(func):
        @wraps(func)
        async def wrapper(message: types.Message, *args, **kwargs):
            if not await has_permission(message.from_user.id, permission):
                await message.answer("❌ Недостаточно прав.")
                return
            return await func(message, *args, **kwargs)
        return wrapper
    return decorator
