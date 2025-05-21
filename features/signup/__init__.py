from flask import Blueprint

# Create the blueprint
signup_bp = Blueprint('signup', __name__, 
                     template_folder='templates',
                     static_folder='static',
                     url_prefix='/signup')

# Import routes to register them with the blueprint
from . import routes