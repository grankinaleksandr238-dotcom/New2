from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup,
    InlineKeyboardButton
)
from typing import List, Dict, Tuple

def back_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="◀️ Назад")]],
        resize_keyboard=True
    )

def cancel_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True
    )

def main_menu_keyboard(is_admin: bool = False):
    buttons = [
        [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="🎁 Бонус")],
        [KeyboardButton(text="🛒 Магазин подарков"), KeyboardButton(text="🎰 Казино")],
        [KeyboardButton(text="🎟 Промокод"), KeyboardButton(text="🏆 Топ игроков")],
        [KeyboardButton(text="💰 Мои покупки"), KeyboardButton(text="🔫 Ограбить")],
        [KeyboardButton(text="📋 Задания"), KeyboardButton(text="🔗 Рефералка")],
        [KeyboardButton(text="🎁 Розыгрыши"), KeyboardButton(text="📊 Уровень")],
        [KeyboardButton(text="🏷 Аукцион"), KeyboardButton(text="🏪 Мои бизнесы")],
        [KeyboardButton(text="💼 Биткоин-биржа")],
    ]
    if is_admin:
        buttons.append([KeyboardButton(text="⚙️ Админ панель")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def casino_menu_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🎰 Играть в казино"), KeyboardButton(text="🎲 Кости")],
        [KeyboardButton(text="🔢 Угадай число"), KeyboardButton(text="🍒 Слоты")],
        [KeyboardButton(text="🎡 Рулетка"), KeyboardButton(text="👥 Мультиплеер 21")],
        [KeyboardButton(text="◀️ Назад")]
    ], resize_keyboard=True)

def multiplayer_lobby_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="➕ Создать комнату")],
        [KeyboardButton(text="🔍 Найти комнату")],
        [KeyboardButton(text="📋 Список комнат")],
        [KeyboardButton(text="◀️ Назад")]
    ], resize_keyboard=True)

def room_control_keyboard(game_id: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Начать игру", callback_data=f"start_game_{game_id}")],
        [InlineKeyboardButton(text="❌ Закрыть комнату", callback_data=f"close_room_{game_id}")]
    ])

def room_action_keyboard(can_double: bool = True):
    buttons = [
        [InlineKeyboardButton(text="🎯 Ещё", callback_data="room_hit"),
         InlineKeyboardButton(text="🛑 Хватит", callback_data="room_stand")]
    ]
    second_row = []
    if can_double:
        second_row.append(InlineKeyboardButton(text="💰 Удвоить", callback_data="room_double"))
    second_row.append(InlineKeyboardButton(text="🏳️ Сдаться", callback_data="room_surrender"))
    buttons.append(second_row)
    buttons.append([InlineKeyboardButton(text="💬 Написать в чат", callback_data="room_chat")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def leave_room_keyboard(game_id: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚪 Выйти из комнаты", callback_data=f"leave_room_{game_id}")]
    ])

def theft_choice_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🎲 Случайная цель")],
        [KeyboardButton(text="👤 Выбрать пользователя")],
        [KeyboardButton(text="◀️ Назад")]
    ], resize_keyboard=True)

def bitcoin_exchange_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📈 Купить BTC"), KeyboardButton(text="📉 Продать BTC")],
        [KeyboardButton(text="📋 Мои заявки"), KeyboardButton(text="📊 Стакан заявок")],
        [KeyboardButton(text="◀️ Назад")]
    ], resize_keyboard=True)

def order_book_keyboard(book: Dict[str, List[Dict]]):
    kb = []
    if book['asks']:
        kb.append([InlineKeyboardButton(text="📉 Продажа (ASK) - лучшие цены", callback_data="noop")])
        for ask in book['asks'][:5]:
            kb.append([InlineKeyboardButton(
                text=f"💰 {ask['price']} $ | {ask['total_amount']:.4f} BTC ({ask['count']} заявок)",
                callback_data=f"buy_from_{ask['price']}"
            )])
    else:
        kb.append([InlineKeyboardButton(text="Нет активных продаж", callback_data="noop")])

    if book['bids']:
        kb.append([InlineKeyboardButton(text="📈 Покупка (BID) - лучшие цены", callback_data="noop")])
        for bid in book['bids'][:5]:
            kb.append([InlineKeyboardButton(
                text=f"💰 {bid['price']} $ | {bid['total_amount']:.4f} BTC ({bid['count']} заявок)",
                callback_data=f"sell_to_{bid['price']}"
            )])
    else:
        kb.append([InlineKeyboardButton(text="Нет активных покупок", callback_data="noop")])

    kb.append([InlineKeyboardButton(text="« Назад", callback_data="exchange_back")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def bitcoin_orders_keyboard(orders: List[dict], order_type: str, page: int = 1, total_pages: int = 1):
    kb = []
    for order in orders:
        kb.append([InlineKeyboardButton(
            text=f"{order['amount']:.4f} BTC @ {order['price']} $ (ID: {order['id']})",
            callback_data=f"{order_type}_order_{order['id']}"
        )])
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"{order_type}_page_{page-1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"{order_type}_page_{page+1}"))
    if nav:
        kb.append(nav)
    kb.append([InlineKeyboardButton("« Назад", callback_data="exchange_back")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def my_orders_keyboard(orders: List[dict], page: int = 1, total_pages: int = 1):
    kb = []
    for order in orders:
        order_type_emoji = "📈" if order['type'] == 'buy' else "📉"
        kb.append([InlineKeyboardButton(
            text=f"{order_type_emoji} {order['amount']:.4f} BTC @ {order['price']} $",
            callback_data=f"myorder_{order['id']}"
        )])
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"myorders_page_{page-1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"myorders_page_{page+1}"))
    if nav:
        kb.append(nav)
    kb.append([InlineKeyboardButton("« Назад", callback_data="exchange_back")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def business_main_keyboard(businesses: List[dict]):
    kb = []
    for biz in businesses:
        kb.append([InlineKeyboardButton(
            text=f"{biz['emoji']} {biz['name']} (ур. {biz['level']}) | Накоплено: {biz['accumulated']//100} баксов",
            callback_data=f"biz_view_{biz['id']}"
        )])
    kb.append([InlineKeyboardButton(text="🛒 Купить новый бизнес", callback_data="buy_business_menu")])
    kb.append([InlineKeyboardButton(text="◀️ Назад", callback_data="biz_back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def business_actions_keyboard(business_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Собрать доход", callback_data=f"biz_collect_{business_id}")],
        [InlineKeyboardButton(text="⬆️ Улучшить", callback_data=f"biz_upgrade_{business_id}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="biz_back")]
    ])

def business_buy_keyboard(business_types: List[dict]):
    kb = []
    for bt in business_types:
        kb.append([InlineKeyboardButton(
            text=f"{bt['emoji']} {bt['name']} – {bt['base_price_btc']} BTC",
            callback_data=f"buybiz_{bt['id']}"
        )])
    kb.append([InlineKeyboardButton(text="◀️ Отмена", callback_data="buy_biz_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def giveaways_user_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📋 Активные розыгрыши")],
        [KeyboardButton(text="🏁 Завершённые розыгрыши")],
        [KeyboardButton(text="◀️ Назад")]
    ], resize_keyboard=True)

def active_giveaways_keyboard(giveaways: List[dict], page: int, total_pages: int):
    kb = []
    for gw in giveaways:
        kb.append([InlineKeyboardButton(
            text=f"#{gw['id']} | {gw['prize']} | до {gw['end_date']}",
            callback_data=f"active_gw_{gw['id']}"
        )])
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"active_gw_page_{page-1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"active_gw_page_{page+1}"))
    if nav:
        kb.append(nav)
    kb.append([InlineKeyboardButton("« Назад", callback_data="active_gw_back")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def completed_giveaways_keyboard(giveaways: List[dict], page: int, total_pages: int):
    kb = []
    for gw in giveaways:
        display = f"#{gw['id']} | {gw['prize']} | {gw['winners_list'][:20]}" if gw['winners_list'] else f"#{gw['id']} | {gw['prize']}"
        kb.append([InlineKeyboardButton(text=display, callback_data=f"completed_gw_{gw['id']}")])
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"completed_gw_page_{page-1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"completed_gw_page_{page+1}"))
    if nav:
        kb.append(nav)
    kb.append([InlineKeyboardButton("« Назад", callback_data="completed_gw_back")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def giveaway_detail_keyboard(giveaway_id: int, is_participant: bool):
    kb = []
    if not is_participant:
        kb.append([InlineKeyboardButton("✅ Участвовать", callback_data=f"join_giveaway_{giveaway_id}")])
    else:
        kb.append([InlineKeyboardButton("❌ Отказаться", callback_data=f"leave_giveaway_{giveaway_id}")])
    kb.append([InlineKeyboardButton("« Назад", callback_data="active_gw_back")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def auction_list_keyboard(auctions: List[dict], page: int, total_pages: int):
    kb = []
    for a in auctions:
        kb.append([InlineKeyboardButton(
            text=f"{a['item_name']} | Текущая ставка: {a['current_price']}",
            callback_data=f"auction_view_{a['id']}"
        )])
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"auction_page_{page-1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"auction_page_{page+1}"))
    if nav:
        kb.append(nav)
    kb.append([InlineKeyboardButton("« Назад", callback_data="auction_list_back")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def auction_detail_keyboard(auction_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("💰 Сделать ставку", callback_data=f"auction_bid_{auction_id}")],
        [InlineKeyboardButton("« Назад", callback_data="auction_list")]
    ])

def confirm_chat_inline(chat_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm_chat_{chat_id}"),
         InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_chat_{chat_id}")]
    ])

def subscription_inline(not_subscribed: List[Tuple[str, str]]):
    kb = []
    for title, link in not_subscribed:
        if link:
            kb.append([InlineKeyboardButton(text=f"📢 {title}", url=link)])
        else:
            kb.append([InlineKeyboardButton(text=f"📢 {title}", callback_data="no_link")])
    kb.append([InlineKeyboardButton(text="✅ Я подписался", callback_data="check_sub")])
    return InlineKeyboardMarkup(row_width=1, inline_keyboard=kb)

def repeat_bet_keyboard(game: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔁 Повторить", callback_data=f"repeat_{game}")]
    ])
  def admin_main_keyboard(permissions: List[str]):
    all_buttons = [
        ("👥 Пользователи", "manage_users"),
        ("🛒 Магазин", "manage_shop"),
        ("🎁 Розыгрыши", "manage_giveaways"),
        ("👾 Боссы", "manage_bosses"),
        ("🏪 Бизнесы", "manage_businesses"),
        ("🏷 Аукцион", "manage_auctions"),
        ("📢 Каналы", "manage_channels"),
        ("🤖 Чаты", "manage_chats"),
        ("🎫 Промокоды", "manage_promocodes"),
        ("📢 Реклама", "manage_ads"),
        ("💼 Биржа", "manage_exchange"),
        ("🖼 Медиа", "manage_media"),
        ("🔨 Блокировки", "manage_bans"),
        ("➕ Админы", "manage_admins"),
        ("📊 Статистика", "view_stats"),
        ("📢 Рассылка", "broadcast"),
        ("🧹 Очистка", "cleanup"),
        ("⚙️ Настройки", "edit_settings"),
    ]

    available = [text for text, perm in all_buttons if perm in permissions]

    buttons = []
    row = []
    for i, text in enumerate(available):
        row.append(KeyboardButton(text))
        if len(row) == 2 or i == len(available) - 1:
            buttons.append(row)
            row = []

    buttons.append([KeyboardButton(text="◀️ Назад в главное меню")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def admin_users_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton("💰 Начислить баксы"), KeyboardButton("💸 Списать баксы")],
        [KeyboardButton("⭐️ Начислить репутацию"), KeyboardButton("🔻 Снять репутацию")],
        [KeyboardButton("📈 Начислить опыт"), KeyboardButton("🔝 Установить уровень")],
        [KeyboardButton("₿ Начислить биткоины"), KeyboardButton("₿ Списать биткоины")],
        [KeyboardButton("⚔️ Начислить авторитет"), KeyboardButton("⚔️ Списать авторитет")],
        [KeyboardButton("👥 Найти пользователя")],
        [KeyboardButton("📊 Экспорт пользователей")],
        [KeyboardButton("◀️ Назад в админку")]
    ], resize_keyboard=True)

def admin_shop_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton("➕ Добавить товар")],
        [KeyboardButton("➖ Удалить товар")],
        [KeyboardButton("✏️ Редактировать товар")],
        [KeyboardButton("📋 Список товаров")],
        [KeyboardButton("🛍️ Список покупок")],
        [KeyboardButton("◀️ Назад в админку")]
    ], resize_keyboard=True)

def admin_giveaway_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton("➕ Создать розыгрыш")],
        [KeyboardButton("📋 Активные розыгрыши")],
        [KeyboardButton("✅ Завершить розыгрыш")],
        [KeyboardButton("📋 Завершённые розыгрыши (админ)")],
        [KeyboardButton("◀️ Назад в админку")]
    ], resize_keyboard=True)

def admin_channel_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton("➕ Добавить канал")],
        [KeyboardButton("➖ Удалить канал")],
        [KeyboardButton("📋 Список каналов")],
        [KeyboardButton("◀️ Назад в админку")]
    ], resize_keyboard=True)

def admin_promo_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton("➕ Создать промокод")],
        [KeyboardButton("📋 Список промокодов")],
        [KeyboardButton("◀️ Назад в админку")]
    ], resize_keyboard=True)

def admin_tasks_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton("➕ Создать задание")],
        [KeyboardButton("📋 Список заданий")],
        [KeyboardButton("❌ Удалить задание")],
        [KeyboardButton("◀️ Назад в админку")]
    ], resize_keyboard=True)

def admin_ban_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton("🔨 Заблокировать пользователя")],
        [KeyboardButton("🔓 Разблокировать пользователя")],
        [KeyboardButton("📋 Список заблокированных")],
        [KeyboardButton("◀️ Назад в админку")]
    ], resize_keyboard=True)

def admin_admins_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton("➕ Добавить админа")],
        [KeyboardButton("✏️ Редактировать права админа")],
        [KeyboardButton("➖ Удалить админа")],
        [KeyboardButton("📋 Список админов")],
        [KeyboardButton("◀️ Назад в админку")]
    ], resize_keyboard=True)

def admin_chats_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton("📋 Список запросов на подтверждение")],
        [KeyboardButton("✅ Подтвердить чат")],
        [KeyboardButton("❌ Отклонить запрос")],
        [KeyboardButton("📋 Список подтверждённых чатов")],
        [KeyboardButton("🗑 Удалить чат из подтверждённых")],
        [KeyboardButton("◀️ Назад в админку")]
    ], resize_keyboard=True)

def admin_boss_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton("📋 Активные боссы")],
        [KeyboardButton("⚔️ Создать босса вручную")],
        [KeyboardButton("❌ Удалить босса (по ID)")],
        [KeyboardButton("◀️ Назад в админку")]
    ], resize_keyboard=True)

def admin_auction_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton("➕ Создать аукцион")],
        [KeyboardButton("📋 Активные аукционы")],
        [KeyboardButton("❌ Отменить аукцион")],
        [KeyboardButton("◀️ Назад в админку")]
    ], resize_keyboard=True)

def admin_ad_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton("➕ Создать рекламу")],
        [KeyboardButton("📋 Список рекламы")],
        [KeyboardButton("✏️ Редактировать рекламу")],
        [KeyboardButton("❌ Удалить рекламу")],
        [KeyboardButton("◀️ Назад в админку")]
    ], resize_keyboard=True)

def admin_exchange_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton("📋 Активные заявки")],
        [KeyboardButton("❌ Удалить заявку (по ID)")],
        [KeyboardButton("📊 История сделок")],
        [KeyboardButton("◀️ Назад в админку")]
    ], resize_keyboard=True)

def admin_business_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton("📋 Список бизнесов")],
        [KeyboardButton("➕ Добавить бизнес")],
        [KeyboardButton("✏️ Редактировать бизнес")],
        [KeyboardButton("🔄 Переключить доступность")],
        [KeyboardButton("◀️ Назад в админку")]
    ], resize_keyboard=True)

def admin_media_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton("➕ Добавить медиа")],
        [KeyboardButton("➖ Удалить медиа")],
        [KeyboardButton("📋 Список медиа")],
        [KeyboardButton("◀️ Назад в админку")]
    ], resize_keyboard=True)

def admin_helper_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton("📋 Активные помощники")],
        [KeyboardButton("📊 Топы чатов")],
        [KeyboardButton("◀️ Назад в админку")]
    ], resize_keyboard=True)

def settings_categories_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton("⚙️ Кража")],
        [KeyboardButton("⚙️ Казино и игры")],
        [KeyboardButton("⚙️ Ограничения по уровню")],
        [KeyboardButton("⚙️ Уведомления")],
        [KeyboardButton("⚙️ Подгон")],
        [KeyboardButton("⚙️ Рефералы")],
        [KeyboardButton("⚙️ Опыт и уровни")],
        [KeyboardButton("⚙️ Репутация")],
        [KeyboardButton("⚙️ Боссы")],
        [KeyboardButton("⚙️ Статы за уровень")],
        [KeyboardButton("⚙️ Аукцион")],
        [KeyboardButton("⚙️ Бой в чатах")],
        [KeyboardButton("⚙️ Качалка (авторитет)")],
        [KeyboardButton("⚙️ Бизнесы")],
        [KeyboardButton("⚙️ Контрабанда")],
        [KeyboardButton("⚙️ Биткоины")],
        [KeyboardButton("⚙️ Биткоин-биржа")],
        [KeyboardButton("⚙️ Очистка логов")],
        [KeyboardButton("⚙️ Автоудаление")],
        [KeyboardButton("⚙️ Стартовый бонус")],
        [KeyboardButton("⚙️ Глобальный кулдаун")],
        [KeyboardButton("⚙️ Лимиты ввода")],
        [KeyboardButton("◀️ Назад в админку")]
    ], resize_keyboard=True)

def settings_param_keyboard(params: List[Tuple[str, str]], category: str):
    kb = []
    for key, desc in params:
        kb.append([InlineKeyboardButton(text=desc, callback_data=f"edit_{key}")])
    kb.append([InlineKeyboardButton(text="◀️ Назад", callback_data=f"settings_back_{category}")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def purchase_action_keyboard(purchase_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Выполнено", callback_data=f"purchase_done_{purchase_id}"),
         InlineKeyboardButton(text="❌ Отказ", callback_data=f"purchase_reject_{purchase_id}")]
    ])

def chat_top_navigation(order: str, page: int, has_prev: bool, has_next: bool):
    kb = []
    row = []
    if has_prev:
        row.append(InlineKeyboardButton("⬅️", callback_data=f"chat_top_page_{order}_{page-1}"))
    row.append(InlineKeyboardButton(f"{page}", callback_data="noop"))
    if has_next:
        row.append(InlineKeyboardButton("➡️", callback_data=f"chat_top_page_{order}_{page+1}"))
    kb.append(row)
    kb.append([
        InlineKeyboardButton("📊 По авторитету", callback_data="chat_top_authority_1"),
        InlineKeyboardButton("💥 По урону", callback_data="chat_top_damage_1"),
        InlineKeyboardButton("⚔️ По боям", callback_data="chat_top_fights_1")
    ])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def cancel_inline():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_action")]
    ])
