from flask import Flask, render_template, jsonify, request, redirect, url_for, flash
import os
from dotenv import load_dotenv
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from database import (
    get_all_history, get_latest_draw, get_config, update_config, 
    save_draw_result, get_unpushed_tickets, mark_ticket_checked, 
    get_prediction, draw_history, bot_users, played_tickets, save_played_ticket,
    get_target_draw_id, save_prediction
)
from analytics import calculate_stats, get_complex_stats, get_ai_lucky_numbers
from apscheduler.schedulers.background import BackgroundScheduler
import requests
from bs4 import BeautifulSoup
from datetime import datetime, time as dtime
import time
import re
import pytz
import threading

vn_tz = pytz.timezone('Asia/Ho_Chi_Minh')

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
    now_vn = datetime.now(vn_tz)
    today_str = now_vn.strftime("%d/%m/%Y")
    print(f"[{now_vn}] Running draw check & ticket verification for {today_str}...")
    
    # 1. Kiểm tra xem DB đã có kết quả hôm nay chưa
    latest_45 = get_latest_draw("6/45")
    latest_55 = get_latest_draw("6/55")
    
    # Xác định loại vé quay thưởng hôm nay
    day = now_vn.weekday()
    target_game = "6/45" if day in [0, 2, 4, 6] else "6/55"
    latest_target = latest_45 if target_game == "6/45" else latest_55
    
    if latest_target and latest_target.get('draw_date') == today_str:
        print(f"✅ Đã có kết quả {target_game} cho ngày {today_str} trong Database. Tiến hành dò luôn.")
    else:
        print(f"🔍 Chưa có kết quả {target_game} cho {today_str}. Đang đi cào dữ liệu mới...")
        scrape_vietlott()
        # Refresh data sau khi cào
        latest_45 = get_latest_draw("6/45")
        latest_55 = get_latest_draw("6/55")
    
    # 2. Check unpushed tickets
    unpushed = get_unpushed_tickets()
    if not unpushed:
        print("No unpushed tickets to check.")
        return

    # Cache kết quả mới nhất
    latest_draws = {
        "6/45": latest_45,
        "6/55": latest_55
    }

    for ticket in unpushed:
        latest = latest_draws.get(ticket['game_type'])
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
    
    # Send a small summary via Telegram if something was checked
    admin_user = bot_users.find_one({"username": "phongzann"})
    if admin_user:
        summary = f"🔄 <b>[DÒ SỐ] KẾT QUẢ CHI TIẾT KỲ NÀY</b>\n\n"
        
        # Group unpushed by game_type to show the result numbers once
        processed_tickets = []
        for t in unpushed:
            latest = latest_draws.get(t['game_type'])
            if not latest: continue
            
            matched = set(t['numbers']) & set(latest['numbers'])
            match_count = len(matched)
            
            status_icon = "✅" if t.get('is_win') else "❌"
            match_text = f"{status_icon} <b>{t['game_type']}</b>: {', '.join(map(str, t['numbers']))} "
            match_text += f"(Trúng {match_count} số"
            
            if t['game_type'] == "6/55" and latest.get('special_number'):
                if latest['special_number'] in t['numbers']:
                    match_text += " + Bonus"
            
            match_text += ")"
            if t.get('is_win'):
                match_text += f" -> <b>TRÚNG {t['win_type']}!</b>"
            
            processed_tickets.append(match_text)

        summary += "\n".join(processed_tickets)
        summary += f"\n\n✨ Tổng cộng: {len(unpushed)} vé. "
        
        if any(t.get('is_win') for t in unpushed):
            summary += "\n🎊 Chúc mừng Đại ca đã có vé trúng thưởng!"
        else:
            summary += "\n💪 Rất tiếc kỳ này chưa trúng, chúc Đại ca may mắn kỳ sau nha!"
            
        send_bot_alert(admin_user['chat_id'], summary)

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
    print(f"[{datetime.now(vn_tz)}] 🤖 Bắt đầu Job mua vé tự động...")
    config = get_config()
    limit = config.get('daily_limit', 5)
    buy_count = config.get('auto_buy_count', 3) # Số bộ số cần mua
    
    user = bot_users.find_one({"username": "phongzann"})
    if not user:
        user = bot_users.find_one()
    
    if not user:
        print("❌ Không tìm thấy user nào để mua vé.")
        return False
        
    chat_id = user['chat_id']
    username = user.get('username') or user.get('first_name', 'Đại ca')
    
    # Xác định loại vé theo ngày (VN time)
    now_vn = datetime.now(vn_tz)
    day = now_vn.weekday()
    if day in [0, 2, 4, 6]: # Thứ 2, 4, 6, CN là 6/45
        game_type = "6/45"
    else: # Thứ 3, 5, 7 là 6/55
        game_type = "6/55"
    
    target_draw_id = get_target_draw_id(game_type)

    # Kiểm tra xem hôm nay ĐÃ MUA TỰ ĐỘNG chưa
    today_start = datetime.combine(now_vn.date(), dtime.min).replace(tzinfo=vn_tz)
    auto_exists = played_tickets.find_one({
        "chat_id": chat_id,
        "played_at": {"$gte": today_start},
        "is_auto": True
    })
    
    if auto_exists:
        print(f"⚠️ Hôm nay hệ thống đã tự động mua vé cho {username} rồi.")
        return "ALREADY_BOUGHT"

    # Kiểm tra giới hạn tổng số vé
    played_today = played_tickets.count_documents({
        "chat_id": chat_id,
        "played_at": {"$gte": today_start}
    })
    
    if played_today >= limit:
        print(f"⚠️ Đại ca {username} đã đạt giới hạn {limit} vé hôm nay.")
        return "LIMIT_REACHED"

    # Thực hiện mua n bộ số
    actual_buy = min(buy_count, limit - played_today)
    if actual_buy <= 0:
        return "LIMIT_REACHED"

    bought_sets = []
    try:
        for _ in range(actual_buy):
            nums = get_ai_lucky_numbers(game_type, "balanced")
            save_played_ticket(chat_id, game_type, nums, draw_id=target_draw_id, is_auto=True)
            bought_sets.append(nums)
        
        # Gửi thông báo tổng hợp qua Telegram
        alert_msg = f"🤖 <b>[AUTO] HỆ THỐNG ĐÃ MUA VÉ CHO ĐẠI CA!</b>\n\n"
        alert_msg += f"🎰 Loại vé: <b>{game_type}</b>\n"
        alert_msg += f"📅 Ngày mua: {now_vn.strftime('%d/%m/%Y')}\n"
        alert_msg += f"🎫 Số lượng: <b>{actual_buy} bộ số</b>\n\n"
        
        for idx, nums in enumerate(bought_sets, 1):
            alert_msg += f"{idx}. <b>{', '.join(map(str, nums))}</b>\n"
            
        alert_msg += f"\n✨ Chúc Đại ca may mắn! Em sẽ dò kết quả lúc 19h nha."
        
        send_bot_alert(chat_id, alert_msg)
        print(f"✅ Đã mua {actual_buy} vé tự động cho {username}")
        return True
    except Exception as e:
        print(f"❌ Lỗi khi mua vé tự động: {e}")
        return False

# Scheduler
scheduler = BackgroundScheduler(timezone=vn_tz)
# Job dò kết quả lúc 18h45 (Uu tiên DB, nếu chưa có thì cào)
scheduler.add_job(func=check_results_job, trigger="cron", hour=18, minute=45)
# Job tự động mua vé lúc 8h30 sáng mỗi ngày
scheduler.add_job(func=auto_buy_job, trigger="cron", hour=8, minute=30)
# Job ping self mỗi 10 phút để đỡ sleep
scheduler.add_job(func=ping_self_job, trigger="interval", minutes=10)
scheduler.start()

@app.route('/')
@login_required
def index():
    now_vn = datetime.now(vn_tz)
    day = now_vn.weekday() # 0=Mon, 6=Sun
    
    # User's rule: 2 4 6 CN (0 2 4 6) -> 6/45, 3 5 7 (1 3 5) -> 6/55
    show_45 = day in [0, 2, 4, 6]
    show_55 = day in [1, 3, 5]

    latest_55 = get_latest_draw("6/55")
    latest_45 = get_latest_draw("6/45")
    stats_55 = calculate_stats("6/55")
    stats_45 = calculate_stats("6/45")
    config = get_config()
    
    # Pagination for tickets
    page = request.args.get('page', 1, type=int)
    per_page = 10
    total_tickets = played_tickets.count_documents({})
    total_pages = (total_tickets + per_page - 1) // per_page
    if total_pages == 0: total_pages = 1
    
    recent_tickets = list(played_tickets.find().sort("played_at", -1).skip((page - 1) * per_page).limit(per_page))
    
    return render_template('index.html', 
                          latest_55=latest_55, 
                          latest_45=latest_45,
                          stats_55=stats_55,
                          stats_45=stats_45,
                          config=config,
                          tickets=recent_tickets,
                          show_45=show_45,
                          show_55=show_55,
                          page=page,
                          total_pages=total_pages)

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
    auto_count = request.form.get('auto_buy_count', type=int)
    if auto_count is not None:
        update_config(auto_buy_count=auto_count)
        flash('Cấu hình đã được cập nhật, Đại ca!', 'success')
    return redirect(url_for('index'))

@app.route('/manual_check')
@login_required
def manual_check():
    """Trigger dò số thủ công ngay lập tức (Chạy ngầm)"""
    threading.Thread(target=check_results_job).start()
    flash('Em đang dò số trong nền đây ạ, Đại ca đợi tin nhắn Telegram gửi về nhé (khoảng 5-10 giây)!', 'success')
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
        pred_nums = get_ai_lucky_numbers("6/55", "balanced")
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
