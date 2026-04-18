import asyncio
from flask import Flask, request
from telethon import TelegramClient, events
from telethon.tl.functions.messages import GetBotCallbackAnswerRequest
from threading import Thread
import requests
import os

# ======================
# ENV
# ======================
api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
verify_token = os.getenv("VERIFY_TOKEN")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")

bot_username = "chatgpt"  # للإرسال فقط

# ======================
# Telegram Setup
# ======================
tg_loop = asyncio.new_event_loop()
asyncio.set_event_loop(tg_loop)

client = TelegramClient("session2", api_id, api_hash, loop=tg_loop)

# ======================
# الحالة
# ======================
last_messages = []  # آخر 3 رسائل
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
async def handle_new(event):
    global last_messages

    sender = await event.get_sender()

    # نأخذ فقط رسائل البوت
    if not sender.bot:
        return

    msg_obj = {
        "msg": event.message,
        "buttons": []
    }

    # استخراج الأزرار
    if event.message.buttons:
        buttons = []
        for row in event.message.buttons:
            for btn in row:
                buttons.append(btn)

        buttons.sort(key=lambda b: b.text.lower())
        msg_obj["buttons"] = buttons

    # حفظ الرسائل (حد أقصى 3)
    last_messages.append(msg_obj)
    if len(last_messages) > 3:
        last_messages.pop(0)

    # إرسال لفايسبوك
    text = event.message.text or ""
    msg = f"📩 من Telegram:\n{text}\n"

    if msg_obj["buttons"]:
        msg += "\n🔘 الأزرار:\n"
        for btn in msg_obj["buttons"]:
            msg += f"- {btn.text}\n"

    send_to_facebook(msg)

# تحديث الرسالة بدل إضافتها
@client.on(events.MessageEdited)
async def handle_edit(event):
    global last_messages

    sender = await event.get_sender()

    if not sender.bot:
        return

    if not last_messages:
        return

    msg_obj = {
        "msg": event.message,
        "buttons": []
    }

    if event.message.buttons:
        buttons = []
        for row in event.message.buttons:
            for btn in row:
                buttons.append(btn)

        buttons.sort(key=lambda b: b.text.lower())
        msg_obj["buttons"] = buttons

    last_messages[-1] = msg_obj

# ======================
# Telegram Functions
# ======================
async def send_text_to_tg(text):
    await client.send_message(bot_username, text)

async def show_last_messages():
    if not last_messages:
        send_to_facebook("❌ لا توجد رسائل")
        return

    msg = "📩 آخر 3 رسائل:\n\n"

    for i, item in enumerate(last_messages):
        m = item["msg"]
        msg += f"{i+1}- {m.text or ''}\n"

        if item["buttons"]:
            msg += "🔘 الأزرار:\n"
            for btn in item["buttons"]:
                msg += f"- {btn.text}\n"

        msg += "\n"

    send_to_facebook(msg)

# الضغط بالاسم
async def press_button_by_text(text):
    text = text.lower()

    for msg_obj in reversed(last_messages):
        for btn in msg_obj["buttons"]:
            if btn.text.lower() == text:
                await client(GetBotCallbackAnswerRequest(
                    peer=msg_obj["msg"].to_id,
                    msg_id=msg_obj["msg"].id,
                    data=btn.data
                ))

                send_to_facebook(f"✅ ضغطت: {btn.text}")
                return

    send_to_facebook("❌ الزر غير موجود")

# ======================
# Flask
# ======================
app = Flask(__name__)

@app.route("/")
def home():
    return "Server is running"

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
                        asyncio.run_coroutine_threadsafe(
                            show_last_messages(), tg_loop
                        )

                    elif text == "3":
                        user_mode[sender_id] = "choose_button"
                        send_to_facebook("🔘 اكتب اسم الزر")

                    elif text == "4":
                        user_mode[sender_id] = None
                        send_to_facebook("👋 خروج")

                    elif mode == "send_text":
                        asyncio.run_coroutine_threadsafe(
                            send_text_to_tg(text), tg_loop
                        )
                        send_to_facebook("✅ تم الإرسال")

                    elif mode == "choose_button":
                        if text:
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

    port = int(os.environ.get("PORT", 10000))

    Thread(
        target=lambda: app.run(host="0.0.0.0", port=port),
        daemon=True
    ).start()

    tg_loop.run_forever()
