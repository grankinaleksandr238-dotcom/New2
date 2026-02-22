import asyncio
import logging
import random
import string
from datetime import datetime
from typing import Optional, List

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot_instance import dp, bot
from bot_instance import dp, bot
from utils.db import (
    db_pool, ensure_user_exists, is_banned, is_admin,
    get_user_balance, update_user_balance, update_user_game_stats,
    add_exp, get_setting_int, get_setting_float, get_media_file_id,
    check_global_cooldown, set_global_cooldown, check_subscription
)
from utils.helpers import (
    safe_send_message, send_with_media, auto_delete_reply
)
from utils.states import MultiplayerGame, RoomChat
from utils.keyboards import (
    back_keyboard, cancel_keyboard, multiplayer_lobby_keyboard,
    room_control_keyboard, room_action_keyboard, leave_room_keyboard,
    main_menu_keyboard, subscription_inline
)
from utils.constants import MULTIPLAYER_PHRASES

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
def generate_game_id():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

def calculate_hand_value(cards):
    value = 0
    aces = 0
    for card in cards:
        rank = card[:-1]
        if rank in ['J', 'Q', 'K']:
            value += 10
        elif rank == 'A':
            aces += 1
            value += 11
        else:
            value += int(rank)
    while value > 21 and aces:
        value -= 10
        aces -= 1
    return value

def create_deck():
    suits = ['♠', '♥', '♦', '♣']
    ranks = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
    deck = [f"{rank}{suit}" for suit in suits for rank in ranks]
    random.shuffle(deck)
    return deck

async def get_multiplayer_game(game_id: str) -> Optional[dict]:
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM multiplayer_games WHERE game_id=$1", game_id)
        return dict(row) if row else None

async def get_game_players(game_id: str) -> List[dict]:
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM game_players WHERE game_id=$1 ORDER BY joined_at", game_id)
        return [dict(r) for r in rows]

async def add_player_to_game(game_id: str, user_id: int, username: str):
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            game = await conn.fetchrow("SELECT * FROM multiplayer_games WHERE game_id=$1 AND status='waiting' FOR UPDATE", game_id)
            if not game:
                raise ValueError("Игра не найдена или уже началась")
            players_count = await conn.fetchval("SELECT COUNT(*) FROM game_players WHERE game_id=$1", game_id)
            if players_count >= game['max_players']:
                raise ValueError("Комната уже полная")
            await conn.execute(
                "INSERT INTO game_players (game_id, user_id, username, cards, value, stopped, joined_at) VALUES ($1, $2, $3, $4, $5, $6, $7)",
                game_id, user_id, username, '', 0, False, datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )

async def remove_player_from_game(game_id: str, user_id: int):
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM game_players WHERE game_id=$1 AND user_id=$2", game_id, user_id)
        remaining = await conn.fetchval("SELECT COUNT(*) FROM game_players WHERE game_id=$1", game_id)
        if remaining == 0:
            await conn.execute("DELETE FROM multiplayer_games WHERE game_id=$1", game_id)

async def start_game(game_id: str):
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            game = await conn.fetchrow("SELECT * FROM multiplayer_games WHERE game_id=$1 AND status='waiting' FOR UPDATE", game_id)
            if not game:
                raise ValueError("Игра не найдена или уже началась")
            players = await conn.fetch("SELECT * FROM game_players WHERE game_id=$1 ORDER BY joined_at FOR UPDATE", game_id)
            if len(players) < 2:
                raise ValueError("Недостаточно игроков")

            bet_amount = float(game['bet_amount'])
            for player in players:
                balance = await get_user_balance(player['user_id'])
                if balance < bet_amount - 0.01:
                    raise ValueError(f"У игрока {player['username']} недостаточно баксов")
                await update_user_balance(player['user_id'], -bet_amount, conn=conn)

            deck = create_deck()
            deck_str = ','.join(deck)
            for player in players:
                cards = [deck.pop(), deck.pop()]
                value = calculate_hand_value(cards)
                await conn.execute(
                    "UPDATE game_players SET cards=$1, value=$2 WHERE game_id=$3 AND user_id=$4",
                    ','.join(cards), value, game_id, player['user_id']
                )
            await conn.execute(
                "UPDATE multiplayer_games SET status='playing', deck=$1, current_player_index=0 WHERE game_id=$2",
                deck_str, game_id
            )
            return game_id

async def get_current_player(game_id: str) -> Optional[dict]:
    async with db_pool.acquire() as conn:
        game = await conn.fetchrow("SELECT * FROM multiplayer_games WHERE game_id=$1", game_id)
        if not game or game['status'] != 'playing':
            return None
        players = await conn.fetch("SELECT * FROM game_players WHERE game_id=$1 ORDER BY joined_at", game_id)
        if not players:
            return None
        idx = game['current_player_index']
        if idx >= len(players):
            return None
        return dict(players[idx])

async def next_player(game_id: str) -> Optional[int]:
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            game = await conn.fetchrow("SELECT * FROM multiplayer_games WHERE game_id=$1 FOR UPDATE", game_id)
            if not game:
                return -1
            players = await conn.fetch("SELECT * FROM game_players WHERE game_id=$1 ORDER BY joined_at FOR UPDATE", game_id)
            if not players:
                return -1
            all_stopped = all(p['stopped'] or p['surrendered'] or p['value'] > 21 for p in players)
            if all_stopped:
                await finish_game(game_id)
                return -1
            current_idx = game['current_player_index']
            next_idx = current_idx
            for _ in range(len(players)):
                next_idx = (next_idx + 1) % len(players)
                p = players[next_idx]
                if not p['stopped'] and not p['surrendered'] and p['value'] <= 21:
                    await conn.execute("UPDATE multiplayer_games SET current_player_index=$1 WHERE game_id=$2", next_idx, game_id)
                    return next_idx
            await finish_game(game_id)
            return -1

async def finish_game(game_id: str):
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            game = await conn.fetchrow("SELECT * FROM multiplayer_games WHERE game_id=$1", game_id)
            if not game or game['status'] != 'playing':
                return
            players = await conn.fetch("SELECT * FROM game_players WHERE game_id=$1", game_id)
            if not players:
                await conn.execute("DELETE FROM multiplayer_games WHERE game_id=$1", game_id)
                return
            best_value = -1
            winner_id = None
            for p in players:
                val = p['value']
                if val <= 21 and val > best_value:
                    best_value = val
                    winner_id = p['user_id']
            bet_amount = float(game['bet_amount'])
            pot = bet_amount * len(players)
            if winner_id:
                await update_user_balance(winner_id, pot, conn=conn)
                await update_user_game_stats(winner_id, 'multiplayer', win=True, conn=conn)
                for p in players:
                    if p['user_id'] != winner_id:
                        await update_user_game_stats(p['user_id'], 'multiplayer', win=False, conn=conn)
                exp_win = await get_setting_int("exp_per_game_win")
                exp_lose = await get_setting_int("exp_per_game_lose")
                await add_exp(winner_id, exp_win, conn=conn)
                for p in players:
                    if p['user_id'] != winner_id:
                        await add_exp(p['user_id'], exp_lose, conn=conn)
                for p in players:
                    if p['user_id'] == winner_id:
                        await safe_send_message(p['user_id'], f"🎉 Ты выиграл в игре 21! Твой выигрыш: {pot:.2f} баксов.")
                    else:
                        await safe_send_message(p['user_id'], f"😢 Ты проиграл в игре 21. Твоя ставка {bet_amount:.2f} баксов потеряна.")
            else:
                for p in players:
                    await update_user_balance(p['user_id'], bet_amount, conn=conn)
                    await update_user_game_stats(p['user_id'], 'multiplayer', win=False, conn=conn)
                    await add_exp(p['user_id'], await get_setting_int("exp_per_game_lose"), conn=conn)
                    await safe_send_message(p['user_id'], f"🤝 В игре 21 ничья. Твоя ставка {bet_amount:.2f} баксов возвращена.")
            await conn.execute("DELETE FROM multiplayer_games WHERE game_id=$1", game_id)
            await conn.execute("DELETE FROM game_players WHERE game_id=$1", game_id)

async def show_current_turn(game_id: str, message: types.Message = None, user_id: int = None):
    game = await get_multiplayer_game(game_id)
    if not game or game['status'] != 'playing':
        return
    current_player = await get_current_player(game_id)
    if not current_player:
        return
    players = await get_game_players(game_id)
    text = f"🎮 Игра {game_id}\n\n"
    for p in players:
        cards = p['cards'].split(',') if p['cards'] else []
        card_str = ' '.join(cards) if cards else '❓'
        status = "✅" if p['stopped'] else "⏳" if p['user_id'] == current_player['user_id'] else "⏸️"
        if p['surrendered']:
            status = "🏳️"
        elif p['value'] > 21:
            status = "💥"
        text += f"{status} {p['username']}: {card_str} = {p['value'] if p['value']>0 else '?'}\n"
    text += f"\n💰 Твоя ставка: {float(game['bet_amount']):.2f} баксов"
    kb = room_action_keyboard(can_double=not current_player['doubled'])
    if user_id:
        await bot.send_message(user_id, text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)
      # ==================== ХЕНДЛЕРЫ ====================
@dp.message_handler(lambda message: message.text == "👥 Мультиплеер 21")
async def multiplayer_menu(message: types.Message):
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
    min_level = await get_setting_int("min_level_multiplayer")
    level = await get_user_level(user_id)
    if level < min_level:
        await message.answer(f"❌ Для игры в мультиплеер нужен {min_level} уровень. Твой уровень: {level}")
        return
    await send_with_media(user_id, "🎮 Мультиплеер 21 (очко)", media_key='multiplayer', reply_markup=multiplayer_lobby_keyboard())

@dp.message_handler(lambda message: message.text == "➕ Создать комнату")
async def create_room_start(message: types.Message):
    if message.chat.type != 'private':
        return
    await message.answer("Введи максимальное количество игроков (2-5):", reply_markup=back_keyboard())
    await MultiplayerGame.create_max_players.set()

@dp.message_handler(state=MultiplayerGame.create_max_players)
async def create_room_max_players(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await multiplayer_menu(message)
        return
    try:
        max_players = int(message.text)
        if max_players < 2 or max_players > 5:
            raise ValueError
    except:
        await message.answer("❌ Введи число от 2 до 5.")
        return
    await state.update_data(max_players=max_players)
    await message.answer("Введи ставку (можно дробную, например 10.50):")
    await MultiplayerGame.create_bet.set()

@dp.message_handler(state=MultiplayerGame.create_bet)
async def create_room_bet(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await multiplayer_menu(message)
        return
    try:
        bet = float(message.text)
        if bet <= 0:
            raise ValueError
        bet = round(bet, 2)
    except ValueError:
        await message.answer("❌ Введи положительное число с точностью до сотых.")
        return
    min_bet = await get_setting_float("multiplayer_min_bet")
    max_bet = await get_setting_float("multiplayer_max_bet")
    max_input = await get_setting_float("max_input_number")
    if bet < min_bet or bet > max_bet:
        await message.answer(f"❌ Ставка должна быть от {min_bet:.2f} до {max_bet:.2f}.")
        return
    if bet > max_input:
        await message.answer(f"❌ Сумма слишком большая (максимум {max_input:.2f}).")
        return
    user_id = message.from_user.id
    balance = await get_user_balance(user_id)
    if balance < bet:
        await message.answer("❌ Недостаточно баксов.")
        return
    data = await state.get_data()
    max_players = data['max_players']
    game_id = generate_game_id()
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO multiplayer_games (game_id, host_id, max_players, bet_amount, status, created_at) VALUES ($1, $2, $3, $4, $5, $6)",
            game_id, user_id, max_players, bet, 'waiting', datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        await conn.execute(
            "INSERT INTO game_players (game_id, user_id, username, cards, value, stopped, joined_at) VALUES ($1, $2, $3, $4, $5, $6, $7)",
            game_id, user_id, message.from_user.username or "Player", '', 0, False, datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
    await state.finish()
    text = (
        f"🎮 Комната {game_id} создана!\n"
        f"Ставка: {bet:.2f} баксов\n"
        f"Игроков: 1/{max_players}\n"
        f"Поделись этим ID с друзьями, чтобы они присоединились."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Присоединиться", url=f"https://t.me/{(await bot.me).username}?start=join_{game_id}")],
        [InlineKeyboardButton(text="❌ Закрыть комнату", callback_data=f"close_room_{game_id}")]
    ])
    await send_with_media(user_id, text, media_key='multiplayer', reply_markup=kb)

@dp.message_handler(lambda message: message.text == "🔍 Найти комнату")
async def join_room_by_code(message: types.Message):
    if message.chat.type != 'private':
        return
    await message.answer("Введи код комнаты (например, ABC123):", reply_markup=back_keyboard())
    await MultiplayerGame.join_code.set()

@dp.message_handler(state=MultiplayerGame.join_code)
async def join_room_code(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await multiplayer_menu(message)
        return
    game_id = message.text.strip().upper()
    user_id = message.from_user.id
    try:
        game = await get_multiplayer_game(game_id)
        if not game or game['status'] != 'waiting':
            await message.answer("❌ Комната не найдена или уже началась.")
            return
        players = await get_game_players(game_id)
        if len(players) >= game['max_players']:
            await message.answer("❌ Комната уже полная.")
            return
        if any(p['user_id'] == user_id for p in players):
            await message.answer("❌ Ты уже в этой комнате.")
            return
        balance = await get_user_balance(user_id)
        bet_amount = float(game['bet_amount'])
        if balance < bet_amount:
            await message.answer(f"❌ Недостаточно баксов для ставки {bet_amount:.2f}.")
            return
        await add_player_to_game(game_id, user_id, message.from_user.username or "Player")
        await message.answer(f"✅ Ты присоединился к комнате {game_id}.\nСтавка: {bet_amount:.2f} баксов.\nОжидаем начала игры.")
        host_id = game['host_id']
        await safe_send_message(host_id, f"🔔 Новый игрок {message.from_user.first_name} присоединился к комнате {game_id}. Текущий состав: {len(players)+1}/{game['max_players']}")
    except Exception as e:
        logging.error(f"Join room error: {e}", exc_info=True)
        await message.answer("❌ Ошибка при присоединении.")
    await state.finish()

@dp.message_handler(lambda message: message.text == "📋 Список комнат")
async def list_rooms(message: types.Message):
    if message.chat.type != 'private':
        return
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM multiplayer_games WHERE status='waiting' ORDER BY created_at DESC LIMIT 10")
    if not rows:
        await message.answer("Нет открытых комнат.")
        return
    text = "📋 Открытые комнаты:\n\n"
    for row in rows:
        players = await get_game_players(row['game_id'])
        text += f"🆔 {row['game_id']} | Ставка: {float(row['bet_amount']):.2f} | Игроков: {len(players)}/{row['max_players']}\n"
    await message.answer(text, reply_markup=multiplayer_lobby_keyboard())

@dp.callback_query_handler(lambda c: c.data.startswith("close_room_"))
async def close_room_callback(callback: types.CallbackQuery):
    await callback.answer()
    game_id = callback.data.split("_")[2]
    user_id = callback.from_user.id
    async with db_pool.acquire() as conn:
        game = await conn.fetchrow("SELECT * FROM multiplayer_games WHERE game_id=$1", game_id)
        if not game or game['host_id'] != user_id:
            await callback.message.answer("❌ Только создатель может закрыть комнату.")
            return
        await conn.execute("DELETE FROM multiplayer_games WHERE game_id=$1", game_id)
        await conn.execute("DELETE FROM game_players WHERE game_id=$1", game_id)
    await callback.message.edit_text("❌ Комната закрыта.")

@dp.callback_query_handler(lambda c: c.data.startswith("start_game_"))
async def start_game_callback(callback: types.CallbackQuery):
    await callback.answer()
    game_id = callback.data.split("_")[2]
    user_id = callback.from_user.id
    try:
        game = await get_multiplayer_game(game_id)
        if not game or game['host_id'] != user_id:
            await callback.message.answer("❌ Только создатель может начать игру.")
            return
        if game['status'] != 'waiting':
            await callback.message.answer("❌ Игра уже началась.")
            return
        players = await get_game_players(game_id)
        if len(players) < 2:
            await callback.message.answer("❌ Недостаточно игроков (минимум 2).")
            return
        await start_game(game_id)
        for p in players:
            await safe_send_message(p['user_id'], f"🎮 Игра {game_id} началась! Твой ход будет объявлен.")
        await show_current_turn(game_id, callback.message)
        await callback.message.delete()
    except Exception as e:
        logging.error(f"Start game error: {e}", exc_info=True)
        await callback.message.answer(f"❌ Ошибка: {str(e)}")
      @dp.callback_query_handler(lambda c: c.data in ["room_hit", "room_stand", "room_double", "room_surrender", "room_chat"])
async def room_action_callback(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    async with db_pool.acquire() as conn:
        game_row = await conn.fetchrow("""
            SELECT g.* FROM multiplayer_games g
            JOIN game_players p ON g.game_id = p.game_id
            WHERE p.user_id=$1 AND g.status='playing'
        """, user_id)
    if not game_row:
        await callback.message.answer("❌ Ты не участвуешь в активной игре.")
        return
    game_id = game_row['game_id']
    action = callback.data.split("_")[1] if "_" in callback.data else callback.data
    current = await get_current_player(game_id)
    if not current or current['user_id'] != user_id:
        await callback.message.answer("❌ Сейчас не твой ход.")
        return

    if action == "hit":
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                game = await conn.fetchrow("SELECT * FROM multiplayer_games WHERE game_id=$1 FOR UPDATE", game_id)
                deck = game['deck'].split(',')
                if not deck:
                    await callback.message.answer("❌ Колода закончилась!")
                    return
                card = deck.pop()
                new_deck = ','.join(deck)
                player = await conn.fetchrow("SELECT * FROM game_players WHERE game_id=$1 AND user_id=$2 FOR UPDATE", game_id, user_id)
                cards = player['cards'].split(',') if player['cards'] else []
                cards.append(card)
                value = calculate_hand_value(cards)
                await conn.execute(
                    "UPDATE game_players SET cards=$1, value=$2 WHERE game_id=$3 AND user_id=$4",
                    ','.join(cards), value, game_id, user_id
                )
                await conn.execute("UPDATE multiplayer_games SET deck=$1 WHERE game_id=$2", new_deck, game_id)
                if value > 21:
                    await conn.execute("UPDATE game_players SET stopped=TRUE WHERE game_id=$1 AND user_id=$2", game_id, user_id)
                    await next_player(game_id)
        await show_current_turn(game_id, user_id=user_id)

    elif action == "stand":
        async with db_pool.acquire() as conn:
            await conn.execute("UPDATE game_players SET stopped=TRUE WHERE game_id=$1 AND user_id=$2", game_id, user_id)
            await next_player(game_id)
        await show_current_turn(game_id, user_id=user_id)

    elif action == "double":
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                player = await conn.fetchrow("SELECT * FROM game_players WHERE game_id=$1 AND user_id=$2 FOR UPDATE", game_id, user_id)
                if player['doubled']:
                    await callback.message.answer("❌ Ты уже удваивал ставку.")
                    return
                game = await conn.fetchrow("SELECT * FROM multiplayer_games WHERE game_id=$1 FOR UPDATE", game_id)
                bet = float(game['bet_amount'])
                balance = await get_user_balance(user_id)
                if balance < bet:
                    await callback.message.answer("❌ Недостаточно баксов для удвоения.")
                    return
                await update_user_balance(user_id, -bet, conn=conn)
                await conn.execute("UPDATE game_players SET doubled=TRUE WHERE game_id=$1 AND user_id=$2", game_id, user_id)
                deck = game['deck'].split(',')
                if deck:
                    card = deck.pop()
                    new_deck = ','.join(deck)
                    cards = player['cards'].split(',') if player['cards'] else []
                    cards.append(card)
                    value = calculate_hand_value(cards)
                    await conn.execute(
                        "UPDATE game_players SET cards=$1, value=$2, stopped=TRUE WHERE game_id=$3 AND user_id=$4",
                        ','.join(cards), value, game_id, user_id
                    )
                    await conn.execute("UPDATE multiplayer_games SET deck=$1 WHERE game_id=$2", new_deck, game_id)
                else:
                    await conn.execute("UPDATE game_players SET stopped=TRUE WHERE game_id=$1 AND user_id=$2", game_id, user_id)
                await next_player(game_id)
        await show_current_turn(game_id, user_id=user_id)

    elif action == "surrender":
        async with db_pool.acquire() as conn:
            await conn.execute("UPDATE game_players SET surrendered=TRUE WHERE game_id=$1 AND user_id=$2", game_id, user_id)
            await next_player(game_id)
        await show_current_turn(game_id, user_id=user_id)

    elif action == "chat":
        await callback.message.answer("💬 Введи сообщение для всех игроков комнаты (или /cancel для выхода):", reply_markup=cancel_keyboard())
        await RoomChat.message.set()
        await state.update_data(game_id=game_id)

@dp.message_handler(state=RoomChat.message)
async def room_chat_message(message: types.Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.finish()
        await multiplayer_menu(message)
        return
    data = await state.get_data()
    game_id = data['game_id']
    players = await get_game_players(game_id)
    for p in players:
        if p['user_id'] != message.from_user.id:
            await safe_send_message(p['user_id'], f"💬 {message.from_user.first_name}: {message.text}")
    await message.answer("✅ Сообщение отправлено всем игрокам комнаты.")
    await state.finish()
    await show_current_turn(game_id, user_id=message.from_user.id)

@dp.callback_query_handler(lambda c: c.data.startswith("leave_room_"))
async def leave_room_callback(callback: types.CallbackQuery):
    await callback.answer()
    game_id = callback.data.split("_")[2]
    user_id = callback.from_user.id
    async with db_pool.acquire() as conn:
        game = await conn.fetchrow("SELECT * FROM multiplayer_games WHERE game_id=$1", game_id)
        if game and game['status'] == 'waiting':
            await remove_player_from_game(game_id, user_id)
            await callback.message.edit_text("✅ Ты покинул комнату.")
        else:
            await callback.message.answer("❌ Нельзя покинуть комнату после начала игры.")
