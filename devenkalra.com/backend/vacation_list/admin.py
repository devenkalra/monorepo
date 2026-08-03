from django.contrib import admin
from .models import VacTag, VacCategory, VacItem, VacList, VacListItem


@admin.register(VacTag)
class VacTagAdmin(admin.ModelAdmin):
    list_display = ('name', 'modified_on')
    search_fields = ('name',)


@admin.register(VacCategory)
class VacCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'modified_on')
    search_fields = ('name',)


@admin.register(VacItem)
class VacItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'name_group', 'category', 'modified_on')
    list_filter = ('category', 'tags', 'name_group')
    search_fields = ('name', 'description', 'name_group')
    filter_horizontal = ('tags',)


class VacListItemInline(admin.TabularInline):
    model = VacListItem
    extra = 0
    autocomplete_fields = ('item',)
    fields = ('item', 'need', 'done')


@admin.register(VacList)
class VacListAdmin(admin.ModelAdmin):
    list_display = ('name', 'item_count', 'modified_on', 'created_at')
    search_fields = ('name',)
    filter_horizontal = ('initial_tags',)
    inlines = [VacListItemInline]
    actions = ['seed_from_tags']

    @admin.display(description='Items')
    def item_count(self, obj):
        return obj.list_items.count()

    @admin.action(description='Seed list items from initial tags')
    def seed_from_tags(self, request, queryset):
        total = 0
        for vac_list in queryset:
            total += vac_list.seed_from_initial_tags()
        self.message_user(request, f'Added {total} list item(s).')


@admin.register(VacListItem)
class VacListItemAdmin(admin.ModelAdmin):
    list_display = ('item', 'in_list', 'need', 'done', 'modified_on')
    list_filter = ('need', 'done', 'in_list')
    search_fields = ('item__name', 'in_list__name')
    autocomplete_fields = ('item', 'in_list')
