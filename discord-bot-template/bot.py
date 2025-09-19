import os
import json
import random
import asyncio
import requests
import discord
from discord.ext import commands, tasks
from discord.ext.commands import CommandOnCooldown, MissingPermissions
import time
from dotenv import load_dotenv
import logging

# Setup logging to file and console
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bot_errors.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

# Debug .env loading
print(f"Current working directory: {os.getcwd()}")
print(f"Attempting to load .env from: {os.path.abspath('.env')}")
env_file = ".env"
if not load_dotenv(env_file):
    logging.error(f"Failed to load .env file at {os.path.abspath(env_file)}. Ensure it exists and is readable.")
else:
    logging.info(f"Loaded .env file from {os.path.abspath(env_file)}")

logging.info(f"Running bot from: {os.path.abspath(__file__)}")
logging.info("Bot starting up...")

# =========================
# ENV VARS
# =========================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
NOTIFY_CHANNEL_ID = int(os.getenv("NOTIFY_CHANNEL_ID", 0))     # Fallback channel
POKEMON_CHANNEL_ID = int(os.getenv("POKEMON_CHANNEL_ID", 0))   # Pokémon spawns
GUILD_ID = int(os.getenv("GUILD_ID", 0))                       # Role management
SHINY_RATE = float(os.getenv("SHINY_RATE", 0.01))              # Default 1%
TWITCH_INTERVAL = int(os.getenv("TWITCH_INTERVAL", 2))         # Minutes
YOUTUBE_INTERVAL = int(os.getenv("YOUTUBE_INTERVAL", 5))       # Minutes
TWITCH_CHANNEL_ID = int(os.getenv("TWITCH_CHANNEL_ID", NOTIFY_CHANNEL_ID))  # Twitch notifications
YOUTUBE_CHANNEL_ID = int(os.getenv("YOUTUBE_CHANNEL_ID", NOTIFY_CHANNEL_ID)) # YouTube notifications
MEME_CHANNEL_ID = int(os.getenv("MEME_CHANNEL_ID", 0))         # Daily memes

# Twitch / YouTube
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_SECRET = os.getenv("TWITCH_SECRET")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

# Pokémon spawn and catch rates
SPAWN_COMMON = float(os.getenv("SPAWN_COMMON", 0.60))
SPAWN_UNCOMMON = float(os.getenv("SPAWN_UNCOMMON", 0.25))
SPAWN_RARE = float(os.getenv("SPAWN_RARE", 0.10))
SPAWN_LEGENDARY = float(os.getenv("SPAWN_LEGENDARY", 0.05))
CATCH_COMMON = float(os.getenv("CATCH_COMMON", 0.80))
CATCH_UNCOMMON = float(os.getenv("CATCH_UNCOMMON", 0.60))
CATCH_RARE = float(os.getenv("CATCH_RARE", 0.35))
CATCH_LEGENDARY = float(os.getenv("CATCH_LEGENDARY", 0.15))
CATCH_SHINY = float(os.getenv("CATCH_SHINY", 0.10))

# Role colors
POKEMON_MASTER_COLOR = os.getenv("POKEMON_MASTER_COLOR", "0000FF")  # Default blue
SHINY_MASTER_COLOR = os.getenv("SHINY_MASTER_COLOR", "800080")      # Default purple

# Debug environment variables
logging.info(f"DEBUG: DISCORD_TOKEN={'Set' if DISCORD_TOKEN else 'Not set'}")
logging.info(f"DEBUG: NOTIFY_CHANNEL_ID={NOTIFY_CHANNEL_ID}")
logging.info(f"DEBUG: TWITCH_CHANNEL_ID={TWITCH_CHANNEL_ID}")
logging.info(f"DEBUG: YOUTUBE_CHANNEL_ID={YOUTUBE_CHANNEL_ID}")
logging.info(f"DEBUG: MEME_CHANNEL_ID={MEME_CHANNEL_ID}")
logging.info(f"DEBUG: TWITCH_CLIENT_ID={'Set' if TWITCH_CLIENT_ID else 'Not set'}")
logging.info(f"DEBUG: TWITCH_SECRET={'Set' if TWITCH_SECRET else 'Not set'}")
logging.info(f"DEBUG: YOUTUBE_API_KEY={'Set' if YOUTUBE_API_KEY else 'Not set'}")
logging.info(f"DEBUG: SPAWN_COMMON={SPAWN_COMMON}, SPAWN_UNCOMMON={SPAWN_UNCOMMON}, SPAWN_RARE={SPAWN_RARE}, SPAWN_LEGENDARY={SPAWN_LEGENDARY}")
logging.info(f"DEBUG: CATCH_COMMON={CATCH_COMMON}, CATCH_UNCOMMON={CATCH_UNCOMMON}, CATCH_RARE={CATCH_RARE}, CATCH_LEGENDARY={CATCH_LEGENDARY}, CATCH_SHINY={CATCH_SHINY}")
logging.info(f"DEBUG: POKEMON_MASTER_COLOR={POKEMON_MASTER_COLOR}, SHINY_MASTER_COLOR={SHINY_MASTER_COLOR}")

STARTUP_LOG_CHANNEL_ID = int(os.getenv("STARTUP_LOG_CHANNEL_ID", 0))

# =========================
# DATA FILES
# =========================
NOTIFY_FILE = "notify_data.json"     # Twitch + YouTube lists and last seen video IDs
PERMANENT_CHANNELS_FILE = "permanent_channels.json"  # Permanent streamers and YouTube channels
POKEMON_FILE = "pokemon_data.json"   # Catches + streaks
MEME_FILE = "memes.json"             # Memes list
JOKE_FILE = "jokes.json"             # Jokes list
CONFIG_FILE = "config.json"          # Server prefixes

def load_json_file(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                logging.info(f"Loaded {path}")
                return data
            except Exception as e:
                logging.error(f"Error loading {path}: {e}")
                return default
    logging.info(f"File {path} not found, using default: {default}")
    return default

def save_json_file(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        logging.info(f"Saved {path}")
    except Exception as e:
        logging.error(f"Error saving {path}: {e}")

memes = load_json_file(MEME_FILE, [])
jokes = load_json_file(JOKE_FILE, [])
config = load_json_file(CONFIG_FILE, {"prefixes": {}})

# =========================
# DISCORD BOT
# =========================
def get_prefix(bot, message):
    guild_id = str(message.guild.id) if message.guild else "default"
    return config.get("prefixes", {}).get(guild_id, "!")

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix=get_prefix, intents=intents)

# Safety: clear any commands if reloaded
for cmd in list(bot.commands):
    bot.remove_command(cmd.name)
logging.info("Commands reset on startup")

bot.remove_command("pokemonstatus")
bot.remove_command("commands")

# =========================
# PERSISTENCE HELPERS
# =========================
def load_notify_data():
    notify_data = load_json_file(NOTIFY_FILE, {"streamers": [], "youtube_channels": {}})
    permanent_data = load_json_file(PERMANENT_CHANNELS_FILE, {"streamers": [], "youtube_channels": {}})
    notify_data["streamers"] = list(set(notify_data.get("streamers", []) + permanent_data.get("streamers", [])))
    for ch_id in permanent_data.get("youtube_channels", {}):
        if ch_id not in notify_data.get("youtube_channels", {}):
            notify_data["youtube_channels"][ch_id] = permanent_data["youtube_channels"][ch_id]
    save_json_file(NOTIFY_FILE, notify_data)
    return notify_data

def save_notify_data(d):
    save_json_file(NOTIFY_FILE, d)
    permanent_data = {
        "streamers": d.get("streamers", []),
        "youtube_channels": {ch_id: "" for ch_id in d.get("youtube_channels", {})}
    }
    save_json_file(PERMANENT_CHANNELS_FILE, permanent_data)

def load_pokemon_data():
    return load_json_file(POKEMON_FILE, {"pokedex": {}, "streaks": {}})

def save_pokemon_data(poke):
    save_json_file(POKEMON_FILE, poke)

notify_data = load_notify_data()
streamers = notify_data.get("streamers", [])
youtube_channels = notify_data.get("youtube_channels", {})  # {channel_id: last_video_id}

poke_data = load_pokemon_data()
pokedex = poke_data.get("pokedex", {})  # user_id -> [{name, rarity, shiny}]
streaks = poke_data.get("streaks", {})  # user_id -> int

# =========================
# FULL GEN 1 LIST (151)
# =========================
ALL_GEN1 = [
    "Bulbasaur","Ivysaur","Venusaur","Charmander","Charmeleon","Charizard",
    "Squirtle","Wartortle","Blastoise","Caterpie","Metapod","Butterfree",
    "Weedle","Kakuna","Beedrill","Pidgey","Pidgeotto","Pidgeot",
    "Rattata","Raticate","Spearow","Fearow","Ekans","Arbok",
    "Pikachu","Raichu","Sandshrew","Sandslash","Nidoran-F","Nidorina","Nidoqueen",
    "Nidoran-M","Nidorino","Nidoking","Clefairy","Clefable","Vulpix","Ninetales",
    "Jigglypuff","Wigglytuff","Zubat","Golbat","Oddish","Gloom","Vileplume",
    "Paras","Parasect","Venonat","Venomoth","Diglett","Dugtrio","Meowth","Persian",
    "Psyduck","Golduck","Mankey","Primeape","Growlithe","Arcanine","Poliwag","Poliwhirl","Poliwrath",
    "Abra","Kadabra","Alakazam","Machop","Machoke","Machamp","Bellsprout","Weepinbell","Victreebel",
    "Tentacool","Tentacruel","Geodude","Graveler","Golem","Ponyta","Rapidash","Slowpoke","Slowbro",
    "Magnemite","Magneton","Farfetch'd","Doduo","Dodrio","Seel","Dewgong","Grimer","Muk","Shellder","Cloyster",
    "Gastly","Haunter","Gengar","Onix","Drowzee","Hypno","Krabby","Kingler","Voltorb","Electrode",
    "Exeggcute","Exeggutor","Cubone","Marowak","Hitmonlee","Hitmonchan","Lickitung","Koffing","Weezing","Rhyhorn","Rhydon",
    "Chansey","Tangela","Kangaskhan","Horsea","Seadra","Goldeen","Seaking","Staryu","Starmie","Mr. Mime","Scyther","Jynx","Electabuzz","Magmar","Pinsir","Tauros",
    "Magikarp","Gyarados","Lapras","Ditto","Eevee","Vaporeon","Jolteon","Flareon","Porygon",
    "Omanyte","Omastar","Kabuto","Kabutops","Aerodactyl","Snorlax","Articuno","Zapdos","Moltres","Dratini","Dragonair","Dragonite","Mewtwo","Mew"
]

# Rarity sets
LEGENDARY = {"Articuno","Zapdos","Moltres","Mewtwo","Mew"}
RARE = {
    "Bulbasaur","Ivysaur","Venusaur","Charmander","Charmeleon","Charizard",
    "Squirtle","Wartortle","Blastoise",
    "Gengar","Alakazam","Machamp","Gyarados",
    "Omastar","Kabutops","Aerodactyl",
    "Lapras","Snorlax","Chansey","Ditto",
    "Dratini","Dragonair","Dragonite","Raichu"
}
UNCOMMON = {
    "Pikachu","Vulpix","Ninetales","Jigglypuff","Wigglytuff","Growlithe","Arcanine","Abra","Kadabra",
    "Bellsprout","Weepinbell","Victreebel","Tentacruel","Golem","Rapidash","Slowbro","Magneton",
    "Farfetch'd","Dodrio","Dewgong","Muk","Cloyster","Haunter","Hypno","Kingler","Electrode","Exeggutor",
    "Marowak","Lickitung","Weezing","Rhydon","Tangela","Kangaskhan","Seadra","Seaking","Starmie",
    "Mr. Mime","Scyther","Jynx","Electabuzz","Magmar","Pinsir","Tauros","Porygon","Eevee","Vaporeon","Jolteon","Flareon"
}

POKEMON_RARITIES = {
    "legendary": sorted(list(LEGENDARY)),
    "rare": sorted(list(RARE - LEGENDARY)),
    "uncommon": sorted(list(UNCOMMON - RARE - LEGENDARY)),
    "common": sorted([p for p in ALL_GEN1 if p not in (LEGENDARY | RARE | UNCOMMON)])
}
CATCH_RATES = {
    "common": CATCH_COMMON,
    "uncommon": CATCH_UNCOMMON,
    "rare": CATCH_RARE,
    "legendary": CATCH_LEGENDARY
}

# =========================
# POKÉMON GAME
# =========================
pokemon_spawning = False
pokemon_loop_task = None
active_pokemon = None  # tuple (name, rarity, shiny)

catch_cooldowns = {}
CATCH_COOLDOWN = 10  # seconds

async def pokemon_spawner():
    global active_pokemon
    await bot.wait_until_ready()
    while pokemon_spawning:
        channel = bot.get_channel(POKEMON_CHANNEL_ID)
        if not channel:
            logging.error(f"Pokémon channel not found: ID {POKEMON_CHANNEL_ID}. Retrying in 60s...")
            await asyncio.sleep(60)
            continue
        await asyncio.sleep(1800)  # 30 minutes
        rarity = random.choices(
            ["common", "uncommon", "rare", "legendary"],
            weights=[SPAWN_COMMON, SPAWN_UNCOMMON, SPAWN_RARE, SPAWN_LEGENDARY]
        )[0]
        pokemon = random.choice(POKEMON_RARITIES[rarity])
        shiny = (random.random() < SHINY_RATE)
        active_pokemon = (pokemon, rarity, shiny)
        shiny_text = " ✨SHINY✨" if shiny else ""
        await channel.send(
            f"A wild **{pokemon}** ({rarity}){shiny_text} appeared! "
            f"Type `{get_prefix(bot, channel)}catch {pokemon}` to try and catch it!"
        )

@bot.command(name="startpokemon")
@commands.has_permissions(administrator=True)
async def startpokemon(ctx):
    global pokemon_spawning, pokemon_loop_task
    if pokemon_spawning:
        await ctx.send("Pokémon spawns are already running!")
    else:
        pokemon_spawning = True
        pokemon_loop_task = asyncio.create_task(pokemon_spawner())
        await ctx.send("🐾 Pokémon spawning has started!")
        logging.info("Pokémon spawning started")

@bot.command(name="stoppokemon")
@commands.has_permissions(administrator=True)
async def stoppokemon(ctx):
    global pokemon_spawning, pokemon_loop_task
    if not pokemon_spawning:
        await ctx.send("Pokémon spawns are not running!")
    else:
        pokemon_spawning = False
        if pokemon_loop_task:
            pokemon_loop_task.cancel()
        await ctx.send("🛑 Pokémon spawning has been stopped.")
        logging.info("Pokémon spawning stopped")

@bot.command(name="pokemonstatus")
async def pokemonstatus(ctx):
    global pokemon_spawning, active_pokemon
    if not pokemon_spawning:
        await ctx.send("🛑 Pokémon spawning is currently **OFF**.")
    elif active_pokemon:
        name, rarity, shiny = active_pokemon
        shiny_text = " ✨SHINY✨" if shiny else ""
        await ctx.send(f"✅ Spawning is **ON**. Active Pokémon: **{name}** ({rarity}){shiny_text}")
    else:
        await ctx.send("✅ Spawning is **ON**, but no Pokémon is currently active.")

@bot.command(name="setcatchcd")
@commands.has_permissions(administrator=True)
async def setcatchcd(ctx, seconds: int):
    global CATCH_COOLDOWN
    if seconds < 0:
        await ctx.send("❌ Cooldown must be 0 or greater.")
    else:
        CATCH_COOLDOWN = seconds
        await ctx.send(f"✅ Catch cooldown set to {CATCH_COOLDOWN} seconds.")
        logging.info(f"Catch cooldown set to {CATCH_COOLDOWN} seconds")

@bot.command(name="catch")
async def catch(ctx, *, name: str):
    global active_pokemon
    if not active_pokemon:
        await ctx.send("❌ There is no Pokémon to catch right now!")
        return
    pokemon, rarity, shiny = active_pokemon
    if name.strip().lower() != pokemon.lower():
        await ctx.send("❌ That’s not the Pokémon! The wild Pokémon escaped…")
        active_pokemon = None
        return
    chance = CATCH_SHINY if shiny else CATCH_RATES[rarity]
    user_id = str(ctx.author.id)
    if random.random() <= chance:
        entry = {"name": pokemon, "rarity": rarity, "shiny": shiny}
        pokedex.setdefault(user_id, []).append(entry)
        streaks[user_id] = streaks.get(user_id, 0) + 1
        save_pokemon_data({"pokedex": pokedex, "streaks": streaks})
        shiny_text = " ✨SHINY✨" if shiny else ""
        msg = f"✅ {ctx.author.mention} caught **{pokemon}** ({rarity}){shiny_text}!"
        if streaks[user_id] >= 3:
            msg += f" 🔥 {ctx.author.display_name} is on fire with {streaks[user_id]} catches in a row!"
        await ctx.send(msg)
        user, leveled_up = add_xp(user_id, LEVEL_CONFIG['catch_xp'])
        if leveled_up and LEVEL_CONFIG.get('announce_levelup', True):
            await ctx.send(f"🎉 <@{user_id}> leveled up to **Level {user['level']}**!")
        await update_roles(ctx.guild)
    else:
        streaks[user_id] = 0
        save_pokemon_data({"pokedex": pokedex, "streaks": streaks})
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
    for rarity in ["shiny","legendary","rare","uncommon","common"]:
        mons = grouped[rarity]
        if mons:
            embed.add_field(name=f"{rarity.capitalize()} ({len(mons)})", value=", ".join(sorted(mons)), inline=False)
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
    embed = discord.Embed(title="🏆 Top Pokémon Trainers", color=discord.Color.gold())
    for i, (user_id, total, shinies) in enumerate(leaderboard[:10], 1):
        try:
            user = await bot.fetch_user(int(user_id))
            name = user.display_name
        except Exception:
            name = f"User {user_id}"
        embed.add_field(name=f"#{i} {name}", value=f"{total} Pokémon ({shinies} shiny)", inline=False)
    await ctx.send(embed=embed)

# Pokémon Trading
pending_trades = {}  # {user_id: (target_id, pokemon_name)}

@bot.command(name="trade")
async def trade(ctx, member: discord.Member, pokemon_name: str):
    user_id = str(ctx.author.id)
    target_id = str(member.id)
    if user_id == target_id:
        await ctx.send("❌ You cannot trade with yourself!")
        return
    if user_id not in pokedex or target_id not in pokedex:
        await ctx.send("❌ Both users must have Pokémon in their Pokédex!")
        return
    user_pokemon = next((p for p in pokedex[user_id] if p["name"].lower() == pokemon_name.lower()), None)
    if not user_pokemon:
        await ctx.send(f"❌ {ctx.author.display_name} doesn't have {pokemon_name}!")
        return
    pending_trades[user_id] = (target_id, user_pokemon)
    await ctx.send(f"{member.mention}, {ctx.author.display_name} wants to trade {pokemon_name}! Reply `{get_prefix(bot, ctx.message)}accept` within 60s to confirm.")
    logging.info(f"Trade initiated: {ctx.author.display_name} offers {pokemon_name} to {member.display_name}")

@bot.command(name="accept")
async def accept_trade(ctx):
    user_id = str(ctx.author.id)
    for initiator_id, (target_id, pokemon) in list(pending_trades.items()):
        if user_id == target_id:
            pokedex[initiator_id].remove(pokemon)
            pokedex[user_id].append(pokemon)
            save_pokemon_data({"pokedex": pokedex, "streaks": streaks})
            await ctx.send(f"✅ Trade complete: {ctx.author.display_name} received {pokemon['name']} from <@{initiator_id}>!")
            del pending_trades[initiator_id]
            logging.info(f"Trade completed: {ctx.author.display_name} received {pokemon['name']} from User {initiator_id}")
            return
    await ctx.send("❌ No pending trade found for you!")

# Pokémon Battles
@bot.command(name="battle")
async def battle(ctx, opponent: discord.Member):
    if opponent.id == ctx.author.id:
        await ctx.send("❌ You cannot battle yourself!")
        return
    user_id = str(ctx.author.id)
    opp_id = str(opponent.id)
    if user_id not in pokedex or opp_id not in pokedex:
        await ctx.send("❌ Both users must have Pokémon!")
        return
    user_pokemon = random.choice(pokedex[user_id])
    opp_pokemon = random.choice(pokedex[opp_id])
    user_score = {"legendary": 4, "rare": 3, "uncommon": 2, "common": 1}[user_pokemon["rarity"]]
    opp_score = {"legendary": 4, "rare": 3, "uncommon": 2, "common": 1}[opp_pokemon["rarity"]]
    if user_pokemon["shiny"]:
        user_score += 1
    if opp_pokemon["shiny"]:
        opp_score += 1
    winner = ctx.author if user_score > opp_score or (user_score == opp_score and random.choice([True, False])) else opponent
    await ctx.send(f"⚔️ {ctx.author.display_name}'s {user_pokemon['name']} vs {opponent.display_name}'s {opp_pokemon['name']}! **{winner.display_name}** wins!")
    user, leveled_up = add_xp(str(winner.id), LEVEL_CONFIG.get("battle_win_xp", 25))
    if leveled_up and LEVEL_CONFIG.get('announce_levelup', True):
        await ctx.send(f"🎉 {winner.mention} leveled up to **Level {user['level']}**!")
    logging.info(f"Battle: {ctx.author.display_name} vs {opponent.display_name}, winner: {winner.display_name}")

# =========================
# ROLE MANAGEMENT
# =========================
async def ensure_roles(guild: discord.Guild):
    top_role = discord.utils.get(guild.roles, name="Top Trainer")
    shiny_role = discord.utils.get(guild.roles, name="Shiny Master")
    if not top_role:
        top_role = await guild.create_role(name="Top Trainer", colour=discord.Colour(int(POKEMON_MASTER_COLOR, 16)))
    if not shiny_role:
        shiny_role = await guild.create_role(name="Shiny Master", colour=discord.Colour(int(SHINY_MASTER_COLOR, 16)))
    return top_role, shiny_role

async def update_roles(guild: discord.Guild):
    if not guild or not pokedex:
        return
    top_role, shiny_role = await ensure_roles(guild)
    top_trainer_id = max(pokedex.items(), key=lambda kv: len(kv[1]))[0] if pokedex else None
    shiny_counts = {uid: sum(1 for m in mons if m["shiny"]) for uid, mons in pokedex.items()}
    shiny_trainer_id = max(shiny_counts, key=shiny_counts.get) if shiny_counts else None
    max_shinies = shiny_counts[shiny_trainer_id] if shiny_trainer_id else 0
    for member in guild.members:
        if top_role in member.roles and str(member.id) != top_trainer_id:
            await member.remove_roles(top_role)
        if top_trainer_id and str(member.id) == top_trainer_id and top_role not in member.roles:
            await member.add_roles(top_role)
        if shiny_role in member.roles and (str(member.id) != shiny_trainer_id or max_shinies == 0):
            await member.remove_roles(shiny_role)
        if shiny_trainer_id and str(member.id) == shiny_trainer_id and shiny_role not in member.roles and max_shinies > 0:
            await member.add_roles(shiny_role)

@bot.command(name="forceroles")
@commands.has_permissions(administrator=True)
async def forceroles(ctx):
    guild = ctx.guild or bot.get_guild(GUILD_ID)
    if not guild:
        await ctx.send("⚠️ Guild not found for role updates.")
        return
    await update_roles(guild)
    await ctx.send("🔄 Roles refreshed.")
    logging.info("Roles refreshed via !forceroles")

# =========================
# TWITCH NOTIFIER
# =========================
TWITCH_ACCESS_TOKEN = None
TWITCH_TOKEN_EXPIRES = 0

def get_twitch_token():
    global TWITCH_ACCESS_TOKEN, TWITCH_TOKEN_EXPIRES
    if not TWITCH_CLIENT_ID or not TWITCH_SECRET:
        logging.error("Missing TWITCH_CLIENT_ID or TWITCH_SECRET in .env")
        return None
    url = "https://id.twitch.tv/oauth2/token"
    params = {
        "client_id": TWITCH_CLIENT_ID,
        "client_secret": TWITCH_SECRET,
        "grant_type": "client_credentials"
    }
    try:
        r = requests.post(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        TWITCH_ACCESS_TOKEN = data.get("access_token")
        TWITCH_TOKEN_EXPIRES = time.time() + data.get("expires_in", 3600) - 60
        logging.info(f"Twitch token refreshed, expires at {time.ctime(TWITCH_TOKEN_EXPIRES)}")
        return TWITCH_ACCESS_TOKEN
    except requests.RequestException as e:
        logging.error(f"Twitch token fetch error: {e}")
        return None

def twitch_headers():
    global TWITCH_ACCESS_TOKEN, TWITCH_TOKEN_EXPIRES
    current_time = time.time()
    if not TWITCH_ACCESS_TOKEN or current_time >= TWITCH_TOKEN_EXPIRES:
        TWITCH_ACCESS_TOKEN = get_twitch_token()
    if not TWITCH_ACCESS_TOKEN:
        logging.error("No valid Twitch access token available")
        return {}
    return {"Client-ID": TWITCH_CLIENT_ID, "Authorization": f"Bearer {TWITCH_ACCESS_TOKEN}"}

last_twitch_status = {}  # streamer -> bool

@tasks.loop(minutes=TWITCH_INTERVAL)
async def twitch_notifier():
    if not TWITCH_CLIENT_ID or not TWITCH_SECRET:
        logging.error("Twitch notifier skipped: Missing TWITCH_CLIENT_ID or TWITCH_SECRET")
        return
    if TWITCH_CHANNEL_ID == 0 or not streamers:
        logging.error(f"Twitch notifier skipped: Invalid channel ID ({TWITCH_CHANNEL_ID}) or no streamers ({len(streamers)})")
        return
    channel = bot.get_channel(TWITCH_CHANNEL_ID)
    if not channel:
        logging.error(f"Notify channel not found: ID {TWITCH_CHANNEL_ID}")
        return
    logging.info(f"Checking Twitch for {len(streamers)} streamers: {', '.join(streamers)}")
    for username in list(streamers):
        try:
            url = "https://api.twitch.tv/helix/streams"
            resp = requests.get(url, headers=twitch_headers(), params={"user_login": username}, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            is_live = bool(data.get("data"))
            was_live = last_twitch_status.get(username, False)
            if is_live and not was_live:
                await channel.send(f"@everyone 🎥 **{username} is LIVE on Twitch!** https://twitch.tv/{username}")
                logging.info(f"Sent Twitch live notification for {username}")
            elif not is_live and was_live:
                logging.info(f"{username} went offline")
            last_twitch_status[username] = is_live
        except requests.RequestException as e:
            logging.error(f"Twitch check error for {username}: {e}")
            await channel.send(f"⚠️ Error checking Twitch status for {username}: {e}")
        except Exception as e:
            logging.error(f"Unexpected error in twitch_notifier for {username}: {e}")

# =========================
# YOUTUBE NOTIFIER
# =========================
@tasks.loop(minutes=YOUTUBE_INTERVAL)
async def youtube_notifier():
    if not YOUTUBE_API_KEY:
        logging.error("YouTube notifier skipped: Missing YOUTUBE_API_KEY")
        return
    if YOUTUBE_CHANNEL_ID == 0 or not youtube_channels:
        logging.error(f"YouTube notifier skipped: Invalid channel ID ({YOUTUBE_CHANNEL_ID}) or no channels ({len(youtube_channels)})")
        return
    channel = bot.get_channel(YOUTUBE_CHANNEL_ID)
    if not channel:
        logging.error(f"Notify channel not found: ID {YOUTUBE_CHANNEL_ID}")
        return
    logging.info(f"Checking YouTube for {len(youtube_channels)} channels: {', '.join(youtube_channels.keys())}")
    updated = False
    for ch_id, last_vid in list(youtube_channels.items()):
        try:
            url = "https://www.googleapis.com/youtube/v3/search"
            params = {
                "part": "snippet",
                "channelId": ch_id,
                "maxResults": 1,
                "order": "date",
                "type": "video",
                "key": YOUTUBE_API_KEY
            }
            r = requests.get(url, params=params, timeout=10)
            r.raise_for_status()
            data = r.json()
            items = data.get("items", [])
            if not items:
                logging.info(f"No recent videos found for YouTube channel {ch_id}")
                continue
            vid = items[0]["id"]["videoId"]
            title = items[0]["snippet"]["title"]
            if not last_vid:
                youtube_channels[ch_id] = vid
                updated = True
                logging.info(f"Initialized last video ID for YouTube channel {ch_id}: {vid}")
            elif vid != last_vid:
                youtube_channels[ch_id] = vid
                updated = True
                await channel.send(f"▶️ New YouTube upload: **{title}**\nhttps://youtu.be/{vid}")
                logging.info(f"Sent YouTube notification for channel {ch_id}, video {vid}")
        except requests.RequestException as e:
            logging.error(f"YouTube check error for {ch_id}: {e}")
            await channel.send(f"⚠️ Error checking YouTube channel {ch_id}: {e}")
        except Exception as e:
            logging.error(f"Unexpected error in youtube_notifier for {ch_id}: {e}")
    if updated:
        notify_data["youtube_channels"] = youtube_channels
        save_notify_data(notify_data)

# =========================
# ADMIN: ADD/REMOVE STREAMERS/YT
# =========================
@bot.command(name="addstreamer")
@commands.has_permissions(administrator=True)
async def add_streamer(ctx, twitch_name: str):
    name = twitch_name.lower()
    if name in streamers:
        await ctx.send(f"⚠️ **{name}** is already in the Twitch list.")
        return
    streamers.append(name)
    notify_data["streamers"] = streamers
    save_notify_data(notify_data)
    await ctx.send(f"✅ Added **{name}** to Twitch notifications.")
    logging.info(f"Added Twitch streamer {name}")

@bot.command(name="addyoutube")
@commands.has_permissions(administrator=True)
async def add_youtube(ctx, channel_id: str):
    if channel_id in youtube_channels:
        await ctx.send(f"⚠️ Channel `{channel_id}` already tracked.")
        return
    youtube_channels[channel_id] = ""
    notify_data["youtube_channels"] = youtube_channels
    save_notify_data(notify_data)
    await ctx.send(f"✅ Added YouTube channel `{channel_id}`. I’ll notify on the next upload.")
    logging.info(f"Added YouTube channel {channel_id}")

@bot.command(name="removestreamer")
@commands.has_permissions(administrator=True)
async def remove_streamer(ctx, twitch_name: str):
    name = twitch_name.lower()
    if name not in streamers:
        await ctx.send(f"⚠️ **{name}** is not in the Twitch list.")
        return
    streamers.remove(name)
    notify_data["streamers"] = streamers
    save_notify_data(notify_data)
    await ctx.send(f"✅ Removed **{name}** from Twitch notifications.")
    logging.info(f"Removed Twitch streamer {name}")

@bot.command(name="removeyoutube")
@commands.has_permissions(administrator=True)
async def remove_youtube(ctx, channel_id: str):
    if channel_id not in youtube_channels:
        await ctx.send(f"⚠️ Channel `{channel_id}` is not tracked.")
        return
    youtube_channels.pop(channel_id, None)
    notify_data["youtube_channels"] = youtube_channels
    save_notify_data(notify_data)
    await ctx.send(f"✅ Removed YouTube channel `{channel_id}`.")
    logging.info(f"Removed YouTube channel {channel_id}")

# Custom Notification Channels
@bot.command(name="settwitchchannel")
@commands.has_permissions(administrator=True)
async def set_twitch_channel(ctx, channel: discord.TextChannel):
    global TWITCH_CHANNEL_ID
    TWITCH_CHANNEL_ID = channel.id
    await ctx.send(f"✅ Twitch notifications will now go to {channel.mention}.")
    logging.info(f"Twitch notification channel set to {channel.id}")

@bot.command(name="setyoutubechannel")
@commands.has_permissions(administrator=True)
async def set_youtube_channel(ctx, channel: discord.TextChannel):
    global YOUTUBE_CHANNEL_ID
    YOUTUBE_CHANNEL_ID = channel.id
    await ctx.send(f"✅ YouTube notifications will now go to {channel.mention}.")
    logging.info(f"YouTube notification channel set to {channel.id}")

@bot.command(name="setmemechannel")
@commands.has_permissions(administrator=True)
async def set_meme_channel(ctx, channel: discord.TextChannel):
    global MEME_CHANNEL_ID
    MEME_CHANNEL_ID = channel.id
    await ctx.send(f"✅ Daily memes will now go to {channel.mention}.")
    logging.info(f"Meme channel set to {channel.id}")

# =========================
# DM COMMAND MENUS
# =========================
@bot.command(name="commands")
@commands.cooldown(1, 20, commands.BucketType.user)
async def commands_list(ctx):
    embed = discord.Embed(title="📖 Commands", color=discord.Color.blue())
    embed.add_field(
        name="🎮 Pokémon Game",
        value="`catch <name>`, `pokedex [@user]`, `top`, `trade @user <pokemon>`, `accept`, `battle @user`",
        inline=False
    )
    embed.add_field(
        name="🤣 Fun Extras",
        value="`meme`, `joke`",
        inline=False
    )
    embed.add_field(
        name="⭐ Levels System",
        value="`level [@user]`, `leaderboard`, `duel @user`",
        inline=False
    )
    embed.add_field(
        name="🔔 Notifications",
        value="Auto Twitch & YouTube alerts in set channels. Use `listfollows` to view followed channels.",
        inline=False
    )
    embed.add_field(
        name="⚙️ Admin Commands",
        value="Use `admincommands` for admin-only commands like managing spawns, notifications, and levels.",
        inline=False
    )
    embed.set_footer(text="Type admincommands for full admin command list if you have access.")
    try:
        await ctx.author.send(embed=embed)
        await ctx.reply("📬 Sent you a DM with the commands!", mention_author=False)
    except discord.Forbidden:
        await ctx.reply(embed=embed, mention_author=False)

@bot.command(name="admincommands")
@commands.cooldown(1, 20, commands.BucketType.user)
async def admin_commands(ctx):
    embed = discord.Embed(title="⚙️ Admin Commands", color=discord.Color.red())
    embed.add_field(
        name="🐾 Pokémon Control",
        value="`startpokemon`, `stoppokemon`, `setcatchcd <seconds>`, `forceroles`",
        inline=False
    )
    embed.add_field(
        name="🔔 Notifications Management",
        value="`addstreamer <twitch_name>`, `addyoutube <channel_id>`, `removestreamer <twitch_name>`, `removeyoutube <channel_id>`, `settwitchchannel #channel`, `setyoutubechannel #channel`, `setmemechannel #channel`, `listfollows`",
        inline=False
    )
    embed.add_field(
        name="⭐ Levels Management",
        value="`setxp <type> <amount>`, `getxpconfig`, `togglelevelup`, `resetlevel @user`, `resetalllevels confirm`",
        inline=False
    )
    embed.add_field(
        name="⚙️ Bot Config",
        value="`setprefix <prefix>`",
        inline=False
    )
    try:
        await ctx.author.send(embed=embed)
        await ctx.reply("📬 Sent you a DM with the admin commands!", mention_author=False)
    except discord.Forbidden:
        await ctx.reply(embed=embed, mention_author=False)

# =========================
# FUN COMMANDS: MEMES & JOKES
# =========================
@bot.command(name="meme")
async def meme_cmd(ctx):
    if not memes:
        await ctx.send("📭 No memes available.")
        return
    meme = random.choice(memes)
    sent = False
    if isinstance(meme, dict):
        title = meme.get("title", "")
        url = meme.get("url", "")
        if url:
            embed = discord.Embed(title=title or "😂 Meme", color=discord.Color.random())
            embed.set_image(url=url)
            await ctx.send(embed=embed)
            sent = True
        elif title:
            await ctx.send(title or "😂 Meme")
            sent = True
    if not sent:
        await ctx.send(str(meme))
    user, leveled_up = add_xp(str(ctx.author.id), LEVEL_CONFIG['meme_xp'])
    if leveled_up and LEVEL_CONFIG.get('announce_levelup', True):
        await ctx.send(f"🎉 {ctx.author.mention} leveled up to **Level {user['level']}**!")

@bot.command(name="joke")
async def joke_cmd(ctx):
    if not jokes:
        await ctx.send("📭 No jokes available.")
        return
    joke = random.choice(jokes)
    sent = False
    if isinstance(joke, dict):
        setup = joke.get("setup")
        punchline = joke.get("punchline")
        text = joke.get("text")
        if setup and punchline:
            await ctx.send(f"🤣 {setup}\n||{punchline}||")
            sent = True
        elif text:
            await ctx.send(text)
            sent = True
    if not sent:
        await ctx.send(str(joke))
    user, leveled_up = add_xp(str(ctx.author.id), LEVEL_CONFIG['joke_xp'])
    if leveled_up and LEVEL_CONFIG.get('announce_levelup', True):
        await ctx.send(f"🎉 {ctx.author.mention} leveled up to **Level {user['level']}**!")

# Daily Meme Task
@tasks.loop(hours=24)
async def daily_meme():
    if MEME_CHANNEL_ID == 0 or not memes:
        logging.error(f"Daily meme skipped: Invalid channel ID ({MEME_CHANNEL_ID}) or no memes ({len(memes)})")
        return
    channel = bot.get_channel(MEME_CHANNEL_ID)
    if not channel:
        logging.error(f"Meme channel not found: ID {MEME_CHANNEL_ID}")
        return
    meme = random.choice(memes)
    if isinstance(meme, dict) and meme.get("url"):
        embed = discord.Embed(title=meme.get("title", "😂 Daily Meme"), color=discord.Color.random())
        embed.set_image(url=meme["url"])
        await channel.send(embed=embed)
    else:
        await channel.send(str(meme))
    logging.info("Sent daily meme")

# =========================
# LIST FOLLOWED STREAMERS & YOUTUBE CHANNELS
# =========================
@bot.command(name="listfollows")
async def list_follows(ctx):
    twitch_list = streamers if streamers else ["(none)"]
    youtube_list = list(youtube_channels.keys()) if youtube_channels else ["(none)"]
    embed = discord.Embed(title="📺 Followed Channels", color=discord.Color.blue())
    embed.add_field(name="Twitch Streamers", value="\n".join(twitch_list), inline=False)
    embed.add_field(name="YouTube Channels", value="\n".join(youtube_list), inline=False)
    await ctx.send(embed=embed)

# =========================
# LEVELS SYSTEM
# =========================
LEVELS_FILE = "levels.json"
LEVEL_CONFIG = {
    "message_xp": 5,
    "catch_xp": 20,
    "meme_xp": 10,
    "joke_xp": 10,
    "duel_win_xp": 30,
    "battle_win_xp": 25,
    "announce_levelup": True
}

def load_levels():
    return load_json_file(LEVELS_FILE, {})

def save_levels(levels):
    save_json_file(LEVELS_FILE, levels)

levels = load_levels()

def add_xp(user_id: str, amount: int):
    user = levels.get(user_id, {"xp": 0, "level": 0})
    user["xp"] += amount
    import math
    new_level = int(math.sqrt(user["xp"] / 50))
    leveled_up = False
    if new_level > user.get("level", 0):
        user["level"] = new_level
        leveled_up = True
    levels[user_id] = user
    save_levels(levels)
    return user, leveled_up

@bot.command(name="level")
async def level_cmd(ctx, member: discord.Member = None):
    user = member or ctx.author
    data = levels.get(str(user.id), {"xp": 0, "level": 0})
    await ctx.send(f"⭐ {user.display_name} - Level {data.get('level', 0)} ({data.get('xp', 0)} XP)")

@bot.command(name="leaderboard")
async def leaderboard_cmd(ctx):
    if not levels:
        await ctx.send("📭 No levels recorded yet!")
        return
    sorted_lvls = sorted(levels.items(), key=lambda kv: kv[1].get("xp", 0), reverse=True)
    embed = discord.Embed(title="🏆 Level Leaderboard", color=discord.Color.gold())
    for i, (uid, data) in enumerate(sorted_lvls[:10], 1):
        try:
            user = await bot.fetch_user(int(uid))
            name = user.display_name
        except Exception:
            name = f"User {uid}"
        embed.add_field(name=f"#{i} {name}", value=f"Level {data.get('level', 0)} ({data.get('xp', 0)} XP)", inline=False)
    await ctx.send(embed=embed)

@bot.command(name="duel")
async def duel_cmd(ctx, opponent: discord.Member):
    if opponent.id == ctx.author.id:
        await ctx.send("❌ You cannot duel yourself!")
        return
    winner = random.choice([ctx.author, opponent])
    user, leveled_up = add_xp(str(winner.id), LEVEL_CONFIG["duel_win_xp"])
    await ctx.send(f"⚔️ {ctx.author.display_name} dueled {opponent.display_name}! **{winner.display_name}** wins and gains {LEVEL_CONFIG['duel_win_xp']} XP!")
    if leveled_up and LEVEL_CONFIG.get('announce_levelup', True):
        await ctx.send(f"🎉 {winner.mention} leveled up to **Level {user['level']}**!")
    logging.info(f"Duel: {ctx.author.display_name} vs {opponent.display_name}, winner: {winner.display_name}")

# =========================
# ADMIN: XP CONFIG / TOGGLES / RESETS
# =========================
@bot.command(name="setxp")
@commands.has_permissions(administrator=True)
async def setxp(ctx, xp_type: str, amount: int):
    key_map = {
        "message": "message_xp",
        "catch": "catch_xp",
        "meme": "meme_xp",
        "joke": "joke_xp",
        "duel_win": "duel_win_xp",
        "battle_win": "battle_win_xp"
    }
    if xp_type not in key_map:
        await ctx.send("❌ Invalid type. Use one of: message, catch, meme, joke, duel_win, battle_win")
        return
    LEVEL_CONFIG[key_map[xp_type]] = amount
    data = load_levels()
    data["_config"] = LEVEL_CONFIG
    save_levels(data)
    await ctx.send(f"✅ Updated **{xp_type}** XP to {amount}.")
    logging.info(f"Updated {xp_type} XP to {amount}")

@bot.command(name="getxpconfig")
@commands.has_permissions(administrator=True)
async def getxpconfig(ctx):
    embed = discord.Embed(title="⚙️ XP Configuration", color=discord.Color.purple())
    for key, value in LEVEL_CONFIG.items():
        embed.add_field(name=key, value=str(value), inline=True)
    await ctx.send(embed=embed)

@bot.command(name="togglelevelup")
@commands.has_permissions(administrator=True)
async def toggle_levelup(ctx):
    LEVEL_CONFIG["announce_levelup"] = not LEVEL_CONFIG.get("announce_levelup", True)
    state = "ON" if LEVEL_CONFIG["announce_levelup"] else "OFF"
    data = load_levels()
    data["_config"] = LEVEL_CONFIG
    save_levels(data)
    await ctx.send(f"🔔 Level-up announcements are now **{state}**.")
    logging.info(f"Level-up announcements set to {state}")

@bot.command(name="resetlevel")
@commands.has_permissions(administrator=True)
async def reset_level(ctx, member: discord.Member):
    user_id = str(member.id)
    if user_id in levels:
        levels[user_id] = {"xp": 0, "level": 0}
        save_levels(levels)
        await ctx.send(f"♻️ Reset {member.display_name}'s level and XP to 0.")
        logging.info(f"Reset level for {member.display_name}")
    else:
        await ctx.send(f"⚠️ {member.display_name} has no recorded XP/level yet.")

@bot.command(name="resetalllevels")
@commands.has_permissions(administrator=True)
async def reset_all_levels(ctx, confirm: str = None):
    if confirm != "confirm":
        await ctx.send("⚠️ This will reset ALL levels! Type `resetalllevels confirm` to proceed.")
        return
    global levels
    levels = {}
    save_levels(levels)
    await ctx.send("♻️ All user levels and XP have been reset.")
    logging.info("All levels reset")

# Custom Prefix
@bot.command(name="setprefix")
@commands.has_permissions(administrator=True)
async def setprefix(ctx, prefix: str):
    guild_id = str(ctx.guild.id)
    config.setdefault("prefixes", {})[guild_id] = prefix
    save_json_file(CONFIG_FILE, config)
    await ctx.send(f"✅ Command prefix set to `{prefix}`.")
    logging.info(f"Prefix set to {prefix} for guild {guild_id}")

# =========================
# ERRORS + STARTUP
# =========================
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, CommandOnCooldown):
        await ctx.reply(f"⏳ Wait {error.retry_after:.1f}s before reusing this.", delete_after=5, mention_author=False)
    elif isinstance(error, commands.CommandNotFound):
        await ctx.reply(f"❌ That command doesn’t exist. Try `{get_prefix(bot, ctx.message)}commands`.", delete_after=5, mention_author=False)
    elif isinstance(error, MissingPermissions):
        await ctx.reply("❌ You need admin permissions to use this command!", delete_after=5, mention_author=False)
    else:
        logging.error(f"Command error: {error}")
        raise error

@bot.event
async def on_ready():
    global pokemon_spawning, pokemon_loop_task
    logging.info(f"Bot ready as {bot.user}")
    logging.info(f"{len(bot.commands)} commands registered")
    channel = bot.get_channel(STARTUP_LOG_CHANNEL_ID or NOTIFY_CHANNEL_ID)
    if channel:
        await channel.send(f"✅ Bot ready as {bot.user}\n✅ {len(bot.commands)} commands registered")
    else:
        logging.error(f"Startup: Notify channel ID {STARTUP_LOG_CHANNEL_ID or NOTIFY_CHANNEL_ID} not found")
    if not pokemon_spawning:
        pokemon_spawning = True
        pokemon_loop_task = asyncio.create_task(pokemon_spawner())
        logging.info("Auto-started Pokémon spawning")
    if not twitch_notifier.is_running():
        twitch_notifier.start()
        logging.info("Auto-started Twitch notifier")
    if not youtube_notifier.is_running():
        youtube_notifier.start()
        logging.info("Auto-started YouTube notifier")
    if not daily_meme.is_running():
        daily_meme.start()
        logging.info("Auto-started daily meme")

bot.run(DISCORD_TOKEN)
