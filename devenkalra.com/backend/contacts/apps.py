from django.apps import AppConfig


class ContactsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'contacts'
    verbose_name = 'Contacts sync'

    def ready(self):
        from django.conf import settings
        if getattr(settings, 'CONTACTS_WORKER_ENABLED', True):
            from .worker import start_worker_thread
            start_worker_thread()
