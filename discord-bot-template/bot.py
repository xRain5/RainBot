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
NOTIFY_CHANNEL_ID = int(os.getenv("NOTIFY_CHANNEL_ID", 0))

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
    global TWITCH_ACCESS_TOKEN
    url = "https://id.twitch.tv/oauth2/token"
    params = {"client_id": TWITCH_CLIENT_ID, "client_secret": TWITCH_SECRET, "grant_type": "client_credentials"}
    try:
        resp = requests.post(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        TWITCH_ACCESS_TOKEN = data["access_token"]
        return TWITCH_ACCESS_TOKEN
    except Exception as e:
        print("❌ Failed to fetch Twitch token:", e)
        return None

def twitch_headers():
    if TWITCH_ACCESS_TOKEN is None:
        get_twitch_token()
    return {"Client-ID": TWITCH_CLIENT_ID, "Authorization": f"Bearer {TWITCH_ACCESS_TOKEN}"}

# --- Persistence ---
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {"streamers": [], "youtube_channels": {}, "custom_commands": {}, "balances": {}, "shop_items": {}, "inventories": {}}

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump(
            {
                "streamers": streamers,
                "youtube_channels": youtube_channels,
                "custom_commands": custom_commands,
                "balances": balances,
                "shop_items": shop_items,
                "inventories": inventories,
            },
            f,
        )

data = load_data()
streamers = data.get("streamers", [])
youtube_channels = data.get("youtube_channels", {})
custom_commands = data.get("custom_commands", {})
balances = data.get("balances", {})
shop_items = data.get("shop_items", {
    "meme": {"price": 5, "desc": "Get a random funny meme", "consumable": True},
    "shoutout": {"price": 10, "desc": "The bot gives you a shoutout!", "consumable": True},
    "rolecolor": {"price": 20, "desc": "Change your role color (random color)", "consumable": True},
})
inventories = data.get("inventories", {})

# --- Economy Helpers ---
def add_coins(user_id: str, amount: int):
    balances[user_id] = balances.get(user_id, 0) + amount
    save_data()

def spend_coins(user_id: str, amount: int):
    if balances.get(user_id, 0) >= amount:
        balances[user_id] -= amount
        save_data()
        return True
    return False

def get_balance(user_id: str):
    return balances.get(user_id, 0)

def add_to_inventory(user_id: str, item: str):
    if user_id not in inventories:
        inventories[user_id] = []
    inventories[user_id].append(item)
    save_data()

def remove_from_inventory(user_id: str, item: str):
    if user_id in inventories and item in inventories[user_id]:
        inventories[user_id].remove(item)
        save_data()

def get_inventory(user_id: str):
    return inventories.get(user_id, [])

# --- Store last notified states ---
last_twitch_status = {}
last_youtube_video = {}

# --- Events ---
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    if not twitch_notifier.is_running():
        twitch_notifier.start()
    if not youtube_notifier.is_running():
        youtube_notifier.start()

# --- Utility Commands ---
@bot.command()
async def ping(ctx):
    await ctx.send("🏓 Pong!")

@bot.command()
async def roll(ctx, sides: int = 6):
    result = random.randint(1, sides)
    add_coins(str(ctx.author.id), 1)
    await ctx.send(f"🎲 You rolled a **{result}** on a {sides}-sided die! (+1 coin)")

@bot.command()
async def debug(ctx):
    twitch_list = "\n".join(f"- {s}" for s in streamers) if streamers else "None"
    yt_list = "\n".join(f"- {n}: {cid}" for n, cid in youtube_channels.items()) if youtube_channels else "None"
    msg = f"**Debug Info:**\nNotify Channel ID: {NOTIFY_CHANNEL_ID}\n\n🎥 Twitch:\n{twitch_list}\n\n📺 YouTube:\n{yt_list}"
    await ctx.send(msg)

# --- Fun Commands ---
@bot.command()
async def joke(ctx):
    jokes = [
        "Why don’t skeletons fight each other? They don’t have the guts.",
        "I told my computer I needed a break, and it froze.",
        "Why did the scarecrow win an award? Because he was outstanding in his field!",
    ]
    await ctx.send(f"😂 {random.choice(jokes)}")

@bot.command()
async def eightball(ctx, *, question: str):
    responses = ["Yes ✅", "No ❌", "Maybe 🤔", "Definitely!", "I wouldn't count on it..."]
    await ctx.send(f"🎱 {random.choice(responses)}")

@bot.command()
async def coinflip(ctx):
    result = random.choice(["Heads", "Tails"])
    add_coins(str(ctx.author.id), 1)
    await ctx.send(f"🪙 {result}! (+1 coin)")

@bot.command()
async def rps(ctx, choice: str):
    options = ["rock", "paper", "scissors"]
    bot_choice = random.choice(options)
    choice = choice.lower()
    if choice not in options:
        await ctx.send("❌ Please choose rock, paper, or scissors.")
        return
    if choice == bot_choice:
        result = "It's a tie!"
    elif (choice == "rock" and bot_choice == "scissors") or \
         (choice == "paper" and bot_choice == "rock") or \
         (choice == "scissors" and bot_choice == "paper"):
        result = "You win! 🎉 (+2 coins)"
        add_coins(str(ctx.author.id), 2)
    else:
        result = "I win! 😎"
    await ctx.send(f"✊ {choice} vs 🤖 {bot_choice} → {result}")

@bot.command()
async def meme(ctx):
    memes = [
        "https://i.imgur.com/fY6VZ3G.jpeg",
        "https://i.imgur.com/w3duR07.png",
        "https://i.imgur.com/4M7IWwP.png",
    ]
    await ctx.send(random.choice(memes))

# --- Economy Commands ---
@bot.command()
async def balance(ctx):
    coins = get_balance(str(ctx.author.id))
    await ctx.send(f"💰 {ctx.author.display_name}, you have **{coins} coins**.")

@bot.command()
async def leaderboard(ctx):
    if not balances:
        await ctx.send("🏆 No leaderboard yet!")
        return
    sorted_balances = sorted(balances.items(), key=lambda x: x[1], reverse=True)[:10]
    leaderboard_text = "\n".join(
        f"{i+1}. <@{uid}> — {coins} coins" for i, (uid, coins) in enumerate(sorted_balances)
    )
    await ctx.send(f"🏆 **Leaderboard**:\n{leaderboard_text}")

@bot.command()
async def shop(ctx):
    if not shop_items:
        await ctx.send("🛒 The shop is empty! Ask an admin to add items.")
        return
    items = "\n".join([
        f"**{name}** ({info['price']} coins) → {info['desc']} {'(Consumable)' if info.get('consumable') else ''}"
        for name, info in shop_items.items()
    ])
    await ctx.send(f"🛒 **Shop Items:**\n{items}")

@bot.command()
async def buy(ctx, item: str):
    item = item.lower()
    if item not in shop_items:
        await ctx.send("❌ Item not found! Use `!shop` to see available items.")
        return

    price = shop_items[item]["price"]
    if not spend_coins(str(ctx.author.id), price):
        await ctx.send("💸 You don’t have enough coins!")
        return

    add_to_inventory(str(ctx.author.id), item)
    await ctx.send(f"✅ You bought `{item}`! Use it later with `!use {item}` if it’s consumable.")

@bot.command()
async def myitems(ctx):
    items = get_inventory(str(ctx.author.id))
    if not items:
        await ctx.send("📦 You don’t own any items yet! Buy some with `!shop`.")
        return
    item_counts = {}
    for item in items:
        item_counts[item] = item_counts.get(item, 0) + 1
    item_list = "\n".join([f"**{item}** × {count}" for item, count in item_counts.items()])
    await ctx.send(f"📦 **Your Items:**\n{item_list}")

@bot.command()
async def use(ctx, item: str):
    user_id = str(ctx.author.id)
    item = item.lower()
    if item not in get_inventory(user_id):
        await ctx.send("❌ You don’t own this item!")
        return

    if item not in shop_items:
        await ctx.send("⚠️ This item no longer exists in the shop.")
        return

    if not shop_items[item].get("consumable", False):
        await ctx.send("♻️ This item isn’t consumable, you keep it forever!")
        return

    # Apply consumable effect
    if item == "meme":
        await meme(ctx)
    elif item == "shoutout":
        await ctx.send(f"📢 BIG SHOUTOUT to {ctx.author.mention}! 🎉")
    elif item == "rolecolor":
        if ctx.guild:
            role = discord.utils.get(ctx.guild.roles, name="CustomColor")
            if not role:
                role = await ctx.guild.create_role(name="CustomColor")
            await ctx.author.add_roles(role)
            color = discord.Colour.random()
            await role.edit(colour=color)
            await ctx.send(f"🌈 {ctx.author.mention}, your role color has been changed!")

    remove_from_inventory(user_id, item)
    await ctx.send(f"✅ You used `{item}`!")

# --- Shop Admin Commands ---
@bot.command()
@commands.has_permissions(administrator=True)
async def additem(ctx, name: str, price: int, consumable: str, *, desc: str):
    """Add an item to the shop. Example: !additem potion 5 true Heals you when used."""
    consumable_flag = consumable.lower() in ["true", "yes", "1"]
    shop_items[name.lower()] = {"price": price, "desc": desc, "consumable": consumable_flag}
    save_data()
    await ctx.send(f"✅ Added `{name}` to the shop for {price} coins. Consumable: {consumable_flag}")

@bot.command()
@commands.has_permissions(administrator=True)
async def removeitem(ctx, name: str):
    if name.lower() in shop_items:
        del shop_items[name.lower()]
        save_data()
        await ctx.send(f"🗑️ Removed `{name}` from the shop.")
    else:
        await ctx.send("❌ Item not found in shop.")

# --- Custom Commands ---
@bot.command()
@commands.has_permissions(administrator=True)
async def addcommand(ctx, name: str, *, response: str):
    custom_commands[name] = response
    save_data()
    await ctx.send(f"✅ Custom command `!{name}` added!")

@bot.command()
@commands.has_permissions(administrator=True)
async def removecommand(ctx, name: str):
    if name in custom_commands:
        del custom_commands[name]
        save_data()
        await ctx.send(f"🗑️ Removed custom command `!{name}`")
    else:
        await ctx.send(f"⚠️ Command `{name}` does not exist.")

@bot.listen("on_message")
async def custom_command_listener(message):
    if message.author == bot.user:
        return
    if not message.content.startswith("!"):
        return
    cmd = message.content[1:].split(" ")[0]
    if cmd in custom_commands:
        await message.channel.send(custom_commands[cmd])

# --- Categorized Help Command ---
@bot.command(name="commands")
async def list_commands(ctx):
    """Show categorized list of available commands"""
    categories = {
        "Utility": ["ping", "roll", "debug"],
        "Fun": ["joke", "eightball", "coinflip", "rps", "meme"],
        "Economy": ["balance", "leaderboard"],
        "Shop": ["shop", "buy", "myitems", "use"],
        "Admin (Shop)": ["additem", "removeitem"],
        "Admin (Custom Commands)": ["addcommand", "removecommand"],
    }

    embed = discord.Embed(title="📖 Available Commands", color=discord.Color.blue())
    for category, cmds in categories.items():
        embed.add_field(name=category, value=", ".join([f"`!{c}`" for c in cmds]), inline=False)

    if custom_commands:
        embed.add_field(
            name="Custom Commands",
            value=", ".join([f"`!{c}`" for c in custom_commands.keys()]),
            inline=False,
        )

    await ctx.send(embed=embed)

# --- Twitch/YouTube Notifiers ---
@tasks.loop(minutes=2)
async def twitch_notifier():
    await bot.wait_until_ready()
    channel = bot.get_channel(NOTIFY_CHANNEL_ID)
    if not channel:
        return
    for username in streamers:
        try:
            url = "https://api.twitch.tv/helix/streams"
            resp = requests.get(url, headers=twitch_headers(), params={"user_login": username})
            resp.raise_for_status()
            data = resp.json()
            is_live = bool(data.get("data"))
            was_live = last_twitch_status.get(username, False)
            if is_live and not was_live:
                await channel.send(f"🎥 **{username} is LIVE on Twitch!** 👉 https://twitch.tv/{username}")
            last_twitch_status[username] = is_live
        except Exception as e:
            print(f"❌ Error checking Twitch streamer {username}:", e)

@tasks.loop(minutes=5)
async def youtube_notifier():
    await bot.wait_until_ready()
    channel = bot.get_channel(NOTIFY_CHANNEL_ID)
    if not channel:
        return
    for name, channel_id in youtube_channels.items():
        try:
            url = f"https://www.googleapis.com/youtube/v3/search?key={YOUTUBE_API_KEY}&channelId={channel_id}&part=snippet,id&order=date&maxResults=1"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json()
            if "items" in data and len(data["items"]) > 0:
                video = data["items"][0]
                video_id = video["id"].get("videoId")
                title = video["snippet"]["title"]
                last_id = last_youtube_video.get(channel_id)
                if video_id and video_id != last_id:
                    await channel.send(f"📺 **{name} uploaded a new video!** 🎬 {title}\n👉 https://youtu.be/{video_id}")
                    last_youtube_video[channel_id] = video_id
        except Exception as e:
            print(f"❌ Error checking YouTube channel {name}:", e)

# --- Run bot ---
bot.run(DISCORD_TOKEN)
