import telebot
from flask import Flask, request
import os
import requests
from datetime import datetime
import pytesseract
from PIL import Image
import io
import re

# ================= OCR =================
pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"

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

def clean_text(text):
    text = mm_to_en(text)

    # 🔥 OCR FIX (VERY IMPORTANT)
    text = text.replace("J", "2")   # Wave fix
    text = text.replace("O", "0")
    text = text.replace("o", "0")

    text = text.replace(",", "")
    return text

def join_numbers(text):
    matches = re.findall(r"\d{2,}\s+\d{2,}", text)
    return [m.replace(" ", "") for m in matches]

# ================= AMOUNT =================
def get_amount(image):
    width, height = image.size

    crops = [
        image.crop((0, 0, width, int(height * 0.4))),   # TOP
        image.crop((0, int(height * 0.4), width, int(height * 0.8)))  # MID
    ]

    all_numbers = []

    for crop in crops:
        text = pytesseract.image_to_string(
            crop,
            lang='eng+my',
            config='--psm 6'
        )

        print("OCR PART:\n", text)

        clean = clean_text(text)

        # decimal support
        nums = re.findall(r"\d{3,}(?:\.\d{2})?", clean)

        for n in nums:
            n = n.replace(".00", "")
            all_numbers.append(n)

        # join split numbers
        all_numbers.extend(join_numbers(clean))

    print("ALL NUMBERS:", all_numbers)

    valid = []

    for n in all_numbers:
        try:
            val = int(n)

            if val < 1000:
                continue

            if val > 10000000:
                continue

            valid.append(val)
        except:
            pass

    if valid:
        return str(max(valid))

    return "unknown"

# ================= BANK =================
def get_bank(text):
    t = text.lower()

    if "kbz" in t:
        return "KBZ"

    if "wave" in t or "အောင်မြင်" in t or "ကျပ်" in t:
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
        image = Image.open(io.BytesIO(file)).convert("L")

        # FULL TEXT
        full_text = pytesseract.image_to_string(
            image,
            lang='eng+my',
            config='--psm 6'
        )

        print("FULL OCR:\n", full_text)

        amount = get_amount(image)
        bank = get_bank(full_text)
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
