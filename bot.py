import os
import requests
from flask import Flask, request
from PIL import Image
import easyocr
import re
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ================== CONFIG ==================
TOKEN = os.getenv("BOT_TOKEN")
SHEET_NAME = "Sheet1"

# ================== GOOGLE SHEETS ==================
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)
sheet = client.open(SHEET_NAME).sheet1

# ================== OCR ==================
reader = easyocr.Reader(['en', 'my'])

# ================== FLASK ==================
app = Flask(__name__)

# ================== FUNCTIONS ==================

def extract_amount(text):
    # Myanmar numbers → English
    mm_to_en = str.maketrans("၀၁၂၃၄၅၆၇၈၉", "0123456789")
    text = text.translate(mm_to_en)

    # remove commas
    text = text.replace(",", "")

    numbers = re.findall(r'\d{4,7}', text)

    if not numbers:
        return "unknown"

    # take smallest (prevent 29000 error)
    return min(numbers, key=int)

def get_file_path(file_id):
    url = f"https://api.telegram.org/bot{TOKEN}/getFile?file_id={file_id}"
    res = requests.get(url).json()
    return res["result"]["file_path"]

def download_image(file_path):
    url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path}"
    img = requests.get(url).content
    with open("image.jpg", "wb") as f:
        f.write(img)
    return "image.jpg"

def process_image(path):
    result = reader.readtext(path, detail=0)
    text = " ".join(result)
    return text

def save_to_sheets(user, amount):
    sheet.append_row([user, amount])

# ================== WEBHOOK ==================
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    data = request.json

    try:
        if "message" in data:
            msg = data["message"]

            user = msg["from"]["first_name"]

            if "photo" in msg:
                file_id = msg["photo"][-1]["file_id"]

                file_path = get_file_path(file_id)
                img_path = download_image(file_path)

                text = process_image(img_path)
                amount = extract_amount(text)

                save_to_sheets(user, amount)

                print("USER:", user)
                print("TEXT:", text)
                print("AMOUNT:", amount)

        return "OK", 200

    except Exception as e:
        print("ERROR:", e)
        return "ERROR", 500

# ================== ROOT ==================
@app.route("/")
def home():
    return "BOT IS RUNNING"

# ================== RUN ==================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
