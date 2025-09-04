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
NOTIFY_CHANNEL_ID = int(os.getenv("NOTIFY_CHANNEL_ID", 0))
POKEMON_CHANNEL_ID = int(os.getenv("POKEMON_CHANNEL_ID", 0))
GUILD_ID = int(os.getenv("GUILD_ID", 0))

# Role colors
POKEMON_MASTER_COLOR = int(os.getenv("POKEMON_MASTER_COLOR", "0000FF"), 16)
SHINY_MASTER_COLOR = int(os.getenv("SHINY_MASTER_COLOR", "800080"), 16)

# Spawn rates (fallback defaults if not set in .env)
rarity_spawn_rates = {
    "Common": float(os.getenv("SPAWN_COMMON", 0.60)),
    "Uncommon": float(os.getenv("SPAWN_UNCOMMON", 0.25)),
    "Rare": float(os.getenv("SPAWN_RARE", 0.10)),
    "Legendary": float(os.getenv("SPAWN_LEGENDARY", 0.05)),
}

# Catch rates
catch_rates = {
    "Common": float(os.getenv("CATCH_COMMON", 0.80)),
    "Uncommon": float(os.getenv("CATCH_UNCOMMON", 0.60)),
    "Rare": float(os.getenv("CATCH_RARE", 0.35)),
    "Legendary": float(os.getenv("CATCH_LEGENDARY", 0.15)),
    "Shiny": float(os.getenv("CATCH_SHINY", 0.10)),
}

DATA_FILE = "notify_data.json"
POKEDEX_FILE = "pokedex.json"
STREAK_FILE = "streaks.json"

# --- Discord bot setup ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- Persistence Helpers ---
def load_json(file, default):
    if os.path.exists(file):
        with open(file, "r") as f:
            return json.load(f)
    return default

def save_json(file, data):
    with open(file, "w") as f:
        json.dump(data, f)

data = load_json(DATA_FILE, {"streamers": [], "youtube_channels": {}})
streamers = data["streamers"]
youtube_channels = data["youtube_channels"]

pokedex = load_json(POKEDEX_FILE, {})
streaks = load_json(STREAK_FILE, {})

# --- Pokémon Data ---
pokemon_by_rarity = {
    "Common": ["Pidgey", "Rattata", "Zubat", "Caterpie", "Magikarp", "Geodude"],
    "Uncommon": ["Pikachu", "Eevee", "Vulpix", "Growlithe", "Jigglypuff", "Machop"],
    "Rare": ["Snorlax", "Dragonite", "Gengar", "Lapras"],
    "Legendary": ["Mewtwo", "Zapdos", "Articuno", "Moltres"]
}

active_pokemon = None
active_rarity = None
active_shiny = False

# --- Role Management ---
async def update_roles():
    """Assign roles for top trainer and shiny master"""
    if not GUILD_ID:
        return
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return

    # Ensure roles exist
    pokemon_role = discord.utils.get(guild.roles, name="Pokémon Master")
    shiny_role = discord.utils.get(guild.roles, name="Shiny Master")

    if not pokemon_role:
        pokemon_role = await guild.create_role(name="Pokémon Master", colour=discord.Colour(POKEMON_MASTER_COLOR))
    if not shiny_role:
        shiny_role = await guild.create_role(name="Shiny Master", colour=discord.Colour(SHINY_MASTER_COLOR))

    # Find top trainer
    if pokedex:
        top_trainer_id, _ = max(pokedex.items(), key=lambda x: len(set(x[1])))
        top_trainer = guild.get_member(int(top_trainer_id))
        if top_trainer:
            for member in guild.members:
                if pokemon_role in member.roles:
                    await member.remove_roles(pokemon_role)
            await top_trainer.add_roles(pokemon_role)

    # Find top shiny master
    shiny_counts = {uid: sum(1 for p in mons if p.startswith("⭐ Shiny")) for uid, mons in pokedex.items()}
    if shiny_counts:
        top_shiny_id = max(shiny_counts, key=shiny_counts.get)
        top_shiny = guild.get_member(int(top_shiny_id))
        if top_shiny:
            for member in guild.members:
                if shiny_role in member.roles:
                    await member.remove_roles(shiny_role)
            await top_shiny.add_roles(shiny_role)

# --- Pokémon Spawn ---
@tasks.loop(minutes=5)
async def spawn_pokemon():
    await bot.wait_until_ready()
    global active_pokemon, active_rarity, active_shiny

    channel = bot.get_channel(POKEMON_CHANNEL_ID)
    if not channel:
        print("⚠️ Pokémon channel not found.")
        return

    rarities = list(rarity_spawn_rates.keys())
    weights = list(rarity_spawn_rates.values())
    active_rarity = random.choices(rarities, weights=weights, k=1)[0]
    active_pokemon = random.choice(pokemon_by_rarity[active_rarity])
    active_shiny = random.randint(1, 500) == 1  # 1/500 shiny chance

    if active_shiny:
        await channel.send(f"✨⭐ A **SHINY {active_pokemon}** appeared!! Rarity: {active_rarity} ⭐✨\nType `!catch {active_pokemon}`!")
    else:
        await channel.send(f"🌟 A wild **{active_rarity} Pokémon** appeared: **{active_pokemon}**! Type `!catch {active_pokemon}`!")

@bot.command()
async def catch(ctx, *, name: str):
    global active_pokemon, active_rarity, active_shiny
    if not active_pokemon:
        await ctx.send("❌ There are no Pokémon right now!")
        return

    user_id = str(ctx.author.id)
    if name.lower() == active_pokemon.lower():
        rarity_key = "Shiny" if active_shiny else active_rarity
        chance = catch_rates.get(rarity_key, 0.5)
        if random.random() < chance:
            if user_id not in pokedex:
                pokedex[user_id] = []
            if user_id not in streaks:
                streaks[user_id] = 0

            caught_name = f"⭐ Shiny {active_pokemon}" if active_shiny else active_pokemon
            if caught_name in pokedex[user_id]:
                await ctx.send(f"⚠️ {ctx.author.mention}, you already caught **{caught_name}**!")
            else:
                pokedex[user_id].append(caught_name)
                streaks[user_id] += 1
                save_json(POKEDEX_FILE, pokedex)
                save_json(STREAK_FILE, streaks)
                await update_roles()

                streak_msg = ""
                if streaks[user_id] == 2:
                    streak_msg = "🔥 is heating up!"
                elif streaks[user_id] == 3:
                    streak_msg = "🔥🔥 is on fire!"
                elif streaks[user_id] >= 5:
                    streak_msg = "🔥🔥🔥 is UNSTOPPABLE!"

                await ctx.send(f"✅ {ctx.author.mention} caught a **{rarity_key} {active_pokemon}**! 🎉 {streak_msg}")
            active_pokemon = None
            active_rarity = None
            active_shiny = False
        else:
            streaks[user_id] = 0
            save_json(STREAK_FILE, streaks)
            await ctx.send(f"🏃💨 {ctx.author.mention} tried to catch **{active_pokemon}**, but it escaped!")
    else:
        streaks[user_id] = 0
        save_json(STREAK_FILE, streaks)
        await ctx.send("❌ Wrong name! The wild Pokémon got away...")

@bot.command()
async def pokedex_cmd(ctx):
    user_id = str(ctx.author.id)
    if user_id not in pokedex or not pokedex[user_id]:
        await ctx.send(f"{ctx.author.mention}, your Pokédex is empty!")
        return

    grouped = {r: [] for r in pokemon_by_rarity.keys()}
    shinies = []
    for p in pokedex[user_id]:
        if p.startswith("⭐ Shiny"):
            shinies.append(p)
        else:
            for rarity, mons in pokemon_by_rarity.items():
                if p in mons:
                    grouped[rarity].append(p)

    msg_lines = [f"📖 {ctx.author.mention}'s Pokédex:"]
    for rarity, mons in grouped.items():
        if mons:
            msg_lines.append(f"**{rarity}:** {', '.join(mons)}")
    if shinies:
        msg_lines.append(f"✨ **Shinies:** {', '.join(shinies)}")
    await ctx.send("\n".join(msg_lines))

@bot.command()
async def toptrainers(ctx):
    if not pokedex:
        await ctx.send("📊 No trainers yet!")
        return

    leaderboard = sorted(pokedex.items(), key=lambda x: len(set(x[1])), reverse=True)
    msg_lines = ["🏆 **Top Trainers** 🏆"]
    for i, (uid, mons) in enumerate(leaderboard[:10], start=1):
        user = await bot.fetch_user(int(uid))
        streak = streaks.get(uid, 0)
        shinies = sum(1 for p in mons if p.startswith("⭐ Shiny"))
        msg_lines.append(f"{i}. **{user.display_name}** — {len(set(mons))} Pokémon, ✨ {shinies} Shinies")
    await ctx.send("\n".join(msg_lines))
    await update_roles()

@bot.command()
async def shinymasters(ctx):
    shiny_counts = {uid: sum(1 for p in mons if p.startswith("⭐ Shiny")) for uid, mons in pokedex.items()}
    if not shiny_counts:
        await ctx.send("✨ No Shinies have been caught yet!")
        return

    leaderboard = sorted(shiny_counts.items(), key=lambda x: x[1], reverse=True)
    msg_lines = ["✨🏆 **Shiny Masters** 🏆✨"]
    for i, (uid, count) in enumerate(leaderboard[:10], start=1):
        user = await bot.fetch_user(int(uid))
        msg_lines.append(f"{i}. **{user.display_name}** — {count} Shiny Pokémon")
    await ctx.send("\n".join(msg_lines))
    await update_roles()

# --- On Ready ---
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    spawn_pokemon.start()

# --- Run bot ---
if DISCORD_TOKEN:
    bot.run(DISCORD_TOKEN)
else:
    print("❌ DISCORD_TOKEN missing!")
