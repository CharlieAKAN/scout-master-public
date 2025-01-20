import discord
from discord.ext import commands
from discord.ext.commands import MissingPermissions
from cogs.discord_plans import (
    get_guild_session_limit,
    set_guild_custom_image,
    update_entitlements_from_api,
)
from enum import IntEnum

class InteractionContextType(IntEnum):
    GUILD = 0
    BOT_DM = 1
    PRIVATE_CHANNEL = 2

class ImageUpload(commands.Cog):
    """Cog that handles custom image uploads for premium guilds."""

    def __init__(self, bot):
        self.bot = bot
        print("ImageUpload cog initialized.")

    @commands.slash_command(
        name="set_custom_image",
        description="(premium only) Set a custom image for a specific game",
        contexts=[InteractionContextType.GUILD],
    )
    @commands.has_permissions(administrator=True)
    async def set_custom_image(
        self,
        interaction: discord.Interaction,
        game_name: str,
        image_url: str,
    ):
        """Allows premium guilds to set a custom image for a given game."""
        guild_id = str(interaction.guild.id)

        # Perform an on-demand entitlement check
        await update_entitlements_from_api()

        # Check if this guild is premium
        session_limit = await get_guild_session_limit(guild_id)
        if session_limit <= 3:
            await interaction.response.send_message(
                "Custom images are only available for premium servers. Use </upgrade_scoutmaster:1330785705542287434> to access this feature.",
                ephemeral=True,
            )
            return

        # Validate the image URL
        if not (image_url.startswith("http://") or image_url.startswith("https://")):
            await interaction.response.send_message(
                "Please provide a valid URL (http:// or https://).", ephemeral=True
            )
            return

        # Save the custom image in Firestore
        await set_guild_custom_image(guild_id, game_name, image_url)
        await interaction.response.send_message(
            f"Successfully set a custom image for **{game_name}**!", ephemeral=True
        )

    @set_custom_image.error
    async def set_custom_image_error(
        self, interaction: discord.Interaction, error: commands.CommandError
    ):
        """Error handler for the set_custom_image command."""
        if isinstance(error, MissingPermissions):
            await interaction.response.send_message(
                "You need to be an administrator to use this command.",
                ephemeral=True,
            )
            print(f"User {interaction.user} tried to use the command without admin permissions.")
        else:
            await interaction.response.send_message(
                "An unexpected error occurred. Please try again later.",
                ephemeral=True,
            )
            print(f"Unexpected error: {error}")

def setup(bot):
    bot.add_cog(ImageUpload(bot))
