import discord
from discord.ext import commands
from discord.ui import View, Select
from cogs.discord_plans import get_guild_session_limit, update_entitlements_from_api  # Ensure this import is correct
from cogs.firestore import FirestoreCog  # Update the import path as per your project structure

class RoleRestrictions(commands.Cog):
    """Cog for managing role restrictions for premium guilds."""

    def __init__(self, bot):
        self.bot = bot
        print("RoleRestrictions cog initialized.")

    @commands.slash_command(
        name="set_role_restrictions",
        description="(premium only) Set role restrictions for using recruitment."
    )
    @commands.has_permissions(administrator=True)
    async def set_role_restrictions(self, interaction: discord.Interaction):
        """Command for admins to set role restrictions."""
        guild_id = str(interaction.guild.id)

        # Perform an on-demand entitlement check
        await update_entitlements_from_api()

        # Check if the guild is premium
        session_limit = await get_guild_session_limit(guild_id)
        if session_limit <= 3:  # Assuming 3 is the free limit
            await interaction.response.send_message(
                "Role restrictions are only available for premium servers. Use </upgrade_scoutmaster:1330785705542287434> to access this feature.",
                ephemeral=True
            )
            return

        # Fetch roles in the guild
        roles = interaction.guild.roles
        options = [discord.SelectOption(label=role.name, value=str(role.id)) for role in roles if not role.managed]

        if not options:
            await interaction.response.send_message(
                "No roles found to restrict. Please create roles first.",
                ephemeral=True
            )
            return

        # Display a dropdown menu for role selection
        view = RoleSelectionView(options, self.bot.get_cog("FirestoreCog"), guild_id)
        await interaction.response.send_message(
            "Select the roles allowed to use recruitment:",
            view=view,
            ephemeral=True
        )

    @set_role_restrictions.error
    async def set_role_restrictions_error(self, interaction: discord.Interaction, error: commands.CommandError):
        """Error handler for the set_role_restrictions command."""
        if isinstance(error, commands.MissingPermissions):
            await interaction.response.send_message(
                "You need Administrator permissions to run this command.",
                ephemeral=True
            )
            print(f"User {interaction.user} attempted to use /set_role_restrictions without Administrator permissions.")
        else:
            await interaction.response.send_message(
                "An unexpected error occurred while executing the command. Please try again later.",
                ephemeral=True
            )
            print(f"Unexpected error in /set_role_restrictions: {error}")

class RoleSelectionView(View):
    """View to handle role selection for restrictions."""

    def __init__(self, options, firestore_cog, guild_id):
        super().__init__(timeout=300)
        self.firestore_cog = firestore_cog
        self.guild_id = guild_id
        self.add_item(RoleSelect(options, self.firestore_cog, self.guild_id))

class RoleSelect(Select):
    """Dropdown for selecting roles."""

    def __init__(self, options, firestore_cog, guild_id):
        super().__init__(
            placeholder="Select roles...",
            min_values=1,
            max_values=len(options),
            options=options
        )
        self.firestore_cog = firestore_cog
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):
        selected_roles = [int(role_id) for role_id in self.values]

        # Save selected roles to Firestore
        config = await self.firestore_cog.load_config(self.guild_id)
        config["role_restrictions"] = selected_roles
        await self.firestore_cog.save_config(self.guild_id, config)

        await interaction.response.send_message(
            "Role restrictions updated successfully!",
            ephemeral=True
        )

def setup(bot):
    bot.add_cog(RoleRestrictions(bot))
