# cogs/recruitment.py
import discord
from discord.ext import commands
from discord.ui import Button, View
import time
import asyncio
from cogs.discord_plans import get_guild_session_limit, get_guild_custom_image
from cogs.reset_manager import get_reset_time
from datetime import datetime
import pytz
from cogs.constants import (
    DAILY_USAGE_COLLECTION,
    USER_USAGE_SUBCOLLECTION,
    USER_SESSIONS_SUBCOLLECTION,
    RESET_HOUR,
    RESET_MINUTE,
    SESSIONS_COLLECTION
)
import uuid



class RecruitmentView(View):
    """View for recruitment actions like joining and withdrawing from a session."""

    def __init__(
        self,
        bot: commands.Bot,
        session_id: str,
        guild: discord.Guild,
        vc: discord.VoiceChannel,
        text_channel: discord.TextChannel,
        game_name: str,
        session_creator: discord.Member,
        joined_users: set,
        remaining_spots: int,
        allowed_channel_id: int,
        notify_channel_id: int,
        timeout: int  # Timeout in seconds
    ):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.session_id = session_id
        self.guild = guild
        self.vc = vc
        self.text_channel = text_channel
        self.game_name = game_name
        self.session_creator = session_creator
        self.crew_members = set(joined_users)
        self.remaining_spots = remaining_spots
        self.allowed_channel_id = allowed_channel_id
        self.notify_channel_id = notify_channel_id
        print(f"RecruitmentView initialized for session_id: {self.session_id}")

    @discord.ui.button(label="Join this Session", style=discord.ButtonStyle.success)
    async def join(self, button: Button, interaction: discord.Interaction):
        """Handle the Join button interaction."""
        print(f"User {interaction.user} clicked Join button for session {self.session_id}")
        try:
            if interaction.user.id in self.crew_members:
                await interaction.response.send_message("You are already in the session!", ephemeral=True)
                return
            elif self.remaining_spots > 0:
                firestore_cog = self.bot.get_cog('FirestoreCog')
                if not firestore_cog:
                    await interaction.response.send_message("Internal error: FirestoreCog not found.", ephemeral=True)
                    return

                # Append user to 'joined_users' and decrement 'remaining_spots'
                await firestore_cog.append_to_field(self.session_id, 'joined_users', interaction.user.id)
                await firestore_cog.update_session_field(self.session_id, 'remaining_spots', self.remaining_spots - 1)

                self.crew_members.add(interaction.user.id)
                self.remaining_spots -= 1

                # Set permissions
                await self.vc.set_permissions(interaction.user, connect=True, view_channel=True)

                # Notify the associated text channel
                await self.text_channel.send(
                    f"{interaction.user.mention} has joined the session!"
                )

                # Fetch the recruitment channel
                recruitment_channel = self.guild.get_channel(self.allowed_channel_id)
                if recruitment_channel:
                    # Send the join message directly in the recruitment channel
                    join_message = await recruitment_channel.send(
                        f"{interaction.user.mention} has joined {self.session_creator.mention}'s session! Remaining spots: {self.remaining_spots}"
                    )
                    # Track the join message ID
                    await firestore_cog.append_to_field(self.session_id, 'join_message_ids', join_message.id)
                    print(f"Tracked join message with ID: {join_message.id}")
                else:
                    print(f"Recruitment channel with ID {self.allowed_channel_id} not found.")

                # Optionally, send a confirmation to the user
                await interaction.response.send_message(
                    "✅ You have successfully joined the session! Look for your voice channel to join!",
                    ephemeral=True  # Set to True if you prefer only the user sees this
                )
            else:
                await interaction.response.send_message("The gaming session is already full!", ephemeral=True)
        except Exception as e:
            print(f"Error in join method: {e}")
            await interaction.response.send_message("An error occurred while joining the session.", ephemeral=True)

    @discord.ui.button(label="Withdraw", style=discord.ButtonStyle.danger)
    async def withdraw(self, button: Button, interaction: discord.Interaction):
        """Handle the Withdraw button interaction."""
        print(f"User {interaction.user} clicked Withdraw button for session {self.session_id}")
        try:
            if interaction.user.id in self.crew_members:
                firestore_cog = self.bot.get_cog('FirestoreCog')
                if not firestore_cog:
                    await interaction.response.send_message("Internal error: FirestoreCog not found.", ephemeral=True)
                    return

                # Remove user from 'joined_users' and increment 'remaining_spots'
                await firestore_cog.remove_from_field(self.session_id, 'joined_users', interaction.user.id)
                await firestore_cog.update_session_field(self.session_id, 'remaining_spots', self.remaining_spots + 1)

                self.crew_members.remove(interaction.user.id)
                self.remaining_spots += 1

                # Reset permissions
                await self.vc.set_permissions(interaction.user, overwrite=None)

                # Send the withdrawal message to the recruitment channel
                recruitment_channel = self.guild.get_channel(self.allowed_channel_id)
                if recruitment_channel:
                    try:
                        withdraw_msg = await recruitment_channel.send(
                            f"{interaction.user.mention} has withdrawn from {self.session_creator.mention}'s session. Remaining spots: {self.remaining_spots}"
                        )
                        # Track the withdrawal message ID
                        await firestore_cog.append_to_field(self.session_id, 'withdraw_message_ids', withdraw_msg.id)
                        print(f"Withdrawal message sent in recruitment channel with ID: {withdraw_msg.id}")
                    except discord.Forbidden:
                        print(f"Failed to send withdrawal message in {recruitment_channel}. Check bot permissions.")
                    except discord.HTTPException as e:
                        print(f"HTTPException when sending withdrawal message: {e}")
                else:
                    print(f"Recruitment channel with ID {self.allowed_channel_id} not found.")

                # Send confirmation to the user
                await interaction.response.send_message(
                    f"You have withdrawn from the session. Voice channel is now locked for you!",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message("You are not part of the session!", ephemeral=True)
        except Exception as e:
            print(f"Error in withdraw method: {e}")
            await interaction.response.send_message("An error occurred while withdrawing from the session.", ephemeral=True)

    async def on_timeout(self):
        """Handle the view timeout by cleaning up the session."""
        try:
            firestore_cog = self.bot.get_cog('FirestoreCog')
            if not firestore_cog:
                print("FirestoreCog not found.")
                return

            session_data = await firestore_cog.load_session(self.session_id)
            if not session_data:
                print(f"Session {self.session_id} not found in Firestore during timeout cleanup.")
                return

            join_message_ids = session_data.get("join_message_ids", [])

            # Delete all join session messages
            for msg_id in join_message_ids:
                try:
                    recruitment_channel = self.guild.get_channel(self.allowed_channel_id)
                    if recruitment_channel:
                        join_message = await recruitment_channel.fetch_message(msg_id)
                        await join_message.delete()
                        print(f"Deleted join session message ID: {msg_id}.")
                except discord.NotFound:
                    print(f"Join session message ID {msg_id} not found.")
                except discord.HTTPException as e:
                    print(f"Error deleting join session message ID {msg_id}: {e}")

            # Retrieve recruitment_message_id
            recruitment_message_id = session_data.get("recruitment_message_id")

            if recruitment_message_id:
                try:
                    # Fetch the recruitment message and edit it to indicate recruitment has ended
                    recruitment_channel = self.guild.get_channel(self.allowed_channel_id)
                    if recruitment_channel:
                        recruitment_message = await recruitment_channel.fetch_message(recruitment_message_id)
                        ended_embed = discord.Embed(
                            title=f"Recruitment for {self.game_name} has ended",
                            description=(
                                f"The session is done!\n\n"
                                f"Participants were:\n" +
                                "\n".join(f"<@{user_id}>" for user_id in self.crew_members) + "\n"
                                f"\nUse command </recruit:1330805308125347906> to start your own crew!"
                            ),
                            color=discord.Color.orange()
                        )
                        await recruitment_message.edit(embed=ended_embed, view=None)
                        print(f"Edited recruitment message {recruitment_message_id} to indicate recruitment has ended.")
                except discord.NotFound:
                    print(f"Recruitment message {recruitment_message_id} not found.")
                except Exception as e:
                    print(f"Error editing recruitment message {recruitment_message_id}: {e}")

            # Perform cleanup (delete other resources but keep recruitment message)
            notify_message_id = session_data.get("notify_message_id")
            join_message_ids = session_data.get("join_message_ids", [])
            withdraw_message_ids = session_data.get("withdraw_message_ids", [])
            vc_id = session_data.get("vc_id")
            text_channel_id = session_data.get("text_channel_id")

            # Delete notify message
            if notify_message_id:
                try:
                    notify_channel = self.guild.get_channel(self.notify_channel_id)
                    if notify_channel:
                        notify_message = await notify_channel.fetch_message(notify_message_id)
                        await notify_message.delete()
                        print("Deleted notify message.")
                except discord.NotFound:
                    print("Notify message not found.")
                except Exception as e:
                    print(f"Error deleting notify message: {e}")

            # Delete join messages (if any)
            if join_message_ids:
                for msg_id in join_message_ids:
                    try:
                        recruitment_channel = self.guild.get_channel(self.allowed_channel_id)
                        if recruitment_channel:
                            join_message = await recruitment_channel.fetch_message(msg_id)
                            await join_message.delete()
                            print(f"Deleted join message {msg_id}.")
                    except discord.NotFound:
                        print(f"Join message {msg_id} not found.")
                    except Exception as e:
                        print(f"Error deleting join message {msg_id}: {e}")

            # Delete withdraw messages from recruitment channel
            for msg_id in withdraw_message_ids:
                try:
                    recruitment_channel = self.guild.get_channel(self.allowed_channel_id)
                    if recruitment_channel:
                        withdraw_msg = await recruitment_channel.fetch_message(msg_id)
                        await withdraw_msg.delete()
                        print(f"Deleted withdraw message ID {msg_id}.")
                except discord.NotFound:
                    print(f"Withdraw message ID {msg_id} not found.")
                except discord.HTTPException as e:
                    print(f"Failed to delete withdrawal message ID {msg_id}: {e}")

            # Delete the voice channel
            if vc_id:
                try:
                    vc = self.guild.get_channel(vc_id)
                    if vc:
                        await vc.delete(reason="Session timed out.")
                        print("Deleted voice channel.")
                except discord.NotFound:
                    print("Voice channel already deleted.")
                except Exception as e:
                    print(f"Error deleting voice channel: {e}")

            # Delete the follow-up message
            followup_message_id = session_data.get("followup_message_id")
            followup_channel_id = session_data.get("followup_channel_id")
            if followup_message_id and followup_channel_id:
                try:
                    channel = self.guild.get_channel(followup_channel_id)
                    if channel:
                        followup_message = await channel.fetch_message(followup_message_id)
                        await followup_message.delete()
                        print("Deleted follow-up message.")
                except discord.NotFound:
                    print("Follow-up message already deleted.")
                except discord.HTTPException as e:
                    print(f"Failed to delete follow-up message: {e}")
            else:
                print("No follow-up message information found in session data.")

            # Retain recruitment_message_id in Firestore
            updated_data = {
                "recruitment_message_id": session_data.get("recruitment_message_id")
            }
            await firestore_cog.save_session(self.session_id, updated_data)
            print(f"Cleaned up session {self.session_id} but retained recruitment_message_id.")

        except Exception as e:
            print(f"Error in on_timeout for RecruitmentView {self.session_id}: {e}")

class CancelSessionView(View):
    """View for canceling a session by the creator."""

    def __init__(
        self,
        bot: commands.Bot,
        session_id: str,
        vc: discord.VoiceChannel,
        text_channel: discord.TextChannel,
        allowed_channel_id: int,
        notify_channel_id: int,
        guild: discord.Guild
    ):
        super().__init__(timeout=None)
        self.bot = bot
        self.session_id = session_id
        self.vc = vc
        self.text_channel = text_channel
        self.allowed_channel_id = allowed_channel_id
        self.notify_channel_id = notify_channel_id
        self.guild = guild
        print(f"CancelSessionView initialized for session_id: {self.session_id}")

    @discord.ui.button(label="Cancel Session", style=discord.ButtonStyle.danger)
    async def cancel(self, button: Button, interaction: discord.Interaction):
        """Handle the Cancel Session button interaction."""
        print(f"User {interaction.user} clicked Cancel button for session {self.session_id}")
        try:
            firestore_cog = self.bot.get_cog('FirestoreCog')
            if not firestore_cog:
                await interaction.response.send_message("Internal error: FirestoreCog not found.", ephemeral=True)
                return

            session_data = await firestore_cog.load_session(self.session_id)
            if not session_data:
                await interaction.response.send_message(
                    "Session data not found. It might have already been canceled or timed out.", ephemeral=True
                )
                return

            creator_id = session_data.get('creator_id')
            creator = self.guild.get_member(creator_id)
            if not creator:
                print(f"Creator with ID {creator_id} not found.")
                await interaction.response.send_message(
                    "Creator not found. Cannot cancel the session.", ephemeral=True
                )
                return

            if interaction.user.id != creator.id:
                await interaction.response.send_message(
                    "Only the gaming session creator can cancel this session.", ephemeral=True
                )
                return

            # Send the confirmation message BEFORE deleting channels
            await interaction.response.send_message(
                "The gaming session has been successfully canceled.",
                ephemeral=True
            )
            print("Sent cancellation confirmation message.")

        except Exception as e:
            print(f"Error in sending confirmation message: {e}")
            await interaction.response.send_message(
                "An error occurred while canceling the session.",
                ephemeral=True
            )
            return

        try:
            # Proceed to delete messages and channels
            notify_message_id = session_data.get("notify_message_id")
            recruitment_message_id = session_data.get("recruitment_message_id")
            join_message_ids = session_data.get("join_message_ids", [])
            withdraw_message_ids = session_data.get("withdraw_message_ids", [])
            vc_id = session_data.get("vc_id")
            text_channel_id = session_data.get("text_channel_id")

            # Delete the @everyone notify message
            if notify_message_id:
                try:
                    notify_channel = self.guild.get_channel(self.notify_channel_id)
                    if notify_channel:
                        notify_message = await notify_channel.fetch_message(notify_message_id)
                        await notify_message.delete()
                        print("Deleted @everyone notify message.")
                    else:
                        print(f"Notify channel ID {self.notify_channel_id} not found.")
                except discord.NotFound:
                    print("Notify message already deleted.")
                except discord.HTTPException as e:
                    print(f"Failed to delete notify message: {e}")

            # Delete the recruitment message
            if recruitment_message_id:
                try:
                    recruitment_channel = self.guild.get_channel(self.allowed_channel_id)
                    if recruitment_channel:
                        recruitment_message = await recruitment_channel.fetch_message(recruitment_message_id)
                        await recruitment_message.delete()
                        print("Deleted recruitment message.")
                    else:
                        print(f"Recruitment channel ID {self.allowed_channel_id} not found.")
                except discord.NotFound:
                    print("Recruitment message already deleted.")
                except discord.HTTPException as e:
                    print(f"Failed to delete recruitment message: {e}")

            # Delete all join messages from recruitment channel
            if join_message_ids:
                for msg_id in join_message_ids:
                    try:
                        recruitment_channel = self.guild.get_channel(self.allowed_channel_id)
                        if recruitment_channel:
                            join_message = await recruitment_channel.fetch_message(msg_id)
                            await join_message.delete()
                            print(f"Deleted join message ID {msg_id}.")
                    except discord.NotFound:
                        print(f"Join message ID {msg_id} already deleted.")
                    except discord.HTTPException as e:
                        print(f"Error deleting join message ID {msg_id}: {e}")

            # Delete all withdraw messages from recruitment channel
            for msg_id in withdraw_message_ids:
                try:
                    recruitment_channel = self.guild.get_channel(self.allowed_channel_id)
                    if recruitment_channel:
                        withdraw_msg = await recruitment_channel.fetch_message(msg_id)
                        await withdraw_msg.delete()
                        print(f"Deleted withdraw message ID {msg_id}.")
                except discord.NotFound:
                    print(f"Withdraw message ID {msg_id} already deleted.")
                except discord.HTTPException as e:
                    print(f"Failed to delete withdrawal message ID {msg_id}: {e}")

            # Notify participants in the allowed channel
            allowed_channel = self.guild.get_channel(self.allowed_channel_id)
            if allowed_channel:
                mentions = " ".join(f"<@{user_id}>" for user_id in session_data.get("joined_users", []))
                await allowed_channel.send(
                    f"The gaming session to play **{session_data.get('game_name', 'a game')}**, hosted by {creator.mention}, has been canceled. "
                    f"Apologies to anyone who joined: {mentions}"
                )
                print("Notified participants about session cancellation.")
            else:
                print(f"Allowed channel ID {self.allowed_channel_id} not found.")

            # Delete the voice channel if it still exists
            if vc_id:
                try:
                    vc = self.guild.get_channel(vc_id)
                    if vc:
                        await vc.delete(reason="Gaming session canceled by the creator.")
                        print("Deleted voice channel.")
                except discord.NotFound:
                    print("Voice channel already deleted.")
                except Exception as e:
                    print(f"Error deleting voice channel: {e}")

            # Delete the follow-up message
            followup_message_id = session_data.get("followup_message_id")
            followup_channel_id = session_data.get("followup_channel_id")
            if followup_message_id and followup_channel_id:
                try:
                    channel = self.guild.get_channel(followup_channel_id)
                    if channel:
                        followup_message = await channel.fetch_message(followup_message_id)
                        await followup_message.delete()
                        print("Deleted follow-up message.")
                except discord.NotFound:
                    print("Follow-up message already deleted.")
                except discord.HTTPException as e:
                    print(f"Failed to delete follow-up message: {e}")
            else:
                print("No follow-up message information found in session data.")

            # Delete the text channel
            if text_channel_id:
                try:
                    text_channel = self.guild.get_channel(text_channel_id)
                    if text_channel:
                        await text_channel.delete(reason="Session timed out.")
                        print("Deleted text channel.")
                except discord.NotFound:
                    print("Text channel already deleted.")
                except Exception as e:
                    print(f"Error deleting text channel: {e}")

            # Retain recruitment_message_id in Firestore
            updated_data = {
                "recruitment_message_id": session_data.get("recruitment_message_id")
            }
            await firestore_cog.save_session(self.session_id, updated_data)
            print(f"Cleaned up session {self.session_id} but retained recruitment_message_id.")

        except Exception as e:
            print(f"Error in cancel session: {e}")

            # Delete the text channel if it still exists
            if text_channel_id:
                try:
                    text_channel = self.guild.get_channel(text_channel_id)
                    if text_channel:
                        await text_channel.delete(reason="Gaming session canceled by the creator.")
                        print("Deleted text channel.")
                except discord.NotFound:
                    print("Text channel already deleted.")
                except Exception as e:
                    print(f"Error deleting text channel: {e}")

            # Remove session from Firestore
            await firestore_cog.remove_session(self.session_id)
            print(f"Session {self.session_id} cleaned up successfully.")

class Recruitment(commands.Cog):
    """Cog for handling recruitment commands."""

    def __init__(self, bot):
        self.bot = bot
        print("Recruitment cog initialized.")

    @commands.slash_command(name="recruit", description="Recruit players for a game session")
    async def recruit(
        self,
        interaction: discord.Interaction,
        game_name: str,
        player_count: int,
        game_time: str,
        hours_playing: int,
        add_player_1: discord.Member = None,
        add_player_2: discord.Member = None,
        add_player_3: discord.Member = None
    ):
        guild_id = interaction.guild.id
        user_id = interaction.user.id
        firestore_cog = self.bot.get_cog('FirestoreCog')
        if not firestore_cog:
            await interaction.response.send_message("Internal error: FirestoreCog not found.", ephemeral=True)
            return

        # Server-wide daily limit
        session_limit = await get_guild_session_limit(str(guild_id))

        # Fetch guild-wide daily usage
        guild_daily_usage = await firestore_cog.get_daily_usage(guild_id)
        guild_usage_count = guild_daily_usage.get("usage_count", 0)

        if guild_usage_count >= session_limit:
            reset_time = await get_reset_time()
            remaining = reset_time - time.time()
            remaining_hours = int(remaining // 3600)
            remaining_minutes = int((remaining % 3600) // 60)
            reset_dt = datetime.fromtimestamp(reset_time, pytz.timezone('US/Eastern'))
            reset_time_str = reset_dt.strftime('%I:%M %p EST')
            await interaction.response.send_message(
                f"🚨 This server has reached its **daily limit of {session_limit} sessions.**\n\n"
                f"⏰ Please wait {remaining_hours} hours and {remaining_minutes} minutes until the reset at {reset_time_str}. \n\n"
                f"⏫ Server owners can increase session limit by using command </upgrade_scoutmaster:1330785705542287434> ",
                ephemeral=True
            )
            print(f"Guild limit reached: {session_limit} sessions.")
            return

        # Load guild configuration
        config = await firestore_cog.load_config(guild_id)
        if not config:
            await interaction.response.send_message(
                "🚨 Configuration not found for this server. Please run </setup_scout_master1330805308125347907 first.> 🚨",
                ephemeral=True
            )
            print("Configuration not found for the guild.")
            return

        role_restrictions = config.get("role_restrictions", [])
        if role_restrictions:
            user_roles = [role.id for role in interaction.user.roles]
            if not any(role_id in user_roles for role_id in role_restrictions):
                await interaction.response.send_message(
                    "You do not have the required role to use this command. Talk with the server owner!",
                 ephemeral=True
                )
                return

        # Extract configurations
        notify_channel_id = config.get("notify_channel_id")
        use_mention = config.get("use_mention", False)
        allowed_channel_id = config.get("allowed_channel_id")
        category_id = config.get("category_id")
        user_usage_limit = config.get("user_usage_limit", 1)  # Default to 1 if not set

        # User-specific daily limit (check BEFORE incrementing usage count)
        user_daily_usage = await firestore_cog.get_daily_usage(guild_id, user_id)
        user_usage_count = user_daily_usage.get("usage_count", 0)

        if user_usage_count >= user_usage_limit:  # Assuming a single daily limit for users
            reset_time = await get_reset_time()
            remaining = reset_time - time.time()
            remaining_hours = int(remaining // 3600)
            remaining_minutes = int((remaining % 3600) // 60)
            reset_dt = datetime.fromtimestamp(reset_time, pytz.timezone('US/Eastern'))
            reset_time_str = reset_dt.strftime('%I:%M %p EST')
            await interaction.response.send_message(
                f"🚨 You reached your limit of {user_usage_limit} per day. The next reset is at {reset_time_str}. \n\n"
                f"⏰ Please wait {remaining_hours} hours and {remaining_minutes} minutes until the reset at {reset_time_str}.",
                ephemeral=True
            )
            print(f"User {user_id} limit reached.")
            return

        # Increment server usage count and update Firestore AFTER the check
        guild_usage_count += 1
        await firestore_cog.set_daily_usage(guild_id, usage_count=guild_usage_count)
        user_usage_count += 1
        await firestore_cog.set_daily_usage(guild_id, usage_count=user_usage_count, user_id=user_id)

        
        print(f"Guild usage updated: {guild_usage_count}, User usage updated: {user_usage_count}")
        
        async def count_active_sessions(firestore_cog, guild_id: int, user_id: int = None) -> int:
            try:
                query = firestore_cog.sessions_collection.where('guild_id', '==', guild_id)
                if user_id is not None:
                    query = query.where('creator_id', '==', user_id)
                sessions = await asyncio.to_thread(lambda: list(query.stream()))
                return len(sessions)
            except Exception as e:
                print(f"Error counting active sessions for guild {guild_id}, user {user_id}: {e}")
                return 0

        active_guild_sessions = await count_active_sessions(firestore_cog, guild_id)
        print(f"User {user_id} has {active_guild_sessions} active sessions.")

        # 3) If user has reached or exceeded the limit, block creation
        if active_guild_sessions >= session_limit:
            await interaction.response.send_message(
                f"You've reached your limit of {session_limit} sessions for your current plan. "
                f"Please upgrade your plan or end an existing session.",
                ephemeral=True
            )
            print(f"User {user_id} has reached the session limit: {session_limit}")
            return

        active_user_sessions = await count_active_sessions(firestore_cog, guild_id, user_id)
        if active_user_sessions >= session_limit:
            await interaction.response.send_message(
                f"You've reached your limit of {session_limit} active sessions for your current plan. "
                f"Please end an existing session before creating a new one.",
                ephemeral=True
            )
            print(f"User {user_id} has reached the session limit of {session_limit}.")
            return

        
        
        session_id = str(uuid.uuid4())
        session_data = await firestore_cog.load_session(session_id)
        
        if session_data:
            start_time = session_data.get("start_time", 0)
            current_time = time.time()
            reset_time = await get_reset_time()

            if current_time < reset_time:
                user_usage = await firestore_cog.get_daily_usage(guild_id, user_id)
                if not user_usage:
                    # If usage data is missing, clean up the session and proceed
                    print(f"Mismatch detected for session {session_id}. Cleaning up...")
                    await firestore_cog.remove_session(session_id)
                else:
                    remaining = reset_time - current_time
                    remaining_hours = int(remaining // 3600)
                    remaining_minutes = int((remaining % 3600) // 60)
                    reset_dt = datetime.fromtimestamp(reset_time, pytz.timezone('US/Eastern'))
                    reset_time_str = reset_dt.strftime('%I:%M %p EST')

                    await interaction.response.send_message(
                        f"You reached your limit of {user_usage_limit} per day. The next reset is at {reset_time_str}. "
                        f"Please wait {remaining_hours} hours and {remaining_minutes} minutes until the reset.",
                        ephemeral=True
                    )
                    print(f"Session cooldown active for user {user_id}.")
                    return
            else:
                # Cooldown has expired; remove the session to allow reuse
                await firestore_cog.remove_session(session_id)
                print(f"Session cooldown expired for user {user_id}. Removed session.")

        print("Recruit command invoked")
        await interaction.response.defer()  # Defer the interaction

        try:
            # Track session creator and joined users
            session_creator = interaction.user
            joined_users = {session_creator.id}

            # Collect pre-added players
            additional_players = [add_player_1, add_player_2, add_player_3]
            additional_players = [player for player in additional_players if player is not None]

            # Build a string of added players' mentions
            if additional_players:
                added_players_mentions = ", ".join([player.mention for player in additional_players])
                added_players_text = f" with {added_players_mentions}"
            else:
                added_players_text = ""

            # Set remaining_spots directly based on player_count
            remaining_spots = player_count

            # **Convert hours_playing to seconds**
            if hours_playing <= 0:
                await interaction.followup.send(
                    "Please provide a positive number for hours_playing.",
                    ephemeral=True
                )
                print("Invalid hours_playing provided.")
                return

            timeout_seconds = hours_playing * 3600  # Convert hours to seconds
            print(f"Timeout set to {timeout_seconds} seconds based on hours_playing={hours_playing}")

            # Embed for recruitment message
            default_image_url = 'https://cdn.discordapp.com/attachments/808508638918475808/1328923195855867905/scoutmaster.jpg'
            session_limit = await get_guild_session_limit(str(guild_id))
            if session_limit > 3:
                possible_custom_image = await get_guild_custom_image(str(guild_id), game_name)
                if possible_custom_image:
                    image_url = possible_custom_image
                    print("Using premium custom image.")
                else:
                    image_url = default_image_url
                    print("Guild is premium but no custom image set; using fallback default.")
            else:
                # If free plan
                image_url = default_image_url
                print("Guild is on free plan; using fallback default image.")

            embed = discord.Embed(
                title=f"Recruiting Players for {game_name}",
                description=(
                    f"Join **{session_creator.mention}**'s gaming session{added_players_text} happening at **{game_time}**!\n\n"
                    f"They will be playing for about **{hours_playing} hour/s**, and the voice channel and session will automatically be deleted afterward.\n\n"
                    f"We need **{remaining_spots}** more player{'s' if remaining_spots > 1 else ''}! "
                    f"Click the buttons below to join or withdraw."
                ),
                color=discord.Color.blue()
            )
            embed.set_image(url=image_url)

            # Fetch the category by its ID
            category = discord.utils.get(interaction.guild.categories, id=category_id)
            if not category:
                await interaction.followup.send(
                    "Error: The specified category does not exist in this server. Please ensure the category ID is correct.",
                    ephemeral=True
                )
                print("Specified category does not exist.")
                return

            # Create the voice channel under the specified category without user limit
            vc_name = f"{session_creator.display_name}'s {game_name} Session"
            try:
                vc = await interaction.guild.create_voice_channel(
                    name=vc_name,
                    category=category
                )
                print(f"Voice channel '{vc_name}' created with ID {vc.id}")
            except discord.HTTPException as e:
                print(f"Failed to create a voice channel: {e}")
                await interaction.followup.send(
                    "Failed to create a voice channel. Please try again later.",
                    ephemeral=True
                )
                return

            # **Fetch the Associated Text Channel Using the Voice Channel's ID**
            # This assumes that a text channel with the same ID as the voice channel exists
            text_channel = interaction.guild.get_channel(vc.id)
            if not text_channel:
                await interaction.followup.send(
                    "Error: Failed to find the associated text channel.",
                    ephemeral=True
                )
                print("Associated text channel not found.")
                return

            # **Set Permissions for the Creator**
            try:
                await vc.set_permissions(session_creator, connect=True, view_channel=True)
                await vc.set_permissions(interaction.guild.default_role, connect=False)
                print(f"Permissions set for creator {session_creator} in voice channel.")
            except discord.HTTPException as e:
                print(f"Failed to set permissions for the voice channel: {e}")
                await interaction.followup.send(
                    "Failed to set permissions for the voice channel. Please try again later.",
                    ephemeral=True
                )
                return

            # **Add Pre-specified Players**
            for player in additional_players:
                try:
                    await vc.set_permissions(player, connect=True, view_channel=True)
                    joined_users.add(player.id)
                    # Notify the player via DM with a clickable link to the text channel
                    await player.send(
                        f"You have been added to {session_creator.display_name}'s gaming session to play **{game_name}**! "
                        f"Join the voice channel in the server: {vc.mention}"
                    )
                    print(f"Added {player} to voice channel permissions and sent DM.")
                except discord.Forbidden:
                    print(f"Could not send DM to {player.display_name}")
                except discord.HTTPException:
                    print(f"Failed to set permissions for {player.display_name}")

            # **Notify Participants in the Associated Text Channel**
            if additional_players:
                mentions = ", ".join(player.mention for player in additional_players)
                await text_channel.send(
                    f"The following players have been added to the session: {mentions}"
                )
                print("Notified additional players in the text channel.")

            # **Fetch the Notification Channel by Its ID**
            notify_channel = interaction.guild.get_channel(notify_channel_id)
            if not notify_channel:
                await interaction.followup.send(
                    "Error: The notification channel does not exist in this server. Please ensure the channel ID is correct.",
                    ephemeral=True
                )
                print("Notification channel not found.")
                return

            # **Send the Notification Message to the Notification Channel**
            if use_mention and interaction.guild.me.guild_permissions.mention_everyone:
                try:
                    notify_message = await notify_channel.send(
                        content=(
                            f"Hey @everyone! **{session_creator.mention}** has started a gaming session to play **{game_name}**!"
                            f" Join the recruitment channel here: <#{allowed_channel_id}>"
                        )
                    )
                    print("Sent @everyone notification message.")
                except discord.HTTPException as e:
                    print(f"Failed to send @everyone message: {e}")
                    try:
                        notify_message = await notify_channel.send(
                            content=(
                                f"**{session_creator.mention}** has started a gaming session to play **{game_name}**!"
                                f" Join the recruitment channel here: <#{allowed_channel_id}>"
                            )
                        )
                        print("Sent notification message without @everyone mention.")
                    except discord.HTTPException as e:
                        print(f"Failed to send fallback notification message: {e}")
                        await interaction.followup.send(
                            "Failed to send notification message. Please check the bot's permissions.",
                            ephemeral=True
                        )
                        return
            else:
                try:
                    notify_message = await notify_channel.send(
                        content=(
                            f"**{session_creator.mention}** has started a gaming session to play **{game_name}**!"
                            f" Join the recruitment channel here: <#{allowed_channel_id}>"
                        )
                    )
                    print("Sent notification message without @everyone mention.")
                except discord.HTTPException as e:
                    print(f"Failed to send notification message: {e}")
                    await interaction.followup.send(
                        "Failed to send notification message. Please check the bot's permissions.",
                        ephemeral=True
                    )
                    return

            # **Add RecruitmentView to Send Recruitment Message with Buttons**
            view = RecruitmentView(
                self.bot,  # Pass the bot instance
                session_id,
                interaction.guild,  # Corrected: pass guild object
                vc,
                text_channel,
                game_name,
                session_creator,
                joined_users,
                remaining_spots,
                allowed_channel_id,
                notify_channel_id,
                timeout_seconds  # Dynamic timeout
            )

            # **Send the Recruitment Message to the Allowed Channel**
            allowed_channel = interaction.guild.get_channel(allowed_channel_id)
            if not allowed_channel:
                await interaction.followup.send(
                    "Error: The allowed channel for recruitment was not found. Please check the configuration.",
                    ephemeral=True
                )
                print("Allowed recruitment channel not found.")
                return

            recruitment_message = await allowed_channel.send(
                embed=embed,
                view=view
            )
            print(f"Sent recruitment message to allowed channel ID {allowed_channel_id} with message ID {recruitment_message.id}")

            # **Add Session to Firestore, Including notify_message_id and Lists for join/withdraw messages**
            print(f"Saving session with ID: {session_id}")  # Debugging

            # Save recruitment_message_id first
            session_data = {
                "creator_id": session_creator.id,
                "game_name": game_name,
                "player_count": player_count,
                "game_time": game_time,
                "vc_id": vc.id,
                "text_channel_id": text_channel.id,
                "joined_users": list(joined_users),
                "notify_message_id": notify_message.id,                # Store the notify message ID
                "recruitment_message_id": recruitment_message.id,      # Initialize recruitment_message_id
                "join_message_ids": [],                                # List to store join message IDs
                "withdraw_message_ids": [],
                # "followup_message_id": followup_message.id,           # Remove from here
                # "followup_channel_id": interaction.channel.id,       # Remove from here
                "start_time": time.time(),                             # Record the current timestamp
                "hours_playing": hours_playing                         # New field
            }
            await firestore_cog.add_session(session_id, session_data)
            print(f"Session {session_id} added to Firestore.")

            # **Attach CancelSessionView to the Session's Text Channel**
            await text_channel.send(
                f"Welcome {session_creator.mention} to your gaming session VC! If you have to cancel, click the Cancel Session button below.",
                view=CancelSessionView(
                    self.bot,  # Pass the bot instance
                    session_id,
                    vc,
                    text_channel,
                    allowed_channel_id,
                    notify_channel_id,
                    interaction.guild  # Corrected: pass interaction.guild
                )
            )
            print("Attached CancelSessionView to the text channel.")

            # **Send the Follow-Up Message with Line Break and Emoji**
            followup_message = await interaction.followup.send(
                content=(
                    f"✅ Recruitment session created!\n\n"  # Line break
                    f"🔥 This server has **{session_limit - guild_usage_count}** session(s) left today!"  # Fire emoji
                ),
                ephemeral=False
            )
            print("Sent minimal follow-up message to conclude the interaction.")

            # **Update session_data with followup_message_id and save again**
            session_data['followup_message_id'] = followup_message.id
            session_data['followup_channel_id'] = interaction.channel.id
            await firestore_cog.save_session(session_id, session_data)
            print(f"Follow-up message stored: ID {followup_message.id} in channel {interaction.channel.id}")

            asyncio.create_task(view.wait())
            print("RecruitmentView is now active and waiting for interactions.")

        except Exception as e:
            print(f"Error in recruit command: {e}")
            try:
                await interaction.followup.send(
                    "An unexpected error occurred while creating the recruitment session. Please try again later.",
                    ephemeral=True
                )
                print("Sent error follow-up message.")
            except Exception as ex:
                print(f"Failed to send error follow-up message: {ex}")

def setup(bot):
    bot.add_cog(Recruitment(bot))
