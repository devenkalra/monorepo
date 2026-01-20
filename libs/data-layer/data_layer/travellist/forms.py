# tickets/forms.py

from django import forms
from django.forms import ModelForm, RadioSelect, MultipleChoiceField



from .models import List, Tag, Item, ListItem

class ListAdminForm(ModelForm):
    name = forms.CharField(label="Name", max_length=32)
    tag_choices = Tag.objects.all().values_list('name', 'name')
    tags = forms.MultipleChoiceField(choices=tag_choices, widget=forms.CheckboxSelectMultiple, required=False)

    class Meta:
        model = List
        fields = [
            "name",
        ]
        #widgets = {
        #    "payment_method": RadioSelect(),
        #}

    def __init__(self, *args, **kwargs):
        instance = kwargs.get('instance')
        initial = {}

        if instance:
            selected_tags = instance.initial_tags.all().values_list('name', flat=True)
            initial = {
                "name": instance.name,

            }

        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        self.instance.name = self.cleaned_data["name"]
        tags_selected = self.cleaned_data.get("tags")
        items = Item.objects.filter(tags__name__in=tags_selected).values_list('id', flat=True)

        # Create matching list items
        new_items = []
        new_list = super().save()

        for item in items:
            new_list_item = ListItem.objects.create(item_id=item, in_list=new_list)
            new_items.append(new_list_item.id)

        new_list = super().save()
        new_list.items.set(new_items)
        return super().save(commit)


