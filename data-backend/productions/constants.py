PRODUCTION_TYPE_SHORT_FORM = 'short_form_documentary'
PRODUCTION_TYPE_LONG_FORM = 'long_form_documentary'
PRODUCTION_TYPE_REEL = 'reel'

PRODUCTION_TYPES = [
    (PRODUCTION_TYPE_SHORT_FORM, 'Short Form Documentary'),
    (PRODUCTION_TYPE_LONG_FORM, 'Long Form Documentary'),
    (PRODUCTION_TYPE_REEL, 'Reel'),
]

PRODUCTION_TYPE_LABELS = dict(PRODUCTION_TYPES)

SCENE_TYPE_PRESETS = [
    'Hook',
    'Intro',
    'Preparation',
    'Anticipation',
    'Body',
    'Outro',
]

ASSET_STATUS_TODO = 'todo'
ASSET_STATUS_IN_PROGRESS = 'in_progress'
ASSET_STATUS_DONE = 'done'

ASSET_STATUSES = [
    (ASSET_STATUS_TODO, 'Todo'),
    (ASSET_STATUS_IN_PROGRESS, 'In progress'),
    (ASSET_STATUS_DONE, 'Done'),
]

DEFAULT_SCENE_DURATION_SECONDS = '10'
