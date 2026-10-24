"""Login-only test for miaucl/cookidoo-api OAuth2 implementation.

No recipe is created, changed, or deleted. No credentials/tokens are logged.
"""
import asyncio
import os
import sys

import aiohttp
from cookidoo_api import Cookidoo
from cookidoo_api.types import CookidooConfig, CookidooLocalizationConfig


async def test_login():
    email = os.environ.get("COOKIDOO_TEST_EMAIL")
    password = os.environ.get("COOKIDOO_TEST_PASSWORD")
    if not email or not password:
        raise RuntimeError("GitHub-Secrets des Cookidoo-Testkontos fehlen.")

    localization = CookidooLocalizationConfig(
        country_code="de",
        language="de-DE",
        url="https://cookidoo.de/foundation/de-DE",
    )
    async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as session:
        client = Cookidoo(
            session,
            cfg=CookidooConfig(
                email=email,
                password=password,
                localization=localization,
            ),
        )
        await client.login()
        print("OAuth2-Login erfolgreich.")
        # Read-only call confirms the authenticated token works with the API.
        await client.get_user_info()
        print("Angemeldeter API-Zugriff erfolgreich. Kein Rezept übertragen.")


if __name__ == "__main__":
    try:
        asyncio.run(test_login())
    except Exception as exc:
        # Avoid exposing credential values, cookies, response bodies or tokens.
        print(
            "OAuth2-Test gescheitert: " + type(exc).__name__
            + ". Keine Rezepte verändert.",
            file=sys.stderr,
        )
        sys.exit(1)
