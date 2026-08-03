from django.contrib import admin
from django.contrib.contenttypes.admin import GenericTabularInline
from .models import (
    AssetPhoto, AssetCategory, AssetTag, AssetArea, AssetBox, AssetItem,
)


class AssetPhotoInline(GenericTabularInline):
    model = AssetPhoto
    extra = 0
    fields = ('image', 'description', 'thumbnail_tag')
    readonly_fields = ('thumbnail_tag',)


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


@admin.register(AssetBox)
class AssetBoxAdmin(admin.ModelAdmin):
    list_display = ('name', 'parent_box', 'area', 'category', 'locator_code', 'modified_at')
    list_filter = ('category', 'tags', 'locator_type', 'area')
    search_fields = ('name', 'description', 'locator_code')
    autocomplete_fields = ('parent_box', 'area', 'category')
    filter_horizontal = ('tags',)
    inlines = [AssetPhotoInline]


@admin.register(AssetItem)
class AssetItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'box', 'area', 'category', 'locator_code', 'modified_at')
    list_filter = ('category', 'tags', 'locator_type', 'area', 'box')
    search_fields = ('name', 'description', 'locator_code')
    autocomplete_fields = ('box', 'area', 'category')
    filter_horizontal = ('tags',)
    inlines = [AssetPhotoInline]


@admin.register(AssetPhoto)
class AssetPhotoAdmin(admin.ModelAdmin):
    list_display = ('id', 'description', 'content_type', 'object_id', 'thumbnail_tag', 'created_at')
    list_filter = ('content_type', 'created_at')
    search_fields = ('description',)
    readonly_fields = ('thumbnail_tag',)
