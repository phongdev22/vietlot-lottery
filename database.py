import os
import certifi
from datetime import datetime
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")

if not MONGO_URI:
    print("❌ ERROR: MONGO_URI is not set!")
    exit(1)

# Cấu hình kết nối MongoDB cho Koyeb/Atlas (Dùng settings tương thích cao)
try:
    # Thử kết nối với bộ tham số "vượt mọi rào cản"
    client = MongoClient(
        MONGO_URI,
        tls=True,
        tlsAllowInvalidCertificates=True,
        serverSelectionTimeoutMS=10000,
        connectTimeoutMS=10000,
        # Đôi khi SNI gặp vấn đề, mình thử cấu hình cơ bản nhất
        retryWrites=False
    )
    # Kiểm tra kêt nối ngay lập tức
    client.admin.command('ping')
    print("✅ Kết nối MongoDB Atlas thành công!")
except Exception as e:
    print(f"⚠️ Vẫn lỗi SSL/Handshake: {e}")
    print("👉 ĐẠI CA KIỂM TRA GIÚP EM: Trên MongoDB Atlas, đã add IP 0.0.0.0/0 (bật Access từ mọi nơi) chưa ạ?")
    client = MongoClient(MONGO_URI)

db = client['lottery_db']

# Collections
draw_history = db['draw_history']
user_selections = db['user_selections']
bot_users = db['bot_users']
played_tickets = db['played_tickets']
system_config = db['system_config']
ai_predictions = db['ai_predictions']

def get_config():
    config = system_config.find_one({"type": "admin_config"})
    if not config:
        config = {
            "type": "admin_config", 
            "daily_limit": 5, 
            "auto_buy_count": 3,  # Số vé tự động mua mỗi sáng
            "admin_username": "phongzann"
        }
        system_config.insert_one(config)
    
    # Đảm bảo có auto_buy_count nếu config cũ chưa có
    if 'auto_buy_count' not in config:
        config['auto_buy_count'] = 3
        system_config.update_one({"type": "admin_config"}, {"$set": {"auto_buy_count": 3}})
        
    return config

def update_config(daily_limit=None, auto_buy_count=None):
    update_data = {}
    if daily_limit is not None:
        update_data["daily_limit"] = daily_limit
    if auto_buy_count is not None:
        update_data["auto_buy_count"] = auto_buy_count
        
    if update_data:
        system_config.update_one({"type": "admin_config"}, {"$set": update_data}, upsert=True)

def save_played_ticket(chat_id, game_type, numbers, draw_id=None, is_auto=False):
    import pytz
    vn_tz = pytz.timezone('Asia/Ho_Chi_Minh')
    now_vn = datetime.now(vn_tz)
    
    played_tickets.insert_one({
        "chat_id": chat_id,
        "game_type": game_type,
        "draw_id": draw_id,
        "numbers": sorted([int(n) for n in numbers]),
        "played_at": datetime.now(),
        "buy_date_vn": now_vn.strftime("%Y-%m-%d"),
        "checked": False,
        "is_win": False,
        "is_auto": is_auto
    })

def get_unpushed_tickets():
    return list(played_tickets.find({"checked": False}))

def mark_ticket_checked(ticket_id, is_win, win_type=None, prize_amount=None):
    played_tickets.update_one({"_id": ticket_id}, {"$set": {
        "checked": True, 
        "is_win": is_win,
        "win_type": win_type,
        "prize_amount": prize_amount
    }})

def save_draw_result(game_type, draw_id, numbers, draw_date, special_number=None):
    """Save a draw result if it doesn't exist."""
    draw_history.update_one(
        {"game_type": game_type, "draw_id": draw_id},
        {"$set": {
            "game_type": game_type,
            "draw_id": draw_id,
            "numbers": sorted([int(n) for n in numbers]),
            "special_number": int(special_number) if special_number else None,
            "draw_date": draw_date
        }},
        upsert=True
    )

def get_latest_draw(game_type):
    return draw_history.find_one({"game_type": game_type}, sort=[("draw_id", -1)])

def get_all_history(game_type, limit=100):
    return list(draw_history.find({"game_type": game_type}).sort("draw_id", -1).limit(limit))

def register_user(chat_id, username, first_name):
    bot_users.update_one(
        {"chat_id": chat_id},
        {"$set": {
            "username": username,
            "first_name": first_name,
            "last_active": datetime.now()
        }},
        upsert=True
    )

def save_prediction(game_type, draw_id, numbers):
    ai_predictions.update_one(
        {"game_type": game_type, "draw_id": draw_id},
        {"$set": {
            "game_type": game_type,
            "draw_id": draw_id,
            "numbers": sorted([int(n) for n in numbers]),
            "generated_at": datetime.now()
        }},
        upsert=True
    )

def get_prediction(game_type, draw_id):
    return ai_predictions.find_one({"game_type": game_type, "draw_id": draw_id})

def get_target_draw_id(game_type):
    from datetime import datetime
    import pytz
    vn_tz = pytz.timezone('Asia/Ho_Chi_Minh')
    
    latest = get_latest_draw(game_type)
    if not latest:
        return 1
    
    now_vn = datetime.now(vn_tz)
    today_str = now_vn.strftime("%d/%m/%Y")
    
    # Nếu trong DB đã có kết quả ngày hôm nay, thì chắc chắn là kỳ tiếp theo (+1)
    if latest.get('draw_date') == today_str:
        return latest['draw_id'] + 1
        
    # Xác định xem hôm nay có phải ngày quay của game này không (theo rule của Đại ca)
    day = now_vn.weekday()
    is_draw_day = False
    if game_type == "6/45" and day in [0, 2, 4, 6]:
        is_draw_day = True
    elif game_type == "6/55" and day in [1, 3, 5]:
        is_draw_day = True

    # Nếu đúng ngày quay và đã sau 18h (đang/đã quay), thì ghi cho kỳ tiếp theo nữa
    if is_draw_day and now_vn.hour >= 18:
        return latest['draw_id'] + 2
        
    # Các trường hợp còn lại là kỳ kế tiếp
    return latest['draw_id'] + 1
