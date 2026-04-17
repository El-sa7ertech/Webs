import asyncio
from flask import Flask, request, jsonify
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
# Note: we'll run this loop in a dedicated thread
client = TelegramClient("session", api_id, api_hash, loop=tg_loop)

# ======================
# الحالة
# ======================
last_messages = []  # each item: {"msg": event.message, "buttons": [Button, ...]}
last_psid = None
user_mode = {}

# ======================
# 🔥 Debug + Split
# ======================
def split_message(text, limit=1800):
    return [text[i:i+limit] for i in range(0, len(text), limit)]

def send_to_facebook(text):
    global last_psid
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

        buttons.sort(key=lambda b: (getattr(b, "text", "") or "").lower())
        msg_obj["buttons"] = buttons

    last_messages.append(msg_obj)
    if len(last_messages) > 3:
        last_messages.pop(0)

    msg = f"📩 من Telegram:\n{text}\n"

    if msg_obj["buttons"]:
        msg += "\n🔘 الأزرار:\n"
        for btn in msg_obj["buttons"]:
            # btn.text may be None for some button types
            btn_text = getattr(btn, "text", "") or ""
            msg += f"- {btn_text}\n"

    # إرسال للفايسبوك
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

        buttons.sort(key=lambda b: (getattr(b, "text", "") or "").lower())
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
        content = m.text or m.message or m.raw_text or ""
        msg += f"{i+1}- {content}\n"
        if item["buttons"]:
            msg += "   🔘 أزرار:\n"
            for b in item["buttons"]:
                bt = getattr(b, "text", "") or ""
                msg += f"     - {bt}\n"
        msg += "\n"

    send_to_facebook(msg)

# ======================
# Helper to schedule coroutine on tg_loop from other threads
def run_async(coro):
    try:
        tg_loop.call_soon_threadsafe(asyncio.ensure_future, coro)
    except Exception as e:
        print("Error scheduling coroutine:", e)

# ======================
# Handling button presses coming from Facebook
async def handle_fb_button_press(payload):
    global last_messages
    # Try to match the payload to a button text (case-insensitive)
    payload_norm = (payload or "").strip().lower()

    if not payload_norm:
        send_to_facebook("❌ لا يوجد حمل صالح")
        return

    # Search from newest to oldest for a matching button
    for item in reversed(last_messages):
        m = item["msg"]
        for btn in item["buttons"]:
            btn_text = (getattr(btn, "text", "") or "").strip()
            if not btn_text:
                continue
            if btn_text.lower() == payload_norm:
                # Found a match
                try:
                    # If the button carries callback data, use GetBotCallbackAnswerRequest
                    data = getattr(btn, "data", None)
                    url = getattr(btn, "url", None)
                    if data:
                        try:
                            input_peer = await client.get_input_entity(bot_username)
                            # Message id to use:
                            msg_id = m.id
                            print("Calling GetBotCallbackAnswerRequest:", msg_id, data)
                            res = await client(GetBotCallbackAnswerRequest(input_peer, msg_id, data))
                            # The result may not contain textual reply; we acknowledge
                            send_to_facebook(f"✅ تم الضغط على الزر: {btn_text}")
                            # If Telegram returns some alert/text inside res, try to display it
                            try:
                                reply_text = getattr(res, "message", None) or getattr(res, "alert", None) or None
                                if reply_text:
                                    send_to_facebook(f"رد من التلجرام:\n{reply_text}")
                            except Exception:
                                pass
                        except Exception as e:
                            print("Error sending callback request:", e)
                            # Fallback: send button text as message
                            await client.send_message(bot_username, btn_text)
                            send_to_facebook(f"✅ تم إرسال نص الزر كرسالة لأن الضغط المباشر فشل: {btn_text}")
                    elif url:
                        send_to_facebook(f"🔗 هذا زر رابط:\n{url}")
                    else:
                        # No data -> it's likely a regular button; just send its text
                        await client.send_message(bot_username, btn_text)
                        send_to_facebook(f"✅ تم إرسال نص الزر: {btn_text}")
                except Exception as ex:
                    print("Error handling button press:", ex)
                    send_to_facebook("❌ حدث خطأ أثناء الضغط على الزر")
                return

    # If we reach here, no matching button was found; send the payload as text to the bot
    try:
        await client.send_message(bot_username, payload)
        send_to_facebook(f"✅ تم إرسال: {payload}")
    except Exception as e:
        print("Error forwarding payload as text:", e)
        send_to_facebook("❌ فشل إرسال الرسالة إلى التلجرام")

# ======================
# Flask App (Facebook webhook)
app = Flask(__name__)

@app.route("/webhook", methods=["GET"])
def verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == verify_token:
        return challenge, 200
    return "Verification token mismatch", 403

@app.route("/webhook", methods=["POST"])
def webhook():
    global last_psid
    data = request.get_json()

    # Facebook may send batch entries
    try:
        entries = data.get("entry", [])
        for entry in entries:
            messaging = entry.get("messaging", [])
            for m in messaging:
                sender = m.get("sender", {}).get("id")
                if not sender:
                    continue
                last_psid = sender  # update global last_psid

                # Handle postback (button press from FB)
                if m.get("postback"):
                    payload = m["postback"].get("payload")
                    if payload:
                        run_async(handle_fb_button_press(payload))
                        continue

                # Handle quick_reply
                if m.get("message", {}).get("quick_reply"):
                    payload = m["message"]["quick_reply"].get("payload")
                    if payload:
                        run_async(handle_fb_button_press(payload))
                        continue

                # Handle text message
                if m.get("message") and "text" in m["message"]:
                    text = m["message"]["text"]
                    # A simple command to show last messages
                    if text.strip().lower() in ["/last", "last", "آخر", "آخر 3", "show last"]:
                        run_async(show_last_messages())
                    else:
                        run_async(send_text_to_tg(text))
    except Exception as e:
        print("Error handling webhook POST:", e)

    return jsonify({"status": "ok"}), 200

# ======================
# Start Telethon client in a separate thread
def start_telegram_client():
    asyncio.set_event_loop(tg_loop)
    try:
        tg_loop.run_until_complete(client.start())
        print("Telegram client started")
        tg_loop.run_until_complete(client.run_until_disconnected())
    except Exception as e:
        print("Telegram client error:", e)

tg_thread = Thread(target=start_telegram_client, daemon=True)
tg_thread.start()

# ======================
# Start Flask app (main thread)
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
