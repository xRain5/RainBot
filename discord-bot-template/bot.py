import os
import json
import random
import asyncio
import requests
import discord
from discord.ext import commands, tasks
from discord.ext.commands import CommandOnCooldown, MissingPermissions, MissingRole
import time
from dotenv import load_dotenv
import logging
from datetime import datetime, timedelta

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
JOKE_CHANNEL_ID = int(os.getenv("JOKE_CHANNEL_ID", 0))         # Daily jokes (replaces MEME_CHANNEL_ID)

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
logging.info(f"DEBUG: JOKE_CHANNEL_ID={JOKE_CHANNEL_ID}")
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
BATTLE_STATS_FILE = "battle_stats.json"  # Battle wins and losses

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
battle_stats = load_json_file(BATTLE_STATS_FILE, {})

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

# Track bot state
bot.is_shutdown = False
bot.daily_joke_task = None

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

def save_battle_stats():
    save_json_file(BATTLE_STATS_FILE, battle_stats)

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

# Gen 1 Type Chart (effectiveness: attacking type -> defending type)
TYPE_CHART = {
    "Normal": {"Rock": 0.5, "Ghost": 0},
    "Fire": {"Fire": 0.5, "Water": 0.5, "Grass": 2, "Ice": 2, "Bug": 2, "Rock": 0.5, "Dragon": 0.5},
    "Water": {"Fire": 2, "Water": 0.5, "Grass": 0.5, "Ground": 2, "Rock": 2, "Dragon": 0.5},
    "Grass": {"Fire": 0.5, "Water": 2, "Grass": 0.5, "Poison": 0.5, "Ground": 2, "Flying": 0.5, "Bug": 0.5, "Rock": 2, "Dragon": 0.5},
    "Electric": {"Water": 2, "Grass": 0.5, "Electric": 0.5, "Ground": 0, "Flying": 2, "Dragon": 0.5},
    "Ice": {"Fire": 0.5, "Water": 0.5, "Grass": 2, "Ice": 0.5, "Ground": 2, "Flying": 2, "Dragon": 2},
    "Fighting": {"Normal": 2, "Ice": 2, "Poison": 0.5, "Flying": 0.5, "Psychic": 0.5, "Bug": 0.5, "Rock": 2, "Ghost": 0},
    "Poison": {"Grass": 2, "Poison": 0.5, "Ground": 0.5, "Bug": 2, "Rock": 0.5, "Ghost": 0.5},
    "Ground": {"Fire": 2, "Electric": 2, "Grass": 0.5, "Poison": 2, "Flying": 0, "Bug": 0.5, "Rock": 2},
    "Flying": {"Electric": 0.5, "Grass": 2, "Fighting": 2, "Bug": 2, "Rock": 0.5},
    "Psychic": {"Fighting": 2, "Poison": 2, "Psychic": 0.5, "Ghost": 0},  # Gen 1: Psychic immune to Ghost
    "Bug": {"Fire": 0.5, "Grass": 2, "Fighting": 0.5, "Poison": 2, "Flying": 0.5, "Psychic": 2, "Ghost": 0.5, "Rock": 0.5},
    "Rock": {"Fire": 2, "Ice": 2, "Fighting": 0.5, "Ground": 0.5, "Flying": 2, "Bug": 2},
    "Ghost": {"Normal": 0, "Psychic": 0, "Ghost": 2},  # Gen 1 bug: Ghost not effective on Psychic
    "Dragon": {"Dragon": 2},
}

# Pokémon Stats: name -> {"types": list, "bst": int}
POKEMON_STATS = {
    "Bulbasaur": {"types": ["Grass", "Poison"], "bst": 318},
    "Ivysaur": {"types": ["Grass", "Poison"], "bst": 405},
    "Venusaur": {"types": ["Grass", "Poison"], "bst": 525},
    "Charmander": {"types": ["Fire"], "bst": 309},
    "Charmeleon": {"types": ["Fire"], "bst": 405},
    "Charizard": {"types": ["Fire", "Flying"], "bst": 534},
    "Squirtle": {"types": ["Water"], "bst": 314},
    "Wartortle": {"types": ["Water"], "bst": 405},
    "Blastoise": {"types": ["Water"], "bst": 530},
    "Caterpie": {"types": ["Bug"], "bst": 195},
    "Metapod": {"types": ["Bug"], "bst": 205},
    "Butterfree": {"types": ["Bug", "Flying"], "bst": 395},
    "Weedle": {"types": ["Bug", "Poison"], "bst": 195},
    "Kakuna": {"types": ["Bug", "Poison"], "bst": 205},
    "Beedrill": {"types": ["Bug", "Poison"], "bst": 395},
    "Pidgey": {"types": ["Normal", "Flying"], "bst": 251},
    "Pidgeotto": {"types": ["Normal", "Flying"], "bst": 349},
    "Pidgeot": {"types": ["Normal", "Flying"], "bst": 479},
    "Rattata": {"types": ["Normal"], "bst": 253},
    "Raticate": {"types": ["Normal"], "bst": 413},
    "Spearow": {"types": ["Normal", "Flying"], "bst": 262},
    "Fearow": {"types": ["Normal", "Flying"], "bst": 442},
    "Ekans": {"types": ["Poison"], "bst": 288},
    "Arbok": {"types": ["Poison"], "bst": 438},
    "Pikachu": {"types": ["Electric"], "bst": 320},
    "Raichu": {"types": ["Electric"], "bst": 485},
    "Sandshrew": {"types": ["Ground"], "bst": 300},
    "Sandslash": {"types": ["Ground"], "bst": 450},
    "Nidoran-F": {"types": ["Poison"], "bst": 275},
    "Nidorina": {"types": ["Poison"], "bst": 365},
    "Nidoqueen": {"types": ["Poison", "Ground"], "bst": 505},
    "Nidoran-M": {"types": ["Poison"], "bst": 273},
    "Nidorino": {"types": ["Poison"], "bst": 365},
    "Nidoking": {"types": ["Poison", "Ground"], "bst": 505},
    "Clefairy": {"types": ["Normal"], "bst": 323},
    "Clefable": {"types": ["Normal"], "bst": 483},
    "Vulpix": {"types": ["Fire"], "bst": 299},
    "Ninetales": {"types": ["Fire"], "bst": 505},
    "Jigglypuff": {"types": ["Normal"], "bst": 270},
    "Wigglytuff": {"types": ["Normal"], "bst": 435},
    "Zubat": {"types": ["Poison", "Flying"], "bst": 245},
    "Golbat": {"types": ["Poison", "Flying"], "bst": 455},
    "Oddish": {"types": ["Grass", "Poison"], "bst": 320},
    "Gloom": {"types": ["Grass", "Poison"], "bst": 395},
    "Vileplume": {"types": ["Grass", "Poison"], "bst": 490},
    "Paras": {"types": ["Bug", "Grass"], "bst": 285},
    "Parasect": {"types": ["Bug", "Grass"], "bst": 405},
    "Venonat": {"types": ["Bug", "Poison"], "bst": 305},
    "Venomoth": {"types": ["Bug", "Poison"], "bst": 450},
    "Diglett": {"types": ["Ground"], "bst": 265},
    "Dugtrio": {"types": ["Ground"], "bst": 405},
    "Meowth": {"types": ["Normal"], "bst": 290},
    "Persian": {"types": ["Normal"], "bst": 440},
    "Psyduck": {"types": ["Water"], "bst": 320},
    "Golduck": {"types": ["Water"], "bst": 500},
    "Mankey": {"types": ["Fighting"], "bst": 305},
    "Primeape": {"types": ["Fighting"], "bst": 455},
    "Growlithe": {"types": ["Fire"], "bst": 350},
    "Arcanine": {"types": ["Fire"], "bst": 555},
    "Poliwag": {"types": ["Water"], "bst": 300},
    "Poliwhirl": {"types": ["Water"], "bst": 385},
    "Poliwrath": {"types": ["Water", "Fighting"], "bst": 510},
    "Abra": {"types": ["Psychic"], "bst": 310},
    "Kadabra": {"types": ["Psychic"], "bst": 400},
    "Alakazam": {"types": ["Psychic"], "bst": 500},
    "Machop": {"types": ["Fighting"], "bst": 305},
    "Machoke": {"types": ["Fighting"], "bst": 405},
    "Machamp": {"types": ["Fighting"], "bst": 505},
    "Bellsprout": {"types": ["Grass", "Poison"], "bst": 300},
    "Weepinbell": {"types": ["Grass", "Poison"], "bst": 390},
    "Victreebel": {"types": ["Grass", "Poison"], "bst": 490},
    "Tentacool": {"types": ["Water", "Poison"], "bst": 335},
    "Tentacruel": {"types": ["Water", "Poison"], "bst": 515},
    "Geodude": {"types": ["Rock", "Ground"], "bst": 300},
    "Graveler": {"types": ["Rock", "Ground"], "bst": 390},
    "Golem": {"types": ["Rock", "Ground"], "bst": 495},
    "Ponyta": {"types": ["Fire"], "bst": 410},
    "Rapidash": {"types": ["Fire"], "bst": 500},
    "Slowpoke": {"types": ["Water", "Psychic"], "bst": 315},
    "Slowbro": {"types": ["Water", "Psychic"], "bst": 490},
    "Magnemite": {"types": ["Electric"], "bst": 325},
    "Magneton": {"types": ["Electric"], "bst": 465},
    "Farfetch'd": {"types": ["Normal", "Flying"], "bst": 352},
    "Doduo": {"types": ["Normal", "Flying"], "bst": 310},
    "Dodrio": {"types": ["Normal", "Flying"], "bst": 460},
    "Seel": {"types": ["Water"], "bst": 325},
    "Dewgong": {"types": ["Water", "Ice"], "bst": 475},
    "Grimer": {"types": ["Poison"], "bst": 325},
    "Muk": {"types": ["Poison"], "bst": 500},
    "Shellder": {"types": ["Water"], "bst": 305},
    "Cloyster": {"types": ["Water", "Ice"], "bst": 525},
    "Gastly": {"types": ["Ghost", "Poison"], "bst": 310},
    "Haunter": {"types": ["Ghost", "Poison"], "bst": 405},
    "Gengar": {"types": ["Ghost", "Poison"], "bst": 500},
    "Onix": {"types": ["Rock", "Ground"], "bst": 385},
    "Drowzee": {"types": ["Psychic"], "bst": 328},
    "Hypno": {"types": ["Psychic"], "bst": 483},
    "Krabby": {"types": ["Water"], "bst": 325},
    "Kingler": {"types": ["Water"], "bst": 475},
    "Voltorb": {"types": ["Electric"], "bst": 330},
    "Electrode": {"types": ["Electric"], "bst": 480},
    "Exeggcute": {"types": ["Grass", "Psychic"], "bst": 325},
    "Exeggutor": {"types": ["Grass", "Psychic"], "bst": 520},
    "Cubone": {"types": ["Ground"], "bst": 320},
    "Marowak": {"types": ["Ground"], "bst": 425},
    "Hitmonlee": {"types": ["Fighting"], "bst": 455},
    "Hitmonchan": {"types": ["Fighting"], "bst": 455},
    "Lickitung": {"types": ["Normal"], "bst": 385},
    "Koffing": {"types": ["Poison"], "bst": 340},
    "Weezing": {"types": ["Poison"], "bst": 490},
    "Rhyhorn": {"types": ["Ground", "Rock"], "bst": 345},
    "Rhydon": {"types": ["Ground", "Rock"], "bst": 485},
    "Chansey": {"types": ["Normal"], "bst": 450},
    "Tangela": {"types": ["Grass"], "bst": 435},
    "Kangaskhan": {"types": ["Normal"], "bst": 490},
    "Horsea": {"types": ["Water"], "bst": 295},
    "Seadra": {"types": ["Water"], "bst": 440},
    "Goldeen": {"types": ["Water"], "bst": 320},
    "Seaking": {"types": ["Water"], "bst": 450},
    "Staryu": {"types": ["Water"], "bst": 340},
    "Starmie": {"types": ["Water", "Psychic"], "bst": 520},
    "Mr. Mime": {"types": ["Psychic"], "bst": 460},
    "Scyther": {"types": ["Bug", "Flying"], "bst": 500},
    "Jynx": {"types": ["Ice", "Psychic"], "bst": 455},
    "Electabuzz": {"types": ["Electric"], "bst": 490},
    "Magmar": {"types": ["Fire"], "bst": 495},
    "Pinsir": {"types": ["Bug"], "bst": 500},
    "Tauros": {"types": ["Normal"], "bst": 490},
    "Magikarp": {"types": ["Water"], "bst": 200},
    "Gyarados": {"types": ["Water", "Flying"], "bst": 540},
    "Lapras": {"types": ["Water", "Ice"], "bst": 535},
    "Ditto": {"types": ["Normal"], "bst": 288},
    "Eevee": {"types": ["Normal"], "bst": 325},
    "Vaporeon": {"types": ["Water"], "bst": 525},
    "Jolteon": {"types": ["Electric"], "bst": 525},
    "Flareon": {"types": ["Fire"], "bst": 525},
    "Porygon": {"types": ["Normal"], "bst": 395},
    "Omanyte": {"types": ["Rock", "Water"], "bst": 355},
    "Omastar": {"types": ["Rock", "Water"], "bst": 495},
    "Kabuto": {"types": ["Rock", "Water"], "bst": 355},
    "Kabutops": {"types": ["Rock", "Water"], "bst": 495},
    "Aerodactyl": {"types": ["Rock", "Flying"], "bst": 515},
    "Snorlax": {"types": ["Normal"], "bst": 540},
    "Articuno": {"types": ["Ice", "Flying"], "bst": 580},
    "Zapdos": {"types": ["Electric", "Flying"], "bst": 580},
    "Moltres": {"types": ["Fire", "Flying"], "bst": 580},
    "Dratini": {"types": ["Dragon"], "bst": 300},
    "Dragonair": {"types": ["Dragon"], "bst": 420},
    "Dragonite": {"types": ["Dragon", "Flying"], "bst": 600},
    "Mewtwo": {"types": ["Psychic"], "bst": 680},
    "Mew": {"types": ["Psychic"], "bst": 600},
}

def get_effectiveness(att_type, def_types):
    eff = 1.0
    for def_type in def_types:
        eff *= TYPE_CHART.get(att_type, {}).get(def_type, 1.0)
    return eff

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
    if bot.is_shutdown:
        await ctx.send("❌ Bot is currently shut down. Use `!restartbot` to restart.")
        return
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
    if bot.is_shutdown:
        await ctx.send("❌ Bot is currently shut down. Use `!restartbot` to restart.")
        return
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
    if bot.is_shutdown:
        await ctx.send("❌ Bot is currently shut down. Use `!restartbot` to restart.")
        return
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
    if bot.is_shutdown:
        await ctx.send("❌ Bot is currently shut down. Use `!restartbot` to restart.")
        return
    if seconds < 0:
        await ctx.send("❌ Cooldown must be 0 or greater.")
    else:
        CATCH_COOLDOWN = seconds
        await ctx.send(f"✅ Catch cooldown set to {CATCH_COOLDOWN} seconds.")
        logging.info(f"Catch cooldown set to {CATCH_COOLDOWN} seconds")

@bot.command(name="catch")
async def catch(ctx, *, name: str):
    global active_pokemon
    if bot.is_shutdown:
        await ctx.send("❌ Bot is currently shut down. Use `!restartbot` to restart.")
        return
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
    if bot.is_shutdown:
        await ctx.send("❌ Bot is currently shut down. Use `!restartbot` to restart.")
        return
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
    if bot.is_shutdown:
        await ctx.send("❌ Bot is currently shut down. Use `!restartbot` to restart.")
        return
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

@bot.command(name="battletop")
async def battletop(ctx):
    if bot.is_shutdown:
        await ctx.send("❌ Bot is currently shut down. Use `!restartbot` to restart.")
        return
    if not battle_stats:
        await ctx.send("📭 No battles have been fought yet!")
        return
    leaders = []
    for uid, stats in battle_stats.items():
        total = stats["wins"] + stats["losses"]
        if total > 0:
            perc = (stats["wins"] / total) * 100
            leaders.append((uid, perc, stats["wins"]))
    leaders.sort(key=lambda x: (x[1], x[2]), reverse=True)
    embed = discord.Embed(title="🏆 Top Battle Trainers (Win %)", color=discord.Color.gold())
    for i, (uid, perc, wins) in enumerate(leaders[:10], 1):
        try:
            user = await bot.fetch_user(int(uid))
            name = user.display_name
        except Exception:
            name = f"User {uid}"
        embed.add_field(name=f"#{i} {name}", value=f"{perc:.1f}% win rate ({wins} wins)", inline=False)
    await ctx.send(embed=embed)

# Pokémon Trading
pending_trades = {}  # {user_id: (target_id, pokemon_name)}

@bot.command(name="trade")
async def trade(ctx, member: discord.Member, pokemon_name: str):
    if bot.is_shutdown:
        await ctx.send("❌ Bot is currently shut down. Use `!restartbot` to restart.")
        return
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
    if bot.is_shutdown:
        await ctx.send("❌ Bot is currently shut down. Use `!restartbot` to restart.")
        return
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
    if bot.is_shutdown:
        await ctx.send("❌ Bot is currently shut down. Use `!restartbot` to restart.")
        return
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
    user_pok = POKEMON_STATS[user_pokemon["name"]]
    opp_pok = POKEMON_STATS[opp_pokemon["name"]]
    user_eff = get_effectiveness(user_pok["types"][0], opp_pok["types"])
    opp_eff = get_effectiveness(opp_pok["types"][0], user_pok["types"])
    user_score = user_pok["bst"] * user_eff * (1.1 if user_pokemon["shiny"] else 1.0)
    opp_score = opp_pok["bst"] * opp_eff * (1.1 if opp_pokemon["shiny"] else 1.0)
    if user_score == opp_score:
        winner = random.choice([ctx.author, opponent])
    else:
        prob_user = user_score / (user_score + opp_score)
        winner = ctx.author if random.random() < prob_user else opponent
    winner_id = str(winner.id)
    loser_id = opp_id if winner_id == user_id else user_id
    battle_stats.setdefault(winner_id, {"wins": 0, "losses": 0})["wins"] += 1
    battle_stats.setdefault(loser_id, {"wins": 0, "losses": 0})["losses"] += 1
    save_battle_stats()
    await ctx.send(f"⚔️ {ctx.author.display_name}'s {user_pokemon['name']} vs {opponent.display_name}'s {opp_pokemon['name']}! **{winner.display_name}** wins!")
    user, leveled_up = add_xp(winner_id, LEVEL_CONFIG.get("battle_win_xp", 25))
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
    if bot.is_shutdown:
        return
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
    if bot.is_shutdown:
        await ctx.send("❌ Bot is currently shut down. Use `!restartbot` to restart.")
        return
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
    if bot.is_shutdown:
        return
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
    if bot.is_shutdown:
        return
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
    if bot.is_shutdown:
        await ctx.send("❌ Bot is currently shut down. Use `!restartbot` to restart.")
        return
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
    if bot.is_shutdown:
        await ctx.send("❌ Bot is currently shut down. Use `!restartbot` to restart.")
        return
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
    if bot.is_shutdown:
        await ctx.send("❌ Bot is currently shut down. Use `!restartbot` to restart.")
        return
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
    if bot.is_shutdown:
        await ctx.send("❌ Bot is currently shut down. Use `!restartbot` to restart.")
        return
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
    if bot.is_shutdown:
        await ctx.send("❌ Bot is currently shut down. Use `!restartbot` to restart.")
        return
    global TWITCH_CHANNEL_ID
    TWITCH_CHANNEL_ID = channel.id
    await ctx.send(f"✅ Twitch notifications will now go to {channel.mention}.")
    logging.info(f"Twitch notification channel set to {channel.id}")

@bot.command(name="setyoutubechannel")
@commands.has_permissions(administrator=True)
async def set_youtube_channel(ctx, channel: discord.TextChannel):
    if bot.is_shutdown:
        await ctx.send("❌ Bot is currently shut down. Use `!restartbot` to restart.")
        return
    global YOUTUBE_CHANNEL_ID
    YOUTUBE_CHANNEL_ID = channel.id
    await ctx.send(f"✅ YouTube notifications will now go to {channel.mention}.")
    logging.info(f"YouTube notification channel set to {channel.id}")

@bot.command(name="setjokechannel")
@commands.has_permissions(administrator=True)
async def set_joke_channel(ctx, channel: discord.TextChannel):
    if bot.is_shutdown:
        await ctx.send("❌ Bot is currently shut down. Use `!restartbot` to restart.")
        return
    global JOKE_CHANNEL_ID
    JOKE_CHANNEL_ID = channel.id
    await ctx.send(f"✅ Daily jokes will now go to {channel.mention}.")
    logging.info(f"Joke channel set to {channel.id}")

# =========================
# MODERATOR COMMANDS
# =========================
@bot.command(name="shutdownbot")
@commands.has_role("Moderator")
async def shutdownbot(ctx):
    if bot.is_shutdown:
        await ctx.send("❌ Bot is already shut down.")
        return
    global pokemon_spawning, pokemon_loop_task
    # Stop Pokémon spawner
    if pokemon_spawning and pokemon_loop_task:
        pokemon_spawning = False
        pokemon_loop_task.cancel()
        pokemon_loop_task = None
        logging.info("Pokémon spawner stopped via shutdownbot")
    # Stop notifiers
    if twitch_notifier.is_running():
        twitch_notifier.cancel()
        logging.info("Twitch notifier stopped via shutdownbot")
    if youtube_notifier.is_running():
        youtube_notifier.cancel()
        logging.info("YouTube notifier stopped via shutdownbot")
    if bot.daily_joke_task:
        bot.daily_joke_task.cancel()
        bot.daily_joke_task = None
        logging.info("Daily joke task stopped via shutdownbot")
    # Set shutdown state
    bot.is_shutdown = True
    # Log out
    await ctx.send("🛑 Bot is shutting down...")
    logging.info(f"Bot shutdown initiated by {ctx.author.display_name}")
    await bot.close()

@bot.command(name="restartbot")
@commands.has_role("Moderator")
async def restartbot(ctx):
    if not bot.is_shutdown:
        await ctx.send("❌ Bot is already running.")
        return
    global pokemon_spawning, pokemon_loop_task
    bot.is_shutdown = False
    # Restart tasks
    if not pokemon_spawning:
        pokemon_spawning = True
        pokemon_loop_task = asyncio.create_task(pokemon_spawner())
        logging.info("Pokémon spawning restarted via restartbot")
    if not twitch_notifier.is_running():
        twitch_notifier.start()
        logging.info("Twitch notifier restarted via restartbot")
    if not youtube_notifier.is_running():
        youtube_notifier.start()
        logging.info("YouTube notifier restarted via restartbot")
    if not bot.daily_joke_task:
        bot.daily_joke_task = asyncio.create_task(daily_joke())
        logging.info("Daily joke task restarted via restartbot")
    await ctx.send(f"✅ Bot restarted by {ctx.author.mention}.")
    logging.info(f"Bot restarted by {ctx.author.display_name}")

# =========================
# DM COMMAND MENUS
# =========================
@bot.command(name="commands")
@commands.cooldown(1, 20, commands.BucketType.user)
async def commands_list(ctx):
    if bot.is_shutdown:
        await ctx.send("❌ Bot is currently shut down. Use `!restartbot` to restart.")
        return
    embed = discord.Embed(title="📖 Commands", color=discord.Color.blue())
    embed.add_field(
        name="🎮 Pokémon Game",
        value="`catch <name>`, `pokedex [@user]`, `top`, `battletop`, `trade @user <pokemon>`, `accept`, `battle @user`",
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
        name="⚙️ Admin/Moderator Commands",
        value="Use `admincommands` for admin-only commands or `modcommands` for moderator commands.",
        inline=False
    )
    embed.set_footer(text="Type admincommands or modcommands for full command lists if you have access.")
    try:
        await ctx.author.send(embed=embed)
        await ctx.reply("📬 Sent you a DM with the commands!", mention_author=False)
    except discord.Forbidden:
        await ctx.reply(embed=embed, mention_author=False)

@bot.command(name="admincommands")
@commands.cooldown(1, 20, commands.BucketType.user)
async def admin_commands(ctx):
    if bot.is_shutdown:
        await ctx.send("❌ Bot is currently shut down. Use `!restartbot` to restart.")
        return
    embed = discord.Embed(title="⚙️ Admin Commands", color=discord.Color.red())
    embed.add_field(
        name="🐾 Pokémon Control",
        value="`startpokemon`, `stoppokemon`, `setcatchcd <seconds>`, `forceroles`",
        inline=False
    )
    embed.add_field(
        name="🔔 Notifications Management",
        value="`addstreamer <twitch_name>`, `addyoutube <channel_id>`, `removestreamer <twitch_name>`, `removeyoutube <channel_id>`, `settwitchchannel #channel`, `setyoutubechannel #channel`, `setjokechannel #channel`, `listfollows`",
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

@bot.command(name="modcommands")
@commands.cooldown(1, 20, commands.BucketType.user)
async def mod_commands(ctx):
    if bot.is_shutdown:
        await ctx.send("❌ Bot is currently shut down. Use `!restartbot` to restart.")
        return
    embed = discord.Embed(title="🛠️ Moderator Commands", color=discord.Color.orange())
    embed.add_field(
        name="⚙️ Bot Control",
        value="`shutdownbot`, `restartbot`",
        inline=False
    )
    try:
        await ctx.author.send(embed=embed)
        await ctx.reply("📬 Sent you a DM with the moderator commands!", mention_author=False)
    except discord.Forbidden:
        await ctx.reply(embed=embed, mention_author=False)

# =========================
# FUN COMMANDS: MEMES & JOKES
# =========================
@bot.command(name="meme")
async def meme_cmd(ctx):
    if bot.is_shutdown:
        await ctx.send("❌ Bot is currently shut down. Use `!restartbot` to restart.")
        return
    if not memes:
        await ctx.send("📭 No memes available.")
        return
    meme = random.choice(memes)
    embed = discord.Embed(title=meme.get("title", "😂 Meme"), color=discord.Color.random())
    if isinstance(meme, dict) and meme.get("url"):
        embed.set_image(url=meme["url"])
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"📭 Meme could not be embedded: {meme.get('title', str(meme))}")
    user, leveled_up = add_xp(str(ctx.author.id), LEVEL_CONFIG['meme_xp'])
    if leveled_up and LEVEL_CONFIG.get('announce_levelup', True):
        await ctx.send(f"🎉 {ctx.author.mention} leveled up to **Level {user['level']}**!")

@bot.command(name="joke")
async def joke_cmd(ctx):
    if bot.is_shutdown:
        await ctx.send("❌ Bot is currently shut down. Use `!restartbot` to restart.")
        return
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

# Daily Joke Task
async def daily_joke():
    await bot.wait_until_ready()
    if JOKE_CHANNEL_ID == 0 or not jokes:
        logging.error(f"Daily joke skipped: Invalid channel ID ({JOKE_CHANNEL_ID}) or no jokes ({len(jokes)})")
        return
    channel = bot.get_channel(JOKE_CHANNEL_ID)
    if not channel:
        logging.error(f"Joke channel not found: ID {JOKE_CHANNEL_ID}")
        return
    while not bot.is_shutdown:
        now = datetime.utcnow()
        # Set target time to 8:00 AM UTC (adjust as needed)
        target_time = now.replace(hour=8, minute=0, second=0, microsecond=0)
        if now >= target_time:
            target_time += timedelta(days=1)
        seconds_until = (target_time - now).total_seconds()
        logging.info(f"Daily joke scheduled for {target_time}, waiting {seconds_until:.0f} seconds")
        await asyncio.sleep(seconds_until)
        if bot.is_shutdown:
            break
        joke = random.choice(jokes)
        sent = False
        if isinstance(joke, dict):
            setup = joke.get("setup")
            punchline = joke.get("punchline")
            text = joke.get("text")
            if setup and punchline:
                await channel.send(f"🤣 {setup}\n||{punchline}||")
                sent = True
            elif text:
                await channel.send(text)
                sent = True
        if not sent:
            await channel.send(str(joke))
        logging.info(f"Sent daily joke at {datetime.utcnow()}")

# =========================
# LIST FOLLOWED STREAMERS & YOUTUBE CHANNELS
# =========================
@bot.command(name="listfollows")
async def list_follows(ctx):
    if bot.is_shutdown:
        await ctx.send("❌ Bot is currently shut down. Use `!restartbot` to restart.")
        return
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
    data = load_json_file(LEVELS_FILE, {})
    global LEVEL_CONFIG
    if "_config" in data:
        LEVEL_CONFIG.update(data.pop("_config"))
    logging.info(f"Levels loaded: {len(data)} users")
    return data

def save_levels(levels):
    data = levels.copy()
    data["_config"] = LEVEL_CONFIG
    save_json_file(LEVELS_FILE, data)
    logging.info(f"Levels saved: {len(levels)} users")

levels = load_levels()

def add_xp(user_id: str, amount: int):
    user = levels.get(user_id, {"xp": 0, "level": 0})
    user["xp"] += amount
    import math
    new_level = int(math.sqrt(user["xp"] / 25))  # Reduced from 50 for faster leveling
    leveled_up = False
    if new_level > user.get("level", 0):
        user["level"] = new_level
        leveled_up = True
    levels[user_id] = user
    save_levels(levels)
    logging.info(f"XP added for user {user_id}: +{amount} XP, now Level {user['level']} ({user['xp']} XP)")
    return user, leveled_up

@bot.command(name="level")
async def level_cmd(ctx, member: discord.Member = None):
    if bot.is_shutdown:
        await ctx.send("❌ Bot is currently shut down. Use `!restartbot` to restart.")
        return
    user = member or ctx.author
    data = levels.get(str(user.id), {"xp": 0, "level": 0})
    await ctx.send(f"⭐ {user.display_name} - Level {data.get('level', 0)} ({data.get('xp', 0)} XP)")

@bot.command(name="leaderboard")
async def leaderboard_cmd(ctx):
    if bot.is_shutdown:
        await ctx.send("❌ Bot is currently shut down. Use `!restartbot` to restart.")
        return
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
    if bot.is_shutdown:
        await ctx.send("❌ Bot is currently shut down. Use `!restartbot` to restart.")
        return
    if opponent.id == ctx.author.id:
        await ctx.send("❌ You cannot duel yourself!")
        return
    winner = random.choice([ctx.author, opponent])
    user, leveled_up = add_xp(str(winner.id), LEVEL_CONFIG["duel_win_xp"])
    await ctx.send(f"⚔️ {ctx.author.display_name} dueled {opponent.display_name}! **{winner.display_name}** wins and gains {LEVEL_CONFIG['duel_win_xp']} XP!")
    if leveled_up and LEVEL_CONFIG.get('announce_levelup', True):
        await ctx.send(f"🎉 {winner.mention} leveled up to **Level {user['level']}**!")
    logging.info(f"Duel: {ctx.author.display_name} vs {opponent.display_name}, winner: {winner.display_name}")

# Message XP
@bot.event
async def on_message(message):
    if bot.is_shutdown or message.author.bot or not message.guild:
        return
    # Check if the message is a command
    prefix = get_prefix(bot, message)
    if not message.content.startswith(prefix):
        user, leveled_up = add_xp(str(message.author.id), LEVEL_CONFIG["message_xp"])
        if leveled_up and LEVEL_CONFIG.get('announce_levelup', True):
            await message.channel.send(f"🎉 {message.author.mention} leveled up to **Level {user['level']}**!")
    await bot.process_commands(message)

# =========================
# ADMIN: XP CONFIG / TOGGLES / RESETS
# =========================
@bot.command(name="setxp")
@commands.has_permissions(administrator=True)
async def setxp(ctx, xp_type: str, amount: int):
    if bot.is_shutdown:
        await ctx.send("❌ Bot is currently shut down. Use `!restartbot` to restart.")
        return
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
    save_levels(levels)
    await ctx.send(f"✅ Updated **{xp_type}** XP to {amount}.")
    logging.info(f"Updated {xp_type} XP to {amount}")

@bot.command(name="getxpconfig")
@commands.has_permissions(administrator=True)
async def getxpconfig(ctx):
    if bot.is_shutdown:
        await ctx.send("❌ Bot is currently shut down. Use `!restartbot` to restart.")
        return
    embed = discord.Embed(title="⚙️ XP Configuration", color=discord.Color.purple())
    for key, value in LEVEL_CONFIG.items():
        embed.add_field(name=key, value=str(value), inline=True)
    await ctx.send(embed=embed)

@bot.command(name="togglelevelup")
@commands.has_permissions(administrator=True)
async def toggle_levelup(ctx):
    if bot.is_shutdown:
        await ctx.send("❌ Bot is currently shut down. Use `!restartbot` to restart.")
        return
    LEVEL_CONFIG["announce_levelup"] = not LEVEL_CONFIG.get("announce_levelup", True)
    state = "ON" if LEVEL_CONFIG["announce_levelup"] else "OFF"
    save_levels(levels)
    await ctx.send(f"🔔 Level-up announcements are now **{state}**.")
    logging.info(f"Level-up announcements set to {state}")

@bot.command(name="resetlevel")
@commands.has_permissions(administrator=True)
async def reset_level(ctx, member: discord.Member):
    if bot.is_shutdown:
        await ctx.send("❌ Bot is currently shut down. Use `!restartbot` to restart.")
        return
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
    if bot.is_shutdown:
        await ctx.send("❌ Bot is currently shut down. Use `!restartbot` to restart.")
        return
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
    if bot.is_shutdown:
        await ctx.send("❌ Bot is currently shut down. Use `!restartbot` to restart.")
        return
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
    if bot.is_shutdown:
        await ctx.send("❌ Bot is currently shut down. Use `!restartbot` to restart.")
        return
    if isinstance(error, CommandOnCooldown):
        await ctx.reply(f"⏳ Wait {error.retry_after:.1f}s before reusing this.", delete_after=5, mention_author=False)
    elif isinstance(error, commands.CommandNotFound):
        await ctx.reply(f"❌ That command doesn’t exist. Try `{get_prefix(bot, ctx.message)}commands`.", delete_after=5, mention_author=False)
    elif isinstance(error, MissingPermissions):
        await ctx.reply("❌ You need admin permissions to use this command!", delete_after=5, mention_author=False)
    elif isinstance(error, MissingRole):
        await ctx.reply("❌ You need the Moderator role to use this command!", delete_after=5, mention_author=False)
    else:
        logging.error(f"Command error: {error}")
        raise error

@bot.event
async def on_ready():
    global pokemon_spawning, pokemon_loop_task
    bot.is_shutdown = False
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
    if not bot.daily_joke_task:
        bot.daily_joke_task = asyncio.create_task(daily_joke())
        logging.info("Auto-started daily joke")

bot.run(DISCORD_TOKEN)
4.2s



Upgrade to SuperGrok
New conversation - Grok
