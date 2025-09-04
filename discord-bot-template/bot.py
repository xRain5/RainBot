import os
import discord
from discord.ext import commands, tasks
import requests
import aiohttp
import asyncio
import random
import json

print("Bot starting up...")

# --- ENV VARS ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_SECRET = os.getenv("TWITCH_SECRET")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
NOTIFY_CHANNEL_ID = int(os.getenv("NOTIFY_CHANNEL_ID", 0))  # Discord channel for notifications

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

# --- Background task: Twitch live checker ---
@tasks.loop(minutes=2)
async def twitch_notifier():
    await bot.wait_until_ready()
    channel = bot.get_channel(NOTIFY_CHANNEL_ID)
    if not channel:
        return

    for username in streamers:
        url = "https://api.twitch.tv/helix/streams"
        resp = requests.get(url, headers=twitch_headers(), params={"user_login": username})
        data = resp.json()

        is_live = bool(data.get("data"))
        was_live = last_twitch_status.get(username, False)

        if is_live and not was_live:
            await channel.send(f"🎥 **{username} is LIVE on Twitch!** 👉 https://twitch.tv/{username}")

        last_twitch_status[username] = is_live

# --- Background task: YouTube new video checker -
