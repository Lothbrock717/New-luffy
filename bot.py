# (c) @TeleRoidGroup || @PredatorHackerzZ

import os
import asyncio
import traceback
from binascii import Error
from pyrogram import Client, enums, filters
from pyrogram.errors import UserNotParticipant, FloodWait, QueryIdInvalid
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from configs import Config
from handlers.database import db
from handlers.add_user_to_db import add_user_to_database
from handlers.send_file import send_media_and_reply
from handlers.helpers import b64_to_str, str_to_b64
from handlers.check_user_status import handle_user_status
from handlers.force_sub_handler import handle_force_sub, get_invite_link
from handlers.broadcast_handlers import main_broadcast_handler
from handlers.save_media import get_short

# Dictionary to store media lists
MediaList = {}

# Initialize Pyrogram Bot
Bot = Client(
    name=Config.BOT_USERNAME,
    in_memory=True,
    bot_token=Config.BOT_TOKEN,
    api_id=Config.API_ID,
    api_hash=Config.API_HASH
)

@Bot.on_message(filters.private)
async def user_status_handler(bot: Client, cmd: Message):
    await handle_user_status(bot, cmd)

@Bot.on_message(filters.command("start") & filters.private)
async def start(bot: Client, cmd: Message):
    if cmd.from_user.id in Config.BANNED_USERS:
        await cmd.reply_text("🚫 Sorry, you are banned.")
        return
    
    if Config.UPDATES_CHANNEL is not None:
        force_sub_status = await handle_force_sub(bot, cmd)
        if force_sub_status == 400:
            return

    usr_cmd = cmd.text.split("_", 1)[-1]
    if usr_cmd == "/start":
        await add_user_to_database(bot, cmd)
        await cmd.reply_text(
            Config.HOME_TEXT.format(cmd.from_user.first_name, cmd.from_user.id),
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔔 Updates", url="https://t.me/+Qi0jCnSsuFkwODA1"),
                 InlineKeyboardButton("💬 Support", url="https://t.me/+HXVFsszfxj81Yjdl")],
                [InlineKeyboardButton("🚪 Close", callback_data="closeMessage")]
            ])
        )
    else:
        try:
            try:
                file_id = int(b64_to_str(usr_cmd).split("_")[-1])
            except (Error, UnicodeDecodeError):
                file_id = int(usr_cmd.split("_")[-1])
            
            GetMessage = await bot.get_messages(chat_id=Config.DB_CHANNEL, message_ids=file_id)
            message_ids = GetMessage.text.split(" ") if GetMessage.text else [int(GetMessage.id)]
            
            _response_msg = await cmd.reply_text(f"📂 **Total Files:** `{len(message_ids)}`", quote=True)

            for msg_id in message_ids:
                await send_media_and_reply(bot, user_id=cmd.from_user.id, file_id=int(msg_id))
        except Exception as err:
            await cmd.reply_text(f"⚠️ **Error:** `{err}`")

@Bot.on_message((filters.document | filters.video | filters.audio | filters.photo) & ~filters.chat(Config.DB_CHANNEL))
async def main(bot: Client, message: Message):
    if message.chat.type == enums.ChatType.PRIVATE:
        await add_user_to_database(bot, message)

        if Config.UPDATES_CHANNEL:
            force_sub_status = await handle_force_sub(bot, message)
            if force_sub_status == 400:
                return

        if message.from_user.id in Config.BANNED_USERS:
            await message.reply_text(
                "🚫 Sorry, you are banned!\n\nContact [Support Group](https://t.me/+HXVFsszfxj81Yjdl)",
                disable_web_page_preview=True
            )
            return

        try:
            forwarded_msg = await message.forward(Config.DB_CHANNEL)
            file_er_id = str(forwarded_msg.id)
            share_link = f"https://telegram.me/{Config.BOT_USERNAME}?start=F2Botz_{str_to_b64(file_er_id)}"
            short_link = get_short(share_link)

            await message.reply_text(
                "**✅ Your file is stored!**\n\n"
                f"🔗 Permanent Link: <code>{short_link}</code>\n\n"
                "Click the link to retrieve your file!",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🌐 Original Link", url=share_link),
                     InlineKeyboardButton("🔗 Short Link", url=short_link)]
                ]),
                disable_web_page_preview=True, quote=True
            )
        except FloodWait as sl:
            await asyncio.sleep(sl.value)
            await bot.send_message(
                chat_id=int(Config.LOG_CHANNEL),
                text=f"🚨 **FloodWait Alert:** `{sl.value}s` wait triggered from `{message.chat.id}`",
                disable_web_page_preview=True
            )

@Bot.on_callback_query()
async def button(bot: Client, cmd: CallbackQuery):
    cb_data = cmd.data

    if cb_data == "closeMessage":
        await cmd.message.delete(True)

    elif cb_data.startswith("ban_user_"):
        user_id = cb_data.split("_", 2)[-1]
        if not cmd.from_user.id == Config.BOT_OWNER:
            await cmd.answer("🚫 You are not authorized!", show_alert=True)
            return
        try:
            await bot.kick_chat_member(chat_id=int(Config.UPDATES_CHANNEL), user_id=int(user_id))
            await cmd.answer("✅ User Banned!", show_alert=True)
        except Exception as e:
            await cmd.answer(f"⚠️ Cannot Ban!\n\nError: {e}", show_alert=True)

    elif cb_data == "getBatchLink":
        message_ids = MediaList.get(str(cmd.from_user.id), None)
        if not message_ids:
            await cmd.answer("⚠️ Batch List is Empty!", show_alert=True)
            return
        await cmd.message.edit("🔄 Generating batch link ...")
        await save_batch_media_in_channel(bot, cmd.message, message_ids)
        MediaList[str(cmd.from_user.id)] = []

    elif cb_data == "addToBatchTrue":
        if MediaList.get(str(cmd.from_user.id)) is None:
            MediaList[str(cmd.from_user.id)] = []
        file_id = cmd.message.reply_to_message.id
        MediaList[str(cmd.from_user.id)].append(file_id)
        await cmd.message.edit(
            "✅ File Added to Batch!\n\nClick below to get batch link.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📎 Get Batch Link", callback_data="getBatchLink")],
                [InlineKeyboardButton("❌ Close", callback_data="closeMessage")]
            ])
        )

    try:
        await cmd.answer()
    except QueryIdInvalid:
        pass

Bot.run()

