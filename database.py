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
        config = {"type": "admin_config", "daily_limit": 5, "admin_username": "phongzann"}
        system_config.insert_one(config)
    return config

def update_config(daily_limit):
    system_config.update_one({"type": "admin_config"}, {"$set": {"daily_limit": daily_limit}}, upsert=True)

def save_played_ticket(chat_id, game_type, numbers):
    played_tickets.insert_one({
        "chat_id": chat_id,
        "game_type": game_type,
        "numbers": sorted([int(n) for n in numbers]),
        "played_at": datetime.now(),
        "checked": False,
        "is_win": False
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
