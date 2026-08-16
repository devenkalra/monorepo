from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.core.serializers import serialize

from vacation_list.models import VacTag, VacCategory, VacItem, VacList, VacListItem


class Command(BaseCommand):
    help = 'Dump vacation_list rows owned by one user as a Django fixture.'

    def add_arguments(self, parser):
        parser.add_argument('--email', required=True, help='Owner email to dump')
        parser.add_argument('-o', '--output', default='-', help='Output path, or - for stdout')

    def handle(self, *args, **options):
        User = get_user_model()
        email = options['email']
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist as exc:
            raise CommandError(f'No user with email {email}') from exc

        objects = [
            *VacTag.objects.filter(user=user),
            *VacCategory.objects.filter(user=user),
            *VacItem.objects.filter(user=user).prefetch_related('tags'),
            *VacList.objects.filter(user=user).prefetch_related('initial_tags'),
            *VacListItem.objects.filter(user=user),
        ]
        payload = serialize('json', objects, indent=2)
        dest = options['output']
        if dest in ('', '-'):
            self.stdout.write(payload)
        else:
            with open(dest, 'w', encoding='utf-8') as fh:
                fh.write(payload)
            self.stdout.write(self.style.SUCCESS(
                f'Wrote {len(objects)} object(s) for {user.email} to {dest}'
            ))
