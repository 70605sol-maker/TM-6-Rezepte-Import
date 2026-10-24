"""Einmaliger Testupload der Fiskgryta in ein separates Cookidoo-Testkonto.

Nur via manuell gestartetem GitHub Actions Workflow.
Keine Zugangsdaten im Repository und kein Upload ohne Secrets.
"""
import importlib.util
import os
from pathlib import Path

from cookidoo_uploader.auth import get_cookie
from cookidoo_uploader.client import CookidooClient
from cookidoo_uploader.schema import build_payload, validate_payload

DOMAIN = "https://cookidoo.de"
LOCALE = "de-DE"
RECIPE_FILE = Path("recipes/fiskgryta_tm6.py")


def main():
    spec = importlib.util.spec_from_file_location("fiskgryta_tm6", RECIPE_FILE)
    recipe_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(recipe_module)
    payload = build_payload(recipe_module.RECIPE, tool="TM6")
    validate_payload(payload)

    if len(payload["ingredients"]) != 14 or len(payload["instructions"]) != 7:
        raise SystemExit("Rezeptdaten unerwartet verändert. Kein Upload.")
    if payload["tool"] != ["TM6"]:
        raise SystemExit("Falsches Gerät. Kein Upload.")

    if not os.environ.get("COOKIDOO_EMAIL") or not os.environ.get("COOKIDOO_PASSWORD"):
        raise SystemExit(
            "GitHub-Secrets COOKIDOO_TEST_EMAIL und COOKIDOO_TEST_PASSWORD fehlen. Kein Upload."
        )

    print("Rezeptdaten geprüft: 14 Zutaten, 7 Schritte, TM6.")
    print("Versuche Login auf cookidoo.de (Testkonto).")
    try:
        cookie = get_cookie()
    except Exception as exc:
        # Keine Ausgaben aus Anmeldeantworten oder vertraulichen Cookies in die Logs.
        raise SystemExit(
            f"Cookidoo-Anmeldung nicht erfolgreich ({type(exc).__name__}). "
            "Der automatische Login des Drittanbieter-Projekts ist experimentell."
        ) from None

    client = CookidooClient(cookie, domain=DOMAIN, locale=LOCALE)
    print("Login-Session erhalten. Versuche Rezept-Upload.")
    try:
        recipe_id = client.upload_recipe(payload)
    except Exception as exc:
        raise SystemExit(
            f"Upload konnte nicht abgeschlossen werden ({type(exc).__name__}). "
            "Eventuell wurde bereits ein unvollständiger Rezeptentwurf erstellt."
        ) from None

    print("Rezept wurde laut Upload-Schnittstelle angelegt.")
    print(f"Rezept-ID: {recipe_id}")
    print(f"Cookidoo-Link: {DOMAIN}/created-recipes/{LOCALE}/{recipe_id}")
    try:
        saved = client.verify(recipe_id)
        good = (
            saved.get("name") == payload["name"]
            and len(saved.get("recipeIngredient", [])) == len(payload["ingredients"])
            and len(saved.get("recipeInstructions", [])) == len(payload["instructions"])
        )
        if not good:
            raise SystemExit(
                "Upload angelegt, aber zurückgelesene Zutaten/Schritte stimmen nicht vollständig überein. "
                "In Cookidoo manuell prüfen."
            )
        print("Upload-Zurücklesen erfolgreich: Name, Zutaten und Schrittzahl stimmen.")
        print("TM6-Einstellungen und Garzustand vor dem Kochen manuell prüfen.")
    except SystemExit:
        raise
    except Exception as exc:
        raise SystemExit(
            f"Upload angelegt, aber automatische Überprüfung fehlgeschlagen ({type(exc).__name__}). "
            "Bitte in Cookidoo prüfen."
        ) from None


if __name__ == "__main__":
    main()
