import discord
import asyncio
from fastapi import FastAPI, HTTPException
import uvicorn
import sys
import os
import logging
from logging.handlers import RotatingFileHandler
# Dynamically determine the instance directory based on the script's location
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
sys.path.insert(0, INSTANCE_DIR)
from instance import secret_config as config

# Set up logging
log_dir = os.path.join(INSTANCE_DIR, "logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "bot.log")

# Set log level based on config. WARNING as default
log_level = config.LOG_LEVEL if hasattr(config, 'LOG_LEVEL') else "WARNING"
log_level = getattr(logging, log_level.upper())

# Set up logger
logger = logging.getLogger("discord_bot")
logger.setLevel(log_level)

# File handler (rotating): writes logs to a file, rotates when file reaches 1MB, keeps 3 backups
file_handler = RotatingFileHandler(log_file, maxBytes=1024*1024, backupCount=3)
file_handler.setLevel(log_level)
formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
file_handler.setFormatter(formatter)

# Console handler: outputs logs to the terminal/console
console_handler = logging.StreamHandler()
console_handler.setLevel(log_level)
console_handler.setFormatter(formatter)

# Add handlers to logger
logger.addHandler(file_handler)
logger.addHandler(console_handler)
logger.debug("Logger started")

logger.debug(f"Config file loaded from: {config.__file__}")
logger.debug(f"Config attributes: {dir(config)}")

DISCORD_TOKEN = config.DISCORD_BOT_TOKEN
GUILD_ID = int(config.DISCORD_GUILD_ID)

intents = discord.Intents.default()
intents.members = True  # Needed to fetch members

bot = discord.Client(intents=intents)
api = FastAPI()

@bot.event
async def on_ready():
    logger.info(f"Bot is ready. Guilds: {[g.id for g in bot.guilds]}")
    
    # Log additional information about guilds
    for guild in bot.guilds:
        if guild.id == GUILD_ID:
            logger.info(f"Connected to target guild: {guild.name} ({guild.id}) with {len(guild.members)} members")
        else:
            logger.info(f"Connected to guild: {guild.name} ({guild.id})")

@api.get("/roles/{user_id}")
async def get_roles(user_id: int):
    try:
        guild = bot.get_guild(GUILD_ID)
        if not guild:
            logger.error(f"Guild not found with ID: {GUILD_ID}")
            raise HTTPException(status_code=404, detail="Guild not found")
            
        member = guild.get_member(user_id)
        if not member:
            logger.warning(f"Member not found with ID: {user_id}")
            raise HTTPException(status_code=404, detail="Member not found")
            
        # Get member's nickname, falling back to username if no nickname exists
        nickname = member.nick if member.nick else member.name
        logger.info(f"Found member: {member.name}, nickname: {nickname}")
        
        return {
            "roles": [{"id": str(role.id), "name": role.name} for role in member.roles],
            "nickname": nickname
        }
    except Exception as e:
        logger.error(f"Error in get_roles: {type(e).__name__}: {e}")
        # Return a minimal response so the main app doesn't fail completely
        return {
            "roles": [],
            "nickname": f"User {user_id}"
        }

@api.get("/health")
async def health_check():
    try:
        guild = bot.get_guild(GUILD_ID)
        return {
            "status": "ok",
            "bot_ready": bot.is_ready(),
            "guild_found": guild is not None,
            "guild_name": guild.name if guild else None,
            "member_count": len(guild.members) if guild else 0
        }
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return {"status": "error", "message": str(e)}

async def start_bot():
    await bot.start(DISCORD_TOKEN)

async def main():
    bot_task = asyncio.create_task(start_bot())
    config_uvicorn = uvicorn.Config(api, host="0.0.0.0", port=8000, loop="asyncio")
    server = uvicorn.Server(config_uvicorn)
    api_task = asyncio.create_task(server.serve())
    await asyncio.gather(bot_task, api_task)

if __name__ == "__main__":
    asyncio.run(main())