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
    text = text.replace("O", "0")
    text = text.replace("o", "0")
    text = text.replace(",", "")
    return text

# ================= BANK =================
def detect_bank(text):
    t = text.lower()

    if "kbz" in t:
        return "KBZ"

    if "wave" in t or "ကျပ်" in text:
        return "Wave"

    return "unknown"

# ================= KBZ =================
def extract_kbz_amount(text):
    text = clean_text(text)

    nums = re.findall(r"\d{4,}", text)

    valid = []
    for n in nums:
        val = int(n)
        if 1000 <= val <= 10000000:
            valid.append(val)

    if valid:
        return str(max(valid))

    return "unknown"

# ================= WAVE (STRONG FIX) =================
def extract_wave_amount(text):
    text = clean_text(text)

    print("CLEAN TEXT:", text)

    # ✅ PRIORITY 1 → number + ကျပ်
    matches = re.findall(r"(\d{4,})\s*ကျပ်", text)
    if matches:
        print("KYAT MATCH:", matches)
        return matches[-1]

    # ✅ PRIORITY 2 → exact 5 digit (15000 type)
    matches = re.findall(r"\b\d{5}\b", text)
    if matches:
        print("5 DIGIT MATCH:", matches)
        return matches[0]

    # ✅ PRIORITY 3 → all numbers filter
    nums = re.findall(r"\d{4,}", text)
    nums = [int(n) for n in nums if 1000 <= int(n) <= 1000000]

    if nums:
        print("FALLBACK:", nums)
        return str(max(nums))

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

        # OCR
        text = pytesseract.image_to_string(image, lang='eng+my')
        print("RAW OCR:", text)

        bank = detect_bank(text)

        if bank == "KBZ":
            amount = extract_kbz_amount(text)
        elif bank == "Wave":
            amount = extract_wave_amount(text)
        else:
            amount = "unknown"

        status = get_status(text)

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
        url=f"https://beautiful-delight-production-79cf.up.railway.app/{TOKEN}"
    )
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
