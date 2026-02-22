import asyncio
import logging
import json
import io
import csv
from datetime import datetime, timedelta

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import asyncpg

from bot_instance import dp, bot
from db import (
    db_pool, is_admin, is_super_admin, is_junior_admin, has_permission,
    get_admin_permissions, update_admin_permissions,
    ensure_user_exists, is_banned, get_user_balance, update_user_balance,
    get_user_reputation, update_user_reputation, get_user_bitcoin,
    update_user_bitcoin, get_user_authority, update_user_authority,
    get_user_level, add_exp, find_user_by_input, get_setting, set_setting,
    get_setting_int, get_setting_float, get_channels, add_confirmed_chat,
    remove_confirmed_chat, get_confirmed_chats, get_pending_chat_requests,
    update_chat_request_status, create_chat_confirmation_request,
    get_business_type_list, get_business_type, get_user_businesses,
    create_user_business, update_business_income, collect_business_income,
    upgrade_business, get_order_book, get_active_orders, create_bitcoin_order,
    cancel_bitcoin_order, match_orders, get_media_file_id,
    perform_cleanup, export_users_to_csv, export_table_to_csv,
    spawn_boss
)
from helpers import (
    safe_send_message, send_with_media, auto_delete_reply, auto_delete_message,
    get_random_phrase, notify_chats, format_time_remaining, progress_bar
)
from constants import (
    PERMISSIONS_LIST, DEFAULT_SETTINGS, ITEMS_PER_PAGE, SUPER_ADMINS
)
from keyboards import (
    admin_main_keyboard, admin_users_keyboard, admin_shop_keyboard,
    admin_giveaway_keyboard, admin_channel_keyboard, admin_promo_keyboard,
    admin_tasks_keyboard, admin_ban_keyboard, admin_admins_keyboard,
    admin_chats_keyboard, admin_boss_keyboard, admin_auction_keyboard,
    admin_ad_keyboard, admin_exchange_keyboard, admin_business_keyboard,
    admin_media_keyboard, settings_categories_keyboard, settings_param_keyboard,
    purchase_action_keyboard, back_keyboard, cancel_keyboard
)
from states import (
    AddBalance, RemoveBalance, AddReputation, RemoveReputation,
    AddExp, SetLevel, AddBitcoin, RemoveBitcoin, AddAuthority, RemoveAuthority,
    FindUser, AddShopItem, RemoveShopItem, EditShopItem,
    CreatePromocode, AddChannel, RemoveChannel, CreateGiveaway, CompleteGiveaway,
    CreateTask, DeleteTask, BlockUser, UnblockUser,
    AddJuniorAdmin, EditAdminPermissions, RemoveJuniorAdmin,
    ManageChats, BossSpawn, DeleteBoss, CreateAuction, CancelAuction,
    CreateAd, EditAd, DeleteAd, CancelBitcoinOrder,
    AddBusiness, EditBusiness, ToggleBusiness, AddMedia, RemoveMedia,
    EditSettings, Broadcast
)

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
async def check_admin_permissions(user_id: int, permission: str) -> bool:
    return await has_permission(user_id, permission)

# ==================== ГЛАВНОЕ МЕНЮ АДМИНКИ ====================
@dp.message_handler(lambda message: message.text == "⚙️ Админ панель")
async def admin_panel(message: types.Message):
    if message.chat.type != 'private':
        return
    if not await is_admin(message.from_user.id):
        await message.answer("У тебя нет прав администратора.")
        return
    permissions = await get_admin_permissions(message.from_user.id)
    await send_with_media(message.chat.id, "Панель администратора:", media_key='admin', reply_markup=admin_main_keyboard(permissions))

@dp.message_handler(lambda message: message.text == "◀️ Назад в админку")
async def back_to_admin(message: types.Message):
    if message.chat.type != 'private':
        return
    if not await is_admin(message.from_user.id):
        return
    permissions = await get_admin_permissions(message.from_user.id)
    await send_with_media(message.chat.id, "Панель администратора:", media_key='admin', reply_markup=admin_main_keyboard(permissions))

# ==================== УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ ====================
@dp.message_handler(lambda message: message.text == "👥 Пользователи")
async def admin_users_menu(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_users"):
        await message.answer("❌ Недостаточно прав.")
        return
    await send_with_media(message.chat.id, "Управление пользователями:", media_key='admin_users', reply_markup=admin_users_keyboard())

# ----- Начисление баксов -----
@dp.message_handler(lambda message: message.text == "💰 Начислить баксы")
async def add_balance_start(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_users"):
        await message.answer("❌ Недостаточно прав.")
        return
    await message.answer("Введи ID или @username пользователя:", reply_markup=back_keyboard())
    await AddBalance.user_id.set()

@dp.message_handler(state=AddBalance.user_id)
async def add_balance_user(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_users_menu(message)
        return
    user_data = await find_user_by_input(message.text)
    if not user_data:
        await message.answer("❌ Пользователь не найден.")
        return
    uid = user_data['user_id']
    await state.update_data(user_id=uid)
    await message.answer("Введи сумму начисления (можно дробную, например 10.50):")
    await AddBalance.amount.set()

@dp.message_handler(state=AddBalance.amount)
async def add_balance_amount(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_users_menu(message)
        return
    try:
        amount = float(message.text)
        if amount <= 0:
            raise ValueError
        amount = round(amount, 2)
        max_input = await get_setting_float("max_input_number")
        if amount > max_input:
            await message.answer(f"❌ Сумма слишком большая (максимум {max_input:.2f}).")
            return
    except ValueError:
        await message.answer("❌ Введи положительное число с точностью до сотых.")
        return
    data = await state.get_data()
    uid = data['user_id']
    try:
        await update_user_balance(uid, amount)
        await message.answer(f"✅ Пользователю {uid} начислено {amount:.2f} баксов.")
        await safe_send_message(uid, f"💰 Вам начислено {amount:.2f} баксов администратором.")
    except Exception as e:
        logging.error(f"Add balance error: {e}", exc_info=True)
        await message.answer("❌ Ошибка.")
    await state.finish()

# ----- Списание баксов -----
@dp.message_handler(lambda message: message.text == "💸 Списать баксы")
async def remove_balance_start(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_users"):
        await message.answer("❌ Недостаточно прав.")
        return
    await message.answer("Введи ID или @username пользователя:", reply_markup=back_keyboard())
    await RemoveBalance.user_id.set()

@dp.message_handler(state=RemoveBalance.user_id)
async def remove_balance_user(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_users_menu(message)
        return
    user_data = await find_user_by_input(message.text)
    if not user_data:
        await message.answer("❌ Пользователь не найден.")
        return
    uid = user_data['user_id']
    await state.update_data(user_id=uid)
    await message.answer("Введи сумму списания (можно дробную):")
    await RemoveBalance.amount.set()

@dp.message_handler(state=RemoveBalance.amount)
async def remove_balance_amount(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_users_menu(message)
        return
    try:
        amount = float(message.text)
        if amount <= 0:
            raise ValueError
        amount = round(amount, 2)
        max_input = await get_setting_float("max_input_number")
        if amount > max_input:
            await message.answer(f"❌ Сумма слишком большая (максимум {max_input:.2f}).")
            return
    except ValueError:
        await message.answer("❌ Введи положительное число.")
        return
    data = await state.get_data()
    uid = data['user_id']
    try:
        await update_user_balance(uid, -amount)
        await message.answer(f"✅ У пользователя {uid} списано {amount:.2f} баксов.")
        await safe_send_message(uid, f"💸 У вас списано {amount:.2f} баксов администратором.")
    except Exception as e:
        logging.error(f"Remove balance error: {e}", exc_info=True)
        await message.answer("❌ Ошибка.")
    await state.finish()

# ----- Начисление репутации -----
@dp.message_handler(lambda message: message.text == "⭐️ Начислить репутацию")
async def add_reputation_start(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_users"):
        await message.answer("❌ Недостаточно прав.")
        return
    await message.answer("Введи ID или @username пользователя:", reply_markup=back_keyboard())
    await AddReputation.user_id.set()

@dp.message_handler(state=AddReputation.user_id)
async def add_reputation_user(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_users_menu(message)
        return
    user_data = await find_user_by_input(message.text)
    if not user_data:
        await message.answer("❌ Пользователь не найден.")
        return
    uid = user_data['user_id']
    await state.update_data(user_id=uid)
    await message.answer("Введи количество репутации для начисления (целое число):")
    await AddReputation.amount.set()

@dp.message_handler(state=AddReputation.amount)
async def add_reputation_amount(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_users_menu(message)
        return
    try:
        amount = int(message.text)
    except ValueError:
        await message.answer("❌ Введи целое число.")
        return
    data = await state.get_data()
    uid = data['user_id']
    try:
        await update_user_reputation(uid, amount)
        await message.answer(f"✅ Пользователю {uid} начислено {amount} репутации.")
        await safe_send_message(uid, f"⭐️ Вам начислено {amount} репутации администратором.")
    except Exception as e:
        logging.error(f"Add reputation error: {e}", exc_info=True)
        await message.answer("❌ Ошибка.")
    await state.finish()
  # ----- Снятие репутации -----
@dp.message_handler(lambda message: message.text == "🔻 Снять репутацию")
async def remove_reputation_start(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_users"):
        await message.answer("❌ Недостаточно прав.")
        return
    await message.answer("Введи ID или @username пользователя:", reply_markup=back_keyboard())
    await RemoveReputation.user_id.set()

@dp.message_handler(state=RemoveReputation.user_id)
async def remove_reputation_user(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_users_menu(message)
        return
    user_data = await find_user_by_input(message.text)
    if not user_data:
        await message.answer("❌ Пользователь не найден.")
        return
    uid = user_data['user_id']
    await state.update_data(user_id=uid)
    await message.answer("Введи количество репутации для снятия (целое число):")
    await RemoveReputation.amount.set()

@dp.message_handler(state=RemoveReputation.amount)
async def remove_reputation_amount(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_users_menu(message)
        return
    try:
        amount = int(message.text)
    except ValueError:
        await message.answer("❌ Введи целое число.")
        return
    data = await state.get_data()
    uid = data['user_id']
    try:
        await update_user_reputation(uid, -amount)
        await message.answer(f"✅ У пользователя {uid} снято {amount} репутации.")
        await safe_send_message(uid, f"🔻 У вас снято {amount} репутации администратором.")
    except Exception as e:
        logging.error(f"Remove reputation error: {e}", exc_info=True)
        await message.answer("❌ Ошибка.")
    await state.finish()

# ----- Начисление опыта -----
@dp.message_handler(lambda message: message.text == "📈 Начислить опыт")
async def add_exp_start(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_users"):
        await message.answer("❌ Недостаточно прав.")
        return
    await message.answer("Введи ID или @username пользователя:", reply_markup=back_keyboard())
    await AddExp.user_id.set()

@dp.message_handler(state=AddExp.user_id)
async def add_exp_user(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_users_menu(message)
        return
    user_data = await find_user_by_input(message.text)
    if not user_data:
        await message.answer("❌ Пользователь не найден.")
        return
    uid = user_data['user_id']
    await state.update_data(user_id=uid)
    await message.answer("Введи количество опыта для начисления (целое число):")
    await AddExp.amount.set()

@dp.message_handler(state=AddExp.amount)
async def add_exp_amount(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_users_menu(message)
        return
    try:
        amount = int(message.text)
    except ValueError:
        await message.answer("❌ Введи целое число.")
        return
    data = await state.get_data()
    uid = data['user_id']
    try:
        await add_exp(uid, amount)
        await message.answer(f"✅ Пользователю {uid} начислено {amount} опыта.")
    except Exception as e:
        logging.error(f"Add exp error: {e}", exc_info=True)
        await message.answer("❌ Ошибка.")
    await state.finish()

# ----- Установка уровня -----
@dp.message_handler(lambda message: message.text == "🔝 Установить уровень")
async def set_level_start(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_users"):
        await message.answer("❌ Недостаточно прав.")
        return
    await message.answer("Введи ID или @username пользователя:", reply_markup=back_keyboard())
    await SetLevel.user_id.set()

@dp.message_handler(state=SetLevel.user_id)
async def set_level_user(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_users_menu(message)
        return
    user_data = await find_user_by_input(message.text)
    if not user_data:
        await message.answer("❌ Пользователь не найден.")
        return
    uid = user_data['user_id']
    await state.update_data(user_id=uid)
    await message.answer("Введи новый уровень (целое число ≥ 1):")
    await SetLevel.level.set()

@dp.message_handler(state=SetLevel.level)
async def set_level_value(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_users_menu(message)
        return
    try:
        level = int(message.text)
        if level < 1:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи целое число ≥ 1.")
        return
    data = await state.get_data()
    uid = data['user_id']
    try:
        async with db_pool.acquire() as conn:
            await conn.execute("UPDATE users SET level=$1 WHERE user_id=$2", level, uid)
        await message.answer(f"✅ Пользователю {uid} установлен уровень {level}.")
        await safe_send_message(uid, f"🔝 Ваш уровень изменён на {level} администратором.")
    except Exception as e:
        logging.error(f"Set level error: {e}", exc_info=True)
        await message.answer("❌ Ошибка.")
    await state.finish()

# ----- Начисление биткоинов -----
@dp.message_handler(lambda message: message.text == "₿ Начислить биткоины")
async def add_bitcoin_start(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_users"):
        await message.answer("❌ Недостаточно прав.")
        return
    await message.answer("Введи ID или @username пользователя:", reply_markup=back_keyboard())
    await AddBitcoin.user_id.set()

@dp.message_handler(state=AddBitcoin.user_id)
async def add_bitcoin_user(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_users_menu(message)
        return
    user_data = await find_user_by_input(message.text)
    if not user_data:
        await message.answer("❌ Пользователь не найден.")
        return
    uid = user_data['user_id']
    await state.update_data(user_id=uid)
    await message.answer("Введи количество биткоинов (можно дробное, например 1.5):")
    await AddBitcoin.amount.set()

@dp.message_handler(state=AddBitcoin.amount)
async def add_bitcoin_amount(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_users_menu(message)
        return
    try:
        amount = float(message.text)
        if amount <= 0:
            raise ValueError
        amount = round(amount, 4)
        max_input = await get_setting_float("max_input_number")
        if amount > max_input:
            await message.answer(f"❌ Сумма слишком большая (максимум {max_input:.4f}).")
            return
    except ValueError:
        await message.answer("❌ Введи положительное число (можно дробное).")
        return
    data = await state.get_data()
    uid = data['user_id']
    try:
        await update_user_bitcoin(uid, amount)
        await message.answer(f"✅ Пользователю {uid} начислено {amount:.4f} BTC.")
        await safe_send_message(uid, f"₿ Вам начислено {amount:.4f} BTC администратором.")
    except Exception as e:
        logging.error(f"Add bitcoin error: {e}", exc_info=True)
        await message.answer("❌ Ошибка.")
    await state.finish()

# ----- Списание биткоинов -----
@dp.message_handler(lambda message: message.text == "₿ Списать биткоины")
async def remove_bitcoin_start(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_users"):
        await message.answer("❌ Недостаточно прав.")
        return
    await message.answer("Введи ID или @username пользователя:", reply_markup=back_keyboard())
    await RemoveBitcoin.user_id.set()

@dp.message_handler(state=RemoveBitcoin.user_id)
async def remove_bitcoin_user(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_users_menu(message)
        return
    user_data = await find_user_by_input(message.text)
    if not user_data:
        await message.answer("❌ Пользователь не найден.")
        return
    uid = user_data['user_id']
    await state.update_data(user_id=uid)
    await message.answer("Введи количество биткоинов для списания:")
    await RemoveBitcoin.amount.set()

@dp.message_handler(state=RemoveBitcoin.amount)
async def remove_bitcoin_amount(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_users_menu(message)
        return
    try:
        amount = float(message.text)
        if amount <= 0:
            raise ValueError
        amount = round(amount, 4)
        max_input = await get_setting_float("max_input_number")
        if amount > max_input:
            await message.answer(f"❌ Сумма слишком большая (максимум {max_input:.4f}).")
            return
    except ValueError:
        await message.answer("❌ Введи положительное число.")
        return
    data = await state.get_data()
    uid = data['user_id']
    try:
        await update_user_bitcoin(uid, -amount)
        await message.answer(f"✅ У пользователя {uid} списано {amount:.4f} BTC.")
        await safe_send_message(uid, f"₿ У вас списано {amount:.4f} BTC администратором.")
    except Exception as e:
        logging.error(f"Remove bitcoin error: {e}", exc_info=True)
        await message.answer("❌ Ошибка.")
    await state.finish()

# ----- Начисление авторитета -----
@dp.message_handler(lambda message: message.text == "⚔️ Начислить авторитет")
async def add_authority_start(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_users"):
        await message.answer("❌ Недостаточно прав.")
        return
    await message.answer("Введи ID или @username пользователя:", reply_markup=back_keyboard())
    await AddAuthority.user_id.set()

@dp.message_handler(state=AddAuthority.user_id)
async def add_authority_user(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_users_menu(message)
        return
    user_data = await find_user_by_input(message.text)
    if not user_data:
        await message.answer("❌ Пользователь не найден.")
        return
    uid = user_data['user_id']
    await state.update_data(user_id=uid)
    await message.answer("Введи количество авторитета (целое число):")
    await AddAuthority.amount.set()

@dp.message_handler(state=AddAuthority.amount)
async def add_authority_amount(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_users_menu(message)
        return
    try:
        amount = int(message.text)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи положительное целое число.")
        return
    data = await state.get_data()
    uid = data['user_id']
    try:
        await update_user_authority(uid, amount)
        await message.answer(f"✅ Пользователю {uid} начислено {amount} авторитета.")
        await safe_send_message(uid, f"⚔️ Вам начислено {amount} авторитета администратором.")
    except Exception as e:
        logging.error(f"Add authority error: {e}", exc_info=True)
        await message.answer("❌ Ошибка.")
    await state.finish()

# ----- Списание авторитета -----
@dp.message_handler(lambda message: message.text == "⚔️ Списать авторитет")
async def remove_authority_start(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_users"):
        await message.answer("❌ Недостаточно прав.")
        return
    await message.answer("Введи ID или @username пользователя:", reply_markup=back_keyboard())
    await RemoveAuthority.user_id.set()

@dp.message_handler(state=RemoveAuthority.user_id)
async def remove_authority_user(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_users_menu(message)
        return
    user_data = await find_user_by_input(message.text)
    if not user_data:
        await message.answer("❌ Пользователь не найден.")
        return
    uid = user_data['user_id']
    await state.update_data(user_id=uid)
    await message.answer("Введи количество авторитета для снятия:")
    await RemoveAuthority.amount.set()

@dp.message_handler(state=RemoveAuthority.amount)
async def remove_authority_amount(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_users_menu(message)
        return
    try:
        amount = int(message.text)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи положительное целое число.")
        return
    data = await state.get_data()
    uid = data['user_id']
    try:
        await update_user_authority(uid, -amount)
        await message.answer(f"✅ У пользователя {uid} снято {amount} авторитета.")
        await safe_send_message(uid, f"⚔️ У вас снято {amount} авторитета администратором.")
    except Exception as e:
        logging.error(f"Remove authority error: {e}", exc_info=True)
        await message.answer("❌ Ошибка.")
    await state.finish()
  # ----- Поиск пользователя -----
@dp.message_handler(lambda message: message.text == "👥 Найти пользователя")
async def find_user_start(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_users"):
        await message.answer("❌ Недостаточно прав.")
        return
    await message.answer("Введи ID или @username пользователя:", reply_markup=back_keyboard())
    await FindUser.query.set()

@dp.message_handler(state=FindUser.query)
async def find_user_result(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        permissions = await get_admin_permissions(message.from_user.id)
        await message.answer("Панель администратора:", reply_markup=admin_main_keyboard(permissions))
        return
    user_data = await find_user_by_input(message.text)
    if not user_data:
        await message.answer("❌ Пользователь не найден.")
        return
    uid = user_data['user_id']
    name = user_data['first_name']
    bal = float(user_data['balance'])
    rep = user_data['reputation']
    spent = float(user_data['total_spent'])
    joined = user_data['joined_date']
    attempts = user_data['theft_attempts']
    success = user_data['theft_success']
    failed = user_data['theft_failed']
    protected = user_data['theft_protected']
    level = user_data['level']
    exp = user_data['exp']
    strength = user_data['strength']
    agility = user_data['agility']
    defense = user_data['defense']
    bitcoin = float(user_data['bitcoin_balance']) if user_data['bitcoin_balance'] is not None else 0.0
    authority = user_data['authority_balance'] or 0
    smuggle_success = user_data.get('smuggle_success', 0)
    smuggle_fail = user_data.get('smuggle_fail', 0)
    banned = await is_banned(uid)
    ban_status = "⛔ Заблокирован" if banned else "✅ Активен"
    text = (
        f"👤 Пользователь: {name} (ID: {uid})\n"
        f"📊 Уровень: {level}, опыт: {exp}\n"
        f"💪 Сила: {strength} | 🏃 Ловкость: {agility} | 🛡 Защита: {defense}\n"
        f"💰 Баланс: {bal:.2f} баксов\n"
        f"₿ Биткоины: {bitcoin:.4f} BTC\n"
        f"⚔️ Авторитет: {authority}\n"
        f"⭐️ Репутация: {rep}\n"
        f"💸 Потрачено: {spent:.2f} баксов\n"
        f"📅 Регистрация: {joined}\n"
        f"🔫 Ограблений: {attempts} (успешно: {success}, провал: {failed})\n"
        f"🛡 Отбито атак: {protected}\n"
        f"📦 Контрабанда: успешно {smuggle_success}, провал {smuggle_fail}\n"
        f"Статус: {ban_status}"
    )
    await message.answer(text)
    await state.finish()

# ----- Экспорт пользователей -----
@dp.message_handler(lambda message: message.text == "📊 Экспорт пользователей")
async def export_users(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_users"):
        return
    try:
        csv_data = await export_users_to_csv()
        if not csv_data:
            await message.answer("Нет пользователей для экспорта.")
            return
        await message.answer_document(
            types.InputFile(io.BytesIO(csv_data), filename="users.csv"),
            caption="📊 Список пользователей"
        )
    except Exception as e:
        logging.error(f"Export error: {e}", exc_info=True)
        await message.answer("❌ Ошибка при экспорте.")

# ==================== УПРАВЛЕНИЕ МАГАЗИНОМ ====================
@dp.message_handler(lambda message: message.text == "🛒 Магазин")
async def admin_shop_menu(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_shop"):
        await message.answer("❌ Недостаточно прав.")
        return
    await send_with_media(message.chat.id, "Управление магазином:", media_key='admin_shop', reply_markup=admin_shop_keyboard())

@dp.message_handler(lambda message: message.text == "➕ Добавить товар")
async def add_shop_item_start(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_shop"):
        return
    await message.answer("Введи название товара:", reply_markup=back_keyboard())
    await AddShopItem.name.set()

@dp.message_handler(state=AddShopItem.name)
async def add_shop_item_name(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_shop_menu(message)
        return
    await state.update_data(name=message.text)
    await message.answer("Введи описание товара:")
    await AddShopItem.next()

@dp.message_handler(state=AddShopItem.description)
async def add_shop_item_description(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_shop_menu(message)
        return
    await state.update_data(description=message.text)
    await message.answer("Введи цену (можно дробную):")
    await AddShopItem.next()

@dp.message_handler(state=AddShopItem.price)
async def add_shop_item_price(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_shop_menu(message)
        return
    try:
        price = float(message.text)
        if price <= 0:
            raise ValueError
        price = round(price, 2)
        max_input = await get_setting_float("max_input_number")
        if price > max_input:
            await message.answer(f"❌ Цена слишком большая (максимум {max_input:.2f}).")
            return
    except ValueError:
        await message.answer("❌ Цена должна быть положительным числом (можно дробным).")
        return
    await state.update_data(price=price)
    await message.answer("Введи количество товара (целое число, -1 для бесконечного):")
    await AddShopItem.stock.set()

@dp.message_handler(state=AddShopItem.stock)
async def add_shop_item_stock(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_shop_menu(message)
        return
    try:
        stock = int(message.text)
    except ValueError:
        await message.answer("❌ Введи целое число.")
        return
    await state.update_data(stock=stock)
    await message.answer("Отправь фото для товара (или 'нет'):")
    await AddShopItem.photo.set()

@dp.message_handler(state=AddShopItem.photo, content_types=['photo', 'text'])
async def add_shop_item_photo(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_shop_menu(message)
        return
    photo_file_id = None
    if message.photo:
        photo_file_id = message.photo[-1].file_id
    elif message.text and message.text.lower() == 'нет':
        pass
    else:
        await message.answer("Отправь фото или 'нет'.")
        return
    data = await state.get_data()
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO shop_items (name, description, price, stock, photo_file_id) VALUES ($1, $2, $3, $4, $5)",
                data['name'], data['description'], data['price'], data['stock'], photo_file_id
            )
        await message.answer("✅ Товар добавлен!", reply_markup=admin_shop_keyboard())
    except Exception as e:
        logging.error(f"Add shop item error: {e}", exc_info=True)
        await message.answer("❌ Ошибка при добавлении товара.")
    await state.finish()

@dp.message_handler(lambda message: message.text == "➖ Удалить товар")
async def remove_shop_item_start(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_shop"):
        return
    try:
        async with db_pool.acquire() as conn:
            items = await conn.fetch("SELECT id, name FROM shop_items ORDER BY id")
        if not items:
            await message.answer("В магазине нет товаров.")
            return
        text = "Товары:\n" + "\n".join([f"ID {i['id']}: {i['name']}" for i in items])
        await message.answer(text + "\n\nВведи ID товара для удаления:", reply_markup=back_keyboard())
    except Exception as e:
        logging.error(f"List items for remove error: {e}", exc_info=True)
        await message.answer("❌ Ошибка.")
        return
    await RemoveShopItem.item_id.set()

@dp.message_handler(state=RemoveShopItem.item_id)
async def remove_shop_item(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_shop_menu(message)
        return
    try:
        item_id = int(message.text)
    except ValueError:
        await message.answer("❌ Введи число.")
        return
    try:
        async with db_pool.acquire() as conn:
            await conn.execute("DELETE FROM shop_items WHERE id=$1", item_id)
        await message.answer("✅ Товар удалён, если существовал.", reply_markup=admin_shop_keyboard())
    except Exception as e:
        logging.error(f"Remove shop item error: {e}", exc_info=True)
        await message.answer("❌ Ошибка.")
    await state.finish()

@dp.message_handler(lambda message: message.text == "✏️ Редактировать товар")
async def edit_shop_item_start(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_shop"):
        return
    await message.answer("Введи ID товара для редактирования:", reply_markup=back_keyboard())
    await EditShopItem.item_id.set()

@dp.message_handler(state=EditShopItem.item_id)
async def edit_shop_item_field(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_shop_menu(message)
        return
    try:
        item_id = int(message.text)
    except ValueError:
        await message.answer("❌ Введи число.")
        return
    await state.update_data(item_id=item_id)
    await message.answer("Что хочешь изменить? (price/stock)")
    await EditShopItem.field.set()

@dp.message_handler(state=EditShopItem.field)
async def edit_shop_item_value(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_shop_menu(message)
        return
    field = message.text.lower()
    if field not in ['price', 'stock']:
        await message.answer("❌ Можно изменить только price или stock.")
        return
    await state.update_data(field=field)
    await message.answer(f"Введи новое значение для {field}:")
    await EditShopItem.value.set()

@dp.message_handler(state=EditShopItem.value)
async def edit_shop_item_final(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_shop_menu(message)
        return
    try:
        data = await state.get_data()
        if data['field'] == 'price':
            value = float(message.text)
            if value <= 0:
                raise ValueError
            value = round(value, 2)
            max_input = await get_setting_float("max_input_number")
            if value > max_input:
                await message.answer(f"❌ Цена слишком большая (максимум {max_input:.2f}).")
                return
        else:
            value = int(message.text)
    except ValueError:
        await message.answer("❌ Введи корректное число.")
        return
    item_id = data['item_id']
    field = data['field']
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(f"UPDATE shop_items SET {field}=$1 WHERE id=$2", value, item_id)
        await message.answer("✅ Товар обновлён.", reply_markup=admin_shop_keyboard())
    except Exception as e:
        logging.error(f"Edit shop item error: {e}", exc_info=True)
        await message.answer("❌ Ошибка.")
    await state.finish()
  @dp.message_handler(lambda message: message.text == "📋 Список товаров")
async def list_shop_items(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_shop"):
        return
    page = 1
    try:
        parts = message.text.split()
        if len(parts) > 1:
            page = int(parts[1])
    except:
        pass
    offset = (page - 1) * ITEMS_PER_PAGE
    try:
        async with db_pool.acquire() as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM shop_items")
            items = await conn.fetch(
                "SELECT id, name, description, price, stock, photo_file_id FROM shop_items ORDER BY id LIMIT $1 OFFSET $2",
                ITEMS_PER_PAGE, offset
            )
        if not items:
            await message.answer("В магазине нет товаров.")
            return
        text = f"📦 Товары (страница {page}):\n"
        for item in items:
            text += f"\nID {item['id']} | {item['name']}\n{item['description']}\n💰 {float(item['price']):.2f} | наличие: {item['stock'] if item['stock']!=-1 else '∞'}\n"
        kb = []
        nav_buttons = []
        if page > 1:
            nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"shopitems_page_{page-1}"))
        if offset + ITEMS_PER_PAGE < total:
            nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"shopitems_page_{page+1}"))
        if nav_buttons:
            kb.append(nav_buttons)
        if kb:
            await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        else:
            await message.answer(text, reply_markup=admin_shop_keyboard())
    except Exception as e:
        logging.error(f"List shop items error: {e}", exc_info=True)
        await message.answer("❌ Ошибка.")

@dp.callback_query_handler(lambda c: c.data.startswith("shopitems_page_"))
async def shopitems_page_callback(callback: types.CallbackQuery):
    await callback.answer()
    page = int(callback.data.split("_")[2])
    callback.message.text = f"📋 Список товаров {page}"
    await list_shop_items(callback.message)

@dp.message_handler(lambda message: message.text == "🛍️ Список покупок")
async def admin_purchases(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_shop"):
        return
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT p.id, u.user_id, u.username, s.name, p.purchase_date, p.status FROM purchases p "
                "JOIN users u ON p.user_id = u.user_id JOIN shop_items s ON p.item_id = s.id "
                "WHERE p.status='pending' ORDER BY p.purchase_date"
            )
        if not rows:
            await message.answer("Нет необработанных покупок.")
            return
        for row in rows:
            pid, uid, username, item_name, date, status = row['id'], row['user_id'], row['username'], row['name'], row['purchase_date'], row['status']
            text = f"🆔 {pid}\nПользователь: {uid} (@{username})\nТовар: {item_name}\nДата: {date}"
            await message.answer(text, reply_markup=purchase_action_keyboard(pid))
    except Exception as e:
        logging.error(f"Admin purchases error: {e}", exc_info=True)
        await message.answer("❌ Ошибка загрузки покупок.")

@dp.callback_query_handler(lambda c: c.data.startswith("purchase_done_"))
async def purchase_done(callback: types.CallbackQuery):
    await callback.answer()
    if not await check_admin_permissions(callback.from_user.id, "manage_shop"):
        await callback.message.answer("Недостаточно прав")
        return
    purchase_id = int(callback.data.split("_")[2])
    try:
        async with db_pool.acquire() as conn:
            await conn.execute("UPDATE purchases SET status='completed' WHERE id=$1", purchase_id)
            user_id = await conn.fetchval("SELECT user_id FROM purchases WHERE id=$1", purchase_id)
            if user_id:
                await safe_send_message(user_id, "✅ Твоя покупка обработана! Админ выслал подарок.")
        await callback.message.delete()
    except Exception as e:
        logging.error(f"Purchase done error: {e}", exc_info=True)
        await callback.message.answer("Ошибка")

@dp.callback_query_handler(lambda c: c.data.startswith("purchase_reject_"))
async def purchase_reject(callback: types.CallbackQuery):
    await callback.answer()
    if not await check_admin_permissions(callback.from_user.id, "manage_shop"):
        await callback.message.answer("Недостаточно прав")
        return
    purchase_id = int(callback.data.split("_")[2])
    try:
        async with db_pool.acquire() as conn:
            await conn.execute("UPDATE purchases SET status='rejected' WHERE id=$1", purchase_id)
            user_id = await conn.fetchval("SELECT user_id FROM purchases WHERE id=$1", purchase_id)
            if user_id:
                await safe_send_message(user_id, "❌ К сожалению, твоя покупка не может быть выполнена. Свяжись с админом.")
        await callback.message.delete()
    except Exception as e:
        logging.error(f"Purchase reject error: {e}", exc_info=True)
        await callback.message.answer("Ошибка")

# ==================== УПРАВЛЕНИЕ КАНАЛАМИ ====================
@dp.message_handler(lambda message: message.text == "📢 Каналы")
async def admin_channel_menu(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_channels"):
        await message.answer("❌ Недостаточно прав.")
        return
    await send_with_media(message.chat.id, "Управление каналами:", media_key='admin_channels', reply_markup=admin_channel_keyboard())

@dp.message_handler(lambda message: message.text == "➕ Добавить канал")
async def add_channel_start(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_channels"):
        return
    await message.answer("Введи chat_id канала (можно получить у @username_to_id_bot):", reply_markup=back_keyboard())
    await AddChannel.chat_id.set()

@dp.message_handler(state=AddChannel.chat_id)
async def add_channel_chat_id(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_channel_menu(message)
        return
    await state.update_data(chat_id=message.text.strip())
    await message.answer("Введи название канала:")
    await AddChannel.next()

@dp.message_handler(state=AddChannel.title)
async def add_channel_title(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_channel_menu(message)
        return
    await state.update_data(title=message.text)
    await message.answer("Введи invite-ссылку (или отправь 'нет'):")
    await AddChannel.next()

@dp.message_handler(state=AddChannel.invite_link)
async def add_channel_link(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_channel_menu(message)
        return
    link = None if message.text.lower() == 'нет' else message.text.strip()
    data = await state.get_data()
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO channels (chat_id, title, invite_link) VALUES ($1, $2, $3)",
                data['chat_id'], data['title'], link
            )
        await message.answer("✅ Канал добавлен!", reply_markup=admin_channel_keyboard())
    except asyncpg.UniqueViolationError:
        await message.answer("❌ Канал с таким chat_id уже существует.")
    except Exception as e:
        logging.error(f"Add channel error: {e}", exc_info=True)
        await message.answer("❌ Ошибка.")
    await state.finish()

@dp.message_handler(lambda message: message.text == "➖ Удалить канал")
async def remove_channel_start(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_channels"):
        return
    await message.answer("Введи chat_id канала для удаления:", reply_markup=back_keyboard())
    await RemoveChannel.chat_id.set()

@dp.message_handler(state=RemoveChannel.chat_id)
async def remove_channel(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_channel_menu(message)
        return
    chat_id = message.text.strip()
    try:
        async with db_pool.acquire() as conn:
            await conn.execute("DELETE FROM channels WHERE chat_id=$1", chat_id)
        await message.answer("✅ Канал удалён, если существовал.", reply_markup=admin_channel_keyboard())
    except Exception as e:
        logging.error(f"Remove channel error: {e}", exc_info=True)
        await message.answer("❌ Ошибка.")
    await state.finish()

@dp.message_handler(lambda message: message.text == "📋 Список каналов")
async def list_channels(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_channels"):
        return
    channels = await get_channels()
    if not channels:
        await message.answer("Нет добавленных каналов.")
        return
    text = "📺 Каналы для подписки:\n"
    for chat_id, title, link in channels:
        text += f"• {title} (chat_id: {chat_id})\n  Ссылка: {link or 'нет'}\n"
    await message.answer(text, reply_markup=admin_channel_keyboard())

# ==================== УПРАВЛЕНИЕ ПРОМОКОДАМИ ====================
@dp.message_handler(lambda message: message.text == "🎫 Промокоды")
async def admin_promo_menu(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_promocodes"):
        await message.answer("❌ Недостаточно прав.")
        return
    await send_with_media(message.chat.id, "Управление промокодами:", media_key='admin_promo', reply_markup=admin_promo_keyboard())

@dp.message_handler(lambda message: message.text == "➕ Создать промокод")
async def create_promo_start(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_promocodes"):
        return
    await message.answer("Введи код промокода (латиница, цифры):", reply_markup=back_keyboard())
    await CreatePromocode.code.set()

@dp.message_handler(state=CreatePromocode.code)
async def create_promo_code(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_promo_menu(message)
        return
    code = message.text.strip().upper()
    await state.update_data(code=code)
    await message.answer("Введи количество баксов, которые даёт промокод (можно дробно):")
    await CreatePromocode.next()

@dp.message_handler(state=CreatePromocode.reward)
async def create_promo_reward(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_promo_menu(message)
        return
    try:
        reward = float(message.text)
        if reward <= 0:
            raise ValueError
        reward = round(reward, 2)
        max_input = await get_setting_float("max_input_number")
        if reward > max_input:
            await message.answer(f"❌ Сумма слишком большая (максимум {max_input:.2f}).")
            return
    except ValueError:
        await message.answer("❌ Введи положительное число (можно дробное).")
        return
    await state.update_data(reward=reward)
    await message.answer("Введи максимальное количество использований:")
    await CreatePromocode.next()

@dp.message_handler(state=CreatePromocode.max_uses)
async def create_promo_max_uses(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_promo_menu(message)
        return
    try:
        max_uses = int(message.text)
        if max_uses <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи положительное целое число.")
        return
    data = await state.get_data()
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO promocodes (code, reward, max_uses, created_at) VALUES ($1, $2, $3, $4)",
                data['code'], data['reward'], max_uses, datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
        await message.answer("✅ Промокод создан!", reply_markup=admin_promo_keyboard())
    except asyncpg.UniqueViolationError:
        await message.answer("❌ Промокод с таким кодом уже существует.")
    except Exception as e:
        logging.error(f"Create promo error: {e}", exc_info=True)
        await message.answer("❌ Ошибка.")
    await state.finish()

@dp.message_handler(lambda message: message.text == "📋 Список промокодов")
async def list_promos(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_promocodes"):
        return
    page = 1
    try:
        parts = message.text.split()
        if len(parts) > 1:
            page = int(parts[1])
    except:
        pass
    offset = (page - 1) * ITEMS_PER_PAGE
    try:
        async with db_pool.acquire() as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM promocodes")
            rows = await conn.fetch(
                "SELECT code, reward, max_uses, used_count FROM promocodes LIMIT $1 OFFSET $2",
                ITEMS_PER_PAGE, offset
            )
        if not rows:
            await message.answer("Нет промокодов.")
            return
        text = f"🎫 Промокоды (страница {page}):\n"
        for row in rows:
            text += f"• {row['code']}: {float(row['reward']):.2f} баксов, использовано {row['used_count']}/{row['max_uses']}\n"
        kb = []
        nav_buttons = []
        if page > 1:
            nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"promos_page_{page-1}"))
        if offset + ITEMS_PER_PAGE < total:
            nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"promos_page_{page+1}"))
        if nav_buttons:
            kb.append(nav_buttons)
        if kb:
            await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        else:
            await message.answer(text, reply_markup=admin_promo_keyboard())
    except Exception as e:
        logging.error(f"List promos error: {e}", exc_info=True)
        await message.answer("❌ Ошибка.")

@dp.callback_query_handler(lambda c: c.data.startswith("promos_page_"))
async def promos_page_callback(callback: types.CallbackQuery):
    await callback.answer()
    page = int(callback.data.split("_")[2])
    callback.message.text = f"📋 Список промокодов {page}"
    await list_promos(callback.message)
  # ==================== УПРАВЛЕНИЕ ЗАДАНИЯМИ ====================
@dp.message_handler(lambda message: message.text == "📋 Задания")
async def admin_tasks_menu(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_tasks"):
        await message.answer("❌ Недостаточно прав.")
        return
    await send_with_media(message.chat.id, "Управление заданиями:", media_key='admin_tasks', reply_markup=admin_tasks_keyboard())

@dp.message_handler(lambda message: message.text == "➕ Создать задание")
async def create_task_start(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_tasks"):
        return
    await message.answer("Введи название задания:", reply_markup=back_keyboard())
    await CreateTask.name.set()

@dp.message_handler(state=CreateTask.name)
async def create_task_name(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_tasks_menu(message)
        return
    await state.update_data(name=message.text)
    await message.answer("Введи описание задания:")
    await CreateTask.next()

@dp.message_handler(state=CreateTask.description)
async def create_task_description(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_tasks_menu(message)
        return
    await state.update_data(description=message.text)
    await message.answer("Введи тип задания (subscribe):")
    await CreateTask.next()

@dp.message_handler(state=CreateTask.task_type)
async def create_task_type(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_tasks_menu(message)
        return
    task_type = message.text.lower()
    if task_type not in ['subscribe']:
        await message.answer("❌ Пока поддерживается только тип 'subscribe'.")
        return
    await state.update_data(task_type=task_type)
    await message.answer("Введи target_id (например, ID канала для подписки):")
    await CreateTask.next()

@dp.message_handler(state=CreateTask.target_id)
async def create_task_target(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_tasks_menu(message)
        return
    await state.update_data(target_id=message.text)
    await message.answer("Введи награду в баксах (можно дробно):")
    await CreateTask.next()

@dp.message_handler(state=CreateTask.reward_coins)
async def create_task_reward_coins(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_tasks_menu(message)
        return
    try:
        coins = float(message.text)
        if coins <= 0:
            raise ValueError
        coins = round(coins, 2)
        max_input = await get_setting_float("max_input_number")
        if coins > max_input:
            await message.answer(f"❌ Сумма слишком большая (максимум {max_input:.2f}).")
            return
    except ValueError:
        await message.answer("❌ Введи положительное число.")
        return
    await state.update_data(reward_coins=coins)
    await message.answer("Введи награду в репутации (целое число):")
    await CreateTask.next()

@dp.message_handler(state=CreateTask.reward_reputation)
async def create_task_reward_rep(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_tasks_menu(message)
        return
    try:
        rep = int(message.text)
        if rep < 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи целое неотрицательное число.")
        return
    await state.update_data(reward_reputation=rep)
    await message.answer("Введи количество дней, на которое задание выдается (0 - бессрочно):")
    await CreateTask.next()

@dp.message_handler(state=CreateTask.required_days)
async def create_task_required_days(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_tasks_menu(message)
        return
    try:
        days = int(message.text)
        if days < 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи целое неотрицательное число.")
        return
    await state.update_data(required_days=days)
    await message.answer("Введи штрафные дни при невыполнении (0 - нет):")
    await CreateTask.next()

@dp.message_handler(state=CreateTask.penalty_days)
async def create_task_penalty_days(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_tasks_menu(message)
        return
    try:
        penalty = int(message.text)
        if penalty < 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи целое неотрицательное число.")
        return
    await state.update_data(penalty_days=penalty)
    await message.answer("Введи максимальное количество выполнений (целое число):")
    await CreateTask.next()

@dp.message_handler(state=CreateTask.max_completions)
async def create_task_max_completions(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_tasks_menu(message)
        return
    try:
        max_comp = int(message.text)
        if max_comp <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи положительное целое число.")
        return
    data = await state.get_data()
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO tasks (name, description, task_type, target_id, reward_coins, reward_reputation, required_days, penalty_days, max_completions, created_by, created_at, active) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)",
                data['name'], data['description'], data['task_type'], data['target_id'], data['reward_coins'], data['reward_reputation'], data['required_days'], data['penalty_days'], max_comp, message.from_user.id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), True
            )
        await message.answer("✅ Задание создано!", reply_markup=admin_tasks_keyboard())
    except Exception as e:
        logging.error(f"Create task error: {e}", exc_info=True)
        await message.answer("❌ Ошибка.")
    await state.finish()

@dp.message_handler(lambda message: message.text == "📋 Список заданий")
async def list_tasks_admin(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_tasks"):
        return
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, name, description, reward_coins, reward_reputation, active FROM tasks ORDER BY id")
    if not rows:
        await message.answer("Нет созданных заданий.")
        return
    text = "📋 Задания:\n\n"
    for row in rows:
        status = "✅" if row['active'] else "❌"
        text += f"{status} ID {row['id']}: {row['name']}\n{row['description']}\nНаграда: {float(row['reward_coins']):.2f} баксов, {row['reward_reputation']} репутации\n\n"
    await message.answer(text, reply_markup=admin_tasks_keyboard())

@dp.message_handler(lambda message: message.text == "❌ Удалить задание")
async def delete_task_start(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_tasks"):
        return
    await message.answer("Введи ID задания для удаления:", reply_markup=back_keyboard())
    await DeleteTask.task_id.set()

@dp.message_handler(state=DeleteTask.task_id)
async def delete_task_finish(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_tasks_menu(message)
        return
    try:
        task_id = int(message.text)
    except ValueError:
        await message.answer("❌ Введи число.")
        return
    try:
        async with db_pool.acquire() as conn:
            await conn.execute("DELETE FROM tasks WHERE id=$1", task_id)
            await conn.execute("DELETE FROM user_tasks WHERE task_id=$1", task_id)
        await message.answer("✅ Задание удалено, если существовало.", reply_markup=admin_tasks_keyboard())
    except Exception as e:
        logging.error(f"Delete task error: {e}", exc_info=True)
        await message.answer("❌ Ошибка.")
    await state.finish()

# ==================== УПРАВЛЕНИЕ БЛОКИРОВКАМИ ====================
@dp.message_handler(lambda message: message.text == "🔨 Блокировки")
async def admin_ban_menu(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_bans"):
        await message.answer("❌ Недостаточно прав.")
        return
    await send_with_media(message.chat.id, "Управление блокировками:", media_key='admin_ban', reply_markup=admin_ban_keyboard())

@dp.message_handler(lambda message: message.text == "🔨 Заблокировать пользователя")
async def block_user_start(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_bans"):
        return
    await message.answer("Введи ID или @username пользователя для блокировки:", reply_markup=back_keyboard())
    await BlockUser.user_id.set()

@dp.message_handler(state=BlockUser.user_id)
async def block_user_id(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_ban_menu(message)
        return
    user_data = await find_user_by_input(message.text)
    if not user_data:
        await message.answer("❌ Пользователь не найден.")
        return
    uid = user_data['user_id']
    if await is_admin(uid):
        await message.answer("❌ Нельзя заблокировать администратора.")
        await state.finish()
        return
    await state.update_data(user_id=uid)
    await message.answer("Введи причину блокировки (можно отправить 'нет'):")
    await BlockUser.reason.set()

@dp.message_handler(state=BlockUser.reason)
async def block_user_reason(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_ban_menu(message)
        return
    reason = None if message.text.lower() == 'нет' else message.text
    data = await state.get_data()
    uid = data['user_id']
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO banned_users (user_id, banned_by, banned_date, reason) VALUES ($1, $2, $3, $4) ON CONFLICT (user_id) DO NOTHING",
                uid, message.from_user.id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), reason
            )
        await message.answer(f"✅ Пользователь {uid} заблокирован.")
        await safe_send_message(uid, f"⛔ Вы заблокированы в боте. Причина: {reason if reason else 'не указана'}")
    except Exception as e:
        logging.error(f"Block user error: {e}", exc_info=True)
        await message.answer("❌ Ошибка.")
    await state.finish()

@dp.message_handler(lambda message: message.text == "🔓 Разблокировать пользователя")
async def unblock_user_start(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_bans"):
        return
    await message.answer("Введи ID или @username пользователя для разблокировки:", reply_markup=back_keyboard())
    await UnblockUser.user_id.set()

@dp.message_handler(state=UnblockUser.user_id)
async def unblock_user_finish(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_ban_menu(message)
        return
    user_data = await find_user_by_input(message.text)
    if not user_data:
        await message.answer("❌ Пользователь не найден.")
        return
    uid = user_data['user_id']
    try:
        async with db_pool.acquire() as conn:
            await conn.execute("DELETE FROM banned_users WHERE user_id=$1", uid)
        await message.answer(f"✅ Пользователь {uid} разблокирован.")
        await safe_send_message(uid, "🔓 Вы разблокированы в боте.")
    except Exception as e:
        logging.error(f"Unblock user error: {e}", exc_info=True)
        await message.answer("❌ Ошибка.")
    await state.finish()

@dp.message_handler(lambda message: message.text == "📋 Список заблокированных")
async def list_banned(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_bans"):
        return
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id, banned_date, reason FROM banned_users ORDER BY banned_date DESC")
    if not rows:
        await message.answer("Нет заблокированных пользователей.")
        return
    text = "⛔ Заблокированные пользователи:\n\n"
    for row in rows:
        text += f"ID: {row['user_id']}, Дата: {row['banned_date']}\nПричина: {row['reason'] or 'не указана'}\n\n"
    await message.answer(text)
  # ==================== УПРАВЛЕНИЕ АДМИНАМИ ====================
@dp.message_handler(lambda message: message.text == "➕ Админы")
async def admin_admins_menu(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_admins"):
        await message.answer("❌ Недостаточно прав.")
        return
    await send_with_media(message.chat.id, "Управление админами:", media_key='admin_admins', reply_markup=admin_admins_keyboard())

@dp.message_handler(lambda message: message.text == "➕ Добавить админа")
async def add_admin_start(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_admins"):
        return
    await message.answer("Введи ID или @username пользователя, которого хочешь сделать младшим админом:", reply_markup=back_keyboard())
    await AddJuniorAdmin.user_id.set()

@dp.message_handler(state=AddJuniorAdmin.user_id)
async def add_admin_finish(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_admins_menu(message)
        return
    user_data = await find_user_by_input(message.text)
    if not user_data:
        await message.answer("❌ Пользователь не найден.")
        return
    uid = user_data['user_id']
    await state.update_data(user_id=uid)
    kb = InlineKeyboardMarkup(row_width=1)
    for perm in PERMISSIONS_LIST:
        kb.add(InlineKeyboardButton(text=perm, callback_data=f"addadmin_perm:{perm}"))
    kb.add(InlineKeyboardButton(text="✅ Готово", callback_data="addadmin_done"))
    await message.answer("Выбери права для нового админа (можно несколько):", reply_markup=kb)
    await AddJuniorAdmin.permissions.set()
    await state.update_data(selected_perms=[])

@dp.callback_query_handler(lambda c: c.data.startswith("addadmin_perm:"), state=AddJuniorAdmin.permissions)
async def add_admin_toggle_perm(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    perm = callback.data.split(":", 1)[1]
    data = await state.get_data()
    selected = data.get('selected_perms', [])
    if perm in selected:
        selected.remove(perm)
    else:
        selected.append(perm)
    await state.update_data(selected_perms=selected)

@dp.callback_query_handler(lambda c: c.data == "addadmin_done", state=AddJuniorAdmin.permissions)
async def add_admin_done(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    uid = data['user_id']
    perms = data.get('selected_perms', [])
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO admins (user_id, added_by, added_date, permissions) VALUES ($1, $2, $3, $4) ON CONFLICT (user_id) DO UPDATE SET permissions=$4",
                uid, callback.from_user.id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), json.dumps(perms)
            )
        await callback.message.edit_text(f"✅ Пользователь {uid} теперь младший админ с правами: {', '.join(perms) if perms else 'нет прав'}.")
        await safe_send_message(uid, f"🔔 Вам назначены права администратора!\nВаши права: {', '.join(perms) if perms else 'нет прав'}.\nПожалуйста, нажмите /start для обновления меню.")
    except Exception as e:
        logging.error(f"Add admin error: {e}", exc_info=True)
        await callback.message.edit_text("❌ Ошибка при добавлении админа.")
    await state.finish()

@dp.message_handler(lambda message: message.text == "✏️ Редактировать права админа")
async def edit_admin_permissions_start(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_admins"):
        return
    await message.answer("Введи ID или @username админа, чьи права хочешь изменить:", reply_markup=back_keyboard())
    await EditAdminPermissions.user_id.set()

@dp.message_handler(state=EditAdminPermissions.user_id)
async def edit_admin_permissions_user(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_admins_menu(message)
        return
    user_data = await find_user_by_input(message.text)
    if not user_data:
        await message.answer("❌ Пользователь не найден.")
        return
    uid = user_data['user_id']
    if await is_super_admin(uid):
        await message.answer("❌ Нельзя редактировать права суперадмина.")
        await state.finish()
        return
    if not await is_junior_admin(uid):
        await message.answer("❌ Этот пользователь не является младшим админом. Сначала добавьте его через «Добавить админа».")
        await state.finish()
        return
    current_perms = await get_admin_permissions(uid)
    await state.update_data(user_id=uid, current_perms=current_perms)
    kb = InlineKeyboardMarkup(row_width=1)
    for perm in PERMISSIONS_LIST:
        status = "✅ " if perm in current_perms else "❌ "
        kb.add(InlineKeyboardButton(text=f"{status}{perm}", callback_data=f"editadmin_perm:{perm}"))
    kb.add(InlineKeyboardButton(text="✅ Сохранить", callback_data="editadmin_save"))
    await message.answer("Выбери права (нажимай для переключения):", reply_markup=kb)
    await EditAdminPermissions.selecting_permissions.set()
    await state.update_data(selected_perms=current_perms.copy())

@dp.callback_query_handler(lambda c: c.data.startswith("editadmin_perm:"), state=EditAdminPermissions.selecting_permissions)
async def edit_admin_toggle_perm(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    perm = callback.data.split(":", 1)[1]
    data = await state.get_data()
    selected = data.get('selected_perms', data['current_perms'].copy())
    if perm in selected:
        selected.remove(perm)
    else:
        selected.append(perm)
    await state.update_data(selected_perms=selected)

@dp.callback_query_handler(lambda c: c.data == "editadmin_save", state=EditAdminPermissions.selecting_permissions)
async def edit_admin_save(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    uid = data['user_id']
    selected = data.get('selected_perms', data['current_perms'])
    await update_admin_permissions(uid, selected)
    await safe_send_message(uid, f"🔔 Ваши права администратора изменены!\nНовые права: {', '.join(selected) if selected else 'нет прав'}.\nПожалуйста, нажмите /start для обновления меню.")
    await callback.message.edit_text(f"✅ Права пользователя {uid} обновлены: {', '.join(selected)}")
    await state.finish()

@dp.message_handler(lambda message: message.text == "➖ Удалить админа")
async def remove_admin_start(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_admins"):
        return
    await message.answer("Введи ID или @username админа, которого хочешь удалить:", reply_markup=back_keyboard())
    await RemoveJuniorAdmin.user_id.set()

@dp.message_handler(state=RemoveJuniorAdmin.user_id)
async def remove_admin_finish(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_admins_menu(message)
        return
    user_data = await find_user_by_input(message.text)
    if not user_data:
        await message.answer("❌ Пользователь не найден.")
        return
    uid = user_data['user_id']
    if await is_super_admin(uid):
        await message.answer("❌ Нельзя удалить суперадмина.")
        await state.finish()
        return
    try:
        async with db_pool.acquire() as conn:
            await conn.execute("DELETE FROM admins WHERE user_id=$1", uid)
        await message.answer(f"✅ Пользователь {uid} больше не админ, если был им.")
        await safe_send_message(uid, "🔔 Ваши права администратора были отозваны.")
    except Exception as e:
        logging.error(f"Remove admin error: {e}", exc_info=True)
        await message.answer("❌ Ошибка.")
    await state.finish()

@dp.message_handler(lambda message: message.text == "📋 Список админов")
async def list_admins(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_admins"):
        return
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id, added_date, permissions FROM admins ORDER BY added_date")
    if not rows:
        await message.answer("Нет младших админов.")
        return
    text = "👥 Младшие админы:\n"
    for row in rows:
        perms = json.loads(row['permissions'])
        perms_str = ', '.join(perms) if perms else 'нет прав'
        text += f"• ID: {row['user_id']}, назначен: {row['added_date']}\n  Права: {perms_str}\n"
    await message.answer(text)

# ==================== УПРАВЛЕНИЕ ЧАТАМИ ====================
@dp.message_handler(lambda message: message.text == "🤖 Чаты")
async def admin_chats_menu(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_chats"):
        await message.answer("❌ Недостаточно прав.")
        return
    await send_with_media(message.chat.id, "Управление чатами:", media_key='admin_chats', reply_markup=admin_chats_keyboard())

@dp.message_handler(lambda message: message.text == "📋 Список запросов на подтверждение")
async def list_pending_requests(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_chats"):
        return
    requests = await get_pending_chat_requests()
    if not requests:
        await message.answer("Нет ожидающих запросов.")
        return
    text = "📋 Ожидающие запросы:\n\n"
    for req in requests:
        text += f"• {req['title']} (ID: {req['chat_id']})\n  Запросил: {req['requested_by']} ({req['request_date']})\n"
    await message.answer(text)

@dp.message_handler(lambda message: message.text == "✅ Подтвердить чат")
async def confirm_chat_manual(message: types.Message, state: FSMContext):
    if not await check_admin_permissions(message.from_user.id, "manage_chats"):
        return
    await message.answer("Введи ID чата, который хочешь подтвердить:", reply_markup=back_keyboard())
    await ManageChats.chat_id.set()
    await state.update_data(action="confirm")

@dp.message_handler(lambda message: message.text == "❌ Отклонить запрос")
async def reject_chat_manual(message: types.Message, state: FSMContext):
    if not await check_admin_permissions(message.from_user.id, "manage_chats"):
        return
    await message.answer("Введи ID чата, запрос которого хочешь отклонить:", reply_markup=back_keyboard())
    await ManageChats.chat_id.set()
    await state.update_data(action="reject")

@dp.message_handler(lambda message: message.text == "🗑 Удалить чат из подтверждённых")
async def remove_confirmed_chat_start(message: types.Message, state: FSMContext):
    if not await check_admin_permissions(message.from_user.id, "manage_chats"):
        return
    await message.answer("Введи ID чата, который нужно удалить из подтверждённых:", reply_markup=back_keyboard())
    await ManageChats.chat_id.set()
    await state.update_data(action="remove")

@dp.message_handler(lambda message: message.text == "📋 Список подтверждённых чатов")
async def list_confirmed_chats(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_chats"):
        return
    confirmed = await get_confirmed_chats(force_update=True)
    if not confirmed:
        await message.answer("Нет подтверждённых чатов.")
        return
    text = "✅ Подтверждённые чаты:\n\n"
    for chat_id, data in confirmed.items():
        text += f"• {data['title']} (ID: {chat_id})\n  Подтверждён: {data.get('confirmed_date', 'неизвестно')}\n"
    await message.answer(text)

@dp.message_handler(state=ManageChats.chat_id)
async def process_chat_id(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_chats_menu(message)
        return
    try:
        chat_id = int(message.text)
    except:
        await message.answer("❌ Введи число.")
        return
    data = await state.get_data()
    action = data.get('action')
    async with db_pool.acquire() as conn:
        if action == "confirm":
            request = await conn.fetchrow("SELECT * FROM chat_confirmation_requests WHERE chat_id=$1", chat_id)
            if request:
                await add_confirmed_chat(chat_id, request['title'], request['type'], message.from_user.id)
                await update_chat_request_status(chat_id, 'approved')
                await message.answer(f"✅ Чат {request['title']} подтверждён.")
                await safe_send_message(request['requested_by'], f"✅ Ваш чат «{request['title']}» активирован!")
            else:
                try:
                    chat = await bot.get_chat(chat_id)
                    await add_confirmed_chat(chat_id, chat.title, chat.type, message.from_user.id)
                    await message.answer(f"✅ Чат {chat.title} подтверждён.")
                except:
                    await message.answer("❌ Не удалось получить информацию о чате.")
        elif action == "reject":
            request = await conn.fetchrow("SELECT * FROM chat_confirmation_requests WHERE chat_id=$1", chat_id)
            if not request:
                await message.answer("❌ Запрос не найден.")
                await state.finish()
                return
            await update_chat_request_status(chat_id, 'rejected')
            await message.answer(f"❌ Запрос для чата {request['title']} отклонён.")
            await safe_send_message(request['requested_by'], f"❌ Запрос на активацию чата «{request['title']}» отклонён.")
        elif action == "remove":
            await remove_confirmed_chat(chat_id)
            await message.answer(f"✅ Чат {chat_id} удалён из подтверждённых.")
    await state.finish()
  # ==================== УПРАВЛЕНИЕ БОССАМИ ====================
@dp.message_handler(lambda message: message.text == "👾 Боссы")
async def admin_boss_menu(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_bosses"):
        await message.answer("❌ Недостаточно прав.")
        return
    await send_with_media(message.chat.id, "Управление боссами:", media_key='admin_boss', reply_markup=admin_boss_keyboard())

@dp.message_handler(lambda message: message.text == "📋 Активные боссы")
async def list_active_bosses(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_bosses"):
        return
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM bosses WHERE status='active' ORDER BY spawned_at")
    if not rows:
        await message.answer("Нет активных боссов.")
        return
    text = "👾 Активные боссы:\n"
    kb = InlineKeyboardMarkup(row_width=1)
    for row in rows:
        text += f"ID {row['id']}: {row['name']} (ур. {row['level']}) в чате {row['chat_id']}, HP {row['hp']}/{row['max_hp']}\n"
        kb.add(InlineKeyboardButton(f"❌ Удалить босса ID {row['id']}", callback_data=f"delete_boss_{row['id']}"))
    await message.answer(text, reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith("delete_boss_"))
async def delete_boss_callback(callback: types.CallbackQuery):
    await callback.answer()
    if not await check_admin_permissions(callback.from_user.id, "manage_bosses"):
        await callback.message.answer("❌ Недостаточно прав")
        return
    boss_id = int(callback.data.split("_")[2])
    async with db_pool.acquire() as conn:
        boss = await conn.fetchrow("SELECT * FROM bosses WHERE id=$1", boss_id)
        if not boss:
            await callback.message.answer("❌ Босс не найден")
            return
        await conn.execute("DELETE FROM bosses WHERE id=$1", boss_id)
        await conn.execute("DELETE FROM boss_attacks WHERE boss_id=$1", boss_id)
    await callback.message.answer(f"✅ Босс {boss['name']} полностью удалён")
    await callback.message.delete()

@dp.message_handler(lambda message: message.text == "⚔️ Создать босса вручную")
async def manual_spawn_boss_start(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_bosses"):
        return
    await message.answer("Введи ID чата, где создать босса:", reply_markup=back_keyboard())
    await BossSpawn.chat_id.set()

@dp.message_handler(state=BossSpawn.chat_id)
async def manual_spawn_boss_chat(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_boss_menu(message)
        return
    try:
        chat_id = int(message.text)
    except:
        await message.answer("❌ Введи число.")
        return
    if not await is_chat_confirmed(chat_id):
        await message.answer("❌ Чат не подтверждён. Сначала подтвердите его.")
        await state.finish()
        return
    await state.update_data(chat_id=chat_id)
    await message.answer("Введи уровень босса (1-10):")
    await BossSpawn.level.set()

@dp.message_handler(state=BossSpawn.level)
async def manual_spawn_boss_level(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_boss_menu(message)
        return
    try:
        level = int(message.text)
        if level < 1 or level > 10:
            raise ValueError
    except:
        await message.answer("❌ Введи число от 1 до 10.")
        return
    await state.update_data(level=level)
    await message.answer("Отправь фото для босса (или отправь 'нет'):")
    await BossSpawn.image.set()

@dp.message_handler(state=BossSpawn.image, content_types=['photo', 'text'])
async def manual_spawn_boss_image(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_boss_menu(message)
        return
    image_file_id = None
    if message.photo:
        image_file_id = message.photo[-1].file_id
    elif message.text and message.text.lower() == 'нет':
        pass
    else:
        await message.answer("Отправь фото или 'нет'.")
        return

    data = await state.get_data()
    chat_id = data['chat_id']
    level = data['level']
    await spawn_boss(chat_id, level=level, image_file_id=image_file_id)
    await message.answer(f"✅ Босс {level} уровня создан в чате {chat_id}.")
    await state.finish()

@dp.message_handler(lambda message: message.text == "❌ Удалить босса (по ID)")
async def delete_boss_by_id_start(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_bosses"):
        return
    await message.answer("Введи ID босса для удаления:", reply_markup=back_keyboard())
    await DeleteBoss.boss_id.set()

@dp.message_handler(state=DeleteBoss.boss_id)
async def delete_boss_by_id_confirm(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_boss_menu(message)
        return
    try:
        boss_id = int(message.text)
    except ValueError:
        await message.answer("❌ Введи целое число.")
        return
    await state.update_data(boss_id=boss_id)
    await message.answer(f"Ты уверен, что хочешь удалить босса с ID {boss_id}? (да/нет)", reply_markup=back_keyboard())
    await DeleteBoss.confirm.set()

@dp.message_handler(state=DeleteBoss.confirm)
async def delete_boss_by_id_final(message: types.Message, state: FSMContext):
    if message.text.lower() == 'нет' or message.text == "◀️ Назад":
        await state.finish()
        await admin_boss_menu(message)
        return
    if message.text.lower() == 'да':
        data = await state.get_data()
        boss_id = data['boss_id']
        async with db_pool.acquire() as conn:
            boss = await conn.fetchrow("SELECT * FROM bosses WHERE id=$1", boss_id)
            if not boss:
                await message.answer("❌ Босс с таким ID не найден.")
                await state.finish()
                return
            await conn.execute("DELETE FROM bosses WHERE id=$1", boss_id)
            await conn.execute("DELETE FROM boss_attacks WHERE boss_id=$1", boss_id)
        await message.answer(f"✅ Босс {boss['name']} удалён.")
        await state.finish()
        await admin_boss_menu(message)
    else:
        await message.answer("Введи 'да' или 'нет'.")

# ==================== УПРАВЛЕНИЕ АУКЦИОНАМИ ====================
@dp.message_handler(lambda message: message.text == "🏷 Аукцион")
async def admin_auction_menu(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_auctions"):
        await message.answer("❌ Недостаточно прав.")
        return
    await send_with_media(message.chat.id, "Управление аукционами:", media_key='admin_auction', reply_markup=admin_auction_keyboard())

@dp.message_handler(lambda message: message.text == "➕ Создать аукцион")
async def create_auction_start(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_auctions"):
        return
    await message.answer("Введи название товара:", reply_markup=back_keyboard())
    await CreateAuction.item_name.set()

@dp.message_handler(state=CreateAuction.item_name)
async def create_auction_name(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_auction_menu(message)
        return
    await state.update_data(item_name=message.text)
    await message.answer("Введи описание товара:")
    await CreateAuction.next()

@dp.message_handler(state=CreateAuction.description)
async def create_auction_description(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_auction_menu(message)
        return
    await state.update_data(description=message.text)
    await message.answer("Введи стартовую цену (можно дробную):")
    await CreateAuction.next()

@dp.message_handler(state=CreateAuction.start_price)
async def create_auction_start_price(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_auction_menu(message)
        return
    try:
        price = float(message.text)
        if price <= 0:
            raise ValueError
        price = round(price, 2)
        max_input = await get_setting_float("max_input_number")
        if price > max_input:
            await message.answer(f"❌ Цена слишком большая (максимум {max_input:.2f}).")
            return
    except:
        await message.answer("❌ Введи положительное число (можно дробное).")
        return
    await state.update_data(start_price=price, current_price=price)
    await message.answer("Введи время окончания в часах (целое число) или 'нет', если не нужно:")
    await CreateAuction.next()

@dp.message_handler(state=CreateAuction.end_time)
async def create_auction_end_time(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_auction_menu(message)
        return
    if message.text.lower() == 'нет':
        end_time = None
    else:
        try:
            hours = int(message.text)
            if hours <= 0:
                raise ValueError
            end_time = datetime.now() + timedelta(hours=hours)
        except:
            await message.answer("❌ Введи целое положительное число часов или 'нет'.")
            return
    await state.update_data(end_time=end_time)
    await message.answer("Введи целевую цену (число) или 'нет', если не нужна:")
    await CreateAuction.next()

@dp.message_handler(state=CreateAuction.target_price)
async def create_auction_target_price(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_auction_menu(message)
        return
    if message.text.lower() == 'нет':
        target_price = None
    else:
        try:
            target_price = float(message.text)
            if target_price <= 0:
                raise ValueError
            target_price = round(target_price, 2)
            max_input = await get_setting_float("max_input_number")
            if target_price > max_input:
                await message.answer(f"❌ Цена слишком большая (максимум {max_input:.2f}).")
                return
        except:
            await message.answer("❌ Введи положительное число или 'нет'.")
            return
    await state.update_data(target_price=target_price)
    await message.answer("Отправь фото для аукциона (или 'нет'):")
    await CreateAuction.photo.set()

@dp.message_handler(state=CreateAuction.photo, content_types=['photo', 'text'])
async def create_auction_photo(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_auction_menu(message)
        return
    photo_file_id = None
    if message.photo:
        photo_file_id = message.photo[-1].file_id
    elif message.text and message.text.lower() == 'нет':
        pass
    else:
        await message.answer("❌ Отправь фото или 'нет'.")
        return
    data = await state.get_data()
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO auctions (item_name, description, start_price, current_price, end_time, target_price, created_by, photo_file_id) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
                data['item_name'], data['description'], data['start_price'], data['start_price'], data['end_time'], data['target_price'], message.from_user.id, photo_file_id
            )
        await message.answer("✅ Аукцион создан!", reply_markup=admin_auction_keyboard())
    except Exception as e:
        logging.error(f"Create auction error: {e}", exc_info=True)
        await message.answer("❌ Ошибка при создании аукциона.")
    await state.finish()

@dp.message_handler(lambda message: message.text == "📋 Активные аукционы")
async def list_active_auctions(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_auctions"):
        return
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM auctions WHERE status='active' ORDER BY created_at")
    if not rows:
        await message.answer("Нет активных аукционов.")
        return
    text = "Активные аукционы:\n"
    for row in rows:
        text += f"ID {row['id']}: {row['item_name']} | Текущая цена: {float(row['current_price']):.2f} | Создатель: {row['created_by']}\n"
    await message.answer(text)

@dp.message_handler(lambda message: message.text == "❌ Отменить аукцион")
async def cancel_auction_start(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_auctions"):
        return
    await message.answer("Введи ID аукциона для отмены:", reply_markup=back_keyboard())
    await CancelAuction.auction_id.set()

@dp.message_handler(state=CancelAuction.auction_id)
async def cancel_auction_finish(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_auction_menu(message)
        return
    try:
        auction_id = int(message.text)
    except:
        await message.answer("❌ Введи число.")
        return
    async with db_pool.acquire() as conn:
        exists = await conn.fetchval("SELECT 1 FROM auctions WHERE id=$1", auction_id)
        if not exists:
            await message.answer("❌ Аукцион с таким ID не найден.")
            await state.finish()
            return
        await conn.execute("UPDATE auctions SET status='cancelled' WHERE id=$1", auction_id)
    await message.answer(f"✅ Аукцион {auction_id} отменён.")
    await state.finish()
  # ==================== УПРАВЛЕНИЕ РЕКЛАМОЙ ====================
@dp.message_handler(lambda message: message.text == "📢 Реклама")
async def admin_ad_menu(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_ads"):
        await message.answer("❌ Недостаточно прав.")
        return
    await send_with_media(message.chat.id, "Управление рекламой:", media_key='admin_ad', reply_markup=admin_ad_keyboard())

@dp.message_handler(lambda message: message.text == "➕ Создать рекламу")
async def create_ad_start(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_ads"):
        return
    await message.answer("Введи текст рекламного сообщения:", reply_markup=back_keyboard())
    await CreateAd.text.set()

@dp.message_handler(state=CreateAd.text)
async def create_ad_text(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_ad_menu(message)
        return
    await state.update_data(text=message.text)
    await message.answer("Введи интервал отправки в минутах (целое число):")
    await CreateAd.interval.set()

@dp.message_handler(state=CreateAd.interval)
async def create_ad_interval(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_ad_menu(message)
        return
    try:
        interval = int(message.text)
        if interval <= 0:
            raise ValueError
    except:
        await message.answer("❌ Введи целое положительное число.")
        return
    await state.update_data(interval=interval)
    await message.answer("Куда отправлять? (chats / private / all):")
    await CreateAd.target.set()

@dp.message_handler(state=CreateAd.target)
async def create_ad_target(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_ad_menu(message)
        return
    target = message.text.lower()
    if target not in ['chats', 'private', 'all']:
        await message.answer("❌ Выбери: chats, private или all.")
        return
    data = await state.get_data()
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO ads (text, interval_minutes, target, last_sent, enabled) VALUES ($1, $2, $3, $4, $5)",
                data['text'], data['interval'], target, datetime.now(), True
            )
        await message.answer("✅ Рекламное объявление создано!", reply_markup=admin_ad_keyboard())
    except Exception as e:
        logging.error(f"Create ad error: {e}", exc_info=True)
        await message.answer("❌ Ошибка.")
    await state.finish()

@dp.message_handler(lambda message: message.text == "📋 Список рекламы")
async def list_ads(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_ads"):
        return
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, text, interval_minutes, enabled FROM ads ORDER BY id")
    if not rows:
        await message.answer("Нет рекламных объявлений.")
        return
    text = "📢 Рекламные объявления:\n"
    for row in rows:
        status = "✅" if row['enabled'] else "❌"
        text += f"{status} ID {row['id']}: {row['text'][:50]}... (интервал {row['interval_minutes']} мин)\n"
    await message.answer(text)

@dp.message_handler(lambda message: message.text == "✏️ Редактировать рекламу")
async def edit_ad_start(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_ads"):
        return
    await message.answer("Введи ID рекламы для редактирования:", reply_markup=back_keyboard())
    await EditAd.ad_id.set()

@dp.message_handler(state=EditAd.ad_id)
async def edit_ad_id(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_ad_menu(message)
        return
    try:
        ad_id = int(message.text)
    except:
        await message.answer("❌ Введи число.")
        return
    async with db_pool.acquire() as conn:
        ad = await conn.fetchrow("SELECT * FROM ads WHERE id=$1", ad_id)
        if not ad:
            await message.answer("❌ Реклама не найдена.")
            await state.finish()
            return
    await state.update_data(ad_id=ad_id)
    await message.answer("Что хочешь изменить? (text/interval/target/enabled)")
    await EditAd.field.set()

@dp.message_handler(state=EditAd.field)
async def edit_ad_field(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_ad_menu(message)
        return
    field = message.text.lower()
    allowed = ['text', 'interval', 'target', 'enabled']
    if field not in allowed:
        await message.answer(f"❌ Можно изменить только: {', '.join(allowed)}")
        return
    await state.update_data(field=field)
    if field == 'enabled':
        await message.answer("Введи новое значение (True/False):")
    elif field == 'interval':
        await message.answer("Введи новый интервал (минуты):")
    else:
        await message.answer(f"Введи новое значение для {field}:")
    await EditAd.value.set()

@dp.message_handler(state=EditAd.value)
async def edit_ad_value(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_ad_menu(message)
        return
    data = await state.get_data()
    ad_id = data['ad_id']
    field = data['field']

    if field == 'enabled':
        val = message.text.lower() in ['true', '1', 'да', 'yes']
    elif field == 'interval':
        try:
            val = int(message.text)
            if val <= 0:
                raise ValueError
        except:
            await message.answer("❌ Введи целое положительное число.")
            return
    else:
        val = message.text

    try:
        async with db_pool.acquire() as conn:
            await conn.execute(f"UPDATE ads SET {field}=$1 WHERE id=$2", val, ad_id)
        await message.answer("✅ Реклама обновлена.", reply_markup=admin_ad_keyboard())
    except Exception as e:
        logging.error(f"Edit ad error: {e}", exc_info=True)
        await message.answer("❌ Ошибка.")
    await state.finish()

@dp.message_handler(lambda message: message.text == "❌ Удалить рекламу")
async def delete_ad_start(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_ads"):
        return
    await message.answer("Введи ID рекламы для удаления:", reply_markup=back_keyboard())
    await DeleteAd.ad_id.set()

@dp.message_handler(state=DeleteAd.ad_id)
async def delete_ad_finish(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_ad_menu(message)
        return
    try:
        ad_id = int(message.text)
    except:
        await message.answer("❌ Введи число.")
        return
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM ads WHERE id=$1", ad_id)
    await message.answer("✅ Реклама удалена, если существовала.", reply_markup=admin_ad_keyboard())
    await state.finish()

# ==================== УПРАВЛЕНИЕ БИРЖЕЙ ====================
@dp.message_handler(lambda message: message.text == "💼 Биржа")
async def admin_exchange_menu(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_exchange"):
        await message.answer("❌ Недостаточно прав.")
        return
    await send_with_media(message.chat.id, "Управление биткоин-биржей:", media_key='admin_exchange', reply_markup=admin_exchange_keyboard())

@dp.message_handler(lambda message: message.text == "📋 Активные заявки")
async def admin_list_orders(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_exchange"):
        return
    orders = await get_active_orders()
    if not orders:
        await message.answer("Нет активных заявок.")
        return
    text = "📋 Активные заявки:\n\n"
    for o in orders:
        text += f"ID {o['id']}: {'📈' if o['type']=='buy' else '📉'} {o['amount']:.4f} BTC @ {o['price']} $ (пользователь {o['user_id']})\n"
    await message.answer(text, reply_markup=admin_exchange_keyboard())

@dp.message_handler(lambda message: message.text == "❌ Удалить заявку (по ID)")
async def admin_remove_order_start(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_exchange"):
        return
    await message.answer("Введи ID заявки для удаления:", reply_markup=back_keyboard())
    await CancelBitcoinOrder.order_id.set()

@dp.message_handler(state=CancelBitcoinOrder.order_id)
async def admin_remove_order_finish(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_exchange_menu(message)
        return
    try:
        order_id = int(message.text)
    except:
        await message.answer("❌ Введи число.")
        return
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            order = await conn.fetchrow("SELECT * FROM bitcoin_orders WHERE id=$1 AND status='active'", order_id)
            if not order:
                await message.answer("❌ Заявка не найдена или уже не активна.")
                await state.finish()
                return
            total_locked = float(order['total_locked'])
            if order['type'] == 'sell':
                await update_user_bitcoin(order['user_id'], total_locked, conn=conn)
            else:
                await update_user_balance(order['user_id'], total_locked, conn=conn)
            await conn.execute("UPDATE bitcoin_orders SET status='cancelled' WHERE id=$1", order_id)
    await message.answer(f"✅ Заявка {order_id} отменена, средства возвращены пользователю.")
    await state.finish()

@dp.message_handler(lambda message: message.text == "📊 История сделок")
async def admin_trade_history(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_exchange"):
        return
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM bitcoin_trades ORDER BY traded_at DESC LIMIT 50")
    if not rows:
        await message.answer("Нет сделок.")
        return
    text = "📊 Последние сделки:\n\n"
    for r in rows:
        text += f"ID {r['id']}: {float(r['amount']):.4f} BTC @ {r['price']} $ (покупатель {r['buyer_id']}, продавец {r['seller_id']}) в {r['traded_at'].strftime('%Y-%m-%d %H:%M')}\n"
    await message.answer(text, reply_markup=admin_exchange_keyboard())
  # ==================== УПРАВЛЕНИЕ БИЗНЕСАМИ ====================
@dp.message_handler(lambda message: message.text == "🏪 Бизнесы")
async def admin_business_menu(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_businesses"):
        await message.answer("❌ Недостаточно прав.")
        return
    await send_with_media(message.chat.id, "Управление бизнесами:", media_key='admin_business', reply_markup=admin_business_keyboard())

@dp.message_handler(lambda message: message.text == "📋 Список бизнесов")
async def admin_list_businesses(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_businesses"):
        return
    types = await get_business_type_list(only_available=False)
    if not types:
        await message.answer("Нет типов бизнесов.")
        return
    text = "🏪 Типы бизнесов:\n\n"
    for bt in types:
        available = "✅" if bt['available'] else "❌"
        text += f"{available} ID {bt['id']}: {bt['emoji']} {bt['name']}\n"
        text += f"  Цена: {bt['base_price_btc']:.2f} BTC, доход: {bt['base_income_cents']} центов/час\n"
        text += f"  Описание: {bt['description']}\n"
        text += f"  Макс. уровень: {bt['max_level']}\n\n"
    await message.answer(text, reply_markup=admin_business_keyboard())

@dp.message_handler(lambda message: message.text == "➕ Добавить бизнес")
async def add_business_start(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_businesses"):
        return
    await message.answer("Введи название бизнеса:", reply_markup=back_keyboard())
    await AddBusiness.name.set()

@dp.message_handler(state=AddBusiness.name)
async def add_business_name(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_business_menu(message)
        return
    await state.update_data(name=message.text)
    await message.answer("Введи эмодзи для бизнеса (один символ):")
    await AddBusiness.next()

@dp.message_handler(state=AddBusiness.emoji)
async def add_business_emoji(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_business_menu(message)
        return
    await state.update_data(emoji=message.text)
    await message.answer("Введи цену в BTC (можно дробную):")
    await AddBusiness.next()

@dp.message_handler(state=AddBusiness.price)
async def add_business_price(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_business_menu(message)
        return
    try:
        price = float(message.text)
        if price <= 0:
            raise ValueError
        price = round(price, 2)
        max_input = await get_setting_float("max_input_number")
        if price > max_input:
            await message.answer(f"❌ Цена слишком большая (максимум {max_input:.2f}).")
            return
    except:
        await message.answer("❌ Введи положительное число.")
        return
    await state.update_data(price=price)
    await message.answer("Введи базовый доход в центах в час (целое число):")
    await AddBusiness.next()

@dp.message_handler(state=AddBusiness.income)
async def add_business_income(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_business_menu(message)
        return
    try:
        income = int(message.text)
        if income <= 0:
            raise ValueError
    except:
        await message.answer("❌ Введи положительное целое число.")
        return
    await state.update_data(income=income)
    await message.answer("Введи описание бизнеса:")
    await AddBusiness.next()

@dp.message_handler(state=AddBusiness.description)
async def add_business_description(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_business_menu(message)
        return
    await state.update_data(description=message.text)
    await message.answer("Введи максимальный уровень прокачки (целое число):")
    await AddBusiness.next()

@dp.message_handler(state=AddBusiness.max_level)
async def add_business_max_level(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_business_menu(message)
        return
    try:
        max_level = int(message.text)
        if max_level < 1:
            raise ValueError
    except:
        await message.answer("❌ Введи положительное целое число.")
        return
    data = await state.get_data()
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO business_types (name, emoji, base_price_btc, base_income_cents, description, max_level, available) VALUES ($1, $2, $3, $4, $5, $6, $7)",
                data['name'], data['emoji'], data['price'], data['income'], data['description'], max_level, True
            )
        await message.answer("✅ Бизнес успешно добавлен!", reply_markup=admin_business_keyboard())
    except asyncpg.UniqueViolationError:
        await message.answer("❌ Бизнес с таким названием уже существует.")
    except Exception as e:
        logging.error(f"Add business error: {e}", exc_info=True)
        await message.answer("❌ Ошибка при добавлении бизнеса.")
    await state.finish()

@dp.message_handler(lambda message: message.text == "✏️ Редактировать бизнес")
async def edit_business_start(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_businesses"):
        return
    await message.answer("Введи ID бизнеса для редактирования:", reply_markup=back_keyboard())
    await EditBusiness.business_id.set()

@dp.message_handler(state=EditBusiness.business_id)
async def edit_business_id(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_business_menu(message)
        return
    try:
        bid = int(message.text)
    except:
        await message.answer("❌ Введи число.")
        return
    biz = await get_business_type(bid)
    if not biz:
        await message.answer("❌ Бизнес с таким ID не найден.")
        return
    await state.update_data(business_id=bid)
    await message.answer("Что хочешь изменить? (name/emoji/price/income/description/max_level/available)")
    await EditBusiness.field.set()

@dp.message_handler(state=EditBusiness.field)
async def edit_business_field(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_business_menu(message)
        return
    field = message.text.lower()
    allowed = ['name', 'emoji', 'price', 'income', 'description', 'max_level', 'available']
    if field not in allowed:
        await message.answer(f"❌ Можно изменить только: {', '.join(allowed)}")
        return
    await state.update_data(field=field)
    if field == 'available':
        await message.answer("Введи новое значение (True/False):")
    elif field == 'price':
        await message.answer("Введи новую цену в BTC (дробное число):")
    elif field == 'income':
        await message.answer("Введи новый базовый доход в центах/час (целое число):")
    elif field == 'max_level':
        await message.answer("Введи новый максимальный уровень (целое число):")
    else:
        await message.answer(f"Введи новое значение для {field}:")
    await EditBusiness.value.set()

@dp.message_handler(state=EditBusiness.value)
async def edit_business_value(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_business_menu(message)
        return
    data = await state.get_data()
    bid = data['business_id']
    field = data['field']

    if field == 'available':
        val = message.text.lower() in ['true', '1', 'да', 'yes']
    elif field == 'price':
        try:
            val = float(message.text)
            if val <= 0:
                raise ValueError
            val = round(val, 2)
            max_input = await get_setting_float("max_input_number")
            if val > max_input:
                await message.answer(f"❌ Цена слишком большая (максимум {max_input:.2f}).")
                return
        except:
            await message.answer("❌ Введи положительное число.")
            return
    elif field in ['income', 'max_level']:
        try:
            val = int(message.text)
            if val <= 0:
                raise ValueError
        except:
            await message.answer("❌ Введи положительное целое число.")
            return
    else:
        val = message.text

    try:
        async with db_pool.acquire() as conn:
            column_map = {
                'name': 'name',
                'emoji': 'emoji',
                'price': 'base_price_btc',
                'income': 'base_income_cents',
                'description': 'description',
                'max_level': 'max_level',
                'available': 'available'
            }
            db_column = column_map[field]
            await conn.execute(f"UPDATE business_types SET {db_column}=$1 WHERE id=$2", val, bid)
        await message.answer(f"✅ Поле {field} обновлено.", reply_markup=admin_business_keyboard())
    except Exception as e:
        logging.error(f"Edit business error: {e}", exc_info=True)
        await message.answer("❌ Ошибка при обновлении.")
    await state.finish()

@dp.message_handler(lambda message: message.text == "🔄 Переключить доступность")
async def toggle_business_start(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_businesses"):
        return
    await message.answer("Введи ID бизнеса, доступность которого нужно переключить:", reply_markup=back_keyboard())
    await ToggleBusiness.business_id.set()

@dp.message_handler(state=ToggleBusiness.business_id)
async def toggle_business_confirm(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_business_menu(message)
        return
    try:
        bid = int(message.text)
    except:
        await message.answer("❌ Введи число.")
        return
    biz = await get_business_type(bid)
    if not biz:
        await message.answer("❌ Бизнес не найден.")
        await state.finish()
        return
    current = biz['available']
    new_status = not current
    await state.update_data(business_id=bid, new_status=new_status)
    await message.answer(f"Текущий статус: {'✅ доступен' if current else '❌ недоступен'}. Переключить на {'❌ недоступен' if current else '✅ доступен'}? (да/нет)")
    await ToggleBusiness.confirm.set()

@dp.message_handler(state=ToggleBusiness.confirm)
async def toggle_business_finish(message: types.Message, state: FSMContext):
    if message.text.lower() == 'нет' or message.text == "◀️ Назад":
        await state.finish()
        await admin_business_menu(message)
        return
    if message.text.lower() == 'да':
        data = await state.get_data()
        bid = data['business_id']
        new_status = data['new_status']
        try:
            async with db_pool.acquire() as conn:
                await conn.execute("UPDATE business_types SET available=$1 WHERE id=$2", new_status, bid)
            await message.answer(f"✅ Доступность бизнеса изменена на {'✅ доступен' if new_status else '❌ недоступен'}.", reply_markup=admin_business_keyboard())
        except Exception as e:
            logging.error(f"Toggle business error: {e}", exc_info=True)
            await message.answer("❌ Ошибка.")
        await state.finish()
    else:
        await message.answer("Введи 'да' или 'нет'.")

# ==================== УПРАВЛЕНИЕ МЕДИА ====================
@dp.message_handler(lambda message: message.text == "🖼 Медиа")
async def admin_media_menu(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_media"):
        await message.answer("❌ Недостаточно прав.")
        return
    await send_with_media(message.chat.id, "Управление медиафайлами:", media_key='admin_media', reply_markup=admin_media_keyboard())

@dp.message_handler(lambda message: message.text == "➕ Добавить медиа")
async def add_media_start(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_media"):
        return
    await message.answer("Введи ключ (например, 'profile', 'casino', 'welcome'):", reply_markup=back_keyboard())
    await AddMedia.key.set()

@dp.message_handler(state=AddMedia.key)
async def add_media_key(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_media_menu(message)
        return
    key = message.text.strip()
    await state.update_data(key=key)
    await message.answer("Отправь фото (или документ/видео):")
    await AddMedia.file.set()

@dp.message_handler(state=AddMedia.file, content_types=['photo', 'document', 'video'])
async def add_media_file(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_media_menu(message)
        return
    file_id = None
    if message.photo:
        file_id = message.photo[-1].file_id
    elif message.document:
        file_id = message.document.file_id
    elif message.video:
        file_id = message.video.file_id
    else:
        await message.answer("❌ Отправь фото, документ или видео.")
        return
    data = await state.get_data()
    key = data['key']
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO media (key, file_id, description) VALUES ($1, $2, $3) ON CONFLICT (key) DO UPDATE SET file_id=$2",
                key, file_id, f"Медиа для {key}"
            )
        await message.answer(f"✅ Медиа с ключом '{key}' сохранено.")
    except Exception as e:
        logging.error(f"Add media error: {e}", exc_info=True)
        await message.answer("❌ Ошибка сохранения.")
    await state.finish()
    await admin_media_menu(message)

@dp.message_handler(lambda message: message.text == "➖ Удалить медиа")
async def remove_media_start(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_media"):
        return
    await message.answer("Введи ключ медиа для удаления:", reply_markup=back_keyboard())
    await RemoveMedia.key.set()

@dp.message_handler(state=RemoveMedia.key)
async def remove_media_finish(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_media_menu(message)
        return
    key = message.text.strip()
    try:
        async with db_pool.acquire() as conn:
            await conn.execute("DELETE FROM media WHERE key=$1", key)
        await message.answer(f"✅ Медиа с ключом '{key}' удалено, если существовало.")
    except Exception as e:
        logging.error(f"Remove media error: {e}", exc_info=True)
        await message.answer("❌ Ошибка.")
    await state.finish()

@dp.message_handler(lambda message: message.text == "📋 Список медиа")
async def list_media(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "manage_media"):
        return
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT key, description FROM media ORDER BY key")
    if not rows:
        await message.answer("Нет сохранённых медиа.")
        return
    text = "🖼 Сохранённые медиа:\n\n"
    for row in rows:
        text += f"• {row['key']}: {row['description']}\n"
    await message.answer(text, reply_markup=admin_media_keyboard())

# ==================== СТАТИСТИКА ====================
@dp.message_handler(lambda message: message.text == "📊 Статистика")
async def stats_handler(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "view_stats"):
        await message.answer("❌ Недостаточно прав.")
        return
    try:
        async with db_pool.acquire() as conn:
            users = await conn.fetchval("SELECT COUNT(*) FROM users")
            total_balance = await conn.fetchval("SELECT SUM(balance) FROM users") or 0.0
            total_reputation = await conn.fetchval("SELECT SUM(reputation) FROM users") or 0
            total_spent = await conn.fetchval("SELECT SUM(total_spent) FROM users") or 0.0
            total_bitcoin = await conn.fetchval("SELECT SUM(bitcoin_balance) FROM users") or 0.0
            active_giveaways = await conn.fetchval("SELECT COUNT(*) FROM giveaways WHERE status='active'") or 0
            shop_items = await conn.fetchval("SELECT COUNT(*) FROM shop_items") or 0
            purchases_pending = await conn.fetchval("SELECT COUNT(*) FROM purchases WHERE status='pending'") or 0
            total_thefts = await conn.fetchval("SELECT SUM(theft_attempts) FROM users") or 0
            total_thefts_success = await conn.fetchval("SELECT SUM(theft_success) FROM users") or 0
            promos = await conn.fetchval("SELECT COUNT(*) FROM promocodes") or 0
            banned = await conn.fetchval("SELECT COUNT(*) FROM banned_users") or 0
            total_bosses = await conn.fetchval("SELECT COUNT(*) FROM bosses") or 0
            active_bosses = await conn.fetchval("SELECT COUNT(*) FROM bosses WHERE status='active'") or 0
            confirmed_chats = await conn.fetchval("SELECT COUNT(*) FROM confirmed_chats") or 0
            active_orders = await conn.fetchval("SELECT COUNT(*) FROM bitcoin_orders WHERE status='active'") or 0
            total_businesses = await conn.fetchval("SELECT COUNT(*) FROM user_businesses") or 0
        text = (
            f"📊 <b>Статистика:</b>\n"
            f"👥 Пользователей: {users}\n"
            f"💰 Всего баксов: {float(total_balance):.2f}\n"
            f"₿ Всего биткоинов: {float(total_bitcoin):.4f}\n"
            f"⭐️ Всего репутации: {total_reputation}\n"
            f"💸 Всего потрачено: {float(total_spent):.2f}\n"
            f"🎁 Активных розыгрышей: {active_giveaways}\n"
            f"🛒 Товаров в магазине: {shop_items}\n"
            f"🛍️ Ожидающих покупок: {purchases_pending}\n"
            f"🔫 Всего ограблений: {total_thefts} (успешно: {total_thefts_success})\n"
            f"🎫 Промокодов создано: {promos}\n"
            f"⛔ Заблокировано: {banned}\n"
            f"👾 Всего боссов: {total_bosses} (активных: {active_bosses})\n"
            f"✅ Подтверждённых чатов: {confirmed_chats}\n"
            f"💼 Активных заявок на бирже: {active_orders}\n"
            f"🏪 Всего бизнесов у игроков: {total_businesses}"
        )
        permissions = await get_admin_permissions(message.from_user.id)
        await message.answer(text, reply_markup=admin_main_keyboard(permissions))
    except Exception as e:
        logging.error(f"Stats error: {e}", exc_info=True)
        await message.answer("❌ Ошибка получения статистики.")

# ==================== РАССЫЛКА ====================
@dp.message_handler(lambda message: message.text == "📢 Рассылка")
async def broadcast_start(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "broadcast"):
        await message.answer("❌ Недостаточно прав.")
        return
    await message.answer("Отправь сообщение для рассылки (текст, фото, видео или документ).", reply_markup=back_keyboard())
    await Broadcast.media.set()

@dp.message_handler(state=Broadcast.media, content_types=['text', 'photo', 'video', 'document'])
async def broadcast_media(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        permissions = await get_admin_permissions(message.from_user.id)
        await message.answer("Панель администратора:", reply_markup=admin_main_keyboard(permissions))
        return

    content = {}
    if message.text:
        content['type'] = 'text'
        content['text'] = message.text
    elif message.photo:
        content['type'] = 'photo'
        content['file_id'] = message.photo[-1].file_id
        content['caption'] = message.caption or ""
    elif message.video:
        content['type'] = 'video'
        content['file_id'] = message.video.file_id
        content['caption'] = message.caption or ""
    elif message.document:
        content['type'] = 'document'
        content['file_id'] = message.document.file_id
        content['caption'] = message.caption or ""
    else:
        await message.answer("Неподдерживаемый тип.")
        return

    await state.finish()

    status_msg = await message.answer("⏳ Рассылка начата... Это может занять некоторое время.")

    async with db_pool.acquire() as conn:
        users = await conn.fetch("SELECT user_id FROM users")
        users = [r['user_id'] for r in users]

    sent = 0
    failed = 0
    total = len(users)

    for i, uid in enumerate(users):
        if await is_banned(uid):
            continue
        try:
            if content['type'] == 'text':
                await bot.send_message(uid, content['text'])
            elif content['type'] == 'photo':
                await bot.send_photo(uid, content['file_id'], caption=content['caption'])
            elif content['type'] == 'video':
                await bot.send_video(uid, content['file_id'], caption=content['caption'])
            elif content['type'] == 'document':
                await bot.send_document(uid, content['file_id'], caption=content['caption'])
            sent += 1
        except (BotBlocked, UserDeactivated, ChatNotFound):
            failed += 1
        except RetryAfter as e:
            await asyncio.sleep(e.timeout)
            try:
                if content['type'] == 'text':
                    await bot.send_message(uid, content['text'])
                else:
                    if content['type'] == 'photo':
                        await bot.send_photo(uid, content['file_id'], caption=content['caption'])
                    elif content['type'] == 'video':
                        await bot.send_video(uid, content['file_id'], caption=content['caption'])
                    elif content['type'] == 'document':
                        await bot.send_document(uid, content['file_id'], caption=content['caption'])
                sent += 1
            except:
                failed += 1
        except Exception as e:
            failed += 1

        if (i + 1) % 10 == 0:
            try:
                await status_msg.edit_text(f"⏳ Прогресс: {i+1}/{total}\n✅ Отправлено: {sent}\n❌ Ошибок: {failed}")
            except:
                pass

        await asyncio.sleep(0.05)

    await status_msg.edit_text(f"✅ Рассылка завершена!\n📊 Отправлено: {sent}\n❌ Ошибок: {failed}\n👥 Всего: {total}")

# ==================== ОЧИСТКА СТАРЫХ ЗАПИСЕЙ ====================
@dp.message_handler(lambda message: message.text == "🧹 Очистка")
async def cleanup_old_data(message: types.Message):
    if not await check_admin_permissions(message.from_user.id, "cleanup"):
        return
    await perform_cleanup(manual=True)
    await message.answer("✅ Старые записи очищены согласно настройкам.")
