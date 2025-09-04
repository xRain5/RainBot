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
POKEMON_FILE = "pokemon_data.json"

# --- Discord bot setup ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- Persistence Helpers (notify system) ---
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {"streamers": [], "youtube_channels": {}}

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump({"streamers": streamers, "youtube_channels": youtube_channels}, f)

# --- Persistence Helpers (Pokémon system) ---
def load_pokemon_data():
    if os.path.exists(POKEMON_FILE):
        with open(POKEMON_FILE, "r") as f:
            return json.load(f)
    return {"pokedex": {}, "streaks": {}}

def save_pokemon_data():
    with open(POKEMON_FILE, "w") as f:
        json.dump({"pokedex": pokedex, "streaks": streaks}, f)

# Load initial data
data = load_data()
streamers = data["streamers"]
youtube_channels = data["youtube_channels"]

poke_data = load_pokemon_data()
pokedex = poke_data["pokedex"]  # user_id -> list of caught Pokémon
streaks = poke_data["streaks"]  # user_id -> streak count

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

# --- Store last notified states ---
last_twitch_status = {}
last_youtube_video = {}

# =========================
# Admin Commands
# =========================
@bot.command(name="addstreamer")
@commands.has_permissions(manage_guild=True)
async def add_streamer(ctx, twitch_name: str):
    twitch_name = twitch_name.lower()
    if twitch_name in streamers:
        await ctx.send(f"⚠️ **{twitch_name}** is already in the Twitch list.")
        return
    streamers.append(twitch_name)
    save_data()
    await ctx.send(f"✅ Added **{twitch_name}** to Twitch notifications.")

@bot.command(name="addyoutube")
@commands.has_permissions(manage_guild=True)
async def add_youtube(ctx, channel_id: str):
    if channel_id in youtube_channels:
        await ctx.send(f"⚠️ Channel `{channel_id}` is already in YouTube list.")
        return
    youtube_channels[channel_id] = channel_id
    save_data()
    await ctx.send(f"✅ Added YouTube channel `{channel_id}`.")

# =========================
# Fun commands
# =========================
@bot.command()
async def joke(ctx):
    jokes = [
        "Why don’t skeletons ever fight each other? They don’t have the guts!",
        "I told my computer I needed a break, and it froze.",
        "Why did the gamer cross the road? To get to the next level!",
    ]
    await ctx.send(random.choice(jokes))

@bot.command()
async def roll(ctx, sides: int = 6):
    result = random.randint(1, sides)
    await ctx.send(f"🎲 You rolled a {result} on a {sides}-sided dice!")

# =========================
# Pokémon Game System
# =========================
pokemon_spawning = False
pokemon_loop_task = None
active_pokemon = None  # currently spawned

POKEMON_RARITIES = {
    "common": ["Pidgey", "Rattata", "Caterpie", "Zubat"],
    "uncommon": ["Eevee", "Vulpix", "Sandshrew"],
    "rare": ["Snorlax", "Lapras", "Dratini"],
    "legendary": ["Mewtwo"]
}
CATCH_RATES = {
    "common": 0.8,
    "uncommon": 0.5,
    "rare": 0.3,
    "legendary": 0.1
}

async def pokemon_spawner():
    global active_pokemon
    await bot.wait_until_ready()
    channel = bot.get_channel(POKEMON_CHANNEL_ID)
    if not channel:
        print("⚠️ Pokémon channel not found.")
        return
    while pokemon_spawning:
        await asyncio.sleep(random.randint(30, 90))
        rarity = random.choices(list(POKEMON_RARITIES.keys()), weights=[70, 20, 9, 1])[0]
        pokemon = random.choice(POKEMON_RARITIES[rarity])
        active_pokemon = (pokemon, rarity)
        await channel.send(f"A wild **{pokemon}** ({rarity}) appeared! Type `!catch {pokemon}` to try and catch it!")

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

@bot.command(name="catch")
async def catch(ctx, *, name: str):
    global active_pokemon
    if not active_pokemon:
        await ctx.send("❌ There is no Pokémon to catch right now!")
        return
    pokemon, rarity = active_pokemon
    if name.lower() != pokemon.lower():
        await ctx.send(f"❌ That’s not the Pokémon! The wild Pokémon escaped...")
        active_pokemon = None
        return
    chance = CATCH_RATES[rarity]
    user_id = str(ctx.author.id)
    if random.random() <= chance:
        pokedex.setdefault(user_id, []).append(pokemon)
        streaks[user_id] = streaks.get(user_id, 0) + 1
        save_pokemon_data()
        msg = f"✅ {ctx.author.mention} caught **{pokemon}** ({rarity})!"
        if streaks[user_id] >= 3:
            msg += f" 🔥 {ctx.author.display_name} is on fire with {streaks[user_id]} catches in a row!"
        await ctx.send(msg)
    else:
        streaks[user_id] = 0
        save_pokemon_data()
        await ctx.send(f"💨 The wild {pokemon} escaped {ctx.author.mention}!")
    active_pokemon = None

# =========================
# Help menus
# =========================
@bot.command(name="commands")
@commands.cooldown(1, 30, commands.BucketType.user)
async def commands_list(ctx):
    embed = discord.Embed(
        title="📖 Available Commands",
        color=discord.Color.blue()
    )
    embed.add_field(name="🎮 Fun", value="`!joke`, `!roll [sides]`", inline=False)
    embed.add_field(name="🐾 Pokémon", value="`!catch <pokemon>`", inline=False)
    try:
        await ctx.author.send(embed=embed)
        await ctx.send("📬 I've sent you a DM with the list of commands!")
    except discord.Forbidden:
        await ctx.send(embed=embed)

@bot.command(name="admincommands")
@commands.has_permissions(manage_guild=True)
@commands.cooldown(1, 30, commands.BucketType.user)
async def admin_commands(ctx):
    embed = discord.Embed(
        title="⚙️ Admin Commands",
        color=discord.Color.red()
    )
    embed.add_field(name="🛠️ Moderation", value="`!addstreamer`, `!addyoutube`", inline=False)
    embed.add_field(name="🐾 Pokémon Control", value="`!startpokemon`, `!stoppokemon`", inline=False)
    try:
        await ctx.author.send(embed=embed)
        await ctx.send("📬 I've sent you a DM with the list of admin commands!")
    except discord.Forbidden:
        await ctx.send(embed=embed)

# =========================
# Error handler
# =========================
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, CommandOnCooldown):
        await ctx.send(f"⏳ Please wait {error.retry_after:.1f}s before using this command again.", delete_after=5)
    elif isinstance(error, commands.CommandNotFound):
        await ctx.send("❌ That command doesn’t exist. Try `!commands`.", delete_after=5)
    else:
        raise error

# =========================
# Bot startup
# =========================
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

bot.run(DISCORD_TOKEN)
