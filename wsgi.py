import sys
import os
import logging

# Dynamically determine the app directory based on this file's location
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

try:
    from app import app as application
except Exception as e:
    # Log import errors to Apache error log
    import traceback
    with open('/tmp/wsgi_error.log', 'w') as f:
        f.write(traceback.format_exc())
    raise