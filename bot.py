import os
import logging
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from analytics import get_ai_lucky_numbers, calculate_stats
from database import get_latest_draw

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

print(TOKEN)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
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

from database import get_config, save_played_ticket, played_tickets
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
    save_played_ticket(chat_id, game_type, nums)
    
    await update.effective_chat.send_message(
        f"✅ <b>Đã tự động chọn vé {game_type} cho Đại ca:</b>\n\n"
        f"🔢 {', '.join(map(str, nums))}\n\n"
        f"💎 Hệ thống đã nhận ở Web. Em sẽ dò kết quả lúc 19h nha!",
        parse_mode='HTML'
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
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

async def manual_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) != 7:
        await update.effective_chat.send_message("❌ Sai cú pháp! Hãy gõ: /buy <loại_vé> <6_số>\nVí dụ: /buy 6/55 01 05 12 24 35 45")
        return

    game_type = args[0]
    if game_type not in ["6/45", "6/55"]:
        await update.effective_chat.send_message("❌ Loại vé phải là 6/45 hoặc 6/55")
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
    config = get_config()
    limit = config.get('daily_limit', 5)

    today_start = datetime.combine(datetime.now().date(), dtime.min)
    played_today = played_tickets.count_documents({
        "chat_id": chat_id,
        "played_at": {"$gte": today_start}
    })
    
    if played_today >= limit:
        await update.effective_chat.send_message(f"🚫 Đại ca chơi {played_today} vé rồi, đạt giới hạn {limit} vé.")
        return

    nums.sort()
    save_played_ticket(chat_id, game_type, nums)
    
    await update.effective_chat.send_message(
        f"✅ <b>Đã lưu vé TỰ CHỌN {game_type} cho Đại ca:</b>\n\n"
        f"🔢 {', '.join(map(str, nums))}\n\n"
        f"💎 Hệ thống đã nhận ở Web. Em sẽ dò kết quả lúc 19h!",
        parse_mode='HTML'
    )

if __name__ == '__main__':
    application = ApplicationBuilder().token(TOKEN).build()
    
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('pick', auto_pick_tickets))
    application.add_handler(CommandHandler('buy', manual_pick))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    print("Bot is running...")
    application.run_polling()
