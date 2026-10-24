"""Automatischer Cookidoo-Testkonto-Upload neuer Rezept-JSON-Dateien.

Nutzt die bereits getestete OAuth2-Bibliothek; keine Anmeldung im Chat.
Führt keine Aktionen im Hauptkonto aus.
"""
import asyncio
import json
import os
import re
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

MAX_RECIPE_BYTES = 100_000
ALLOWED_TEMPS = set(range(37, 121)) | {"varoma"}
ALLOWED_SPEEDS = {"soft"} | {str(v / 2).rstrip("0").rstrip(".") if v % 2 else str(v // 2) for v in range(1, 21)}
FOLDER = Path("recipes/inbox")


def check_text(value, what, max_length=4000):
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise ValueError(f"{what}: ungültiger Text")
    return value.strip()


def load_recipe(file_path):
    file_path = Path(file_path)
    if file_path.parent != FOLDER or file_path.suffix.lower() != ".json":
        raise ValueError("Nur JSON-Dateien in recipes/inbox erlaubt.")
    if not file_path.is_file() or file_path.stat().st_size > MAX_RECIPE_BYTES:
        raise ValueError("Rezeptdatei fehlt oder ist zu groß.")
    obj = json.loads(file_path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict) or obj.get("schema_version") != 1:
        raise ValueError("Unbekanntes Rezeptformat.")
    name = check_text(obj.get("title"), "Rezepttitel", 160)
    ingredients = obj.get("ingredients")
    raw_steps = obj.get("steps")
    if not isinstance(ingredients, list) or not 1 <= len(ingredients) <= 90:
        raise ValueError("Ungültige Zutatenliste.")
    if not isinstance(raw_steps, list) or not 1 <= len(raw_steps) <= 70:
        raise ValueError("Ungültige Schrittzahl.")
    ingredients = [check_text(v, "Zutat", 300) for v in ingredients]
    if len(set(ingredients)) != len(ingredients):
        raise ValueError("Doppelte Zutatenangaben.")

    servings = obj.get("servings")
    prep = obj.get("prep_time_minutes")
    total = obj.get("total_time_minutes")
    if type(servings) is not int or not 1 <= servings <= 50:
        raise ValueError("Ungültige Portionen.")
    if type(prep) is not int or type(total) is not int or not 0 <= prep <= total <= 1440:
        raise ValueError("Ungültige Zeitangaben.")

    enforce_quantities = obj.get("enforce_quantities_in_steps", False)
    if type(enforce_quantities) is not bool:
        raise ValueError("enforce_quantities_in_steps muss true/false sein.")
    documented_ingredients = set()

    hints = obj.get("notes", [])
    if not isinstance(hints, list) or len(hints) > 12:
        raise ValueError("Ungültige Hinweise.")
    hints = [check_text(x, "Hinweis", 700) for x in hints]
    hints.append(
        "Automatisch auf TM6 übertragen. Zutatenmengen und Guided-Cooking-"
        "Einstellungen vor Verwendung prüfen. Keine offizielle Vorwerk-Rezeptprüfung."
    )
    steps = []
    count = 0
    for i, raw in enumerate(raw_steps, 1):
        if not isinstance(raw, dict):
            raise ValueError(f"Schritt {i}: kein Objekt.")
        text = check_text(raw.get("text"), f"Schritt {i}")
        if enforce_quantities:
            uses = raw.get("uses", [])
            if not isinstance(uses, list) or not uses:
                # Es gibt auch reine Maschinen-, Misch- und Servierschritte.
                uses = [] if uses == [] else None
            if uses is None or len(uses) > 30:
                raise ValueError(f"Schritt {i}: ungültige Zutatenreferenzen.")
            for entry in uses:
                if not isinstance(entry, dict):
                    raise ValueError(f"Schritt {i}: ungültige Zutatenreferenz.")
                ingredient = check_text(entry.get("ingredient"), "Zutatenreferenz", 300)
                mention = check_text(entry.get("mention"), "Mengenangabe", 180)
                if ingredient not in ingredients or text.count(mention) != 1:
                    raise ValueError(f"Schritt {i}: Zutatenmenge fehlt im Anweisungstext.")
                tokens = ingredient.split()
                expected_prefix = " ".join(tokens[:3 if len(tokens) >= 3 and tokens[1] in ("g", "kg", "ml", "l", "TL", "EL") else 2])
                if not mention.startswith(expected_prefix):
                    raise ValueError(f"Schritt {i}: Zutatenmenge stimmt nicht mit Zutatenliste überein.")
                if ingredient in documented_ingredients:
                    raise ValueError(f"Schritt {i}: Zutat bereits in anderem Schritt verwendet.")
                documented_ingredients.add(ingredient)
        annotations = []
        raw_weigh = raw.get("weigh", [])
        if not isinstance(raw_weigh, list) or len(raw_weigh) > 20:
            raise ValueError(f"Schritt {i}: ungültige Wiegezuordnungen.")
        if raw_weigh and text.lstrip().upper().startswith("[FRIEND"):
            raise ValueError(f"Schritt {i}: Friend hat keine Waage.")
        seen_slots = set()
        for mapping in raw_weigh:
            if not isinstance(mapping, dict):
                raise ValueError(f"Schritt {i}: ungültige Zutatmarkierung.")
            slot = check_text(mapping.get("slot"), f"Schritt {i}: Markierung", 120)
            ingredient = check_text(mapping.get("ingredient"), f"Schritt {i}: Zutat", 300)
            if ingredient not in ingredients or not ingredient.startswith(slot):
                raise ValueError(f"Schritt {i}: Markierung passt nicht zur Zutatenliste.")
            if not re.match(r"^\d+(?:[.,]\d+)?\s*g\s+\S", slot):
                raise ValueError(f"Schritt {i}: nur Grammangaben automatisch wiegen.")
            if text.count(slot) != 1 or slot in seen_slots:
                raise ValueError(f"Schritt {i}: Markierung im Text nicht eindeutig.")
            annotations.append(CookidooIngredientAnnotation(slot=slot, description=ingredient))
            seen_slots.add(slot)

        config = raw.get("cooking")
        if config is None:
            steps.append(CookidooInstruction(text=text, annotations=annotations))
            continue
        if not isinstance(config, dict):
            raise ValueError(f"Schritt {i}: falsche Kocheinstellung.")
        sec, temp, speed = (
            config.get("seconds"),
            config.get("temperature"),
            config.get("speed"),
        )
        if type(sec) is not int or not 1 <= sec <= 7200:
            raise ValueError(f"Schritt {i}: ungültige Zeit.")
        if type(temp) is int:
            if temp not in ALLOWED_TEMPS:
                raise ValueError(f"Schritt {i}: ungültige Temperatur.")
        elif temp is not None and temp != "varoma":
            raise ValueError(f"Schritt {i}: ungültige Temperatur.")
        if speed is None or str(speed) not in ALLOWED_SPEEDS:
            raise ValueError(f"Schritt {i}: ungültige Geschwindigkeit.")
        if type(config.get("reverse", False)) is not bool:
            raise ValueError(f"Schritt {i}: ungültiger Linkslauf.")
        reverse = config.get("reverse", False)
        if "[TM6:" in text:
            raise ValueError(f"Schritt {i}: reservierte Programmkennung im Text.")
        minsec = f"{sec // 60} Min." if sec % 60 == 0 else f"{sec} Sek."
        tempdesc = "Varoma" if temp == "varoma" else (f"{temp} °C" if temp is not None else "ohne Heizung")
        speeddesc = "Sanftrührstufe" if str(speed) == "soft" else f"Stufe {speed}"
        slot = f"[TM6: {minsec} / {tempdesc} / {speeddesc}{' / Linkslauf' if reverse else ''}]"
        full = text + "\n" + slot
        ann = CookidooTTSAnnotation(
            slot=slot,
            time=sec,
            temperature=(
                CookidooTemperatureSetting(
                    value=temp, unit=None if temp == "varoma" else "C"
                ) if temp is not None else None
            ),
            speed=str(speed),
            direction="CCW" if reverse else None,
        )
        steps.append(CookidooInstruction(text=full, annotations=[*annotations, ann]))
        count += 1

    if enforce_quantities:
        missing = set(ingredients) - documented_ingredients
        if missing:
            raise ValueError(
                "Nicht alle Zutaten mit Mengenangabe in den Kochschritten: "
                + ", ".join(sorted(missing))
            )

    recipe = CookidooCreateCustomRecipe(
        name=name,
        ingredients=ingredients,
        instructions=steps,
        serving_size=servings,
        active_time=prep * 60,
        total_time=total * 60,
        tools=[ThermomixMachineType.TM6],
        hints=hints,
        work_status="PRIVATE",
        requires_annotations_check=True,
    )
    # Validierung der erzeugten API-Payload und UTF-16-Offsets ohne Netzwerk.
    payload = Cookidoo._build_custom_recipe_payload(
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
    assert len(payload["instructions"]) == len(raw_steps)
    expected_weigh = sum(len(raw.get("weigh", [])) for raw in raw_steps)
    got_weigh = sum(
        len([a for a in step.get("annotations", []) if a.get("type") == "INGREDIENT"])
        for step in payload["instructions"]
    )
    assert got_weigh == expected_weigh
    assert sum(
        len([a for a in s.get("annotations", []) if a.get("type") == "TTS"])
        for s in payload["instructions"]
    ) == count
    return recipe, count


async def run(file_paths):
    email = os.environ.get("COOKIDOO_TEST_EMAIL")
    password = os.environ.get("COOKIDOO_TEST_PASSWORD")
    if not email or not password:
        raise ValueError("Cookidoo-Testkonto-Secrets nicht gesetzt.")
    parsed = [load_recipe(p) for p in file_paths]
    if not parsed:
        print("Keine neuen JSON-Rezepte erkannt; kein Upload.")
        return
    cfg = CookidooConfig(
        email=email,
        password=password,
        localization=CookidooLocalizationConfig(
            country_code="de",
            language="de-DE",
            url="https://cookidoo.de/foundation/de-DE",
        ),
    )
    async with aiohttp.ClientSession(
        cookie_jar=aiohttp.CookieJar(unsafe=True)
    ) as session:
        client = Cookidoo(session, cfg=cfg)
        await client.login()
        await client.get_user_info()
        print("Cookidoo-Testkonto erfolgreich angemeldet.")
        for (recipe, count), path in zip(parsed, file_paths):
            existing = await client.list_custom_recipes()
            matches = [r for r in existing if r.name == recipe.name]
            if matches:
                print(f"{path}: bereits vorhanden, kein Duplikat.")
                print("Rezept-Link:", matches[0].url)
                print("Zum Ändern eine neue Versionsbezeichnung verwenden.")
                continue
            created = await client.create_custom_recipe(recipe)
            if (created.name != recipe.name
                    or len(created.ingredients) != len(recipe.ingredients)
                    or len(created.instructions) != len(recipe.instructions)):
                raise RuntimeError("Rezept angelegt; Rückleseprüfung fehlgeschlagen.")
            print(f"{path}: HOCHGELADEN; {count} automatische TM6-Schritte.")
            print("Rezept-Link:", created.url)
            print("In Cookidoo-Testkonto: Rezept teilen und ins Hauptkonto übernehmen.")


if __name__ == "__main__":
    try:
        files = sys.argv[1:]
        if not files:
            raise ValueError("Keine Rezeptdateien übergeben.")
        asyncio.run(run(files))
    except Exception as exc:
        # Keine vollständigen Netzwerkfehler ausgeben: könnten Tokens enthalten.
        print(f"Automatischer Import fehlgeschlagen ({type(exc).__name__}).", file=sys.stderr)
        print("Vor einem Wiederholungsversuch Testkonto auf Teilimporte prüfen.", file=sys.stderr)
        sys.exit(1)
