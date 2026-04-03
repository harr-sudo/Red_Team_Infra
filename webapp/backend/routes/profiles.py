from flask import Blueprint, jsonify, request
from pathlib import Path

bp = Blueprint('profiles', __name__)

# Profiles directory
project_root = Path(__file__).parent.parent.parent.parent
profiles_dir = project_root / "profiles"

VALID_CATEGORIES = {'Normal', 'APT', 'Crimeware'}


@bp.route('/', methods=['GET'])
def list_profiles():
    """List all available Malleable C2 profiles grouped by category"""
    categories = {}

    for category in sorted(VALID_CATEGORIES):
        category_dir = profiles_dir / category
        if category_dir.is_dir():
            profiles = sorted([
                f.name for f in category_dir.iterdir()
                if f.is_file() and f.suffix == '.profile'
            ])
            if profiles:
                categories[category] = profiles

    return jsonify({'success': True, 'categories': categories})


@bp.route('/<category>/<name>', methods=['GET'])
def get_profile(category, name):
    """Get the content of a specific Malleable C2 profile"""
    if category not in VALID_CATEGORIES:
        return jsonify({'success': False, 'error': f'Invalid category: {category}'}), 400

    if not name.endswith('.profile'):
        name += '.profile'

    profile_path = profiles_dir / category / name

    # Prevent path traversal
    try:
        profile_path = profile_path.resolve()
        if not str(profile_path).startswith(str(profiles_dir.resolve())):
            return jsonify({'success': False, 'error': 'Invalid path'}), 400
    except (ValueError, OSError):
        return jsonify({'success': False, 'error': 'Invalid path'}), 400

    if not profile_path.is_file():
        return jsonify({'success': False, 'error': f'Profile not found: {category}/{name}'}), 404

    content = profile_path.read_text(encoding='utf-8', errors='replace')

    return jsonify({
        'success': True,
        'name': name,
        'category': category,
        'content': content
    })
