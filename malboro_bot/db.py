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
