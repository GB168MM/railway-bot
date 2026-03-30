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

# ================= OCR =================
pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"
print("TESSERACT LANGS:", pytesseract.get_languages(config=''))

# ================= BOT =================
TOKEN = os.environ.get("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)

app = Flask(__name__)

user_source = {}
first_msg_saved = {}

GOOGLE_SHEET_URL = "https://script.google.com/macros/s/AKfycbxnchGPWar1Ktl8IWa7xVq8FxsskDL9WmRRb3eANP5UnQvqKU_hPebnTfPo0R5Z5dDnzw/exec"

# ================= SEND =================
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

# ================= UTIL =================
def mm_to_en(text):
    mm = "၀၁၂၃၄၅၆၇၈၉"
    en = "0123456789"
    for m, e in zip(mm, en):
        text = text.replace(m, e)
    return text

def fix_ocr_errors(text):
    text = text.replace("J", "2")
    text = text.replace("O", "0")
    text = text.replace("o", "0")
    text = text.replace("B", "8")
    return text

# ================= PREPROCESS =================
def preprocess_wave_strong(pil_image):
    img = np.array(pil_image)

    hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)

    lower = np.array([0, 0, 0])
    upper = np.array([180, 255, 120])

    mask = cv2.inRange(hsv, lower, upper)

    return mask

# ================= BANK =================
def detect_bank(image, text):
    t = text.lower()

    if "kbz" in t:
        return "KBZ"

    small = image.resize((50,50))
    pixels = list(small.getdata())

    yellow = 0
    for r,g,b in pixels:
        if r > 200 and g > 200 and b < 150:
            yellow += 1

    if yellow > 500:
        return "Wave"

    if "ကျပ်" in t or "အောင်မြင်" in t:
        return "Wave"

    return "unknown"

# ================= KBZ =================
def extract_kbz_amount(text):
    text = mm_to_en(text)
    text = fix_ocr_errors(text)
    text = text.replace(",", "")

    nums = re.findall(r"\d{4,}", text)

    valid = []
    for n in nums:
        val = int(n)
        if 1000 <= val <= 10000000:
            valid.append(val)

    return str(max(valid)) if valid else "unknown"

# ================= WAVE (ULTRA FIX) =================
def extract_wave_amount(image):
    width, height = image.size

    # 🔥 multiple tight scan zones
    areas = [
        image.crop((0, int(height * 0.2), width, int(height * 0.4))),
        image.crop((0, int(height * 0.25), width, int(height * 0.5))),
        image.crop((0, int(height * 0.3), width, int(height * 0.55)))
    ]

    results = []

    for i, area in enumerate(areas):
        processed = preprocess_wave_strong(area)

        text = pytesseract.image_to_string(
            processed,
            lang='eng+my',
            config='--psm 7'
        )

        print(f"OCR AREA {i}:", text)

        text = mm_to_en(text)
        text = fix_ocr_errors(text)
        text = text.replace(",", "")

        nums = re.findall(r"\d{4,}", text)

        for n in nums:
            val = int(n)
            if 1000 <= val <= 10000000:
                results.append(val)

    # 🔥 fallback (full image OCR)
    if not results:
        print("Fallback OCR...")
        text = pytesseract.image_to_string(image, lang='eng+my')

        text = mm_to_en(text)
        text = fix_ocr_errors(text)

        nums = re.findall(r"\d{4,}", text)

        for n in nums:
            val = int(n)
            if 1000 <= val <= 10000000:
                results.append(val)

    print("FINAL RESULTS:", results)

    return str(max(results)) if results else "unknown"

# ================= STATUS =================
def get_status(text):
    t = text.lower()
    if "success" in t or "completed" in t or "thank" in t or "အောင်မြင်" in t:
        return "success"
    return "unknown"

# ================= START =================
@bot.message_handler(commands=['start'])
def start(msg):
    uid = msg.chat.id
    source = "unknown"

    if len(msg.text.split()) > 1:
        source = msg.text.split()[1]

    user_source[uid] = source
    first_msg_saved[uid] = False

    send_to_sheet(uid, source, "start", "start", "", "", "")

# ================= TEXT =================
@bot.message_handler(func=lambda m: True, content_types=['text'])
def first_msg(msg):
    uid = msg.chat.id
    source = user_source.get(uid, "unknown")

    if not first_msg_saved.get(uid, False):
        send_to_sheet(uid, source, "first_message", msg.text, "", "", "")
        first_msg_saved[uid] = True

# ================= PHOTO =================
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
        image = Image.open(io.BytesIO(file)).convert("RGB")

        # FULL OCR
        full_text = pytesseract.image_to_string(
            image,
            lang='eng+my',
            config='--psm 6'
        )

        full_text = mm_to_en(full_text)
        full_text = fix_ocr_errors(full_text)

        print("FULL OCR:", full_text)

        bank = detect_bank(image, full_text)

        if bank == "KBZ":
            amount = extract_kbz_amount(full_text)
        elif bank == "Wave":
            amount = extract_wave_amount(image)
        else:
            amount = "unknown"

        status = get_status(full_text)

        print("FINAL:", amount, bank, status)

        send_to_sheet(uid, source, "deposit", image_url, amount, bank, status)

    except Exception as e:
        print("ERROR:", e)

# ================= WEBHOOK =================
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = telebot.types.Update.de_json(request.get_data().decode("utf-8"))
    bot.process_new_updates([update])
    return "OK"

@app.route("/")
def home():
    return "Bot Running"

# ================= RUN =================
if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(
        url=f"https://railway-bot-production-e57e.up.railway.app/{TOKEN}"
    )
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
