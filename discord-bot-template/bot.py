import os
import requests
import discord
from discord.ext import commands

# Load environment variables
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_SECRET = os.getenv("TWITCH_SECRET")

# Twitch token storage
TWITCH_ACCESS_TOKEN = None

def get_twitch_token():
    """Fetch a new Twitch OAuth token using Client Credentials flow."""
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
    print("✅ Got Twitch token")
    return TWITCH_ACCESS_TOKEN

def twitch_headers():
    """Return headers with current token (refresh if needed)."""
    if TWITCH_ACCESS_TOKEN is None:
        get_twitch_token()
    return {
        "Client-ID": TWITCH_CLIENT_ID,
        "Authorization": f"Bearer {TWITCH_ACCESS_TOKEN}"
    }

# Discord bot setup
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"🤖 Logged in as {bot.user}")
    get_twitch_token()  # Grab a token on startup

@bot.command()
async def twitchcheck(ctx, username: str):
    """Check if a Twitch streamer is live."""
    url = "https://api.twitch.tv/helix/streams"
    resp = requests.get(url, headers=twitch_headers(), params={"user_login": username})
    data = resp.json()

    if data.get("data"):
        await ctx.send(f"🎥 {username} is **LIVE** on Twitch!")
    else:
        await ctx.send(f"❌ {username} is not live right now.")

bot.run(DISCORD_TOKEN)
