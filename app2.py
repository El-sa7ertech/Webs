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

bot_username = "chatgpt"

# ======================
# Telegram Setup
# ======================
tg_loop = asyncio.new_event_loop()
asyncio.set_event_loop(tg_loop)

client = TelegramClient("session", api_id, api_hash, loop=tg_loop)

# ======================
# الحالة
# ======================
last_messages = []
last_psid = None
user_mode = {}

# ======================
# 🔥 Debug + Split
# ======================
def split_message(text, limit=1800):
    return [text[i:i+limit] for i in range(0, len(text), limit)]

def send_to_facebook(text):
    if not last_psid:
        print("❌ لا يوجد مستخدم")
        return

    print("\n================ FACEBOOK DEBUG ================")
    print("SEND LENGTH:", len(text))
    print("PSID:", last_psid)

    url = f"https://graph.facebook.com/v17.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"

    parts = split_message(text)

    for i, part in enumerate(parts):
        print(f"\n--- Sending part {i+1} ---")
        print("PART LENGTH:", len(part))
        print("PART SAMPLE:", part[:200])

        try:
            r = requests.post(url, json={
                "recipient": {"id": last_psid},
                "message": {"text": part}
            })

            print("Facebook Response:", r.status_code, r.text)

        except Exception as e:
            print("ERROR SENDING:", e)

# ======================
# Telegram Events
# ======================
@client.on(events.NewMessage)
async def handle_new(event):
    global last_messages

    sender = await event.get_sender()

    if not sender.bot:
        return

    # 🔥 استخراج النص بأكثر من طريقة (DEBUG)
    text1 = event.message.text
    text2 = event.message.message
    text3 = event.message.raw_text

    text = text2 or text1 or text3 or ""

    print("\n================ TELEGRAM DEBUG ================")
    print("TEXT:", text1)
    print("MESSAGE:", text2)
    print("RAW:", text3)
    print("FINAL LENGTH:", len(text))

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

    last_messages.append(msg_obj)
    if len(last_messages) > 3:
        last_messages.pop(0)

    msg = f"📩 من Telegram:\n{text}\n"

    if msg_obj["buttons"]:
        msg += "\n🔘 الأزرار:\n"
        for btn in msg_obj["buttons"]:
            msg += f"- {btn.text}\n"

    send_to_facebook(msg)

# ======================
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

# ======================
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
app = Flask(__name__)

@app.route("/")
def home():
    return "Server is running"

@app.route("/webhook", methods=["GET"])
def verify_webhook():
    if request.args.get("hub.verify_token") == verify_token:
        return request.args.get("hub.challenge"), 200
    return "error", 403

@app.route("/webhook", methods=["POST"])
def webhook():
    global last_psid

    data = request.get_json(force=True)

    if data.get("object") == "page":
        for entry in data.get("entry", []):
            for msg in entry.get("messaging", []):

                if "message" not in msg:
                    continue

                sender_id = msg.get("sender", {}).get("id")
                text = msg["message"].get("text")

                last_psid = sender_id
                mode = user_mode.get(sender_id)

                print("\n========== FACEBOOK INPUT ==========")
                print("TEXT:", text)

                if text == "1":
                    user_mode[sender_id] = "send_text"
                    send_to_facebook("✏️ ارسل النص")

                elif text == "2":
                    asyncio.run_coroutine_threadsafe(show_last_messages(), tg_loop)

                elif text == "3":
                    user_mode[sender_id] = "choose_button"
                    send_to_facebook("🔘 اكتب اسم الزر")

                elif text == "4":
                    user_mode[sender_id] = None
                    send_to_facebook("👋 خروج")

                elif mode == "send_text":
                    asyncio.run_coroutine_threadsafe(send_text_to_tg(text), tg_loop)
                    send_to_facebook("✅ تم الإرسال")

                elif mode == "choose_button":
                    asyncio.run_coroutine_threadsafe(press_button_by_text(text), tg_loop)

    return "OK", 200

# ======================
async def start():
    await client.start()
    print("✅ Telegram Ready")

if __name__ == "__main__":
    tg_loop.run_until_complete(start())

    port = int(os.environ.get("PORT", 10000))

    Thread(
        target=lambda: app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False),
        daemon=True
    ).start()

    tg_loop.run_forever()
