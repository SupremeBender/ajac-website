from flask import Blueprint

# Create the blueprint
auth_bp = Blueprint('auth', __name__, 
                   template_folder='templates',
                   static_folder='static',
                   url_prefix='/auth')

# Import routes to register them with the blueprint
from . import routes