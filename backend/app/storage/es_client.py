from elasticsearch import AsyncElasticsearch

from app.config import get_settings

_client: AsyncElasticsearch | None = None


def get_es() -> AsyncElasticsearch:
    global _client
    if _client is None:
        settings = get_settings()
        _client = AsyncElasticsearch(
            hosts=[settings.es_url],
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
