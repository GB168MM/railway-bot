import telebot
from flask import Flask, request
import os
import requests
from datetime import datetime
import pytesseract
from PIL import Image
import io
import re

# ================= OCR CONFIG =================
pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"

# 🔥 IMPORTANT (Myanmar OCR fix)
os.environ["TESSDATA_PREFIX"] = "/usr/share/tesseract-ocr/4.00/tessdata"

# ================= BOT =================
TOKEN = os.environ.get("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)

app = Flask(__name__)

user_source = {}
first_msg_saved = {}

GOOGLE_SHEET_URL = "https://script.google.com/macros/s/AKfycbxnchGPWar1Ktl8IWa7xVq8FxsskDL9WmRRb3eANP5UnQvqKU_hPebnTfPo0R5Z5dDnzw/exec"


# ================= SHEET =================
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
        print("SHEET:", res.status_code)
    except Exception as e:
        print("SHEET ERROR:", e)


# ================= UTIL =================
def mm_to_en(text):
    mm = "၀၁၂၃၄၅၆၇၈၉"
    en = "0123456789"
    for m, e in zip(mm, en):
        text = text.replace(m, e)
    return text


# ================= SLIP CHECK =================
def is_slip(text):
    t = text.lower()

    if "kbz" in t:
        return True

    # 🔥 Myanmar Wave detect
    if "ကျပ်" in text:
        return True

    return False


# ================= AMOUNT =================
def get_amount(text):
    text = mm_to_en(text)
    t = text.replace(",", "")

    # 🔥 Myanmar Wave
    match = re.findall(r"(\d{3,})\s*ကျပ်", t)
    if match:
        return match[0]

    # decimal fallback
    nums = re.findall(r"\d{3,}\.\d{2}", t)
    if nums:
        return max(nums, key=lambda x: float(x))

    # general fallback
    nums = re.findall(r"\d{4,7}", t)
    if nums:
        return max(nums, key=lambda x: int(x))

    return "unknown"


# ================= BANK =================
def get_bank(text):
    t = text.lower()

    if "kbz" in t:
        return "KBZ"

    if "ကျပ်" in text:
        return "Wave"

    return "unknown"


# ================= STATUS =================
def get_status(text):
    t = text.lower()
    if any(x in t for x in ["success", "completed", "thank", "အောင်မြင်"]):
        return "success"
    return "unknown"


# ================= START =================
@bot.message_handler(commands=['start'])
def start(msg):
    print("START WORKED")

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
    print("TEXT WORKED")

    uid = msg.chat.id
    source = user_source.get(uid, "unknown")

    if not first_msg_saved.get(uid, False):
        send_to_sheet(uid, source, "first_message", msg.text, "", "", "")
        first_msg_saved[uid] = True


# ================= PHOTO =================
@bot.message_handler(content_types=['photo'])
def photo(msg):
    print("📸 PHOTO RECEIVED")

    uid = msg.chat.id
    source = user_source.get(uid, "unknown")

    try:
        file_id = msg.photo[-1].file_id
        file_info = bot.get_file(file_id)

        file_path = file_info.file_path
        image_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"

        file = bot.download_file(file_path)
        image = Image.open(io.BytesIO(file))

        # 🔥 DEBUG language check
        print("LANGS:", pytesseract.get_languages(config=''))

        # 🔥 OCR (Myanmar + English)
        text = pytesseract.image_to_string(
            image,
            lang='eng+my',
            config='--psm 6'
        )

        print("========== OCR ==========")
        print(text)
        print("=========================")

        if not is_slip(text):
            print("❌ NOT SLIP")
            return

        amount = get_amount(text)
        bank = get_bank(text)
        status = get_status(text)

        print("RESULT:", amount, bank)

        send_to_sheet(uid, source, "deposit", image_url, amount, bank, status)

    except Exception as e:
        print("ERROR:", e)


# ================= WEBHOOK =================
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    print("🔥 Webhook HIT")
    update = telebot.types.Update.de_json(request.get_data().decode("utf-8"))
    bot.process_new_updates([update])
    return "OK"


@app.route("/")
def home():
    return "Running"


# ================= RUN =================
if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"https://railway-bot-production-e57e.up.railway.app/{TOKEN}")

    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
