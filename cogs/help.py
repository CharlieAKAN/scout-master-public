import discord
from discord.ext import commands

class Help(commands.Cog):
    """Cog for providing help information to admins."""

    def __init__(self, bot):
        self.bot = bot
        print("Help cog initialized.")

    @commands.slash_command(
        name="help_scout_master",
        description="Get help with Scout Master by Storytellers of the Apocalypse."
    )
    @commands.has_permissions(administrator=True)
    async def help_scout_master(self, interaction: discord.Interaction):
        """Provides help information for admins."""
        help_message = (
            "**Need help with Scout Master by Storytellers of the Apocalypse?**\n\n"
            "📩 **DM CharlieAKAN** [click here](<https://discord.com/users/93071518229078016>)\n\n"
            "🌐 **Join our Discord!** [Storytellers of the Apocalypse](<https://discord.gg/zCBzPwe>)\n\n"
            "We’re here to support you in using Scout Master effectively! 🚀"
        )

        await interaction.response.send_message(help_message, ephemeral=True)


def setup(bot):
    bot.add_cog(Help(bot))
