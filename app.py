import asyncio
from flask import Flask, request
from telethon import TelegramClient, events
from telethon.tl.functions.messages import GetBotCallbackAnswerRequest
from threading import Thread
import requests

# ======================
# إعداد Facebook
# ======================
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")

api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")

bot_username = "mysudan1bot"

tg_loop = asyncio.new_event_loop()
asyncio.set_event_loop(tg_loop)

client = TelegramClient("session", api_id, api_hash, loop=tg_loop)

# ======================
# الحالة
# ======================
last_message = None
current_buttons = []
last_psid = None
user_mode = {}

# ======================
# إرسال إلى Facebook
# ======================
def send_to_facebook(text):
    if not last_psid:
        print("❌ لا يوجد مستخدم")
        return

    url = f"https://graph.facebook.com/v17.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    data = {
        "recipient": {"id": last_psid},
        "message": {"text": text}
    }
    r = requests.post(url, json=data)
    print("FB:", r.json())

# ======================
# Telegram Events
# ======================
@client.on(events.NewMessage)
@client.on(events.MessageEdited)
async def handle_message(event):
    global last_message, current_buttons

    sender = await event.get_sender()
    username = sender.username if sender.username else sender.first_name

    if username != bot_username:
        return

    last_message = event.message
    current_buttons = []

    msg = f"📩 من Telegram:\n{event.message.text}\n"

    if event.message.buttons:
        buttons_temp = []

        # جمع الأزرار
        for row in event.message.buttons:
            for btn in row:
                buttons_temp.append(btn)

        # 🔥 ترتيب أبجدي
        buttons_temp.sort(key=lambda b: b.text.lower())

        current_buttons = buttons_temp

        msg += "\n🔘 الأزرار:\n"
        for i, btn in enumerate(current_buttons):
            msg += f"{i} - {btn.text}\n"

    send_to_facebook(msg)

# ======================
# وظائف Telegram
# ======================
async def send_text_to_tg(text):
    await client.send_message(bot_username, text)

async def show_last_message():
    if not last_message:
        send_to_facebook("❌ لا توجد رسالة")
        return

    msg = f"📩 آخر رسالة:\n{last_message.text}\n"

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

# تحقق Webhook
@app.route("/webhook", methods=["GET"])
def verify_webhook():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("✅ VERIFIED")
        return challenge, 200
    return "Verification failed", 403

# استقبال الرسائل
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

                    # ===== الأوامر =====
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

                    # ===== الحالات =====
                    elif mode == "send_text":
                        asyncio.run_coroutine_threadsafe(
                            send_text_to_tg(text),
                            tg_loop
                        )
                        send_to_facebook("✅ تم الإرسال")

                    elif mode == "choose_button":
                        if text.isdigit():
                            asyncio.run_coroutine_threadsafe(
                                press_button_by_index(int(text)),
                                tg_loop
                            )
                        else:
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

    Thread(target=lambda: app.run(host="0.0.0.0", port=5000), daemon=True).start()

    tg_loop.run_forever()
