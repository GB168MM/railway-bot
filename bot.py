import telebot
from flask import Flask, request
import os
import requests

TOKEN = os.environ.get("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)

app = Flask(__name__)

# 👉 user source memory
user_source = {}

# 👉 Google Sheets Webhook URL (ဒီမှာထည့်)
GOOGLE_SHEET_URL = "https://script.google.com/macros/s/AKfycby5_bxl2uISK4WsD-uFxPTvGbcuc0ZJKKAhS-BQIXWxV4Bp2Dj-BWPqyOarg0iyoWKx_A/exec"


# 🔥 START (channel tracking)
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.chat.id
    text = message.text

    source = "unknown"
    if len(text.split()) > 1:
        source = text.split()[1]

    user_source[user_id] = source

    print(f"START | {user_id} | {source}")

    # 👉 Google Sheets ကိုပို့
    send_to_sheet(user_id, "start", source, "start")


# 💬 TEXT MESSAGE (chat tracking)
@bot.message_handler(func=lambda m: True, content_types=['text'])
def handle_text(message):
    user_id = message.chat.id
    text = message.text
    source = user_source.get(user_id, "unknown")

    print(f"MSG | {user_id} | {source} | {text}")

    # 👉 Google Sheets ကိုပို့
    send_to_sheet(user_id, text, source, "text")


# 📸 PHOTO (deposit slip tracking + link)
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    user_id = message.chat.id
    source = user_source.get(user_id, "unknown")

    # 👉 photo id
    photo = message.photo[-1].file_id

    # 👉 get file path
    file_info = bot.get_file(photo)
    file_path = file_info.file_path

    # 👉 generate image link
    image_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"

    print(f"DEPOSIT | {user_id} | {source} | LINK: {image_url}")

    # 👉 Google Sheets ကိုပို့ (IMPORTANT)
    send_to_sheet(user_id, image_url, source, "deposit")


# 🚀 SEND DATA → GOOGLE SHEETS
def send_to_sheet(user_id, message, source, msg_type):
    data = {
        "user_id": user_id,
        "message": message,
        "source": source,
        "type": msg_type
    }

    try:
        requests.post(GOOGLE_SHEET_URL, json=data)
    except Exception as e:
        print("Sheet Error:", e)


# 🌐 WEBHOOK ROUTE
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    json_str = request.get_data().decode("UTF-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "OK", 200


# 🌐 HOME CHECK
@app.route("/")
def home():
    return "Bot Running 🚀"


# 🚀 RUN
if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(
        url=f"https://railway-bot-production-e57e.up.railway.app/{TOKEN}"
    )
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
