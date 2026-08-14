"""
Link orphaned orders to the customer account with the same email address.

Why this exists: checkout is open to guests, so an order can legitimately have
no account attached. But orders placed by a signed-in customer *before* the
frontend started sending its auth token were also saved anonymously, so they
never appeared under "My Orders" or in the account totals.

    python manage.py link_orders                 # dry run — shows what it would do
    python manage.py link_orders --apply         # actually link
    python manage.py link_orders --email a@b.com --apply   # one customer only

SECURITY NOTE — read before using this in production.

Normal account queries deliberately match on the `Order.user` foreign key and
NEVER on `customer_email`, because an email typed at checkout is self-asserted:
matching on it at request time would let anyone read another customer's orders
by typing their address. This command is the one deliberate exception, and it is
safe only because:

  * it is run by an administrator on the server, not triggered by a request;
  * it matches the *account* email, which is unique at registration and is not
    self-editable through the API;
  * it never overwrites an order that already has a user.

Keep it manual. Do not wire it into a signal or a view.
"""
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db.models import Count

from apps.orders.models import Order


class Command(BaseCommand):
    help = 'Attach orders with no account to the user holding the same email'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='Actually write the links (default is a dry run)')
        parser.add_argument('--email', type=str, default='',
                            help='Limit to a single email address')

    def handle(self, *args, **options):
        apply_changes = options['apply']
        only_email = options['email'].strip().lower()

        orphans = Order.objects.filter(user__isnull=True).exclude(customer_email='')
        if only_email:
            orphans = orphans.filter(customer_email__iexact=only_email)

        if not orphans.exists():
            self.stdout.write('No orphaned orders found — nothing to do.')
            return

        # Emails shared by more than one account are ambiguous: we cannot know
        # which account the buyer meant, so we refuse rather than guess.
        dupes = {
            row['email'].lower()
            for row in User.objects.values('email')
                                   .annotate(n=Count('id'))
                                   .filter(n__gt=1)
            if row['email']
        }

        linked = skipped_no_account = skipped_ambiguous = 0
        for order in orphans.order_by('created_at'):
            email = (order.customer_email or '').strip().lower()
            if email in dupes:
                self.stdout.write(self.style.WARNING(
                    f'  ambiguous  {order.order_number}  {email} — '
                    f'several accounts share this email, skipped'))
                skipped_ambiguous += 1
                continue

            user = User.objects.filter(email__iexact=email).first()
            if not user:
                skipped_no_account += 1
                continue

            self.stdout.write(
                f'  link       {order.order_number}  {email} -> {user.username}')
            if apply_changes:
                order.user = user
                order.save(update_fields=['user', 'updated_at'])
            linked += 1

        self.stdout.write('')
        self.stdout.write(f'  linked                : {linked}')
        self.stdout.write(f'  no matching account   : {skipped_no_account} (genuine guest orders)')
        self.stdout.write(f'  ambiguous email       : {skipped_ambiguous}')

        if not apply_changes:
            self.stdout.write(self.style.WARNING(
                '\nDRY RUN — nothing was written. Re-run with --apply.'))
        else:
            self.stdout.write(self.style.SUCCESS('\nDone.'))
