import os
import json
import random
import asyncio
import requests
import discord
from discord.ext import commands, tasks
from discord.ext.commands import CommandOnCooldown

print("Bot starting up...")

# =========================
# ENV VARS
# =========================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
NOTIFY_CHANNEL_ID = int(os.getenv("NOTIFY_CHANNEL_ID", 0))     # where Twitch/YT notifications go
POKEMON_CHANNEL_ID = int(os.getenv("POKEMON_CHANNEL_ID", 0))   # where Pokémon spawns happen
GUILD_ID = int(os.getenv("GUILD_ID", 0))                       # for role management
SHINY_RATE = float(os.getenv("SHINY_RATE", 0.01))              # default 1%

# Twitch / YouTube
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_SECRET = os.getenv("TWITCH_SECRET")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

# =========================
# DATA FILES
# =========================
NOTIFY_FILE = "notify_data.json"     # Twitch + YouTube lists and last seen video IDs
POKEMON_FILE = "pokemon_data.json"   # catches + streaks

MEME_FILE = "memes.json"             # memes list
JOKE_FILE = "jokes.json"             # jokes list

def load_json_file(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except Exception:
                pass
    return default

memes = load_json_file(MEME_FILE, [])
jokes = load_json_file(JOKE_FILE, [])


# =========================
# DISCORD BOT
# =========================
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# =========================
# PERSISTENCE HELPERS
# =========================
def load_notify_data():
    if os.path.exists(NOTIFY_FILE):
        with open(NOTIFY_FILE, "r") as f:
            try:
                return json.load(f)
            except Exception:
                pass
    # default structure: youtube_channels is dict channel_id -> last_video_id (or "")
    return {"streamers": [], "youtube_channels": {}}

def save_notify_data(d):
    with open(NOTIFY_FILE, "w") as f:
        json.dump(d, f, indent=2)

def load_pokemon_data():
    if os.path.exists(POKEMON_FILE):
        with open(POKEMON_FILE, "r") as f:
            try:
                return json.load(f)
            except Exception:
                pass
    return {"pokedex": {}, "streaks": {}}

def save_pokemon_data(poke):
    with open(POKEMON_FILE, "w") as f:
        json.dump(poke, f, indent=2)

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

# Rarity sets (hand-picked). Everything not in UNCOMMON/RARE/LEGENDARY becomes COMMON automatically.
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
CATCH_RATES = {"common": 0.8, "uncommon": 0.5, "rare": 0.3, "legendary": 0.05}

# =========================
# POKÉMON GAME
# =========================
pokemon_spawning = False
pokemon_loop_task = None
active_pokemon = None  # tuple (name, rarity, shiny)

async def pokemon_spawner():
    global active_pokemon
    await bot.wait_until_ready()
    channel = bot.get_channel(POKEMON_CHANNEL_ID)
    if not channel:
        print("⚠️ Pokémon channel not found.")
        return
    while pokemon_spawning:
        await asyncio.sleep(random.randint(30, 90))
        rarity = random.choices(["common","uncommon","rare","legendary"], weights=[70, 20, 9, 1])[0]
        pokemon = random.choice(POKEMON_RARITIES[rarity])
        shiny = (random.random() < SHINY_RATE)
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
    if name.strip().lower() != pokemon.lower():
        await ctx.send("❌ That’s not the Pokémon! The wild Pokémon escaped…")
        active_pokemon = None
        return

    chance = CATCH_RATES[rarity]
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

# =========================
# ROLE MANAGEMENT
# =========================
async def ensure_roles(guild: discord.Guild):
    top_role = discord.utils.get(guild.roles, name="Top Trainer")
    shiny_role = discord.utils.get(guild.roles, name="Shiny Master")
    if not top_role:
        top_role = await guild.create_role(name="Top Trainer", colour=discord.Colour.gold())
    if not shiny_role:
        shiny_role = await guild.create_role(name="Shiny Master", colour=discord.Colour.purple())
    return top_role, shiny_role

async def update_roles(guild: discord.Guild):
    if not guild or not pokedex:
        return
    top_role, shiny_role = await ensure_roles(guild)

    # Compute leaders
    top_trainer_id = max(pokedex.items(), key=lambda kv: len(kv[1]))[0]
    shiny_trainer_id = max(pokedex.items(), key=lambda kv: sum(1 for m in kv[1] if m["shiny"]))[0]

    for member in guild.members:
        # Top Trainer role
        if top_role in member.roles and str(member.id) != top_trainer_id:
            await member.remove_roles(top_role)
        if str(member.id) == top_trainer_id and top_role not in member.roles:
            await member.add_roles(top_role)

        # Shiny Master role
        if shiny_role in member.roles and str(member.id) != shiny_trainer_id:
            await member.remove_roles(shiny_role)
        if str(member.id) == shiny_trainer_id and shiny_role not in member.roles:
            await member.add_roles(shiny_role)

@bot.command(name="forceroles")
@commands.has_permissions(manage_guild=True)
async def forceroles(ctx):
    guild = ctx.guild or bot.get_guild(GUILD_ID)
    if not guild:
        await ctx.send("⚠️ Guild not found for role updates.")
        return
    await update_roles(guild)
    await ctx.send("🔄 Roles refreshed.")

# =========================
# TWITCH NOTIFIER
# =========================
TWITCH_ACCESS_TOKEN = None
TWITCH_TOKEN_EXPIRES = 0

def get_twitch_token():
    global TWITCH_ACCESS_TOKEN, TWITCH_TOKEN_EXPIRES
    if not TWITCH_CLIENT_ID or not TWITCH_SECRET:
        return None
    url = "https://id.twitch.tv/oauth2/token"
    params = {
        "client_id": TWITCH_CLIENT_ID,
        "client_secret": TWITCH_SECRET,
        "grant_type": "client_credentials"
    }
    try:
        r = requests.post(url, params=params, timeout=10)
        data = r.json()
        TWITCH_ACCESS_TOKEN = data.get("access_token")
        # no precise expiry from API here; just refresh every hour in loop
        TWITCH_TOKEN_EXPIRES = 3600
        return TWITCH_ACCESS_TOKEN
    except Exception as e:
        print("Twitch token error:", e)
        return None

def twitch_headers():
    if not TWITCH_ACCESS_TOKEN:
        get_twitch_token()
    if not TWITCH_ACCESS_TOKEN:
        return {}
    return {"Client-ID": TWITCH_CLIENT_ID, "Authorization": f"Bearer {TWITCH_ACCESS_TOKEN}"}

last_twitch_status = {}  # streamer -> bool

@tasks.loop(minutes=2)
async def twitch_notifier():
    if NOTIFY_CHANNEL_ID == 0 or not streamers:
        return
    channel = bot.get_channel(NOTIFY_CHANNEL_ID)
    if not channel:
        return
    for username in list(streamers):
        try:
            url = "https://api.twitch.tv/helix/streams"
            resp = requests.get(url, headers=twitch_headers(), params={"user_login": username}, timeout=10)
            data = resp.json()
            is_live = bool(data.get("data"))
            was_live = last_twitch_status.get(username, False)
            if is_live and not was_live:
                await channel.send(f"🎥 **{username} is LIVE on Twitch!** https://twitch.tv/{username}")
            last_twitch_status[username] = is_live
        except Exception as e:
            print(f"Twitch check error for {username}:", e)

# =========================
# YOUTUBE NOTIFIER
# =========================
@tasks.loop(minutes=5)
async def youtube_notifier():
    if NOTIFY_CHANNEL_ID == 0 or not youtube_channels or not YOUTUBE_API_KEY:
        return
    channel = bot.get_channel(NOTIFY_CHANNEL_ID)
    if not channel:
        return

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
            data = r.json()
            items = data.get("items", [])
            if not items:
                continue
            vid = items[0]["id"]["videoId"]
            title = items[0]["snippet"]["title"]

            if not last_vid:
                # seed without notifying the first time we see it
                youtube_channels[ch_id] = vid
                updated = True
            elif vid != last_vid:
                youtube_channels[ch_id] = vid
                updated = True
                await channel.send(f"▶️ New YouTube upload: **{title}**\nhttps://youtu.be/{vid}")
        except Exception as e:
            print(f"YouTube check error for {ch_id}:", e)

    if updated:
        notify_data["youtube_channels"] = youtube_channels
        save_notify_data(notify_data)

# =========================
# ADMIN: ADD STREAMERS / YT
# =========================
@bot.command(name="addstreamer")
@commands.has_permissions(manage_guild=True)
async def add_streamer(ctx, twitch_name: str):
    name = twitch_name.lower()
    if name in streamers:
        await ctx.send(f"⚠️ **{name}** is already in the Twitch list.")
        return
    streamers.append(name)
    notify_data["streamers"] = streamers
    save_notify_data(notify_data)
    await ctx.send(f"✅ Added **{name}** to Twitch notifications.")

@bot.command(name="addyoutube")
@commands.has_permissions(manage_guild=True)
async def add_youtube(ctx, channel_id: str):
    if channel_id in youtube_channels:
        await ctx.send(f"⚠️ Channel `{channel_id}` already tracked.")
        return
    youtube_channels[channel_id] = ""  # no last video yet
    notify_data["youtube_channels"] = youtube_channels
    save_notify_data(notify_data)
    await ctx.send(f"✅ Added YouTube channel `{channel_id}`. I’ll notify on the next upload.")

# =========================
# DM COMMAND MENUS
# =========================
@bot.command(name="commands")
@commands.cooldown(1, 20, commands.BucketType.user)
async def commands_list(ctx):
    embed = discord.Embed(title="📖 Commands", color=discord.Color.blue())
    embed.add_field(
        name="🎮 Fun / Pokémon",
        value="`!startpokemon`*, `!stoppokemon`*, `!catch <name>`, `!pokedex [@user]`, `!top`",
        inline=False
    )
    embed.add_field(
        name="🤣 Fun Extras",
        value="`!meme`, `!joke`",
        inline=False
    )
    embed.add_field(
        name="🔔 Notifications",
        value="Auto Twitch & YouTube alerts in the notify channel",
        inline=False
    )
    embed.set_footer(text="* admin only")
    try:
        await ctx.author.send(embed=embed)
        await ctx.reply("📬 Sent you a DM with the commands!", mention_author=False)
    except discord.Forbidden:
        await ctx.reply(embed=embed, mention_author=False)

@bot.command(name="admincommands")
@commands.has_permissions(manage_guild=True)
@commands.cooldown(1, 20, commands.BucketType.user)
async def admin_commands(ctx):
    embed = discord.Embed(title="⚙️ Admin Commands", color=discord.Color.red())
    embed.add_field(name="🔔 Notifiers", value="`!addstreamer <twitch_name>`, `!addyoutube <channel_id>`", inline=False)
    embed.add_field(name="🐾 Pokémon Control", value="`!startpokemon`, `!stoppokemon`, `!forceroles`", inline=False)
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
    if isinstance(meme, dict):
        title = meme.get("title", "")
        url = meme.get("url", "")
        if url:
            embed = discord.Embed(title=title or "😂 Meme", color=discord.Color.random())
            embed.set_image(url=url)
            await ctx.send(embed=embed)
        else:
            await ctx.send(title or "😂 Meme")
    else:
        await ctx.send(str(meme))

@bot.command(name="joke")
async def joke_cmd(ctx):
    if not jokes:
        await ctx.send("📭 No jokes available.")
        return
    joke = random.choice(jokes)
    if isinstance(joke, dict):
        setup = joke.get("setup")
        punchline = joke.get("punchline")
        if setup and punchline:
            await ctx.send(f"🤣 {setup}\n||{punchline}||")
        else:
            await ctx.send(joke.get("text", "😂 Bad joke file format!"))
    else:
        await ctx.send(str(joke))


# =========================
# ERRORS + STARTUP
# =========================
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, CommandOnCooldown):
        await ctx.reply(f"⏳ Wait {error.retry_after:.1f}s before reusing this.", delete_after=5, mention_author=False)
    elif isinstance(error, commands.CommandNotFound):
        await ctx.reply("❌ That command doesn’t exist. Try `!commands`.", delete_after=5, mention_author=False)
    else:
        raise error

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    # start background tasks
    if not twitch_notifier.is_running():
        twitch_notifier.start()
    if not youtube_notifier.is_running():
        youtube_notifier.start()
    # prepare roles
    guild = bot.get_guild(GUILD_ID)
    if guild:
        await ensure_roles(guild)
        await update_roles(guild)

bot.run(DISCORD_TOKEN)
