import asyncio
from telethon import TelegramClient
api_id = 12345
api_hash = 'your_api_hash'
bot_username = "mysudan1bot"
client = TelegramClient('session', api_id , api_hash )

async def main():
    await client.start()
    user = "Aminabdalbdea"
    msg = "اشتغل"
    await client.send_message(user, msg)
    print("تم إرسال الرسالة!")

asyncio.run(main())
