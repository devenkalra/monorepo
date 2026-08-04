from django.contrib import admin
from django.contrib.contenttypes.admin import GenericTabularInline
from .models import (
    AssetPhoto, AssetCategory, AssetTag, AssetArea, AssetItem,
)


class AssetPhotoInline(GenericTabularInline):
    model = AssetPhoto
    extra = 0
    fields = ('image', 'description', 'sort_order', 'thumbnail_tag')
    readonly_fields = ('thumbnail_tag',)
    ordering = ('sort_order', 'id')


@admin.register(AssetCategory)
class AssetCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'modified_at')
    search_fields = ('name', 'description')


@admin.register(AssetTag)
class AssetTagAdmin(admin.ModelAdmin):
    list_display = ('name', 'modified_at')
    search_fields = ('name',)


@admin.register(AssetArea)
class AssetAreaAdmin(admin.ModelAdmin):
    list_display = ('name', 'parent_area', 'category', 'locator_code', 'modified_at')
    list_filter = ('category', 'tags', 'locator_type')
    search_fields = ('name', 'description', 'locator_code')
    autocomplete_fields = ('parent_area', 'category')
    filter_horizontal = ('tags',)
    inlines = [AssetPhotoInline]


@admin.register(AssetItem)
class AssetItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'area', 'category', 'locator_code', 'modified_at')
    list_filter = ('category', 'tags', 'locator_type', 'area')
    search_fields = ('name', 'description', 'locator_code')
    autocomplete_fields = ('area', 'category')
    filter_horizontal = ('tags',)
    inlines = [AssetPhotoInline]


@admin.register(AssetPhoto)
class AssetPhotoAdmin(admin.ModelAdmin):
    list_display = ('id', 'description', 'sort_order', 'content_type', 'object_id', 'created_at')
    list_filter = ('content_type',)
    search_fields = ('description',)
    readonly_fields = ('thumbnail_tag',)
