from django.apps import AppConfig

class FileCatalogConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'file_catalog'

    def ready(self):
        import file_catalog.signals