import os
import logging
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from analytics import get_ai_lucky_numbers, calculate_stats
from database import get_latest_draw

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    reply_keyboard = [['🎯 6/55 Lucky Pick', '🎲 6/45 Lucky Pick'], 
                      ['📊 Thống kê', '📈 AI Soi Cầu'],
                      ['🔍 Kết quả mới nhất', '🎟 Tự động chọn số']]
    
    markup = ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)
    
    await update.message.reply_html(
        f"Chào <b>{user.first_name}</b>, Đại ca đến với Vietlott Pro Tool! 🎰\n\n"
        "Em là trợ lý ảo giúp Đại ca chọn số may mắn và quản lý vé cược.\n"
        "Chọn menu bên dưới hoặc dùng lệnh /pick để em tự động chọn số nha!",
        reply_markup=markup
    )

from database import get_config, save_played_ticket, played_tickets
from datetime import datetime, time as dtime

async def auto_pick_tickets(update: Update, context: ContextTypes.DEFAULT_TYPE, game_type=None):
    chat_id = update.effective_chat.id
    config = get_config()
    limit = config.get('daily_limit', 5)
    
    # Determine game type based on schedule if not provided
    # Mon: 0, Tue: 1, Wed: 2, Thu: 3, Fri: 4, Sat: 5, Sun: 6
    day = datetime.now().weekday()
    if not game_type:
        if day in [0, 2, 4, 6]: # Mon, Wed, Fri, Sun (2, 4, 6, CN)
            game_type = "6/45"
        else: # Tue, Thu, Sat (3, 5, 7)
            game_type = "6/55"

    # Check current tickets played today
    today_start = datetime.combine(datetime.now().date(), dtime.min)
    played_today = played_tickets.count_documents({
        "chat_id": chat_id,
        "played_at": {"$gte": today_start}
    })
    
    if played_today >= limit:
        await update.message.reply_text(f"🚫 Đại ca ơi, hôm nay chơi {played_today} vé rồi, đạt giới hạn {limit} vé rồi ạ. Nghỉ ngơi mai chiến tiếp nha!")
        return

    # Pick numbers
    nums = get_ai_lucky_numbers(game_type, "balanced")
    save_played_ticket(chat_id, game_type, nums)
    
    await update.message.reply_html(
        f"✅ <b>Đã tự động chọn vé {game_type} cho Đại ca (Lịch {day+2 if day<6 else 'CN'}):</b>\n\n"
        f"🔢 {', '.join(map(str, nums))}\n\n"
        f"💎 Vé đã được lưu vào hệ thống. Em sẽ tự động dò kết quả lúc 19h nha!"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    
    if text == '🎯 6/55 Lucky Pick':
        nums = get_ai_lucky_numbers("6/55", "balanced")
        await update.message.reply_text(f"🎰 Bộ số 6/55 may mắn cho Đại ca:\n\n✨ {' - '.join(map(str, nums))} ✨\n\nChúc Đại ca trúng Jackpot! 💰")
    
    elif text == '🎲 6/45 Lucky Pick':
        nums = get_ai_lucky_numbers("6/45", "balanced")
        await update.message.reply_text(f"🎰 Bộ số 6/45 may mắn cho Đại ca:\n\n✨ {' - '.join(map(str, nums))} ✨\n\nChúc Đại ca nổ Jackpot! 💰")
        
    elif text == '📊 Thống kê':
        stats55 = calculate_stats("6/55")
        stats45 = calculate_stats("6/45")
        
        msg = "📊 <b>Thống kê Hot Numbers (10 số xuất hiện nhiều nhất)</b>\n\n"
        msg += f"🔹 <b>6/55:</b> {', '.join(map(str, stats55['hot']))}\n"
        msg += f"🔹 <b>6/45:</b> {', '.join(map(str, stats45['hot']))}\n\n"
        msg += "💡 <i>Dùng tổ hợp Hot + Cold để tăng tỉ lệ trúng nha Đại ca!</i>"
        await update.message.reply_html(msg)

    elif text == '🔍 Kết quả mới nhất':
        res55 = get_latest_draw("6/55")
        res45 = get_latest_draw("6/45")
        
        msg = "🔍 <b>Kết quả xổ số mới nhất:</b>\n\n"
        if res55:
            msg += f"🏆 <b>Power 6/55 (Kỳ #{res55['draw_id']}):</b>\n📅 {res55['draw_date']}\n🔢 {', '.join(map(str, res55['numbers']))}\n\n"
        if res45:
            msg += f"🏆 <b>Mega 6/45 (Kỳ #{res45['draw_id']}):</b>\n📅 {res45['draw_date']}\n🔢 {', '.join(map(str, res45['numbers']))}\n"
            
        await update.message.reply_html(msg)

    elif text == '📈 AI Soi Cầu':
        nums = get_ai_lucky_numbers("6/55", "mixed")
        await update.message.reply_text(f"🤖 AI đã phân tích lịch sử 500 kỳ gần nhất...\n\nGợi ý VIP cho Đại ca:\n\n💎 {' - '.join(map(str, nums))} 💎")

    elif text == '🎟 Tự động chọn số':
        await auto_pick_tickets(update, context)

async def manual_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) != 7:
        await update.message.reply_text("❌ Sai cú pháp! Hãy gõ: /buy <loại_vé> <6_số>\nVí dụ: /buy 6/55 01 05 12 24 35 45")
        return

    game_type = args[0]
    if game_type not in ["6/45", "6/55"]:
        await update.message.reply_text("❌ Loại vé phải là 6/45 hoặc 6/55")
        return

    try:
        nums = [int(x) for x in args[1:]]
    except ValueError:
        await update.message.reply_text("❌ Các số phải là số nguyên!")
        return
        
    for n in nums:
        if n < 1 or (game_type == "6/45" and n > 45) or (game_type == "6/55" and n > 55):
            await update.message.reply_text(f"❌ Số không hợp lệ cho {game_type}! (Từ 1 đến {'45' if game_type == '6/45' else '55'})")
            return
            
    if len(set(nums)) != 6:
        await update.message.reply_text("❌ 6 số không được trùng nhau!")
        return

    chat_id = update.effective_chat.id
    config = get_config()
    limit = config.get('daily_limit', 5)

    today_start = datetime.combine(datetime.now().date(), dtime.min)
    played_today = played_tickets.count_documents({
        "chat_id": chat_id,
        "played_at": {"$gte": today_start}
    })
    
    if played_today >= limit:
        await update.message.reply_text(f"🚫 Đại ca ơi, hôm nay chơi {played_today} vé rồi, đạt giới hạn {limit} vé rồi ạ.")
        return

    nums.sort()
    save_played_ticket(chat_id, game_type, nums)
    
    await update.message.reply_html(
        f"✅ <b>Đã lưu vé TỰ CHỌN {game_type} cho Đại ca:</b>\n\n"
        f"🔢 {', '.join(map(str, nums))}\n\n"
        f"💎 Hệ thống đã nhận ở Web. Em sẽ tự động dò kết quả lúc 19h nha!"
    )

if __name__ == '__main__':
    application = ApplicationBuilder().token(TOKEN).build()
    
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('pick', auto_pick_tickets))
    application.add_handler(CommandHandler('buy', manual_pick))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    print("Bot is running...")
    application.run_polling()
