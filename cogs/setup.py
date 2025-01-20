# cogs/setup.py
import discord
from discord.ext import commands
from discord.ui import View, Select, button

class Config:
    """A class to hold the configuration data for a server."""
    def __init__(self, guild, bot):
        self.guild = guild
        self.bot = bot
        self.notify_channel_id = None
        self.use_mention = False
        self.selected_recruitment_channel_id = None
        self.selected_category_id = None

class SetupScoutMaster(commands.Cog):
    """Cog for setting up Scout Master configurations."""

    def __init__(self, bot):
        self.bot = bot
        print("SetupScoutMaster cog initialized.")

    @commands.slash_command(
        name="setup_scout_master",
        description="Configure the Scout Master settings for this server."
    )
    @commands.has_permissions(administrator=True)
    async def setup_scout_master(self, interaction: discord.Interaction):
        """Initiates the setup process."""
        await interaction.response.defer(ephemeral=True)
        # Initialize the Config with guild and bot
        config = Config(interaction.guild, self.bot)
        # Initialize the SetupChannelSelectView with the config
        view = SetupChannelSelectView(config)
        await interaction.followup.send(
            "Let's configure your Scout Master settings. Please select the notification channel\n\n"
            "**This is where Scout Master will let your server know who started a gaming session!**",
            view=view,
            ephemeral=True,
        )

    @setup_scout_master.error
    async def setup_scout_master_error(self, interaction: discord.Interaction, error: commands.CommandError):
        """Error handler for the setup_scout_master command."""
        if isinstance(error, commands.MissingPermissions):
            await interaction.response.send_message(
                "You need Administrator permissions to run this command.",
                ephemeral=True
            )
            print(
                f"User {interaction.user} attempted to use /setup_scout_master without Administrator permissions."
            )
        else:
            await interaction.response.send_message(
                "An unexpected error occurred while executing the command. Please try again later.",
                ephemeral=True
            )
            print(f"Unexpected error in /setup_scout_master: {error}")

class SetupChannelSelectView(View):
    """View to select the notification channel."""

    def __init__(self, config):
        super().__init__(timeout=300)  # 5 minutes timeout
        self.config = config
        guild = config.guild
        if not guild.text_channels:
            # Handle case with no text channels
            self.add_item(discord.ui.Button(
                label="No Text Channels Found",
                style=discord.ButtonStyle.red,
                disabled=True
            ))
            return
        self.notification_channels = [
            discord.SelectOption(label=channel.name, value=str(channel.id))
            for channel in guild.text_channels
        ]
        # Add the dropdown menu with the populated options
        self.add_item(NotificationChannelSelect(self.notification_channels, self.config))

    async def on_timeout(self):
        print("SetupChannelSelectView timed out.")

class NotificationChannelSelect(Select):
    """Select component for choosing the notification channel."""

    def __init__(self, options, config):
        super().__init__(
            placeholder="Select the notification channel...",
            min_values=1,
            max_values=1,
            options=options
        )
        self.config = config

    async def callback(self, interaction: discord.Interaction):
        # Store the selected notification channel ID
        self.config.notify_channel_id = int(self.values[0])
        await interaction.response.send_message(
            "Do you want to use `@everyone` mentions in notifications?",
            view=MentionPreferenceView(self.config),
            ephemeral=True
        )

class MentionPreferenceView(View):
    """View to select whether to use @everyone mentions."""

    def __init__(self, config):
        super().__init__(timeout=300)
        self.config = config

    @button(label="Yes, use @everyone", style=discord.ButtonStyle.green)
    async def use_mention_yes(self, button: discord.Button, interaction: discord.Interaction):
        self.config.use_mention = True
        await interaction.response.send_message(
            "Great! Now, please select the recruitment channel\n\n"
            "**This is where the recruitment message will be sent too**",
            view=RecruitmentChannelSelectView(self.config),
            ephemeral=True
        )
        self.stop()

    @button(label="No, skip mentions", style=discord.ButtonStyle.red)
    async def use_mention_no(self, button: discord.Button, interaction: discord.Interaction):
        self.config.use_mention = False
        await interaction.response.send_message(
            "Understood! Now, please select the recruitment channel\n\n"
            "**This is where the recruitment message will be sent too**",
            view=RecruitmentChannelSelectView(self.config),
            ephemeral=True
        )
        self.stop()

    async def on_timeout(self):
        print("MentionPreferenceView timed out.")

class RecruitmentChannelSelectView(View):
    """View to select the recruitment channel."""

    def __init__(self, config):
        super().__init__(timeout=300)
        self.config = config
        guild = config.guild
        # Populate channels excluding the previously selected notification channel
        self.recruitment_channels = [
            discord.SelectOption(label=channel.name, value=str(channel.id))
            for channel in guild.text_channels
            if channel.id != config.notify_channel_id
        ]

        if not self.recruitment_channels:
            # Handle case with no eligible recruitment channels
            self.add_item(discord.ui.Button(
                label="No Eligible Recruitment Channels Found",
                style=discord.ButtonStyle.red,
                disabled=True
            ))
            return

        self.add_item(RecruitmentChannelSelect(self.recruitment_channels, self.config))

    async def on_timeout(self):
        print("RecruitmentChannelSelectView timed out.")

class RecruitmentChannelSelect(Select):
    """Select component for choosing the recruitment channel."""

    def __init__(self, options, config):
        super().__init__(
            placeholder="Select the recruitment channel...",
            min_values=1,
            max_values=1,
            options=options
        )
        self.config = config

    async def callback(self, interaction: discord.Interaction):
        self.config.selected_recruitment_channel_id = int(self.values[0])
        await interaction.response.send_message(
            "Please select the category for the voice channels to be created in\n\n"
            "**Scout Master creates temporary voice channels under the selected category**",
            view=CategorySelectView(self.config),
            ephemeral=True
        )

class CategorySelectView(View):
    """View to select the category for gaming sessions."""

    def __init__(self, config):
        super().__init__(timeout=300)
        self.config = config
        guild = config.guild
        # Populate categories
        self.categories = [
            discord.SelectOption(label=category.name, value=str(category.id))
            for category in guild.categories
        ]

        if not self.categories:
            # Handle case with no categories
            self.add_item(discord.ui.Button(
                label="No Categories Found",
                style=discord.ButtonStyle.red,
                disabled=True
            ))
            return

        self.add_item(CategorySelect(self.categories, self.config))

    async def callback(self, interaction: discord.Interaction):
        self.config.selected_category_id = int(self.values[0])
        await interaction.response.send_message(
            "🎉 Setup complete! Your Scout Master settings have been configured. \n\n"
            "Members can now use </recruit:1330805308125347906> to start a gaming session! 🥳 Let them know!.🥳 ",
            ephemeral=True
        )
        # Save the configurations to Firestore
        firestore_cog = self.config.bot.get_cog('FirestoreCog')
        if not firestore_cog:
            await interaction.followup.send(
                "Internal error: FirestoreCog not found.",
                ephemeral=True
            )
            return

        guild_id = self.config.guild.id
        config_data = {
            "notify_channel_id": self.config.notify_channel_id,
            "use_mention": self.config.use_mention,
            "allowed_channel_id": self.config.selected_recruitment_channel_id,
            "category_id": self.config.selected_category_id
            # Removed 'cooldown' and 'timeout'
        }

        await firestore_cog.save_config(guild_id, config_data)
        print(f"Configuration for guild {guild_id} saved.")

class CategorySelect(Select):
    """Select component for choosing the category."""

    def __init__(self, options, config):
        super().__init__(
            placeholder="Select the category...",
            min_values=1,
            max_values=1,
            options=options
        )
        self.config = config

    async def callback(self, interaction: discord.Interaction):
        self.config.selected_category_id = int(self.values[0])
        await interaction.response.send_message(
            "How many gaming sessions do you want to allow your members to do per day?",
            view=UserUsageLimitSelectView(self.config),
            ephemeral=True
        )
        # Save the configurations to Firestore
        firestore_cog = self.config.bot.get_cog('FirestoreCog')
        if not firestore_cog:
            await interaction.followup.send(
                "Internal error: FirestoreCog not found.",
                ephemeral=True
            )
            return

        guild_id = self.config.guild.id
        config_data = {
            "notify_channel_id": self.config.notify_channel_id,
            "use_mention": self.config.use_mention,
            "allowed_channel_id": self.config.selected_recruitment_channel_id,
            "category_id": self.config.selected_category_id
            # Removed 'cooldown' and 'timeout'
        }

        await firestore_cog.save_config(guild_id, config_data)
        print(f"Configuration for guild {guild_id} saved.")

class UserUsageLimitSelectView(View):
    """View to select the daily usage limit for users."""

    def __init__(self, config):
        super().__init__(timeout=300)
        self.config = config

        # Options for user usage limits
        self.add_item(UserUsageLimitSelect())

    async def on_timeout(self):
        print("UserUsageLimitSelectView timed out.")

class UserUsageLimitSelect(Select):
    """Dropdown to select the daily usage limit per user."""

    def __init__(self):
        super().__init__(
            placeholder="Select the daily usage limit per user...",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label=str(i), value=str(i)) for i in range(1, 11)
            ],
        )

    async def callback(self, interaction: discord.Interaction):
        limit = int(self.values[0])
        self.view.config.user_usage_limit = limit
        await interaction.response.send_message(
            f"Daily usage limit set to {limit}.\n\n"
            "Members can now use </recruit:1330805308125347906> to start a gaming session! 🥳 Let them know!.🥳 ",
            ephemeral=True
        )
        # Save the settings to Firestore
        firestore_cog = self.view.config.bot.get_cog("FirestoreCog")
        if not firestore_cog:
            await interaction.followup.send(
                "Internal error: FirestoreCog not found.",
                ephemeral=True,
            )
            return

        guild_id = self.view.config.guild.id
        config_data = {
            "notify_channel_id": self.view.config.notify_channel_id,
            "use_mention": self.view.config.use_mention,
            "allowed_channel_id": self.view.config.selected_recruitment_channel_id,
            "category_id": self.view.config.selected_category_id,
            "user_usage_limit": self.view.config.user_usage_limit,
        }

        await firestore_cog.save_config(guild_id, config_data)
        print(f"Configuration for guild {guild_id} saved.")




def setup(bot):
    bot.add_cog(SetupScoutMaster(bot))
