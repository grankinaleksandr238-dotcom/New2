from aiogram.dispatcher.filters.state import State, StatesGroup

class CreateGiveaway(StatesGroup):
    prize = State()
    description = State()
    end_date = State()
    media = State()

class AddChannel(StatesGroup):
    chat_id = State()
    title = State()
    invite_link = State()

class RemoveChannel(StatesGroup):
    chat_id = State()

class AddShopItem(StatesGroup):
    name = State()
    description = State()
    price = State()
    stock = State()
    photo = State()

class RemoveShopItem(StatesGroup):
    item_id = State()

class EditShopItem(StatesGroup):
    item_id = State()
    field = State()
    value = State()

class CreatePromocode(StatesGroup):
    code = State()
    reward = State()
    max_uses = State()

class Broadcast(StatesGroup):
    media = State()

class AddBalance(StatesGroup):
    user_id = State()
    amount = State()

class RemoveBalance(StatesGroup):
    user_id = State()
    amount = State()

class AddReputation(StatesGroup):
    user_id = State()
    amount = State()

class RemoveReputation(StatesGroup):
    user_id = State()
    amount = State()

class AddExp(StatesGroup):
    user_id = State()
    amount = State()

class SetLevel(StatesGroup):
    user_id = State()
    level = State()

class AddBitcoin(StatesGroup):
    user_id = State()
    amount = State()

class RemoveBitcoin(StatesGroup):
    user_id = State()
    amount = State()

class AddAuthority(StatesGroup):
    user_id = State()
    amount = State()

class RemoveAuthority(StatesGroup):
    user_id = State()
    amount = State()

class CasinoBet(StatesGroup):
    amount = State()

class DiceBet(StatesGroup):
    amount = State()

class GuessBet(StatesGroup):
    amount = State()
    number = State()

class SlotsBet(StatesGroup):
    amount = State()

class RouletteBet(StatesGroup):
    amount = State()
    bet_type = State()
    number = State()

class PromoActivate(StatesGroup):
    code = State()

class TheftTarget(StatesGroup):
    target = State()

class FindUser(StatesGroup):
    query = State()

class AddJuniorAdmin(StatesGroup):
    user_id = State()
    permissions = State()

class EditAdminPermissions(StatesGroup):
    user_id = State()
    selecting_permissions = State()
    confirm = State()

class RemoveJuniorAdmin(StatesGroup):
    user_id = State()

class CompleteGiveaway(StatesGroup):
    giveaway_id = State()
    winners_count = State()

class BlockUser(StatesGroup):
    user_id = State()
    reason = State()

class UnblockUser(StatesGroup):
    user_id = State()

class EditSettings(StatesGroup):
    key = State()
    value = State()

class CreateTask(StatesGroup):
    name = State()
    description = State()
    task_type = State()
    target_id = State()
    reward_coins = State()
    reward_reputation = State()
    required_days = State()
    penalty_days = State()
    max_completions = State()

class DeleteTask(StatesGroup):
    task_id = State()

class MultiplayerGame(StatesGroup):
    create_max_players = State()
    create_bet = State()
    join_code = State()

class RoomChat(StatesGroup):
    message = State()

class ManageChats(StatesGroup):
    action = State()
    chat_id = State()

class BossSpawn(StatesGroup):
    chat_id = State()
    level = State()
    image = State()

class DeleteBoss(StatesGroup):
    boss_id = State()
    confirm = State()

class CreateAuction(StatesGroup):
    item_name = State()
    description = State()
    start_price = State()
    end_time = State()
    target_price = State()
    photo = State()

class AuctionBid(StatesGroup):
    auction_id = State()
    amount = State()

class CancelAuction(StatesGroup):
    auction_id = State()

class CreateAd(StatesGroup):
    text = State()
    interval = State()
    target = State()

class EditAd(StatesGroup):
    ad_id = State()
    field = State()
    value = State()

class SellBitcoin(StatesGroup):
    amount = State()
    price = State()

class BuyBitcoin(StatesGroup):
    amount = State()
    price = State()

class CancelBitcoinOrder(StatesGroup):
    order_id = State()

class AddBusiness(StatesGroup):
    name = State()
    emoji = State()
    price = State()
    income = State()
    description = State()
    max_level = State()

class EditBusiness(StatesGroup):
    business_id = State()
    field = State()
    value = State()

class ToggleBusiness(StatesGroup):
    business_id = State()
    confirm = State()

class BuyBusiness(StatesGroup):
    business_type_id = State()
    confirming = State()

class UpgradeBusiness(StatesGroup):
    business_id = State()
    confirming = State()

class AddMedia(StatesGroup):
    key = State()
    file = State()

class RemoveMedia(StatesGroup):
    key = State()

class DeleteAd(StatesGroup):
    ad_id = State()

class BuyFromPrice(StatesGroup):
    price = State()
    orders = State()
    total_available = State()
    amount = State()

class SellToPrice(StatesGroup):
    price = State()
    orders = State()
    total_available = State()
    amount = State()
