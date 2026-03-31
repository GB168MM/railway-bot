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
WEBHOOK_URL = f"https://beautiful-delight-production-79cf.up.railway.app/{TOKEN}"

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"

GOOGLE_SHEET_URL = "https://script.google.com/macros/s/AKfycbxnchGPWar1Ktl8IWa7xVq8FxsskDL9WmRRb3eANP5UnQvqKU_hPebnTfPo0R5Z5dDnzw/exec"

user_source = {}
first_msg_saved = {}

# ================= GOOGLE SHEETS =================
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

    print("SEND:", data)

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

def clean_text(text):
    text = mm_to_en(text)
    text = text.replace(",", "")
    text = text.replace("O", "0").replace("o", "0")
    return text

# ================= BANK DETECT =================
def detect_bank(text):
    t = text.lower()
    if "kbz" in t or "kpay" in t:
        return "KBZ"
    if "wave" in t or "ကျပ်" in text:
        return "Wave"
    return "unknown"

# ================= AMOUNT =================
def extract_amount(text):
    text = clean_text(text)

    # ကျပ် pattern
    matches = re.findall(r"(\d{4,6})\s*ကျပ်", text)
    if matches:
        return matches[-1]

    # ks pattern
    matches = re.findall(r"(\d{4,6})\s*ks", text.lower())
    if matches:
        return matches[-1]

    # fallback numbers
    nums = re.findall(r"\d{4,6}", text)
    nums = [int(n) for n in nums if 1000 <= int(n) <= 100000]

    if nums:
        nums.sort()
        return str(nums[len(nums)//2])

    return "0"

# ================= STATUS =================
def get_status(text):
    t = text.lower()
    if "success" in t or "completed" in t or "အောင်မြင်" in t:
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

    send_to_sheet(uid, source, "start", "start", "0", "", "")

# ================= TEXT =================
@bot.message_handler(content_types=['text'])
def text_handler(msg):
    uid = msg.chat.id
    source = user_source.get(uid, "unknown")

    if not first_msg_saved.get(uid, False):
        send_to_sheet(uid, source, "first_message", msg.text, "0", "", "")
        first_msg_saved[uid] = True

# ================= IMAGE =================
@bot.message_handler(content_types=['photo', 'document'])
def image_handler(msg):
    print("IMAGE RECEIVED")

    uid = msg.chat.id
    source = user_source.get(uid, "unknown")

    try:
        if msg.content_type == 'photo':
            file_id = msg.photo[-1].file_id
        else:
            file_id = msg.document.file_id

        file_info = bot.get_file(file_id)
        file_path = file_info.file_path

        file = bot.download_file(file_path)
        image = Image.open(io.BytesIO(file)).convert("RGB")

        text = pytesseract.image_to_string(image, lang='eng+my', config='--psm 6')
        print("OCR:", text)

        bank = detect_bank(text)
        amount = extract_amount(text)
        status = get_status(text)

        image_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"

        print("FINAL:", amount, bank, status)

        send_to_sheet(uid, source, "deposit", image_url, amount, bank, status)

    except Exception as e:
        print("IMAGE ERROR:", e)

# ================= WEBHOOK =================
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = telebot.types.Update.de_json(request.get_data().decode("utf-8"))
    bot.process_new_updates([update])
    return "OK"

@app.route("/")
def home():
    return "BOT RUNNING"

# ================= RUN =================
if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
