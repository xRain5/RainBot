import os
import discord
from discord.ext import commands, tasks
import requests
import aiohttp
import asyncio
import random

# --- ENV VARS ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_SECRET = os.getenv("TWITCH_SECRET")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
NOTIFY_CHANNEL_ID = int(os.getenv("NOTIFY_CHANNEL_ID", 0))  # Discord channel for notifications

# --- Discord bot setup ---
intents = discord.Intents.default()
intents.message_content = True
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
