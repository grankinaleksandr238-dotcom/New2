import asyncio
import logging
import random
import json
from datetime import datetime

from aiogram import types
from aiogram.dispatcher import FSMContext

from bot_instance import dp, bot
from utils.db import (
    ensure_user_exists, is_banned, is_admin, get_user_balance, get_user_level,
    update_user_balance, update_user_bitcoin, update_user_game_stats,
    update_user_reputation, add_exp, get_setting, get_setting_int, get_setting_float,
    check_global_cooldown, set_global_cooldown, check_subscription, db_pool,
    slots_spin, format_slots_result, roulette_spin
)
from utils.helpers import (
    safe_send_message, send_with_media, auto_delete_reply, auto_delete_message,
    get_random_phrase, notify_chats
)
from utils.constants import (
    CASINO_WIN_PHRASES, CASINO_LOSE_PHRASES, BIG_WIN_THRESHOLD,
    DICE_WIN_PHRASES, DICE_LOSE_PHRASES,
    GUESS_WIN_PHRASES, GUESS_LOSE_PHRASES,
    SLOTS_WIN_PHRASES, SLOTS_LOSE_PHRASES,
    ROULETTE_WIN_PHRASES, ROULETTE_LOSE_PHRASES
)
from utils.keyboards import (
    main_menu_keyboard, back_keyboard, casino_menu_keyboard,
    repeat_bet_keyboard, subscription_inline
)
from utils.states import (
    CasinoBet, DiceBet, GuessBet, SlotsBet, RouletteBet
)
from utils.db import slots_spin, format_slots_result, roulette_spin

# ==================== КАЗИНО И ИГРЫ ====================
@dp.message_handler(lambda message: message.text == "🎰 Казино")
async def casino_menu(message: types.Message):
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
    min_level = await get_setting_int("min_level_casino")
    level = await get_user_level(user_id)
    if level < min_level:
        await message.answer(f"❌ Для доступа к казино нужен {min_level} уровень. Твой уровень: {level}")
        return
    await send_with_media(user_id, "Выбери игру:", media_key='casino', reply_markup=casino_menu_keyboard())

async def save_last_bet(user_id: int, game: str, amount: float, bet_data: dict = None):
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO user_last_bets (user_id, game, bet_amount, bet_data, updated_at)
            VALUES ($1, $2, $3, $4, NOW())
            ON CONFLICT (user_id, game) DO UPDATE SET
                bet_amount = EXCLUDED.bet_amount,
                bet_data = EXCLUDED.bet_data,
                updated_at = NOW()
        """, user_id, game, amount, json.dumps(bet_data) if bet_data else None)

# ----- Казино (простое) -----
@dp.message_handler(lambda message: message.text == "🎰 Играть в казино")
async def casino_start(message: types.Message):
    if message.chat.type != 'private':
        return
    user_id = message.from_user.id
    min_level = await get_setting_int("min_level_casino")
    level = await get_user_level(user_id)
    if level < min_level:
        await message.answer(f"❌ Для этой игры нужен {min_level} уровень. Твой уровень: {level}")
        return
    await message.answer("Введи сумму ставки (можно дробную, например 10.50):", reply_markup=back_keyboard())
    await CasinoBet.amount.set()

@dp.message_handler(state=CasinoBet.amount)
async def casino_bet(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await casino_menu(message)
        return
    
    ok, remaining = await check_global_cooldown(message.from_user.id, "casino")
    if not ok:
        await message.answer(f"⏳ Подожди ещё {remaining} сек перед следующей игрой.")
        return
    
    try:
        amount = float(message.text)
        if amount <= 0 or amount % 0.01 != 0:
            raise ValueError
        amount = round(amount, 2)
    except ValueError:
        await message.answer("❌ Введи положительное число с точностью до сотых (например, 10.50).")
        return
    user_id = message.from_user.id
    balance = await get_user_balance(user_id)
    min_bet = await get_setting_float("casino_min_bet")
    max_bet = await get_setting_float("casino_max_bet")
    max_input = await get_setting_float("max_input_number")
    if amount < min_bet or amount > max_bet:
        await message.answer(f"❌ Ставка должна быть от {min_bet:.2f} до {max_bet:.2f}.")
        return
    if amount > max_input:
        await message.answer(f"❌ Сумма слишком большая (максимум {max_input:.2f}).")
        return
    if amount > balance:
        await message.answer("❌ Недостаточно баксов.")
        return

    win_chance = await get_setting_float("casino_win_chance")
    multiplier = await get_setting_float("casino_multiplier")

    anim = await message.answer("🎰 Крутим барабан...")
    await asyncio.sleep(1)
    await anim.edit_text("🎰 🎰 🎰")
    await asyncio.sleep(1)

    win = random.random() * 100 <= win_chance

    async with db_pool.acquire() as conn:
        await update_user_balance(user_id, -amount, conn=conn)
        await update_user_game_stats(user_id, 'casino', win, conn=conn)

        if win:
            profit = amount * (multiplier - 1)
            await update_user_balance(user_id, amount * multiplier, conn=conn)
            exp = await get_setting_int("exp_per_casino_win")
            btc_reward = await get_setting_int("bitcoin_per_casino_win")
            if btc_reward > 0:
                await update_user_bitcoin(user_id, float(btc_reward), conn=conn)
                btc_text = f" и {btc_reward} BTC"
            else:
                btc_text = ""
            phrase = get_random_phrase(CASINO_WIN_PHRASES, win=amount*multiplier, profit=profit)
            if amount * multiplier >= BIG_WIN_THRESHOLD and await get_setting("chat_notify_big_win") == "1":
                await notify_chats(f"🔥 {message.from_user.first_name} сорвал куш в казино: +{amount * multiplier:.2f} баксов!{btc_text}")
        else:
            exp = await get_setting_int("exp_per_casino_lose")
            phrase = get_random_phrase(CASINO_LOSE_PHRASES, loss=amount)
        await add_exp(user_id, exp, conn=conn)

    await save_last_bet(user_id, 'casino', amount)
    await set_global_cooldown(user_id, "casino")

    await anim.edit_text(phrase, reply_markup=repeat_bet_keyboard('casino'))
    await state.finish()

# ----- Кости -----
@dp.message_handler(lambda message: message.text == "🎲 Кости")
async def dice_start(message: types.Message):
    if message.chat.type != 'private':
        return
    user_id = message.from_user.id
    min_level = await get_setting_int("min_level_dice")
    level = await get_user_level(user_id)
    if level < min_level:
        await message.answer(f"❌ Для этой игры нужен {min_level} уровень. Твой уровень: {level}")
        return
    await send_with_media(user_id, "Введи сумму ставки (можно дробную):", media_key='dice', reply_markup=back_keyboard())
    await DiceBet.amount.set()

@dp.message_handler(state=DiceBet.amount)
async def dice_bet(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await casino_menu(message)
        return
    
    ok, remaining = await check_global_cooldown(message.from_user.id, "dice")
    if not ok:
        await message.answer(f"⏳ Подожди ещё {remaining} сек.")
        return
    
    try:
        amount = float(message.text)
        if amount <= 0:
            raise ValueError
        amount = round(amount, 2)
    except ValueError:
        await message.answer("❌ Введи положительное число.")
        return
    user_id = message.from_user.id
    balance = await get_user_balance(user_id)
    min_bet = 1.0
    max_bet = await get_setting_float("casino_max_bet")
    max_input = await get_setting_float("max_input_number")
    if amount < min_bet:
        await message.answer(f"❌ Минимальная ставка {min_bet:.2f} бакса.")
        return
    if amount > max_bet:
        await message.answer(f"❌ Максимальная ставка {max_bet:.2f}.")
        return
    if amount > max_input:
        await message.answer(f"❌ Сумма слишком большая (максимум {max_input:.2f}).")
        return
    if amount > balance:
        await message.answer("❌ Недостаточно баксов.")
        return

    dice1 = random.randint(1, 6)
    dice2 = random.randint(1, 6)
    total = dice1 + dice2
    threshold = await get_setting_int("dice_win_threshold")
    win = total > threshold

    async with db_pool.acquire() as conn:
        await update_user_balance(user_id, -amount, conn=conn)
        await update_user_game_stats(user_id, 'dice', win, conn=conn)
        if win:
            multiplier = await get_setting_float("dice_multiplier")
            profit = amount * multiplier
            await update_user_balance(user_id, profit, conn=conn)
            exp = await get_setting_int("exp_per_dice_win")
            btc_reward = await get_setting_int("bitcoin_per_dice_win")
            if btc_reward > 0:
                await update_user_bitcoin(user_id, float(btc_reward), conn=conn)
            phrase = get_random_phrase(DICE_WIN_PHRASES, dice1=dice1, dice2=dice2, total=total, profit=profit)
        else:
            exp = await get_setting_int("exp_per_dice_lose")
            phrase = get_random_phrase(DICE_LOSE_PHRASES, dice1=dice1, dice2=dice2, total=total, loss=amount)
        await add_exp(user_id, exp, conn=conn)

    await save_last_bet(user_id, 'dice', amount)
    await set_global_cooldown(user_id, "dice")

    await message.answer(phrase, reply_markup=repeat_bet_keyboard('dice'))
    await state.finish()

# ----- Угадай число -----
@dp.message_handler(lambda message: message.text == "🔢 Угадай число")
async def guess_start(message: types.Message):
    if message.chat.type != 'private':
        return
    user_id = message.from_user.id
    min_level = await get_setting_int("min_level_guess")
    level = await get_user_level(user_id)
    if level < min_level:
        await message.answer(f"❌ Для этой игры нужен {min_level} уровень. Твой уровень: {level}")
        return
    await send_with_media(user_id, "Введи сумму ставки (можно дробную):", media_key='guess', reply_markup=back_keyboard())
    await GuessBet.amount.set()

@dp.message_handler(state=GuessBet.amount)
async def guess_bet(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await casino_menu(message)
        return
    
    ok, remaining = await check_global_cooldown(message.from_user.id, "guess")
    if not ok:
        await message.answer(f"⏳ Подожди ещё {remaining} сек.")
        return
    
    try:
        amount = float(message.text)
        if amount <= 0:
            raise ValueError
        amount = round(amount, 2)
    except ValueError:
        await message.answer("❌ Введи положительное число.")
        return
    user_id = message.from_user.id
    balance = await get_user_balance(user_id)
    min_bet = 1.0
    max_bet = await get_setting_float("casino_max_bet")
    max_input = await get_setting_float("max_input_number")
    if amount < min_bet:
            if amount > balance:
        await message.answer("❌ Недостаточно баксов.")

    await state.update_data(amount=amount)
    await message.answer("Загадано число от 1 до 5. Введи свой вариант:")
    await GuessBet.number.set()

@dp.message_handler(state=GuessBet.number)
async def guess_number(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await casino_menu(message)
        return
    try:
        guess = int(message.text)
        if guess < 1 or guess > 5:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи число от 1 до 5.")
        return
    data = await state.get_data()
    amount = data['amount']
    user_id = message.from_user.id

    secret = random.randint(1, 5)
    win = (guess == secret)

    async with db_pool.acquire() as conn:
        await update_user_balance(user_id, -amount, conn=conn)
        await update_user_game_stats(user_id, 'guess', win, conn=conn)
        if win:
            multiplier = await get_setting_float("guess_multiplier")
            rep_reward = await get_setting_int("guess_reputation")
            profit = amount * multiplier
            await update_user_balance(user_id, profit, conn=conn)
            await update_user_reputation(user_id, rep_reward)
            exp = await get_setting_int("exp_per_guess_win")
            btc_reward = await get_setting_int("bitcoin_per_guess_win")
            if btc_reward > 0:
                await update_user_bitcoin(user_id, float(btc_reward), conn=conn)
            phrase = get_random_phrase(GUESS_WIN_PHRASES, secret=secret, profit=profit, rep=rep_reward)
            bet_data = {'number': guess}
        else:
            exp = await get_setting_int("exp_per_guess_lose")
            phrase = get_random_phrase(GUESS_LOSE_PHRASES, secret=secret, loss=amount)
            bet_data = {'number': guess}
        await add_exp(user_id, exp, conn=conn)

    await save_last_bet(user_id, 'guess', amount, bet_data)
    await set_global_cooldown(user_id, "guess")

    await message.answer(phrase, reply_markup=repeat_bet_keyboard('guess'))
    await state.finish()

# ----- Слоты -----
@dp.message_handler(lambda message: message.text == "🍒 Слоты")
async def slots_start(message: types.Message):
    if message.chat.type != 'private':
        return
    user_id = message.from_user.id
    min_level = await get_setting_int("min_level_slots")
    level = await get_user_level(user_id)
    if level < min_level:
        await message.answer(f"❌ Для этой игры нужен {min_level} уровень. Твой уровень: {level}")
        return
    await send_with_media(user_id, "Введи сумму ставки (можно дробную):", media_key='slots', reply_markup=back_keyboard())
    await SlotsBet.amount.set()

@dp.message_handler(state=SlotsBet.amount)
async def slots_bet(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await casino_menu(message)
        return
    
    ok, remaining = await check_global_cooldown(message.from_user.id, "slots")
    if not ok:
        await message.answer(f"⏳ Подожди ещё {remaining} сек.")
        return
    
    try:
        amount = float(message.text)
        if amount <= 0:
            raise ValueError
        amount = round(amount, 2)
    except ValueError:
        await message.answer("❌ Введи положительное число.")
        return
    user_id = message.from_user.id
    balance = await get_user_balance(user_id)
    min_bet = await get_setting_float("slots_min_bet")
    max_bet = await get_setting_float("slots_max_bet")
    max_input = await get_setting_float("max_input_number")
    if amount < min_bet or amount > max_bet:
        await message.answer(f"❌ Ставка должна быть от {min_bet:.2f} до {max_bet:.2f}.")
        return
    if amount > max_input:
        await message.answer(f"❌ Сумма слишком большая (максимум {max_input:.2f}).")
        return
    if amount > balance:
        await message.answer("❌ Недостаточно баксов.")
        return

    anim = await message.answer("🍒 Запускаем слоты...")
    stages = [
        "🍒 | 🍋 | 🍊",
        "🍋 | 🍊 | 7️⃣",
        "🍊 | 7️⃣ | 💎",
        "7️⃣ | 💎 | 🍒",
    ]
    for stage in stages:
        await asyncio.sleep(0.3)
        await anim.edit_text(stage)

    symbols, multiplier, win = await slots_spin()
    result_str = format_slots_result(symbols)

    async with db_pool.acquire() as conn:
        await update_user_balance(user_id, -amount, conn=conn)
        await update_user_game_stats(user_id, 'slots', win, conn=conn)
        if win:
            profit = amount * multiplier
            await update_user_balance(user_id, profit, conn=conn)
            exp = await get_setting_int("exp_per_slots_win")
            btc_reward = await get_setting_int("bitcoin_per_slots_win")
            if btc_reward > 0:
                await update_user_bitcoin(user_id, float(btc_reward), conn=conn)
            phrase = get_random_phrase(SLOTS_WIN_PHRASES, combo=result_str, multiplier=multiplier, profit=profit)
        else:
            exp = await get_setting_int("exp_per_slots_lose")
            phrase = get_random_phrase(SLOTS_LOSE_PHRASES, combo=result_str, loss=amount)
        await add_exp(user_id, exp, conn=conn)

    await save_last_bet(user_id, 'slots', amount)
    await set_global_cooldown(user_id, "slots")

    await anim.edit_text(phrase, reply_markup=repeat_bet_keyboard('slots'))
    await state.finish()

# ----- Рулетка -----
@dp.message_handler(lambda message: message.text == "🎡 Рулетка")
async def roulette_start(message: types.Message):
    if message.chat.type != 'private':
        return
    user_id = message.from_user.id
    min_level = await get_setting_int("min_level_roulette")
    level = await get_user_level(user_id)
    if level < min_level:
        await message.answer(f"❌ Для этой игры нужен {min_level} уровень. Твой уровень: {level}")
        return
    await send_with_media(user_id, "Введи сумму ставки (можно дробную):", media_key='roulette', reply_markup=back_keyboard())
    await RouletteBet.amount.set()

@dp.message_handler(state=RouletteBet.amount)
async def roulette_bet_amount(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await casino_menu(message)
        return
    
    ok, remaining = await check_global_cooldown(message.from_user.id, "roulette")
    if not ok:
        await message.answer(f"⏳ Подожди ещё {remaining} сек.")
        return
    
    try:
        amount = float(message.text)
        if amount <= 0:
            raise ValueError
        amount = round(amount, 2)
    except ValueError:
        await message.answer("❌ Введи положительное число.")
        return
    user_id = message.from_user.id
    balance = await get_user_balance(user_id)
    min_bet = await get_setting_float("roulette_min_bet")
    max_bet = await get_setting_float("roulette_max_bet")
    max_input = await get_setting_float("max_input_number")
    if amount < min_bet or amount > max_bet:
        await message.answer(f"❌ Ставка должна быть от {min_bet:.2f} до {max_bet:.2f}.")
        return
    if amount > max_input:
        await message.answer(f"❌ Сумма слишком большая (максимум {max_input:.2f}).")
        return
    if amount > balance:
        await message.answer("❌ Недостаточно баксов.")
        return
    await state.update_data(amount=amount)
    await message.answer("На что ставим? (red/black/green/number)", reply_markup=back_keyboard())
    await RouletteBet.bet_type.set()

@dp.message_handler(state=RouletteBet.bet_type)
async def roulette_bet_type(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await casino_menu(message)
        return
    bet_type = message.text.lower()
    if bet_type not in ['red', 'black', 'green', 'number']:
        await message.answer("❌ Выбери: red, black, green или number.")
        return
    await state.update_data(bet_type=bet_type)
    if bet_type == 'number':
        await message.answer("Введи число от 0 до 36:")
        await RouletteBet.number.set()
    else:
        await state.update_data(number=None)
        await process_roulette_bet(message, state)

@dp.message_handler(state=RouletteBet.number)
async def roulette_bet_number(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await casino_menu(message)
        return
    try:
        number = int(message.text)
        if number < 0 or number > 36:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи число от 0 до 36.")
        return
    await state.update_data(number=number)
    await process_roulette_bet(message, state)

async def process_roulette_bet(message: types.Message, state: FSMContext):
    data = await state.get_data()
    amount = data['amount']
    bet_type = data['bet_type']
    bet_number = data.get('number')
    user_id = message.from_user.id

    anim = await message.answer("🎡 Крутим рулетку...")
    for _ in range(3):
        await asyncio.sleep(0.5)
        await anim.edit_text("🎡 • •")
        await asyncio.sleep(0.5)
        await anim.edit_text("• 🎡 •")
        await asyncio.sleep(0.5)
        await anim.edit_text("• • 🎡")

    number, color, win = await roulette_spin(bet_type, bet_number)

    async with db_pool.acquire() as conn:
        await update_user_balance(user_id, -amount, conn=conn)
        await update_user_game_stats(user_id, 'roulette', win, conn=conn)
        if win:
            if bet_type == 'number':
                multiplier = await get_setting_float("roulette_number_multiplier")
            elif bet_type == 'green':
                multiplier = await get_setting_float("roulette_green_multiplier")
            else:
                multiplier = await get_setting_float("roulette_color_multiplier")
            profit = amount * multiplier
            await update_user_balance(user_id, profit, conn=conn)
            exp = await get_setting_int("exp_per_roulette_win")
            btc_reward = await get_setting_int("bitcoin_per_roulette_win")
            if btc_reward > 0:
                await update_user_bitcoin(user_id, float(btc_reward), conn=conn)
            phrase = get_random_phrase(ROULETTE_WIN_PHRASES, number=number, color=color, profit=profit)
            bet_data = {'bet_type': bet_type, 'number': bet_number}
        else:
            exp = await get_setting_int("exp_per_roulette_lose")
            phrase = get_random_phrase(ROULETTE_LOSE_PHRASES, number=number, color=color, loss=amount)
            bet_data = {'bet_type': bet_type, 'number': bet_number}
        await add_exp(user_id, exp, conn=conn)

    await save_last_bet(user_id, 'roulette', amount, bet_data)
    await set_global_cooldown(user_id, "roulette")

    await anim.edit_text(phrase, reply_markup=repeat_bet_keyboard('roulette'))
    await state.finish()
