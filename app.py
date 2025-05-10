from flask import Flask, render_template, session, redirect, url_for, request
import os
import logging
from logging.handlers import RotatingFileHandler

def create_app():
    """Create and configure the Flask application"""
    app = Flask(__name__, instance_relative_config=True)
    
    # Load default configuration
    app.config.from_mapping(
        SECRET_KEY=os.environ.get('SECRET_KEY', 'dev_key_for_testing'),
    )
    
    # Load instance config if it exists
    app.config.from_pyfile('config.py', silent=True)
    
    # Ensure instance folder exists
    try:
        os.makedirs(app.instance_path, exist_ok=True)
        os.makedirs(os.path.join(app.instance_path, 'logs'), exist_ok=True)
    except OSError:
        pass
    
    # Set up logging
    log_level = app.config.get('LOG_LEVEL', 'INFO')
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    
    file_handler = RotatingFileHandler(
        os.path.join(app.instance_path, 'logs', 'app.log'),
        maxBytes=1024*1024*5,
        backupCount=5
    )
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    
    app.logger.addHandler(file_handler)
    app.logger.setLevel(numeric_level)
    app.logger.info('Application startup')
    
    # Register blueprints
    from auth.routes import auth_bp
    app.register_blueprint(auth_bp)
    
    # Root route
    @app.route('/')
    def index():
        if not session.get('discord_id'):
            return redirect(url_for('auth.login'))
        
        team = session.get('team', 'blue')
        return render_template('index.html', team=team)
    
    return app

# Create app instance for direct running
app = create_app()

if __name__ == '__main__':
    app.run(debug=True)