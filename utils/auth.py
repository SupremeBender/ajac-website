from functools import wraps
from flask import session, redirect, url_for, request, flash
import logging

logger = logging.getLogger(__name__)

def login_required(f):
    """
    Custom decorator to require login for routes.
    If user is not logged in, redirects to login page.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        logger.debug(f"Checking authentication for {request.path}")
        logger.debug(f"Session data: user_id={session.get('user_id')}, is_authenticated={session.get('is_authenticated')}")
        
        # Check if user is authenticated
        is_authenticated = False
        
        # First check if we have a user_id
        if session.get('user_id'):
            is_authenticated = True
        # Also check for is_authenticated flag as backup
        elif session.get('is_authenticated') is True:
            is_authenticated = True
        
        # If not authenticated, redirect to login
        if not is_authenticated:
            logger.debug(f"Unauthorized access to {request.path}, redirecting to login")
            # Clear any invalid session data
            session.clear()
            # Redirect to login
            return redirect(url_for('auth.login'))
            
        logger.debug(f"User {session.get('username', 'unknown')} is authenticated, proceeding to {request.path}")
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """
    Custom decorator to require admin privileges for routes.
    If user is not admin, redirects to login or shows unauthorized message.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        logger.debug(f"Checking admin for {request.path}")
        is_admin = session.get('is_admin', False)
        if not is_admin:
            logger.warning(f"Unauthorized admin access attempt to {request.path}")
            flash("You do not have permission to access this page.", "danger")
            return redirect(url_for('root'))
        logger.debug(f"User {session.get('username', 'unknown')} is admin, proceeding to {request.path}")
        return f(*args, **kwargs)
    return decorated_function
