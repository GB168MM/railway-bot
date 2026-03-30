import os
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

import telebot
from flask import Flask, request
import requests
from datetime import datetime
from PIL import Image
import io
import re
import numpy as np

from paddleocr import PaddleOCR

# ================= OCR =================
ocr = PaddleOCR(use_angle_cls=True, lang='en')

# ================= BOT =================
TOKEN = os.environ.get("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)

app = Flask(__name__)

GOOGLE_SHEET_URL = "https://script.google.com/macros/s/AKfycbxnchGPWar1Ktl8IWa7xVq8FxsskDL9WmRRb3eANP5UnQvqKU_hPebnTfPo0R5Z5dDnzw/exec"

user_source = {}
first_msg_saved = {}

# ================= UTIL =================
def mm_to_en(text):
    mm = "၀၁၂၃၄၅၆၇၈၉"
    en = "0123456789"
    for m, e in zip(mm, en):
        text = text.replace(m, e)
    return text

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

# ================= OCR =================
def extract_amount(image):
    img = np.array(image)

    result = ocr.ocr(img)

    texts = []
    for line in result:
        for word in line:
            texts.append(word[1][0])

    full_text = " ".join(texts)
    print("OCR TEXT:", full_text)

    full_text = mm_to_en(full_text)
    full_text = full_text.replace(",", "")

    # 🔥 keyword-based filtering
    keywords = ["amount", "kyat", "ks", "ကျပ်"]

    words = full_text.split()
    candidates = []

    for i, w in enumerate(words):
        if any(k in w.lower() for k in keywords):
            for j in range(i, min(i+3, len(words))):
                nums = re.findall(r"\d{4,}", words[j])
                for n in nums:
                    val = int(n)
                    if 1000 <= val <= 10000000:
                        candidates.append(val)

    # fallback
    if not candidates:
        nums = re.findall(r"\d{4,}", full_text)
        for n in nums:
            val = int(n)
            if 1000 <= val <= 10000000:
                candidates.append(val)

    if candidates:
        return str(max(candidates)), full_text

    return "unknown", full_text

# ================= BANK =================
def detect_bank(text):
    t = text.lower()

    if "kbz" in t or "kpay" in t:
        return "KBZ"

    if "wave" in t or "ကျပ်" in t:
        return "Wave"

    return "unknown"

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

        amount, full_text = extract_amount(image)
        bank = detect_bank(full_text)
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
