from flask import Flask, request, jsonify
from werkzeug.middleware.proxy_fix import ProxyFix

# Create a Flask application instance
app = Flask(__name__)

# Apply ProxyFix middleware to handle reverse proxy headers
app.wsgi_app = ProxyFix(app.wsgi_app)

@app.route('/')
def index():
    """
    Index route that returns a welcome message.
    This route is accessed when the root URL is visited.
    """
    app.logger.debug("Index route accessed")  # Debug log for tracking route access
    return jsonify({"message": "Welcome to the Flask app!"})  # Return a JSON response with a welcome message

@app.route('/data', methods=['POST'])
def data():
    """
    Data route that handles POST requests.
    Expects JSON payload and returns it in the response.
    """
    app.logger.debug("Data route accessed with payload: %s", request.json)  # Debug log for tracking payload data
    return jsonify({"received": request.json})  # Return a JSON response with the received payload

# Add a basic Content Security Policy (CSP) header to all responses for improved security
@app.after_request
def add_csp_header(response):
    # TEMP: Allow 'unsafe-inline' for script-src for debugging JS issues
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "  # Allow inline scripts for now
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "object-src 'none'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    return response

if __name__ == '__main__':
    # Run the Flask application in debug mode for development purposes
    app.run(debug=True)