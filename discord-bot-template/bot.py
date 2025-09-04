import os
import discord
from discord.ext import commands, tasks
import requests
import aiohttp
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

    # Start background tasks
    if not twitch_notifier.is_running():
        twitch_notifier.start()
        print("⏰ Twitch notifier task started")

    if not youtube_notifier.is_running():
        youtube_notifier.start()
        print("⏰ YouTube notifier task started")

# --- Basic Commands ---
@bot.command()
async def ping(ctx):
    print("📩 Ping command received")
    await ctx.send("🏓 Pong!")

@bot.command()
async def roll(ctx, sides: int = 6):
    print(f"🎲 Roll command received with {sides} sides")
    result = random.randint(1, sides)
    await ctx.send(f"🎲 You rolled a **{result}** on a {sides}-sided die!")

@bot.command()
async def debug(ctx):
    """Shows raw debug info about tracked channels"""
    print("🐞 Debug command used")
    twitch_list = "\n".join(f"- {s}" for s in streamers) if streamers else "None"
    yt_list = "\n".join(f"- {n}: {cid}" for n, cid in youtube_channels.items()) if youtube_channels else "None"

    msg = (
        f"**📡 Debug Info:**\n"
        f"**Notify Channel ID:** {NOTIFY_CHANNEL_ID}\n\n"
        f"**🎥 Twitch Streamers:**\n{twitch_list}\n\n"
        f"**📺 YouTube Channels:**\n{yt_list}"
    )
    await ctx.send(msg)

@bot.command()
async def listchannels(ctx):
    """Show a clean list of tracked Twitch + YouTube channels"""
    print("📋 Listchannels command used")
    twitch_list = "\n".join(f"🎥 {s}" for s in streamers) if streamers else "None"
    yt_list = "\n".join(f"📺 {n}" for n in youtube_channels.keys()) if youtube_channels else "None"

    msg = (
        f"**📋 Currently Tracking:**\n\n"
        f"**Twitch:**\n{twitch_list}\n\n"
        f"**YouTube:**\n{yt_list}"
    )
    await ctx.send(msg)

@bot.command()
async def clearall(ctx, confirm: str = None):
    """Remove ALL tracked Twitch and YouTube channels (requires !clearall confirm)"""
    global streamers, youtube_channels
    if confirm != "confirm":
        await ctx.send("⚠️ This will erase ALL tracked channels! Type `!clearall confirm` to proceed.")
        return

    print("🗑️ Clearall command used with confirmation")
    streamers = []
    youtube_channels = {}
    save_data()
    await ctx.send("🧹 All tracked Twitch and YouTube channels have been cleared!")

# --- Twitch Management Commands ---
@bot.command()
async def addstreamer(ctx, username: str):
    """Add a Twitch streamer to track"""
    if username.lower() not in [s.lower() for s in streamers]:
        streamers.append(username)
        save_data()
        await ctx.send(f"✅ Added Twitch streamer: **{username}**")
    else:
        await ctx.send(f"⚠️ {username} is already being tracked.")

@bot.command()
async def removestreamer(ctx, username: str):
    """Remove a Twitch streamer"""
    if username in streamers:
        streamers.remove(username)
        save_data()
        await ctx.send(f"🗑️ Removed Twitch streamer: **{username}**")
    else:
        await ctx.send(f"⚠️ {username} is not in the tracking list.")

# --- Helper: Resolve YouTube handle to channelId ---
async def resolve_youtube_channel(identifier: str):
    """Resolve @handle to (channelId, title, customUrl)"""
    if identifier.startswith("@"):
        print(f"🔎 Resolving YouTube handle {identifier}")
        url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&type=channel&q={identifier}&key={YOUTUBE_API_KEY}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    print(f"❌ Failed to resolve handle {identifier}, status {resp.status}")
                    return None, None, None
                data = await resp.json()
                if "items" in data and len(data["items"]) > 0:
                    item = data["items"][0]
                    channel_id = item["snippet"]["channelId"]
                    title = item["snippet"]["title"]
                    custom_url = f"https://www.youtube.com/channel/{channel_id}"
                    return channel_id, title, custom_url
        return None, None, None
    # If it's already a channelId
    return identifier, None, f"https://www.youtube.com/channel/{identifier}"

# --- YouTube Management Commands ---
@bot.command()
async def addyoutube(ctx, name: str, identifier: str):
    """Add a YouTube channel (name + channelId or @handle)"""
    channel_id, title, link = await resolve_youtube_channel(identifier)
    if not channel_id:
        await ctx.send(f"❌ Could not resolve YouTube channel: {identifier}")
        return
    youtube_channels[name] = channel_id
    save_data()
    display_name = title or name
    await ctx.send(f"✅ Added YouTube channel: **{display_name}**\n🔗 {link}")

@bot.command()
async def removeyoutube(ctx, name: str):
    """Remove a YouTube channel by name"""
    if name in youtube_channels:
        del youtube_channels[name]
        save_data()
        await ctx.send(f"🗑️ Removed YouTube channel: **{name}**")
    else:
        await ctx.send(f"⚠️ {name} is not being tracked.")

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
