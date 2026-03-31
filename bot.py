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
        res = requests.post(GOOGLE_SHEET_URL, json=data)
        print("SENT:", data, "STATUS:", res.status_code)
    except Exception as e:
        print("SHEET ERROR:", e)

# ========= UTIL =========
def mm_to_en(text):
    mm = "၀၁၂၃၄၅၆၇၈၉"
    en = "0123456789"
    for m, e in zip(mm, en):
        text = text.replace(m, e)
    return text

def extract_amount(text):
    text = mm_to_en(text)
    text = text.replace(",", "")
    nums = re.findall(r"\d{4,6}", text)
    if nums:
        nums = [int(n) for n in nums if 1000 <= int(n) <= 100000]
        if nums:
            nums.sort()
            return str(nums[len(nums)//2])
    return "0"

# ========= START =========
@bot.message_handler(commands=['start'])
def start(msg):
    send_to_sheet({
        "type": "start",
        "user_id": msg.chat.id,
        "text": "start",
        "amount": "0",
        "time": str(datetime.now())
    })

# ========= TEXT =========
@bot.message_handler(content_types=['text'])
def text(msg):
    send_to_sheet({
        "type": "text",
        "user_id": msg.chat.id,
        "text": msg.text,
        "amount": "0",
        "time": str(datetime.now())
    })

# ========= IMAGE =========
@bot.message_handler(content_types=['photo', 'document'])
def image(msg):
    print("IMAGE RECEIVED")

    try:
        # photo OR document
        if msg.content_type == 'photo':
            file_id = msg.photo[-1].file_id
        else:
            file_id = msg.document.file_id

        file_info = bot.get_file(file_id)
        file = bot.download_file(file_info.file_path)

        image = Image.open(io.BytesIO(file)).convert("RGB")

        # OCR
        text = pytesseract.image_to_string(image, lang='eng+my', config='--psm 6')
        print("OCR TEXT:", text)

        amount = extract_amount(text)

        image_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}"

        print("FINAL AMOUNT:", amount)

        send_to_sheet({
            "type": "image",
            "user_id": msg.chat.id,
            "text": text,
            "amount": amount,
            "image_url": image_url,
            "time": str(datetime.now())
        })

    except Exception as e:
        print("IMAGE ERROR:", e)

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
    bot.set_webhook(
        url="https://beautiful-delight-production-79cf.up.railway.app/"
    )
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
