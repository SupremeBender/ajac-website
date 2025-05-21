import os
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from flask import Flask, redirect, url_for, render_template, session, current_app, request
from flask_session import Session
from flask_discord import DiscordOAuth2Session

# Import our custom login_required decorator
from utils.auth import login_required
logger = logging.getLogger(__name__)

def create_app():
    # Create Flask app
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object('config')
    app.config.from_pyfile('secret_config.py')
    
    # Ensure instance directories exist
    os.makedirs(os.path.join(app.instance_path, 'campaigns'), exist_ok=True)
    os.makedirs(os.path.join(app.instance_path, 'missions'), exist_ok=True)
    os.makedirs(os.path.join(app.instance_path, 'logs'), exist_ok=True)
    
    # Set up logging
    configure_logging(app)
    logger.debug("Logger started")
    
    # Set up session
    Session(app)
    logger.debug("Setting up session")
    
    # Set up Discord OAuth
    discord = DiscordOAuth2Session(app)
    app.discord = discord  # Make discord available to blueprints
    logger.debug("Setting up OAuth2 integration")
    
    # Register feature blueprints
    register_blueprints(app)
    logger.debug(f"Registering blueprints")
    
    return app

def configure_logging(app):
    log_file = os.path.join(app.instance_path, "logs", "app.log")
    log_level = app.config.get("LOG_LEVEL", "WARNING").upper()

    file_handler = RotatingFileHandler(
        log_file, maxBytes=1024*1024, backupCount=3
    )
    file_handler.setLevel(getattr(logging, log_level))

    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, log_level))

    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    # Configure the root logger so all modules' logs are captured
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level))
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    # Remove any handlers from the module logger to avoid duplicate logs
    logger.handlers.clear()

def register_blueprints(app):
    """Register all feature blueprints"""
    # Import blueprints
    from features.auth import auth_bp
    from features.signup import signup_bp
    from features.missions import missions_bp
    from features.campaigns import campaigns_bp
    
    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(signup_bp)
    app.register_blueprint(missions_bp)
    app.register_blueprint(campaigns_bp)
    
    # You'll add more blueprints here as you create them

# Create the Flask application
app = create_app()

@app.context_processor
def inject_beta_banner():
    banner_path = os.path.join(current_app.instance_path, 'beta_banner.txt')
    beta_banner = None
    if os.path.isfile(banner_path):
        try:
            with open(banner_path) as f:
                beta_banner = f.read().replace('\n', '<br>')
        except Exception as e:
            beta_banner = "BETA VERSION"
    return dict(beta_banner=beta_banner)

# Root route renders root.html and checks Discord roles for access
@app.route("/")
@login_required
def root():
    """Home page showing available features based on user roles"""
    # User is authenticated at this point thanks to @login_required
    
    try:
        # Get Discord user and roles
        discord = current_app.discord
        user = discord.fetch_user()
        user_id = user.id
        
        # Fetch roles from bot API
        import requests
        try:
            resp = requests.get(f"http://localhost:8000/roles/{user_id}", timeout=2)
            resp.raise_for_status()
            response_data = resp.json()
            user_roles = response_data.get("roles", [])
            
            # Try to get nickname
            nickname = response_data.get("nickname", user.username)
        except Exception as e:
            logger.error(f"Could not fetch roles from bot: {e}")
            user_roles = []
            nickname = user.username
            
        # Get role config
        admin_role = current_app.config.get("ADMIN_ROLE")
        mission_maker_role = current_app.config.get("MISSION_MAKER_ROLE", "")
        red_team_roles = current_app.config.get("RED_TEAM_ROLE", "")
        blue_team_roles = current_app.config.get("BLUE_TEAM_ROLE", "")
        
        # Support multiple roles for blue/red (comma separated)
        red_team_roles = [r.strip() for r in red_team_roles.split(",") if r.strip()]
        blue_team_roles = [r.strip() for r in blue_team_roles.split(",") if r.strip()]
        
        user_role_ids = [role['id'] for role in user_roles]
        
        # Access logic
        can_access_signup = True  # All logged-in users
        can_access_missions = admin_role in user_role_ids or mission_maker_role in user_role_ids
        can_access_campaigns = admin_role in user_role_ids or mission_maker_role in user_role_ids
        
        # Determine if user is admin or mission maker for template
        is_admin = admin_role in user_role_ids
        is_mission_maker = mission_maker_role in user_role_ids
        
        # Store important user info in session for templates
        session['display_name'] = nickname
        session['is_admin'] = is_admin
        session['is_mission_maker'] = is_mission_maker
        
        return render_template(
            "root.html",
            can_access_signup=can_access_signup,
            can_access_missions=can_access_missions,
            can_access_campaigns=can_access_campaigns,
            current_year=datetime.now().year,
            is_authenticated=True,
            is_admin=is_admin,
            is_mission_maker=is_mission_maker,
            display_name=nickname
        )
    except Exception as e:
        logger.error(f"Error in root route: {e}")
        # Handle errors by clearing session and sending to login
        session.clear()
        return redirect(url_for("auth.login"))

# Add a root-level callback route to handle Discord OAuth redirects
@app.route("/callback")
def discord_callback():
    """Handle Discord OAuth callback directly at the root level"""
    logger.debug("Received Discord OAuth callback at root level")
    
    # Check for error parameter from Discord
    if request.args.get('error'):
        error = request.args.get('error')
        error_description = request.args.get('error_description', 'Unknown error')
        logger.error(f"Discord OAuth error: {error} - {error_description}")
        session.clear()
        return redirect(url_for("root"))
    
    try:
        # Process the callback directly rather than redirecting
        discord = current_app.discord
        discord.callback()
        
        if discord.authorized:
            # Successfully authorized
            user = discord.fetch_user()
            session['user_id'] = user.id
            session['username'] = user.username
            session['avatar'] = user.avatar_url
            session['is_authenticated'] = True
            session.modified = True
            
            logger.debug(f"Successfully authenticated user {user.username} ({user.id})")
            
            # Redirect to home page
            return redirect(url_for("root"))
        else:
            logger.error("Discord callback did not result in authorization")
            session.clear()
            return redirect(url_for("auth.login"))
    except Exception as e:
        import traceback
        logger.error(f"Error processing Discord callback: {e}")
        logger.error(traceback.format_exc())
        session.clear()
        return redirect(url_for("auth.login"))

@app.errorhandler(404)
def page_not_found(e):
    """Handle 404 errors"""
    logger.warning(f"404 error: {request.path}")
    # Check if user is logged in
    is_authenticated = 'user_id' in session
    return render_template("404.html", 
                          current_year=datetime.now().year,
                          is_authenticated=is_authenticated), 404

@app.errorhandler(500)
def internal_server_error(e):
    """Handle 500 errors"""
    logger.error(f"500 error: {str(e)}")
    # Check if user is logged in
    is_authenticated = 'user_id' in session
    return render_template("500.html", 
                          current_year=datetime.now().year,
                          is_authenticated=is_authenticated), 500

if __name__ == "__main__":
    app.run(debug=True)