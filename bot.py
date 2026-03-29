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

# 👉 Google Sheet URL
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


# 🔥 Myanmar Number → English
def mm_to_en_digits(text):
    mm_digits = "၀၁၂၃၄၅၆၇၈၉"
    en_digits = "0123456789"

    for m, e in zip(mm_digits, en_digits):
        text = text.replace(m, e)

    return text


# 🧠 SLIP CHECK
def is_valid_slip(text):
    t = text.lower()

    keywords = [
        "kbz", "pay", "bank",
        "wave", "money",
        "transfer", "success",
        "mmk", "ks", "ကျပ်"
    ]

    score = sum([1 for k in keywords if k in t])

    print("SLIP SCORE:", score)

    return score >= 2


# 🧠 AMOUNT EXTRACT (FINAL 🔥)
def extract_amount(text):
    # 👉 convert Myanmar numbers
    text = mm_to_en_digits(text)

    t = text.lower().replace("o", "0")
    t_clean = t.replace(",", "").replace(" ", "")

    # ✅ STEP 1: Ks / MMK / ကျပ်
    match = re.findall(r"(\d{3,})\s*(ks|mmk|ကျပ်)", t_clean)
    if match:
        return match[0][0]

    # ✅ STEP 2: line search
    for line in text.split("\n"):
        l = mm_to_en_digits(line.lower())

        if "ကျပ်" in l or "mmk" in l or "ks" in l:
            nums = re.findall(r"\d{3,}", l.replace(",", ""))
            if nums:
                return nums[0]

    # ✅ STEP 3: fallback
    nums = re.findall(r"\d{4,}", t_clean)

    # ❗ avoid ref no
    nums = [n for n in nums if 4 <= len(n) <= 7]

    if nums:
        return max(nums, key=lambda x: int(x))

    return "unknown"


# 🧠 BANK
def extract_bank(text):
    t = text.lower()

    if "kbz" in t:
        return "KBZ"
    elif "wave" in t or "money" in t or "ကျပ်" in t:
        return "Wave"
    elif "aya" in t:
        return "AYA"
    elif "cb" in t:
        return "CB"
    else:
        return "unknown"


# 🧠 STATUS
def extract_status(text):
    t = text.lower()

    if "success" in t or "completed" in t or "thank" in t:
        return "success"

    return "unknown"


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

    print(f"START | {user_id} | {source}")

    send_to_sheet(user_id, source, "start", "start", "", "", "")


# 💬 FIRST MESSAGE ONLY
@bot.message_handler(func=lambda m: True, content_types=['text'])
def handle_text(message):
    user_id = message.chat.id
    text = message.text
    source = user_source.get(user_id, "unknown")

    if not user_first_message_saved.get(user_id, False):
        print(f"FIRST MSG | {user_id} | {text}")
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

        file_path = file_info.file_path
        image_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"

        downloaded_file = bot.download_file(file_path)

        # 👉 preprocess
        image = Image.open(io.BytesIO(downloaded_file)).convert("L")
        image = image.filter(ImageFilter.SHARPEN)

        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(2)

        # 👉 OCR
        text = pytesseract.image_to_string(
            image,
            lang='eng',
            config='--psm 6'
        )

        print("OCR TEXT:\n", text)

        # 👉 slip check
        if not is_valid_slip(text):
            print("❌ NOT SLIP")
            return

        # 👉 extract
        amount = extract_amount(text)
        bank = extract_bank(text)
        status = extract_status(text)

        print("✅ RESULT:", amount, bank)

        # 👉 SAVE
        send_to_sheet(user_id, source, "deposit", image_url, amount, bank, status)

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
