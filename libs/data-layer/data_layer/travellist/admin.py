from .models import Item, ListItem, Tag, Category, List
from django.http import HttpResponse as HTTPResponse
from django.contrib import admin
from django.contrib.admin.widgets import AdminFileWidget
from django.utils.safestring import mark_safe
from .forms import ListAdminForm
from django.db.models import Q
import json
from django import forms
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.urls import path, reverse
from django.shortcuts import render
from django.db.models import Q
from django.db import models
from django.contrib.admin.helpers import ActionForm  # <-- add this



class AreaChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return obj.full_path()  # uses AssArea.full_path()


class BoxChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return obj.full_path()  # uses AssBox.full_path()



@admin.action(description='Not In List')
def not_in_list(modeladmin, request, queryset):
    def missing_items(list_name):
        list_id = List.objects.get(name=list_name).id
        # items that are not in the list
        # not(item.id == ListItem.item_id and ListItem.in_list_id == list_id)
        excluded_items = Item.objects.exclude(
            Q(id__in=ListItem.objects.filter(in_list_id=list_id).values_list('item_id', flat=True))
        ).values(['name'], flat=True)

    if 'apply' in request.POST:
        list_name = request.POST['list_name']
        excluded_items = missing_items(list_name)

        return render(request, 'admin/missing_items_confirmation.html',
                      context={'items': json.dumps(excluded_items), 'list_name': list_name})
    elif 'confirm' in request.POST:
        list_name = request.POST['list_name']
        return None
    return render(request, 'admin/list_selection.html', context={'items': queryset})


class ItemAdmin(admin.ModelAdmin):

    @admin.action(description='Set Group')
    def set_group(modeladmin, request, queryset):
        def get_groups():
            groups =  list(Item.objects.all().values('name_group').distinct().order_by('name_group'))
            groups = [x['name_group'] for x in groups if x['name_group'] != ""]
            return groups

        if 'confirm' in request.POST:
            selected_group = request.POST.getlist('new_group')[0]
            for item in queryset:
                item.name_group = selected_group
                item.save()
            return None

        if 'cancel' in request.POST:
            return None

        items_selected = list(queryset.values("id", 'name'))
        return render(request, 'admin/set_group.html', context={
            "items_selected":items_selected, 'groups': get_groups()})

    @admin.action(description='Set Tags')
    def set_tags(modeladmin, request, queryset):
        def get_tags():
            return list(Tag.objects.all().order_by('name').values('id', 'name'))

        if 'confirm' in request.POST:
            selected_tags = [int(x) for x in  json.loads(request.POST.getlist('selected')[0])]
            for item in queryset:
                item.tags.clear()
                item.tags.add(*selected_tags)
            return None

        if 'cancel' in request.POST:
            return None

        items_selected = list(queryset.values("id", 'name'))
        return render(request, 'admin/set_tags.html', context={
            "items_selected":items_selected, 'tags': get_tags()})



    def changelist_view(self, request, extra_context=None):
        return super().changelist_view(request, extra_context=extra_context)

    def response_action(self, request, queryset):
        return super().response_action(request, queryset)

    def get_tags(self, obj):
        return ", ".join([t.name for t in obj.tags.all()])

    actions = [set_tags, set_group]
    get_tags.short_description = 'Tags'
    list_display = ('name', 'name_group', 'category', 'get_tags')
    search_fields = ['name']
    list_filter = ['category',  ]


admin.site.register(Item, ItemAdmin)


class ListItemInline(admin.TabularInline):
    model = ListItem
    extra = 0


@admin.action(description='Mark As Done')
def mark_as_done(modeladmin, request, queryset):
    queryset.update(done=True)


@admin.action(description='Mark As Not Done')
def mark_as_not_done(modeladmin, request, queryset):
    queryset.update(done=False)


@admin.action(description='Mark As Needed')
def mark_as_needed(modeladmin, request, queryset):
    queryset.update(need=True)


@admin.action(description='Mark As Not Needed')
def mark_as_not_needed(modeladmin, request, queryset):
    queryset.update(need=False)


from django.contrib import messages


class ListItemAdmin(admin.ModelAdmin):

    @admin.action(description='Remove From List')
    def remove_from_list(modeladmin, request, queryset):
        queryset.delete()

    @admin.action(description='Not In List')
    def not_in_list(modeladmin, request, queryset):
        def missing_items(list_id, *need_fields):
            excluded_items = Item.objects.exclude(
                Q(id__in=ListItem.objects.filter(in_list_id=list_id).values_list('item_id', flat=True))
            ).values(*need_fields, flat=True)
            return excluded_items

        if 'confirm' in request.POST:
            list_id = request.POST['list_id']
            selected = request.POST.getlist('selected')
            missing_items = json.loads(selected[0])

            for item in missing_items:
                ListItem.objects.create(item_id=item, in_list_id=list_id)
                List.objects.get(id=list_id).items.add(item)

            return None
        if 'in_list__id__exact' not in request.GET:
            modeladmin.message_user(
                request,
                "Please select a list to add items to",
                messages.INFO,
            )
            return None
        list_id = request.GET['in_list__id__exact'][0]

        excluded_items = list(Item.objects.exclude(
            Q(id__in=ListItem.objects.filter(in_list_id=list_id).values_list('item_id', flat=True))
        ).order_by('category__name').values("id", "name", "category__name"))

        if (len(excluded_items) == 0):
            modeladmin.message_user(
                request,
                "No Items To Add",
                messages.INFO,
            )
            return None
        return render(request, 'admin/missing_items_confirmation.html',
                      context={'items': excluded_items, 'list_id': list_id})

    actions = [mark_as_done, mark_as_not_done, mark_as_needed, mark_as_not_needed, not_in_list, remove_from_list]
    search_fields = ['item__name', 'need', 'done']
    list_filter = ['need', 'done', "item__category", 'in_list', ]

    def changelist_view(self, request, extra_context=None):
        if "action" in request.POST and request.POST["action"] == "not_in_list":
            return self.response_action(request, self.get_queryset(request))

        return super().changelist_view(request, extra_context=extra_context)

    def response_action(self, request, queryset):
        if '_not_in_list' in request.POST:
            return not_in_list(self, request, queryset)
        if "action" in request.POST and request.POST["action"] == "not_in_list":
            request.POST._mutable = True
            request.POST['_selected_action'] = '1'
        return super().response_action(request, queryset)

    def get_category(self, obj):
        return obj.item.category

    @admin.display(description='Need')
    def get_need(obj):
        return f"{obj.need}" #obj.need

    get_category.short_description = 'Category'
    get_category.admin_order_field = 'item__category'

    def get_tags(self, obj):
        return ", ".join([t.name for t in obj.item.tags.all()])

    get_tags.short_description = 'Tags'

    get_category.short_description = 'Category'
    list_display = ('item', 'get_category', get_need, 'need', 'done', 'get_tags')


admin.site.register(ListItem, ListItemAdmin)
admin.site.register(Tag)
admin.site.register(Category)


class ListAdmin(admin.ModelAdmin):
    form = ListAdminForm


admin.site.register(List, ListAdmin)


# admin.py
from django.contrib import admin
from django.contrib.contenttypes.admin import GenericTabularInline
from django.utils.html import format_html, format_html_join



# ---------- Helpers ----------
@admin.action(description="Assign category (from action form)")
def assign_category_action(self, request, queryset):
    category_id = request.POST.get("category")
    if not category_id:
        self.message_user(
            request,
            "No category selected in the action bar.",
            level=messages.WARNING,
        )
        return

    try:
        category = AssetCategory.objects.get(pk=category_id)
    except AssetCategory.DoesNotExist:
        self.message_user(
            request,
            "Selected category does not exist.",
            level=messages.ERROR,
        )
        return

    updated = queryset.update(category=category)
    self.message_user(
        request,
        f"Category '{category.name}' assigned to {updated} item(s).",
        level=messages.SUCCESS,
    )

@admin.action(description="Add tags (from action form)")
def add_tags_action(self, request, queryset):
    tag_ids = request.POST.getlist("tags")
    if not tag_ids:
        self.message_user(
            request,
            "No tags selected in the action bar.",
            level=messages.WARNING,
        )
        return

    tags = list(AssetTag.objects.filter(pk__in=tag_ids))
    if not tags:
        self.message_user(
            request,
            "None of the selected tags exist.",
            level=messages.ERROR,
        )
        return

    for obj in queryset:
        obj.tags.add(*tags)

    self.message_user(
        request,
        f"Added {len(tags)} tag(s) to {queryset.count()} item(s).",
        level=messages.SUCCESS,
    )



