import asyncio
import logging
import random
from datetime import datetime, timedelta

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot_instance import dp, bot
from db import (
    db_pool, ensure_user_exists, is_banned, is_admin, has_permission,
    get_user_balance, update_user_balance, update_user_total_spent,
    get_user_reputation, update_user_reputation, get_user_bitcoin,
    update_user_bitcoin, get_user_authority, update_user_authority,
    get_user_level, add_exp, get_setting, get_setting_int, get_setting_float,
    get_random_user, find_user_by_input, check_global_cooldown, set_global_cooldown,
    get_media_file_id, check_subscription
)
from helpers import (
    safe_send_message, send_with_media, auto_delete_reply, auto_delete_message,
    get_random_phrase, notify_chats, progress_bar, format_time_remaining
)
from constants import (
    PURCHASE_PHRASES, BIG_PURCHASE_THRESHOLD, CHAT_PURCHASE_PHRASES,
    THEFT_CHOICE_PHRASES, THEFT_COOLDOWN_PHRASES, THEFT_NO_MONEY_PHRASES,
    THEFT_SUCCESS_PHRASES, THEFT_FAIL_PHRASES, THEFT_DEFENSE_PHRASES,
    THEFT_VICTIM_DEFENSE_PHRASES, ITEMS_PER_PAGE, SUPER_ADMINS
)
from keyboards import (
    main_menu_keyboard, back_keyboard, cancel_keyboard, subscription_inline,
    theft_choice_keyboard, purchase_action_keyboard, repeat_bet_keyboard,
    admin_main_keyboard, auction_list_keyboard, auction_detail_keyboard
)
from states import (
    PromoActivate, TheftTarget, AuctionBid
)

# ==================== МАГАЗИН ПОДАРКОВ ====================
@dp.message_handler(lambda message: message.text == "🛒 Магазин подарков")
async def shop_handler(message: types.Message):
    if message.chat.type != 'private':
        return
    user_id = message.from_user.id
    if await is_banned(user_id) and not await is_admin(user_id):
        return
    await ensure_user_exists(user_id, message.from_user.username, message.from_user.first_name)
    ok, not_subscribed = await check_subscription(user_id)
    if not ok:
        await message.answer("❗️ Сначала подпишись на каналы.", reply_markup=subscription_inline(not_subscribed))
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
            rows = await conn.fetch(
                "SELECT id, name, description, price, stock, photo_file_id FROM shop_items ORDER BY id LIMIT $1 OFFSET $2",
                ITEMS_PER_PAGE, offset
            )
        if not rows:
            await message.answer("🎁 В магазине пока нет подарков.")
            return
        text = f"🎁 Подарки (страница {page}):\n\n"
        kb = []
        for row in rows:
            item_id = row['id']
            name = row['name']
            desc = row['description']
            price = float(row['price'])
            stock = row['stock']
            stock_info = f" (в наличии: {stock})" if stock != -1 else ""
            text += f"🔹 {name}\n{desc}\n💰 {price:.2f} баксов{stock_info}\n\n"
            button_text = f"Купить {name}"
            kb.append([InlineKeyboardButton(text=button_text, callback_data=f"buy_{item_id}")])
        nav_buttons = []
        if page > 1:
            nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"shop_page_{page-1}"))
        if offset + ITEMS_PER_PAGE < total:
            nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"shop_page_{page+1}"))
        if nav_buttons:
            kb.append(nav_buttons)
        await send_with_media(message.chat.id, text, media_key='shop', reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    except Exception as e:
        logging.error(f"Shop error: {e}", exc_info=True)
        await message.answer("❌ Ошибка загрузки магазина.")

@dp.callback_query_handler(lambda c: c.data.startswith("shop_page_"))
async def shop_page_callback(callback: types.CallbackQuery):
    page = int(callback.data.split("_")[2])
    callback.message.text = f"🛒 Магазин подарков {page}"
    await shop_handler(callback.message)
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("buy_"))
async def buy_callback(callback: types.CallbackQuery):
    await callback.answer()

    parts = callback.data.split("_")
    if len(parts) != 2 or not parts[1].isdigit():
        return

    user_id = callback.from_user.id
    if await is_banned(user_id) and not await is_admin(user_id):
        await callback.message.answer("⛔ Вы заблокированы.")
        return
    await ensure_user_exists(user_id, callback.from_user.username, callback.from_user.first_name)
    ok, not_subscribed = await check_subscription(user_id)
    if not ok:
        await callback.message.edit_text("❗️ Сначала подпишись на каналы.", reply_markup=subscription_inline(not_subscribed))
        return
    item_id = int(callback.data.split("_")[1])
    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT name, price, stock FROM shop_items WHERE id=$1", item_id)
            if not row:
                await callback.message.answer("Товар не найден")
                return
            name, price, stock = row['name'], float(row['price']), row['stock']
            if stock != -1 and stock <= 0:
                await callback.message.answer("Товара нет в наличии!")
                return
            balance = await get_user_balance(user_id)
            if balance < price:
                await callback.message.answer("Не хватает баксов!")
                return
            async with conn.transaction():
                await update_user_balance(user_id, -price, conn=conn)
                await update_user_total_spent(user_id, price)
                await conn.execute(
                    "INSERT INTO purchases (user_id, item_id, purchase_date) VALUES ($1, $2, $3)",
                    user_id, item_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                )
                if stock != -1:
                    await conn.execute("UPDATE shop_items SET stock = stock - 1 WHERE id=$1", item_id)

        phrase = get_random_phrase(PURCHASE_PHRASES)
        await callback.message.answer(f"✅ Ты купил {name}! {phrase}")

        if await get_setting("chat_notify_big_purchase") == "1" and price >= BIG_PURCHASE_THRESHOLD:
            user = callback.from_user
            chat_phrase = get_random_phrase(CHAT_PURCHASE_PHRASES, name=user.first_name, item=name, price=price)
            await notify_chats(chat_phrase)

        asyncio.create_task(notify_admins_about_purchase(callback.from_user, name, price))
        await send_with_media(user_id, f"✅ Покупка совершена! {phrase}", media_key='purchase')
        await callback.message.delete()
    except Exception as e:
        logging.error(f"Purchase error: {e}", exc_info=True)
        await callback.message.answer("❌ Ошибка при покупке. Попробуй позже.")

async def notify_admins_about_purchase(user: types.User, item_name: str, price: float):
    admins = SUPER_ADMINS.copy()
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id FROM admins")
        for row in rows:
            admins.append(row['user_id'])
    for admin_id in admins:
        await safe_send_message(admin_id,
            f"🛒 Покупка: пользователь {user.full_name} (@{user.username})\n"
            f"<a href=\"tg://user?id={user.id}\">Ссылка</a> купил {item_name} за {price:.2f} баксов."
        )

# ==================== МОИ ПОКУПКИ ====================
@dp.message_handler(lambda message: message.text == "💰 Мои покупки")
async def my_purchases(message: types.Message):
    if message.chat.type != 'private':
        return
    user_id = message.from_user.id
    if await is_banned(user_id) and not await is_admin(user_id):
        return
    await ensure_user_exists(user_id, message.from_user.username, message.from_user.first_name)
    ok, not_subscribed = await check_subscription(user_id)
    if not ok:
        await message.answer("❗️ Сначала подпишись на каналы.", reply_markup=subscription_inline(not_subscribed))
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
            total = await conn.fetchval("SELECT COUNT(*) FROM purchases WHERE user_id=$1", user_id)
            rows = await conn.fetch(
                "SELECT p.id, s.name, p.purchase_date, p.status, p.admin_comment FROM purchases p "
                "JOIN shop_items s ON p.item_id = s.id WHERE p.user_id=$1 ORDER BY p.purchase_date DESC LIMIT $2 OFFSET $3",
                user_id, ITEMS_PER_PAGE, offset
            )
        if not rows:
            await message.answer("У тебя пока нет покупок.", reply_markup=main_menu_keyboard(await is_admin(user_id)))
            return
        text = f"📦 Твои покупки (страница {page}):\n\n"
        for row in rows:
            pid, name, date, status, comment = row['id'], row['name'], row['purchase_date'], row['status'], row['admin_comment']
            status_emoji = "⏳" if status == 'pending' else "✅" if status == 'completed' else "❌"
            text += f"{status_emoji} {name} от {date}\n"
            if comment:
                text += f"   Комментарий: {comment}\n"
            text += "\n"
        kb = []
        nav_buttons = []
        if page > 1:
            nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"mypurchases_page_{page-1}"))
        if offset + ITEMS_PER_PAGE < total:
            nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"mypurchases_page_{page+1}"))
        if nav_buttons:
            kb.append(nav_buttons)
        if kb:
            await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        else:
            await message.answer(text, reply_markup=main_menu_keyboard(await is_admin(user_id)))
    except Exception as e:
        logging.error(f"My purchases error: {e}", exc_info=True)
        await message.answer("❌ Ошибка загрузки покупок.")

@dp.callback_query_handler(lambda c: c.data.startswith("mypurchases_page_"))
async def mypurchases_page_callback(callback: types.CallbackQuery):
    page = int(callback.data.split("_")[2])
    callback.message.text = f"💰 Мои покупки {page}"
    await my_purchases(callback.message)
    await callback.answer()
  # ==================== ПРОМОКОД ====================
@dp.message_handler(lambda message: message.text == "🎟 Промокод")
async def promo_handler(message: types.Message):
    if message.chat.type != 'private':
        return
    user_id = message.from_user.id
    if await is_banned(user_id) and not await is_admin(user_id):
        return
    await ensure_user_exists(user_id, message.from_user.username, message.from_user.first_name)
    ok, not_subscribed = await check_subscription(user_id)
    if not ok:
        await message.answer("❗️ Сначала подпишись на каналы.", reply_markup=subscription_inline(not_subscribed))
        return
    await send_with_media(user_id, "Введи промокод:", media_key='promo', reply_markup=back_keyboard())
    await PromoActivate.code.set()

@dp.message_handler(state=PromoActivate.code)
async def promo_activate(message: types.Message, state: FSMContext):
    if message.chat.type != 'private':
        await state.finish()
        return
    if message.text == "◀️ Назад":
        await state.finish()
        await message.answer("Главное меню:", reply_markup=main_menu_keyboard(await is_admin(message.from_user.id)))
        return
    code = message.text.strip().upper()
    user_id = message.from_user.id
    ok, not_subscribed = await check_subscription(user_id)
    if not ok:
        await message.answer("❗️ Сначала подпишись на каналы.", reply_markup=subscription_inline(not_subscribed))
        await state.finish()
        return
    try:
        async with db_pool.acquire() as conn:
            already_used = await conn.fetchval(
                "SELECT 1 FROM promo_activations WHERE user_id=$1 AND promo_code=$2",
                user_id, code
            )
            if already_used:
                await message.answer("❌ Ты уже активировал этот промокод.")
                await state.finish()
                return
            row = await conn.fetchrow("SELECT reward, max_uses, used_count FROM promocodes WHERE code=$1", code)
            if not row:
                await message.answer("❌ Промокод не найден.")
                await state.finish()
                return
            reward = float(row['reward'])
            max_uses = row['max_uses']
            used = row['used_count']
            if used >= max_uses:
                await message.answer("❌ Промокод уже использован максимальное количество раз.")
                await state.finish()
                return
            async with conn.transaction():
                await update_user_balance(user_id, reward, conn=conn)
                await conn.execute("UPDATE promocodes SET used_count = used_count + 1 WHERE code=$1", code)
                await conn.execute(
                    "INSERT INTO promo_activations (user_id, promo_code, activated_at) VALUES ($1, $2, $3)",
                    user_id, code, datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                )
        await message.answer(
            f"✅ Промокод активирован! Ты получил {reward:.2f} баксов.",
            reply_markup=main_menu_keyboard(await is_admin(user_id))
        )
    except Exception as e:
        logging.error(f"Promo error: {e}", exc_info=True)
        await message.answer("❌ Ошибка активации промокода.")
    await state.finish()

# ==================== ОГРАБЛЕНИЕ ====================
async def get_theft_success_chance(attacker_id: int) -> float:
    base = await get_setting_float("theft_success_chance")
    rep = await get_user_reputation(attacker_id)
    bonus = float(await get_setting_float("reputation_theft_bonus")) * rep
    max_bonus = await get_setting_float("reputation_max_bonus_percent")
    bonus = min(bonus, max_bonus)
    return base + bonus

async def get_defense_chance(victim_id: int) -> float:
    base = await get_setting_float("theft_defense_chance")
    rep = await get_user_reputation(victim_id)
    bonus = float(await get_setting_float("reputation_defense_bonus")) * rep
    max_bonus = await get_setting_float("reputation_max_bonus_percent")
    bonus = min(bonus, max_bonus)
    return base + bonus

async def perform_theft(message: types.Message, robber_id: int, victim_id: int, cost: float = 0):
    success_chance = await get_theft_success_chance(robber_id)
    defense_chance = await get_defense_chance(victim_id)
    defense_penalty = await get_setting_int("theft_defense_penalty")
    min_amount = await get_setting_float("min_theft_amount")
    max_amount = await get_setting_float("max_theft_amount")
    bitcoin_reward = await get_setting_int("bitcoin_per_theft")

    try:
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                robber_balance = await get_user_balance(robber_id)
                if robber_balance is None:
                    await message.answer("❌ Ошибка: ваш профиль не найден.")
                    return
                if robber_balance < cost:
                    await message.answer(get_random_phrase(THEFT_NO_MONEY_PHRASES), reply_markup=main_menu_keyboard(await is_admin(robber_id)))
                    return

                victim_row = await conn.fetchrow("SELECT balance, username, first_name FROM users WHERE user_id=$1", victim_id)
                if not victim_row:
                    await message.answer("❌ Цель не найдена в базе.")
                    return
                victim_balance = float(victim_row['balance'])
                victim_username = victim_row['username']
                victim_first = victim_row['first_name']
                victim_name = victim_first if victim_first else str(victim_id)

                if cost > 0:
                    await update_user_balance(robber_id, -cost, conn=conn)
                    robber_balance -= cost

                defense_triggered = random.random() * 100 <= defense_chance
                if defense_triggered:
                    penalty = min(defense_penalty, robber_balance)
                    if penalty > 0:
                        await update_user_balance(robber_id, -penalty, conn=conn)
                        await update_user_balance(victim_id, penalty, conn=conn)
                    await conn.execute("UPDATE users SET theft_attempts = theft_attempts + 1, theft_failed = theft_failed + 1 WHERE user_id=$1", robber_id)
                    await conn.execute("UPDATE users SET theft_protected = theft_protected + 1 WHERE user_id=$1", victim_id)
                    await conn.execute("UPDATE users SET last_theft_time = $1 WHERE user_id=$2", datetime.now().strftime("%Y-%m-%d %H:%M:%S"), robber_id)

                    exp_defense = await get_setting_int("exp_per_theft_defense")
                    await add_exp(victim_id, exp_defense, conn=conn)
                    exp_fail = await get_setting_int("exp_per_theft_fail")
                    await add_exp(robber_id, exp_fail, conn=conn)

                    robber_phrase = get_random_phrase(THEFT_DEFENSE_PHRASES, target=victim_name, penalty=penalty)
                    victim_phrase = get_random_phrase(THEFT_VICTIM_DEFENSE_PHRASES, attacker=message.from_user.first_name, penalty=penalty)
                    await message.answer(robber_phrase, reply_markup=main_menu_keyboard(await is_admin(robber_id)))
                    await safe_send_message(victim_id, victim_phrase)
                    return

                success = random.random() * 100 <= success_chance
                if success and victim_balance > 0:
                    if victim_balance < min_amount:
                        steal_amount = 0
                    else:
                        max_possible = min(max_amount, victim_balance)
                        steal_amount = round(random.uniform(min_amount, max_possible), 2)

                    if steal_amount > 0:
                        await update_user_balance(victim_id, -steal_amount, conn=conn)
                        await update_user_balance(robber_id, steal_amount, conn=conn)
                        if bitcoin_reward > 0:
                            await update_user_bitcoin(robber_id, float(bitcoin_reward), conn=conn)
                        await conn.execute("UPDATE users SET theft_attempts = theft_attempts + 1, theft_success = theft_success + 1 WHERE user_id=$1", robber_id)

                        exp_success = await get_setting_int("exp_per_theft_success")
                        await add_exp(robber_id, exp_success, conn=conn)

                        required_thefts = await get_setting_int("referral_required_thefts")
                        new_success = await conn.fetchval("SELECT theft_success FROM users WHERE user_id=$1", robber_id)
                        if new_success == required_thefts:
                            ref = await conn.fetchrow("SELECT referrer_id FROM referrals WHERE referred_id=$1 AND reward_given=FALSE", robber_id)
                            if ref:
                                referrer_id = ref['referrer_id']
                                bonus_coins = await get_setting_float("referral_bonus")
                                bonus_rep = await get_setting_int("referral_reputation")
                                await update_user_balance(referrer_id, bonus_coins, conn=conn)
                                await update_user_reputation(referrer_id, bonus_rep)
                                await conn.execute("UPDATE referrals SET reward_given=TRUE WHERE referred_id=$1", robber_id)
                                await conn.execute("UPDATE referrals SET active=TRUE WHERE referred_id=$1", robber_id)
                                await safe_send_message(referrer_id, f"🎉 Ваш реферал совершил {required_thefts} успешных ограблений! Вы получили {bonus_coins:.2f} баксов и {bonus_rep} репутации.")

                        btc_text = f" и {bitcoin_reward} BTC" if bitcoin_reward > 0 else ""
                        phrase = get_random_phrase(THEFT_SUCCESS_PHRASES, amount=steal_amount, target=victim_name)
                        await message.answer(f"{phrase}{btc_text}", reply_markup=main_menu_keyboard(await is_admin(robber_id)))
                        await safe_send_message(victim_id, f"🔫 Вас ограбили! {message.from_user.first_name} украл {steal_amount:.2f} баксов.")
                    else:
                        await conn.execute("UPDATE users SET theft_attempts = theft_attempts + 1, theft_failed = theft_failed + 1 WHERE user_id=$1", robber_id)
                        exp_fail = await get_setting_int("exp_per_theft_fail")
                        await add_exp(robber_id, exp_fail, conn=conn)
                        phrase = get_random_phrase(THEFT_FAIL_PHRASES, target=victim_name)
                        await message.answer(phrase, reply_markup=main_menu_keyboard(await is_admin(robber_id)))
                else:
                    await conn.execute("UPDATE users SET theft_attempts = theft_attempts + 1, theft_failed = theft_failed + 1 WHERE user_id=$1", robber_id)
                    exp_fail = await get_setting_int("exp_per_theft_fail")
                    await add_exp(robber_id, exp_fail, conn=conn)
                    phrase = get_random_phrase(THEFT_FAIL_PHRASES, target=victim_name)
                    await message.answer(phrase, reply_markup=main_menu_keyboard(await is_admin(robber_id)))

                await conn.execute("UPDATE users SET last_theft_time = $1 WHERE user_id=$2", datetime.now().strftime("%Y-%m-%d %H:%M:%S"), robber_id)

    except Exception as e:
        logging.error(f"Theft error: {e}", exc_info=True)
        await message.answer("❌ Ошибка при ограблении.")

@dp.message_handler(lambda message: message.text == "🔫 Ограбить")
async def theft_menu(message: types.Message):
    if message.chat.type != 'private':
        return
    user_id = message.from_user.id
    if await is_banned(user_id) and not await is_admin(user_id):
        return
    await ensure_user_exists(user_id, message.from_user.username, message.from_user.first_name)
    ok, not_subscribed = await check_subscription(user_id)
    if not ok:
        await message.answer("❗️ Сначала подпишись на каналы.", reply_markup=subscription_inline(not_subscribed))
        return
    phrase = get_random_phrase(THEFT_CHOICE_PHRASES)
    await send_with_media(user_id, phrase, media_key='theft', reply_markup=theft_choice_keyboard())

@dp.message_handler(lambda message: message.text == "🎲 Случайная цель")
async def theft_random(message: types.Message, state: FSMContext):
    if message.chat.type != 'private':
        return
    user_id = message.from_user.id
    cooldown_minutes = await get_setting_int("theft_cooldown_minutes")
    async with db_pool.acquire() as conn:
        last_time_str = await conn.fetchval("SELECT last_theft_time FROM users WHERE user_id=$1", user_id)
        if last_time_str:
            try:
                last_time = datetime.strptime(last_time_str, "%Y-%m-%d %H:%M:%S")
                diff = datetime.now() - last_time
                if diff < timedelta(minutes=cooldown_minutes):
                    remaining = cooldown_minutes - int(diff.total_seconds() // 60)
                    phrase = get_random_phrase(THEFT_COOLDOWN_PHRASES, minutes=remaining)
                    await message.answer(phrase, reply_markup=main_menu_keyboard(await is_admin(user_id)))
                    return
            except:
                pass
    target_id = await get_random_user(user_id)
    if not target_id:
        await message.answer("😕 В игре пока нет других игроков.", reply_markup=main_menu_keyboard(await is_admin(user_id)))
        return
    cost = await get_setting_float("random_attack_cost")
    await perform_theft(message, user_id, target_id, cost)

@dp.message_handler(lambda message: message.text == "👤 Выбрать пользователя")
async def theft_choose_user(message: types.Message, state: FSMContext):
    if message.chat.type != 'private':
        return
    user_id = message.from_user.id
    cooldown_minutes = await get_setting_int("theft_cooldown_minutes")
    async with db_pool.acquire() as conn:
        last_time_str = await conn.fetchval("SELECT last_theft_time FROM users WHERE user_id=$1", user_id)
        if last_time_str:
            try:
                last_time = datetime.strptime(last_time_str, "%Y-%m-%d %H:%M:%S")
                diff = datetime.now() - last_time
                if diff < timedelta(minutes=cooldown_minutes):
                    remaining = cooldown_minutes - int(diff.total_seconds() // 60)
                    phrase = get_random_phrase(THEFT_COOLDOWN_PHRASES, minutes=remaining)
                    await message.answer(phrase, reply_markup=main_menu_keyboard(await is_admin(user_id)))
                    return
            except:
                pass
    await message.answer("Введи @username или ID того, кого хочешь ограбить:", reply_markup=back_keyboard())
    await TheftTarget.target.set()

@dp.message_handler(state=TheftTarget.target)
async def theft_target_entered(message: types.Message, state: FSMContext):
    if message.chat.type != 'private':
        await state.finish()
        return
    if message.text == "◀️ Назад":
        await state.finish()
        await message.answer("Главное меню:", reply_markup=main_menu_keyboard(await is_admin(message.from_user.id)))
        return
    target_input = message.text.strip()
    robber_id = message.from_user.id

    target_data = await find_user_by_input(target_input)
    if not target_data:
        await message.answer("❌ Пользователь не найден. Проверь username или ID.")
        return
    target_id = target_data['user_id']

    if target_id == robber_id:
        await message.answer("Сам себя не ограбишь, бро! 😆")
        await state.finish()
        return

    if await is_banned(target_id):
        await message.answer("❌ Этот пользователь заблокирован и не может быть целью.")
        await state.finish()
        return

    cost = await get_setting_float("targeted_attack_cost")
    await perform_theft(message, robber_id, target_id, cost)
    await state.finish()
  # ==================== РЕФЕРАЛЬНАЯ ССЫЛКА ====================
@dp.message_handler(lambda message: message.text == "🔗 Рефералка")
async def referral_link(message: types.Message):
    if message.chat.type != 'private':
        return
    user_id = message.from_user.id
    bot_username = (await bot.me).username
    link = f"https://t.me/{bot_username}?start=ref{user_id}"
    bonus_coins = await get_setting_float("referral_bonus")
    bonus_rep = await get_setting_int("referral_reputation")
    required_thefts = await get_setting_int("referral_required_thefts")

    async with db_pool.acquire() as conn:
        clicks = await conn.fetchval("SELECT SUM(clicks) FROM referrals WHERE referrer_id=$1", user_id) or 0
        active = await conn.fetchval("SELECT COUNT(*) FROM referrals WHERE referrer_id=$1 AND active=TRUE", user_id) or 0
        earned = active * bonus_coins

    text = (
        f"🔗 Твоя реферальная ссылка:\n{link}\n\n"
        f"📊 Статистика:\n"
        f"• Переходов: {clicks}\n"
        f"• Активных рефералов: {active}\n"
        f"• Заработано баксов: {earned:.2f}\n\n"
        f"Бонус: {bonus_coins:.2f} баксов и {bonus_rep} репутации за каждого активного реферала ({required_thefts} успешных краж)."
    )
    await send_with_media(user_id, text, media_key='referral', reply_markup=main_menu_keyboard(await is_admin(user_id)))

# ==================== ЗАДАНИЯ ====================
@dp.message_handler(lambda message: message.text == "📋 Задания")
async def tasks_handler(message: types.Message):
    if message.chat.type != 'private':
        return
    user_id = message.from_user.id
    if await is_banned(user_id) and not await is_admin(user_id):
        return
    await ensure_user_exists(user_id, message.from_user.username, message.from_user.first_name)
    ok, not_subscribed = await check_subscription(user_id)
    if not ok:
        await message.answer("❗️ Сначала подпишись на каналы.", reply_markup=subscription_inline(not_subscribed))
        return

    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, name, description, reward_coins, reward_reputation, max_completions, completed_count FROM tasks WHERE active=TRUE")
    
    if not rows:
        await message.answer("📋 Пока нет доступных заданий.", reply_markup=main_menu_keyboard(await is_admin(user_id)))
        return

    text = "📋 Доступные задания:\n\n"
    kb = []
    for row in rows:
        progress = f" (выполнено {row['completed_count']}/{row['max_completions']})" if row['max_completions'] > 1 else ""
        text += f"🔹 {row['name']}{progress}\n{row['description']}\nНаграда: {float(row['reward_coins']):.2f} баксов, {row['reward_reputation']} репутации\n\n"
        kb.append([InlineKeyboardButton(text=f"Выполнить {row['name']}", callback_data=f"task_{row['id']}")])
    
    await send_with_media(message.chat.id, text, media_key='tasks', reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query_handler(lambda c: c.data.startswith("task_"))
async def take_task(callback: types.CallbackQuery):
    task_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id

    async with db_pool.acquire() as conn:
        existing = await conn.fetchval("SELECT 1 FROM user_tasks WHERE user_id=$1 AND task_id=$2", user_id, task_id)
        if existing:
            await callback.answer("Ты уже выполнял это задание!", show_alert=True)
            return

        task = await conn.fetchrow("SELECT * FROM tasks WHERE id=$1 AND active=TRUE", task_id)
        if not task:
            await callback.answer("Задание не найдено или неактивно.", show_alert=True)
            return

        if task['max_completions'] > 0 and task['completed_count'] >= task['max_completions']:
            await callback.answer("Это задание больше недоступно (лимит выполнений исчерпан).", show_alert=True)
            return

        if task['task_type'] == 'subscribe':
            channel_id = task['target_id']
            try:
                member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
                if member.status in ['left', 'kicked']:
                    await callback.answer("❌ Ты не подписан на этот канал!", show_alert=True)
                    return
            except Exception as e:
                logging.error(f"Task subscribe check error: {e}", exc_info=True)
                await callback.answer("❌ Не удалось проверить подписку. Возможно, бот не админ канала.", show_alert=True)
                return

            async with conn.transaction():
                await update_user_balance(user_id, float(task['reward_coins']), conn=conn)
                await update_user_reputation(user_id, task['reward_reputation'])
                expires_at = (datetime.now() + timedelta(days=task['required_days'])).strftime("%Y-%m-%d %H:%M:%S") if task['required_days'] > 0 else None
                await conn.execute(
                    "INSERT INTO user_tasks (user_id, task_id, completed_at, expires_at, status) VALUES ($1, $2, $3, $4, $5)",
                    user_id, task_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), expires_at, 'completed'
                )
                await conn.execute("UPDATE tasks SET completed_count = completed_count + 1 WHERE id=$1", task_id)

            await callback.answer(f"✅ Задание выполнено! +{float(task['reward_coins']):.2f} баксов, +{task['reward_reputation']} репутации", show_alert=True)
            await callback.message.delete()
        else:
            await callback.answer("Этот тип заданий пока не поддерживается.", show_alert=True)

# ==================== АУКЦИОН ====================
@dp.message_handler(lambda message: message.text == "🏷 Аукцион")
async def auction_handler(message: types.Message):
    if message.chat.type != 'private':
        return
    user_id = message.from_user.id
    if await is_banned(user_id) and not await is_admin(user_id):
        return
    await ensure_user_exists(user_id, message.from_user.username, message.from_user.first_name)
    ok, not_subscribed = await check_subscription(user_id)
    if not ok:
        await message.answer("❗️ Сначала подпишись на каналы.", reply_markup=subscription_inline(not_subscribed))
        return

    await list_auctions(message)

async def list_auctions(message: types.Message, page: int = 1):
    offset = (page - 1) * ITEMS_PER_PAGE
    async with db_pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM auctions WHERE status='active'")
        rows = await conn.fetch(
            "SELECT id, item_name, current_price, end_time, target_price FROM auctions WHERE status='active' ORDER BY created_at DESC LIMIT $1 OFFSET $2",
            ITEMS_PER_PAGE, offset
        )
    if not rows:
        await message.answer("🏷 На данный момент нет активных аукционов.", reply_markup=main_menu_keyboard(await is_admin(message.from_user.id)))
        return
    text = f"🏷 Активные аукционы (страница {page}):\n\n"
    for row in rows:
        text += f"🆔 {row['id']} | {row['item_name']} | Текущая ставка: {float(row['current_price']):.2f}\n"
        if row['end_time']:
            remaining = row['end_time'] - datetime.now()
            if remaining.total_seconds() > 0:
                hours = int(remaining.total_seconds() // 3600)
                minutes = int((remaining.total_seconds() % 3600) // 60)
                text += f"⏳ Осталось: {hours}ч {minutes}м\n"
        if row['target_price']:
            text += f"🎯 Целевая цена: {float(row['target_price']):.2f}\n"
        text += "\n"
    total_pages = (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    kb = auction_list_keyboard(rows, page, total_pages)
    await send_with_media(message.chat.id, text, media_key='auction', reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith("auction_page_"))
async def auction_page_callback(callback: types.CallbackQuery):
    page = int(callback.data.split("_")[2])
    await list_auctions(callback.message, page)
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("auction_view_"))
async def auction_view(callback: types.CallbackQuery):
    auction_id = int(callback.data.split("_")[2])
    async with db_pool.acquire() as conn:
        auction = await conn.fetchrow("SELECT * FROM auctions WHERE id=$1 AND status='active'", auction_id)
        if not auction:
            await callback.answer("Аукцион не найден или завершён.", show_alert=True)
            return
        bids = await conn.fetch("SELECT user_id, bid_amount, bid_time FROM auction_bids WHERE auction_id=$1 ORDER BY bid_time DESC LIMIT 5", auction_id)
    text = (
        f"🏷 <b>{auction['item_name']}</b>\n"
        f"📝 {auction['description']}\n\n"
        f"💰 Стартовая цена: {float(auction['start_price']):.2f}\n"
        f"💵 Текущая ставка: {float(auction['current_price']):.2f}\n"
    )
    if auction['end_time']:
        remaining = auction['end_time'] - datetime.now()
        if remaining.total_seconds() > 0:
            hours = int(remaining.total_seconds() // 3600)
            minutes = int((remaining.total_seconds() % 3600) // 60)
            text += f"⏳ Окончание через: {hours}ч {minutes}м\n"
    if auction['target_price']:
        text += f"🎯 Целевая цена: {float(auction['target_price']):.2f}\n"
    text += "\n📊 Последние ставки:\n"
    if bids:
        for bid in bids:
            user = await conn.fetchval("SELECT first_name FROM users WHERE user_id=$1", bid['user_id'])
            text += f"• {user or 'Неизвестно'}: {float(bid['bid_amount']):.2f} баксов ({bid['bid_time'].strftime('%Y-%m-%d %H:%M')})\n"
    else:
        text += "Пока нет ставок.\n"
    if auction['photo_file_id']:
        await callback.message.delete()
        await callback.message.answer_photo(auction['photo_file_id'], caption=text, reply_markup=auction_detail_keyboard(auction_id))
    else:
        await callback.message.edit_text(text, reply_markup=auction_detail_keyboard(auction_id))
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("auction_bid_"))
async def auction_bid_start(callback: types.CallbackQuery, state: FSMContext):
    auction_id = int(callback.data.split("_")[2])
    await state.update_data(auction_id=auction_id)
    await callback.message.answer("Введи сумму ставки (можно дробную):", reply_markup=back_keyboard())
    await AuctionBid.amount.set()
    await callback.answer()

@dp.message_handler(state=AuctionBid.amount)
async def auction_bid_amount(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await auction_handler(message)
        return
    try:
        amount = float(message.text)
        if amount <= 0:
            raise ValueError
        amount = round(amount, 2)
    except ValueError:
        await message.answer("❌ Введи положительное число с точностью до сотых.")
        return
    data = await state.get_data()
    auction_id = data['auction_id']
    user_id = message.from_user.id
    async with db_pool.acquire() as conn:
        auction = await conn.fetchrow("SELECT * FROM auctions WHERE id=$1 AND status='active'", auction_id)
        if not auction:
            await message.answer("❌ Аукцион не найден или завершён.")
            await state.finish()
            return

        current_leader = await conn.fetchval(
            "SELECT user_id FROM auction_bids WHERE auction_id=$1 ORDER BY bid_amount DESC, bid_time ASC LIMIT 1",
            auction_id
        )
        if current_leader == user_id:
            await message.answer("❌ Ты уже являешься лидером этого аукциона. Нельзя повышать свою ставку.")
            await state.finish()
            return

        min_step = await get_setting_int("auction_min_bid_step")
        min_bid = float(auction['current_price']) + min_step
        if amount < min_bid:
            await message.answer(f"❌ Ставка должна быть не меньше {min_bid:.2f} (текущая цена + минимальный шаг).")
            return
        max_input = await get_setting_float("max_input_number")
        if amount > max_input:
            await message.answer(f"❌ Сумма слишком большая (максимум {max_input:.2f}).")
            return
        balance = await get_user_balance(user_id)
        if balance < amount:
            await message.answer("❌ Недостаточно баксов.")
            return
        await update_user_balance(user_id, -amount, conn=conn)
        await conn.execute(
            "UPDATE auctions SET current_price=$1 WHERE id=$2",
            amount, auction_id
        )
        await conn.execute(
            "INSERT INTO auction_bids (auction_id, user_id, bid_amount, bid_time) VALUES ($1, $2, $3, $4)",
            auction_id, user_id, amount, datetime.now()
        )
        if auction['target_price'] and amount >= float(auction['target_price']):
            await conn.execute("UPDATE auctions SET status='ended', winner_id=$1 WHERE id=$2", user_id, auction_id)
            await safe_send_message(user_id, f"🎉 Поздравляем! Ты выиграл аукцион «{auction['item_name']}» с ценой {amount:.2f} баксов. Админ скоро свяжется для передачи товара.")
            await safe_send_message(auction['created_by'], f"🏁 Аукцион «{auction['item_name']}» завершён по достижению целевой цены. Победитель: {message.from_user.first_name} (ID: {user_id}) с суммой {amount:.2f} баксов.")
            await message.answer("✅ Аукцион завершён! Ты победитель.")
        else:
            await message.answer(f"✅ Ставка принята! Ты теперь лидер с ценой {amount:.2f} баксов.")
    await state.finish()

@dp.callback_query_handler(lambda c: c.data == "auction_list")
async def auction_list_back(callback: types.CallbackQuery):
    await list_auctions(callback.message)
    await callback.answer()
