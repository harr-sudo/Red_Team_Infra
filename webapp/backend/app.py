#!/usr/bin/env python3
"""
Red Team Infrastructure Web Application
Local-only web interface for managing infrastructure deployment
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Frontend path
frontend_path = Path(__file__).parent.parent / 'frontend'

from flask import Flask, render_template, jsonify, request, send_from_directory
from flask_cors import CORS
from webapp.backend.routes import config, deploy, aws_check, health, goad, architecture, tools, profiles, costs, setup_check, beacon, terminal
from webapp.backend.middleware import identity

# Initialize Flask app
app = Flask(__name__, 
            static_folder=str(frontend_path),
            static_url_path='',
            template_folder=str(frontend_path))
CORS(app)  # Enable CORS for local development

# Configure file upload limits
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max file size

# Register blueprints
app.register_blueprint(config.bp, url_prefix='/api/config')
app.register_blueprint(deploy.bp, url_prefix='/api/deploy')
app.register_blueprint(aws_check.bp, url_prefix='/api/aws')
app.register_blueprint(health.bp, url_prefix='/api/health')
app.register_blueprint(goad.bp)  # GOAD routes at /api/goad
app.register_blueprint(architecture.bp)  # Architecture docs at /api/architecture
app.register_blueprint(tools.bp, url_prefix='/api/tools')
app.register_blueprint(profiles.bp, url_prefix='/api/profiles')
app.register_blueprint(costs.bp, url_prefix='/api/costs')
app.register_blueprint(setup_check.bp, url_prefix='/api/setup-check')
app.register_blueprint(beacon.bp, url_prefix='/api/beacon')
app.register_blueprint(terminal.bp)
app.register_blueprint(identity.bp)

# Initialize WebSocket support for terminal
terminal.init_sock(app)

# Serve frontend
@app.route('/')
def index():
    """Serve main application page"""
    return render_template('index.html')

@app.route('/css/<path:filename>')
def serve_css(filename):
    """Serve CSS files"""
    return send_from_directory(str(frontend_path / 'css'), filename)

@app.route('/js/<path:filename>')
def serve_js(filename):
    """Serve JavaScript files"""
    response = send_from_directory(str(frontend_path / 'js'), filename)
    # Disable caching for development
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/assets/<path:filename>')
def serve_assets(filename):
    """Serve asset files"""
    return send_from_directory(str(frontend_path / 'assets'), filename)

@app.route('/api/')
def api_info():
    """API information endpoint"""
    return jsonify({
        'name': 'Red Team Infrastructure API',
        'version': '1.0.0',
        'endpoints': {
            'config': '/api/config',
            'deploy': '/api/deploy',
            'aws': '/api/aws',
            'goad': '/api/goad',
            'costs': '/api/costs'
        }
    })

if __name__ == '__main__':
    # Run on localhost only for security
    print("=" * 60)
    print("Red Team Infrastructure Web Application")
    print("=" * 60)
    print("Access the application at: http://127.0.0.1:5000")
    print("Press Ctrl+C to stop the server")
    print("=" * 60)
    
    app.run(
        host='127.0.0.1',  # Localhost only
        port=5000,
        debug=False
    )

