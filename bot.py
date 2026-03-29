import telebot
from flask import Flask, request
import os
import requests
from datetime import datetime
import pytesseract
from PIL import Image
import io
import re
import cv2
import numpy as np

pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"

TOKEN = os.environ.get("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

GOOGLE_SHEET_URL = "https://script.google.com/macros/s/AKfycbxnchGPWar1Ktl8IWa7xVq8FxsskDL9WmRRb3eANP5UnQvqKU_hPebnTfPo0R5Z5dDnzw/exec"

user_source = {}
first_msg_saved = {}

# 👉 Myanmar number → English
def mm_to_en(text):
    mm = "၀၁၂၃၄၅၆၇၈၉"
    en = "0123456789"
    for m, e in zip(mm, en):
        text = text.replace(m, e)
    return text


# 👉 IMAGE PREPROCESS (🔥 IMPORTANT)
def preprocess(image):
    img = np.array(image)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # sharpen
    kernel = np.array([[0,-1,0],[-1,5,-1],[0,-1,0]])
    sharp = cv2.filter2D(gray, -1, kernel)

    # threshold
    _, thresh = cv2.threshold(sharp, 150, 255, cv2.THRESH_BINARY)

    return thresh


# 👉 BANK DETECT
def get_bank(text):
    t = text.lower()
    if "kbz" in t:
        return "KBZ"
    if "wave" in t:
        return "Wave"
    return "unknown"


# 👉 AMOUNT EXTRACT (🔥 CORE FIX)
def get_amount(text, bank):
    text = mm_to_en(text)
    t = text.lower().replace(",", "")

    # ---------- KBZ ----------
    if bank == "KBZ":
        # -200000.00 Ks
        match = re.findall(r"-?\d{4,}\.\d{2}", t)
        if match:
            return match[0].replace("-", "")

    # ---------- WAVE ----------
    if bank == "Wave":
        # 10000.00
        match = re.findall(r"\d{3,}\.\d{2}", t)
        if match:
            return match[0]

    # ---------- COMMON ----------
    match = re.findall(r"(?:ks|mmk|kyat)?\s*(\d{3,7})\s*(?:ks|mmk|kyat)?", t)

    # filter phone numbers (9-11 digits)
    match = [m for m in match if len(m) <= 7]

    if match:
        return max(match, key=lambda x: int(x))

    return "unknown"


# 👉 STATUS
def get_status(text):
    t = text.lower()
    if "success" in t or "completed" in t or "အောင်မြင်" in t:
        return "success"
    return "unknown"


# 👉 SEND TO SHEET
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
    except:
        pass


# 🚀 START
@bot.message_handler(commands=['start'])
def start(msg):
    uid = msg.chat.id
    source = "unknown"

    if len(msg.text.split()) > 1:
        source = msg.text.split()[1]

    user_source[uid] = source
    first_msg_saved[uid] = False

    send_to_sheet(uid, source, "start", "start", "", "", "")


# 💬 FIRST MESSAGE
@bot.message_handler(func=lambda m: True, content_types=['text'])
def first_msg(msg):
    uid = msg.chat.id
    source = user_source.get(uid, "unknown")

    if not first_msg_saved.get(uid, False):
        send_to_sheet(uid, source, "first_message", msg.text, "", "", "")
        first_msg_saved[uid] = True


# 📸 PHOTO OCR
@bot.message_handler(content_types=['photo'])
def photo(msg):
    uid = msg.chat.id
    source = user_source.get(uid, "unknown")

    try:
        file_id = msg.photo[-1].file_id
        file_info = bot.get_file(file_id)

        file_path = file_info.file_path
        image_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"

        file = bot.download_file(file_path)
        image = Image.open(io.BytesIO(file))

        # 🔥 preprocess
        processed = preprocess(image)

        # OCR
        text = pytesseract.image_to_string(
            processed,
            lang='eng+my',
            config='--psm 6'
        )

        print("OCR:\n", text)

        bank = get_bank(text)

        # ❌ not slip
        if bank == "unknown":
            return

        amount = get_amount(text, bank)
        status = get_status(text)

        print("RESULT:", amount, bank)

        send_to_sheet(uid, source, "deposit", image_url, amount, bank, status)

    except Exception as e:
        print("ERROR:", e)


# 🌐 WEBHOOK
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = telebot.types.Update.de_json(request.get_data().decode("utf-8"))
    bot.process_new_updates([update])
    return "OK"


@app.route("/")
def home():
    return "Running"


# 🚀 RUN
if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"https://your-app-url/{TOKEN}")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
