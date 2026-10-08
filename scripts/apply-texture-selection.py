#!/usr/bin/env python3
"""Apply schema2 review choices: modern by default, only checked images from1.12.2.

python3 scripts/apply-texture-selection.py selection.json          # dry run
python3 scripts/apply-texture-selection.py selection.json --apply  # apply full selection
python3 scripts/apply-texture-selection.py --self-test

Every unchecked path returns to the pinned modern baseline. Models stay modern.
Original storage-box colors are registered only for selected legacy box images.
Schema1 keep_modern exports are rejected; make a fresh selection in the updated review.
"""
import argparse
import hashlib
import io
import json
import os
import re
from pathlib import Path, PurePosixPath
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
from unittest.mock import patch
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
RESOURCES = ROOT / "src/main/resources"
MANIFEST = ROOT / "docs/legacy-textures.json"
BASE = "417fddb1fd23b926accc02b380cd658121f5c9e1"
STORAGE = {"storage_box": ("IRON", 13158600), "wooden_storage_box": ("WOODEN", 10454093), "bronze_storage_box": ("BRONZE", 16744448), "steel_storage_box": ("STEEL", 8421504)}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key!r}")
        result[key] = value
    return result


def load_baseline():
    data = subprocess.check_output(["git", "archive", BASE, "src/main/resources/assets/ic2/textures"], cwd=ROOT, stderr=subprocess.PIPE)
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        return {entry.name.removeprefix("src/main/resources/"): archive.extractfile(entry).read() for entry in archive.getmembers() if entry.isfile()}


def validate_selection(selection, allowed):
    if type(selection) is not dict or set(selection) != {"schema", "base_commit", "use_legacy"}:
        raise ValueError("Expected schema2 with exactly schema, base_commit and use_legacy; export a fresh selection")
    if type(selection["schema"]) is not int or selection["schema"] != 2 or selection["base_commit"] != BASE:
        raise ValueError("Selection schema or base commit does not match this review")
    chosen = selection["use_legacy"]
    if type(chosen) is not list or any(type(path) is not str for path in chosen):
        raise ValueError("use_legacy must be a list of texture paths")
    if len(chosen) != len(set(chosen)):
        raise ValueError("Duplicate selected texture")
    for path in chosen:
        if PurePosixPath(path).as_posix() != path or ".." in PurePosixPath(path).parts or path not in allowed:
            raise ValueError(f"Texture is not selectable: {path[:200]!r}")
    return chosen


def validate_png(data):
    # Pixel data comes only from a pinned Git commit or the hash-checked original archive.
    if len(data) < 45 or not data.startswith(b"\x89PNG\r\n\x1a\n") or data[12:16] != b"IHDR" or b"IEND" not in data[-32:]:
        raise ValueError("Malformed original PNG")
    width, height = struct.unpack(">II", data[16:24])
    if not 0 < width <= 16384 or not 0 < height <= 16384:
        raise ValueError("Invalid PNG dimensions")


def target_path(name):
    path = RESOURCES / name
    if not path.resolve().is_relative_to(RESOURCES.resolve()):
        raise ValueError("Resource path escapes the project")
    return path


def optional_bytes(path):
    return path.read_bytes() if path.exists() else None


def storage_colors(text, selected):
    text = re.sub(r'    envProxy\.registerColorProvider\(\n        \(state, world, pos, tintIndex\) -> (?:10454093|13158600|16744448|8421504), Ic2Blocks\.(?:WOODEN|IRON|BRONZE|STEEL)_STORAGE_BOX\);\n    envProxy\.registerColorProvider\(\(stack, tintIndex\) -> (?:10454093|13158600|16744448|8421504), Ic2Items\.(?:WOODEN|IRON|BRONZE|STEEL)_STORAGE_BOX\);\n', '', text)
    anchor = '    envProxy.registerColorProvider(SideProxyClient::getFluidCellTintColor, Ic2Items.EMPTY_CELL);\n'
    if text.count(anchor) != 1:
        raise ValueError("Expected storage color registration anchor is missing")
    registrations = ''
    for name, (constant, color) in STORAGE.items():
        if "assets/ic2/textures/block/" + name + ".png" in selected:
            registrations += f'    envProxy.registerColorProvider(\n        (state, world, pos, tintIndex) -> {color}, Ic2Blocks.{constant}_STORAGE_BOX);\n'
            registrations += f'    envProxy.registerColorProvider((stack, tintIndex) -> {color}, Ic2Items.{constant}_STORAGE_BOX);\n'
    return text.replace(anchor, anchor + registrations)


def prepare(selection):
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"), object_pairs_hook=unique_keys)
    mapping = manifest["selectable_legacy_mapping"]
    chosen = validate_selection(selection, mapping)
    selected = set(chosen)
    baseline = load_baseline()
    archive_path = RESOURCES / manifest["source_archive"]
    if sha(archive_path.read_bytes()) != manifest["source_archive_sha256"]:
        raise ValueError("Original legacy archive is modified")
    changes = {}
    with ZipFile(archive_path) as source:
        source_names = set(source.namelist())
        for name, original in mapping.items():
            modern = baseline.get(name)
            modern_meta = baseline.get(name + ".mcmeta")
            if modern is None and name not in manifest["minecraft_overrides"]:
                raise ValueError(f"Missing pinned modern counterpart: {name}")
            legacy = source.read(original)
            legacy_meta = source.read(original + ".mcmeta") if original + ".mcmeta" in source_names else None
            desired = (legacy, legacy_meta) if name in selected else (modern, modern_meta)
            current = (optional_bytes(target_path(name)), optional_bytes(target_path(name + ".mcmeta")))
            if current not in [(modern, modern_meta), (legacy, legacy_meta)]:
                raise ValueError(f"Refusing to overwrite modified pixels or animation: {name}")
            if name in selected:
                validate_png(legacy)
                if legacy_meta is not None:
                    json.loads(legacy_meta.decode("utf-8"), object_pairs_hook=unique_keys)
            for suffix, value in zip(("", ".mcmeta"), desired):
                path = target_path(name + suffix)
                if optional_bytes(path) != value:
                    changes[path] = value
    client = RESOURCES.parent / "java/ic2/core/proxy/SideProxyClient.java"
    current_client = client.read_text(encoding="utf-8")
    if current_client != storage_colors(current_client, set(manifest["selected_legacy_textures"])):
        raise ValueError("Refusing to overwrite modified storage color registrations")
    desired_client = storage_colors(current_client, selected)
    if desired_client != current_client:
        changes[client] = desired_client.encode("utf-8")
    manifest["selected_legacy_textures"] = sorted(chosen)
    data = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode()
    if MANIFEST.read_bytes() != data:
        changes[MANIFEST] = data
    return chosen, changes, ["Unchecked paths return to modern textures; models, fluid colors and registry IDs stay modern."]


def apply_changes(changes):
    """Stage every write before replacing files; retain originals for error rollback."""
    prepared, originals, replaced = {}, {}, []
    try:
        for path, data in changes.items():
            originals[path] = optional_bytes(path)
            if data is not None:
                path.parent.mkdir(parents=True, exist_ok=True)
                fd, temporary = tempfile.mkstemp(prefix=".texture-selection-", dir=path.parent)
                prepared[path] = Path(temporary)
                with os.fdopen(fd, "wb") as output:
                    output.write(data)
        for path, data in changes.items():
            if data is None:
                path.unlink(missing_ok=True)
            else:
                os.replace(prepared[path], path)
            replaced.append(path)
    except OSError:
        for path in reversed(replaced):
            data = originals[path]
            if data is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(data)
        raise
    finally:
        for temporary in prepared.values():
            temporary.unlink(missing_ok=True)


def self_test():
    global RESOURCES, MANIFEST
    crop = "assets/ic2/textures/block/crop/ender_blossom_3.png"
    valid = {"schema": 2, "base_commit": BASE, "use_legacy": []}
    assert validate_selection(valid, {crop}) == []
    invalid = [{**valid, "schema": True}, {**valid, "schema": 1}, {**valid, "base_commit": "wrong"}, {**valid, "use_legacy": "wrong"}, {"schema": 1, "base_commit": BASE, "keep_modern": []}, *[{**valid, "use_legacy": value} for value in [[crop, crop], [None], ["../outside.png"], ["assets/ic2/textures/unknown.png"]]]]
    for selection in invalid:
        try:
            validate_selection(selection, {crop})
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid selection accepted")
    watched = [MANIFEST, RESOURCES / crop, RESOURCES.parent / "java/ic2/core/proxy/SideProxyClient.java"]
    before = [(file.read_bytes(), file.stat().st_mtime_ns) for file in watched]
    chosen = [crop, "assets/ic2/textures/block/bronze_storage_box.png", "assets/minecraft/textures/item/copper_ingot.png"]
    with tempfile.TemporaryDirectory() as temporary:
        file = Path(temporary) / "selection.json"
        file.write_text(json.dumps({**valid, "use_legacy": chosen}))
        subprocess.run([sys.executable, __file__, str(file)], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
        real_resources, real_manifest = RESOURCES, MANIFEST
        try:
            fixture = Path(temporary) / "fixture"
            shutil.copytree(RESOURCES, fixture / "resources")
            shutil.copyfile(MANIFEST, fixture / "manifest.json")
            client = fixture / "java/ic2/core/proxy/SideProxyClient.java"
            client.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(RESOURCES.parent / "java/ic2/core/proxy/SideProxyClient.java", client)
            RESOURCES, MANIFEST = fixture / "resources", fixture / "manifest.json"
            apply_changes(prepare(valid)[1])
            assert prepare(valid)[1] == {}, "Empty selection must equal modern baseline"
            _, changes, _ = prepare({**valid, "use_legacy": chosen})
            apply_changes(changes)
            manifest = json.loads(MANIFEST.read_bytes())
            assert manifest["selected_legacy_textures"] == sorted(chosen)
            with ZipFile(RESOURCES / manifest["source_archive"]) as old:
                assert (RESOURCES / crop).read_bytes() == old.read("assets/ic2/textures/blocks/crop/ender_blossom_4.png")
            colors = client.read_text()
            assert "Ic2Blocks.BRONZE_STORAGE_BOX" in colors and "Ic2Blocks.WOODEN_STORAGE_BOX" not in colors
            assert prepare({**valid, "use_legacy": chosen})[1] == {}, "Repeat must be idempotent"
            _, changes, _ = prepare(valid)
            apply_changes(changes)
            assert (RESOURCES / crop).read_bytes() == load_baseline()[crop]
            assert not (RESOURCES / chosen[2]).exists(), "Unchecked copper must use Minecraft"
            assert client.read_bytes() == (real_resources.parent / "java/ic2/core/proxy/SideProxyClient.java").read_bytes()
            assert prepare(valid)[1] == {}
            (RESOURCES / crop).write_bytes(b"modified")
            try:
                prepare(valid)
            except ValueError:
                pass
            else:
                raise AssertionError("Modified pixels were overwritten")
            first, second = fixture / "first", fixture / "second"
            first.write_bytes(b"original"); second.write_bytes(b"original")
            replace = os.replace
            count = 0

            def fail_second(source, destination):
                nonlocal count
                count += 1
                if count == 2:
                    raise OSError("Simulated write failure")
                replace(source, destination)

            try:
                with patch("os.replace", fail_second):
                    apply_changes({first: b"new", second: b"new"})
            except OSError:
                pass
            else:
                raise AssertionError("Write failure ignored")
            assert first.read_bytes() == second.read_bytes() == b"original"
        finally:
            RESOURCES, MANIFEST = real_resources, real_manifest
    assert before == [(file.read_bytes(), file.stat().st_mtime_ns) for file in watched]
    print("PASS: schema2/invalid selections, dry run, isolated legacy choices, ender blossom3→old4, repeat, uncheck→modern, modified-pixel refusal and rollback; real resources unchanged.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("selection", nargs="?", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            if args.selection or args.apply:
                parser.error("--self-test cannot be combined with selection or --apply")
            self_test()
            return
        if args.selection is None:
            parser.error("Provide an exported schema2 selection.json")
        selection = json.loads(args.selection.read_text(encoding="utf-8"), object_pairs_hook=unique_keys)
        chosen, changes, messages = prepare(selection)
        for message in messages:
            print(message)
        for path, data in changes.items():
            print(("REMOVE " if data is None else "WRITE  ") + str(path.relative_to(ROOT)))
        print(f"{'APPLY' if args.apply else 'DRY RUN'}: {len(chosen)} legacy choices, {len(changes)} file changes. Full declarative selection.")
        if args.apply:
            apply_changes(changes)
    except (ValueError, UnicodeError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(2, f"Selection rejected: {error}\n")


if __name__ == "__main__":
    main()
