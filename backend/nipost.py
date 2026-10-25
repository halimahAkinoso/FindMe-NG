import httpx


LOOKUP_LEVEL = 1


async def request_lookup(*, base_url: str, postcode: str, api_key: str):
    """Look up a postcode using the documented NIPOST API contract."""
    url = f"{base_url.rstrip('/')}/v1/lookup"
    async with httpx.AsyncClient(timeout=10.0) as client:
        return await client.get(
            url,
            params={"code": postcode, "level": LOOKUP_LEVEL},
            headers={
                "X-API-Key": api_key,
                "Accept": "application/json",
            },
        )
