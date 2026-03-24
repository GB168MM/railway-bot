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

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_web).start()

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "Railway Bot Running 🚀")

bot.infinity_polling()
