"""Reserved first URL path segments (not usable as public_username)."""

RESERVED_USERNAMES = frozenset({
    'app',
    'apps',
    'admin',
    'accounts',
    'api',
    'static',
    'media',
    'login',
    'logout',
    'health',
    'favicon.ico',
    'robots.txt',
    'well-known',
    'api-tester',
})

ROLE_VIEW = 'view'
ROLE_ADD = 'add_photos'
ROLE_EDIT = 'edit'
ROLE_CHOICES = [
    (ROLE_VIEW, 'View'),
    (ROLE_ADD, 'Add photos'),
    (ROLE_EDIT, 'Edit'),
]

ACCESS_PUBLIC = 'public'
ACCESS_RESTRICTED = 'restricted'
ACCESS_CHOICES = [
    (ACCESS_PUBLIC, 'Public (anyone with link)'),
    (ACCESS_RESTRICTED, 'Restricted (allow-list)'),
]

MEDIA_IMAGE = 'image'
MEDIA_VIDEO = 'video'
MEDIA_OTHER = 'other'
MEDIA_TYPE_CHOICES = [
    (MEDIA_IMAGE, 'Image'),
    (MEDIA_VIDEO, 'Video'),
    (MEDIA_OTHER, 'Other'),
]

VIDEO_EXTENSIONS = frozenset({'.mp4', '.webm', '.mov', '.m4v', '.mkv'})
IMAGE_EXTENSIONS = frozenset({'.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.bmp'})
