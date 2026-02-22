import asyncio
import logging
import random
from datetime import datetime, timedelta

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot_instance import dp, bot
from db import (
    db_pool, ensure_user_exists, is_banned, is_admin, is_chat_confirmed,
    get_user_balance, update_user_balance, get_user_bitcoin, update_user_bitcoin,
    get_user_stats, get_user_level, get_user_reputation, add_exp,
    get_setting, get_setting_int, get_setting_float,
    check_smuggle_cooldown, set_smuggle_cooldown,
    can_fight, set_fight_cooldown, add_chat_authority, log_fight,
    calculate_fight_damage, calculate_fight_authority,
    is_critical, is_counter, get_media_file_id,
    create_chat_confirmation_request, get_confirmed_chats, get_pending_chat_requests,
    add_confirmed_chat, update_chat_request_status
)
from helpers import (
    safe_send_message, send_with_media, auto_delete_reply, auto_delete_message,
    get_random_phrase, format_time_remaining, progress_bar
)
from constants import (
    FIGHT_HIT_PHRASES, FIGHT_CRIT_PHRASES, FIGHT_COUNTER_PHRASES,
    SMUGGLE_START_PHRASES, SMUGGLE_CARGO, SUPER_ADMINS,
    ITEMS_PER_PAGE
)
from keyboards import confirm_chat_inline, subscription_inline

# ==================== БОЙ В ЧАТАХ (/fight) ====================
@dp.message_handler(commands=['fight'], chat_type=[types.ChatType.GROUP, types.ChatType.SUPERGROUP])
async def fight_command(message: types.Message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    if not await is_chat_confirmed(chat_id):
        await auto_delete_reply(message, "❌ Этот чат не активирован. Используй /activate_chat для запроса активации.")
        return

    if await is_banned(user_id):
        await auto_delete_reply(message, "⛔ Вы заблокированы в боте.")
        return

    await ensure_user_exists(user_id, message.from_user.username, message.from_user.first_name)

    ok, remaining = await can_fight(chat_id, user_id)
    if not ok:
        time_str = format_time_remaining(remaining)
        await auto_delete_reply(message, f"⏳ Ты ещё не восстановился. Подожди {time_str}.")
        return

    stats = await get_user_stats(user_id)
    strength = stats['strength']
    agility = stats['agility']
    defense = stats['defense']

    damage = await calculate_fight_damage(strength)
    authority = await calculate_fight_authority()
    crit = is_critical(strength, agility)
    counter = is_counter(defense)

    if crit:
        damage = int(damage * 1.5)
        phrase_template = FIGHT_CRIT_PHRASES
    else:
        phrase_template = FIGHT_HIT_PHRASES

    outcome = "hit"
    if counter:
        loss = damage // 2
        balance = await get_user_balance(user_id)
        if balance >= loss:
            await update_user_balance(user_id, -loss)
            phrase = get_random_phrase(FIGHT_COUNTER_PHRASES, damage=loss)
            outcome = "counter"
            authority = 0
        else:
            phrase = get_random_phrase(FIGHT_HIT_PHRASES, damage=damage, authority=authority)
    else:
        await add_chat_authority(chat_id, user_id, authority, damage)
        await update_user_balance(user_id, damage)
        btc_reward = await get_setting_int("fight_bitcoin_reward")
        if btc_reward > 0:
            await update_user_bitcoin(user_id, float(btc_reward))
        phrase = get_random_phrase(phrase_template, damage=damage, authority=authority)

    exp = await get_setting_int("exp_per_fight")
    await add_exp(user_id, exp)

    await log_fight(chat_id, user_id, damage, authority, outcome)
    await set_fight_cooldown(chat_id, user_id)

    await auto_delete_reply(message, phrase, delete_seconds=30)

# ==================== КОНТРАБАНДА (/smuggle) ====================
@dp.message_handler(commands=['smuggle'], chat_type=[types.ChatType.GROUP, types.ChatType.SUPERGROUP])
async def smuggle_command(message: types.Message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    if not await is_chat_confirmed(chat_id):
        await auto_delete_reply(message, "❌ Этот чат не активирован. Используй /activate_chat для запроса активации.")
        return

    if await is_banned(user_id):
        await auto_delete_reply(message, "⛔ Вы заблокированы в боте.")
        return

    await ensure_user_exists(user_id, message.from_user.username, message.from_user.first_name)

    ok, remaining = await check_smuggle_cooldown(user_id)
    if not ok:
        time_str = format_time_remaining(remaining)
        await auto_delete_reply(message, f"⏳ Контрабанда ещё не вернулась. Подожди {time_str}.")
        return

    cost = 0
    balance = await get_user_balance(user_id)
    if balance < cost:
        await auto_delete_reply(message, "❌ Недостаточно баксов для снаряжения рейса.")
        return

    min_dur = await get_setting_int("smuggle_min_duration")
    max_dur = await get_setting_int("smuggle_max_duration")
    duration = random.randint(min_dur, max_dur)
    end_time = datetime.now() + timedelta(minutes=duration)

    cargo = random.choice(SMUGGLE_CARGO)

    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO smuggle_runs (user_id, chat_id, start_time, end_time) VALUES ($1, $2, $3, $4)",
            user_id, chat_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), end_time.strftime("%Y-%m-%d %H:%M:%S")
        )
        if cost > 0:
            await update_user_balance(user_id, -cost, conn=conn)

    end_time_str = end_time.strftime("%H:%M")
    phrase = get_random_phrase(SMUGGLE_START_PHRASES, cargo=cargo, end_time=end_time_str)
    await auto_delete_reply(message, phrase, delete_seconds=60)

# ==================== АКТИВАЦИЯ ЧАТА (/activate_chat) ====================
@dp.message_handler(commands=['activate_chat'], chat_type=[types.ChatType.GROUP, types.ChatType.SUPERGROUP])
async def activate_chat_command(message: types.Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    chat_title = message.chat.title
    chat_type = message.chat.type

    if await is_banned(user_id):
        await auto_delete_reply(message, "⛔ Вы заблокированы в боте.")
        return

    if await is_chat_confirmed(chat_id):
        await auto_delete_reply(message, "✅ Этот чат уже активирован.")
        return

    await create_chat_confirmation_request(chat_id, chat_title, chat_type, user_id)

    user_name = message.from_user.full_name
    text = f"📩 Запрос на активацию чата:\nНазвание: {chat_title}\nID: {chat_id}\nОт пользователя: {user_name}"
    kb = confirm_chat_inline(chat_id)

    admins = SUPER_ADMINS.copy()
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id FROM admins")
        for r in rows:
            admins.append(r['user_id'])

    for admin_id in admins:
        await safe_send_message(admin_id, text, reply_markup=kb)

    await auto_delete_reply(message, "✅ Запрос отправлен администраторам. Ожидайте подтверждения.")
  # ==================== ОБРАБОТЧИКИ ПОДТВЕРЖДЕНИЯ ЧАТОВ (ИНЛАЙН) ====================
@dp.callback_query_handler(lambda c: c.data.startswith("confirm_chat_"))
async def confirm_chat_callback(callback: types.CallbackQuery):
    await callback.answer()
    if not await is_admin(callback.from_user.id):
        await callback.message.answer("❌ Недостаточно прав.")
        return
    chat_id = int(callback.data.split("_")[2])
    async with db_pool.acquire() as conn:
        req = await conn.fetchrow("SELECT * FROM chat_confirmation_requests WHERE chat_id=$1 AND status='pending'", chat_id)
        if not req:
            await callback.message.edit_text("❌ Запрос уже обработан.")
            return
        await add_confirmed_chat(chat_id, req['title'], req['type'], callback.from_user.id)
        await update_chat_request_status(chat_id, 'approved')
        await safe_send_message(req['requested_by'], f"✅ Ваш чат «{req['title']}» активирован!")
    await callback.message.edit_text(f"✅ Чат {chat_id} подтверждён.")

@dp.callback_query_handler(lambda c: c.data.startswith("reject_chat_"))
async def reject_chat_callback(callback: types.CallbackQuery):
    await callback.answer()
    if not await is_admin(callback.from_user.id):
        await callback.message.answer("❌ Недостаточно прав.")
        return
    chat_id = int(callback.data.split("_")[2])
    async with db_pool.acquire() as conn:
        req = await conn.fetchrow("SELECT * FROM chat_confirmation_requests WHERE chat_id=$1 AND status='pending'", chat_id)
        if not req:
            await callback.message.edit_text("❌ Запрос уже обработан.")
            return
        await update_chat_request_status(chat_id, 'rejected')
        await safe_send_message(req['requested_by'], f"❌ Ваш запрос на активацию чата «{req['title']}» отклонён.")
    await callback.message.edit_text(f"❌ Запрос для чата {chat_id} отклонён.")

# ==================== ТОП ЧАТА (/top) ====================
@dp.message_handler(commands=['top'], chat_type=[types.ChatType.GROUP, types.ChatType.SUPERGROUP])
async def chat_top_command(message: types.Message):
    chat_id = message.chat.id
    args = message.get_args().split()
    order = args[0] if args else 'authority'
    page = int(args[1]) if len(args) > 1 and args[1].isdigit() else 1

    if order not in ['authority', 'damage', 'fights']:
        order = 'authority'

    offset = (page - 1) * ITEMS_PER_PAGE
    async with db_pool.acquire() as conn:
        if order == 'authority':
            order_by = 'authority DESC'
        elif order == 'damage':
            order_by = 'total_damage DESC'
        else:
            order_by = 'fights DESC'

        total = await conn.fetchval("SELECT COUNT(*) FROM chat_authority WHERE chat_id=$1", chat_id)
        rows = await conn.fetch(
            f"SELECT user_id, authority, total_damage, fights FROM chat_authority WHERE chat_id=$1 ORDER BY {order_by} LIMIT $2 OFFSET $3",
            chat_id, ITEMS_PER_PAGE, offset
        )

    if not rows:
        await auto_delete_reply(message, "В этом чате пока нет статистики боёв.")
        return

    title_map = {'authority': 'авторитету', 'damage': 'урону', 'fights': 'количеству боёв'}
    text = f"🏆 Топ чата по {title_map[order]} (страница {page}):\n\n"
    for idx, row in enumerate(rows, start=offset+1):
        try:
            member = await bot.get_chat_member(chat_id, row['user_id'])
            name = member.user.first_name if member else f"ID {row['user_id']}"
        except:
            name = f"ID {row['user_id']}"
        
        if order == 'authority':
            value = row['authority']
        elif order == 'damage':
            value = row['total_damage']
        else:
            value = row['fights']
        text += f"{idx}. {name} – {value}\n"

    kb = InlineKeyboardMarkup()
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton("⬅️", callback_data=f"chat_top_page_{order}_{page-1}"))
    nav_row.append(InlineKeyboardButton(f"{page}", callback_data="noop"))
    if offset + ITEMS_PER_PAGE < total:
        nav_row.append(InlineKeyboardButton("➡️", callback_data=f"chat_top_page_{order}_{page+1}"))
    kb.row(*nav_row)
    kb.row(
        InlineKeyboardButton("📊 По авторитету", callback_data="chat_top_authority_1"),
        InlineKeyboardButton("💥 По урону", callback_data="chat_top_damage_1"),
        InlineKeyboardButton("⚔️ По боям", callback_data="chat_top_fights_1")
    )

    await auto_delete_reply(message, text, reply_markup=kb, delete_seconds=60)

@dp.callback_query_handler(lambda c: c.data.startswith("chat_top_"))
async def chat_top_navigation(callback: types.CallbackQuery):
    await callback.answer()
    parts = callback.data.split("_")
    if parts[2] == 'page':
        order = parts[3]
        page = int(parts[4])
    else:
        order = parts[2]
        page = int(parts[3])
    
    fake_message = callback.message
    fake_message.text = f"/top {order} {page}"
    await chat_top_command(fake_message)
    await callback.message.delete()

# ==================== ПОМОЩЬ В ГРУППЕ (/mlb_help) ====================
@dp.message_handler(commands=['mlb_help'], chat_type=[types.ChatType.GROUP, types.ChatType.SUPERGROUP])
async def mlb_help_group(message: types.Message):
    text = (
        "📚 <b>Команды для групп</b>\n\n"
        "/fight – атаковать банду, получить авторитет и баксы\n"
        "/smuggle – отправиться в контрабандный рейс\n"
        "/activate_chat – запросить активацию чата у администраторов\n"
        "/top [authority/damage/fights] [страница] – топ игроков чата\n"
        "/mlb_help – это сообщение"
    )
    await auto_delete_reply(message, text, delete_seconds=60)
