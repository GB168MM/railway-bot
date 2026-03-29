import telebot
from flask import Flask, request
import os
import requests
from datetime import datetime
import pytesseract
from PIL import Image
import io
import re

# ================= CONFIG =================
TOKEN = os.environ.get("BOT_TOKEN")
APP_URL = "https://beautiful-delight-production-79cf.up.railway.app"

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"

GOOGLE_SHEET_URL = "https://script.google.com/macros/s/AKfycbxnchGPWar1Ktl8IWa7xVq8FxsskDL9WmRRb3eANP5UnQvqKU_hPebnTfPo0R5Z5dDnzw/exec"

# ================= UTIL =================

def clean(text):
    text = text.replace(",", "")
    text = text.replace("O", "0").replace("o", "0")
    text = text.replace("l", "1").replace("I", "1")
    text = text.replace("S", "5")
    return text


# ================= BANK =================

def get_bank(text):
    t = text.lower()

    if "kbz" in t:
        return "KBZ"

    if "wave" in t or "money" in t:
        return "Wave"

    return "unknown"


# ================= AMOUNT =================

def get_amount_wave(text):
    text = clean(text)

    # Wave slip usually has decimal amount
    nums = re.findall(r"\d{3,}\.\d{2}", text)
    if nums:
        return max(nums, key=lambda x: float(x))

    return "unknown"


def get_amount_kbz(text):
    text = clean(text)

    # KBZ: often integer big number
    nums = re.findall(r"\d{4,7}", text)

    # filter unrealistic numbers
    nums = [n for n in nums if int(n) < 10000000]

    if nums:
        return max(nums, key=lambda x: int(x))

    return "unknown"


def get_amount(text, bank):
    if bank == "Wave":
        return get_amount_wave(text)

    if bank == "KBZ":
        return get_amount_kbz(text)

    return "unknown"


# ================= STATUS =================

def get_status(text):
    t = text.lower()

    if any(x in t for x in ["success", "completed", "sent", "paid", "အောင်မြင်"]):
        return "success"

    return "unknown"


# ================= SHEET =================

def send_to_sheet(user_id, amount, bank, status, image_url):
    data = {
        "user_id": user_id,
        "amount": amount,
        "bank": bank,
        "status": status,
        "image": image_url,
        "time": str(datetime.now())
    }
    try:
        res = requests.post(GOOGLE_SHEET_URL, json=data)
        print("SHEET:", res.status_code)
    except Exception as e:
        print("SHEET ERROR:", e)


# ================= BOT =================

@bot.message_handler(content_types=['photo'])
def photo(msg):
    uid = msg.chat.id

    try:
        file_id = msg.photo[-1].file_id
        file_info = bot.get_file(file_id)

        file = bot.download_file(file_info.file_path)
        image = Image.open(io.BytesIO(file))

        # 🔥 OCR 2 PASS
        text1 = pytesseract.image_to_string(image, lang='eng+my', config='--psm 6')
        text2 = pytesseract.image_to_string(image, lang='eng+my', config='--psm 11')

        text = text1 + "\n" + text2

        print("OCR:\n", text)

        bank = get_bank(text)
        amount = get_amount(text, bank)
        status = get_status(text)

        print("RESULT:", bank, amount)

        if bank != "unknown" and amount != "unknown":
            image_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}"
            send_to_sheet(uid, amount, bank, status, image_url)

        else:
            print("❌ NOT DETECTED")

    except Exception as e:
        print("ERROR:", e)


# ================= WEBHOOK =================

@app.route("/")
def home():
    return "Running"


@app.route("/webhook", methods=["POST"])
def webhook():
    print("Webhook HIT")
    update = telebot.types.Update.de_json(request.get_data().decode("utf-8"))
    bot.process_new_updates([update])
    return "OK"


# ================= RUN =================

if __name__ == "__main__":
    bot.delete_webhook()
    bot.set_webhook(url=f"{APP_URL}/webhook")

    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
