import os
import logging
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from analytics import get_ai_lucky_numbers, calculate_stats

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")

import pytz
vn_tz = pytz.timezone('Asia/Ho_Chi_Minh')

if not TOKEN or not MONGO_URI:
    print("❌ ERROR: TELEGRAM_BOT_TOKEN or MONGO_URI is not set!")
    print("Nếu Đại ca đang chạy trên Koyeb, hãy vào Setting -> Environment Variables để thêm nhé!")
    exit(1)

print(f"Bot starting with token: {TOKEN[:10]}...")

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    # Register user to database
    register_user(chat_id, user.username, user.first_name)
    
    keyboard = [
        [
            InlineKeyboardButton("🎯 6/55 Lucky", callback_data='pick_655'),
            InlineKeyboardButton("🎲 6/45 Lucky", callback_data='pick_645')
        ],
        [
            InlineKeyboardButton("📊 Thống kê", callback_data='stats'),
            InlineKeyboardButton("📈 AI Soi Cầu", callback_data='ai_prediction')
        ],
        [
            InlineKeyboardButton("🔍 Kết quả mới", callback_data='latest'),
            InlineKeyboardButton("🎟 Auto Pick", callback_data='auto_pick')
        ],
        [
            InlineKeyboardButton("🎫 Kiểm tra vé hôm nay", callback_data='check_today')
        ],
        [
            InlineKeyboardButton("🎲 Mua vé tự động ngay", callback_data='manual_buy'),
            InlineKeyboardButton("🔍 Dò số ngay", callback_data='manual_check')
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.effective_chat.send_message(
        f"Chào <b>{user.first_name}</b>, Đại ca đến với Vietlott Pro Tool! 🎰\n\n"
        "Em là trợ lý ảo giúp Đại ca chọn số may mắn và quản lý vé cược.\n"
        "Bấm nút bên dưới hoặc dùng lệnh /buy để tự chọn số nha!",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

from database import (
    get_config, save_played_ticket, played_tickets, get_target_draw_id,
    register_user, get_latest_draw
)
from datetime import datetime, time as dtime

async def auto_pick_tickets(update: Update, context: ContextTypes.DEFAULT_TYPE, game_type=None):
    chat_id = update.effective_chat.id
    config = get_config()
    limit = config.get('daily_limit', 5)
    
    day = datetime.now().weekday()
    if not game_type:
        if day in [0, 2, 4, 6]: 
            game_type = "6/45"
        else: 
            game_type = "6/55"

    today_start = datetime.combine(datetime.now().date(), dtime.min)
    played_today = played_tickets.count_documents({
        "chat_id": chat_id,
        "played_at": {"$gte": today_start}
    })
    
    if played_today >= limit:
        await update.effective_chat.send_message(f"🚫 Đại ca ơi, hôm nay chơi {played_today} vé rồi, đạt giới hạn {limit} vé rồi ạ. Nghỉ mai chiến tiếp!")
        return

    nums = get_ai_lucky_numbers(game_type, "balanced")
    target_draw_id = get_target_draw_id(game_type)
    save_played_ticket(chat_id, game_type, nums, draw_id=target_draw_id)
    
    await update.effective_chat.send_message(
        f"✅ <b>Đã tự động chọn vé {game_type} cho Đại ca:</b>\n\n"
        f"🔢 {', '.join(map(str, nums))}\n\n"
        f"💎 Hệ thống đã nhận ở Web. Em sẽ dò kết quả lúc 19h nha!",
        parse_mode='HTML'
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    # Register/Update user
    from database import register_user
    register_user(chat_id, user.username, user.first_name)
    
    await query.answer()
    
    if query.data == 'pick_655':
        nums = get_ai_lucky_numbers("6/55", "balanced")
        await update.effective_chat.send_message(f"🎰 Bộ số 6/55 cho Đại ca: {' - '.join(map(str, nums))}")
    
    elif query.data == 'pick_645':
        nums = get_ai_lucky_numbers("6/45", "balanced")
        await update.effective_chat.send_message(f"🎰 Bộ số 6/45 cho Đại ca: {' - '.join(map(str, nums))}")
        
    elif query.data == 'stats':
        stats55 = calculate_stats("6/55")
        stats45 = calculate_stats("6/45")
        msg = "📊 <b>Hot Numbers (TOP 10)</b>\n\n"
        msg += f"🔹 <b>6/55:</b> {', '.join(map(str, stats55['hot']))}\n"
        msg += f"🔹 <b>6/45:</b> {', '.join(map(str, stats45['hot']))}"
        await update.effective_chat.send_message(msg, parse_mode='HTML')

    elif query.data == 'latest':
        res55 = get_latest_draw("6/55")
        res45 = get_latest_draw("6/45")
        msg = "🔍 <b>Kết quả mới nhất:</b>\n"
        if res55: msg += f"\n🏆 <b>6/55:</b> {', '.join(map(str, res55['numbers']))}"
        if res45: msg += f"\n🏆 <b>6/45:</b> {', '.join(map(str, res45['numbers']))}"
        await update.effective_chat.send_message(msg, parse_mode='HTML')

    elif query.data == 'ai_prediction':
        nums = get_ai_lucky_numbers("6/55", "mixed")
        await update.effective_chat.send_message(f"🤖 AI Soi Cầu (Gợi ý VIP): {' - '.join(map(str, nums))}")

    elif query.data == 'auto_pick':
        await auto_pick_tickets(update, context)

    elif query.data == 'manual_buy':
        from app import auto_buy_job
        result = auto_buy_job()
        
        if result == "ALREADY_BOUGHT":
            await update.effective_chat.send_message("⚠️ Hôm nay hệ thống đã tự động mua vé cho Đại ca rồi, không cần mua thêm đâu ạ!")
        elif result == "LIMIT_REACHED":
            await update.effective_chat.send_message("🚫 Đại ca đã đạt giới hạn số vé trong ngày rồi ạ.")
        elif result:
            # Note: auto_buy_job already sends a telegram alert on success
            await query.edit_message_text("✅ Đã kích hoạt mua vé thành công! Đại ca kiểm tra tin nhắn mới nhất nha.")
        else:
            await update.effective_chat.send_message("❌ Có lỗi xảy ra khi mua vé. Đại ca kiểm tra lại hệ thống nhé.")

    elif query.data == 'check_today':
        await check_today_tickets(update, context)

    elif query.data == 'manual_check':
        from app import check_results_job
        check_results_job()
        await update.effective_chat.send_message("🔍 Em đang tiến hành dò số đây ạ! Đại ca đợi tin nhắn kết quả nhé.")

async def manual_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) != 7:
        await update.effective_chat.send_message("❌ Sai cú pháp! Hãy gõ: /buy <loại> <6_số>\nVí dụ: /buy 655 01 05 12 24 35 45")
        return

    game_type = args[0]
    # Chuẩn hóa loại vé: 645 -> 6/45, 655 -> 6/55
    if game_type in ["645", "45"]:
        game_type = "6/45"
    elif game_type in ["655", "55"]:
        game_type = "6/55"

    if game_type not in ["6/45", "6/55"]:
        await update.effective_chat.send_message("❌ Loại vé phải là 645 hoặc 655 ạ!")
        return

    try:
        nums = [int(x) for x in args[1:]]
    except ValueError:
        await update.effective_chat.send_message("❌ Các số phải là số nguyên!")
        return
        
    for n in nums:
        if n < 1 or (game_type == "6/45" and n > 45) or (game_type == "6/55" and n > 55):
            await update.effective_chat.send_message(f"❌ Số không hợp lệ! (1-{'45' if game_type == '6/45' else '55'})")
            return
            
    if len(set(nums)) != 6:
        await update.effective_chat.send_message("❌ 6 số không được trùng nhau!")
        return

    chat_id = update.effective_chat.id
    nums.sort()
    target_draw_id = get_target_draw_id(game_type)
    save_played_ticket(chat_id, game_type, nums, draw_id=target_draw_id)
    
    await update.effective_chat.send_message(
        f"✅ <b>Đã lưu vé TỰ CHỌN {game_type} cho Đại ca:</b>\n\n"
        f"🔢 {', '.join(map(str, nums))}\n\n"
        f"💎 Hệ thống đã nhận ở Web. Em sẽ dò kết quả lúc 19h!",
        parse_mode='HTML'
    )

async def check_today_tickets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    now_vn = datetime.now(vn_tz)
    today_start = datetime.combine(now_vn.date(), dtime.min).replace(tzinfo=vn_tz)
    
    tickets = list(played_tickets.find({
        "chat_id": chat_id,
        "played_at": {"$gte": today_start}
    }))
    
    if not tickets:
        await update.effective_chat.send_message("🎫 Hôm nay Đại ca chưa mua vé nào hết. Mau mau chọn số đi ạ! /buy hoặc /pick nhé.")
        return
        
    msg = f"🎫 <b>DANH SÁCH VÉ CỦA ĐẠI CA HÔM NAY:</b>\n"
    msg += f"📅 Ngày: {now_vn.strftime('%d/%m/%Y')}\n\n"
    
    for idx, t in enumerate(tickets, 1):
        mode = "🤖 [AUTO]" if t.get('is_auto') else "👤 [MANUAL]"
        msg += f"{idx}. {mode} <b>{t['game_type']}</b>: {', '.join(map(str, t['numbers']))}\n"
    
    msg += f"\n✨ Tổng cộng: {len(tickets)} vé. Chúc Đại ca may mắn!"
    await update.effective_chat.send_message(msg, parse_mode='HTML')

async def manual_check_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from app import check_results_job
    check_results_job()
    await update.effective_chat.send_message("🔍 Em đang tiến hành dò số đây ạ! Đại ca đợi tin nhắn kết quả nhé.")

if __name__ == '__main__':
    application = ApplicationBuilder().token(TOKEN).build()
    
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('pick', auto_pick_tickets))
    application.add_handler(CommandHandler('buy', manual_pick))
    application.add_handler(CommandHandler('check', check_today_tickets))
    application.add_handler(CommandHandler('check_results', manual_check_cmd))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    print("Bot is running...")
    application.run_polling()
