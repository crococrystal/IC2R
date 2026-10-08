#!/usr/bin/env python3
"""Verify original texture bytes, animations, model references and dynamic sprite paths.

Usage: python3 scripts/verify_legacy_textures.py [build/libs/IC2R.jar]
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import struct
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
RESOURCES = ROOT / "src/main/resources"
COLORS = "white orange magenta light_blue yellow lime pink gray light_gray cyan purple blue brown green red black".split()


def texture_path(sprite):
    namespace, path = sprite.split(":", 1)
    assert namespace and path and ".." not in Path(path).parts
    return f"assets/{namespace}/textures/{path}.png"


def self_check():
    assert texture_path("ic2:block/crop/wheat_1") == "assets/ic2/textures/block/crop/wheat_1.png"
    assert texture_path("minecraft:item/copper_ingot") == "assets/minecraft/textures/item/copper_ingot.png"
    try:
        texture_path("ic2:../outside")
    except AssertionError:
        pass
    else:
        raise AssertionError("Texture paths must remain inside their namespace")


def main():
    self_check()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jar", nargs="?", type=Path)
    args = parser.parse_args()
    manifest = json.loads((ROOT / "docs/legacy-textures.json").read_text())
    jar = ZipFile(args.jar) if args.jar else None
    read = jar.read if jar else lambda name: (RESOURCES / name).read_bytes()
    resource_names = set(jar.namelist()) if jar else {str(p.relative_to(RESOURCES)) for p in RESOURCES.rglob("*") if p.is_file()}
    fork_textures = manifest.get("fork_native_textures", {})
    assert len(fork_textures) == manifest.get("fork_native_png_count", 0)
    assert len(manifest["modern_native_textures"]) == manifest["modern_native_png_count"]
    selection_aliases = manifest.get("selection_legacy_aliases", {})
    modern_overrides = manifest.get("modern_texture_overrides", {})
    modern_models = manifest.get("modern_model_overrides", {})
    expected_pngs = set(manifest["mapping"]) | set(manifest["modern_native_textures"]) | set(fork_textures) | {name.removeprefix("assets/ic2/textures/") for name in selection_aliases}
    actual_pngs = {name.removeprefix("assets/ic2/textures/") for name in resource_names if name.startswith("assets/ic2/textures/") and name.endswith(".png")}
    assert actual_pngs == expected_pngs, "Texture inventory differs from recorded provenance"
    for name, properties in fork_textures.items():
        png = read("assets/ic2/textures/" + name)
        assert png.startswith(b"\x89PNG\r\n\x1a\n")
        assert hashlib.sha256(png).hexdigest() == properties["sha256"]
        assert struct.unpack(">II", png[16:24]) == (properties["width"], properties["height"])
    archive_bytes = read(manifest["source_archive"])
    assert hashlib.sha256(archive_bytes).hexdigest() == manifest["source_archive_sha256"]
    with ZipFile(io.BytesIO(archive_bytes)) as source:
        original_pngs = {n for n in source.namelist() if n.endswith(".png")}
        assert len(original_pngs) == manifest["source_png_count"] == 2079
        assert sum(n.startswith("assets/") for n in original_pngs) == manifest["source_experimental_png_count"] == 1609
        assert sum(n.startswith("ic2/profiles/") for n in original_pngs) == manifest["source_classic_png_count"] == 470
        assert sum(n.endswith(".mcmeta") for n in source.namelist()) == manifest["source_animation_metadata_count"]
        mappings = {f"assets/ic2/textures/{target}": original for target, original in manifest["mapping"].items()}
        mappings.update(manifest["minecraft_overrides"])
        assert len(manifest["mapping"]) == manifest["mapped_png_count"]
        assert len(set(manifest["mapping"].values())) == manifest["unique_mapped_source_png_count"] == 1609
        for target, original in mappings.items():
            assert ".." not in Path(target).parts and target.startswith("assets/") and target.endswith(".png"), target
            override = modern_overrides.get(target)
            if override:
                assert override["base_commit"] == "417fddb1fd23b926accc02b380cd658121f5c9e1"
                if override.get("removed"):
                    assert target in manifest["minecraft_overrides"], f"Only vanilla overrides may be removed: {target}"
                    assert target not in resource_names and target + ".mcmeta" not in resource_names
                    continue
                assert read(target).startswith(b"\x89PNG\r\n\x1a\n")
                assert hashlib.sha256(read(target)).hexdigest() == override["sha256"], f"Altered selected modern pixels: {target}"
                metadata_hash = override["mcmeta_sha256"]
                if metadata_hash is not None:
                    assert hashlib.sha256(read(target + ".mcmeta")).hexdigest() == metadata_hash
                else:
                    assert target + ".mcmeta" not in resource_names
                if "untinted_model" in override:
                    model = override["untinted_model"]
                    assert model["path"].startswith("assets/ic2/models/block/") and ".." not in Path(model["path"]).parts
                    assert hashlib.sha256(read(model["path"])).hexdigest() == model["sha256"]
                    assert json.loads(read(model["path"]))["parent"] == "minecraft:block/cube_all"
                continue
            assert read(target) == source.read(original), f"Altered legacy pixels: {target}"
            if original + ".mcmeta" in source.namelist():
                assert read(target + ".mcmeta") == source.read(original + ".mcmeta"), f"Altered animation: {target}"
            else:
                assert target + ".mcmeta" not in resource_names, f"Unexpected animation: {target}"
        assert set(modern_overrides) <= mappings.keys(), "Unknown modern texture override"
        for target, entry in selection_aliases.items():
            assert target.startswith("assets/ic2/textures/block/crop/selection_legacy/") and ".." not in Path(target).parts
            assert read(target) == source.read(entry["source"])
            assert hashlib.sha256(read(target)).hexdigest() == entry["sha256"]
            if entry["mcmeta_sha256"] is not None:
                assert read(target + ".mcmeta") == source.read(entry["source"] + ".mcmeta")
                assert hashlib.sha256(read(target + ".mcmeta")).hexdigest() == entry["mcmeta_sha256"]
            else:
                assert target + ".mcmeta" not in resource_names
        for name, entry in modern_models.items():
            assert name.startswith("assets/ic2/models/block/crop/") and ".." not in Path(name).parts
            assert entry["base_commit"] == "417fddb1fd23b926accc02b380cd658121f5c9e1"
            assert hashlib.sha256(read(name)).hexdigest() == entry["sha256"]
        crop_aliases = {"eating_plant": "eatingplant", "poppy": "rose", "red_wheat": "redwheat", "sticky_reed": "stickreed"}
        crop_ages = {}
        for original in original_pngs:
            match = re.fullmatch(r"assets/ic2/textures/blocks/crop/(.+)_(\d+)\.png", original)
            if match and not (match[1] == "reed" and match[2] == "33"):
                crop_ages.setdefault(match[1], []).append(int(match[2]))
        model_refs = set()
        crop_models = 0
        dynamic_cables = 0
        cable_types = {"copper": (1, 1), "glass": (0, 0), "gold": (2, 1), "iron": (3, 1), "tin": (1, 1), "detector": (0, 2147483647), "splitter": (0, 2147483647)}
        for name in sorted(resource_names):
            if not name.startswith("assets/ic2/models/") or not name.endswith(".json"):
                continue
            model = json.loads(read(name))
            for ref in model.get("textures", {}).values():
                if ref.startswith("ic2:"):
                    assert texture_path(ref) in resource_names, f"Missing model texture: {name}: {ref}"
                    model_refs.add(texture_path(ref))
            crop = re.fullmatch(r"assets/ic2/models/block/crop/(.+)_(\d+)\.json", name)
            if crop:
                legacy_name = crop_aliases.get(crop[1], crop[1])
                ages = crop_ages.get(legacy_name)
                if ages and name not in modern_models:
                    stage = min(int(crop[2]) + (min(ages) != 0), max(ages))
                    expected = f"ic2:block/crop/{legacy_name}_{stage}"
                    assert expected in model["textures"].values(), f"Wrong crop growth stage: {name}"
                    crop_models += 1
            if model.get("loader") == "ic2:cable":
                cable = model["type"]
                insulation = model["insulation"]
                maximum, minimum_colored = cable_types[cable]
                assert 0 <= insulation <= maximum
                for color in COLORS if insulation >= minimum_colored else ["black"]:
                    suffix = f"_{color}" if insulation >= minimum_colored else ""
                    active = "_active" if model.get("active") and cable in ("detector", "splitter") else ""
                    ref = texture_path(f"ic2:block/wiring/cable/{cable}_cable_{insulation}{suffix}{active}")
                    assert ref in resource_names, f"Missing dynamic cable texture: {ref}"
                    model_refs.add(ref)
                foam = model["foam"]
                if foam == "soft":
                    assert texture_path("ic2:block/cf/foam") in resource_names
                elif foam.startswith("hard_"):
                    assert texture_path("ic2:block/cf/wall_" + foam[5:]) in resource_names
                dynamic_cables += 1
        fluids = (ROOT / "src/main/java/ic2/core/ref/Ic2Fluids.java").read_text()
        declarations = re.findall(r'create\(\s*"([a-z_]+)",\s*-?\d+,\s*-?\d+,\s*\d+,\s*\d+,\s*(?:true|false),\s*"([a-z_]+)",\s*("[a-z_]+"|null),\s*-?\d+\)', fluids)
        assert len(declarations) == 17
        for fluid, still, flow in declarations:
            assert still == fluid
            assert texture_path(f"ic2:block/fluid/{still}_still") in resource_names
            if flow != "null":
                assert flow.strip('"') == fluid
                assert texture_path(f"ic2:block/fluid/{fluid}_flow") in resource_names
        assert "(color & 0xFF000000) | 0xFFFFFF" in fluids
        cable_source = (ROOT / "src/main/java/ic2/core/block/wiring/DynamicCableModel.java").read_text()
        assert '"block/wiring/cable/"' in cable_source and '"blocks/' not in cable_source
        colors = (ROOT / "src/main/java/ic2/core/proxy/SideProxyClient.java").read_text()
        for material, color in manifest["storage_box_tints"].items():
            constant = material.upper() + "_STORAGE_BOX"
            assert re.search(r"->\s*" + str(color) + r",\s*Ic2Blocks\." + constant + r"\)", colors)
            assert re.search(r"->\s*" + str(color) + r",\s*Ic2Items\." + constant + r"\)", colors)
        direct_files = set()
        for java in (ROOT / "src/main/java").rglob("*.java"):
            for path in re.findall(r'"(textures/[^"+]+\.png)"', java.read_text()):
                name = "assets/ic2/" + path
                assert name in resource_names, f"Missing direct texture: {java}: {path}"
                direct_files.add(name)
        print(f"PASS: {len(mappings) - len(modern_overrides)} exact original PNG copies; {len(modern_overrides)} selected modern overrides; {len(selection_aliases)} protected legacy crop frames; all {len(original_pngs)} originals archived; {len(model_refs)} model/dynamic sprites; {crop_models} crop stage models; {dynamic_cables} cable loader models; 17 fluids; {len(direct_files)} direct renderer/GUI paths; {len(fork_textures)} fork-native GUI texture.")
    if jar:
        jar.close()


if __name__ == "__main__":
    main()
