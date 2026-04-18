import asyncio
from flask import Flask, request
from telethon import TelegramClient, events
from telethon.tl.functions.messages import GetBotCallbackAnswerRequest
from threading import Thread
import requests
import os
#from dotenv import load_dotenv

# ======================
# ENV
# =====================

api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
verify_token = os.getenv("VERIFY_TOKEN")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
bot_username = "mysudan1bot"

# ======================
# Telegram
# ======================
tg_loop = asyncio.new_event_loop()
asyncio.set_event_loop(tg_loop)

client = TelegramClient("session3", api_id, api_hash, loop=tg_loop)

# ======================
# الحالة
# ======================
last_message = None
current_buttons = []
last_psid = None
user_mode = {}

# ======================
# Facebook Send
# ======================
def send_to_facebook(text):
    if not last_psid:
        print("❌ لا يوجد مستخدم")
        return

    url = f"https://graph.facebook.com/v17.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"

    requests.post(url, json={
        "recipient": {"id": last_psid},
        "message": {"text": str(text)}
    })

# ======================
# Telegram Events
# ======================
@client.on(events.NewMessage)
@client.on(events.MessageEdited)
async def handle_message(event):
    global last_message, current_buttons

    sender = await event.get_sender()

    # ✅ الحل الصحيح
    if not getattr(sender, "username", None) or sender.username.lower() != bot_username.lower():
        return

    last_message = event.message
    current_buttons = []

    text = event.message.text or ""
    msg = f"📩 من Telegram:\n{text}\n"

    if event.message.buttons:
        buttons_temp = []

        for row in event.message.buttons:
            for btn in row:
                buttons_temp.append(btn)

        buttons_temp.sort(key=lambda b: b.text.lower())
        current_buttons = buttons_temp

        msg += "\n🔘 الأزرار:\n"
        for i, btn in enumerate(current_buttons):
            msg += f"{i} - {btn.text}\n"

    send_to_facebook(msg)

# ======================
# Telegram Functions
# ======================
async def send_text_to_tg(text):
    await client.send_message(bot_username, text)

async def show_last_message():
    if not last_message:
        send_to_facebook("❌ لا توجد رسالة")
        return

    msg = f"📩 آخر رسالة:\n{last_message.text or ''}\n"

    if current_buttons:
        msg += "\n🔘 الأزرار:\n"
        for i, btn in enumerate(current_buttons):
            msg += f"{i} - {btn.text}\n"

    send_to_facebook(msg)

async def press_button_by_index(index):
    if index >= len(current_buttons):
        send_to_facebook("❌ رقم غير صحيح")
        return

    btn = current_buttons[index]

    await client(GetBotCallbackAnswerRequest(
        peer=last_message.to_id,
        msg_id=last_message.id,
        data=btn.data
    ))

    send_to_facebook(f"✅ ضغطت: {btn.text}")

async def press_button_by_text(text):
    btn = next((b for b in current_buttons if b.text.lower() == text.lower()), None)

    if not btn:
        send_to_facebook("❌ الزر غير موجود")
        return

    await client(GetBotCallbackAnswerRequest(
        peer=last_message.to_id,
        msg_id=last_message.id,
        data=btn.data
    ))

    send_to_facebook(f"✅ ضغطت: {btn.text}")

# ======================
# Flask
# ======================
app = Flask(__name__)

@app.route("/webhook", methods=["GET"])
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == verify_token:
        return challenge, 200
    return "Verification failed", 403

@app.route("/webhook", methods=["POST"])
def webhook():
    global last_psid

    data = request.get_json()

    if data.get("object") == "page":
        for entry in data["entry"]:
            for msg in entry["messaging"]:

                if "message" in msg:
                    sender_id = msg["sender"]["id"]
                    text = msg["message"].get("text")

                    last_psid = sender_id
                    mode = user_mode.get(sender_id)

                    print("FB:", text)

                    if text == "1":
                        user_mode[sender_id] = "send_text"
                        send_to_facebook("✏️ ارسل النص")

                    elif text == "2":
                        asyncio.run_coroutine_threadsafe(show_last_message(), tg_loop)

                    elif text == "3":
                        user_mode[sender_id] = "choose_button"
                        send_to_facebook("🔢 ارسل رقم أو اسم الزر")

                    elif text == "4":
                        user_mode[sender_id] = None
                        send_to_facebook("👋 خروج")

                    elif mode == "send_text":
                        asyncio.run_coroutine_threadsafe(
                            send_text_to_tg(text),
                            tg_loop
                        )
                        send_to_facebook("✅ تم الإرسال")

                    elif mode == "choose_button":
                        if text and text.isdigit():
                            asyncio.run_coroutine_threadsafe(
                                press_button_by_index(int(text)),
                                tg_loop
                            )
                        elif text:
                            asyncio.run_coroutine_threadsafe(
                                press_button_by_text(text),
                                tg_loop
                            )

    return "OK", 200

# ======================
# تشغيل
# ======================
async def start():
    await client.start()
    print("✅ Telegram Ready")

if __name__ == "__main__":
    tg_loop.run_until_complete(start())

    # ✅ مهم لـ Render
    port = int(os.environ.get("PORT", 10000))

    Thread(
        target=lambda: app.run(host="0.0.0.0", port=port),
        daemon=True
    ).start()

    tg_loop.run_forever()
