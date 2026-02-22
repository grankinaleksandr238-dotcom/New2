import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import types
from aiogram.dispatcher import FSMContext

from bot_instance import dp, bot
from db import (
    ensure_user_exists, is_banned, is_admin, get_user_balance, get_user_reputation,
    get_user_level, get_user_exp, get_user_stats, get_user_bitcoin, get_user_authority,
    get_total_user_authority, get_total_user_fights, update_user_balance,
    update_user_reputation, get_setting, get_setting_int, get_setting_float,
    check_subscription, db_pool
)
from helpers import (
    safe_send_message, send_with_media, auto_delete_reply, auto_delete_message,
    progress_bar, get_random_phrase, notify_chats, find_user_by_input
)
from constants import (
    BONUS_PHRASES, ITEMS_PER_PAGE, SUPER_ADMINS
)
from keyboards import (
    main_menu_keyboard, back_keyboard, cancel_keyboard, subscription_inline,
    repeat_bet_keyboard
)
from states import PromoActivate

# ==================== ГЛОБАЛЬНЫЙ ОБРАБОТЧИК /cancel ====================
@dp.message_handler(commands=['cancel'], state='*')
async def cmd_cancel(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        return
    await state.finish()
    user_id = message.from_user.id
    await ensure_user_exists(user_id, message.from_user.username, message.from_user.first_name)
    await message.answer("❌ Действие отменено.", reply_markup=main_menu_keyboard(await is_admin(user_id)))

# ==================== СТАРТ И ГЛАВНОЕ МЕНЮ ====================
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    if message.chat.type != 'private':
        return
    user_id = message.from_user.id
    if await is_banned(user_id) and not await is_admin(user_id):
        await message.answer("⛔ Вы заблокированы в боте.")
        return

    args = message.get_args()
    if args and args.startswith('ref'):
        try:
            referrer_id = int(args[3:])
            if referrer_id != user_id:
                async with db_pool.acquire() as conn:
                    referrer_exists = await conn.fetchval("SELECT 1 FROM users WHERE user_id=$1", referrer_id)
                    if referrer_exists and not await is_banned(referrer_id):
                        existing = await conn.fetchval("SELECT 1 FROM referrals WHERE referred_id=$1", user_id)
                        if not existing:
                            await conn.execute(
                                "INSERT INTO referrals (referrer_id, referred_id, referred_date, reward_given, clicks) VALUES ($1, $2, $3, $4, 1) ON CONFLICT (referred_id) DO NOTHING",
                                referrer_id, user_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), False
                            )
                            await conn.execute("UPDATE referrals SET clicks = clicks + 1 WHERE referred_id=$1", user_id)
                            await safe_send_message(referrer_id, f"🔗 Новый пользователь {message.from_user.first_name} зарегистрировался по вашей ссылке! Награда будет выдана после того, как он совершит {await get_setting('referral_required_thefts')} успешных ограблений.")
        except:
            pass

    created, bonus = await ensure_user_exists(user_id, message.from_user.username, message.from_user.first_name)
    if created:
        await message.answer(f"🎁 Вам начислен стартовый бонус: {bonus} баксов!")

    welcome_text = "Добро пожаловать в Malboro GAME!"
    await send_with_media(user_id, welcome_text, media_key='welcome')

    ok, not_subscribed = await check_subscription(user_id)
    if not ok:
        await message.answer(
            "❗️ Для использования бота необходимо подписаться на наши каналы:",
            reply_markup=subscription_inline(not_subscribed)
        )
        return

    is_admin_user = await is_admin(user_id)
    await message.answer(
        f"Привет, {message.from_user.first_name}!\n"
        f"Добро пожаловать в <b>Malboro GAME</b>! 🚬\n"
        f"Тут ты найдёшь: казино, розыгрыши, магазин, аукцион, биткоин-биржу.\n"
        f"А ещё можешь грабить других – случайно или по username!\n"
        f"У тебя 1 уровень. Зарабатывай опыт и повышай уровень!\n\n"
        f"Канал: @lllMALBOROlll (подпишись!)",
        reply_markup=main_menu_keyboard(is_admin_user)
    )

@dp.message_handler(commands=['help'])
async def cmd_help_private(message: types.Message):
    if message.chat.type != 'private':
        await message.reply("Для списка команд в личных сообщениях используйте /help в ЛС.\n"
                           "Команды для групп:\n"
                           "/fight – атаковать банду\n"
                           "/smuggle – отправиться в контрабанду\n"
                           "/activate_chat – активировать чат\n"
                           "/top – топ чата\n"
                           "/mlb_help – помощь в группе")
        return
    user_id = message.from_user.id
    if await is_banned(user_id) and not await is_admin(user_id):
        return
    await ensure_user_exists(user_id, message.from_user.username, message.from_user.first_name)
    ok, not_subscribed = await check_subscription(user_id)
    if not ok:
        await message.answer("❗️ Сначала подпишись на каналы.", reply_markup=subscription_inline(not_subscribed))
        return
    text = (
        "📚 <b>Доступные команды и разделы</b>\n\n"
        "👤 Профиль – статистика и характеристики\n"
        "🎁 Бонус – ежедневный бонус\n"
        "🛒 Магазин подарков – покупка подарков\n"
        "🎰 Казино – азартные игры (кости, угадайка, слоты, рулетка, мультиплеер 21)\n"
        "🎟 Промокод – активация промокодов\n"
        "🏆 Топ игроков – рейтинг по баксам, репутации, биткоинам и т.д.\n"
        "💰 Мои покупки – история заказов\n"
        "🔫 Ограбить – укради баксы у другого\n"
        "📋 Задания – выполняй и получай награды\n"
        "🔗 Рефералка – приглашай друзей\n"
        "📊 Уровень – твой прогресс\n"
        "🎁 Розыгрыши – активные и завершённые\n"
        "🏷 Аукцион – участвуй в торгах\n"
        "🏪 Мои бизнесы – управление бизнесом (покупка за BTC)\n"
        "💼 Биткоин-биржа – продавай и покупай BTC за баксы\n"
        "⚙️ Админ панель – для администраторов"
    )
    await message.answer(text)

# ==================== ПРОВЕРКА ПОДПИСКИ (ИНЛАЙН) ====================
@dp.callback_query_handler(lambda c: c.data == "check_sub")
async def check_subscription_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if await is_banned(user_id) and not await is_admin(user_id):
        await callback.answer("⛔ Вы заблокированы.", show_alert=True)
        return
    await ensure_user_exists(user_id, callback.from_user.username, callback.from_user.first_name)
    ok, not_subscribed = await check_subscription(user_id)
    if ok:
        await callback.message.delete()
        is_admin_user = await is_admin(user_id)
        await callback.message.answer(
            "✅ Спасибо за подписку! Добро пожаловать.",
            reply_markup=main_menu_keyboard(is_admin_user)
        )
    else:
        await callback.answer("❌ Ты ещё не подписался на все каналы!", show_alert=True)
        await callback.message.edit_reply_markup(reply_markup=subscription_inline(not_subscribed))

@dp.callback_query_handler(lambda c: c.data == "no_link")
async def no_link_callback(callback: types.CallbackQuery):
    await callback.answer("Ссылка отсутствует. Подпишись вручную.", show_alert=True)

# ==================== ПРОФИЛЬ ====================
@dp.message_handler(lambda message: message.text == "👤 Профиль")
async def profile_handler(message: types.Message):
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

    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT balance, reputation, total_spent, negative_balance, joined_date, "
                "theft_attempts, theft_success, theft_failed, theft_protected, "
                "casino_wins, casino_losses, dice_wins, dice_losses, guess_wins, guess_losses, "
                "slots_wins, slots_losses, roulette_wins, roulette_losses, "
                "COALESCE(multiplayer_wins, 0) as multiplayer_wins, "
                "COALESCE(multiplayer_losses, 0) as multiplayer_losses, "
                "exp, level, strength, agility, defense, "
                "COALESCE(smuggle_success, 0) as smuggle_success, "
                "COALESCE(smuggle_fail, 0) as smuggle_fail, "
                "bitcoin_balance, authority_balance "
                "FROM users WHERE user_id=$1",
                user_id
            )
        if row:
            balance = float(row['balance'] or 0)
            rep = row['reputation'] or 0
            spent = float(row['total_spent'] or 0)
            neg = float(row['negative_balance'] or 0)
            joined = row['joined_date']
            attempts = row['theft_attempts'] or 0
            success = row['theft_success'] or 0
            failed = row['theft_failed'] or 0
            protected = row['theft_protected'] or 0
            cw = row['casino_wins'] or 0
            cl = row['casino_losses'] or 0
            dw = row['dice_wins'] or 0
            dl = row['dice_losses'] or 0
            gw = row['guess_wins'] or 0
            gl = row['guess_losses'] or 0
            sw = row['slots_wins'] or 0
            sl = row['slots_losses'] or 0
            rw = row['roulette_wins'] or 0
            rl = row['roulette_losses'] or 0
            mpw = row['multiplayer_wins'] or 0
            mpl = row['multiplayer_losses'] or 0
            exp = row['exp'] or 0
            level = row['level'] or 1
            strength = row['strength'] or 1
            agility = row['agility'] or 1
            defense = row['defense'] or 1
            smuggle_success = row['smuggle_success'] or 0
            smuggle_fail = row['smuggle_fail'] or 0
            bitcoin = float(row['bitcoin_balance']) if row['bitcoin_balance'] is not None else 0.0
            authority = row['authority_balance'] or 0

            neg_text = f" (долг: {neg:.2f})" if neg > 0 else ""
            level_mult = await get_setting_int("level_multiplier")
            exp_needed = level * level_mult
            bar = progress_bar(exp, exp_needed, 10)

            total_authority_chat = await get_total_user_authority(user_id)
            total_fights, total_damage = await get_total_user_fights(user_id)

            joined_str = joined if joined else 'неизвестно'

            text = (
                f"👤 <b>Твой профиль</b>\n"
                f"📊 <b>Уровень:</b> {level}\n"
                f"📈 <b>Опыт:</b> {exp}/{exp_needed}\n{bar}\n"
                f"💪 Сила: {strength} | 🏃 Ловкость: {agility} | 🛡 Защита: {defense}\n"
                f"💰 Баланс: {balance:.2f} баксов{neg_text}\n"
                f"₿ Биткоины: {bitcoin:.4f} BTC\n"
                f"⭐️ Репутация: {rep}\n"
                f"⚔️ Авторитет (прокачка): {authority}\n"
                f"🗣 Авторитет в чатах: {total_authority_chat} (боёв: {total_fights}, урон: {total_damage})\n"
                f"💸 Всего потрачено: {spent:.2f} баксов\n"
                f"📅 Зарегистрирован: {joined_str}\n"
                f"🔫 Ограблений: {attempts} (успешно: {success}, провал: {failed})\n"
                f"🛡 Отбито атак: {protected}\n"
                f"🎰 Казино: побед {cw}, поражений {cl}\n"
                f"🎲 Кости: побед {dw}, поражений {dl}\n"
                f"🔢 Угадайка: побед {gw}, поражений {gl}\n"
                f"🍒 Слоты: побед {sw}, поражений {sl}\n"
                f"🎡 Рулетка: побед {rw}, поражений {rl}\n"
                f"👥 Мультиплеер: побед {mpw}, поражений {mpl}\n"
                f"📦 Контрабанда: успешно {smuggle_success}, провал {smuggle_fail}"
            )
        else:
            text = "Профиль не найден"
    except Exception as e:
        logging.error(f"Profile error: {e}", exc_info=True)
        text = "❌ Ошибка загрузки профиля. Подробности в логах."

    await send_with_media(user_id, text, media_key='profile', reply_markup=main_menu_keyboard(await is_admin(user_id)))
  # ==================== УРОВЕНЬ ====================
@dp.message_handler(lambda message: message.text == "📊 Уровень")
async def level_handler(message: types.Message):
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
    level = await get_user_level(user_id)
    exp = await get_user_exp(user_id)
    level_mult = await get_setting_int("level_multiplier")
    exp_needed = level * level_mult
    bar = progress_bar(exp, exp_needed, 10)
    level_names = {
        1: "🔰 Новичок",
        2: "⛏️ Искатель",
        3: "⚔️ Воин",
        4: "🛡️ Защитник",
        5: "🌟 Звезда",
        6: "🔥 Ветеран",
        7: "💫 Мастер",
        8: "👑 Легенда",
        9: "💎 Алмазный",
        10: "👁‍🗨 Патриарх",
    }
    level_name = level_names.get(level, f"Уровень {level}")
    
    async with db_pool.acquire() as conn:
        next_reward = await conn.fetchrow(
            "SELECT coins, reputation FROM level_rewards WHERE level=$1",
            level + 1
        )
        next_coins = float(next_reward['coins']) if next_reward else 0
        next_rep = next_reward['reputation'] if next_reward else 0

    text = (
        f"📊 <b>{level_name}</b>\n\n"
        f"Уровень: {level}\n"
        f"Опыт: {exp} / {exp_needed}\n"
        f"{bar}\n\n"
        f"За повышение уровня ты получаешь баксы, репутацию и очки статов!\n"
        f"Следующая награда: +{next_coins:.2f} баксов, +{next_rep} репутации."
    )
    await message.answer(text, reply_markup=main_menu_keyboard(await is_admin(user_id)))

# ==================== РЕПУТАЦИЯ ====================
@dp.message_handler(lambda message: message.text == "⭐️ Репутация")
async def reputation_handler(message: types.Message):
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
    rep = await get_user_reputation(user_id)
    theft_bonus = float(await get_setting_float("reputation_theft_bonus")) * rep
    defense_bonus = float(await get_setting_float("reputation_defense_bonus")) * rep
    smuggle_bonus = float(await get_setting_float("reputation_smuggle_bonus")) * rep
    smuggle_success_bonus = float(await get_setting_float("reputation_smuggle_success_bonus")) * rep
    max_bonus = await get_setting_float("reputation_max_bonus_percent")
    
    theft_bonus = min(theft_bonus, max_bonus)
    defense_bonus = min(defense_bonus, max_bonus)
    smuggle_success_bonus = min(smuggle_success_bonus, max_bonus)
    
    await message.answer(
        f"⭐️ Твоя репутация: {rep}\n\n"
        f"Репутация увеличивает шансы и добычу (макс. +{max_bonus}%):\n"
        f"🔫 Бонус к грабежу: +{theft_bonus:.1f}%\n"
        f"🛡 Бонус к защите: +{defense_bonus:.1f}%\n"
        f"📦 Бонус к добыче BTC: +{smuggle_bonus:.1f} BTC\n"
        f"🚤 Бонус к успеху контрабанды: +{smuggle_success_bonus:.1f}%\n\n"
        f"Зарабатывай репутацию в играх и за выполнение заданий!",
        reply_markup=main_menu_keyboard(await is_admin(user_id))
    )

# ==================== ЕЖЕДНЕВНЫЙ БОНУС ====================
@dp.message_handler(lambda message: message.text == "🎁 Бонус")
async def bonus_handler(message: types.Message):
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
        last_bonus_str = await conn.fetchval("SELECT last_bonus FROM users WHERE user_id=$1", user_id)

        now = datetime.now()
        if last_bonus_str:
            try:
                last_bonus = datetime.strptime(last_bonus_str, "%Y-%m-%d %H:%M:%S")
                if last_bonus.date() == now.date():
                    next_bonus = last_bonus + timedelta(days=1)
                    time_left = next_bonus - now
                    hours, remainder = divmod(time_left.seconds, 3600)
                    minutes, _ = divmod(remainder, 60)
                    await message.answer(f"⏳ Бонус уже получен сегодня. Следующий через {hours} ч {minutes} мин.")
                    return
            except:
                pass

        bonus = random.randint(10, 50)
        phrase = get_random_phrase(BONUS_PHRASES, bonus=bonus)

        await conn.execute(
            "UPDATE users SET balance = balance + $1, last_bonus = $2 WHERE user_id=$3",
            bonus, now.strftime("%Y-%m-%d %H:%M:%S"), user_id
        )
    await message.answer(phrase, reply_markup=main_menu_keyboard(await is_admin(user_id)))

# ==================== ТОП ИГРОКОВ ====================
@dp.message_handler(lambda message: message.text == "🏆 Топ игроков")
async def leaderboard_menu(message: types.Message):
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
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="💰 Самые богатые")],
        [KeyboardButton(text="💸 Транжиры")],
        [KeyboardButton(text="🔫 Крадуны")],
        [KeyboardButton(text="⭐️ По репутации")],
        [KeyboardButton(text="₿ По биткоинам")],
        [KeyboardButton(text="📈 По уровню")],
        [KeyboardButton(text="💪 По силе")],
        [KeyboardButton(text="🏃 По ловкости")],
        [KeyboardButton(text="🛡 По защите")],
        [KeyboardButton(text="◀️ Назад")]
    ], resize_keyboard=True)
    await message.answer("Выбери категорию топа:", reply_markup=kb)

async def show_top(message: types.Message, order_field: str, title: str):
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
            if order_field == 'bitcoin_balance':
                order_expr = "bitcoin_balance"
            else:
                order_expr = order_field
            total = await conn.fetchval(f"SELECT COUNT(*) FROM users")
            rows = await conn.fetch(
                f"SELECT first_name, {order_expr} as value FROM users ORDER BY value DESC LIMIT $1 OFFSET $2",
                ITEMS_PER_PAGE, offset
            )
        if not rows:
            await message.answer("Нет данных.")
            return
        text = f"{title} (страница {page}):\n\n"
        for idx, row in enumerate(rows, start=offset+1):
            val = row['value']
            if order_field == 'bitcoin_balance':
                val = f"{float(val):.4f}"
            elif order_field in ['balance', 'total_spent']:
                val = f"{float(val):.2f}"
            text += f"{idx}. {row['first_name']} – {val}\n"
        kb = []
        nav_buttons = []
        if page > 1:
            nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"top:{order_field}:{page-1}"))
        if offset + ITEMS_PER_PAGE < total:
            nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"top:{order_field}:{page+1}"))
        if nav_buttons:
            kb.append(nav_buttons)
        if kb:
            await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        else:
            await message.answer(text)
    except Exception as e:
        logging.error(f"Top error: {e}", exc_info=True)
        await message.answer("❌ Ошибка загрузки топа.")

@dp.message_handler(lambda message: message.text == "💰 Самые богатые")
async def top_rich_handler(message: types.Message):
    await show_top(message, "balance", "💰 Самые богатые")

@dp.message_handler(lambda message: message.text == "💸 Транжиры")
async def top_spenders_handler(message: types.Message):
    await show_top(message, "total_spent", "💸 Транжиры")

@dp.message_handler(lambda message: message.text == "🔫 Крадуны")
async def top_thieves_handler(message: types.Message):
    await show_top(message, "theft_success", "🔫 Крадуны")

@dp.message_handler(lambda message: message.text == "⭐️ По репутации")
async def top_reputation_handler(message: types.Message):
    await show_top(message, "reputation", "⭐️ По репутации")

@dp.message_handler(lambda message: message.text == "₿ По биткоинам")
async def top_bitcoin_handler(message: types.Message):
    await show_top(message, "bitcoin_balance", "₿ По биткоинам")

@dp.message_handler(lambda message: message.text == "📈 По уровню")
async def top_level_handler(message: types.Message):
    await show_top(message, "level", "📈 По уровню")

@dp.message_handler(lambda message: message.text == "💪 По силе")
async def top_strength_handler(message: types.Message):
    await show_top(message, "strength", "💪 По силе")

@dp.message_handler(lambda message: message.text == "🏃 По ловкости")
async def top_agility_handler(message: types.Message):
    await show_top(message, "agility", "🏃 По ловкости")

@dp.message_handler(lambda message: message.text == "🛡 По защите")
async def top_defense_handler(message: types.Message):
    await show_top(message, "defense", "🛡 По защите")

@dp.callback_query_handler(lambda c: c.data.startswith("top:"))
async def top_page_callback(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    field = parts[1]
    page = int(parts[2])
    titles = {
        "balance": "💰 Самые богатые",
        "total_spent": "💸 Транжиры",
        "theft_success": "🔫 Крадуны",
        "reputation": "⭐️ По репутации",
        "bitcoin_balance": "₿ По биткоинам",
        "level": "📈 По уровню",
        "strength": "💪 По силе",
        "agility": "🏃 По ловкости",
        "defense": "🛡 По защите"
    }
    title = titles.get(field, "Топ")
    await show_top(callback.message, field, title)
    await callback.answer()
