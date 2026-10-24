"""Erstellt die Fiskgryta mit der funktionierenden Cookidoo-OAuth2-Bibliothek.

Kein Upload ohne manuelle GitHub-Actions-Auslösung.
Beide Koch- und API-Bibliotheken sind im Workflow auf getestete Commits fixiert.
"""
import asyncio
import importlib.util
import os
import sys
from pathlib import Path

import aiohttp
from cookidoo_api import Cookidoo
from cookidoo_api.types import (
    CookidooConfig,
    CookidooCreateCustomRecipe,
    CookidooIngredientAnnotation,
    CookidooInstruction,
    CookidooLocalizationConfig,
    CookidooTemperatureSetting,
    CookidooTTSAnnotation,
    ThermomixMachineType,
)
from cookidoo_uploader.schema import build_payload, validate_payload


def build_test_recipe():
    path = Path("recipes/fiskgryta_tm6.py")
    spec = importlib.util.spec_from_file_location("fiskgryta_tm6", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    original = build_payload(module.RECIPE, tool="TM6")
    validate_payload(original)
    ingredients = [i["text"] for i in original["ingredients"]]
    steps = []
    converted_tts = 0

    for item in original["instructions"]:
        annotations = []
        for source in item.get("annotations", []):
            pos = source["position"]
            slot = item["text"][pos["offset"]:pos["offset"] + pos["length"]]
            if source["type"] == "TTS":
                data = source["data"]
                temp = data.get("temperature")
                annotations.append(
                    CookidooTTSAnnotation(
                        slot=slot,
                        time=data.get("time"),
                        speed=data.get("speed"),
                        direction=data.get("direction"),
                        temperature=(
                            CookidooTemperatureSetting(
                                value=temp["value"], unit=temp.get("unit", "C")
                            )
                            if temp else None
                        ),
                    )
                )
                converted_tts += 1
            elif source["type"] == "INGREDIENT":
                # Nur exakte Zutaten-Annotationen übernehmen.
                desc = source["data"]["description"]
                if desc in ingredients:
                    annotations.append(CookidooIngredientAnnotation(
                        slot=slot, description=desc
                    ))
        steps.append(CookidooInstruction(text=item["text"], annotations=annotations))

    if len(ingredients) != 14 or len(steps) != 7 or converted_tts != 3:
        raise ValueError("Unerwartete Rezeptdaten. Upload abgebrochen.")

    recipe = CookidooCreateCustomRecipe(
        name=original["name"],
        ingredients=ingredients,
        instructions=steps,
        serving_size=original["yield"]["value"],
        total_time=original["totalTime"],
        active_time=original["prepTime"],
        tools=[ThermomixMachineType.TM6],
        hints=[
            "Inoffizielle, ungetestete TM6-Adaption. Vor dem Kochen alle "
            "Geräteeinstellungen prüfen. Kartoffeln werden manuell mit "
            "Varoma-Einstellung gegart. Lachs vollständig durchgaren."
        ],
        work_status="PRIVATE",
    )
    # Validiert die Daten gegen das Schema der neuen Bibliothek vor dem Login.
    Cookidoo._build_custom_recipe_payload(
        name=recipe.name,
        ingredients=recipe.ingredients,
        steps=recipe.instructions,
        servings=recipe.serving_size,
        active_time=recipe.active_time,
        total_time=recipe.total_time,
        hints=recipe.hints,
        machine_types=recipe.tools,
        unit_text=recipe.unit_text,
        image=recipe.image,
        image_owned_by_user=False,
        work_status=recipe.work_status,
        requires_annotations_check=recipe.requires_annotations_check,
    )
    print("Rezept validiert: 14 Zutaten, 7 Schritte, 3 TM6-TTS-Blöcke.")
    return recipe


async def upload():
    email = os.environ.get("COOKIDOO_TEST_EMAIL")
    password = os.environ.get("COOKIDOO_TEST_PASSWORD")
    if not email or not password:
        raise ValueError("GitHub-Secrets für das Testkonto fehlen.")
    recipe = build_test_recipe()
    localization = CookidooLocalizationConfig(
        country_code="de",
        language="de-DE",
        url="https://cookidoo.de/foundation/de-DE",
    )
    async with aiohttp.ClientSession(
        cookie_jar=aiohttp.CookieJar(unsafe=True)
    ) as session:
        cookidoo = Cookidoo(session, cfg=CookidooConfig(
            email=email, password=password, localization=localization,
        ))
        await cookidoo.login()
        await cookidoo.get_user_info()
        print("Cookidoo-Testkonto erfolgreich angemeldet.")

        # Zweiter Start darf nicht versehentlich ein Duplikat erstellen.
        previous = await cookidoo.list_custom_recipes()
        existing = next((r for r in previous if r.name == recipe.name), None)
        if existing:
            print("Rezept bereits vorhanden, kein weiterer Upload.")
            print("Rezept-ID:", existing.id)
            print("Rezept-Link:", existing.url)
            return

        print("Erstelle Fiskgryta in Meine Kreationen...")
        created = await cookidoo.create_custom_recipe(recipe)
        print("Rezept-ID:", created.id)
        print("Rezept-Link:", created.url)
        print("Name:", created.name)
        print("Zutaten:", len(created.ingredients))
        print("Schritte:", len(created.instructions))
        if (created.name != recipe.name
                or len(created.ingredients) != 14
                or len(created.instructions) != 7):
            raise RuntimeError(
                "Rezept wurde erstellt, aber Rückleseprüfung weicht ab. "
                "In Cookidoo manuell prüfen."
            )
        print("UPLOAD ERFOLGREICH. TM6-Geräteeinstellungen vor Verwendung kontrollieren.")


if __name__ == "__main__":
    try:
        asyncio.run(upload())
    except Exception as e:
        # Nie Login-Responses, Passwörter, Cookies oder Tokens ins Log schreiben.
        print("Testupload nicht erfolgreich:", type(e).__name__, file=sys.stderr)
        print("Keinen zweiten Lauf starten, ohne den Rezeptbestand zu prüfen.", file=sys.stderr)
        sys.exit(1)
