from django.db import models
import datetime

class Item(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)
    name = models.CharField(max_length=255)
    name_group = models.CharField(max_length=255, blank=True)
    description = models.TextField(null=True, blank=True)
    category = models.ForeignKey('Category', null=True, on_delete=models.CASCADE)
    tags = models.ManyToManyField('Tag', blank=True)
    def __str__(self):
        return self.name

class ListItem(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)
    item = models.ForeignKey('Item', on_delete=models.CASCADE)
    need = models.BooleanField(default=True)
    done = models.BooleanField(default=False)
    in_list = models.ForeignKey('List', on_delete=models.CASCADE)

    def __str__(self):
        return self.item.name

class Tag(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)
    name = models.CharField(max_length=255)


    def __str__(self):
        return self.name

class Category(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)
    name = models.CharField(max_length=255)
    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

class List(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)
    name = models.CharField(max_length=255)
    items = models.ManyToManyField('ListItem')
    initial_tags = models.ManyToManyField('Tag', blank=True)
    def __str__(self):
        return self.name


