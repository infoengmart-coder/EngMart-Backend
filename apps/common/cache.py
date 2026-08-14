"""
Response caching for the public catalog.

The database is in another region, so even a well-optimised query costs a
couple of hundred milliseconds of round-trip. Catalog data changes rarely, so
public GETs are cached in memory and served instantly on repeat views.

Invalidation is version-based: every write bumps a counter that is part of the
cache key, so all previously cached catalog responses become unreachable at
once. No key bookkeeping, no stale data after an admin edit.
"""
from django.core.cache import cache

CATALOG_VERSION_KEY = 'catalog:version'
DEFAULT_TIMEOUT = 300  # seconds


def get_catalog_version():
    """Current catalog version, created on first use."""
    version = cache.get(CATALOG_VERSION_KEY)
    if version is None:
        version = 1
        cache.set(CATALOG_VERSION_KEY, version, None)  # never expires
    return version


def bump_catalog_version():
    """Invalidate every cached catalog response."""
    try:
        return cache.incr(CATALOG_VERSION_KEY)
    except ValueError:
        # Key missing (e.g. cache was cleared) — start a fresh generation.
        cache.set(CATALOG_VERSION_KEY, 2, None)
        return 2


class CachedListMixin:
    """
    Cache the rendered response of a public list/detail GET.

    Only anonymous, unfiltered-by-auth GETs are cached — staff requests can see
    inactive rows via ?all=true, so caching those would risk leaking drafts to
    the public. Any non-GET method bumps the version instead.
    """
    cache_timeout = DEFAULT_TIMEOUT

    def _cache_key(self, request):
        version = get_catalog_version()
        query = request.GET.urlencode()
        return f'catalog:v{version}:{request.path}?{query}'

    def _is_cacheable(self, request):
        if request.method != 'GET':
            return False
        user = getattr(request, 'user', None)
        # Staff responses can contain inactive rows — never cache those.
        return not (user and user.is_authenticated and user.is_staff)

    def list(self, request, *args, **kwargs):
        if not self._is_cacheable(request):
            response = super().list(request, *args, **kwargs)
            response['X-Cache'] = 'BYPASS'
            return response

        key = self._cache_key(request)
        cached = cache.get(key)
        if cached is not None:
            from rest_framework.response import Response
            response = Response(cached)
            response['X-Cache'] = 'HIT'
            return response

        response = super().list(request, *args, **kwargs)
        cache.set(key, response.data, self.cache_timeout)
        response['X-Cache'] = 'MISS'
        return response


class CachedRetrieveMixin(CachedListMixin):
    """
    Same caching for single-object GETs (product / brand / category detail).

    Detail pages are the most-visited pages on a storefront and each one costs
    several queries against a remote database, so they benefit most.
    """

    def retrieve(self, request, *args, **kwargs):
        if not self._is_cacheable(request):
            return super().retrieve(request, *args, **kwargs)

        key = self._cache_key(request)
        cached = cache.get(key)
        if cached is not None:
            from rest_framework.response import Response
            response = Response(cached)
            response['X-Cache'] = 'HIT'
            return response

        response = super().retrieve(request, *args, **kwargs)
        if response.status_code == 200:
            cache.set(key, response.data, self.cache_timeout)
        response['X-Cache'] = 'MISS'
        return response


class InvalidatesCatalogMixin:
    """Bump the catalog version after any successful write."""

    def perform_create(self, serializer):
        super().perform_create(serializer)
        bump_catalog_version()

    def perform_update(self, serializer):
        super().perform_update(serializer)
        bump_catalog_version()

    def perform_destroy(self, instance):
        super().perform_destroy(instance)
        bump_catalog_version()
