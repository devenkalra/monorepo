from rest_framework import viewsets, filters
from .serializers import ListItemSerializer, ListSerializer, CategorySerializer, ItemSerializer, TagSerializer
from .models import ListItem, List, Category, Item, Tag
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.decorators import action

class ListItemViewSet(viewsets.ModelViewSet):
    def get_queryset(self):
        in_list = self.request.query_params.get('in_list', None)
        queryset = ListItem.objects.all()
        if in_list is not None:
            queryset = ListItem.objects.filter(in_list__id=in_list)
        return queryset

    @action(detail=False, methods=['patch'])
    def bulk_update(self, request):
        ids = request.data.get('ids', [])
        data = request.data.get('data', {})
        if not ids:
            return Response(
                {"error": "No IDs provided"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Filter the items and delete them in one database query
        queryset = self.get_queryset().filter(id__in=ids)
        if "need" in data:
            updated_count = queryset.update(need=data["need"])
        elif "done" in data:
            updated_count = queryset.update(done=data["done"])
        else:
            raise Exception("Need or Done not provided")

        return Response(
            {"message": f"Successfully deleted {updated_count} items."},
            status=status.HTTP_204_NO_CONTENT
        )

    queryset = ListItem.objects.all()
    serializer_class = ListItemSerializer

class ListViewSet(viewsets.ModelViewSet):
    def get_queryset(self):

        in_list = self.request.query_params.get('in_list', None)
        queryset = List.objects.all()
        return queryset

    queryset = List.objects.all()
    serializer_class = ListSerializer

class CategoryViewSet(viewsets.ModelViewSet):
    def get_queryset(self):

        queryset = Category.objects.all()
        return queryset

    queryset = Category.objects.all()
    serializer_class = CategorySerializer


class TagViewSet(viewsets.ModelViewSet):
    def get_queryset(self):
        queryset = Tag.objects.all()
        return queryset

    queryset = Tag.objects.all()
    serializer_class = TagSerializer

class ItemViewSet(viewsets.ModelViewSet):
    def get_queryset(self):

        queryset = Item.objects.all()
        return queryset

    # This creates a new endpoint: /api/travel-items/bulk_delete/
    @action(detail=False, methods=['delete'])
    def bulk_delete(self, request):
        ids = request.data.get('ids', [])

        if not ids:
            return Response(
                {"error": "No IDs provided"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Filter the items and delete them in one database query
        queryset = self.get_queryset().filter(id__in=ids)
        deleted_count, _ = queryset.delete()

        return Response(
            {"message": f"Successfully deleted {deleted_count} items."},
            status=status.HTTP_204_NO_CONTENT
        )

    queryset = Item.objects.all()
    serializer_class = ItemSerializer

# listmanager/views.py
from rest_framework import generics, status, views
from rest_framework.response import Response
from django.db.models import Q
from .models import ListItem, List, Item, Tag, Category
from .serializers import (
    ListItemSerializer, ListSerializer, TagSerializer, CategorySerializer
)

class ListItemsForListView(generics.ListAPIView):
    serializer_class = ListItemSerializer

    def get_queryset(self):
        list_id = self.kwargs["list_id"]
        qs = ListItem.objects.select_related("item", "in_list", "item__category").prefetch_related("item__tags")
        qs = qs.filter(in_list_id=list_id)

        text = self.request.query_params.get("q")
        category_id = self.request.query_params.get("category")
        need = self.request.query_params.get("need")
        done = self.request.query_params.get("done")
        tags = self.request.query_params.getlist("tags")  # ?tags=1&tags=2

        if text:
            qs = qs.filter(
                Q(item__name__icontains=text) |
                Q(item__description__icontains=text)
            )

        if category_id:
            qs = qs.filter(item__category_id=category_id)

        if need in ["true", "false"]:
            qs = qs.filter(need=(need == "true"))

        if done in ["true", "false"]:
            qs = qs.filter(done=(done == "true"))

        if tags:
            qs = qs.filter(item__tags__id__in=tags).distinct()

        return qs

class ListItemBulkActionView(views.APIView):
    """
    POST body:
    {
      "ids": [1,2,3],
      "action": "mark_as_done" | "mark_as_not_done" | "mark_as_needed" |
                "mark_as_not_needed" | "remove_from_list"
    }
    """

    def post(self, request, *args, **kwargs):
        ids = request.data.get("ids", [])
        action = request.data.get("action")

        qs = ListItem.objects.filter(id__in=ids)

        if action == "mark_as_done":
            qs.update(done=True)
        elif action == "mark_as_not_done":
            qs.update(done=False)
        elif action == "mark_as_needed":
            qs.update(need=True)
        elif action == "mark_as_not_needed":
            qs.update(need=False)
        elif action == "remove_from_list":
            qs.delete()
        else:
            return Response({"detail": "Invalid action"}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"detail": "OK"})

class CategoryCreateView(generics.CreateAPIView):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer

class TagCreateView(generics.CreateAPIView):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer

class ListCreateWithItemsView(views.APIView):
    """
    POST body:
    {
      "name": "Weekend Groceries",
      "item_ids": [10, 12, 15],
      "initial_tag_ids": [1, 2]
    }
    """

    def post(self, request, *args, **kwargs):
        name = request.data.get("name")
        item_ids = request.data.get("item_ids", [])
        initial_tags = request.data.get("initial_tag_ids", [])

        if not name:
            return Response({"detail": "Name is required"}, status=400)

        list_obj = List.objects.create(name=name)
        if initial_tags:
            list_obj.initial_tags.set(initial_tags)

        items = Item.objects.filter(id__in=item_ids)
        list_items = []
        for item in items:
            li = ListItem(item=item, in_list=list_obj)
            list_items.append(li)
        ListItem.objects.bulk_create(list_items)

        return Response(ListSerializer(list_obj).data, status=201)

