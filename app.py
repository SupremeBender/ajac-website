from datetime import datetime
from flask import Flask, redirect, url_for, render_template
from flask_session import Session
from flask_discord import DiscordOAuth2Session
import logging
from logging.handlers import RotatingFileHandler
import os
import requests

# Start app: create Flask app and load configuration
app = Flask(__name__, instance_relative_config=True)
app.config.from_object('config')  # Loads config.py
app.config.from_pyfile('secret_config.py')  # Loads instance/config.py

# Define log file location and name
log_file = os.path.join(app.instance_path, "logs", "app.log")

# Set log level based on config. WARNING as default
log_level = app.config.get("LOG_LEVEL", "WARNING").upper()

# File handler (rotating): writes logs to a file, rotates when file reaches 1MB, keeps 3 backups
file_handler = RotatingFileHandler(log_file, maxBytes=1024*1024, backupCount=3)
file_handler.setLevel(getattr(logging, log_level))
formatter = logging.formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
file_handler.setFormatter(formatter)

# Console handler: outputs logs to the terminal/console
console_handler = logging.StreamHandler()
console_handler.setLevel(getattr(logging, log_level))
console_handler.setFormatter(formatter)

# Start logger: attaches handlers and sets level
logger = logging.getLogger(__name__)
logger.setLevel(getattr(logging, log_level))
logger.addHandler(file_handler)
logger.addHandler(console_handler)
logger.debug("Logger started")

# Set up server-side sessions
Session(app)
logger.debug(f"Setting up session")
# Set up Discord OAuth2 integration
discord = DiscordOAuth2Session(app)
logger.debug(f"Setting up Oauth2 integration")

@app.route("/")
def index():
    logger.debug(f"Accessed root page")
    return "Hello, world!"

# Route for Discord login
@app.route("/login/")
def login():
    logger.debug("discord session created")
    return discord.create_session()

# Route for Discord OAuth2 callback
@app.route("/callback")
def callback():
    logger.debug("callback redirecting to landing page")
    discord.callback()
    return redirect(url_for("landing"))  

@app.route("/landing")
def landing():
    if not discord.authorized:
        return redirect(url_for("login"))
    
    user = discord.fetch_user()
    user_id = user.id
    
    # Fetch roles from your bot API
    try:
        logger.debug(f"Fetching roles and nickname for user ID {user_id}")
        resp = requests.get(f"http://localhost:8000/roles/{user_id}", timeout=2)
        resp.raise_for_status()
        response_data = resp.json()
        user_roles = response_data.get("roles", [])
        
        # Try to get nickname from bot API if available
        nickname = response_data.get("nickname", user.username)
        logger.debug(f"Got nickname from bot API: '{nickname}'")
    except Exception as e:
        logger.error(f"Could not fetch roles from bot: {e}")
        user_roles = []
        nickname = user.username
        logger.debug(f"Using Discord username as fallback: '{nickname}'")
        
    # Process nickname: remove clan tags and capitalize
    # Remove text within square brackets or parentheses
    import re
    clean_name = re.sub(r'\[.*?\]|\(.*?\)', '', nickname).strip()
    logger.debug(f"After removing clan tags: '{clean_name}'")
    
    # Make the whole name uppercase
    display_name = clean_name.upper()
    logger.debug(f"Final display name: '{display_name}'")
    
    # Check for admin role
    admin_role = app.config.get("ADMIN_ROLE")
    is_admin = any(role['id'] == admin_role for role in user_roles)
    
    # You can add more role checks as needed
    mission_maker_role = app.config.get("MISSION_MAKER_ROLE", "")
    red_team_role = app.config.get("RED_TEAM_ROLE", "")
    blue_team_role = app.config.get("BLUE_TEAM_ROLE", "")
    is_mission_maker = any(role['id'] == mission_maker_role for role in user_roles)
    has_red_role = any(role['id'] == red_team_role for role in user_roles)
    has_blue_role = any(role['id'] == blue_team_role for role in user_roles)
    
    return render_template(
        "landing.html",
        user=user,
        display_name=display_name,  # This is important!
        user_roles=user_roles,
        is_admin=is_admin,
        is_mission_maker=is_mission_maker,
        admin_role=admin_role,
        red_team_role=red_team_role,
        blue_team_role=blue_team_role,
        has_red_role=has_red_role,
        has_blue_role=has_blue_role,
        current_year=datetime.now().year
    )

if __name__ == "__main__":
    app.run(debug=True)