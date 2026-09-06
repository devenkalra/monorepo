from django.contrib import admin
from .models import VacTag, VacCategory, VacItem, VacList, VacListItem


@admin.register(VacTag)
class VacTagAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'modified_on')
    list_filter = ('user',)
    search_fields = ('name', 'user__email')


@admin.register(VacCategory)
class VacCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'modified_on')
    list_filter = ('user',)
    search_fields = ('name', 'user__email')


@admin.register(VacItem)
class VacItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'name_group', 'category', 'has_image', 'modified_on')
    list_filter = ('user', 'category', 'tags', 'name_group')
    search_fields = ('name', 'description', 'name_group', 'user__email')
    filter_horizontal = ('tags',)

    @admin.display(boolean=True, description='Image')
    def has_image(self, obj):
        return bool(obj.image)


class VacListItemInline(admin.TabularInline):
    model = VacListItem
    extra = 0
    autocomplete_fields = ('item',)
    fields = ('item', 'need', 'done')


@admin.register(VacList)
class VacListAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'is_archived', 'item_count', 'modified_on', 'created_at')
    list_filter = ('user', 'is_archived')
    search_fields = ('name', 'user__email')
    filter_horizontal = ('initial_tags',)
    inlines = [VacListItemInline]
    actions = ['seed_from_tags', 'archive_lists', 'unarchive_lists']

    @admin.display(description='Items')
    def item_count(self, obj):
        return obj.list_items.count()

    @admin.action(description='Seed list items from initial tags')
    def seed_from_tags(self, request, queryset):
        total = 0
        for vac_list in queryset:
            total += vac_list.seed_from_initial_tags()
        self.message_user(request, f'Added {total} list item(s).')

    @admin.action(description='Archive selected lists')
    def archive_lists(self, request, queryset):
        updated = queryset.update(is_archived=True)
        self.message_user(request, f'Archived {updated} list(s).')

    @admin.action(description='Unarchive selected lists')
    def unarchive_lists(self, request, queryset):
        updated = queryset.update(is_archived=False)
        self.message_user(request, f'Unarchived {updated} list(s).')


@admin.register(VacListItem)
class VacListItemAdmin(admin.ModelAdmin):
    list_display = ('item', 'in_list', 'user', 'need', 'done', 'modified_on')
    list_filter = ('user', 'need', 'done', 'in_list')
    search_fields = ('item__name', 'in_list__name', 'user__email')
    autocomplete_fields = ('item', 'in_list')
