# bot.py (Updated)
import os
from discord.ext import commands
from dotenv import load_dotenv
import asyncio
from enum import IntEnum
from discord import Intents, Game

class InteractionContextType(IntEnum):
    GUILD = 0
    BOT_DM = 1
    PRIVATE_CHANNEL = 2


# Import the reset_usage function
from cogs.reset_manager import reset_usage

# Load environment variables
load_dotenv()
TOKEN = os.getenv('DISCORD_RECRUITMENT_BOT_TOKEN')  # Your bot's token

# Define intents
from discord import Intents
intents = Intents.default()
intents.messages = True
intents.message_content = True
intents.voice_states = True  # Required for handling voice events
intents.guilds = True
intents.members = True

# Initialize the bot
bot = commands.Bot(command_prefix='/', intents=intents)

def load_cogs():
    try:
        bot.load_extension('cogs.firestore')
        bot.load_extension('cogs.recruitment')
        bot.load_extension('cogs.setup')
        bot.load_extension('cogs.upgrade')        # The new upgrade cog
        bot.load_extension('cogs.image_upload')   # The custom image cog
        bot.load_extension('cogs.entitlement_sync')
        bot.load_extension("cogs.role_restrictions")
        bot.load_extension('cogs.welcome')
        bot.load_extension("cogs.help")  # Add the Help cog here
        bot.load_extension('cogs.broadcast')  # Load the new broadcast cog
        bot.load_extension("cogs.check_entitle")
        print("Cogs loaded successfully.")
    except Exception as e:
        print(f"Failed to load cogs: {e}")

@bot.event
async def on_ready():
    print(f"Bot is online as {bot.user}")
    # Set the bot's status to "Beta V 0.1.0"
    await bot.change_presence(activity=Game(name="Beta V 0.1.0"))

    # Start the reset_usage task
    firestore_cog = bot.get_cog('FirestoreCog')
    if firestore_cog:
        bot.loop.create_task(reset_usage(firestore_cog))
        print("Reset usage task started.")
    else:
        print("FirestoreCog not found. Reset usage task not started.")

def main():
    load_cogs()  # Load cogs (including entitlement_sync) synchronously
    bot.run(TOKEN)  # Run the bot

if __name__ == "__main__":
    main()