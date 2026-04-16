import asyncio
from flask import Flask, request
from telethon import TelegramClient, events
from telethon.tl.functions.messages import GetBotCallbackAnswerRequest
from threading import Thread
import requests
import os

# ======================
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")

api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")

bot_username = "mysudan1bot"

# ======================
tg_loop = asyncio.new_event_loop()
asyncio.set_event_loop(tg_loop)

client = TelegramClient("session", api_id, api_hash, loop=tg_loop)

# ======================
# لكل مستخدم بيانات منفصلة 🔥
# ======================
users = {}

def get_user(psid):
    if psid not in users:
        users[psid] = {
            "mode": None,
            "buttons": [],
            "last_message": None
        }
    return users[psid]

# ======================
def send_to_facebook(psid, text):
    url = f"https://graph.facebook.com/v17.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    requests.post(url, json={
        "recipient": {"id": psid},
        "message": {"text": text}
    })

# ======================
@client.on(events.NewMessage)
@client.on(events.MessageEdited)
async def handle_message(event):

    sender = await event.get_sender()
    username = sender.username or sender.first_name

    if username != bot_username:
        return

    psid = "fb_user"  # لا تعتمد على global

    user = get_user(psid)

    user["last_message"] = event.message
    user["buttons"] = []

    msg = f"📩 {event.message.text}\n"

    if event.message.buttons:
        temp = []

        for row in event.message.buttons:
            for btn in row:
                temp.append(btn)

        temp.sort(key=lambda b: b.text.lower())
        user["buttons"] = temp

        msg += "\n🔘 الأزرار:\n"
        for i, b in enumerate(temp):
            msg += f"{i} - {b.text}\n"

    send_to_facebook(psid, msg)

# ======================
async def send_text(text):
    await client.send_message(bot_username, text)

async def press_button(psid, index):
    user = get_user(psid)

    if index >= len(user["buttons"]):
        send_to_facebook(psid, "❌ خطأ")
        return

    btn = user["buttons"][index]

    await client(GetBotCallbackAnswerRequest(
        peer=user["last_message"].to_id,
        msg_id=user["last_message"].id,
        data=btn.data
    ))

    send_to_facebook(psid, f"✅ {btn.text}")

# ======================
app = Flask(__name__)

@app.route("/webhook", methods=["GET"])
def verify():
    if request.args.get("hub.verify_token") == VERIFY_TOKEN:
        return request.args.get("hub.challenge"), 200
    return "403", 403

@app.route("/webhook", methods=["POST"])
def webhook():

    data = request.get_json()

    if data.get("object") == "page":
        for entry in data["entry"]:
            for msg in entry["messaging"]:

                psid = msg["sender"]["id"]
                user = get_user(psid)

                text = msg["message"].get("text")

                # ===== أوامر =====
                if text == "1":
                    user["mode"] = "send"
                    send_to_facebook(psid, "✏️ ارسل النص")

                elif text == "2":
                    lm = user["last_message"]
                    if lm:
                        send_to_facebook(psid, lm.text)
                    else:
                        send_to_facebook(psid, "لا توجد رسالة")

                elif text == "3":
                    user["mode"] = "buttons"
                    send_to_facebook(psid, "🔢 اختر رقم")

                elif text == "4":
                    user["mode"] = None
                    send_to_facebook(psid, "👋 خروج")

                # ===== حالات =====
                elif user["mode"] == "send":
                    asyncio.run_coroutine_threadsafe(
                        send_text(text), tg_loop
                    )

                elif user["mode"] == "buttons":
                    if text.isdigit():
                        asyncio.run_coroutine_threadsafe(
                            press_button(psid, int(text)),
                            tg_loop
                        )

    return "OK", 200

# ======================
async def start():
    await client.start()
    print("Telegram Ready")

if __name__ == "__main__":
    tg_loop.run_until_complete(start())

    Thread(target=lambda: app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", 5000))
    ), daemon=True).start()

    tg_loop.run_forever()
