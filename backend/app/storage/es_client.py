import socket

from elasticsearch import AsyncElasticsearch

from app.config import get_settings

_client: AsyncElasticsearch | None = None


def _resolve_es_hosts(url: str) -> str:
    """Resolve hostname to IP, falling back to original URL on failure.

    Works around aiohttp async DNS resolver instability with Docker
    Desktop's embedded DNS server (127.0.0.11).
    """
    try:
        from urllib.parse import urlparse, urlunparse

        parsed = urlparse(url)
        ip = socket.gethostbyname(parsed.hostname)
        resolved = parsed._replace(netloc=f"{ip}:{parsed.port or 9200}")
        return urlunparse(resolved)
    except Exception:
        return url


def get_es() -> AsyncElasticsearch:
    global _client
    if _client is None:
        settings = get_settings()
        resolved_url = _resolve_es_hosts(settings.es_url)
        _client = AsyncElasticsearch(
            hosts=[resolved_url],
            request_timeout=30,
            max_retries=3,
            retry_on_timeout=True,
        )
    return _client


async def close_es() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None
