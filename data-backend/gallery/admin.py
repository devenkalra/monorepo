from django.contrib import admin

from .models import Gallery, GalleryItem, GalleryShare, GalleryShow, UserMedia


class GalleryItemInline(admin.TabularInline):
    model = GalleryItem
    extra = 0


class GalleryShareInline(admin.TabularInline):
    model = GalleryShare
    extra = 0
    readonly_fields = ('password_hash',)


class GalleryShowInline(admin.TabularInline):
    model = GalleryShow
    extra = 0


@admin.register(Gallery)
class GalleryAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug', 'owner', 'access_mode', 'updated_at')
    list_filter = ('access_mode',)
    search_fields = ('title', 'slug', 'owner__username', 'owner__email')
    inlines = [GalleryItemInline, GalleryShareInline, GalleryShowInline]


@admin.register(GalleryItem)
class GalleryItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'gallery', 'media_type', 'sort_order', 'title')


@admin.register(GalleryShare)
class GalleryShareAdmin(admin.ModelAdmin):
    list_display = ('email', 'gallery', 'role', 'active')


@admin.register(GalleryShow)
class GalleryShowAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug', 'gallery', 'updated_at')


@admin.register(UserMedia)
class UserMediaAdmin(admin.ModelAdmin):
    list_display = ('filename', 'owner', 'media_type', 'created_at')
    list_filter = ('media_type',)
    search_fields = ('filename', 'url', 'owner__email')
