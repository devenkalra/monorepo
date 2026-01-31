"""
Management command to set up Google OAuth
"""
from django.core.management.base import BaseCommand
from django.contrib.sites.models import Site
from allauth.socialaccount.models import SocialApp
from allauth.socialaccount.providers.google.provider import GoogleProvider


class Command(BaseCommand):
    help = 'Set up Google OAuth configuration'

    def add_arguments(self, parser):
        parser.add_argument(
            '--client-id',
            type=str,
            help='Google OAuth Client ID',
        )
        parser.add_argument(
            '--client-secret',
            type=str,
            help='Google OAuth Client Secret',
        )
        parser.add_argument(
            '--domain',
            type=str,
            default='localhost:8001',
            help='Domain name for the site (default: localhost:8001)',
        )

    def handle(self, *args, **options):
        client_id = options.get('client_id')
        client_secret = options.get('client_secret')
        domain = options.get('domain')

        self.stdout.write(self.style.WARNING('\n' + '='*70))
        self.stdout.write(self.style.WARNING('  Google OAuth Setup'))
        self.stdout.write(self.style.WARNING('='*70 + '\n'))

        # Update or create the Site
        site, created = Site.objects.get_or_create(
            pk=1,
            defaults={
                'domain': domain,
                'name': domain
            }
        )
        
        if not created and (site.domain != domain or site.name != domain):
            site.domain = domain
            site.name = domain
            site.save()
            self.stdout.write(self.style.SUCCESS(f'✓ Updated site to: {domain}'))
        else:
            self.stdout.write(self.style.SUCCESS(f'✓ Site configured: {domain}'))

        # Check if we have credentials
        if not client_id or not client_secret:
            self.stdout.write(self.style.WARNING('\n⚠️  No credentials provided.'))
            self.stdout.write('\nTo complete setup, you need to:')
            self.stdout.write('1. Get Google OAuth credentials from:')
            self.stdout.write('   https://console.cloud.google.com/')
            self.stdout.write('\n2. Run this command with credentials:')
            self.stdout.write(self.style.SUCCESS(
                '   python manage.py setup_google_oauth \\'
            ))
            self.stdout.write(self.style.SUCCESS(
                '     --client-id="YOUR_CLIENT_ID" \\'
            ))
            self.stdout.write(self.style.SUCCESS(
                '     --client-secret="YOUR_CLIENT_SECRET"'
            ))
            self.stdout.write('\nOR configure via Django Admin:')
            self.stdout.write('   http://localhost:8001/admin/socialaccount/socialapp/')
            self.stdout.write('\n' + '='*70 + '\n')
            return

        # Create or update Google OAuth app
        try:
            social_app = SocialApp.objects.get(provider=GoogleProvider.id)
            social_app.name = 'Google OAuth'
            social_app.client_id = client_id
            social_app.secret = client_secret
            social_app.save()
            self.stdout.write(self.style.SUCCESS('✓ Updated existing Google OAuth app'))
        except SocialApp.DoesNotExist:
            social_app = SocialApp.objects.create(
                provider=GoogleProvider.id,
                name='Google OAuth',
                client_id=client_id,
                secret=client_secret,
            )
            self.stdout.write(self.style.SUCCESS('✓ Created new Google OAuth app'))

        # Associate with site
        if site not in social_app.sites.all():
            social_app.sites.add(site)
            self.stdout.write(self.style.SUCCESS(f'✓ Associated with site: {domain}'))

        self.stdout.write(self.style.SUCCESS('\n✅ Google OAuth setup complete!'))
        self.stdout.write('\nNext steps:')
        self.stdout.write('1. Ensure these redirect URIs are in Google Console:')
        self.stdout.write(f'   - http://localhost:3000/auth/google/callback')
        self.stdout.write(f'   - http://{domain}/accounts/google/login/callback/')
        self.stdout.write('\n2. Start the servers:')
        self.stdout.write('   Backend:  python manage.py runserver 8001')
        self.stdout.write('   Frontend: cd frontend && npm run dev')
        self.stdout.write('\n3. Test at: http://localhost:3000/login')
        self.stdout.write('\n' + '='*70 + '\n')
