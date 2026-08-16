from django.conf import settings
from django.db import models


class VacTag(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='vacation_tags',
    )
    name = models.CharField(max_length=255)

    class Meta:
        ordering = ['name']
        verbose_name = 'Vacation tag'
        verbose_name_plural = 'Vacation tags'
        indexes = [
            models.Index(fields=['user'], name='vac_tag_user_idx'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'name'],
                name='vacation_list_vactag_user_name_uniq',
            ),
        ]

    def __str__(self):
        return self.name


class VacCategory(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='vacation_categories',
    )
    name = models.CharField(max_length=255)

    class Meta:
        ordering = ['name']
        verbose_name = 'Vacation category'
        verbose_name_plural = 'Vacation categories'
        indexes = [
            models.Index(fields=['user'], name='vac_category_user_idx'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'name'],
                name='vacation_list_vaccategory_user_name_uniq',
            ),
        ]

    def __str__(self):
        return self.name


class VacItem(models.Model):
    """Catalog packing item (e.g. passport, charger)."""
    created_at = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='vacation_items',
    )
    name = models.CharField(max_length=255)
    name_group = models.CharField(max_length=255, blank=True)
    description = models.TextField(null=True, blank=True)
    category = models.ForeignKey(
        VacCategory,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='items',
    )
    tags = models.ManyToManyField(VacTag, blank=True, related_name='items')

    class Meta:
        ordering = ['name']
        verbose_name = 'Vacation item'
        verbose_name_plural = 'Vacation items'
        indexes = [
            models.Index(fields=['user'], name='vac_item_user_idx'),
        ]

    def __str__(self):
        return self.name


class VacList(models.Model):
    """A packing list for a trip (seeded from initial_tags when created)."""
    created_at = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='vacation_lists',
    )
    name = models.CharField(max_length=255)
    is_archived = models.BooleanField(
        default=False,
        db_index=True,
        help_text='Archived lists are hidden from the default list picker.',
    )
    initial_tags = models.ManyToManyField(VacTag, blank=True, related_name='lists')

    class Meta:
        ordering = ['-modified_on']
        verbose_name = 'Vacation list'
        verbose_name_plural = 'Vacation lists'
        indexes = [
            models.Index(fields=['user'], name='vac_list_user_idx'),
        ]

    def __str__(self):
        return self.name

    def seed_from_initial_tags(self):
        """Add VacListItems for catalog items matching any initial_tags."""
        tags = self.initial_tags.all()
        if not tags.exists():
            return 0
        existing = set(self.list_items.values_list('item_id', flat=True))
        to_add = []
        for item in VacItem.objects.filter(user=self.user, tags__in=tags).distinct():
            if item.id in existing:
                continue
            to_add.append(
                VacListItem(item=item, in_list=self, user=self.user, need=True, done=False)
            )
            existing.add(item.id)
        VacListItem.objects.bulk_create(to_add)
        return len(to_add)

    def populate_all_catalog_items(self):
        """Add every VacItem from this user's catalog (need=True, done=False)."""
        existing = set(self.list_items.values_list('item_id', flat=True))
        to_add = [
            VacListItem(item=item, in_list=self, user=self.user, need=True, done=False)
            for item in VacItem.objects.filter(user=self.user)
            if item.id not in existing
        ]
        VacListItem.objects.bulk_create(to_add)
        return len(to_add)

    def copy_items_from(self, source_list):
        """Copy membership from another of this user's lists. Preserves need; resets done."""
        existing = set(self.list_items.values_list('item_id', flat=True))
        to_add = []
        for li in source_list.list_items.select_related('item'):
            if li.item_id in existing:
                continue
            to_add.append(
                VacListItem(
                    item_id=li.item_id,
                    in_list=self,
                    user=self.user,
                    need=li.need,
                    done=False,
                )
            )
            existing.add(li.item_id)
        VacListItem.objects.bulk_create(to_add)
        return len(to_add)


class VacListItem(models.Model):
    """An item instance on a specific packing list."""
    created_at = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='vacation_list_items',
    )
    item = models.ForeignKey(VacItem, on_delete=models.CASCADE, related_name='list_items')
    need = models.BooleanField(default=True)
    done = models.BooleanField(default=False)
    in_list = models.ForeignKey(VacList, on_delete=models.CASCADE, related_name='list_items')

    class Meta:
        ordering = ['item__name']
        verbose_name = 'Vacation list item'
        verbose_name_plural = 'Vacation list items'
        indexes = [
            models.Index(fields=['user'], name='vac_listitem_user_idx'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['item', 'in_list'],
                name='vacation_list_unique_item_per_list',
            ),
        ]

    def __str__(self):
        return f"{self.item.name} ({self.in_list.name})"
