import asyncio
from flask import Flask, request
from telethon import TelegramClient
from threading import Thread
from queue import Queue
import os

# ========= ENV =========
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")

api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")

bot_username = "mysudan1bot"

# ========= Queue =========
q = Queue()

# ========= Telegram =========
loop = asyncio.new_event_loop()
client = TelegramClient("session", api_id, api_hash, loop=loop)

# ========= Telegram send =========
async def send_to_tg(text):
    await client.send_message(bot_username, text)

def worker():
    while True:
        msg = q.get()
        asyncio.run_coroutine_threadsafe(send_to_tg(msg), loop)

# ========= Flask =========
app = Flask(__name__)

@app.route("/webhook", methods=["GET"])
def verify():
    if request.args.get("hub.verify_token") == VERIFY_TOKEN:
        return request.args.get("hub.challenge"), 200
    return "403", 403

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()

    print("📩 FB RAW:", data)  # 🔥 مهم للتأكد

    if data.get("object") == "page":
        for entry in data.get("entry", []):
            for event in entry.get("messaging", []):

                msg = event.get("message", {})
                text = msg.get("text")

                if text:
                    print("➡️ QUEUE:", text)
                    q.put(text)

    return "OK", 200

# ========= تشغيل =========
async def start():
    await client.start()
    print("✅ Telegram Ready")

if __name__ == "__main__":
    loop.run_until_complete(start())

    Thread(target=worker, daemon=True).start()
    Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000))), daemon=True).start()

    loop.run_forever()
