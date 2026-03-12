from flask import Flask, render_template, jsonify, request, redirect, url_for, flash
import os
from dotenv import load_dotenv
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from database import (
    get_all_history, get_latest_draw, get_config, update_config, 
    save_draw_result, get_unpushed_tickets, mark_ticket_checked, 
    get_prediction, draw_history, bot_users, played_tickets, save_played_ticket
)
from analytics import calculate_stats, get_complex_stats, get_ai_lucky_numbers
from apscheduler.schedulers.background import BackgroundScheduler
import requests
from bs4 import BeautifulSoup
from datetime import datetime, time as dtime
import time
import re

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "vietlot_pro_secret_key_2024")

# Login Setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, id):
        self.id = id

@login_manager.user_loader
def load_user(user_id):
    if user_id == "phongzann":
        return User(user_id)
    return None

from crawler import scrape_vietlott

def send_bot_alert(chat_id, message):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Failed to send bot alert: {e}")

def check_results_job():
    print(f"[{datetime.now()}] Running draw check & ticket verification...")
    # 1. Scrape real data
    new_results = scrape_vietlott()
    
    # 2. Check unpushed tickets
    unpushed = get_unpushed_tickets()
    for ticket in unpushed:
        latest = get_latest_draw(ticket['game_type'])
        if latest:
            # Check if ticket numbers match latest draw
            matched = set(ticket['numbers']) & set(latest['numbers'])
            win_count = len(matched)
            is_win = False
            win_type = None
            prize = 0
            
            if ticket['game_type'] == "6/45":
                if win_count == 3:
                    is_win, win_type, prize = True, "Giải Ba", 30000
                elif win_count == 4:
                    is_win, win_type, prize = True, "Giải Nhì", 300000
                elif win_count == 5:
                    is_win, win_type, prize = True, "Giải Nhất", 10000000
                elif win_count == 6:
                    is_win, win_type, prize = True, "JACKPOT", "JACKPOT 💰"
            
            elif ticket['game_type'] == "6/55":
                special_match = latest.get('special_number') in ticket['numbers']
                if win_count == 3:
                    is_win, win_type, prize = True, "Giải Ba", 50000
                elif win_count == 4:
                    is_win, win_type, prize = True, "Giải Nhì", 500000
                elif win_count == 5:
                    if special_match:
                        is_win, win_type, prize = True, "JACKPOT 2", "JACKPOT 2 💎"
                    else:
                        is_win, win_type, prize = True, "Giải Nhất", 40000000
                elif win_count == 6:
                    is_win, win_type, prize = True, "JACKPOT 1", "JACKPOT 1 👑"

            if is_win:
                mark_ticket_checked(ticket['_id'], True, win_type, prize)
                # Send Alert
                alert_msg = f"🎊 <b>ĐẠI CA TRÚNG GIẢI RỒI!!!</b> 🎊\n\n"
                alert_msg += f"🎰 Loại vé: {ticket['game_type']}\n"
                alert_msg += f"🏆 Giải: <b>{win_type}</b>\n"
                alert_msg += f"💰 Tiền thưởng: <b>{f'{prize:,}' if isinstance(prize, int) else prize}đ</b>\n"
                alert_msg += f"🔢 Bộ số của Đại ca: {', '.join(map(str, ticket['numbers']))}\n"
                alert_msg += f"✨ Kết quả kỳ này: {', '.join(map(str, latest['numbers']))}"
                if latest.get('special_number'):
                    alert_msg += f" (Bonus: {latest['special_number']})"
                
                send_bot_alert(ticket['chat_id'], alert_msg)
                print(f"Ticket {ticket['_id']} is a WINNER! Message sent.")
            else:
                mark_ticket_checked(ticket['_id'], False)

def ping_self_job():
    """Ping trang web để tránh bị Koyeb cho sleep"""
    url = "https://indirect-kesley-phongzann-35e454f0.koyeb.app"
    try:
        # Thêm User-Agent để giống trình duyệt
        headers = {'User-Agent': 'VietlottPro/1.0 (Keep-Alive)'}
        r = requests.get(url, headers=headers, timeout=15)
        print(f"[{datetime.now()}] 🛠 Ping Self ({url}): {r.status_code}")
    except Exception as e:
        print(f"[{datetime.now()}] ❌ Ping Self Failed: {e}")

def auto_buy_job():
    """Tự động chọn và lưu vé cho Đại ca mỗi ngày"""
    print(f"[{datetime.now()}] 🤖 Bắt đầu Job mua vé tự động...")
    config = get_config()
    limit = config.get('daily_limit', 5)
    
    # Tìm Đại ca phongzann hoặc user đầu tiên
    user = bot_users.find_one({"username": "phongzann"})
    if not user:
        user = bot_users.find_one() # Lấy đại 1 user nếu ko thấy phongzann
    
    if not user:
        print("❌ Không tìm thấy user nào để mua vé.")
        return
        
    chat_id = user['chat_id']
    
    # Xác định loại vé theo ngày (giống bot.py)
    day = datetime.now().weekday()
    if day in [0, 2, 4, 6]: # Thứ 2, 4, 6, CN là 6/45 (Mega)
        game_type = "6/45"
    else: # Thứ 3, 5, 7 là 6/55 (Power)
        game_type = "6/55"

    # Kiểm tra xem hôm nay đã chơi bao nhiêu vé rồi
    today_start = datetime.combine(datetime.now().date(), dtime.min)
    played_today = played_tickets.count_documents({
        "chat_id": chat_id,
        "played_at": {"$gte": today_start}
    })
    
    if played_today >= limit:
        print(f"⚠️ Đại ca {user.get('username')} đã đạt giới hạn {limit} vé hôm nay.")
        return

    # Lấy số may mắn từ AI
    nums = get_ai_lucky_numbers(game_type, "balanced")
    save_played_ticket(chat_id, game_type, nums)
    
    # Gửi thông báo qua Telegram
    alert_msg = f"🤖 <b>[AUTO] HỆ THỐNG ĐÃ MUA VÉ CHO ĐẠI CA!</b>\n\n"
    alert_msg += f"🎰 Loại vé: {game_type}\n"
    alert_msg += f"🔢 Bộ số may mắn: <b>{', '.join(map(str, nums))}</b>\n"
    alert_msg += f"✨ Chúc Đại ca may mắn! Em sẽ dò kết quả lúc 19h nha."
    
    send_bot_alert(chat_id, alert_msg)
    print(f"✅ Đã mua vé tự động cho {user.get('username')}: {nums}")

# Scheduler
scheduler = BackgroundScheduler()
# Job dò kết quả lúc 19h
scheduler.add_job(func=check_results_job, trigger="cron", hour=19, minute=5)
# Job tự động mua vé lúc 9h sáng mỗi ngày
scheduler.add_job(func=auto_buy_job, trigger="cron", hour=9, minute=0)
# Job ping self mỗi 10 phút để đỡ sleep
scheduler.add_job(func=ping_self_job, trigger="interval", minutes=10)
scheduler.start()

@app.route('/')
@login_required
def index():
    latest_55 = get_latest_draw("6/55")
    latest_45 = get_latest_draw("6/45")
    stats_55 = calculate_stats("6/55")
    stats_45 = calculate_stats("6/45")
    config = get_config()
    from database import played_tickets
    recent_tickets = list(played_tickets.find().sort("played_at", -1).limit(10))
    
    return render_template('index.html', 
                          latest_55=latest_55, 
                          latest_45=latest_45,
                          stats_55=stats_55,
                          stats_45=stats_45,
                          config=config,
                          tickets=recent_tickets)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        # Simple hardcoded check as requested (only you can enter)
        if username == "phongzann" and password == "Password@2208":
            user = User(username)
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Login failed. Only "phongzann" can enter!', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/settings', methods=['POST'])
@login_required
def settings():
    limit = request.form.get('daily_limit', type=int)
    if limit:
        update_config(limit)
        flash('Cấu hình đã được cập nhật, Đại ca!', 'success')
    return redirect(url_for('index'))

@app.route('/manual_buy')
@login_required
def manual_buy():
    """Trigger mua vé thủ công ngay lập tức"""
    # CHạy job mua vé ngay
    auto_buy_job()
    flash('Em đã mua vé may mắn cho Đại ca rồi nhé! Check Telegram nha.', 'success')
    return redirect(url_for('index'))

@app.route('/api/history/<game_type>')
@login_required
def api_history(game_type):
    formatted_type = game_type.replace('-', '/')
    history = get_all_history(formatted_type)
    for h in history:
        h['_id'] = str(h['_id'])
    return jsonify(history)

@app.route('/stats')
@login_required
def stats_page():
    # 6/55
    latest_55 = get_latest_draw("6/55")
    next_id_55 = (latest_55['draw_id'] + 1) if latest_55 else 1
    complex_55 = get_complex_stats("6/55")
    prediction_55 = get_prediction("6/55", next_id_55)
    if not prediction_55:
        # Generate and save new prediction if not exists
        from analytics import get_ai_lucky_numbers
        pred_nums = get_ai_lucky_numbers("6/55", "balanced")
        from database import save_prediction
        save_prediction("6/55", next_id_55, pred_nums)
        prediction_55 = {"numbers": pred_nums, "draw_id": next_id_55}

    # 6/45
    latest_45 = get_latest_draw("6/45")
    next_id_45 = (latest_45['draw_id'] + 1) if latest_45 else 1
    complex_45 = get_complex_stats("6/45")
    prediction_45 = get_prediction("6/45", next_id_45)
    if not prediction_45:
        pred_nums = get_ai_lucky_numbers("6/45", "balanced")
        save_prediction("6/45", next_id_45, pred_nums)
        prediction_45 = {"numbers": pred_nums, "draw_id": next_id_45}

    from analytics import calculate_stats
    simple_55 = calculate_stats("6/55")
    simple_45 = calculate_stats("6/45")

    return render_template('stats.html',
                          complex_55=complex_55,
                          complex_45=complex_45,
                          prediction_55=prediction_55,
                          prediction_45=prediction_45,
                          simple_55=simple_55,
                          simple_45=simple_45,
                          next_id_55=next_id_55,
                          next_id_45=next_id_45)

if __name__ == '__main__':
    # Koyeb cung cấp biến PORT tự động, mình nên dùng nó để linh hoạt
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
