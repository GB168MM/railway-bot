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

# 👉 Google Sheet URL (ပြောင်းထည့်)
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


# 🧠 SLIP CHECK
def is_valid_slip(text):
    text = text.lower()

    if "kbz" in text and ("pay" in text or "bank" in text):
        return True

    currency = ["ks", "mmk", "ကျပ်"]
    bank = ["kbz", "wave", "aya", "cb", "uab"]
    success = ["success", "completed", "thank"]

    score = sum([
        any(x in text for x in currency),
        any(x in text for x in bank),
        any(x in text for x in success),
        bool(re.search(r"\d+", text))
    ])

    print("SCORE:", score)

    return score >= 3


# 🧠 SMART AMOUNT EXTRACT 🔥
def extract_slip_data(text):
    text_lower = text.lower()
    text_clean = text.replace(",", "")

    amount = "unknown"

    # 👉 STEP 1: Ks / MMK pattern
    match = re.findall(r"(\d{3,}(?:\.\d+)?)\s*(ks|mmk)", text_lower)
    if match:
        amount = match[0][0]

    else:
        # 👉 STEP 2: amount line detect
        lines = text.split("\n")
        for line in lines:
            if "amount" in line.lower() or "total" in line.lower():
                nums = re.findall(r"\d{3,}", line.replace(",", ""))
                if nums:
                    amount = nums[0]
                    break

        # 👉 STEP 3: fallback (filter ref no)
        if amount == "unknown":
            nums = re.findall(r"\d{5,}", text_clean)

            # 👉 remove too long numbers (ref no / phone)
            filtered = [n for n in nums if len(n) <= 7]

            if filtered:
                amount = max(filtered, key=lambda x: int(x))

    # 👉 bank detect
    if "kbz" in text_lower:
        bank = "KBZ"
    elif "wave" in text_lower:
        bank = "Wave"
    elif "aya" in text_lower:
        bank = "AYA"
    elif "cb" in text_lower:
        bank = "CB"
    elif "uab" in text_lower:
        bank = "UAB"
    else:
        bank = "unknown"

    # 👉 status detect
    if "thank" in text_lower or "success" in text_lower or "completed" in text_lower:
        status = "success"
    else:
        status = "unknown"

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
        downloaded_file = bot.download_file(file_info.file_path)

        # 👉 preprocess
        image = Image.open(io.BytesIO(downloaded_file)).convert("L")
        image = image.filter(ImageFilter.SHARPEN)

        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(2)

        # 👉 OCR
        text = pytesseract.image_to_string(image, lang='eng', config='--psm 6')

        print("OCR TEXT:\n", text)

        if is_valid_slip(text):
            amount, bank, status = extract_slip_data(text)

            file_path = file_info.file_path
            image_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"

            print(f"VALID SLIP | {amount} | {bank}")

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
