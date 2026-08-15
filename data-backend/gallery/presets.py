"""Style tables for the show compiler. Sequential A/B blend is not used here."""

PRESETS = {
    'kenburns': {
        'seconds': 6.0,
        'zoom_end': 1.18,
        'fade': 0.8,
        'crop_top': 0.0,
        'crop_bottom': 0.0,
    },
    'punchy': {
        'seconds': 2.8,
        'zoom_end': 1.06,
        'fade': 0.0,
        'crop_top': 0.0,
        'crop_bottom': 0.0,
    },
    'documentary': {
        'seconds': 8.0,
        'zoom_end': 1.12,
        'fade': 1.2,
        'crop_top': 0.0,
        'crop_bottom': 0.0,
    },
    'cinematic': {
        'seconds': 5.0,
        'zoom_end': 1.15,
        'fade': 0.8,
        'crop_top': 0.1,
        'crop_bottom': 0.1,
    },
}

DEFAULT_STYLE = 'kenburns'
MIN_CLIP = 0.2
MAX_SHOTS = 80
MIN_TARGET = 8.0
MAX_TARGET = 180.0
