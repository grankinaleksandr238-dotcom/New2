import os
import asyncio
import logging
import time
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Tuple, Any, Union
import random
import string
import json
import asyncpg
from asyncpg.pool import Pool

from constants import DEFAULT_SETTINGS

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL не задан. Создайте PostgreSQL базу.")

if "sslmode" not in DATABASE_URL:
    if "?" in DATABASE_URL:
        DATABASE_URL += "&sslmode=require"
    else:
        DATABASE_URL += "?sslmode=require"

db_pool: Optional[Pool] = None

settings_cache: Dict[str, str] = {}
settings_cache_lock = asyncio.Lock()
last_settings_update: float = 0

channels_cache: List[tuple] = []
channels_cache_lock = asyncio.Lock()
last_channels_update: float = 0

confirmed_chats_cache: Dict[int, dict] = {}
confirmed_chats_lock = asyncio.Lock()
last_confirmed_chats_update: float = 0

async def create_db_pool(retries: int = 5, delay: int = 3) -> None:
    global db_pool
    for attempt in range(1, retries + 1):
        try:
            db_pool = await asyncpg.create_pool(
                DATABASE_URL,
                min_size=5,
                max_size=20,
                command_timeout=60,
                max_queries=50000,
                max_inactive_connection_lifetime=300
            )
            logging.info(f"✅ Подключение к PostgreSQL установлено (попытка {attempt})")
            return
        except Exception as e:
            logging.error(f"❌ Ошибка подключения к БД (попытка {attempt}/{retries}): {e}")
            if attempt < retries:
                await asyncio.sleep(delay)
            else:
                raise

async def init_db() -> None:
    async with db_pool.acquire() as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                joined_date TEXT,
                balance NUMERIC(12,2) DEFAULT 0,
                reputation INTEGER DEFAULT 0,
                total_spent NUMERIC(12,2) DEFAULT 0,
                negative_balance NUMERIC(12,2) DEFAULT 0,
                last_bonus TEXT,
                last_theft_time TEXT,
                theft_attempts INTEGER DEFAULT 0,
                theft_success INTEGER DEFAULT 0,
                theft_failed INTEGER DEFAULT 0,
                theft_protected INTEGER DEFAULT 0,
                casino_wins INTEGER DEFAULT 0,
                casino_losses INTEGER DEFAULT 0,
                dice_wins INTEGER DEFAULT 0,
                dice_losses INTEGER DEFAULT 0,
                guess_wins INTEGER DEFAULT 0,
                guess_losses INTEGER DEFAULT 0,
                slots_wins INTEGER DEFAULT 0,
                slots_losses INTEGER DEFAULT 0,
                roulette_wins INTEGER DEFAULT 0,
                roulette_losses INTEGER DEFAULT 0,
                multiplayer_wins INTEGER DEFAULT 0,
                multiplayer_losses INTEGER DEFAULT 0,
                exp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 1,
                strength INTEGER DEFAULT 1,
                agility INTEGER DEFAULT 1,
                defense INTEGER DEFAULT 1,
                last_gift_time TEXT,
                gift_count_today INTEGER DEFAULT 0,
                global_authority INTEGER DEFAULT 0,
                smuggle_success INTEGER DEFAULT 0,
                smuggle_fail INTEGER DEFAULT 0,
                bitcoin_balance NUMERIC(12,4) DEFAULT 0,
                authority_balance INTEGER DEFAULT 0
            )
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS user_businesses (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                business_type_id INTEGER NOT NULL,
                level INTEGER DEFAULT 1,
                last_collection TEXT,
                accumulated INTEGER DEFAULT 0,
                UNIQUE(user_id, business_type_id)
            )
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS business_types (
                id SERIAL PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                emoji TEXT NOT NULL,
                base_price_btc NUMERIC(10,2) NOT NULL,
                base_income_cents INTEGER NOT NULL,
                description TEXT,
                max_level INTEGER DEFAULT 10,
                available BOOLEAN DEFAULT TRUE
            )
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS user_last_bets (
                user_id BIGINT,
                game TEXT,
                bet_amount NUMERIC(12,2),
                bet_data JSONB,
                updated_at TIMESTAMP DEFAULT NOW(),
                PRIMARY KEY (user_id, game)
            )
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS confirmed_chats (
                chat_id BIGINT PRIMARY KEY,
                title TEXT,
                type TEXT,
                joined_date TEXT,
                confirmed_by BIGINT,
                confirmed_date TEXT,
                notify_enabled BOOLEAN DEFAULT TRUE,
                last_gift_date DATE,
                gift_count_today INTEGER DEFAULT 0,
                boss_last_spawn TEXT,
                boss_spawn_count INTEGER DEFAULT 0,
                auto_delete_enabled BOOLEAN DEFAULT TRUE,
                last_boss_status_time TEXT
            )
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS chat_confirmation_requests (
                chat_id BIGINT PRIMARY KEY,
                title TEXT,
                type TEXT,
                requested_by BIGINT,
                request_date TEXT,
                status TEXT DEFAULT 'pending'
            )
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS bosses (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT,
                name TEXT,
                level INTEGER,
                hp INTEGER,
                max_hp INTEGER,
                spawned_at TEXT,
                expires_at TEXT,
                reward_coins INTEGER,
                reward_bitcoin INTEGER,
                participants BIGINT[] DEFAULT '{}',
                status TEXT DEFAULT 'active',
                image_file_id TEXT,
                description TEXT
            )
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS boss_attacks (
                boss_id INTEGER,
                user_id BIGINT,
                damage INTEGER,
                attack_time TEXT,
                PRIMARY KEY (boss_id, user_id)
            )
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS channels (
                id SERIAL PRIMARY KEY,
                chat_id TEXT UNIQUE,
                title TEXT,
                invite_link TEXT
            )
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS referrals (
                id SERIAL PRIMARY KEY,
                referrer_id BIGINT,
                referred_id BIGINT UNIQUE,
                referred_date TEXT,
                reward_given BOOLEAN DEFAULT FALSE,
                clicks INTEGER DEFAULT 0,
                active BOOLEAN DEFAULT FALSE
            )
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS shop_items (
                id SERIAL PRIMARY KEY,
                name TEXT,
                description TEXT,
                price NUMERIC(12,2),
                stock INTEGER DEFAULT -1,
                photo_file_id TEXT
            )
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS purchases (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                item_id INTEGER,
                purchase_date TEXT,
                status TEXT DEFAULT 'pending',
                admin_comment TEXT
            )
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS promocodes (
                code TEXT PRIMARY KEY,
                reward NUMERIC(12,2),
                max_uses INTEGER,
                used_count INTEGER DEFAULT 0,
                created_at TEXT
            )
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS promo_activations (
                user_id BIGINT,
                promo_code TEXT,
                activated_at TEXT,
                PRIMARY KEY (user_id, promo_code)
            )
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS giveaways (
                id SERIAL PRIMARY KEY,
                prize TEXT,
                description TEXT,
                end_date TEXT,
                media_file_id TEXT,
                media_type TEXT,
                status TEXT DEFAULT 'active',
                winner_id BIGINT,
                winners_count INTEGER DEFAULT 1,
                winners_list TEXT,
                notified BOOLEAN DEFAULT FALSE
            )
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS participants (
                user_id BIGINT,
                giveaway_id INTEGER,
                PRIMARY KEY (user_id, giveaway_id)
            )
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS admins (
                user_id BIGINT PRIMARY KEY,
                added_by BIGINT,
                added_date TEXT,
                permissions TEXT DEFAULT '[]'
            )
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS banned_users (
                user_id BIGINT PRIMARY KEY,
                banned_by BIGINT,
                banned_date TEXT,
                reason TEXT
            )
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id SERIAL PRIMARY KEY,
                name TEXT,
                description TEXT,
                task_type TEXT,
                target_id TEXT,
                reward_coins NUMERIC(12,2) DEFAULT 0,
                reward_reputation INTEGER DEFAULT 0,
                required_days INTEGER DEFAULT 0,
                penalty_days INTEGER DEFAULT 0,
                created_by BIGINT,
                created_at TEXT,
                active BOOLEAN DEFAULT TRUE,
                max_completions INTEGER DEFAULT 1,
                completed_count INTEGER DEFAULT 0
            )
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS user_tasks (
                user_id BIGINT,
                task_id INTEGER,
                completed_at TEXT,
                expires_at TEXT,
                status TEXT DEFAULT 'completed',
                PRIMARY KEY (user_id, task_id)
            )
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS multiplayer_games (
                game_id TEXT PRIMARY KEY,
                host_id BIGINT,
                max_players INTEGER,
                bet_amount NUMERIC(12,2),
                status TEXT DEFAULT 'waiting',
                deck TEXT,
                created_at TEXT,
                current_player_index INTEGER DEFAULT 0
            )
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS game_players (
                game_id TEXT,
                user_id BIGINT,
                username TEXT,
                cards TEXT,
                value INTEGER DEFAULT 0,
                stopped BOOLEAN DEFAULT FALSE,
                joined_at TEXT,
                doubled BOOLEAN DEFAULT FALSE,
                surrendered BOOLEAN DEFAULT FALSE,
                PRIMARY KEY (game_id, user_id)
            )
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS level_rewards (
                level INTEGER PRIMARY KEY,
                coins NUMERIC(12,2),
                reputation INTEGER
            )
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS auctions (
                id SERIAL PRIMARY KEY,
                item_name TEXT NOT NULL,
                description TEXT,
                start_price NUMERIC(12,2) NOT NULL,
                current_price NUMERIC(12,2) NOT NULL,
                start_time TIMESTAMP NOT NULL DEFAULT NOW(),
                end_time TIMESTAMP,
                target_price NUMERIC(12,2),
                status TEXT DEFAULT 'active',
                winner_id BIGINT,
                created_by BIGINT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                photo_file_id TEXT
            )
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS auction_bids (
                id SERIAL PRIMARY KEY,
                auction_id INTEGER REFERENCES auctions(id) ON DELETE CASCADE,
                user_id BIGINT NOT NULL,
                bid_amount NUMERIC(12,2) NOT NULL,
                bid_time TIMESTAMP DEFAULT NOW()
            )
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS chat_authority (
                chat_id BIGINT,
                user_id BIGINT,
                authority INTEGER DEFAULT 0,
                total_damage INTEGER DEFAULT 0,
                fights INTEGER DEFAULT 0,
                PRIMARY KEY (chat_id, user_id)
            )
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS fight_cooldowns (
                chat_id BIGINT,
                user_id BIGINT,
                last_fight TIMESTAMP,
                PRIMARY KEY (chat_id, user_id)
            )
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS global_cooldowns (
                user_id BIGINT,
                command TEXT,
                last_used TIMESTAMP,
                PRIMARY KEY (user_id, command)
            )
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS fight_logs (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT,
                user_id BIGINT,
                timestamp TIMESTAMP DEFAULT NOW(),
                damage INTEGER,
                authority_gained INTEGER,
                outcome TEXT
            )
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS ads (
                id SERIAL PRIMARY KEY,
                text TEXT NOT NULL,
                interval_minutes INTEGER DEFAULT 60,
                last_sent TIMESTAMP,
                enabled BOOLEAN DEFAULT TRUE,
                target TEXT DEFAULT 'chats'
            )
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS bitcoin_orders (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                type TEXT NOT NULL CHECK (type IN ('buy', 'sell')),
                amount NUMERIC(12,4) NOT NULL CHECK (amount > 0),
                price INTEGER NOT NULL CHECK (price >= 1),
                total_locked NUMERIC(12,4) NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                status TEXT DEFAULT 'active' CHECK (status IN ('active', 'completed', 'cancelled'))
            )
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS bitcoin_trades (
                id SERIAL PRIMARY KEY,
                buy_order_id INTEGER REFERENCES bitcoin_orders(id),
                sell_order_id INTEGER REFERENCES bitcoin_orders(id),
                amount NUMERIC(12,4) NOT NULL,
                price INTEGER NOT NULL,
                buyer_id BIGINT NOT NULL,
                seller_id BIGINT NOT NULL,
                traded_at TIMESTAMP DEFAULT NOW()
            )
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS smuggle_runs (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                chat_id BIGINT,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                status TEXT DEFAULT 'in_progress',
                result TEXT,
                smuggle_amount NUMERIC(12,4) DEFAULT 0,
                notified BOOLEAN DEFAULT FALSE
            )
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS smuggle_cooldowns (
                user_id BIGINT PRIMARY KEY,
                cooldown_until TIMESTAMP
            )
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS media (
                id SERIAL PRIMARY KEY,
                key TEXT UNIQUE NOT NULL,
                file_id TEXT NOT NULL,
                description TEXT
            )
        ''')

        await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_balance ON users(balance DESC)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_reputation ON users(reputation DESC)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_total_spent ON users(total_spent DESC)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_username_lower ON users(LOWER(username))")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_purchases_user_id ON purchases(user_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_purchases_status ON purchases(status)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_giveaways_status ON giveaways(status)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_promo_activations_user ON promo_activations(user_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_user_tasks_expires ON user_tasks(expires_at)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_active ON tasks(active)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_multiplayer_games_status ON multiplayer_games(status)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_level ON users(level)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_exp ON users(exp)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_bosses_chat_status ON bosses(chat_id, status)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_boss_attacks_boss ON boss_attacks(boss_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_boss_attacks_user ON boss_attacks(user_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_confirmed_chats_chat ON confirmed_chats(chat_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_requests_status ON chat_confirmation_requests(status)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_auctions_status ON auctions(status)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_auctions_end_time ON auctions(end_time)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_auction_bids_auction ON auction_bids(auction_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_authority_chat ON chat_authority(chat_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_fight_cooldowns_chat ON fight_cooldowns(chat_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_fight_logs_timestamp ON fight_logs(timestamp)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_ads_enabled ON ads(enabled)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_bitcoin_orders_user ON bitcoin_orders(user_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_bitcoin_orders_status ON bitcoin_orders(status)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_bitcoin_orders_type ON bitcoin_orders(type)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_smuggle_runs_user ON smuggle_runs(user_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_smuggle_runs_end ON smuggle_runs(end_time)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_user_businesses_user ON user_businesses(user_id)")

    await init_settings()
    await init_level_rewards()
    await init_business_types()
    logging.info("✅ Таблицы в PostgreSQL проверены/обновлены")

async def init_settings():
    async with db_pool.acquire() as conn:
        for key, value in DEFAULT_SETTINGS.items():
            await conn.execute(
                "INSERT INTO settings (key, value) VALUES ($1, $2) ON CONFLICT (key) DO NOTHING",
                key, value
            )

async def init_level_rewards():
    async with db_pool.acquire() as conn:
        for lvl in range(1, 101):
            exists = await conn.fetchval("SELECT level FROM level_rewards WHERE level=$1", lvl)
            if not exists:
                coins = int(DEFAULT_SETTINGS["level_reward_coins"]) + (lvl-1) * int(DEFAULT_SETTINGS["level_reward_coins_increment"])
                rep = int(DEFAULT_SETTINGS["level_reward_reputation"]) + (lvl-1) * int(DEFAULT_SETTINGS["level_reward_reputation_increment"])
                await conn.execute(
                    "INSERT INTO level_rewards (level, coins, reputation) VALUES ($1, $2, $3)",
                    lvl, float(coins), rep
                )

async def init_business_types():
    async with db_pool.acquire() as conn:
        count = await conn.fetchval("SELECT COUNT(*) FROM business_types")
        if count == 0:
            businesses = [
                ("🥙 Ларёк с шаурмой", "🥙", 5.0, 60, "Уличная точка быстрого питания. Приносит стабильный, но небольшой доход.", 10),
                ("🏪 Магазин у дома", "🏪", 15.0, 120, "Небольшой продуктовый магазин. Доход выше, чем у ларька.", 10),
                ("🚗 Автомойка", "🚗", 30.0, 180, "Мойка самообслуживания. Требует вложений, но окупается.", 10),
                ("☕ Кафе", "☕", 50.0, 220, "Уютное кафе в центре. Хороший пассивный доход.", 10),
                ("🏨 Мини-отель", "🏨", 80.0, 260, "Небольшая гостиница. Доход позволяет не работать.", 10),
                ("🏬 Торговый центр", "🏬", 150.0, 298, "Крупный торговый комплекс. Максимальный доход (до 500 баксов/неделю).", 10),
            ]
            for name, emoji, price, income, desc, max_lvl in businesses:
                await conn.execute(
                    "INSERT INTO business_types (name, emoji, base_price_btc, base_income_cents, description, max_level, available) VALUES ($1, $2, $3, $4, $5, $6, $7)",
                    name, emoji, price, income, desc, max_lvl, True
                )

async def get_setting(key: str) -> str:
    global settings_cache, last_settings_update
    async with settings_cache_lock:
        now = time.time()
        if now - last_settings_update > 60 or not settings_cache:
            async with db_pool.acquire() as conn:
                rows = await conn.fetch("SELECT key, value FROM settings")
                settings_cache = {row['key']: row['value'] for row in rows}
            last_settings_update = now
        value = settings_cache.get(key)
        if value is None:
            value = DEFAULT_SETTINGS.get(key, "")
            if value:
                async with db_pool.acquire() as conn:
                    await conn.execute(
                        "INSERT INTO settings (key, value) VALUES ($1, $2) ON CONFLICT (key) DO NOTHING",
                        key, value
                    )
                settings_cache[key] = value
        return value

async def get_setting_float(key: str) -> float:
    val = await get_setting(key)
    try:
        return float(val)
    except:
        return 0.0

async def get_setting_int(key: str) -> int:
    val = await get_setting(key)
    try:
        return int(val)
    except:
        return 0

async def set_setting(key: str, value: str):
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE settings SET value=$1 WHERE key=$2", value, key)
    async with settings_cache_lock:
        settings_cache[key] = value
        global last_settings_update
        last_settings_update = 0

async def get_channels():
    global channels_cache, last_channels_update
    async with channels_cache_lock:
        now = time.time()
        if now - last_channels_update > 300 or not channels_cache:
            async with db_pool.acquire() as conn:
                rows = await conn.fetch("SELECT chat_id, title, invite_link FROM channels")
                channels_cache = [(r['chat_id'], r['title'], r['invite_link']) for r in rows]
            last_channels_update = now
        return channels_cache

async def get_confirmed_chats(force_update=False) -> Dict[int, dict]:
    global confirmed_chats_cache, last_confirmed_chats_update
    async with confirmed_chats_lock:
        now = time.time()
        if force_update or now - last_confirmed_chats_update > 300 or not confirmed_chats_cache:
            async with db_pool.acquire() as conn:
                rows = await conn.fetch("SELECT * FROM confirmed_chats")
                confirmed_chats_cache = {row['chat_id']: dict(row) for row in rows}
            last_confirmed_chats_update = now
        return confirmed_chats_cache

async def is_chat_confirmed(chat_id: int) -> bool:
    confirmed = await get_confirmed_chats()
    return chat_id in confirmed

async def add_confirmed_chat(chat_id: int, title: str, chat_type: str, confirmed_by: int):
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO confirmed_chats (chat_id, title, type, joined_date, confirmed_by, confirmed_date) VALUES ($1, $2, $3, $4, $5, $6) ON CONFLICT (chat_id) DO UPDATE SET confirmed_by=$5, confirmed_date=$6",
            chat_id, title, chat_type, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), confirmed_by, datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
    await get_confirmed_chats(force_update=True)

async def remove_confirmed_chat(chat_id: int):
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM confirmed_chats WHERE chat_id=$1", chat_id)
    await get_confirmed_chats(force_update=True)

async def create_chat_confirmation_request(chat_id: int, title: str, chat_type: str, requested_by: int):
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO chat_confirmation_requests (chat_id, title, type, requested_by, request_date, status) VALUES ($1, $2, $3, $4, $5, $6) ON CONFLICT (chat_id) DO UPDATE SET status='pending', requested_by=$4, request_date=$5",
            chat_id, title, chat_type, requested_by, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 'pending'
        )

async def get_pending_chat_requests() -> List[dict]:
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM chat_confirmation_requests WHERE status='pending' ORDER BY request_date")
        return [dict(r) for r in rows]

async def update_chat_request_status(chat_id: int, status: str):
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE chat_confirmation_requests SET status=$1 WHERE chat_id=$2", status, chat_id)

async def get_media_file_id(key: str) -> Optional[str]:
    async with db_pool.acquire() as conn:
        file_id = await conn.fetchval("SELECT file_id FROM media WHERE key=$1", key)
        return file_id
        async def ensure_user_exists(user_id: int, username: str = None, first_name: str = None):
    async with db_pool.acquire() as conn:
        exists = await conn.fetchval("SELECT 1 FROM users WHERE user_id=$1", user_id)
        if not exists:
            bonus = await get_setting_float("new_user_bonus")
            await conn.execute(
                "INSERT INTO users (user_id, username, first_name, joined_date, balance, reputation, total_spent, negative_balance, exp, level, strength, agility, defense, bitcoin_balance, authority_balance) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)",
                user_id, username, first_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                bonus, 0, 0, 0, 0, 1, 1, 1, 1, 0.0, 0
            )
            return True, bonus
    return False, 0

async def get_user_balance(user_id: int) -> float:
    async with db_pool.acquire() as conn:
        balance = await conn.fetchval("SELECT balance FROM users WHERE user_id=$1", user_id)
        return float(balance) if balance is not None else 0.0

async def update_user_balance(user_id: int, delta: float, conn=None):
    delta = float(delta)
    async def _update(conn):
        row = await conn.fetchrow("SELECT balance, negative_balance FROM users WHERE user_id=$1", user_id)
        if not row:
            await ensure_user_exists(user_id)
            row = {'balance': 0.0, 'negative_balance': 0.0}
        balance = float(row['balance'])
        negative = float(row['negative_balance']) if row['negative_balance'] else 0.0
        new_balance = balance + delta
        if new_balance < 0:
            negative += abs(new_balance)
            new_balance = 0.0
        new_balance = round(new_balance, 2)
        negative = round(negative, 2)
        await conn.execute(
            "UPDATE users SET balance=$1, negative_balance=$2 WHERE user_id=$3",
            new_balance, negative, user_id
        )
    if conn:
        await _update(conn)
    else:
        async with db_pool.acquire() as new_conn:
            await _update(new_conn)

async def get_user_bitcoin(user_id: int) -> float:
    async with db_pool.acquire() as conn:
        btc = await conn.fetchval("SELECT bitcoin_balance FROM users WHERE user_id=$1", user_id)
        return float(btc) if btc is not None else 0.0

async def update_user_bitcoin(user_id: int, delta: float, conn=None):
    delta = float(delta)
    async def _update(conn):
        row = await conn.fetchrow("SELECT bitcoin_balance FROM users WHERE user_id=$1", user_id)
        if not row:
            await ensure_user_exists(user_id)
            row = {'bitcoin_balance': 0.0}
        current = float(row['bitcoin_balance'])
        new_balance = current + delta
        if new_balance < 0:
            raise ValueError("Недостаточно биткоинов")
        new_balance = round(new_balance, 4)
        await conn.execute(
            "UPDATE users SET bitcoin_balance=$1 WHERE user_id=$2",
            new_balance, user_id
        )
    if conn:
        await _update(conn)
    else:
        async with db_pool.acquire() as new_conn:
            await _update(new_conn)

async def get_user_authority(user_id: int) -> int:
    async with db_pool.acquire() as conn:
        auth = await conn.fetchval("SELECT authority_balance FROM users WHERE user_id=$1", user_id)
        return auth if auth is not None else 0

async def update_user_authority(user_id: int, delta: int, conn=None):
    async def _update(conn):
        await conn.execute(
            "UPDATE users SET authority_balance = authority_balance + $1 WHERE user_id=$2",
            delta, user_id
        )
    if conn:
        await _update(conn)
    else:
        async with db_pool.acquire() as new_conn:
            await _update(new_conn)

async def get_user_reputation(user_id: int) -> int:
    async with db_pool.acquire() as conn:
        rep = await conn.fetchval("SELECT reputation FROM users WHERE user_id=$1", user_id)
        return rep if rep is not None else 0

async def update_user_reputation(user_id: int, delta: int):
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE users SET reputation = reputation + $1 WHERE user_id=$2", delta, user_id)

async def get_user_stats(user_id: int) -> dict:
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT level, strength, agility, defense FROM users WHERE user_id=$1", user_id)
        if row:
            return dict(row)
        return {'level': 1, 'strength': 1, 'agility': 1, 'defense': 1}

async def update_user_stats(user_id: int, strength_delta=0, agility_delta=0, defense_delta=0):
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET strength = strength + $1, agility = agility + $2, defense = defense + $3 WHERE user_id=$4",
            strength_delta, agility_delta, defense_delta, user_id
        )

async def update_user_game_stats(user_id: int, game: str, win: bool, conn=None):
    async def _update(conn):
        if win:
            if game == 'casino':
                await conn.execute("UPDATE users SET casino_wins = casino_wins + 1 WHERE user_id=$1", user_id)
            elif game == 'dice':
                await conn.execute("UPDATE users SET dice_wins = dice_wins + 1 WHERE user_id=$1", user_id)
            elif game == 'guess':
                await conn.execute("UPDATE users SET guess_wins = guess_wins + 1 WHERE user_id=$1", user_id)
            elif game == 'slots':
                await conn.execute("UPDATE users SET slots_wins = slots_wins + 1 WHERE user_id=$1", user_id)
            elif game == 'roulette':
                await conn.execute("UPDATE users SET roulette_wins = roulette_wins + 1 WHERE user_id=$1", user_id)
            elif game == 'multiplayer':
                await conn.execute("UPDATE users SET multiplayer_wins = multiplayer_wins + 1 WHERE user_id=$1", user_id)
        else:
            if game == 'casino':
                await conn.execute("UPDATE users SET casino_losses = casino_losses + 1 WHERE user_id=$1", user_id)
            elif game == 'dice':
                await conn.execute("UPDATE users SET dice_losses = dice_losses + 1 WHERE user_id=$1", user_id)
            elif game == 'guess':
                await conn.execute("UPDATE users SET guess_losses = guess_losses + 1 WHERE user_id=$1", user_id)
            elif game == 'slots':
                await conn.execute("UPDATE users SET slots_losses = slots_losses + 1 WHERE user_id=$1", user_id)
            elif game == 'roulette':
                await conn.execute("UPDATE users SET roulette_losses = roulette_losses + 1 WHERE user_id=$1", user_id)
            elif game == 'multiplayer':
                await conn.execute("UPDATE users SET multiplayer_losses = multiplayer_losses + 1 WHERE user_id=$1", user_id)
    if conn:
        await _update(conn)
    else:
        async with db_pool.acquire() as new_conn:
            await _update(new_conn)

async def add_exp(user_id: int, exp: int, conn=None):
    async def _add(conn):
        user = await conn.fetchrow("SELECT exp, level FROM users WHERE user_id=$1", user_id)
        if not user:
            return
        new_exp = user['exp'] + exp
        level = user['level']
        level_mult = await get_setting_int("level_multiplier")
        if level_mult <= 0:
            level_mult = 1
        levels_gained = 0
        while new_exp >= level * level_mult:
            new_exp -= level * level_mult
            level += 1
            levels_gained += 1
        await conn.execute(
            "UPDATE users SET exp=$1, level=$2 WHERE user_id=$3",
            new_exp, level, user_id
        )
        if levels_gained > 0:
            str_inc = await get_setting_int("stat_strength_per_level") * levels_gained
            agi_inc = await get_setting_int("stat_agility_per_level") * levels_gained
            def_inc = await get_setting_int("stat_defense_per_level") * levels_gained
            await update_user_stats(user_id, str_inc, agi_inc, def_inc)
            for lvl in range(level - levels_gained + 1, level + 1):
                await reward_level_up(user_id, lvl, conn)
    if conn:
        await _add(conn)
    else:
        async with db_pool.acquire() as conn2:
            await _add(conn2)

async def reward_level_up(user_id: int, new_level: int, conn=None):
    async def _reward(conn):
        reward = await conn.fetchrow(
            "SELECT coins, reputation FROM level_rewards WHERE level=$1",
            new_level
        )
        if reward:
            await update_user_balance(user_id, float(reward['coins']), conn=conn)
            await update_user_reputation(user_id, reward['reputation'])
    if conn:
        await _reward(conn)
    else:
        async with db_pool.acquire() as conn2:
            await _reward(conn2)

async def get_user_level(user_id: int) -> int:
    async with db_pool.acquire() as conn:
        level = await conn.fetchval("SELECT level FROM users WHERE user_id=$1", user_id)
        return level if level is not None else 1

async def get_user_exp(user_id: int) -> int:
    async with db_pool.acquire() as conn:
        exp = await conn.fetchval("SELECT exp FROM users WHERE user_id=$1", user_id)
        return exp if exp is not None else 0

async def update_user_total_spent(user_id: int, amount: float):
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE users SET total_spent = total_spent + $1 WHERE user_id=$2", amount, user_id)

async def get_random_user(exclude_id: int):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT user_id FROM users 
            WHERE user_id != $1 AND user_id NOT IN (SELECT user_id FROM banned_users)
            ORDER BY RANDOM() LIMIT 1
        """, exclude_id)
        return row['user_id'] if row else None

async def check_global_cooldown(user_id: int, command: str) -> Tuple[bool, int]:
    cooldown = await get_setting_int("global_cooldown_seconds")
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT last_used FROM global_cooldowns WHERE user_id=$1 AND command=$2", user_id, command)
        if row and row['last_used']:
            diff = datetime.now() - row['last_used']
            remaining = cooldown - diff.total_seconds()
            if remaining > 0:
                return False, int(remaining)
    return True, 0

async def set_global_cooldown(user_id: int, command: str):
    async with db_pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO global_cooldowns (user_id, command, last_used)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id, command) DO UPDATE SET last_used = $3
        ''', user_id, command, datetime.now())

async def get_business_type_list(only_available: bool = True) -> List[dict]:
    async with db_pool.acquire() as conn:
        if only_available:
            rows = await conn.fetch("SELECT * FROM business_types WHERE available = TRUE ORDER BY base_price_btc")
        else:
            rows = await conn.fetch("SELECT * FROM business_types ORDER BY base_price_btc")
        result = []
        for r in rows:
            d = dict(r)
            d['base_price_btc'] = float(d['base_price_btc'])
            result.append(d)
        return result

async def get_business_type(business_type_id: int) -> Optional[dict]:
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM business_types WHERE id=$1", business_type_id)
        if row:
            d = dict(row)
            d['base_price_btc'] = float(d['base_price_btc'])
            return d
        return None

async def get_user_businesses(user_id: int) -> List[dict]:
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT ub.*, bt.name, bt.emoji, bt.base_price_btc, bt.base_income_cents, bt.max_level
            FROM user_businesses ub
            JOIN business_types bt ON ub.business_type_id = bt.id
            WHERE ub.user_id = $1
            ORDER BY bt.base_price_btc
        """, user_id)
        result = []
        for r in rows:
            d = dict(r)
            d['base_price_btc'] = float(d['base_price_btc'])
            result.append(d)
        return result

async def get_user_business(user_id: int, business_type_id: int) -> Optional[dict]:
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT ub.*, bt.name, bt.emoji, bt.base_price_btc, bt.base_income_cents, bt.max_level
            FROM user_businesses ub
            JOIN business_types bt ON ub.business_type_id = bt.id
            WHERE ub.user_id = $1 AND ub.business_type_id = $2
        """, user_id, business_type_id)
        if row:
            d = dict(row)
            d['base_price_btc'] = float(d['base_price_btc'])
            return d
        return None

async def get_business_price(business_type: dict, level: int) -> float:
    base_price = business_type['base_price_btc']
    if level == 1:
        return base_price
    else:
        upgrade_base = await get_setting_float("business_upgrade_cost_per_level")
        cost = upgrade_base * (level ** 1.5)
        return round(cost, 2)

async def get_business_income(business_type: dict, level: int) -> int:
    return business_type['base_income_cents'] * level

async def create_user_business(user_id: int, business_type_id: int):
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO user_businesses (user_id, business_type_id, level, last_collection, accumulated) VALUES ($1, $2, $3, $4, $5) ON CONFLICT (user_id, business_type_id) DO NOTHING",
            user_id, business_type_id, 1, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 0
        )

async def update_business_income(user_id: int, conn=None):
    async def _update(conn):
        now = datetime.now()
        businesses = await conn.fetch(
            "SELECT ub.*, bt.base_income_cents FROM user_businesses ub JOIN business_types bt ON ub.business_type_id = bt.id WHERE ub.user_id=$1",
            user_id
        )
        for biz in businesses:
            if biz['last_collection']:
                try:
                    last_col = datetime.strptime(biz['last_collection'], "%Y-%m-%d %H:%M:%S")
                    hours_passed = int((now - last_col).total_seconds() // 3600)
                    if hours_passed > 0:
                        income_per_hour = biz['base_income_cents'] * biz['level']
                        new_accum = biz['accumulated'] + hours_passed * income_per_hour
                        await conn.execute(
                            "UPDATE user_businesses SET accumulated=$1, last_collection=$2 WHERE id=$3",
                            new_accum, now.strftime("%Y-%m-%d %H:%M:%S"), biz['id']
                        )
                except:
                    pass
    if conn:
        await _update(conn)
    else:
        async with db_pool.acquire() as new_conn:
            await _update(new_conn)

async def collect_business_income(user_id: int, business_id: int) -> Tuple[bool, str]:
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            biz = await conn.fetchrow("SELECT * FROM user_businesses WHERE id=$1 AND user_id=$2", business_id, user_id)
            if not biz:
                return False, "Бизнес не найден."
            if biz['accumulated'] == 0:
                return False, "Нет дохода для сбора."
            amount_cents = biz['accumulated']
            coins = amount_cents // 100
            remainder = amount_cents % 100
            if coins > 0:
                await update_user_balance(user_id, float(coins), conn=conn)
            await conn.execute(
                "UPDATE user_businesses SET accumulated=$1, last_collection=$2 WHERE id=$3",
                remainder, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), business_id
            )
            return True, f"Собрано {coins} баксов и {remainder} центов."

async def upgrade_business(user_id: int, business_id: int) -> Tuple[bool, str]:
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            biz = await conn.fetchrow("""
                SELECT ub.*, bt.base_price_btc, bt.base_income_cents, bt.max_level 
                FROM user_businesses ub 
                JOIN business_types bt ON ub.business_type_id = bt.id 
                WHERE ub.id=$1 AND ub.user_id=$2
            """, business_id, user_id)
            if not biz:
                return False, "Бизнес не найден."
            if biz['level'] >= biz['max_level']:
                return False, f"Бизнес уже максимального уровня ({biz['max_level']})."
            base_price = float(biz['base_price_btc'])
            cost = await get_business_price({'base_price_btc': base_price}, biz['level'] + 1)
            btc_balance = await get_user_bitcoin(user_id)
            if btc_balance < cost - 0.0001:
                return False, f"Недостаточно биткоинов. Нужно {cost:.2f} BTC, у вас {btc_balance:.4f}."
            await update_user_bitcoin(user_id, -cost, conn=conn)
            await conn.execute(
                "UPDATE user_businesses SET level = level + 1 WHERE id=$1",
                business_id
            )
            return True, f"✅ Бизнес улучшен до уровня {biz['level'] + 1}! Потрачено {cost:.2f} BTC."

async def get_chat_authority(chat_id: int, user_id: int) -> int:
    async with db_pool.acquire() as conn:
        val = await conn.fetchval("SELECT authority FROM chat_authority WHERE chat_id=$1 AND user_id=$2", chat_id, user_id)
        return val if val is not None else 0

async def add_chat_authority(chat_id: int, user_id: int, amount: int, damage: int = 0):
    async with db_pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO chat_authority (chat_id, user_id, authority, total_damage, fights)
            VALUES ($1, $2, $3, $4, 1)
            ON CONFLICT (chat_id, user_id) DO UPDATE
            SET authority = chat_authority.authority + $3,
                total_damage = chat_authority.total_damage + $4,
                fights = chat_authority.fights + 1
        ''', chat_id, user_id, amount, damage)

async def get_total_user_authority(user_id: int) -> int:
    async with db_pool.acquire() as conn:
        total = await conn.fetchval("SELECT SUM(authority) FROM chat_authority WHERE user_id=$1", user_id)
        return total or 0

async def get_total_user_fights(user_id: int) -> Tuple[int, int]:
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT SUM(fights) as total_fights, SUM(total_damage) as total_damage FROM chat_authority WHERE user_id=$1",
            user_id
        )
        return (row['total_fights'] or 0, row['total_damage'] or 0)

async def spend_chat_authority(chat_id: int, user_id: int, amount: int) -> bool:
    current = await get_chat_authority(chat_id, user_id)
    if current < amount:
        return False
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE chat_authority SET authority = authority - $1 WHERE chat_id=$2 AND user_id=$3", amount, chat_id, user_id)
    return True

async def log_fight(chat_id: int, user_id: int, damage: int, authority: int, outcome: str):
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO fight_logs (chat_id, user_id, timestamp, damage, authority_gained, outcome) VALUES ($1, $2, $3, $4, $5, $6)",
            chat_id, user_id, datetime.now(), damage, authority, outcome
        )

async def can_fight(chat_id: int, user_id: int) -> Tuple[bool, int]:
    cooldown = await get_setting_int("fight_cooldown_minutes")
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT last_fight FROM fight_cooldowns WHERE chat_id=$1 AND user_id=$2", chat_id, user_id)
        if row and row['last_fight']:
            diff = datetime.now() - row['last_fight']
            remaining = cooldown * 60 - diff.total_seconds()
            if remaining > 0:
                return False, int(remaining)
        return True, 0

async def set_fight_cooldown(chat_id: int, user_id: int):
    async with db_pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO fight_cooldowns (chat_id, user_id, last_fight)
            VALUES ($1, $2, $3)
            ON CONFLICT (chat_id, user_id) DO UPDATE SET last_fight = $3
        ''', chat_id, user_id, datetime.now())
        BOSS_NAMES = [
    "Дон Корлеоне", "Крёстный отец", "Аль Капоне", "Люциано", "Гамбино",
    "Джон Готти", "Фрэнк Костелло", "Мейер Лански", "Багси Сигел",
    "Сальваторе Теста", "Карло Гамбино", "Пол Кастеллано", "Винсент Джиганте",
    "Крёстный отец", "Мафиози", "Гангстер", "Рэкетир"
]

BOSS_DESCRIPTIONS = [
    "Глава мафиозного клана, держит в страхе весь район.",
    "Безжалостный гангстер, правая рука дона.",
    "Известный рэкетир, контролирует подпольный бизнес.",
    "Старый вор в законе, уважаемый в криминальном мире.",
    "Молодой и амбициозный лидер банды.",
    "Торговец оружием, всегда при деньгах.",
    "Налётчик со стажем, его боятся даже полицейские.",
    "Киллер, на счету которого десятки жертв.",
    "Хозяин подпольных казино и притонов.",
    "Смотрящий за городом, решает все вопросы."
]

async def spawn_boss(chat_id: int, level: int = None, image_file_id: str = None):
    if level is None:
        level = random.randint(1, 5)
    name = random.choice(BOSS_NAMES)
    description = random.choice(BOSS_DESCRIPTIONS)
    hp_mult = await get_setting_int("boss_hp_multiplier")
    hp = level * hp_mult * random.randint(5, 10)
    base_reward_coins = await get_setting_int("boss_reward_coins")
    variance_coins = await get_setting_int("boss_reward_coins_variance")
    reward_coins = base_reward_coins + random.randint(-variance_coins, variance_coins)
    base_reward_btc = await get_setting_int("boss_reward_bitcoin")
    variance_btc = await get_setting_int("boss_reward_bitcoin_variance")
    reward_btc = base_reward_btc + random.randint(-variance_btc, variance_btc)
    now = datetime.now()
    expires_at = now + timedelta(hours=2)
    async with db_pool.acquire() as conn:
        boss_id = await conn.fetchval(
            "INSERT INTO bosses (chat_id, name, level, hp, max_hp, spawned_at, expires_at, reward_coins, reward_bitcoin, participants, status, image_file_id, description) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13) RETURNING id",
            chat_id, name, level, hp, hp, now.strftime("%Y-%m-%d %H:%M:%S"),
            expires_at.strftime("%Y-%m-%d %H:%M:%S"), reward_coins, reward_btc, [], 'active', image_file_id, description
        )
        await conn.execute(
            "UPDATE confirmed_chats SET boss_last_spawn=$1, boss_spawn_count = boss_spawn_count + 1 WHERE chat_id=$2",
            now.strftime("%Y-%m-%d %H:%M:%S"), chat_id
        )
    return boss_id

async def finish_boss_fight(boss_id: int):
    async with db_pool.acquire() as conn:
        boss = await conn.fetchrow("SELECT * FROM bosses WHERE id=$1", boss_id)
        if not boss or boss['status'] != 'active':
            return
        participants = boss['participants'] or []
        if not participants:
            await conn.execute("UPDATE bosses SET status='defeated' WHERE id=$1", boss_id)
            return
        reward_coins = boss['reward_coins']
        reward_btc = boss['reward_bitcoin']
        coins_per_player = reward_coins // len(participants)
        btc_per_player = reward_btc // len(participants)
        remainder_coins = reward_coins % len(participants)
        remainder_btc = reward_btc % len(participants)
        for i, uid in enumerate(participants):
            coins = coins_per_player + (1 if i < remainder_coins else 0)
            btc = btc_per_player + (1 if i < remainder_btc else 0)
            await update_user_balance(uid, float(coins), conn=conn)
            await update_user_bitcoin(uid, float(btc), conn=conn)
            exp = await get_setting_int("exp_per_game_win")
            await add_exp(uid, exp, conn=conn)
        await conn.execute("UPDATE bosses SET status='defeated' WHERE id=$1", boss_id)

async def calculate_fight_damage(strength: int) -> int:
    base = await get_setting_int("fight_base_damage")
    variance = await get_setting_int("fight_damage_variance")
    damage = base + strength // 2 + random.randint(-variance, variance)
    return max(1, damage)

async def calculate_fight_authority() -> int:
    min_auth = await get_setting_int("fight_authority_min")
    max_auth = await get_setting_int("fight_authority_max")
    return random.randint(min_auth, max_auth)

def is_critical(strength: int, agility: int) -> bool:
    chance = 5 + agility * 2
    if chance > 50:
        chance = 50
    return random.randint(1, 100) <= chance

def is_counter(defense: int) -> bool:
    chance = 5 + defense * 1
    if chance > 40:
        chance = 40
    return random.randint(1, 100) <= chance

async def slots_spin() -> Tuple[List[str], float, bool]:
    symbols = ['🍒', '🍋', '🍊', '7️⃣', '💎']
    result = [random.choice(symbols) for _ in range(3)]
    win_prob = await get_setting_float("slots_win_probability")
    win = random.random() * 100 <= win_prob
    if not win:
        while result[0] == result[1] or result[1] == result[2] or result[0] == result[2]:
            result = [random.choice(symbols) for _ in range(3)]
        return result, 0, False
    else:
        if random.random() < 0.1:
            sym = random.choice(symbols)
            result = [sym, sym, sym]
        else:
            sym = random.choice(symbols)
            pos = random.randint(0, 2)
            result = [random.choice(symbols) for _ in range(3)]
            result[pos] = sym
            result[(pos+1)%3] = sym
        if result[0] == result[1] == result[2]:
            if result[0] == '7️⃣':
                multiplier = await get_setting_float("slots_multiplier_seven")
            elif result[0] == '💎':
                multiplier = await get_setting_float("slots_multiplier_diamond")
            else:
                multiplier = await get_setting_float("slots_multiplier_three")
            return result, multiplier, True
        else:
            return result, 2.0, True

def format_slots_result(symbols: List[str]) -> str:
    return " | ".join(symbols)

async def roulette_spin(bet_type: str, bet_number: int = None) -> Tuple[int, str, bool]:
    number = random.randint(0, 36)
    color = 'green' if number == 0 else ('red' if number % 2 == 0 else 'black')
    if bet_type == 'number':
        if bet_number == number:
            return number, color, True
        else:
            return number, color, False
    elif bet_type == 'red':
        if color == 'red':
            return number, color, True
        else:
            return number, color, False
    elif bet_type == 'black':
        if color == 'black':
            return number, color, True
        else:
            return number, color, False
    elif bet_type == 'green':
        if color == 'green':
            return number, color, True
        else:
            return number, color, False
    else:
        return number, color, False

async def check_smuggle_cooldown(user_id: int) -> Tuple[bool, int]:
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT cooldown_until FROM smuggle_cooldowns WHERE user_id=$1", user_id)
        if row and row['cooldown_until']:
            cooldown_until = row['cooldown_until']
            if isinstance(cooldown_until, str):
                cooldown_until = datetime.strptime(cooldown_until, "%Y-%m-%d %H:%M:%S")
            remaining = (cooldown_until - datetime.now()).total_seconds()
            if remaining > 0:
                return False, int(remaining)
    return True, 0

async def set_smuggle_cooldown(user_id: int, penalty: int = 0):
    base = await get_setting_int("smuggle_cooldown_minutes")
    cooldown_until = datetime.now() + timedelta(minutes=base + penalty)
    async with db_pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO smuggle_cooldowns (user_id, cooldown_until)
            VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE SET cooldown_until = $2
        ''', user_id, cooldown_until)

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

async def perform_cleanup(manual=False):
    days_bosses = await get_setting_int("cleanup_days_bosses")
    days_auctions = await get_setting_int("cleanup_days_auctions")
    days_purchases = await get_setting_int("cleanup_days_purchases")
    days_giveaways = await get_setting_int("cleanup_days_giveaways")
    days_tasks = await get_setting_int("cleanup_days_user_tasks")
    days_fight = await get_setting_int("cleanup_days_fight_logs")
    days_smuggle = await get_setting_int("cleanup_days_smuggle")
    days_orders = await get_setting_int("cleanup_days_bitcoin_orders")

    now = datetime.now()
    cutoff_bosses = (now - timedelta(days=days_bosses)).strftime("%Y-%m-%d %H:%M:%S")
    cutoff_purchases = (now - timedelta(days=days_purchases)).strftime("%Y-%m-%d %H:%M:%S")
    cutoff_giveaways = (now - timedelta(days=days_giveaways)).strftime("%Y-%m-%d %H:%M:%S")
    cutoff_tasks = (now - timedelta(days=days_tasks)).strftime("%Y-%m-%d %H:%M:%S")
    cutoff_smuggle = (now - timedelta(days=days_smuggle)).strftime("%Y-%m-%d %H:%M:%S")
    cutoff_auctions = now - timedelta(days=days_auctions)
    cutoff_fight = now - timedelta(days=days_fight)
    cutoff_orders = now - timedelta(days=days_orders)

    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM bosses WHERE status IN ('defeated', 'expired') AND spawned_at < $1", cutoff_bosses)
        await conn.execute("DELETE FROM boss_attacks WHERE attack_time < $1", cutoff_bosses)
        await conn.execute("DELETE FROM purchases WHERE status IN ('completed','rejected') AND purchase_date < $1", cutoff_purchases)
        await conn.execute("DELETE FROM giveaways WHERE status='completed' AND end_date < $1", cutoff_giveaways)
        await conn.execute("DELETE FROM user_tasks WHERE expires_at IS NOT NULL AND expires_at < $1", cutoff_tasks)
        await conn.execute("DELETE FROM smuggle_runs WHERE status IN ('completed', 'failed') AND end_time < $1", cutoff_smuggle)
        await conn.execute("DELETE FROM auctions WHERE status='ended' AND end_time < $1", cutoff_auctions)
        await conn.execute("DELETE FROM fight_logs WHERE timestamp < $1", cutoff_fight)
        await conn.execute("DELETE FROM bitcoin_orders WHERE status IN ('completed', 'cancelled') AND created_at < $1", cutoff_orders)

        cooldown_minutes = await get_setting_int("fight_cooldown_minutes")
        cutoff_cooldown = now - timedelta(minutes=cooldown_minutes * 2)
        await conn.execute("DELETE FROM global_cooldowns WHERE last_used < $1", cutoff_cooldown)

    if manual:
        logging.info("Ручная очистка выполнена.")
    else:
        logging.info("Автоматическая очистка выполнена.")

async def export_users_to_csv() -> bytes:
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM users ORDER BY user_id")
    if not rows:
        return b""
    import csv, io
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(dict(rows[0]).keys())
    for row in rows:
        row_dict = dict(row)
        for k, v in row_dict.items():
            if isinstance(v, (asyncpg.pgproto.pgdecimal.Decimal, float)):
                row_dict[k] = float(v)
        writer.writerow(row_dict.values())
    return output.getvalue().encode('utf-8')

ALLOWED_TABLES = ['users', 'purchases', 'bosses', 'auctions', 'giveaways', 'tasks', 'chat_authority', 'fight_logs', 'bitcoin_orders']

async def export_table_to_csv(table: str) -> Optional[bytes]:
    if table not in ALLOWED_TABLES:
        return None
    async with db_pool.acquire() as conn:
        try:
            exists = await conn.fetchval(
                "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = $1)",
                table
            )
            if not exists:
                return None
            rows = await conn.fetch(f"SELECT * FROM {table} ORDER BY id")
        except Exception:
            return None
        if not rows:
            return None
        import csv, io
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(dict(rows[0]).keys())
        for row in rows:
            row_dict = dict(row)
            for k, v in row_dict.items():
                if isinstance(v, (asyncpg.pgproto.pgdecimal.Decimal, float)):
                    row_dict[k] = float(v)
            writer.writerow(row_dict.values())
        return output.getvalue().encode('utf-8')

async def get_order_book() -> Dict[str, List[Dict]]:
    async with db_pool.acquire() as conn:
        buy_orders = await conn.fetch("""
            SELECT price, SUM(amount) as total_amount, COUNT(*) as count
            FROM bitcoin_orders
            WHERE type='buy' AND status='active'
            GROUP BY price
            ORDER BY price DESC
        """)
        sell_orders = await conn.fetch("""
            SELECT price, SUM(amount) as total_amount, COUNT(*) as count
            FROM bitcoin_orders
            WHERE type='sell' AND status='active'
            GROUP BY price
            ORDER BY price ASC
        """)
        bids = []
        for r in buy_orders:
            bids.append({
                'price': r['price'],
                'total_amount': float(r['total_amount']),
                'count': r['count']
            })
        asks = []
        for r in sell_orders:
            asks.append({
                'price': r['price'],
                'total_amount': float(r['total_amount']),
                'count': r['count']
            })
        return {'bids': bids, 'asks': asks}

async def get_active_orders(order_type: str = None) -> List[dict]:
    async with db_pool.acquire() as conn:
        if order_type == 'buy':
            rows = await conn.fetch("SELECT * FROM bitcoin_orders WHERE type='buy' AND status='active' ORDER BY price DESC, created_at ASC")
        elif order_type == 'sell':
            rows = await conn.fetch("SELECT * FROM bitcoin_orders WHERE type='sell' AND status='active' ORDER BY price ASC, created_at ASC")
        else:
            rows = await conn.fetch("SELECT * FROM bitcoin_orders WHERE status='active' ORDER BY created_at DESC")
        result = []
        for r in rows:
            d = dict(r)
            d['amount'] = float(d['amount'])
            d['total_locked'] = float(d['total_locked'])
            result.append(d)
        return result

async def create_bitcoin_order(user_id: int, order_type: str, amount: float, price: int) -> int:
    try:
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                if order_type == 'sell':
                    current_btc = await get_user_bitcoin(user_id)
                    if current_btc < amount - 0.0001:
                        raise ValueError("Недостаточно BTC")
                    await update_user_bitcoin(user_id, -amount, conn=conn)
                    total_locked = amount
                else:
                    total_cost = amount * price
                    current_balance = await get_user_balance(user_id)
                    if current_balance < total_cost - 0.01:
                        raise ValueError("Недостаточно баксов")
                    max_input = await get_setting_float("max_input_number")
                    if total_cost > max_input:
                        raise ValueError(f"Сумма слишком большая (максимум {max_input:.2f})")
                    await update_user_balance(user_id, -total_cost, conn=conn)
                    total_locked = total_cost

                order_id = await conn.fetchval(
                    "INSERT INTO bitcoin_orders (user_id, type, amount, price, total_locked) VALUES ($1, $2, $3, $4, $5) RETURNING id",
                    user_id, order_type, amount, price, total_locked
                )
                await match_orders(conn)
                return order_id
    except ValueError as e:
        raise e
    except Exception as e:
        logging.error(f"Unexpected error in create_bitcoin_order for user {user_id}: {e}", exc_info=True)
        raise ValueError("Внутренняя ошибка сервера. Попробуйте позже.")

async def cancel_bitcoin_order(order_id: int, user_id: int) -> bool:
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            order = await conn.fetchrow("SELECT * FROM bitcoin_orders WHERE id=$1 AND user_id=$2 AND status='active'", order_id, user_id)
            if not order:
                return False
            total_locked = float(order['total_locked'])
            if order['type'] == 'sell':
                await update_user_bitcoin(user_id, total_locked, conn=conn)
            else:
                await update_user_balance(user_id, total_locked, conn=conn)
            await conn.execute("UPDATE bitcoin_orders SET status='cancelled' WHERE id=$1", order_id)
            return True

async def match_orders(conn):
    while True:
        buy = await conn.fetchrow("""
            SELECT id, user_id, price, amount, total_locked
            FROM bitcoin_orders
            WHERE type='buy' AND status='active'
            ORDER BY price DESC, created_at ASC
            LIMIT 1
        """)
        sell = await conn.fetchrow("""
            SELECT id, user_id, price, amount, total_locked
            FROM bitcoin_orders
            WHERE type='sell' AND status='active'
            ORDER BY price ASC, created_at ASC
            LIMIT 1
        """)
        if not buy or not sell or buy['price'] < sell['price']:
            break

        buy_amount = float(buy['amount'])
        buy_total_locked = float(buy['total_locked'])
        sell_amount = float(sell['amount'])
        sell_total_locked = float(sell['total_locked'])
        trade_price = sell['price']

        trade_amount = min(buy_amount, sell_amount)
        total_cost = trade_amount * trade_price

        buyer_id = buy['user_id']
        seller_id = sell['user_id']

        await update_user_balance(seller_id, total_cost, conn=conn)
        await update_user_bitcoin(buyer_id, trade_amount, conn=conn)

        new_buy_amount = max(0, buy_amount - trade_amount)
        new_sell_amount = max(0, sell_amount - trade_amount)
        new_buy_locked = max(0, buy_total_locked - total_cost)
        new_sell_locked = max(0, sell_total_locked - trade_amount)

        new_buy_amount = round(new_buy_amount, 8)
        new_sell_amount = round(new_sell_amount, 8)
        new_buy_locked = round(new_buy_locked, 8)
        new_sell_locked = round(new_sell_locked, 8)

        if new_buy_amount <= 1e-8:
            await conn.execute("UPDATE bitcoin_orders SET status='completed', amount=0, total_locked=0 WHERE id=$1", buy['id'])
        else:
            await conn.execute("UPDATE bitcoin_orders SET amount=$1, total_locked=$2 WHERE id=$3", new_buy_amount, new_buy_locked, buy['id'])

        if new_sell_amount <= 1e-8:
            await conn.execute("UPDATE bitcoin_orders SET status='completed', amount=0, total_locked=0 WHERE id=$1", sell['id'])
        else:
            await conn.execute("UPDATE bitcoin_orders SET amount=$1, total_locked=$2 WHERE id=$3", new_sell_amount, new_sell_locked, sell['id'])

        await conn.execute(
            "INSERT INTO bitcoin_trades (buy_order_id, sell_order_id, amount, price, buyer_id, seller_id) VALUES ($1, $2, $3, $4, $5, $6)",
            buy['id'], sell['id'], trade_amount, trade_price, buyer_id, seller_id
      )
