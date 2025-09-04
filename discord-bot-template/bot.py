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
POKEMON_CHANNEL_ID = int(os.getenv("POKEMON_CHANNEL_ID", 0))  # Channel for Pokémon spawns

DATA_FILE = "notify_data.json"

# --- Discord bot setup ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- Twitch setup ---
TWITCH_ACCESS_TOKEN = None

def get_twitch_token():
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
    if TWITCH_ACCESS_TOKEN is None:
        get_twitch_token()
    return {
        "Client-ID": TWITCH_CLIENT_ID,
        "Authorization": f"Bearer {TWITCH_ACCESS_TOKEN}"
    }

# --- Persistence Helpers ---
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {"streamers": [], "youtube_channels": {}}

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump({"streamers": streamers, "youtube_channels": youtube_channels}, f)

# --- Joke & Meme loaders ---
def load_json_list(filename):
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

jokes = load_json_list("jokes.json")
memes = load_json_list("memes.json")

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

# --- Commands ---
@bot.command(name="joke")
async def joke(ctx):
    if jokes:
        await ctx.send(random.choice(jokes))
    else:
        await ctx.send("😢 No jokes loaded.")

@bot.command(name="meme")
async def meme(ctx):
    if memes:
        await ctx.send(random.choice(memes))
    else:
        await ctx.send("😢 No memes loaded.")

# Pokémon Game System
pokemon_spawning = False
pokemon_loop_task = None

async def pokemon_spawner():
    await bot.wait_until_ready()
    channel = bot.get_channel(POKEMON_CHANNEL_ID)
    if not channel:
        print("⚠️ Pokemon channel not found.")
        return
    while pokemon_spawning:
        await asyncio.sleep(random.randint(30, 90))
        pokemon = random.choice(["Pikachu", "Charmander", "Squirtle", "Bulbasaur"])
        await channel.send(f"A wild **{pokemon}** appeared! Type `!catch {pokemon}` to try and catch it!")

@bot.command(name="startpokemon")
@commands.has_permissions(manage_guild=True)
async def startpokemon(ctx):
    global pokemon_spawning, pokemon_loop_task
    if pokemon_spawning:
        await ctx.send("Pokémon spawns are already running!")
        return
    pokemon_spawning = True
    pokemon_loop_task = asyncio.create_task(pokemon_spawner())
    await ctx.send("🐾 Pokémon spawning has started!")

@bot.command(name="stoppokemon")
@commands.has_permissions(manage_guild=True)
async def stoppokemon(ctx):
    global pokemon_spawning, pokemon_loop_task
    if not pokemon_spawning:
        await ctx.send("Pokémon spawns are not running.")
        return
    pokemon_spawning = False
    if pokemon_loop_task:
        pokemon_loop_task.cancel()
    await ctx.send("🐾 Pokémon spawning has stopped!")

# --- Bot startup ---
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    twitch_notifier.start()

bot.run(DISCORD_TOKEN)
