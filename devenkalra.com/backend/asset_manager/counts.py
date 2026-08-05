"""Recursive container / item counts for AssetArea trees."""

from collections import defaultdict

from django.db.models import Count

from .models import AssetArea, AssetItem


def compute_area_descendant_counts():
    """
    Return {area_id: {'containers': int, 'items': int}} for every area.

    containers = number of nested areas under this area (not including self)
    items = items in this area plus all nested areas
    """
    areas = list(AssetArea.objects.values_list('id', 'parent_area_id'))
    direct_items = {
        area_id: n
        for area_id, n in (
            AssetItem.objects
            .exclude(area_id__isnull=True)
            .values('area_id')
            .annotate(n=Count('id'))
            .values_list('area_id', 'n')
        )
    }

    children = defaultdict(list)
    for area_id, parent_id in areas:
        children[parent_id].append(area_id)

    memo = {}

    def walk(area_id):
        if area_id in memo:
            return memo[area_id]
        containers = 0
        items = direct_items.get(area_id, 0)
        for child_id in children.get(area_id, []):
            child_containers, child_items = walk(child_id)
            containers += 1 + child_containers
            items += child_items
        memo[area_id] = (containers, items)
        return memo[area_id]

    for area_id, _parent in areas:
        walk(area_id)

    return {
        area_id: {'containers': c, 'items': i}
        for area_id, (c, i) in memo.items()
    }


def inventory_summary():
    counts = compute_area_descendant_counts()
    return {
        'container_count': AssetArea.objects.count(),
        'item_count': AssetItem.objects.count(),
        'unlocated_item_count': AssetItem.objects.filter(area__isnull=True).count(),
        'area_counts': counts,
    }
