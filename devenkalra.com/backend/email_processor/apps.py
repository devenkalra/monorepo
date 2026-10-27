from django.apps import AppConfig


class EmailProcessorConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'email_processor'
    verbose_name = 'Email Processor'

    def ready(self):
        # Start background job loop once per process when enabled.
        from django.conf import settings
        if getattr(settings, 'EMAIL_WORKER_ENABLED', True):
            from .worker import start_worker_thread
            start_worker_thread()
