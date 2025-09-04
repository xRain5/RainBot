import os
import discord
from discord.ext import commands, tasks
import requests
import aiohttp
import asyncio
import random
import json
import traceback

print("🚀 Bot starting up...")

# --- ENV VARS ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_SECRET = os.getenv("TWITCH_SECRET")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
NOTIFY_CHANNEL_ID = int(os.getenv("NOTIFY_CHANNEL_ID", 0))  # Discord channel for notifications

if not DISCORD_TOKEN:
    print("❌ ERROR: DISCORD_TOKEN is missing! Did you set it in Railway Variables?")
    exit(1)

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
    print("🔑 Fetching new Twitch token...")
    url = "https://id.twitch.tv/oauth2/token"
    params = {
        "client_id": TWITCH_CLIENT_ID,
        "client_secret": TWITCH_SECRET,
        "grant_type": "client_credentials"
    }
    try:
        resp = requests.post(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        TWITCH_ACCESS_TOKEN = data["access_token"]
        print("✅ Twitch token fetched successfully")
        return TWITCH_ACCESS_TOKEN
    except Exception as e:
        print("❌ Failed to fetch Twitch token:", e)
        traceback.print_exc()
        return None

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
            print("📂 Loading notify_data.json")
            return json.load(f)
    print("📂 No notify_data.json found, starting fresh")
    return {"streamers": [], "youtube_channels": {}}

def save_data():
    """Save notify data to file"""
    with open(DATA_FILE, "w") as f:
        json.dump({"streamers": streamers, "youtube_channels": youtube_channels}, f)
    print("💾 Saved notify data to file")

# Load initial data
data = load_data()
streamers = data["streamers"]
youtube_channels = data["youtube_channels"]

# --- Store last notified states ---
last_twitch_status = {}
last_youtube_video = {}

# --- Events ---
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    print("📡 Bot is ready and listening for commands!")

# --- Commands for testing ---
@bot.command()
async def ping(ctx):
    print("📩 Ping command received")
    await ctx.send("🏓 Pong!")

@bot.command()
async def roll(ctx, sides: int = 6):
    print(f"🎲 Roll command received with {sides} sides")
    result = random.randint(1, sides)
    await ctx.send(f"🎲 You rolled a **{result}** on a {sides}-sided die!")

# --- Background task: Twitch live checker ---
@tasks.loop(minutes=2)
async def twitch_notifier():
    await bot.wait_until_ready()
    print("🔎 Checking Twitch streamers...")
    channel = bot.get_channel(NOTIFY_CHANNEL_ID)
    if not channel:
        print("⚠️ Could not find notify channel, check NOTIFY_CHANNEL_ID")
        return

    for username in streamers:
        print(f"➡️ Checking Twitch streamer: {username}")
        try:
            url = "https://api.twitch.tv/helix/streams"
            resp = requests.get(url, headers=twitch_headers(), params={"user_login": username})
            resp.raise_for_status()
            data = resp.json()

            is_live = bool(data.get("data"))
            was_live = last_twitch_status.get(username, False)

            if is_live and not was_live:
                print(f"📢 {username} went live! Sending notification...")
                await channel.send(f"🎥 **{username} is LIVE on Twitch!** 👉 https://twitch.tv/{username}")

            last_twitch_status[username] = is_live
        except Exception as e:
            print(f"❌ Error checking Twitch streamer {username}:", e)
            traceback.print_exc()

# --- Background task: YouTube new video checker ---
@tasks.loop(minutes=5)
async def youtube_notifier():
    await bot.wait_until_ready()
    print("🔎 Checking YouTube channels...")
    channel = bot.get_channel(NOTIFY_CHANNEL_ID)
    if not channel:
        print("⚠️ Could not find notify channel, check NOTIFY_CHANNEL_ID")
        return

    for name, channel_id in youtube_channels.items():
        print(f"➡️ Checking YouTube channel: {name} ({channel_id})")
        try:
            url = f"https://www.googleapis.com/youtube/v3/search?key={YOUTUBE_API_KEY}&channelId={channel_id}&part=snippet,id&order=date&maxResults=1"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        print(f"❌ YouTube API error {resp.status}")
                        continue
                    data = await resp.json()

            if "items" in data and len(data["items"]) > 0:
                video = data["items"][0]
                video_id = video["id"].get("videoId")
                title = video["snippet"]["title"]

                last_id = last_youtube_video.get(channel_id)
                if video_id and video_id != last_id:
                    print(f"📢 New video found for {name}: {title}")
                    await channel.send(f"📺 **{name} uploaded a new video!** 🎬 {title}\n👉 https://youtu.be/{video_id}")
                    last_youtube_video[channel_id] = video_id
        except Exception as e:
            print(f"❌ Error checking YouTube channel {name}:", e)
            traceback.print_exc()

# --- Run bot with crash handling ---
try:
    print("▶️ Starting bot.run()...")
    bot.run(DISCORD_TOKEN)
except Exception as e:
    print("❌ Bot crashed with error:")
    traceback.print_exc()
