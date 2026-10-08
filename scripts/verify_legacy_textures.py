#!/usr/bin/env python3
"""Verify the modern baseline plus declarative, explicitly selected legacy images.

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
BASE = "417fddb1fd23b926accc02b380cd658121f5c9e1"
COLORS = "white orange magenta light_blue yellow lime pink gray light_gray cyan purple blue brown green red black".split()
INACTIVE_MODELS = {"assets/ic2/models/item/uu_matter.json", "assets/ic2/models/block/machine/misc/item_buffer_2.json"}
STORAGE = {"storage_box": ("IRON", 13158600), "wooden_storage_box": ("WOODEN", 10454093), "bronze_storage_box": ("BRONZE", 16744448), "steel_storage_box": ("STEEL", 8421504)}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def texture_path(sprite):
    namespace, path = sprite.split(":", 1)
    assert namespace and path and ".." not in Path(path).parts
    return f"assets/{namespace}/textures/{path}.png"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jar", nargs="?", type=Path)
    args = parser.parse_args()
    manifest = json.loads((ROOT / "docs/legacy-textures.json").read_text())
    assert manifest["workflow_schema"] == 2 and manifest["base_commit"] == BASE
    mapping = manifest["selectable_legacy_mapping"]
    selected = set(manifest["selected_legacy_textures"])
    assert len(selected) == len(manifest["selected_legacy_textures"]) and selected <= mapping.keys()
    assert len(mapping) == manifest["selectable_legacy_png_count"] == 1955
    assert mapping["assets/ic2/textures/block/crop/ender_blossom_3.png"] == "assets/ic2/textures/blocks/crop/ender_blossom_4.png"
    jar = ZipFile(args.jar) if args.jar else None
    read = jar.read if jar else lambda name: (RESOURCES / name).read_bytes()
    names = set(jar.namelist()) if jar else {str(path.relative_to(RESOURCES)) for path in RESOURCES.rglob("*") if path.is_file()}
    baseline = manifest["baseline_png_sha256"]
    fork = manifest["fork_native_textures"]
    assert len(baseline) == 2038 and len(fork) == manifest["fork_native_png_count"]
    expected_pngs = set(baseline) | set(fork)
    actual_pngs = {name.removeprefix("assets/ic2/textures/") for name in names if name.startswith("assets/ic2/textures/") and name.endswith(".png")}
    assert actual_pngs == expected_pngs, "Only baseline textures and fork GUI belong in the active IC2 inventory"
    archive_bytes = read(manifest["source_archive"])
    assert digest(archive_bytes) == manifest["source_archive_sha256"]
    with ZipFile(io.BytesIO(archive_bytes)) as original:
        source_names = set(original.namelist())
        original_pngs = {name for name in source_names if name.endswith(".png")}
        assert len(original_pngs) == manifest["source_png_count"] == 2079
        assert sum(name.startswith("assets/") for name in original_pngs) == manifest["source_experimental_png_count"] == 1609
        assert sum(name.startswith("ic2/profiles/") for name in original_pngs) == manifest["source_classic_png_count"] == 470
        assert sum(name.endswith(".mcmeta") for name in source_names) == manifest["source_animation_metadata_count"] == 35
        for path, expected_hash in baseline.items():
            target = "assets/ic2/textures/" + path
            if target in selected:
                assert read(target) == original.read(mapping[target]), f"Altered legacy image: {target}"
            else:
                assert digest(read(target)) == expected_hash, f"Altered modern image: {target}"
            if target in selected:
                source_meta = mapping[target] + ".mcmeta"
                if source_meta in source_names:
                    assert read(target + ".mcmeta") == original.read(source_meta)
                else:
                    assert target + ".mcmeta" not in names
            elif path + ".mcmeta" in manifest["baseline_mcmeta_sha256"]:
                assert digest(read(target + ".mcmeta")) == manifest["baseline_mcmeta_sha256"][path + ".mcmeta"]
            else:
                assert target + ".mcmeta" not in names
        for target in manifest["minecraft_overrides"]:
            if target in selected:
                assert read(target) == original.read(mapping[target])
            else:
                assert target not in names, f"Unchecked vanilla copper must use Minecraft: {target}"
            assert target + ".mcmeta" not in names
    for path, properties in fork.items():
        png = read("assets/ic2/textures/" + path)
        assert digest(png) == properties["sha256"]
        assert struct.unpack(">II", png[16:24]) == (properties["width"], properties["height"])
    model_refs, dynamic_models = set(), 0
    for name, expected_hash in manifest["baseline_model_sha256"].items():
        assert digest(read(name)) == expected_hash, f"Models must remain modern: {name}"
        model = json.loads(read(name))
        for ref in model.get("textures", {}).values():
            if ref.startswith("ic2:") and name not in INACTIVE_MODELS:
                path = texture_path(ref)
                assert path in names, f"Missing model texture: {name}: {ref}"
                model_refs.add(path)
        if model.get("loader") == "ic2:cable":
            minimum = {"copper": 1, "glass": 0, "gold": 1, "iron": 1, "tin": 1, "detector": 2147483647, "splitter": 2147483647}[model["type"]]
            colored = model["insulation"] >= minimum
            for color in COLORS if colored else ["black"]:
                suffix = "_" + color if colored else ""
                active = "_active" if model.get("active") and model["type"] in ("detector", "splitter") else ""
                path = texture_path(f"ic2:block/wiring/cable/{model['type']}_cable_{model['insulation']}{suffix}{active}")
                assert path in names
                model_refs.add(path)
            dynamic_models += 1
    fluids = (ROOT / "src/main/java/ic2/core/ref/Ic2Fluids.java").read_text()
    assert "(color & 0xFF000000)" not in fluids, "Fluid colors must stay modern"
    declarations = re.findall(r'create\(\s*"([a-z_]+)",\s*-?\d+,\s*-?\d+,\s*\d+,\s*\d+,\s*(?:true|false),\s*"([a-z_0-9]+)",\s*("[a-z_0-9]+"|null),\s*-?\d+\)', fluids)
    assert len(declarations) == 17
    for _, still, flow in declarations:
        assert texture_path(f"ic2:block/fluid/{still}_still") in names
        if flow != "null":
            assert texture_path("ic2:block/fluid/" + flow.strip('"') + "_flow") in names
    colors = (ROOT / "src/main/java/ic2/core/proxy/SideProxyClient.java").read_text()
    for name, (constant, color) in STORAGE.items():
        active = "assets/ic2/textures/block/" + name + ".png" in selected
        for category in ("Ic2Blocks", "Ic2Items"):
            pattern = r"->\s*" + str(color) + r",\s*" + category + r"\." + constant + r"_STORAGE_BOX\)"
            assert bool(re.search(pattern, colors)) == active, "Storage tints must affect only selected legacy boxes"
    cable_source = (ROOT / "src/main/java/ic2/core/block/wiring/DynamicCableModel.java").read_text()
    assert '"block/wiring/cable/"' in cable_source and '"blocks/' not in cable_source
    direct_files = set()
    for java in (ROOT / "src/main/java").rglob("*.java"):
        for path in re.findall(r'"(textures/[^"+]+\.png)"', java.read_text()):
            name = "assets/ic2/" + path
            assert name in names, f"Missing direct texture: {java}: {path}"
            direct_files.add(name)
    print(f"PASS: {len(baseline)} modern baseline PNGs + {len(fork)} fork GUI; {len(selected)} opt-in legacy choices; all2079 originals archived; {len(model_refs)} model/dynamic sprites; {dynamic_models} cable models; 17 modern fluids; {len(direct_files)} direct texture paths.")
    if jar:
        jar.close()


if __name__ == "__main__":
    main()
