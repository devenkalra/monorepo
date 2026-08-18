from django.core.management.base import BaseCommand

from audio_library.indexer import index_roots
from audio_library.roots import configured_roots


class Command(BaseCommand):
    help = 'Scan configured AUDIO_LIBRARY_ROOTS and refresh the track catalog.'

    def handle(self, *args, **options):
        roots = configured_roots()
        if not roots:
            self.stdout.write(self.style.WARNING('No AUDIO_LIBRARY_ROOTS configured.'))
            return
        for row in roots:
            self.stdout.write(f"  {row['slug']}: {row['path']}")
        counts = index_roots(roots)
        self.stdout.write(self.style.SUCCESS(
            f"Indexed {counts['scanned']} files "
            f"{counts['upserted']} updated, {counts.get('covers', 0)} covers, "
            f"{counts['removed']} removed, {counts['missing_roots']} missing roots)."
        ))
