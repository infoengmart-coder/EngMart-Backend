"""
Diagnose the SendGrid setup and optionally send one real test email.

    python manage.py check_email                    # config + connection only
    python manage.py check_email --to you@mail.com  # also delivers a test message
"""
from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Check the SendGrid/SMTP email configuration and optionally send a test email.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--to',
            help='Send a real test email to this address. Omit to only check config + connection.',
        )

    def handle(self, *args, **options):
        ok = self.style.SUCCESS
        warn = self.style.WARNING
        bad = self.style.ERROR

        self.stdout.write('\n=== 1. Configuration ===')
        backend = settings.EMAIL_BACKEND.rsplit('.', 1)[-1]
        using_smtp = 'smtp' in settings.EMAIL_BACKEND.lower()

        self.stdout.write(f'  Backend            : {backend}')
        if not using_smtp:
            self.stdout.write(warn(
                '  SENDGRID_API_KEY is empty, so emails print to the console '
                'instead of being delivered.'
            ))
        self.stdout.write(f'  From (sender)      : {settings.DEFAULT_FROM_EMAIL}')
        self.stdout.write(f'  Reply-To           : {settings.REPLY_TO_EMAIL}')
        self.stdout.write(f'  Sales notifications: {settings.SALES_NOTIFICATION_EMAIL}')

        sender_domain = settings.DEFAULT_FROM_EMAIL.rsplit('@', 1)[-1].lower()
        free_providers = {
            'gmail.com', 'googlemail.com', 'yahoo.com', 'outlook.com',
            'hotmail.com', 'live.com', 'aol.com',
        }
        if sender_domain in free_providers:
            self.stdout.write(warn(
                f'\n  WARNING: the From address uses {sender_domain}, a free mail provider.\n'
                '  You cannot add SendGrid to that domain\'s SPF record, so these messages\n'
                '  fail SPF/DKIM alignment and are likely to be spam-foldered or rejected.\n'
                '  Use an address on a domain you control (e.g. @eng-mart.com) as the From,\n'
                '  and keep the free address as Reply-To.'
            ))
        else:
            self.stdout.write(ok(f'  Sender domain "{sender_domain}" is not a free provider — good.'))

        if not using_smtp:
            self.stdout.write('\nSet SENDGRID_API_KEY in .env to test real delivery.')
            return

        self.stdout.write('\n=== 2. SMTP connection ===')
        self.stdout.write(f'  Host: {settings.EMAIL_HOST}:{settings.EMAIL_PORT} (TLS={settings.EMAIL_USE_TLS})')
        try:
            connection = get_connection(fail_silently=False)
            connection.open()
            connection.close()
            self.stdout.write(ok('  Connected and authenticated successfully.'))
        except Exception as exc:
            self.stdout.write(bad(f'  FAILED: {type(exc).__name__}: {exc}'))
            self.stdout.write(
                '  A 535 error means the API key is wrong or lacks the "Mail Send" scope.'
            )
            return

        recipient = options.get('to')
        if not recipient:
            self.stdout.write(
                '\nConfig and connection are fine. No email was sent.\n'
                'Run with --to your@email.com to deliver a real test message.'
            )
            return

        self.stdout.write(f'\n=== 3. Sending a real test email to {recipient} ===')
        try:
            message = EmailMultiAlternatives(
                subject='Eng-Mart — SendGrid test',
                body=(
                    'This is a test message from the Eng-Mart website.\n\n'
                    f'From:     {settings.DEFAULT_FROM_EMAIL}\n'
                    f'Reply-To: {settings.REPLY_TO_EMAIL}\n\n'
                    'If you received this, transactional email is working.\n'
                    'Check whether it landed in Inbox or Spam — Spam usually means the\n'
                    'sending domain still needs authentication in SendGrid.'
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[recipient],
                reply_to=[settings.REPLY_TO_EMAIL] if settings.REPLY_TO_EMAIL else None,
            )
            message.send(fail_silently=False)
            self.stdout.write(ok('  Accepted by SendGrid. Check the inbox (and the spam folder).'))
        except Exception as exc:
            text = str(exc)
            self.stdout.write(bad(f'  FAILED: {type(exc).__name__}: {text}'))
            if 'does not match a verified Sender Identity' in text or '403' in text:
                self.stdout.write(warn(
                    f'\n  SendGrid is rejecting "{settings.DEFAULT_FROM_EMAIL}" as an\n'
                    '  unverified sender. Fix it in the SendGrid dashboard:\n'
                    '    Settings > Sender Authentication > either\n'
                    '      - Authenticate Your Domain (recommended, needs DNS access), or\n'
                    '      - Verify a Single Sender (quick, but weaker deliverability)'
                ))
