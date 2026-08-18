from django.core.management.base import BaseCommand

from audio_library.indexer import index_roots
from audio_library.roots import configured_roots


class Command(BaseCommand):
    help = 'Scan configured AUDIO_LIBRARY_ROOTS and refresh the track catalog.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--missing',
            action='store_true',
            help='Only add files that are not already in the catalog. Skip tag refresh and deletions.',
        )
        parser.add_argument(
            '--folder',
            default='',
            help='Limit to one folder under a root (e.g. Indian). Reindexes existing files in that folder.',
        )

    def handle(self, *args, **options):
        roots = configured_roots()
        if not roots:
            self.stdout.write(self.style.WARNING('No AUDIO_LIBRARY_ROOTS configured.'))
            return
        for row in roots:
            self.stdout.write(f"  {row['slug']}: {row['path']}")
        counts = index_roots(roots, missing_only=options['missing'], folder=options['folder'] or None)
        self.stdout.write(self.style.SUCCESS(
            f"Indexed {counts['scanned']} files "
            f"({counts['upserted']} updated, {counts.get('skipped', 0)} skipped, "
            f"{counts.get('covers', 0)} covers, "
            f"{counts['removed']} removed, {counts['missing_roots']} missing roots)."
        ))
