
"""
🔥 ULTRA-POWERFUL KICK HANDLERS 🔥
Lightning-fast member removal with military precision
"""

import asyncio
from typing import List
from pyrogram import Client
from pyrogram.types import Message, ChatMember
from pyrogram.errors import FloodWait, ChatAdminRequired, UserAdminInvalid
from config import Config
from handlers.utils import Utils

class KickHandler:
    """Ultra-powerful handler for kick operations"""

    def __init__(self, app: Client, config: Config, utils: Utils, logger):
        self.app = app
        self.config = config
        self.utils = utils
        self.logger = logger

    async def kick_all_members(self, message: Message):
        """🔥 KICK ALL MEMBERS - ULTRA EVACUATION 🔥"""
        if not self.utils.is_sudo_user(message.from_user.id):
            await message.reply_text("🚫 **ACCESS DENIED!** Only SUDO users can use ULTRA KICK.")
            return

        await self.utils.delete_message_safe(message)

        if not await self.utils.check_bot_permissions(message.chat.id):
            await message.reply_text("❌ **ERROR!** Bot needs admin permissions for ULTRA KICK operation.")
            return

        try:
            if not self.config.STEALTH_MODE:
                status_message = await message.reply_text("🔥 **ULTRA KICK-ALL OPERATION INITIATED...**\n\n⚡ Preparing for MASS EVACUATION...")
            else:
                status_message = None

            # Get all members with caching
            members = await self.utils.get_all_members(message.chat.id)
            if not members:
                if status_message:
                    await status_message.edit_text("❌ **ERROR!** Could not fetch group members.")
                return

            # Filter actionable members
            actionable_members = await self.utils.filter_actionable_members(message.chat.id, members)

            if not actionable_members:
                if status_message:
                    await status_message.edit_text("ℹ️ **NO TARGETS!** All members are protected or admins.")
                await asyncio.sleep(2)
                if self.config.AUTO_LEAVE_AFTER_KICK:
                    await self.utils.leave_chat(message.chat.id)
                return

            if status_message:
                await status_message.edit_text(f"👢 **KICKING {len(actionable_members)} TARGETS...**\n⚡ ULTRA EVACUATION MODE ENGAGED!")

            # Ultra-powerful concurrent kicking
            kicked_count = 0
            failed_count = 0
            semaphore = asyncio.Semaphore(self.config.MAX_CONCURRENT_OPERATIONS)

            async def ultra_kick_member(member: ChatMember):
                nonlocal kicked_count, failed_count
                async with semaphore:
                    try:
                        # Kick = Ban + Immediate Unban
                        await self.utils.handle_flood_wait(
                            self.app.ban_chat_member,
                            message.chat.id,
                            member.user.id
                        )
                        # Unban immediately to kick (not ban)
                        await self.utils.handle_flood_wait(
                            self.app.unban_chat_member,
                            message.chat.id,
                            member.user.id
                        )
                        kicked_count += 1
                        self.logger.log_action("MEMBER_KICKED", message.chat.id, member.user.id)
                    except Exception as e:
                        failed_count += 1
                        self.logger.log_error(f"Kick failed for user {member.user.id}: {str(e)}")

                    # Ultra-fast operation delay
                    await asyncio.sleep(self.config.OPERATION_DELAY)

            # Execute ultra-fast concurrent kicks
            tasks = [ultra_kick_member(member) for member in actionable_members]
            await asyncio.gather(*tasks, return_exceptions=True)

            # Log operation results
            operation_stats = {
                "kicked": kicked_count,
                "failed": failed_count,
                "total_processed": len(actionable_members)
            }
            self.logger.log_operation("KICK_ALL", message.chat.id, operation_stats)

            # Final status
            if not self.config.STEALTH_MODE:
                result_text = f"👢 **ULTRA KICK-ALL OPERATION COMPLETED!** 👢\n\n"
                result_text += f"**👢 KICKED:** {kicked_count} targets\n"
                result_text += f"**❌ FAILED:** {failed_count} targets\n"
                result_text += f"**⚡ TOTAL PROCESSED:** {len(actionable_members)} targets\n\n"
                
                if self.config.AUTO_LEAVE_AFTER_KICK:
                    result_text += f"**🚪 LEAVING CHAT IN 3 SECONDS...**\n🔥 NO TRACES LEFT BEHIND!"

                if status_message:
                    await status_message.edit_text(result_text)

            # Auto-leave for stealth
            if self.config.AUTO_LEAVE_AFTER_KICK:
                await asyncio.sleep(3)
                await self.utils.leave_chat(message.chat.id)

        except Exception as e:
            self.logger.log_error(f"Kick-all operation failed: {str(e)}", f"Chat: {message.chat.id}")
            if not self.config.STEALTH_MODE:
                await message.reply_text("❌ **ERROR during ULTRA KICK operation!**")
            if self.config.AUTO_LEAVE_AFTER_KICK:
                await asyncio.sleep(2)
                await self.utils.leave_chat(message.chat.id)

    async def kick_all_bots(self, message: Message):
        """🤖 REMOVE ALL BOTS - BOT PURGE 🤖"""
        if not self.utils.is_sudo_user(message.from_user.id):
            await message.reply_text("🚫 **ACCESS DENIED!** Only SUDO users can use BOT PURGE.")
            return

        await self.utils.delete_message_safe(message)

        if not await self.utils.check_bot_permissions(message.chat.id):
            await message.reply_text("❌ **ERROR!** Bot needs admin permissions for BOT PURGE operation.")
            return

        try:
            status_message = await message.reply_text("🤖 **BOT PURGE OPERATION INITIATED...**")

            members = await self.utils.get_all_members(message.chat.id)
            
            # Filter bot members (exclude self and admin bots)
            bot_members = []
            bot_info = await self.app.get_me()
            
            for member in members:
                if (member.user.is_bot and 
                    member.user.id != bot_info.id and 
                    member.status not in ["creator", "administrator"] and
                    not self.config.is_protected_user(member.user.id)):
                    bot_members.append(member)

            if not bot_members:
                await status_message.edit_text("ℹ️ **NO BOTS TO REMOVE!** All bots are protected or admins.")
                return

            await status_message.edit_text(f"🤖 **PURGING {len(bot_members)} BOTS...**")

            kicked_count = 0
            failed_count = 0
            semaphore = asyncio.Semaphore(self.config.MAX_CONCURRENT_OPERATIONS)

            async def purge_bot(bot_member: ChatMember):
                nonlocal kicked_count, failed_count
                async with semaphore:
                    try:
                        await self.utils.handle_flood_wait(
                            self.app.ban_chat_member,
                            message.chat.id,
                            bot_member.user.id
                        )
                        await self.utils.handle_flood_wait(
                            self.app.unban_chat_member,
                            message.chat.id,
                            bot_member.user.id
                        )
                        kicked_count += 1
                        self.logger.log_action("BOT_PURGED", message.chat.id, bot_member.user.id)
                    except Exception:
                        failed_count += 1

                    await asyncio.sleep(self.config.OPERATION_DELAY * 2)  # Slower for bots

            # Execute bot purge
            tasks = [purge_bot(bot_member) for bot_member in bot_members]
            await asyncio.gather(*tasks, return_exceptions=True)

            operation_stats = {"bots_removed": kicked_count, "failed": failed_count}
            self.logger.log_operation("BOT_PURGE", message.chat.id, operation_stats)

            result_text = f"🤖 **BOT PURGE COMPLETED!** 🤖\n\n"
            result_text += f"**🤖 REMOVED:** {kicked_count} bots\n"
            result_text += f"**❌ FAILED:** {failed_count} bots\n"
            result_text += f"**⚡ TOTAL PROCESSED:** {len(bot_members)} bots"

            await status_message.edit_text(result_text)

        except Exception as e:
            self.logger.log_error(f"Bot purge operation failed: {str(e)}")
            await message.reply_text("❌ **ERROR during BOT PURGE operation!**")
