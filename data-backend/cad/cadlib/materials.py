"""
Material library for CAD visualization.
Apply by name in Python scripts: body.set_material(name="walnut")
"""

MATERIAL_LIBRARY = {
    # Woods
    "pine": {"color": "#e8d5a3", "specular": "#222222", "shininess": 15},
    "cherry": {"color": "#6b4423", "specular": "#331100", "shininess": 25},
    "walnut": {"color": "#3d2817", "specular": "#1a0a00", "shininess": 20},
    "oak": {"color": "#c4a574", "specular": "#332211", "shininess": 18},
    "maple": {"color": "#e8dcc4", "specular": "#222222", "shininess": 22},
    "birch": {"color": "#f0e6d3", "specular": "#333333", "shininess": 20},
    "mahogany": {"color": "#4a2c1a", "specular": "#1a0800", "shininess": 25},
    "ebony": {"color": "#1a1210", "specular": "#0a0505", "shininess": 30},
    # Metals
    "steel": {"color": "#8b8b8b", "specular": "#cccccc", "shininess": 90},
    "aluminum": {"color": "#a8a8a8", "specular": "#eeeeee", "shininess": 85},
    "brass": {"color": "#b8860b", "specular": "#ffdd88", "shininess": 95},
    "copper": {"color": "#b87333", "specular": "#dd9944", "shininess": 80},
    "bronze": {"color": "#8b6914", "specular": "#ccaa44", "shininess": 75},
    "chrome": {"color": "#c0c0c0", "specular": "#ffffff", "shininess": 120},
    "gold": {"color": "#ffd700", "specular": "#fff8dc", "shininess": 100},
    "iron": {"color": "#5c5c5c", "specular": "#999999", "shininess": 70},
    # Plastics
    "plastic_white": {"color": "#f5f5f5", "specular": "#ffffff", "shininess": 60},
    "plastic_black": {"color": "#1a1a1a", "specular": "#444444", "shininess": 55},
    "plastic_red": {"color": "#c41e3a", "specular": "#ff6666", "shininess": 50},
    "plastic_blue": {"color": "#0066cc", "specular": "#6699ff", "shininess": 50},
    "plastic_green": {"color": "#228b22", "specular": "#66cc66", "shininess": 50},
    "plastic_yellow": {"color": "#ffcc00", "specular": "#ffee66", "shininess": 50},
    "plastic_orange": {"color": "#ff8c00", "specular": "#ffbb66", "shininess": 50},
    "plastic_gray": {"color": "#808080", "specular": "#aaaaaa", "shininess": 50},
    "plastic_clear": {"color": "#e8f4f8", "specular": "#ffffff", "shininess": 80},
}


def get_material(name):
    """Get material properties by name. Returns None if not found."""
    if not name:
        return None
    return MATERIAL_LIBRARY.get(str(name).lower().strip())


def list_materials():
    """Return list of available material names."""
    return list(MATERIAL_LIBRARY.keys())
