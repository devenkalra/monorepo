from django.contrib import admin

from .models import Trip, TripDay, TripLodging, TripMedia, TripStop, TripStopAttachment


class TripStopInline(admin.TabularInline):
    model = TripStop
    extra = 0


class TripDayInline(admin.TabularInline):
    model = TripDay
    extra = 0
    fields = ('date', 'title', 'lodging', 'sort_order')


@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'start_date', 'end_date', 'modified_on')
    list_filter = ('user',)
    search_fields = ('title', 'user__email')
    inlines = [TripDayInline]


@admin.register(TripLodging)
class TripLodgingAdmin(admin.ModelAdmin):
    list_display = ('name', 'trip', 'confirmation', 'user')
    list_filter = ('user',)
    search_fields = ('name', 'address', 'confirmation')


@admin.register(TripDay)
class TripDayAdmin(admin.ModelAdmin):
    list_display = ('date', 'title', 'lodging', 'trip', 'user')
    list_filter = ('user',)
    search_fields = ('title', 'trip__title')
    inlines = [TripStopInline]


class TripStopAttachmentInline(admin.TabularInline):
    model = TripStopAttachment
    extra = 0


@admin.register(TripStop)
class TripStopAdmin(admin.ModelAdmin):
    list_display = ('text', 'day', 'start_time', 'duration_minutes', 'loc', 'cat', 'status', 'done', 'user')
    list_filter = ('user', 'status', 'done', 'cat')
    search_fields = ('text', 'loc')
    inlines = [TripStopAttachmentInline]


@admin.register(TripStopAttachment)
class TripStopAttachmentAdmin(admin.ModelAdmin):
    list_display = ('kind', 'title', 'stop', 'user')
    list_filter = ('user', 'kind')


@admin.register(TripMedia)
class TripMediaAdmin(admin.ModelAdmin):
    list_display = ('asset', 'trip', 'day', 'stop', 'user')
    list_filter = ('user',)
