"""
A Redis cache backend that is never allowed to take the site down.

Django's stock RedisCache lets connection errors propagate. That is the wrong
trade for us: this cache holds public catalog responses that can always be
rebuilt from Postgres, so an Upstash outage, a network blip, or an exhausted
free-tier command quota should make pages *slower*, not return HTTP 500.

Every read degrades to "miss" and every write degrades to a no-op. Failures are
logged at WARNING so an outage shows up in the logs instead of passing silently.

Kept in its own module rather than alongside the caching mixins in cache.py:
Django imports the backend class while wiring up the cache framework, and that
module imports ``django.core.cache`` at module level.
"""

import logging

from django.core.cache.backends.redis import RedisCache

logger = logging.getLogger(__name__)

# redis-py raises its own exception tree. Import defensively so a missing or
# renamed dependency cannot itself become the outage.
try:
    from redis.exceptions import RedisError
    _REDIS_ERRORS: tuple = (RedisError, OSError)
except Exception:  # pragma: no cover - only if redis is not installed
    _REDIS_ERRORS = (OSError,)


class ResilientRedisCache(RedisCache):
    """RedisCache that falls back to cache-miss behaviour when Redis is down."""

    def _safe(self, operation, func, fallback, *args, **kwargs):
        try:
            return func(*args, **kwargs)
        except _REDIS_ERRORS as exc:
            # warning, not error: the request still succeeds, just uncached.
            logger.warning('Cache %s failed, serving uncached: %s', operation, exc)
            return fallback

    def get(self, key, default=None, version=None):
        return self._safe('get', super().get, default, key, default, version)

    def set(self, key, value, timeout=..., version=None):
        return self._safe('set', super().set, None, key, value, timeout, version)

    def add(self, key, value, timeout=..., version=None):
        # False == "not added", which callers already handle.
        return self._safe('add', super().add, False, key, value, timeout, version)

    def delete(self, key, version=None):
        return self._safe('delete', super().delete, False, key, version)

    def get_many(self, keys, version=None):
        return self._safe('get_many', super().get_many, {}, keys, version)

    def set_many(self, data, timeout=..., version=None):
        # On failure report every key as unset, which is the truth.
        return self._safe('set_many', super().set_many, list(data), data, timeout, version)

    def delete_many(self, keys, version=None):
        return self._safe('delete_many', super().delete_many, None, keys, version)

    def incr(self, key, delta=1, version=None):
        # Drives the catalog cache-version counter. If this fails the old
        # payload survives until its TTL expires - acceptable, and far better
        # than a 500 when an admin saves a product.
        return self._safe('incr', super().incr, None, key, delta, version)

    def has_key(self, key, version=None):
        return self._safe('has_key', super().has_key, False, key, version)

    def clear(self):
        return self._safe('clear', super().clear, None)
