import os
import asyncio
import re
import random
import string
import logging
import json
from aiohttp import ClientSession
from aiohttp_sse_client import client as sse_client

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.client.default import DefaultBotProperties

BOT_TOKEN = os.getenv("BOT_TOKEN", "8615982333:AAEtzMXZXQIQZ_RemRvvntFWtS3LjU8tL98")
API_BASE = "https://api.mail.tm"
MERCURE_HUB = "https://mercure.mail.tm/.well-known/mercure"

logging.basicConfig(level=logging.INFO)

# HTML parse mode must on
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

user_sessions = {}
active_sse_tasks = {}

def random_string(length=7):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def extract_otp(text):
    if not text:
        return None
    matches = re.findall(r'\b\d{4,8}\b', text)
    return matches[0] if matches else None

# Button UI exact match kora
def get_main_keyboard(email):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"📋 {email}",
                    callback_data="copy_email"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Refresh",
                    callback_data="refresh"
                ),
                InlineKeyboardButton(
                    text="🔀 Change",
                    callback_data="change"
                )
            ]
        ]
    )

async def create_mail():
    username = f"usr_{random_string(8)}"
    password = f"Sec_{random_string(8)}!1"

    async with ClientSession() as session:
        async with session.get(f"{API_BASE}/domains") as res:
            if res.status != 200:
                return None
            domains = await res.json()
            domain = domains['hydra:member'][0]['domain']

        email = f"{username}@{domain}"
        payload = {"address": email, "password": password}

        async with session.post(f"{API_BASE}/accounts", json=payload) as res:
            if res.status not in (200, 201):
                return None
            acc_data = await res.json()
            account_id = acc_data.get('id')

        async with session.post(f"{API_BASE}/token", json=payload) as res:
            if res.status != 200:
                return None
            token_data = await res.json()
            token = token_data.get('token')

        return {
            "email": email,
            "token": token,
            "account_id": account_id
        }

async def fetch_message_detail(message_id, token):
    headers = {"Authorization": f"Bearer {token}"}
    async with ClientSession() as session:
        async with session.get(f"{API_BASE}/messages/{message_id}", headers=headers) as res:
            if res.status == 200:
                return await res.json()
    return None

async def delete_after_delay(chat_id, message_id, delay=60):
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass

async def sse_listener(user_id, account_id, token, email):
    url = f"{MERCURE_HUB}?topic=/accounts/{account_id}"
    try:
        async with sse_client.EventSource(url) as event_source:
            async for event in event_source:
                if not event.data:
                    continue
                data = json.loads(event.data)
                msg_id = data.get("id")
                if not msg_id:
                    continue

                detail = await fetch_message_detail(msg_id, token)
                if not detail:
                    continue

                subject = detail.get("subject", "")
                text_body = detail.get("text", "") or detail.get("intro", "")
                full_content = f"{subject}\n{text_body}".strip()

                otp = extract_otp(full_content) or "N/A"

                # 2nd photo er moto message format
                otp_msg_text = (
                    f"✉️ <b>Email:</b> <code>{email}</code>\n"
                    f"🔐 <b>OTP:</b> <code>{otp}</code>"
                )

                buttons = [
                    [
                        InlineKeyboardButton(
                            text=f"📋 🔑 {otp}",
                            callback_data=f"copy_otp:{otp}"
                        ),
                        InlineKeyboardButton(
                            text="📋 Copy Full SMS",
                            callback_data="copy_full"
                        )
                    ]
                ]

                sent_msg = await bot.send_message(
                    chat_id=user_id,
                    text=otp_msg_text,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
                )

                if user_id in user_sessions:
                    user_sessions[user_id]["last_sms"] = full_content

                asyncio.create_task(delete_after_delay(user_id, sent_msg.message_id, 60))

    except asyncio.CancelledError:
        pass
    except Exception as e:
        logging.error(f"SSE Error: {e}")

@dp.message(F.text == "/start")
async def start_cmd(message: Message):
    user_id = message.from_user.id

    if user_id in active_sse_tasks:
        active_sse_tasks[user_id].cancel()

    account = await create_mail()
    if not account:
        await message.answer("⚠️ Connection Error. Please retry /start")
        return

    user_sessions[user_id] = account

    task = asyncio.create_task(
        sse_listener(user_id, account["account_id"], account["token"], account["email"])
    )
    active_sse_tasks[user_id] = task

    # Exact text formatting
    await message.answer(
        "নিচের বাটনে ক্লিক করলেই copy হয়ে যাবে 👇",
        reply_markup=get_main_keyboard(account["email"])
    )

@dp.callback_query(F.data == "change")
async def on_change(call: CallbackQuery):
    user_id = call.from_user.id
    await call.answer("⚡ Generating...")

    if user_id in active_sse_tasks:
        active_sse_tasks[user_id].cancel()

    account = await create_mail()
    if not account:
        await call.answer("Error creating email!", show_alert=True)
        return

    user_sessions[user_id] = account

    task = asyncio.create_task(
        sse_listener(user_id, account["account_id"], account["token"], account["email"])
    )
    active_sse_tasks[user_id] = task

    await call.message.edit_text(
        "নিচের বাটনে ক্লিক করলেই copy হয়ে যাবে 👇",
        reply_markup=get_main_keyboard(account["email"])
    )

@dp.callback_query(F.data == "refresh")
async def on_refresh(call: CallbackQuery):
    await call.answer("🔄 Inbox listening active!", show_alert=False)

@dp.callback_query(F.data == "copy_email")
async def on_copy_email(call: CallbackQuery):
    user_id = call.from_user.id
    email = user_sessions.get(user_id, {}).get("email", "")
    await call.answer(f"{email}", show_alert=False)

@dp.callback_query(F.data.startswith("copy_otp:"))
async def on_copy_otp(call: CallbackQuery):
    otp = call.data.split(":")[1]
    await call.answer(f"Copied: {otp}", show_alert=False)

@dp.callback_query(F.data == "copy_full")
async def on_copy_full(call: CallbackQuery):
    user_id = call.from_user.id
    last_sms = user_sessions.get(user_id, {}).get("last_sms", "No text found")
    await call.answer(last_sms[:180], show_alert=True)

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
