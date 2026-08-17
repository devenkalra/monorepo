from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from trips.seed_death_valley import create_death_valley_trip


class Command(BaseCommand):
    help = 'Create the Sierra & Death Valley 2026 trip for a user if it is missing.'

    def add_arguments(self, parser):
        parser.add_argument('--email', required=True)

    def handle(self, *args, **options):
        User = get_user_model()
        email = options['email']
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist as exc:
            raise CommandError(f'No user with email {email}') from exc
        trip, created = create_death_valley_trip(user)
        verb = 'Created' if created else 'Already exists'
        self.stdout.write(self.style.SUCCESS(f'{verb}: {trip.title} (id={trip.id}) for {user.email}'))
