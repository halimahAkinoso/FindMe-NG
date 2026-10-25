import asyncio
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import HTTPException
from pydantic import ValidationError

from backend import main, nipost

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


class StubAsyncClient:
    def __init__(self, *, timeout):
        self.timeout = timeout
        self.call = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def get(self, url, *, params, headers):
        self.call = (url, params, headers)
        return httpx.Response(
            200,
            json={"data": {"postcode": "EK-01-A03-FK-01", "valid": True}},
        )


class NipostIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.original_mock_mode = main.NIPOST_MOCK_MODE
        self.original_base_url = main.NIPOST_API_BASE_URL
        self.original_api_key = main.NIPOST_API_KEY
        main.NIPOST_MOCK_MODE = False
        main.NIPOST_API_BASE_URL = "https://api.postcode.gov.ng"
        main.NIPOST_API_KEY = "test-key"

    async def asyncTearDown(self):
        main.NIPOST_MOCK_MODE = self.original_mock_mode
        main.NIPOST_API_BASE_URL = self.original_base_url
        main.NIPOST_API_KEY = self.original_api_key

    async def test_lookup_uses_documented_url_params_and_header(self):
        client = StubAsyncClient(timeout=10.0)
        with patch.object(nipost.httpx, "AsyncClient", return_value=client):
            await nipost.request_lookup(
                base_url="https://api.postcode.gov.ng/",
                postcode="EK01A03FK01",
                api_key="test-key",
            )

        self.assertEqual(
            client.call,
            (
                "https://api.postcode.gov.ng/v1/lookup",
                {"code": "EK01A03FK01", "level": 1},
                {"X-API-Key": "test-key", "Accept": "application/json"},
            ),
        )

    async def test_endpoint_normalizes_and_maps_documented_level_one_data(self):
        request = main.PostcodeRequest(postcode=" ek 01-a03 fk 01 ")
        with patch.object(
            main,
            "request_lookup",
            new=AsyncMock(
                return_value=httpx.Response(
                    200,
                    json={
                        "data": {
                            "postcode": "EK-01-A03-FK-01",
                            "valid": True,
                        }
                    },
                )
            ),
        ) as lookup:
            result = await main.validate_postcode_endpoint(request)

        self.assertEqual(lookup.await_args.kwargs["postcode"], "EK01A03FK01")
        self.assertEqual(result["valid"], True)
        self.assertTrue(result["verified"])
        self.assertEqual(result["postcode"], "EK-01-A03-FK-01")
        self.assertNotIn("raw_response", result)

    async def test_invalid_postcode_is_rejected_before_lookup(self):
        with self.assertRaises(ValidationError):
            main.PostcodeRequest(postcode="EK-00-A03-FK-01")

    async def test_authentication_errors_are_sanitized(self):
        for status in (401, 403):
            with self.subTest(status=status):
                with patch.object(
                    main,
                    "request_lookup",
                    new=AsyncMock(return_value=httpx.Response(status)),
                ):
                    with self.assertRaises(HTTPException) as raised:
                        await main.validate_postcode_endpoint(
                            main.PostcodeRequest(postcode="EK-01-A03-FK-01")
                        )
                self.assertEqual(raised.exception.status_code, 502)
                self.assertNotIn("test-key", raised.exception.detail)

    async def test_timeout_and_upstream_server_error_are_sanitized(self):
        with patch.object(
            main,
            "request_lookup",
            new=AsyncMock(side_effect=httpx.TimeoutException("timed out")),
        ):
            with self.assertRaises(HTTPException) as raised:
                await main.validate_postcode_endpoint(
                    main.PostcodeRequest(postcode="EK-01-A03-FK-01")
                )
        self.assertEqual(raised.exception.status_code, 504)

        with patch.object(
            main,
            "request_lookup",
            new=AsyncMock(return_value=httpx.Response(500)),
        ):
            with self.assertRaises(HTTPException) as raised:
                await main.validate_postcode_endpoint(
                    main.PostcodeRequest(postcode="EK-01-A03-FK-01")
                )
        self.assertEqual(raised.exception.status_code, 502)

    def test_delivery_endpoints_remain_registered(self):
        paths = {route.path for route in main.app.routes}
        self.assertIn("/api/deliveries", paths)
        self.assertIn("/api/deliveries/{delivery_id}/status", paths)


if __name__ == "__main__":
    unittest.main()
