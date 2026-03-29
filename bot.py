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

print("TOKEN =", TOKEN)

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


def get_bank(text):
    t = text.lower()

    if any(x in t for x in ["kbz", "kpay", "k-pay"]):
        return "KBZ"

    if any(x in t for x in ["wave", "wav", "money"]):
        return "Wave"

    return "unknown"


def get_amount(text, bank):
    text = clean(text)

    # Wave
    if bank == "Wave":
        nums = re.findall(r"\d{3,}\.\d{2}", text)
        if nums:
            return max(nums, key=lambda x: float(x))

    # KBZ
    if bank == "KBZ":
        nums = re.findall(r"\d{4,7}", text)
        if nums:
            return max(nums, key=lambda x: int(x))

    # fallback
    nums = re.findall(r"\d{4,7}", text)
    if nums:
        return max(nums, key=lambda x: int(x))

    return "unknown"


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
        print("SHEET STATUS:", res.status_code)
    except Exception as e:
        print("SHEET ERROR:", e)


# ================= BOT =================

@bot.message_handler(content_types=['photo'])
def photo(msg):
    print("📸 PHOTO RECEIVED")

    uid = msg.chat.id

    try:
        file_id = msg.photo[-1].file_id
        file_info = bot.get_file(file_id)

        file = bot.download_file(file_info.file_path)
        image = Image.open(io.BytesIO(file))

        # 🔥 OCR
        text = pytesseract.image_to_string(image, lang='eng+my')

        print("========== OCR RAW ==========")
        print(text)
        print("=============================")

        bank = get_bank(text)
        amount = get_amount(text, bank)

        print("BANK =", bank)
        print("AMOUNT =", amount)

        image_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}"

        # 🔥 ALWAYS SEND (debug)
        send_to_sheet(uid, amount, bank, "test", image_url)

    except Exception as e:
        print("ERROR:", e)


# ================= WEBHOOK =================

@app.route("/", methods=["GET"])
def home():
    return "Running"


@app.route("/webhook", methods=["POST"])
def webhook():
    print("🔥 Webhook HIT")
    update = telebot.types.Update.de_json(request.get_data().decode("utf-8"))
    bot.process_new_updates([update])
    return "OK"


# ================= RUN =================

if __name__ == "__main__":
    bot.delete_webhook()

    bot.set_webhook(
        url="https://beautiful-delight-production-79cf.up.railway.app/webhook"
    )

    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
