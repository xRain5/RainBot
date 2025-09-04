import os
import discord
from discord.ext import commands, tasks
import requests
import aiohttp
import asyncio
import random
import json
from discord.ext.commands import CommandOnCooldown

print("Bot starting up...")

# --- ENV VARS ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_SECRET = os.getenv("TWITCH_SECRET")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
NOTIFY_CHANNEL_ID = int(os.getenv("NOTIFY_CHANNEL_ID", 0))  # Discord channel for notifications
POKEMON_CHANNEL_ID = int(os.getenv("POKEMON_CHANNEL_ID", 0))  # Channel for Pokémon spawns
GUILD_ID = int(os.getenv("GUILD_ID", 0))  # Server ID for assigning roles

DATA_FILE = "notify_data.json"

# --- Discord bot setup ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- Twitch setup ---
TWITCH_ACCESS_TOKEN = None

def get_twitch_token():
    """Fetch a new Twitch OAuth token"""
    global TWITCH_ACCESS_TOKEN
    url = "https://id.twitch.tv/oauth2/token"
    params = {
        "client_id": TWITCH_CLIENT_ID,
        "client_secret": TWITCH_SECRET,
        "grant_type": "client_credentials"
    }
    resp = requests.post(url, params=params)
    data = resp.json()
    TWITCH_ACCESS_TOKEN = data["access_token"]
    return TWITCH_ACCESS_TOKEN

def twitch_headers():
    """Return headers with token"""
    if TWITCH_ACCESS_TOKEN is None:
        get_twitch_token()
    return {
        "Client-ID": TWITCH_CLIENT_ID,
        "Authorization": f"Bearer {TWITCH_ACCESS_TOKEN}"
    }

# --- Persistence Helpers ---
def load_data():
    """Load notify data from file"""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {"streamers": [], "youtube_channels": {}}

def save_data():
    """Save notify data to file"""
    with open(DATA_FILE, "w") as f:
        json.dump({"streamers": streamers, "youtube_channels": youtube_channels}, f)

# Load initial data
data = load_data()
streamers = data["streamers"]
youtube_channels = data["youtube_channels"]

# --- Store last notified states ---
last_twitch_status = {}
last_youtube_video = {}

# =========================
# Admin Commands
# =========================
@bot.command(name="addstreamer")
@commands.has_permissions(manage_guild=True)
async def add_streamer(ctx, twitch_name: str):
    """Add a Twitch streamer for notifications"""
    twitch_name = twitch_name.lower()
    if twitch_name in streamers:
        await ctx.send(f"⚠️ **{twitch_name}** is already in the Twitch notifications list.")
        return
    streamers.append(twitch_name)
    save_data()
    await ctx.send(f"✅ Added **{twitch_name}** to Twitch notifications.")

@bot.command(name="addyoutube")
@commands.has_permissions(manage_guild=True)
async def add_youtube(ctx, channel_id: str):
    """Add a YouTube channel for notifications"""
    if channel_id in youtube_channels:
        await ctx.send(f"⚠️ Channel `{channel_id}` is already in YouTube notifications.")
        return
    youtube_channels[channel_id] = channel_id
    save_data()
    await ctx.send(f"✅ Added YouTube channel `{channel_id}` for notifications.")

# =========================
# Fun commands
# =========================
@bot.command()
async def joke(ctx):
    """Tell a random joke"""
    jokes = [
        "Why don’t skeletons ever fight each other? They don’t have the guts!",
        "I told my computer I needed a break, and it froze.",
        "Why did the gamer cross the road? To get to the next level!",
    ]
    await ctx.send(random.choice(jokes))

@bot.command()
async def roll(ctx, sides: int = 6):
    """Roll a dice"""
    result = random.randint(1, sides)
    await ctx.send(f"🎲 You rolled a {result} on a {sides}-sided dice!")

# =========================
# Auto-updating Help Menus
# =========================
@bot.command(name="commands")
@commands.cooldown(1, 30, commands.BucketType.user)
async def commands_list(ctx):
    """Show a list of available commands for regular users."""
    embed = discord.Embed(
        title="📖 Available Commands",
        description="Here are the commands you can use:",
        color=discord.Color.blue()
    )
    user_cmds = [
        "`!joke` - Get a random joke",
        "`!roll [sides]` - Roll a dice",
        "`!catch <pokemon>` - Try catching a Pokémon",
    ]
    embed.add_field(name="🎮 Fun", value="\n".join(user_cmds), inline=False)

    try:
        await ctx.author.send(embed=embed)
        await ctx.send("📬 I've sent you a DM with the list of commands!")
    except discord.Forbidden:
        await ctx.send(embed=embed)

@bot.command(name="admincommands")
@commands.has_permissions(manage_guild=True)
@commands.cooldown(1, 30, commands.BucketType.user)
async def admin_commands(ctx):
    """Show a list of admin-only commands."""
    embed = discord.Embed(
        title="⚙️ Admin Commands",
        description="Moderator-only commands:",
        color=discord.Color.red()
    )
    admin_cmds = [
        "`!addstreamer <twitch_name>` - Add a Twitch streamer for notifications",
        "`!addyoutube <channel_id>` - Add a YouTube channel for notifications",
        "`!startpokemon` - Start Pokémon spawns",
        "`!stoppokemon` - Stop Pokémon spawns",
    ]
    embed.add_field(name="🛠️ Moderation", value="\n".join(admin_cmds), inline=False)

    try:
        await ctx.author.send(embed=embed)
        await ctx.send("📬 I've sent you a DM with the list of admin commands!")
    except discord.Forbidden:
        await ctx.send(embed=embed)

# =========================
# Error handler for cooldowns
# =========================
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, CommandOnCooldown):
        await ctx.send(f"⏳ Please wait {error.retry_after:.1f}s before using this command again.", delete_after=5)
    elif isinstance(error, commands.CommandNotFound):
        await ctx.send("❌ That command doesn’t exist. Try `!commands` to see available ones.", delete_after=5)
    else:
        raise error

# =========================
# Run bot
# =========================
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

bot.run(DISCORD_TOKEN)
