import secrets
from urllib.parse import quote_plus

from django.conf import settings
from django.db import models

# Prices with a blank currency are in this one.
DEFAULT_CURRENCY = 'USD'
DEFAULT_CURRENCY_SYMBOL = '$'


def google_maps_url(address='', lat=None, lng=None):
    if lat is not None and lng is not None:
        return f'https://www.google.com/maps?q={lat},{lng}'
    if address:
        return f'https://www.google.com/maps/search/?api=1&query={quote_plus(address)}'
    return ''


def osm_maps_url(address='', lat=None, lng=None):
    if lat is not None and lng is not None:
        return f'https://www.openstreetmap.org/?mlat={lat}&mlon={lng}#map=16/{lat}/{lng}'
    if address:
        return f'https://www.openstreetmap.org/search?query={quote_plus(address)}'
    return ''


class Trip(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='trips',
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    notes = models.TextField(blank=True, default='')
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    timezone = models.CharField(
        max_length=64, blank=True, default='',
        help_text='IANA zone the trip starts in, e.g. America/Los_Angeles.',
    )
    packing_list = models.ForeignKey(
        'vacation_list.VacList',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='trips',
    )
    gallery = models.ForeignKey(
        'gallery.Gallery',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='trips',
    )
    share_token = models.CharField(max_length=64, unique=True, null=True, blank=True)
    public_enabled = models.BooleanField(default=False)

    class Meta:
        ordering = ['-start_date', '-modified_on']
        indexes = [models.Index(fields=['user'], name='trip_user_idx')]

    def __str__(self):
        return self.title

    def ensure_share_token(self, *, rotate=False):
        if rotate or not self.share_token:
            for _ in range(5):
                candidate = secrets.token_urlsafe(24)
                if not Trip.objects.filter(share_token=candidate).exists():
                    self.share_token = candidate
                    return self.share_token
            self.share_token = secrets.token_urlsafe(32)
        return self.share_token

    def sync_dates_from_days(self):
        dates = list(self.days.order_by('date').values_list('date', flat=True))
        self.start_date = dates[0] if dates else None
        self.end_date = dates[-1] if dates else None
        self.save(update_fields=['start_date', 'end_date', 'modified_on'])


class TripLodging(models.Model):
    STATUS_OPTION = 'option'
    STATUS_NO_BOOKING = 'no_booking'
    STATUS_TOBOOK = 'tobook'
    STATUS_BOOKED = 'booked'
    STATUS_CONFIRMED = 'confirmed'
    STATUS_CHOICES = (
        (STATUS_OPTION, 'Option'),
        (STATUS_NO_BOOKING, 'No booking needed'),
        (STATUS_TOBOOK, 'To book'),
        (STATUS_BOOKED, 'Booked'),
        (STATUS_CONFIRMED, 'Confirmed'),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='trip_lodgings',
    )
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name='lodgings')
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=500, blank=True, default='')
    phone = models.CharField(max_length=64, blank=True, default='')
    url = models.CharField(max_length=2000, blank=True, default='')
    confirmation = models.CharField(max_length=128, blank=True, default='')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_TOBOOK)
    price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(
        max_length=8, blank=True, default='',
        help_text='ISO code such as THB; blank means the default currency ($).',
    )
    person = models.CharField(max_length=120, blank=True, default='')
    notes = models.TextField(blank=True, default='')
    check_in_time = models.TimeField(null=True, blank=True)
    check_out_time = models.TimeField(null=True, blank=True)

    class Meta:
        ordering = ['name', 'id']
        indexes = [models.Index(fields=['user', 'trip'], name='triplodge_user_trip_idx')]

    def __str__(self):
        return self.name

    @property
    def maps_url(self):
        return google_maps_url(self.address) if self.address else ''


class TripLeg(models.Model):
    """A named region/phase grouping consecutive days of a trip (e.g., Bangkok, Chiang Mai)."""

    created_at = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='trip_legs',
    )
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name='legs')
    name = models.CharField(max_length=160)
    location = models.CharField(max_length=255, blank=True, default='')
    timezone = models.CharField(
        max_length=64, blank=True, default='',
        help_text='Optional default time zone for this leg.',
    )
    notes = models.TextField(blank=True, default='')
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'id']
        indexes = [models.Index(fields=['user', 'trip'], name='tripleg_user_trip_idx')]

    def __str__(self):
        return self.name


class TripDay(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='trip_days',
    )
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name='days')
    date = models.DateField()
    title = models.CharField(max_length=255, blank=True, default='')
    notes = models.TextField(
        blank=True, default='',
        help_text='High-level planning notes for the day (distinct from the travelog journal).',
    )
    journal = models.TextField(blank=True, default='')
    timezone = models.CharField(
        max_length=64, blank=True, default='',
        help_text='Blank continues in the zone the previous day ended in.',
    )
    lodging = models.ForeignKey(
        TripLodging,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='days',
    )
    leg = models.ForeignKey(
        TripLeg,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='days',
    )
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['date', 'sort_order', 'id']
        indexes = [models.Index(fields=['user', 'trip'], name='tripday_user_trip_idx')]
        constraints = [
            models.UniqueConstraint(fields=['trip', 'date'], name='trips_unique_date_per_trip'),
        ]

    def __str__(self):
        return f'{self.date} {self.title}'.strip()


class TripStop(models.Model):
    STATUS_OPTION = 'option'
    STATUS_NO_BOOKING = 'no_booking'
    STATUS_TOBOOK = 'tobook'
    STATUS_BOOKED = 'booked'
    STATUS_CONFIRMED = 'confirmed'
    STATUS_CHOICES = (
        (STATUS_OPTION, 'Option'),
        (STATUS_NO_BOOKING, 'No booking needed'),
        (STATUS_TOBOOK, 'To book'),
        (STATUS_BOOKED, 'Booked'),
        (STATUS_CONFIRMED, 'Confirmed'),
    )
    KIND_ACTIVITY = 'activity'
    KIND_TRAVEL = 'travel'
    KIND_EVENT = 'event'
    KIND_CHOICES = (
        (KIND_ACTIVITY, 'Activity'),
        (KIND_TRAVEL, 'Travel'),
        (KIND_EVENT, 'Event'),
    )
    TRAVEL_FLIGHT = 'flight'
    TRAVEL_DRIVE = 'drive'
    TRAVEL_WALK = 'walk'
    TRAVEL_BOAT = 'boat'
    TRAVEL_MODE_CHOICES = (
        (TRAVEL_FLIGHT, 'Flight'),
        (TRAVEL_DRIVE, 'Drive'),
        (TRAVEL_WALK, 'Walk'),
        (TRAVEL_BOAT, 'Boat'),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='trip_stops',
    )
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name='stops')
    day = models.ForeignKey(TripDay, null=True, blank=True, on_delete=models.CASCADE, related_name='stops')
    leg = models.ForeignKey(TripLeg, null=True, blank=True, on_delete=models.SET_NULL, related_name='ideas')
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default=KIND_ACTIVITY)
    travel_mode = models.CharField(max_length=20, choices=TRAVEL_MODE_CHOICES, blank=True, default='')
    text = models.TextField()
    description = models.TextField(blank=True, default='')
    loc = models.CharField(max_length=255, blank=True, default='')
    arrive_loc = models.CharField(max_length=255, blank=True, default='')
    cat = models.CharField(max_length=64, blank=True, default='')
    price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(
        max_length=8, blank=True, default='',
        help_text='ISO code such as THB; blank means the default currency ($).',
    )
    person = models.CharField(max_length=120, blank=True, default='')
    confirmation = models.CharField(max_length=128, blank=True, default='')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_NO_BOOKING)
    done = models.BooleanField(default=False)
    start_time = models.TimeField(null=True, blank=True)
    duration_minutes = models.PositiveIntegerField(null=True, blank=True)
    timezone = models.CharField(
        max_length=64, blank=True, default='',
        help_text='Blank uses the zone the itinerary is in at this point of the day.',
    )
    arrive_timezone = models.CharField(
        max_length=64, blank=True, default='',
        help_text='Travel only; blank arrives in the departure zone. Later items continue in this zone.',
    )
    extra = models.JSONField(default=dict, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'id']
        indexes = [
            models.Index(fields=['user', 'day'], name='tripstop_user_day_idx'),
            models.Index(fields=['user', 'trip'], name='tripstop_user_trip_idx'),
        ]

    def save(self, *args, **kwargs):
        if self.day_id and not self.trip_id:
            self.trip_id = self.day.trip_id
        elif self.day_id and self.trip_id != self.day.trip_id:
            self.trip_id = self.day.trip_id
        if self.leg_id and not self.trip_id:
            self.trip_id = self.leg.trip_id
        super().save(*args, **kwargs)

    def __str__(self):
        return self.text[:80]


class TripTodo(models.Model):
    """A to-do on the trip itself, or on one of its days or stops."""

    created_at = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='trip_todos',
    )
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name='todos')
    day = models.ForeignKey(TripDay, null=True, blank=True, on_delete=models.CASCADE, related_name='todos')
    stop = models.ForeignKey(TripStop, null=True, blank=True, on_delete=models.CASCADE, related_name='todos')
    text = models.TextField()
    category = models.CharField(max_length=60, blank=True, default='')
    done = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'id']
        indexes = [models.Index(fields=['user', 'trip'], name='triptodo_user_trip_idx')]

    def __str__(self):
        return self.text[:80]


class TripSuggestionBatch(models.Model):
    """One AI request from the trip assistant; filled in by a background task."""

    STATUS_RUNNING = 'running'
    STATUS_DONE = 'done'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = (
        (STATUS_RUNNING, 'Running'),
        (STATUS_DONE, 'Done'),
        (STATUS_FAILED, 'Failed'),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='trip_suggestion_batches',
    )
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name='suggestion_batches')
    day = models.ForeignKey(TripDay, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    prompt = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_RUNNING)
    error = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-created_at', '-id']
        indexes = [models.Index(fields=['user', 'trip'], name='tripsugbatch_user_trip_idx')]

    def __str__(self):
        return self.prompt[:80]


class TripSuggestion(models.Model):
    """A structured AI recommendation that can be turned into a stop, event, or lodging."""

    KIND_STOP = 'stop'
    KIND_EVENT = 'event'
    KIND_LODGING = 'lodging'
    KIND_CHOICES = (
        (KIND_STOP, 'Stop'),
        (KIND_EVENT, 'Event'),
        (KIND_LODGING, 'Lodging'),
    )
    STATUS_PENDING = 'pending'
    STATUS_ADDED = 'added'
    STATUS_DISMISSED = 'dismissed'
    STATUS_CHOICES = (
        (STATUS_PENDING, 'Pending'),
        (STATUS_ADDED, 'Added'),
        (STATUS_DISMISSED, 'Dismissed'),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='trip_suggestions',
    )
    batch = models.ForeignKey(TripSuggestionBatch, on_delete=models.CASCADE, related_name='suggestions')
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    data = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    stop = models.ForeignKey(TripStop, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    lodging = models.ForeignKey(TripLodging, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'id']
        indexes = [models.Index(fields=['user', 'batch'], name='tripsug_user_batch_idx')]

    def __str__(self):
        return self.data.get('name', '')[:80]


class TripMedia(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='trip_media',
    )
    asset = models.ForeignKey(
        'gallery.UserMedia',
        on_delete=models.CASCADE,
        related_name='trip_placements',
    )
    trip = models.ForeignKey(
        Trip, null=True, blank=True, on_delete=models.CASCADE, related_name='media'
    )
    day = models.ForeignKey(
        TripDay, null=True, blank=True, on_delete=models.CASCADE, related_name='media'
    )
    stop = models.ForeignKey(
        TripStop, null=True, blank=True, on_delete=models.CASCADE, related_name='media'
    )
    caption = models.CharField(max_length=500, blank=True, default='')
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'created_at']
        indexes = [models.Index(fields=['user'], name='tripmedia_user_idx')]

    def __str__(self):
        return self.caption or str(self.asset_id)


class TripStopAttachment(models.Model):
    KIND_DOCUMENT = 'document'
    KIND_URL = 'url'
    KIND_PICTURE = 'picture'
    KIND_LOCATION = 'location'
    KIND_CHOICES = (
        (KIND_DOCUMENT, 'Document'),
        (KIND_URL, 'URL'),
        (KIND_PICTURE, 'Picture'),
        (KIND_LOCATION, 'Location'),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='trip_attachments',
    )
    stop = models.ForeignKey(
        TripStop,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='attachments',
    )
    lodging = models.ForeignKey(
        'TripLodging',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='attachments',
    )
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    title = models.CharField(max_length=255, blank=True, default='')
    url = models.CharField(max_length=2000, blank=True, default='')
    osm_url = models.CharField(max_length=2000, blank=True, default='')
    address = models.CharField(max_length=500, blank=True, default='')
    lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    asset = models.ForeignKey(
        'gallery.UserMedia',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='trip_attachments',
    )
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'id']
        indexes = [
            models.Index(fields=['user', 'stop'], name='tripattach_user_stop_idx'),
            models.Index(fields=['user', 'lodging'], name='tripattach_user_lodge_idx'),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(stop__isnull=False, lodging__isnull=True)
                    | models.Q(stop__isnull=True, lodging__isnull=False)
                ),
                name='tripattach_stop_or_lodging',
            ),
        ]

    def __str__(self):
        return self.title or self.kind

    def fill_map_urls(self):
        if self.kind != self.KIND_LOCATION:
            return
        self.url = self.url or google_maps_url(self.address, self.lat, self.lng)
        self.osm_url = self.osm_url or osm_maps_url(self.address, self.lat, self.lng)


class TripShare(models.Model):
    """Explicit collaborator share grant on a trip (Editor or Viewer)."""

    ROLE_EDITOR = 'editor'
    ROLE_VIEWER = 'viewer'
    ROLE_CHOICES = (
        (ROLE_EDITOR, 'Editor'),
        (ROLE_VIEWER, 'Viewer'),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name='shares')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='trip_shares',
    )
    email = models.EmailField()
    role = models.CharField(max_length=16, choices=ROLE_CHOICES, default=ROLE_VIEWER)
    invite_token = models.CharField(max_length=64, unique=True, blank=True, default='')
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
    )

    class Meta:
        ordering = ['created_at', 'id']
        indexes = [
            models.Index(fields=['trip'], name='tripshare_trip_idx'),
            models.Index(fields=['user'], name='tripshare_user_idx'),
            models.Index(fields=['email'], name='tripshare_email_idx'),
        ]
        constraints = [
            models.UniqueConstraint(fields=['trip', 'email'], name='tripshare_trip_email_uniq'),
        ]

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.strip().lower()
        if not self.invite_token:
            self.invite_token = secrets.token_urlsafe(24)
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.email} ({self.role}) on {self.trip_id}'


class TripComment(models.Model):
    """Threaded comment attached to a trip, leg, day, stop/idea, or lodging."""

    TARGET_TRIP = 'trip'
    TARGET_LEG = 'leg'
    TARGET_DAY = 'day'
    TARGET_STOP = 'stop'
    TARGET_LODGING = 'lodging'

    created_at = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='trip_comments',
    )
    parent = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='replies',
    )
    leg = models.ForeignKey(TripLeg, null=True, blank=True, on_delete=models.CASCADE, related_name='comments')
    day = models.ForeignKey(TripDay, null=True, blank=True, on_delete=models.CASCADE, related_name='comments')
    stop = models.ForeignKey(TripStop, null=True, blank=True, on_delete=models.CASCADE, related_name='comments')
    lodging = models.ForeignKey(TripLodging, null=True, blank=True, on_delete=models.CASCADE, related_name='comments')
    body = models.TextField()
    resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
    )

    class Meta:
        ordering = ['created_at', 'id']
        indexes = [
            models.Index(fields=['trip', 'resolved'], name='tripcomment_trip_res_idx'),
            models.Index(fields=['parent'], name='tripcomment_parent_idx'),
        ]

    @property
    def target_type(self):
        if self.stop_id:
            return self.TARGET_STOP
        if self.lodging_id:
            return self.TARGET_LODGING
        if self.day_id:
            return self.TARGET_DAY
        if self.leg_id:
            return self.TARGET_LEG
        return self.TARGET_TRIP

    def __str__(self):
        return f'Comment #{self.pk} on trip {self.trip_id}: {self.body[:50]}'

