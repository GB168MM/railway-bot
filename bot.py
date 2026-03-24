import telebot
from flask import Flask, request
import os
import requests

TOKEN = os.environ.get("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)

app = Flask(__name__)

# 👉 user source memory
user_source = {}

# 👉 ManyChat webhook URL (ဒီမှာထည့်)
MANYCHAT_URL = "https://your-manychat-webhook-url"


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

    # 👉 ManyChat ကိုပို့
    send_to_manychat(user_id, "start", source)


# 💬 TEXT MESSAGE (chat tracking)
@bot.message_handler(func=lambda m: True, content_types=['text'])
def handle_text(message):
    user_id = message.chat.id
    text = message.text
    source = user_source.get(user_id, "unknown")

    print(f"MSG | {user_id} | {source} | {text}")

    # 👉 ManyChat ကိုပို့
    send_to_manychat(user_id, text, source)


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

    # 👉 ManyChat ကိုပို့
    send_to_manychat(user_id, image_url, source)


# 🚀 SEND DATA → ManyChat
def send_to_manychat(user_id, text, source):
    data = {
        "user_id": user_id,
        "message": text,
        "source": source
    }

    try:
        requests.post(MANYCHAT_URL, json=data)
    except Exception as e:
        print("ManyChat Error:", e)


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
