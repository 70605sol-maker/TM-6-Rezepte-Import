"""Schwedische Fiskgryta, manuell adaptiert für den TM6.
Ungetestete Adaption: Vor Verwendung Gargrad und Geräteeinstellungen prüfen.
"""
from cookidoo_uploader.schema import Recipe, step, tts

INGREDIENTS = [
    "800 g Kartoffeln, geschält",
    "2 Karotten",
    "½ Stange Porree",
    "1 Bund Schnittlauch",
    "500 g Lachsfilet, ohne Haut und Gräten",
    "600 g Wasser (Kartoffeln dämpfen)",
    "300 g Wasser (Sauce)",
    "100 g Milch",
    "150 g Schlagsahne (mind. 30 % Fett)",
    "15 g Öl",
    "10–15 g Speisestärke",
    "1 Gemüsebrühwürfel oder 1 TL Brühepulver",
    "Salz",
    "1 Prise Cayennepfeffer",
]

INSTRUCTIONS = [
    step("Kartoffeln schälen, in ca. 2–3 cm große Stücke schneiden und im Varoma-Behälter verteilen. Dampfschlitze freilassen."),
    # Upstream tts() supports numeric Celsius only. No unverified Varoma annotation.
    step("600 g Wasser in den Mixtopf füllen, Varoma aufsetzen. Am TM6 MANUELL 30 Min. / Varoma / Stufe 1 einstellen. Kartoffeln auf Gargrad prüfen und bei Bedarf weiterdämpfen. Varoma abnehmen, Kartoffeln warm halten und Mixtopf leeren."),
    step("Karotten in dünne Scheiben und Porree in feine Ringe schneiden. Zusammen mit 15 g Öl in den Mixtopf geben und andünsten.",
         settings=tts(240, 1, temp=120, reverse=True), ingredient_spans=["15 g Öl"]),
    step("300 g Wasser, 150 g Schlagsahne und Brühe zugeben. 10–15 g Speisestärke mit 100 g kalter Milch anrühren und zugeben. Sauce unter Rühren erhitzen.",
         settings=tts(600, 1, temp=100, reverse=True),
         ingredient_spans=["300 g Wasser", "150 g Schlagsahne", "10–15 g Speisestärke", "100 g"]),
    step("Lachs in etwa 2 × 2 cm große Stücke schneiden und vorsichtig zugeben. Schonend garen.",
         settings=tts(420, "soft", temp=90, reverse=True)),
    step("Prüfen, ob der Lachs vollständig durchgegart ist; falls nötig die Garzeit verlängern. Schnittlauch schneiden, Hälfte vorsichtig unterrühren. Mit Salz und Cayennepfeffer abschmecken."),
    step("Kartoffeln auf die Teller verteilen, Lachseintopf darübergeben und mit restlichem Schnittlauch garnieren."),
]

RECIPE = Recipe(
    name="Schwedische Fiskgryta – Lachseintopf (TM6)",
    ingredients=INGREDIENTS,
    instructions=INSTRUCTIONS,
    total_time=63 * 60,
    prep_time=12 * 60,
    yield_value=4,
)
