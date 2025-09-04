import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import random

# Load .env file (for local testing)
load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

# Simple command: roll a dice
@bot.command()
async def roll(ctx, sides: int = 6):
    result = random.randint(1, sides)
    await ctx.send(f"🎲 You rolled a {result}!")

# Run bot using token from .env or Railway
bot.run(os.getenv("DISCORD_TOKEN"))
