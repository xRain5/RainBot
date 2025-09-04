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

# --- Data file paths ---
NOTIFY_FILE = "notify_data.json"
POKEMON_FILE = "pokemon_data.json"

# --- Discord bot setup ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# =========================
# Persistence Helpers
# =========================
def load_notify_data():
    if os.path.exists(NOTIFY_FILE):
        with open(NOTIFY_FILE, "r") as f:
            return json.load(f)
    return {"streamers": [], "youtube_channels": {}}

def save_notify_data():
    with open(NOTIFY_FILE, "w") as f:
        json.dump({"streamers": streamers, "youtube_channels": youtube_channels}, f, indent=2)

def load_pokemon_data():
    if os.path.exists(POKEMON_FILE):
        with open(POKEMON_FILE, "r") as f:
            return json.load(f)
    return {"pokedex": {}, "streaks": {}}

def save_pokemon_data():
    with open(POKEMON_FILE, "w") as f:
        json.dump({"pokedex": pokedex, "streaks": streaks}, f, indent=2)

# --- Load initial data ---
notify_data = load_notify_data()
streamers = notify_data["streamers"]
youtube_channels = notify_data["youtube_channels"]

poke_data = load_pokemon_data()
pokedex = poke_data["pokedex"]  # user_id -> list of caught Pokémon
streaks = poke_data["streaks"]  # user_id -> streak count

# =========================
# Twitch setup
# =========================
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
    save_notify_data()
    await ctx.send(f"✅ Added **{twitch_name}** to Twitch notifications.")

@bot.command(name="addyoutube")
@commands.has_permissions(manage_guild=True)
async def add_youtube(ctx, channel_id: str):
    if channel_id in youtube_channels:
        await ctx.send(f"⚠️ Channel `{channel_id}` is already in YouTube list.")
        return
    youtube_channels[channel_id] = channel_id
    save_notify_data()
    await ctx.send(f"✅ Added YouTube channel `{channel_id}`.")

@bot.command(name="resetpokedex")
@commands.has_permissions(manage_guild=True)
async def reset_pokedex(ctx, member: discord.Member):
    user_id = str(member.id)
    if user_id in pokedex:
        pokedex[user_id] = []
        save_pokemon_data()
        await ctx.send(f"🗑️ Pokédex reset for {member.display_name}.")
    else:
        await ctx.send(f"⚠️ {member.display_name} has no Pokédex to reset.")

@bot.command(name="resetstreak")
@commands.has_permissions(manage_guild=True)
async def reset_streak(ctx, member: discord.Member):
    user_id = str(member.id)
    if user_id in streaks:
        streaks[user_id] = 0
        save_pokemon_data()
        await ctx.send(f"🛑 Streak reset for {member.display_name}.")
    else:
        await ctx.send(f"⚠️ {member.display_name} had no streak to reset.")

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

# Gen 1 Pokémon split into rarity tiers
POKEMON_RARITIES = {
    "common": [
        "Pidgey", "Rattata", "Caterpie", "Weedle", "Zubat", "Spearow", "Oddish", "Poliwag",
        "Machop", "Geodude", "Krabby", "Magnemite", "Voltorb", "Tentacool", "Sandshrew",
        "Ekans", "Paras", "Diglett", "Meowth", "Doduo"
    ],
    "uncommon": [
        "Pikachu", "Clefairy", "Vulpix", "Jigglypuff", "Growlithe", "Abra", "Bellsprout",
        "Slowpoke", "Seel", "Gastly", "Drowzee", "Horsea", "Cubone", "Koffing", "Rhyhorn",
        "Exeggcute", "Chansey", "Eevee", "Omanyte", "Kabuto"
    ],
    "rare": [
        "Bulbasaur", "Charmander", "Squirtle", "Farfetch’d", "Onix", "Hitmonlee", "Hitmonchan",
        "Lickitung", "Kangaskhan", "Scyther", "Pinsir", "Tauros", "Gyarados", "Lapras", "Ditto",
        "Aerodactyl", "Snorlax", "Dratini", "Dragonair"
    ],
    "legendary": [
        "Articuno", "Zapdos", "Moltres", "Mewtwo", "Mew"
    ]
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
        pokedex.setdefault(user_id, []).append({"name": pokemon, "rarity": rarity})
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

@bot.command(name="pokedex")
async def pokedex_cmd(ctx, member: discord.Member = None):
    user = member or ctx.author
    user_id = str(user.id)
    if user_id not in pokedex or not pokedex[user_id]:
        await ctx.send(f"📭 {user.display_name} has not caught any Pokémon yet!")
        return

    grouped = {"common": [], "uncommon": [], "rare": [], "legendary": []}
    for entry in pokedex[user_id]:
        grouped[entry["rarity"]].append(entry["name"])

    embed = discord.Embed(
        title=f"📘 Pokédex for {user.display_name}",
        color=discord.Color.green()
    )
    for rarity, mons in grouped.items():
        if mons:
            embed.add_field(
                name=f"{rarity.capitalize()} ({len(mons)})",
                value=", ".join(mons),
                inline=False
            )

    streak_count = streaks.get(user_id, 0)
    if streak_count > 0:
        embed.set_footer(text=f"🔥 Current streak: {streak_count}")

    await ctx.send(embed=embed)

@bot.command(name="top")
async def top(ctx):
    """Show leaderboard of most Pokémon caught"""
    if not pokedex:
        await ctx.send("📭 No Pokémon have been caught yet!")
        return

    leaderboard = []
    for user_id, mons in pokedex.items():
        leaderboard.append((user_id, len(mons)))

    leaderboard.sort(key=lambda x: x[1], reverse=True)
    top_users = leaderboard[:10]

    embed = discord.Embed(title="🏆 Top Pokémon Trainers", color=discord.Color.gold())
    for i, (user_id, count) in enumerate(top_users, 1):
        user = await bot.fetch_user(int(user_id))
        embed.add_field(name=f"#{i} {user.display_name}", value=f"{count} Pokémon", inline=False)

    await ctx.send(embed=embed)

# =========================
# Help menus
# =========================
@bot.command(name="commands")
@commands.cooldown(1, 30, commands.BucketType.user)
async def commands_list(ctx):
    embed = discord.Embed(title="📖 Available Commands", color=discord.Color.blue())
    embed.add_field(name="🎮 Fun", value="`!joke`, `!roll [sides]`", inline=False)
    embed.add_field(name="🐾 Pokémon", value="`!catch <pokemon>`, `!pokedex`, `!top`", inline=False)
    try:
        await ctx.author.send(embed=embed)
        await ctx.send("📬 I've sent you a DM with the list of commands!")
    except discord.Forbidden:
        await ctx.send(embed=embed)

@bot.command(name="admincommands")
@commands.has_permissions(manage_guild=True)
@commands.cooldown(1, 30, commands.BucketType.user)
async def admin_commands(ctx):
    embed = discord.Embed(title="⚙️ Admin Commands", color=discord.Color.red())
    embed.add_field(name="🛠️ Moderation", value="`!addstreamer`, `!addyoutube`", inline=False)
    embed.add_field(
        name="🐾 Pokémon Control",
        value="`!startpokemon`, `!stoppokemon`, `!resetpokedex @user`, `!resetstreak @user`",
        inline=False
    )
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
