# Discord Bot Template 🤖

This is a ready-to-use Discord bot template you can deploy on **Railway**.

## 🚀 Features
- Moderation (extendable)
- Fun commands (example: roll a dice)
- YouTube/Twitch notification ready
- Uses `.env` for secrets

## 📂 Repo Structure
```
discord-bot/
│── bot.py            # Main bot code
│── requirements.txt  # Python dependencies
│── Procfile          # Start command for Railway
│── .gitignore        # Ignore secrets and cache
│── README.md         # Project instructions
```

## 🔑 Setup

1. Create a `.env` file:
```
DISCORD_TOKEN=your-bot-token-here
```

2. Run locally:
```
python bot.py
```

3. Deploy to Railway:
- Connect this repo
- Add environment variable `DISCORD_TOKEN` in Railway dashboard
- Deploy 🚀
