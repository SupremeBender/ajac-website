from flask import Blueprint

campaigns_bp = Blueprint('campaigns', __name__,
    template_folder='templates',
    static_folder='static',
    url_prefix='/campaigns')

from . import routes
