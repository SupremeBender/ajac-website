from flask import Blueprint

# Create the blueprint
missions_bp = Blueprint('missions', __name__, 
                      template_folder='templates',
                      static_folder='static',
                      url_prefix='/missions')

# Import routes to register them with the blueprint
from . import routes