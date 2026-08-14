"""
Pre-deployment readiness check.

Runs Django's own --deploy checks plus the things that have actually bitten
this project: a Windows junction in media/, a dev secret key, missing Redis,
localhost left in CORS, and product images that do not exist on disk.

    python manage.py check_deploy
"""
import os

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Check whether this environment is safe to deploy'

    def handle(self, *args, **options):
        problems, warnings, passes = [], [], []

        def check(ok, label, fix, hard=True):
            if ok:
                passes.append(label)
            elif hard:
                problems.append((label, fix))
            else:
                warnings.append((label, fix))

        # ── DEBUG ────────────────────────────────────────────────
        check(not settings.DEBUG, 'DEBUG is False',
              'Set DEBUG=False. Leaving it True exposes tracebacks, settings and SQL.')

        # ── Secret key ───────────────────────────────────────────
        key = settings.SECRET_KEY
        check(not key.startswith('dev-insecure') and len(key) >= 50,
              'SECRET_KEY is strong',
              'Generate one: python -c "from django.core.management.utils '
              'import get_random_secret_key; print(get_random_secret_key())"')

        # ── Cache ────────────────────────────────────────────────
        backend = settings.CACHES['default']['BACKEND']
        check('redis' in backend.lower(), 'Cache is Redis (shared by all workers)',
              'Set REDIS_URL. With LocMemCache each Gunicorn worker keeps its own '
              'copy, so admin edits appear not to save.',
              hard=not settings.DEBUG)

        # ── CORS / hosts ─────────────────────────────────────────
        origins = getattr(settings, 'CORS_ALLOWED_ORIGINS', [])
        check(not any('localhost' in o or '127.0.0.1' in o for o in origins),
              'CORS has no localhost origins',
              f'Remove localhost from CORS_ORIGINS (currently {origins}).',
              hard=not settings.DEBUG)
        check(not any(h in ('localhost', '127.0.0.1') for h in settings.ALLOWED_HOSTS),
              'ALLOWED_HOSTS is production-only',
              f'Set ALLOWED_HOSTS to the real domain (currently {settings.ALLOWED_HOSTS}).',
              hard=not settings.DEBUG)

        # ── Media: junctions/symlinks do not survive Linux ───────
        media_root = str(settings.MEDIA_ROOT)
        links = []
        if os.path.isdir(media_root):
            for name in os.listdir(media_root):
                path = os.path.join(media_root, name)
                # A Windows junction reports as a link via islink() on py3.8+,
                # and st_nlink/reparse points are messier — islink covers it.
                if os.path.islink(path):
                    links.append(name)
        check(not links, 'media/ contains no symlinks or junctions',
              f'media/{", ".join(links)} is a link. Junctions do not exist on '
              f'Linux — every file under it will 404. Copy the real files in, or '
              f'move media to object storage.')

        # ── Email ────────────────────────────────────────────────
        check(bool(getattr(settings, 'SENDGRID_API_KEY', '')),
              'Email is configured (SendGrid)',
              'Set SENDGRID_API_KEY, or transactional email silently prints to '
              'the console instead of being delivered.',
              hard=not settings.DEBUG)

        # ── Product images actually on disk ──────────────────────
        from apps.products.models import Product
        missing = 0
        qs = Product.objects.exclude(image='').exclude(image__isnull=True).only('image')
        for product in qs[:500]:
            if not os.path.exists(os.path.join(media_root, str(product.image))):
                missing += 1
        check(missing == 0, 'Product image files exist on disk',
              f'{missing} of the first 500 product images are missing from '
              f'{media_root}.')

        # ── Report ───────────────────────────────────────────────
        for label in passes:
            self.stdout.write(self.style.SUCCESS(f'  PASS  {label}'))
        for label, fix in warnings:
            self.stdout.write(self.style.WARNING(f'  WARN  {label}'))
            self.stdout.write(f'        -> {fix}')
        for label, fix in problems:
            self.stdout.write(self.style.ERROR(f'  FAIL  {label}'))
            self.stdout.write(f'        -> {fix}')

        self.stdout.write('')
        if problems:
            self.stdout.write(self.style.ERROR(
                f'{len(problems)} blocker(s) — not safe to deploy yet.'))
        elif warnings:
            self.stdout.write(self.style.WARNING(
                f'{len(warnings)} warning(s) — review before going live.'))
        else:
            self.stdout.write(self.style.SUCCESS('Ready to deploy.'))
        self.stdout.write(
            '\nAlso run:  python manage.py check --deploy\n'
            'And confirm DNS has ONE SPF record (two = both fail).')
