import telebot
from flask import Flask
import threading
import os

TOKEN = os.environ.get("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running 🚀"

def run_bot():
    bot.infinity_polling()

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# run both safely
threading.Thread(target=run_bot).start()
run_web()
