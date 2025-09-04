import os
import discord
from discord.ext import commands, tasks
import requests
import aiohttp
import asyncio

# --- ENV VARS ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_SECRET = os.getenv("TWITCH_SECRET")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
NOTIFY_CHANNEL_ID = int(os.getenv("NOTIFY_CHANNEL_ID", 0))  # Discord channel for notifications

# --- Discord bot setup ---
intents = discord.Intents.default()
intents.message_content = True  # Needed for command reading
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

    streamers = ["example_streamer"]  # Replace with Twitch usernames

    for username in streamers:
        url = "https://api.twitch.tv/helix/streams"
        resp = requests.get(url, headers=twitch_headers(), params={"user_login": username})
        data = resp.json()

        is_live = bool(data.get("data"))
        was_live = last_twitch_status.get(username, False)

        if is_live and not was_live:
            await channel.send(f"🎥 **{username} is LIVE on Twitch!** 👉 https://twitch.tv/{username}")

        last_twitch_status[username] = is_live

# --- Background task: YouTube new video checker ---
@tasks.loop(minutes=5)
async def youtube_notifier():
    await bot.wait_until_ready()
    channel = bot.get_channel(NOTIFY_CHANNEL_ID)
    if not channel:
        return

    youtube_channels = {
        "ExampleChannel": "UCxxxxxxxxxxxxxxx"  # Replace with real channel IDs
    }

    for name, channel_id in youtube_channels.items():
        url = f"https://www.googleapis.com/youtube/v3/search?key={YOUTUBE_API_KEY}&channelId={channel_id}&part=snippet,id&order=date&maxResults=1"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()

        if "items" in data:
            latest_video = data["items"][0]
            video_id = latest_video["id"].get("videoId")

            if video_id and last_youtube_video.get(channel_id) != video_id:
                last_youtube_video[channel_id] = video_id
                video_url = f"https://youtube.com/watch?v={video_id}"
                await channel.send(f"📺 New video from **{name}**! 👉 {video_url}")

# --- Example Moderation Command ---
@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason="No reason provided"):
    await member.kick(reason=reason)
    await ctx.send(f"👢 {member.mention} was kicked. Reason: {reason}")

# --- Example Game Command ---
import random
@bot.command()
async def roll(ctx, sides: int = 6):
    result = random.randint(1, sides)
    await ctx.send(f"🎲 You rolled a **{result}** on a {sides}-sided die!")

# --- Startup ---
@bot.event
async def on_ready():
    print(f"🤖 Logged in as {bot.user}")
    get_twitch_token()
    twitch_notifier.start()
    youtube_notifier.start()

bot.run(DISCORD_TOKEN)
