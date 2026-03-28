import telebot
from flask import Flask, request
import os
import requests
from datetime import datetime
import pytesseract
from PIL import Image
import io
import re

# 👉 Tesseract Path (Railway Linux)
pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"

TOKEN = os.environ.get("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)

app = Flask(__name__)

# 👉 memory
user_source = {}
user_first_message_saved = {}

# 👉 Google Sheets Webhook URL (ဒီမှာထည့်)
GOOGLE_SHEET_URL = "https://script.google.com/macros/s/AKfycby5_bxl2uISK4WsD-uFxPTvGbcuc0ZJKKAhS-BQIXWxV4Bp2Dj-BWPqyOarg0iyoWKx_A/exec"


# 🚀 SEND DATA → GOOGLE SHEETS
def send_to_sheet(user_id, source, msg_type, message, amount, bank, status):
    data = {
        "user_id": user_id,
        "source": source,
        "type": msg_type,
        "message": message,
        "amount": amount,
        "bank": bank,
        "status": status,
        "time": str(datetime.now())
    }

    try:
        requests.post(GOOGLE_SHEET_URL, json=data)
    except Exception as e:
        print("Sheet Error:", e)


# 🧠 SLIP DETECTION (SCORE SYSTEM)
def is_valid_slip(text):
    text = text.lower()

    currency_keywords = ["ks", "mmk", "ကျပ်"]
    bank_keywords = ["kbz", "wave", "aya", "cb", "uab"]
    success_keywords = ["success", "completed", "successful", "done"]

    amount_pattern = re.findall(r"\d{1,3}(,\d{3})+", text)

    has_currency = any(k in text for k in currency_keywords)
    has_bank = any(k in text for k in bank_keywords)
    has_success = any(k in text for k in success_keywords)
    has_amount = len(amount_pattern) > 0

    score = sum([has_currency, has_bank, has_success, has_amount])

    print(f"SCORE: {score}")

    return score >= 3


# 🧠 EXTRACT DATA
def extract_slip_data(text):
    text_lower = text.lower()

    # 👉 Amount
    amount_match = re.search(r"\d{1,3}(,\d{3})+", text)
    amount = amount_match.group() if amount_match else "unknown"

    # 👉 Bank detect
    if "kbz" in text_lower:
        bank = "KBZ"
    elif "wave" in text_lower:
        bank = "Wave"
    elif "aya" in text_lower:
        bank = "AYA"
    elif "cb" in text_lower:
        bank = "CB"
    elif "uab" in text_lower:
        bank = "UAB"
    else:
        bank = "unknown"

    # 👉 Status
    if "success" in text_lower or "completed" in text_lower:
        status = "success"
    else:
        status = "unknown"

    return amount, bank, status


# 🔥 START (source tracking)
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.chat.id
    text = message.text

    source = "unknown"
    if len(text.split()) > 1:
        source = text.split()[1]

    user_source[user_id] = source
    user_first_message_saved[user_id] = False

    print(f"START | {user_id} | {source}")

    send_to_sheet(user_id, source, "start", "start", "", "", "")


# 💬 FIRST MESSAGE ONLY
@bot.message_handler(func=lambda m: True, content_types=['text'])
def handle_text(message):
    user_id = message.chat.id
    text = message.text
    source = user_source.get(user_id, "unknown")

    if not user_first_message_saved.get(user_id, False):
        print(f"FIRST MSG | {user_id} | {text}")

        send_to_sheet(user_id, source, "first_message", text, "", "", "")

        user_first_message_saved[user_id] = True
    else:
        print(f"IGNORE TEXT | {user_id}")


# 📸 PHOTO (OCR + FILTER + EXTRACT)
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    user_id = message.chat.id
    source = user_source.get(user_id, "unknown")

    try:
        # 👉 download photo
        photo = message.photo[-1].file_id
        file_info = bot.get_file(photo)
        downloaded_file = bot.download_file(file_info.file_path)

        # 👉 OCR
        image = Image.open(io.BytesIO(downloaded_file))
        text = pytesseract.image_to_string(image)

        print("OCR TEXT:\n", text)

        # 👉 detect slip
        if is_valid_slip(text):
            amount, bank, status = extract_slip_data(text)

            file_path = file_info.file_path
            image_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"

            print(f"VALID SLIP | {user_id} | {amount} | {bank} | {status}")

            send_to_sheet(user_id, source, "deposit", image_url, amount, bank, status)

        else:
            print(f"IGNORE PHOTO | {user_id}")

    except Exception as e:
        print("PHOTO ERROR:", e)


# 🌐 WEBHOOK
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    json_str = request.get_data().decode("UTF-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "OK", 200


# 🌐 HOME
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
