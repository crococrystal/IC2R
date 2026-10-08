#!/usr/bin/env python3
"""Check Russian coverage, formatting, and translation keys used by the UI."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LANG = ROOT / "src/main/resources/assets/ic2/lang"
FORMAT = re.compile(r"%(?:\d+\$)?[-#+ 0,(<]*\d*(?:\.\d+)?(?:[tT])?[a-zA-Z%]")
SYMBOL_KEYS = {
    "advancements.ic2.root",
    "ic2.AdvMiner.gui.info.minelevel",
    "ic2.generic.text.C",
    "ic2.generic.text.EU",
    "ic2.generic.text.bucketUnit",
    "ic2.generic.text.hu",
    "ic2.generic.text.v",
    "ic2.name",
    "ic2.tooltip.sound",
    "ic2.upgrade.advancedGUI.nbt",
    "item.ic2.mining_laser.tooltip.mode.3x3",
    "itemGroup.ic2.general",
}


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        assert key not in result, f"Duplicate translation key: {key}"
        result[key] = value
    return result


english = json.loads((LANG / "en_us.json").read_text(), object_pairs_hook=unique_keys)
russian = json.loads((LANG / "ru_ru.json").read_text(), object_pairs_hook=unique_keys)
assert english.keys() == russian.keys(), "English/Russian translation coverage differs"
for key, text in russian.items():
    assert isinstance(text, str) and text.strip(), f"Empty translation: {key}"
    assert FORMAT.findall(text) == FORMAT.findall(english[key]), f"Changed placeholders: {key}"
    assert not re.search(r"[\u4e00-\u9fff]", text), f"Untranslated Chinese: {key}"
    assert key in SYMBOL_KEYS or re.search(r"[А-Яа-яЁё]", text), f"Untranslated text: {key}"

ui_calls = re.compile(
    r'(?:Component\.translatable|TextProvider\.ofTranslated|\.withTooltip|\.withText)'
    r'\(\s*"(ic2\.[\w.]+)"'
    r'|\.messagePlayer\([^,]+,\s*"(ic2\.[\w.]+)"'
)
for source in (ROOT / "src/main/java").rglob("*.java"):
    source_text = source.read_text()
    for match in ui_calls.finditer(source_text):
        key = match[1] or match[2]
        if not key.endswith(".") and not re.match(r"\s*\+", source_text[match.end():]):
            assert key in russian, f"Missing UI translation {key} in {source}"
for source in (ROOT / "src/main/resources/assets/ic2/guidef").glob("*.xml"):
    for key in re.findall(r"(?:\{|text=\")(ic2\.[\w.]+)", source.read_text()):
        assert key in russian, f"Missing XML translation {key} in {source}"
for direction in ("Bottom", "Top", "North", "South", "West", "East"):
    assert f"ic2.dir.{direction}" in russian
for setting in ("ignored", "fuzzy", "exact", "direct", "comparison", "range"):
    assert f"ic2.upgrade.advancedGUI.{setting}" in russian
    assert f"ic2.upgrade.advancedGUI.{setting}.desc" in russian
assert russian["itemGroup.ic2.general"] == "IndustrialCraft 2"
print(f"Russian localization OK: {len(russian)} keys; UI/XML coverage and placeholders match")
