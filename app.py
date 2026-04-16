import asyncio
import os
import time
from flask import Flask, request
from telethon import TelegramClient, events
from telethon.tl.functions.messages import GetBotCallbackAnswerRequest
from threading import Thread
from queue import Queue
import requests

# ========= ENV =========
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
PAGE_ACCESS_TOKEN = os.getenv("FB_PAGE_TOKEN")
api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
bot_username = "mysudan1bot"

# ========= Queue =========
task_queue = Queue()

# ========= Telegram =========
tg_loop = asyncio.new_event_loop()
client = TelegramClient("session", api_id, api_hash, loop=tg_loop)

# ========= State =========
last_message = None
current_buttons = []
last_psid = None

user_mode = {}
user_state = {}

tg_ready = False

# ========= Facebook =========
def send_to_facebook(psid, text):
    url = f"https://graph.facebook.com/v17.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    try:
        requests.post(url, json={
            "recipient": {"id": psid},
            "message": {"text": text}
        })
    except Exception as e:
        print("FB error:", e)

# ========= MENU =========
MENU = {
    "main": {
        "title": "🏠 القائمة الرئيسية",
        "buttons": {
            "1": {"text": "📩 خدمات", "next": "services"},
            "2": {"text": "⚙️ إعدادات", "next": "settings"}
        }
    },
    "services": {
        "title": "📩 الخدمات",
        "buttons": {
            "1": {"text": "✏️ إرسال", "action": "send"},
            "2": {"text": "📨 آخر رسالة", "action": "last"},
            "3": {"text": "🔘 أزرار Telegram", "action": "buttons"},
            "0": {"text": "⬅️ رجوع", "next": "main"}
        }
    }
}

def build_menu(node):
    data = MENU[node]
    text = data["title"] + "\n\n"
    for k, v in data["buttons"].items():
        text += f"{k} - {v['text']}\n"
    return text

def handle_menu(psid, choice):
    current = user_state.get(psid, "main")
    node = MENU[current]

    if choice not in node["buttons"]:
        return "error"

    btn = node["buttons"][choice]

    if "next" in btn:
        user_state[psid] = btn["next"]
        return btn["next"]

    if "action" in btn:
        return btn["action"]

# ========= Telegram events =========
@client.on(events.NewMessage)
@client.on(events.MessageEdited)
async def handle_message(event):
    global last_message, current_buttons

    try:
        sender = await event.get_sender()
        username = sender.username if sender.username else sender.first_name

        if username != bot_username:
            return

        last_message = event.message
        current_buttons = []

        msg = f"📩 {event.message.text}\n"

        if event.message.buttons:
            for row in event.message.buttons:
                for btn in row:
                    current_buttons.append(btn)

            msg += "\n🔘 الأزرار:\n"
            for i, btn in enumerate(current_buttons):
                msg += f"{i} - {btn.text}\n"

        if last_psid:
            send_to_facebook(last_psid, msg)

    except Exception as e:
        print("Telegram error:", e)

# ========= Telegram actions =========
async def send_text(text):
    await client.send_message(bot_username, text)

async def press_button(index):
    if not last_message or index >= len(current_buttons):
        if last_psid:
            send_to_facebook(last_psid, "❌ اختيار غير صحيح")
        return

    btn = current_buttons[index]

    await client(GetBotCallbackAnswerRequest(
        peer=last_message.to_id,
        msg_id=last_message.id,
        data=btn.data
    ))

    send_to_facebook(last_psid, f"✅ اخترت {btn.text}")

# ========= Worker =========
def queue_worker():
    while True:
        task = task_queue.get()
        try:
            if task["type"] == "text":
                asyncio.run_coroutine_threadsafe(
                    send_text(task["data"]), tg_loop
                )
            elif task["type"] == "button":
                asyncio.run_coroutine_threadsafe(
                    press_button(task["data"]), tg_loop
                )
        except Exception as e:
            print("Worker error:", e)

# ========= Flask =========
app = Flask(__name__)

@app.route("/webhook", methods=["GET"])
def verify():
    if request.args.get("hub.verify_token") == VERIFY_TOKEN:
        return request.args.get("hub.challenge"), 200
    return "Error", 403

@app.route("/webhook", methods=["POST"])
def webhook():
    global last_psid

    data = request.get_json()

    if data.get("object") == "page":
        for entry in data.get("entry", []):
            for msg in entry.get("messaging", []):

                if "message" in msg:
                    psid = msg["sender"]["id"]
                    text = msg["message"].get("text")

                    last_psid = psid

                    # أول دخول
                    if psid not in user_state:
                        user_state[psid] = "main"
                        send_to_facebook(psid, build_menu("main"))
                        return "OK", 200

                    mode = user_mode.get(psid)

                    # 🔥 إذا Telegram غير جاهز
                    if not tg_ready:
                        send_to_facebook(psid, "⏳ جاري تشغيل النظام... أعد الإرسال بعد ثواني")
                        return "OK", 200

                    # أوضاع
                    if mode == "send":
                        task_queue.put({"type": "text", "data": text})
                        user_mode[psid] = None
                        return "OK", 200

                    if mode == "buttons" and text.isdigit():
                        task_queue.put({"type": "button", "data": int(text)})
                        user_mode[psid] = None
                        return "OK", 200

                    # menu
                    result = handle_menu(psid, text)

                    if result == "error":
                        send_to_facebook(psid, "❌ خيار غير صحيح")
                        return "OK", 200

                    if result in MENU:
                        send_to_facebook(psid, build_menu(result))

                    elif result == "send":
                        user_mode[psid] = "send"
                        send_to_facebook(psid, "✏️ ارسل النص")

                    elif result == "last":
                        if last_message:
                            send_to_facebook(psid, f"📨 {last_message.text}")
                        else:
                            send_to_facebook(psid, "🚫 لا توجد رسائل")

                    elif result == "buttons":
                        user_mode[psid] = "buttons"
                        send_to_facebook(psid, "🔢 اختر رقم الزر")

    return "OK", 200

# ========= Start =========
async def start():
    global tg_ready
    await client.start()
    tg_ready = True
    print("Telegram Ready")

if __name__ == "__main__":
    tg_loop.run_until_complete(start())

    Thread(target=queue_worker, daemon=True).start()

    Thread(target=lambda: app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", 5000)),
        debug=False
    ), daemon=True).start()

    tg_loop.run_forever()
