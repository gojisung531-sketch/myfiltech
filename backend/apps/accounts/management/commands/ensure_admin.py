from django.core.management.base import BaseCommand

from apps.accounts.services import DEFAULT_ADMIN_USERNAME, ensure_default_admin


class Command(BaseCommand):
    help = "Create the default admin account (admin / admin1234!) if no ADMIN user exists."

    def handle(self, *args, **options):
        if ensure_default_admin():
            self.stdout.write(
                self.style.SUCCESS(f"Default admin '{DEFAULT_ADMIN_USERNAME}' created.")
            )
        else:
            self.stdout.write("An ADMIN user already exists (or username is taken); no change.")
