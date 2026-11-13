import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from trips.models import Trip
from trips.transfer import FORMAT_VERSION, export_trip, export_zip


class Command(BaseCommand):
    help = (
        'Dump trips owned by one user for import_trip_fixture. '
        'Write to a .zip path to include uploaded files (documents, pictures).'
    )

    def add_arguments(self, parser):
        parser.add_argument('--email', required=True, help='Owner email to dump')
        parser.add_argument('-o', '--output', default='-', help='Output path (.json or .zip), or - for stdout')
        parser.add_argument('--trip', type=int, action='append', help='Only this trip id (repeatable)')

    def handle(self, *args, **options):
        User = get_user_model()
        email = options['email']
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist as exc:
            raise CommandError(f'No user with email {email}') from exc

        trips = Trip.objects.filter(user=user).select_related('packing_list', 'gallery')
        if options['trip']:
            trips = trips.filter(pk__in=options['trip'])
        trips = list(trips)

        dest = options['output']
        if dest.lower().endswith('.zip'):
            with open(dest, 'wb') as fh:
                fh.write(export_zip(trips))
        else:
            payload = {'version': FORMAT_VERSION, 'email': user.email, 'trips': [export_trip(t) for t in trips]}
            text = json.dumps(payload, indent=2, default=str)
            if dest in ('', '-'):
                self.stdout.write(text)
                return
            with open(dest, 'w', encoding='utf-8') as fh:
                fh.write(text)
        self.stdout.write(self.style.SUCCESS(f'Wrote {len(trips)} trip(s) for {user.email} to {dest}'))
