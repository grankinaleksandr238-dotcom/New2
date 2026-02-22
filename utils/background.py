import asyncio
import logging
import random
from datetime import datetime, timedelta, date

from bot_instance import bot
from db import (
    db_pool, get_setting, get_setting_int, get_setting_float,
    get_confirmed_chats, get_user_reputation, get_media_file_id,
    update_user_bitcoin, update_user_balance, add_exp, set_smuggle_cooldown,
    spawn_boss
)
from constants import (
    SMUGGLE_SUCCESS_PHRASES, SMUGGLE_CAUGHT_PHRASES, SMUGGLE_LOST_PHRASES
)
from helpers import get_random_phrase, notify_chats

async def process_smuggle_runs():
    while True:
        try:
            await asyncio.sleep(30)
            now = datetime.now()
            async with db_pool.acquire() as conn:
                runs = await conn.fetch("""
                    SELECT * FROM smuggle_runs
                    WHERE status = 'in_progress' AND end_time::timestamp <= $1 AND notified = FALSE
                """, now)

                for run in runs:
                    try:
                        user_id = run['user_id']
                        chat_id = run['chat_id']

                        rep = await get_user_reputation(user_id)

                        success_chance = await get_setting_float("smuggle_success_chance")
                        caught_chance = await get_setting_float("smuggle_caught_chance")
                        lost_chance = await get_setting_float("smuggle_lost_chance")

                        rep_success_bonus = float(await get_setting_float("reputation_smuggle_success_bonus")) * rep
                        max_bonus = await get_setting_float("reputation_max_bonus_percent")
                        rep_success_bonus = min(rep_success_bonus, max_bonus)

                        total_success_chance = min(success_chance + rep_success_bonus, 100)
                        remaining = 100 - total_success_chance
                        if remaining < 0:
                            remaining = 0

                        total_base_catch_lost = caught_chance + lost_chance
                        if total_base_catch_lost > 0:
                            adjusted_caught = int(remaining * caught_chance / total_base_catch_lost)
                            adjusted_lost = remaining - adjusted_caught
                        else:
                            adjusted_caught = 0
                            adjusted_lost = 0

                        rand = random.randint(1, 100)
                        result_text = ""
                        status = ""
                        amount = 0.0
                        penalty = 0

                        if rand <= total_success_chance:
                            base_amount = await get_setting_float("smuggle_base_amount")
                            rep_bonus = float(await get_setting_float("reputation_smuggle_bonus")) * rep
                            amount = base_amount + rep_bonus
                            await update_user_bitcoin(user_id, amount, conn=conn)
                            await conn.execute(
                                "UPDATE users SET smuggle_success = smuggle_success + 1 WHERE user_id = $1",
                                user_id
                            )
                            result_text = get_random_phrase(SMUGGLE_SUCCESS_PHRASES, amount=amount)
                            status = 'completed'
                            penalty = 0
                        elif rand <= total_success_chance + adjusted_caught:
                            penalty = await get_setting_int("smuggle_fail_penalty_minutes")
                            await conn.execute(
                                "UPDATE users SET smuggle_fail = smuggle_fail + 1 WHERE user_id = $1",
                                user_id
                            )
                            result_text = get_random_phrase(SMUGGLE_CAUGHT_PHRASES)
                            status = 'failed'
                        else:
                            await conn.execute(
                                "UPDATE users SET smuggle_fail = smuggle_fail + 1 WHERE user_id = $1",
                                user_id
                            )
                            result_text = get_random_phrase(SMUGGLE_LOST_PHRASES)
                            status = 'failed'
                            penalty = 0

                        await conn.execute(
                            "UPDATE smuggle_runs SET status = $1, notified = TRUE, result = $2, smuggle_amount = $3 WHERE id = $4",
                            status, result_text, amount, run['id']
                        )

                        if chat_id:
                            try:
                                user = await conn.fetchrow("SELECT first_name FROM users WHERE user_id=$1", user_id)
                                name = user['first_name'] if user else f"ID {user_id}"
                                file_id = await get_media_file_id('smuggle_result')
                                if file_id:
                                    await bot.send_photo(chat_id, file_id, caption=f"{result_text}\n(для {name})")
                                else:
                                    await bot.send_message(chat_id, f"{result_text}\n(для {name})")
                            except:
                                await bot.send_message(user_id, result_text)
                        else:
                            await bot.send_message(user_id, result_text)

                        await set_smuggle_cooldown(user_id, penalty)

                        exp = await get_setting_int("exp_per_smuggle")
                        await add_exp(user_id, exp, conn=conn)
                    except Exception as e:
                        logging.error(f"Error processing smuggle run {run['id']}: {e}", exc_info=True)
        except Exception as e:
            logging.error(f"Error in process_smuggle_runs: {e}", exc_info=True)
            await asyncio.sleep(60)

async def check_auctions():
    while True:
        try:
            await asyncio.sleep(60)
            now = datetime.now()
            async with db_pool.acquire() as conn:
                expired = await conn.fetch("""
                    SELECT * FROM auctions
                    WHERE status = 'active' AND end_time IS NOT NULL AND end_time <= $1
                """, now)

                for auction in expired:
                    try:
                        auction_id = auction['id']
                        winner_bid = await conn.fetchrow("""
                            SELECT user_id, bid_amount FROM auction_bids
                            WHERE auction_id = $1
                            ORDER BY bid_amount DESC, bid_time ASC
                            LIMIT 1
                        """, auction_id)

                        if winner_bid:
                            winner_id = winner_bid['user_id']
                            final_price = float(winner_bid['bid_amount'])
                            await conn.execute(
                                "UPDATE auctions SET status = 'ended', winner_id = $1, current_price = $2 WHERE id = $3",
                                winner_id, final_price, auction_id
                            )
                            await bot.send_message(
                                winner_id,
                                f"🎉 Поздравляем! Вы выиграли аукцион «{auction['item_name']}» с ценой {final_price:.2f} баксов. Админ скоро свяжется."
                            )
                            await bot.send_message(
                                auction['created_by'],
                                f"🏁 Аукцион «{auction['item_name']}» завершён. Победитель: {winner_id}, цена: {final_price:.2f}."
                            )
                        else:
                            await conn.execute(
                                "UPDATE auctions SET status = 'ended', winner_id = NULL WHERE id = $1",
                                auction_id
                            )
                            await bot.send_message(
                                auction['created_by'],
                                f"🏁 Аукцион «{auction['item_name']}» завершён без ставок."
                            )
                    except Exception as e:
                        logging.error(f"Error processing auction {auction['id']}: {e}", exc_info=True)
        except Exception as e:
            logging.error(f"Error in check_auctions: {e}", exc_info=True)
            await asyncio.sleep(60)

async def boss_spawn_scheduler():
    while True:
        try:
            await asyncio.sleep(1800)
            spawn_chance = await get_setting_int("boss_spawn_chance")
            if random.randint(1, 100) > spawn_chance:
                continue

            async with db_pool.acquire() as conn:
                chat_row = await conn.fetchrow("""
                    SELECT chat_id FROM confirmed_chats 
                    WHERE boss_spawn_count < (SELECT value::int FROM settings WHERE key='boss_max_per_day')
                    ORDER BY RANDOM() LIMIT 1
                """)
                if not chat_row:
                    continue
                chat_id = chat_row['chat_id']

            max_per_day = await get_setting_int("boss_max_per_day")
            today = date.today().isoformat()

            async with db_pool.acquire() as conn2:
                chat_data = await conn2.fetchrow(
                    "SELECT boss_last_spawn, boss_spawn_count FROM confirmed_chats WHERE chat_id = $1",
                    chat_id
                )
                if chat_data:
                    last_spawn_str = chat_data['boss_last_spawn']
                    spawn_count = chat_data['boss_spawn_count']

                    if last_spawn_str:
                        try:
                            last_spawn_date = datetime.strptime(last_spawn_str, "%Y-%m-%d %H:%M:%S").date()
                            if last_spawn_date == date.today():
                                if spawn_count >= max_per_day:
                                    continue
                            else:
                                await conn2.execute(
                                    "UPDATE confirmed_chats SET boss_spawn_count = 0 WHERE chat_id = $1",
                                    chat_id
                                )
                        except:
                            pass

                existing = await conn2.fetchval(
                    "SELECT 1 FROM bosses WHERE chat_id = $1 AND status = 'active'",
                    chat_id
                )
                if existing:
                    continue

            image_file_id = await get_media_file_id('boss_default')
            level = random.randint(1, 5)
            await spawn_boss(chat_id, level=level, image_file_id=image_file_id)
        except Exception as e:
            logging.error(f"Error in boss_spawn_scheduler: {e}", exc_info=True)
            await asyncio.sleep(60)

async def ad_sender():
    while True:
        try:
            await asyncio.sleep(300)
            now = datetime.now()
            async with db_pool.acquire() as conn:
                ads = await conn.fetch("SELECT * FROM ads WHERE enabled = TRUE")
                for ad in ads:
                    try:
                        last_sent = ad['last_sent']
                        interval = ad['interval_minutes']
                        if last_sent:
                            try:
                                if isinstance(last_sent, str):
                                    last = datetime.strptime(last_sent, "%Y-%m-%d %H:%M:%S.%f")
                                else:
                                    last = last_sent
                                if (now - last).total_seconds() < interval * 60:
                                    continue
                            except:
                                pass

                        target = ad['target']
                        recipients = []

                        if target in ('chats', 'all'):
                            confirmed = await get_confirmed_chats()
                            for chat_id in confirmed.keys():
                                recipients.append(('chat', chat_id))
                        if target in ('private', 'all'):
                            async with db_pool.acquire() as conn2:
                                users = await conn2.fetch("SELECT user_id FROM users")
                                for u in users:
                                    recipients.append(('user', u['user_id']))

                        sent_count = 0
                        for typ, dest in recipients:
                            try:
                                if typ == 'chat':
                                    await bot.send_message(dest, ad['text'])
                                else:
                                    await bot.send_message(dest, ad['text'])
                                sent_count += 1
                            except:
                                pass
                            await asyncio.sleep(0.05)

                        await conn.execute(
                            "UPDATE ads SET last_sent = $1 WHERE id = $2",
                            now, ad['id']
                        )
                        logging.info(f"Ad {ad['id']} sent to {sent_count} recipients")
                    except Exception as e:
                        logging.error(f"Error processing ad {ad['id']}: {e}", exc_info=True)
        except Exception as e:
            logging.error(f"Error in ad_sender: {e}", exc_info=True)
            await asyncio.sleep(60)

async def check_giveaways():
    while True:
        try:
            await asyncio.sleep(60)
            now = datetime.now()
            async with db_pool.acquire() as conn:
                expired = await conn.fetch("""
                    SELECT * FROM giveaways
                    WHERE status = 'active' AND end_date <= $1
                """, now.strftime("%Y-%m-%d %H:%M:%S"))

                for gw in expired:
                    try:
                        gw_id = gw['id']
                        winners_count = gw['winners_count'] or 1
                        participants = await conn.fetch("SELECT user_id FROM participants WHERE giveaway_id=$1", gw_id)
                        participant_ids = [p['user_id'] for p in participants]

                        if not participant_ids:
                            winners_list = "нет участников"
                        elif len(participant_ids) <= winners_count:
                            winners = participant_ids
                            winners_list = ", ".join(str(uid) for uid in winners)
                        else:
                            winners = random.sample(participant_ids, winners_count)
                            winners_list = ", ".join(str(uid) for uid in winners)

                        await conn.execute(
                            "UPDATE giveaways SET status='completed', winners_list=$1 WHERE id=$2",
                            winners_list, gw_id
                        )

                        for uid in winners:
                            await bot.send_message(uid, f"🎉 Поздравляем! Вы выиграли в розыгрыше #{gw_id}: {gw['prize']}!")
                        if await get_setting("chat_notify_giveaway") == "1":
                            confirmed = await get_confirmed_chats()
                            for chat_id, data in confirmed.items():
                                if data.get('notify_enabled', True):
                                    await bot.send_message(chat_id, f"🏁 Розыгрыш #{gw_id} завершён! Победители: {winners_list}")
                    except Exception as e:
                        logging.error(f"Error processing giveaway {gw['id']}: {e}", exc_info=True)
        except Exception as e:
            logging.error(f"Error in check_giveaways main loop: {e}", exc_info=True)
            await asyncio.sleep(60)

async def periodic_cleanup():
    while True:
        try:
            await asyncio.sleep(86400)
            from db import perform_cleanup
            await perform_cleanup(manual=False)
        except Exception as e:
            logging.error(f"Error in periodic_cleanup: {e}", exc_info=True)
            await asyncio.sleep(3600)

async def update_all_businesses_income():
    while True:
        await asyncio.sleep(3600)
        try:
            async with db_pool.acquire() as conn:
                businesses = await conn.fetch("""
                    SELECT ub.*, bt.base_income_cents 
                    FROM user_businesses ub
                    JOIN business_types bt ON ub.business_type_id = bt.id
                """)
                for biz in businesses:
                    try:
                        income_per_hour = biz['base_income_cents'] * biz['level']
                        new_accum = biz['accumulated'] + income_per_hour
                        await conn.execute(
                            "UPDATE user_businesses SET accumulated = $1 WHERE id = $2",
                            new_accum, biz['id']
                        )
                    except Exception as e:
                        logging.error(f"Error updating business {biz['id']}: {e}", exc_info=True)
                logging.info("Автоматическое начисление дохода по бизнесам выполнено.")
        except Exception as e:
            logging.error(f"Ошибка в update_all_businesses_income: {e}", exc_info=True)

async def start_background_tasks():
    tasks = [
        process_smuggle_runs(),
        check_auctions(),
        boss_spawn_scheduler(),
        ad_sender(),
        periodic_cleanup(),
        update_all_businesses_income(),
        check_giveaways(),
    ]
    await asyncio.gather(*tasks)
