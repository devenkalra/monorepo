from urllib.parse import quote_plus

from django.conf import settings
from django.db import models


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
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
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

    class Meta:
        ordering = ['-start_date', '-modified_on']
        indexes = [models.Index(fields=['user'], name='trip_user_idx')]

    def __str__(self):
        return self.title

    def sync_dates_from_days(self):
        dates = list(self.days.order_by('date').values_list('date', flat=True))
        self.start_date = dates[0] if dates else None
        self.end_date = dates[-1] if dates else None
        self.save(update_fields=['start_date', 'end_date', 'modified_on'])


class TripLodging(models.Model):
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
    journal = models.TextField(blank=True, default='')
    lodging = models.ForeignKey(
        TripLodging,
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
    STATUS_TOBOOK = 'tobook'
    STATUS_BOOKED = 'booked'
    STATUS_CONFIRMED = 'confirmed'
    STATUS_CHOICES = (
        (STATUS_TOBOOK, 'To book'),
        (STATUS_BOOKED, 'Booked'),
        (STATUS_CONFIRMED, 'Confirmed'),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='trip_stops',
    )
    day = models.ForeignKey(TripDay, on_delete=models.CASCADE, related_name='stops')
    text = models.TextField()
    loc = models.CharField(max_length=255, blank=True, default='')
    cat = models.CharField(max_length=64, blank=True, default='')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_CONFIRMED)
    done = models.BooleanField(default=False)
    start_time = models.TimeField(null=True, blank=True)
    duration_minutes = models.PositiveIntegerField(null=True, blank=True)
    extra = models.JSONField(default=dict, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'id']
        indexes = [models.Index(fields=['user', 'day'], name='tripstop_user_day_idx')]

    def __str__(self):
        return self.text[:80]


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
    stop = models.ForeignKey(TripStop, on_delete=models.CASCADE, related_name='attachments')
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
        indexes = [models.Index(fields=['user', 'stop'], name='tripattach_user_stop_idx')]

    def __str__(self):
        return self.title or self.kind

    def fill_map_urls(self):
        if self.kind != self.KIND_LOCATION:
            return
        self.url = self.url or google_maps_url(self.address, self.lat, self.lng)
        self.osm_url = self.osm_url or osm_maps_url(self.address, self.lat, self.lng)
