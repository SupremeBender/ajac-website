import sys
import os

# Ensure the app directory is in the path
sys.path.insert(0, '/var/www/beta.ajac.no')

# Optionally set environment variables
os.environ['FLASK_ENV'] = 'production'

try:
    from app import app as application
except Exception as e:
    # Log import errors to Apache error log
    import traceback
    with open('/tmp/wsgi_error.log', 'w') as f:
        f.write(traceback.format_exc())
    raise