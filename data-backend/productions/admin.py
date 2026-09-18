from django.contrib import admin

from .models import Production, ProductionAssetStatus, Scene, SceneAsset


class SceneInline(admin.TabularInline):
    model = Scene
    extra = 0


class SceneAssetInline(admin.TabularInline):
    model = SceneAsset
    extra = 0


@admin.register(Production)
class ProductionAdmin(admin.ModelAdmin):
    list_display = ('title', 'production_type', 'user', 'is_archived', 'modified_on')
    list_filter = ('production_type', 'is_archived', 'user')
    search_fields = ('title', 'subtitle', 'user__email')
    inlines = [SceneInline]


@admin.register(Scene)
class SceneAdmin(admin.ModelAdmin):
    list_display = ('scene_type', 'production', 'sort_order', 'start_seconds', 'duration_seconds')
    list_filter = ('user',)
    inlines = [SceneAssetInline]


@admin.register(ProductionAssetStatus)
class ProductionAssetStatusAdmin(admin.ModelAdmin):
    list_display = ('display_name', 'status', 'production')
    list_filter = ('status',)
