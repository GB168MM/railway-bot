import telebot
from flask import Flask, request
import os
import requests
from datetime import datetime
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter
import io
import re

# 👉 OCR path
pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"

TOKEN = os.environ.get("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)

app = Flask(__name__)

user_source = {}
user_first_message_saved = {}

# 👉 Google Sheets URL
GOOGLE_SHEET_URL = "https://script.google.com/macros/s/AKfycbxnchGPWar1Ktl8IWa7xVq8FxsskDL9WmRRb3eANP5UnQvqKU_hPebnTfPo0R5Z5dDnzw/exec"


# 🚀 SEND TO SHEET
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


# 🧠 SLIP DETECTION
def is_valid_slip(text):
    t = text.lower()

    if "kbz" in t and ("pay" in t or "bank" in t):
        return True

    keywords = ["ks", "mmk", "kbz", "wave", "aya", "success", "thank"]
    score = sum([1 for k in keywords if k in t])

    return score >= 2


# 🧠 FINAL AMOUNT EXTRACT (ULTIMATE 🔥)
def extract_slip_data(text):
    t = text.lower()

    # 👉 OCR fix (O → 0)
    t = t.replace("o", "0")

    # 👉 remove commas & spaces
    t_clean = t.replace(",", "").replace(" ", "")

    amount = "unknown"

    # 🎯 STEP 1: amount with currency
    match = re.findall(r"(\d{3,})(?:\.?\d*)\s*(ks|mmk)", t_clean)
    if match:
        amount = match[0][0]

    # 🎯 STEP 2: search lines
    if amount == "unknown":
        for line in text.split("\n"):
            l = line.lower().replace("o", "0")
            if "ks" in l or "amount" in l:
                nums = re.findall(r"\d{3,}", l.replace(",", ""))
                if nums:
                    amount = nums[0]
                    break

    # 🎯 STEP 3: fallback safe numbers
    if amount == "unknown":
        nums = re.findall(r"\d{4,}", t_clean)

        # 👉 filter (avoid ref no / phone)
        filtered = [n for n in nums if 4 <= len(n) <= 7]

        if filtered:
            amount = max(filtered, key=lambda x: int(x))

    # 👉 bank detect
    if "kbz" in t:
        bank = "KBZ"
    elif "wave" in t:
        bank = "Wave"
    elif "aya" in t:
        bank = "AYA"
    elif "cb" in t:
        bank = "CB"
    elif "uab" in t:
        bank = "UAB"
    else:
        bank = "unknown"

    # 👉 status
    if "thank" in t or "success" in t or "completed" in t:
        status = "success"
    else:
        status = "unknown"

    print("CLEAN TEXT:", t_clean)
    print("FINAL AMOUNT:", amount)
    print("BANK:", bank)

    return amount, bank, status


# 🚀 START
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.chat.id
    text = message.text

    source = "unknown"
    if len(text.split()) > 1:
        source = text.split()[1]

    user_source[user_id] = source
    user_first_message_saved[user_id] = False

    send_to_sheet(user_id, source, "start", "start", "", "", "")


# 💬 FIRST MESSAGE ONLY
@bot.message_handler(func=lambda m: True, content_types=['text'])
def handle_text(message):
    user_id = message.chat.id
    text = message.text
    source = user_source.get(user_id, "unknown")

    if not user_first_message_saved.get(user_id, False):
        send_to_sheet(user_id, source, "first_message", text, "", "", "")
        user_first_message_saved[user_id] = True


# 📸 PHOTO HANDLER
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    user_id = message.chat.id
    source = user_source.get(user_id, "unknown")

    try:
        print("PHOTO RECEIVED")

        photo = message.photo[-1].file_id
        file_info = bot.get_file(photo)
        downloaded_file = bot.download_file(file_info.file_path)

        # 👉 preprocess
        image = Image.open(io.BytesIO(downloaded_file)).convert("L")
        image = image.filter(ImageFilter.SHARPEN)

        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(2)

        # 👉 OCR (focus numbers + ks)
        text = pytesseract.image_to_string(
            image,
            lang='eng',
            config='--psm 6 -c tessedit_char_whitelist=0123456789.Ksks'
        )

        print("OCR TEXT:\n", text)

        if is_valid_slip(text):
            amount, bank, status = extract_slip_data(text)

            file_path = file_info.file_path
            image_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"

            send_to_sheet(user_id, source, "deposit", image_url, amount, bank, status)
        else:
            print("IGNORE PHOTO")

    except Exception as e:
        print("PHOTO ERROR:", e)


# 🌐 WEBHOOK
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    json_str = request.get_data().decode("UTF-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "OK", 200


@app.route("/")
def home():
    return "Bot Running 🚀"


# 🚀 RUN
if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(
        url=f"https://railway-bot-production-e57e.up.railway.app/{TOKEN}"
    )
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
