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

# ================= CONFIG =================
TOKEN = os.environ.get("BOT_TOKEN")
APP_URL = "https://beautiful-delight-production-79cf.up.railway.app"

print("TOKEN =", TOKEN)  # 🔥 DEBUG

pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"

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


def clean_ocr_text(text):
    text = text.replace("J", "0")
    text = text.replace("O", "0")
    text = text.replace("l", "1")
    return text


def preprocess(image):
    img = np.array(image)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    kernel = np.array([[0,-1,0],[-1,5,-1],[0,-1,0]])
    sharp = cv2.filter2D(gray, -1, kernel)

    _, thresh = cv2.threshold(sharp, 150, 255, cv2.THRESH_BINARY)

    return thresh


# ================= CORE =================

def get_bank(text):
    t = text.lower()
    if "kbz" in t:
        return "KBZ"
    if "wave" in t:
        return "Wave"
    return "unknown"


def get_amount(text, bank):
    text = mm_to_en(text)
    text = clean_ocr_text(text)

    t = text.lower().replace(",", "")

    # Wave
    if bank == "Wave":
        lines = text.split("\n")
        for line in lines:
            l = clean_ocr_text(line)
            if "ks" in l.lower() or "ကျပ်" in l:
                nums = re.findall(r"\d{3,}\.\d{2}", l.replace(",", ""))
                if nums:
                    return nums[0]

        nums = re.findall(r"\d{3,}\.\d{2}", t)
        if nums:
            return max(nums, key=lambda x: float(x))

    # KBZ
    if bank == "KBZ":
        nums = re.findall(r"-?\d{4,}\.\d{2}", t)
        if nums:
            return nums[0].replace("-", "")

    # fallback
    nums = re.findall(r"\d{3,7}", t)
    nums = [n for n in nums if len(n) <= 7]

    if nums:
        return max(nums, key=lambda x: int(x))

    return "unknown"


def get_status(text):
    t = text.lower()
    if "success" in t or "completed" in t or "အောင်မြင်" in t:
        return "success"
    return "unknown"


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
        res = requests.post(GOOGLE_SHEET_URL, json=data)
        print("SHEET STATUS:", res.status_code, res.text)  # 🔥 DEBUG
    except Exception as e:
        print("SHEET ERROR:", e)


# ================= BOT =================

@bot.message_handler(commands=['start'])
def start(msg):
    uid = msg.chat.id
    source = "unknown"

    if len(msg.text.split()) > 1:
        source = msg.text.split()[1]

    user_source[uid] = source
    first_msg_saved[uid] = False

    send_to_sheet(uid, source, "start", "start", "", "", "")


@bot.message_handler(func=lambda m: True, content_types=['text'])
def first_msg(msg):
    uid = msg.chat.id
    source = user_source.get(uid, "unknown")

    if not first_msg_saved.get(uid, False):
        send_to_sheet(uid, source, "first_message", msg.text, "", "", "")
        first_msg_saved[uid] = True


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

        processed = preprocess(image)

        text = pytesseract.image_to_string(
            processed,
            lang='eng+my',
            config='--psm 6 --oem 3 -c tessedit_char_whitelist=0123456789.Ksks'
        )

        print("OCR:\n", text)

        bank = get_bank(text)

        if bank == "unknown":
            print("NOT SLIP")
            return

        amount = get_amount(text, bank)
        status = get_status(text)

        print("RESULT:", amount, bank)

        send_to_sheet(uid, source, "deposit", image_url, amount, bank, status)

    except Exception as e:
        print("ERROR:", e)


# ================= WEBHOOK =================

@app.route("/", methods=["GET"])
def home():
    return "Running"


@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    print("Webhook HIT")  # 🔥 DEBUG
    json_str = request.get_data().decode("utf-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "OK"


# ================= RUN =================

if __name__ == "__main__":
    if not TOKEN:
        print("❌ ERROR: BOT_TOKEN missing")

    bot.delete_webhook()  # 🔥 reset
    bot.set_webhook(url=f"{APP_URL}/{TOKEN}")

    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
