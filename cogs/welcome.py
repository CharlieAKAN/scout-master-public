import discord
from discord.ext import commands


class Welcome(commands.Cog):
    """Cog for sending a welcome message when the bot joins a new server."""

    def __init__(self, bot):
        self.bot = bot
        print("Welcome cog initialized.")

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        welcome_message = (
            "🎉 **Scout Master by Storytellers of the Apocalypse has joined your server! YAY!** 🎉\n\n"
            "To get started, use </setup_scout_master:1330805308125347907> to configure your server. 🚀\n"
            "If you need help, check the documentation or contact support!"
            
        )

        # Try to send the message to the system channel
        if guild.system_channel:
            try:
                await guild.system_channel.send(welcome_message)
                print(f"Sent welcome message to system channel in guild: {guild.name}")
                return
            except discord.Forbidden:
                print(f"Permission denied to send message to system channel in guild: {guild.name}")
        
        # If the system channel is unavailable or sending fails, try the first available text channel
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                try:
                    await channel.send(welcome_message)
                    print(f"Sent welcome message to first available text channel in guild: {guild.name}")
                    return
                except discord.Forbidden:
                    continue

        # If no suitable channel is found, log the failure
        print(f"Failed to send welcome message in guild: {guild.name}")


def setup(bot):
    bot.add_cog(Welcome(bot))
