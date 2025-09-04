import os
import discord
from discord.ext import commands
import requests
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
NOTIFY_CHANNEL_ID = int(os.getenv("NOTIFY_CHANNEL_ID", 0))
POKEMON_CHANNEL_ID = int(os.getenv("POKEMON_CHANNEL_ID", 0))
GUILD_ID = int(os.getenv("GUILD_ID", 0))
SHINY_RATE = float(os.getenv("SHINY_RATE", 0.01))  # Default 1%

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
pokedex = poke_data["pokedex"]
streaks = poke_data["streaks"]

# =========================
# Pokémon Data
# =========================
ALL_GEN1 = [
    "Bulbasaur","Ivysaur","Venusaur","Charmander","Charmeleon","Charizard",
    "Squirtle","Wartortle","Blastoise","Caterpie","Metapod","Butterfree",
    "Weedle","Kakuna","Beedrill","Pidgey","Pidgeotto","Pidgeot",
    "Rattata","Raticate","Spearow","Fearow","Ekans","Arbok",
    "Pikachu","Raichu","Sandshrew","Sandslash","Nidoran♀","Nidorina","Nidoqueen",
    "Nidoran♂","Nidorino","Nidoking","Clefairy","Clefable","Vulpix","Ninetales",
    "Jigglypuff","Wigglytuff","Zubat","Golbat","Oddish","Gloom","Vileplume",
    "Paras","Parasect","Venonat","Venomoth","Diglett","Dugtrio","Meowth","Persian",
    "Psyduck","Golduck","Mankey","Primeape","Growlithe","Arcanine","Poliwag","Poliwhirl","Poliwrath",
    "Abra","Kadabra","Alakazam","Machop","Machoke","Machamp","Bellsprout","Weepinbell","Victreebel",
    "Tentacool","Tentacruel","Geodude","Graveler","Golem","Ponyta","Rapidash","Slowpoke","Slowbro",
    "Magnemite","Magneton","Farfetch’d","Doduo","Dodrio","Seel","Dewgong","Grimer","Muk","Shellder","Cloyster",
    "Gastly","Haunter","Gengar","Onix","Drowzee","Hypno","Krabby","Kingler","Voltorb","Electrode",
    "Exeggcute","Exeggutor","Cubone","Marowak","Hitmonlee","Hitmonchan","Lickitung","Koffing","Weezing","Rhyhorn","Rhydon",
    "Chansey","Tangela","Kangaskhan","Horsea","Seadra","Goldeen","Seaking","Staryu","Starmie","Mr. Mime","Scyther","Jynx","Electabuzz","Magmar","Pinsir","Tauros",
    "Magikarp","Gyarados","Lapras","Ditto","Eevee","Vaporeon","Jolteon","Flareon","Porygon",
    "Omanyte","Omastar","Kabuto","Kabutops","Aerodactyl","Snorlax","Articuno","Zapdos","Moltres","Dratini","Dragonair","Dragonite","Mewtwo","Mew"
]

POKEMON_RARITIES = {
    "common": [p for p in ALL_GEN1 if p not in ["Bulbasaur","Charmander","Squirtle","Dratini","Dragonair","Dragonite","Articuno","Zapdos","Moltres","Mewtwo","Mew","Snorlax","Lapras","Ditto","Eevee","Omanyte","Kabuto","Aerodactyl"]],
    "uncommon": ["Eevee","Ditto","Omanyte","Kabuto","Growlithe","Abra","Gastly","Cubone","Scyther","Pinsir","Jynx","Electabuzz","Magmar","Hitmonlee","Hitmonchan"],
    "rare": ["Bulbasaur","Charmander","Squirtle","Dratini","Dragonair","Dragonite","Lapras","Snorlax","Aerodactyl"],
    "legendary": ["Articuno","Zapdos","Moltres","Mewtwo","Mew"]
}
CATCH_RATES = {"common": 0.8,"uncommon": 0.5,"rare": 0.3,"legendary": 0.05}

# =========================
# Pokémon Game
# =========================
pokemon_spawning = False
pokemon_loop_task = None
active_pokemon = None

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
        shiny = random.random() < SHINY_RATE
        active_pokemon = (pokemon, rarity, shiny)
        shiny_text = " ✨SHINY✨" if shiny else ""
        await channel.send(f"A wild **{pokemon}** ({rarity}){shiny_text} appeared! Type `!catch {pokemon}` to try and catch it!")

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
    pokemon, rarity, shiny = active_pokemon
    if name.lower() != pokemon.lower():
        await ctx.send(f"❌ That’s not the Pokémon! The wild Pokémon escaped...")
        active_pokemon = None
        return
    chance = CATCH_RATES[rarity]
    user_id = str(ctx.author.id)
    if random.random() <= chance:
        entry = {"name": pokemon, "rarity": rarity, "shiny": shiny}
        pokedex.setdefault(user_id, []).append(entry)
        streaks[user_id] = streaks.get(user_id, 0) + 1
        save_pokemon_data()
        shiny_text = " ✨SHINY✨" if shiny else ""
        msg = f"✅ {ctx.author.mention} caught **{pokemon}** ({rarity}){shiny_text}!"
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
    grouped = {"common": [], "uncommon": [], "rare": [], "legendary": [], "shiny": []}
    for entry in pokedex[user_id]:
        if entry["shiny"]:
            grouped["shiny"].append(entry["name"])
        else:
            grouped[entry["rarity"]].append(entry["name"])
    embed = discord.Embed(title=f"📘 Pokédex for {user.display_name}", color=discord.Color.green())
    for rarity, mons in grouped.items():
        if mons:
            embed.add_field(name=f"{rarity.capitalize()} ({len(mons)})", value=", ".join(mons), inline=False)
    streak_count = streaks.get(user_id, 0)
    if streak_count > 0:
        embed.set_footer(text=f"🔥 Current streak: {streak_count}")
    await ctx.send(embed=embed)

@bot.command(name="top")
async def top(ctx):
    if not pokedex:
        await ctx.send("📭 No Pokémon have been caught yet!")
        return
    leaderboard = []
    for user_id, mons in pokedex.items():
        total = len(mons)
        shiny_count = sum(1 for m in mons if m["shiny"])
        leaderboard.append((user_id, total, shiny_count))
    leaderboard.sort(key=lambda x: (x[1], x[2]), reverse=True)
    top_users = leaderboard[:10]
    embed = discord.Embed(title="🏆 Top Pokémon Trainers", color=discord.Color.gold())
    for i, (user_id, total, shinies) in enumerate(top_users, 1):
        user = await bot.fetch_user(int(user_id))
        embed.add_field(name=f"#{i} {user.display_name}", value=f"{total} Pokémon ({shinies} shiny)", inline=False)
    await ctx.send(embed=embed)

# =========================
# Error + startup
# =========================
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, CommandOnCooldown):
        await ctx.send(f"⏳ Wait {error.retry_after:.1f}s before reusing this.", delete_after=5)
    elif isinstance(error, commands.CommandNotFound):
        await ctx.send("❌ That command doesn’t exist. Try `!commands`.", delete_after=5)
    else:
        raise error

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

bot.run(DISCORD_TOKEN)
