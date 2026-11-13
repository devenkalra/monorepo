import io
import sys

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from trips.transfer import TransferError, import_payload, read_bundle


class Command(BaseCommand):
    help = (
        'Import a trip export (.zip with files, or .json) and assign every row to one user. '
        'Primary keys are remapped so existing production rows are not overwritten.'
    )

    def add_arguments(self, parser):
        parser.add_argument('fixture', help='Path to trip export .zip/.json (use - for stdin)')
        parser.add_argument('--email', required=True, help='Production owner email')
        parser.add_argument(
            '--replace',
            action='store_true',
            help="Delete this user's existing trips before import",
        )

    def handle(self, *args, **options):
        User = get_user_model()
        email = options['email']
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist as exc:
            raise CommandError(f'No user with email {email}') from exc

        path = options['fixture']
        try:
            if path == '-':
                payload, load_file = read_bundle(io.BytesIO(sys.stdin.buffer.read()))
            else:
                with open(path, 'rb') as fh:
                    payload, load_file = read_bundle(fh)
            if isinstance(payload, list):
                raise TransferError('Fixture must be an object with a "trips" list')
            if options['replace']:
                self.stdout.write(f'Removing existing trips for {user.email}')
            _, counts = import_payload(user, payload, load_file, replace=options['replace'])
        except TransferError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(
            f'Imported for {user.email}: '
            f'{counts["trips"]} trips, {counts["lodgings"]} lodgings, '
            f'{counts["days"]} days, {counts["stops"]} stops, '
            f'{counts["attachments"]} attachments, {counts["media"]} media, {counts["files"]} files'
        ))
