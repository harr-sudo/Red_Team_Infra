"""
Architecture documentation routes
Serves markdown files for architecture diagrams
"""

from flask import Blueprint, jsonify, send_file
from pathlib import Path
import os

bp = Blueprint('architecture', __name__, url_prefix='/api/architecture')

# Get project root
project_root = Path(__file__).parent.parent.parent.parent

@bp.route('/docs/<path:filename>')
def get_architecture_doc(filename):
    """
    Serve architecture documentation markdown files
    """
    try:
        # Construct full path to documentation file
        docs_path = project_root / 'docs' / 'architectures' / filename
        
        # Security check - ensure file is within docs/architectures
        docs_path = docs_path.resolve()
        architectures_dir = (project_root / 'docs' / 'architectures').resolve()
        
        if not str(docs_path).startswith(str(architectures_dir)):
            return jsonify({'error': 'Access denied'}), 403
        
        # Check if file exists
        if not docs_path.exists():
            return jsonify({'error': f'Documentation file not found: {filename}'}), 404
        
        # Read and return file content
        with open(docs_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        return jsonify({
            'status': 'success',
            'filename': filename,
            'content': content
        })
    
    except Exception as e:
        return jsonify({
            'error': f'Error reading documentation: {str(e)}'
        }), 500

@bp.route('/diagram/<path:filename>')
def get_diagram(filename):
    """
    Serve architecture diagram images
    """
    try:
        # Construct full path to diagram file
        diagram_path = project_root / 'generated-diagrams' / filename
        
        # Security check
        diagram_path = diagram_path.resolve()
        diagrams_dir = (project_root / 'generated-diagrams').resolve()
        
        if not str(diagram_path).startswith(str(diagrams_dir)):
            return jsonify({'error': 'Access denied'}), 403
        
        # Check if file exists
        if not diagram_path.exists():
            return jsonify({'error': f'Diagram not found: {filename}'}), 404
        
        # Return image file
        return send_file(diagram_path, mimetype='image/png')
    
    except Exception as e:
        return jsonify({
            'error': f'Error loading diagram: {str(e)}'
        }), 500

@bp.route('/list')
def list_architectures():
    """
    List all available architecture documentation files
    """
    try:
        architectures_dir = project_root / 'docs' / 'architectures'
        diagrams_dir = project_root / 'generated-diagrams'
        
        # Get all markdown files
        docs = []
        if architectures_dir.exists():
            docs = [f.name for f in architectures_dir.glob('*.md')]
        
        # Get all diagram files
        diagrams = []
        if diagrams_dir.exists():
            diagrams = [f.name for f in diagrams_dir.glob('*.png')]
        
        return jsonify({
            'status': 'success',
            'documentation': docs,
            'diagrams': diagrams
        })
    
    except Exception as e:
        return jsonify({
            'error': f'Error listing files: {str(e)}'
        }), 500
