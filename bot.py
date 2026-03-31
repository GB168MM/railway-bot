import telebot
from flask import Flask, request
import os
import requests
from datetime import datetime
from PIL import Image
import pytesseract
import io
import re

# ========= CONFIG =========
TOKEN = os.environ.get("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

GOOGLE_SHEET_URL = "https://script.google.com/macros/s/AKfycbxnchGPWar1Ktl8IWa7xVq8FxsskDL9WmRRb3eANP5UnQvqKU_hPebnTfPo0R5Z5dDnzw/exec"

# ========= SEND TO SHEET =========
def send_to_sheet(data):
    try:
        requests.post(GOOGLE_SHEET_URL, json=data)
        print("SENT:", data)
    except Exception as e:
        print("SHEET ERROR:", e)

# ========= START =========
@bot.message_handler(commands=['start'])
def start(msg):
    send_to_sheet({
        "type": "start",
        "user_id": msg.chat.id,
        "text": "start",
        "amount": "0"
    })

# ========= TEXT =========
@bot.message_handler(content_types=['text'])
def text(msg):
    send_to_sheet({
        "type": "text",
        "user_id": msg.chat.id,
        "text": msg.text,
        "amount": "0"
    })

# ========= IMAGE =========
@bot.message_handler(content_types=['photo'])
def photo(msg):
    print("PHOTO RECEIVED")

    file_id = msg.photo[-1].file_id
    file_info = bot.get_file(file_id)
    file = bot.download_file(file_info.file_path)

    image = Image.open(io.BytesIO(file))
    text = pytesseract.image_to_string(image)

    print("OCR:", text)

    amount = extract_amount(text)

    send_to_sheet({
        "type": "image",
        "user_id": msg.chat.id,
        "text": text,
        "amount": amount
    })

# ========= AMOUNT =========
def extract_amount(text):
    nums = re.findall(r"\d{4,6}", text)
    if nums:
        return nums[0]
    return "0"

# ========= WEBHOOK =========
@app.route("/", methods=["POST"])
def webhook():
    json_str = request.get_data().decode("UTF-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "OK"

@app.route("/")
def home():
    return "BOT RUNNING"

# ========= RUN =========
if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url="https://beautiful-delight-production-79cf.up.railway.app/")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
