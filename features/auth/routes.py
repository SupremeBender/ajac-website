from flask import redirect, url_for, current_app, session
from . import auth_bp
import logging

logger = logging.getLogger(__name__)

@auth_bp.route("/login/")
def login():
    """Handle login requests by creating a Discord OAuth session"""
    # If user is already logged in, redirect to home page
    if session.get('user_id'):
        logger.debug(f"User {session.get('username')} already logged in, redirecting to home")
        return redirect(url_for('root'))
        
    # Otherwise, create a new Discord OAuth session
    logger.debug("Creating new Discord OAuth session")
    discord = current_app.discord
    return discord.create_session()

@auth_bp.route("/callback")
def callback():
    """Process OAuth callback from Discord"""
    logger.debug("Auth blueprint callback processing Discord OAuth response")
    logger.debug(f"Session before callback: {session}")
    
    try:
        # Get Discord OAuth instance
        discord = current_app.discord
        
        # Process callback and store in session
        discord.callback()
        logger.debug("Discord callback processed")
        
        # Make sure we're authenticated
        if not discord.authorized:
            logger.error("Discord callback did not result in authorization")
            return redirect(url_for("auth.login"))
            
        # Set the user data in session
        try:
            user = discord.fetch_user()
            logger.debug(f"Fetched user: {user.username} ({user.id})")
            
            # Store essential data in session
            session['user_id'] = user.id
            session['username'] = user.username
            session['avatar'] = user.avatar_url
            session['is_authenticated'] = True
            session.modified = True  # Mark session as modified to ensure it's saved
            
            logger.debug(f"Session after user data storage: {session}")
        except Exception as fetch_error:
            logger.error(f"Error fetching user data: {fetch_error}")
            # Continue with redirect even if we couldn't fetch all user data
        
        logger.debug("Redirecting to root after successful login")
        # Redirect to the home page (root)
        return redirect(url_for("root"))
    except Exception as e:
        import traceback
        logger.error(f"Error in Discord callback: {e}")
        logger.error(traceback.format_exc())
        # Clear any partial session data that might be causing issues
        session.clear()
        # Redirect to login
        return redirect(url_for("auth.login"))

@auth_bp.route("/logout/")
def logout():
    """Handle logout requests"""
    logger.debug("User logged out")
    discord = current_app.discord
    discord.revoke()
    session.clear()
    return redirect(url_for("root"))