#!/usr/bin/env python3
"""Preview or apply an additive selection exported by the offline texture review.

python3 scripts/apply-texture-selection.py selection.json          # dry run
python3 scripts/apply-texture-selection.py selection.json --apply  # write checked paths
python3 scripts/apply-texture-selection.py --self-test

Unchecking a texture in a later export does not undo a previous applied choice.
Minecraft copper choices remove our overrides, so Minecraft supplies those images.
Selected storage boxes receive untinted models because the modern images contain color.
Crop models use selected modern sprites; unchecked stages retain protected legacy copies.
"""
import argparse
import binascii
import hashlib
import json
import os
import re
import shutil
from pathlib import Path, PurePosixPath
import struct
import subprocess
import sys
import tempfile
from zipfile import ZipFile
import zlib
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
RESOURCES = ROOT / "src/main/resources"
MANIFEST = ROOT / "docs/legacy-textures.json"
BASE = "417fddb1fd23b926accc02b380cd658121f5c9e1"
STORAGE_MODELS = {
    "assets/ic2/textures/block/storage_box.png": "assets/ic2/models/block/iron_storage_box.json",
    "assets/ic2/textures/block/wooden_storage_box.png": "assets/ic2/models/block/wooden_storage_box.json",
    "assets/ic2/textures/block/bronze_storage_box.png": "assets/ic2/models/block/bronze_storage_box.json",
    "assets/ic2/textures/block/steel_storage_box.png": "assets/ic2/models/block/steel_storage_box.json",
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key!r}")
        result[key] = value
    return result


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, stderr=subprocess.PIPE)


def validate_selection(selection, allowed):
    if type(selection) is not dict or set(selection) != {"schema", "base_commit", "keep_modern"}:
        raise ValueError("Expected exactly schema, base_commit and keep_modern")
    if type(selection["schema"]) is not int or selection["schema"] != 1 or selection["base_commit"] != BASE:
        raise ValueError("Selection schema or base commit does not match this review")
    chosen = selection["keep_modern"]
    if type(chosen) is not list or any(type(path) is not str for path in chosen):
        raise ValueError("keep_modern must be a list of texture paths")
    if len(chosen) != len(set(chosen)):
        raise ValueError("Duplicate selected texture")
    for path in chosen:
        if PurePosixPath(path).as_posix() != path or ".." in PurePosixPath(path).parts or path not in allowed:
            raise ValueError(f"Texture is not selectable: {path[:200]!r}")
    return chosen


def validate_png(data):
    """Validate chunk CRCs and decoded scanlines without an imaging dependency."""
    if not data.startswith(b"\x89PNG\r\n\x1a\n") or len(data) > 16 * 1024 * 1024:
        raise ValueError("Invalid PNG signature or size")
    offset, image_data, header, ended = 8, bytearray(), None, False
    while offset < len(data):
        if offset + 12 > len(data):
            raise ValueError("Truncated PNG chunk")
        length, kind = struct.unpack(">I4s", data[offset:offset + 8])
        end = offset + 12 + length
        if end > len(data):
            raise ValueError("Truncated PNG payload")
        payload = data[offset + 8:end - 4]
        if binascii.crc32(kind + payload) & 0xFFFFFFFF != struct.unpack(">I", data[end - 4:end])[0]:
            raise ValueError("Invalid PNG chunk CRC")
        if header is None and kind != b"IHDR":
            raise ValueError("PNG must start with IHDR")
        if kind == b"IHDR":
            if header is not None or len(payload) != 13:
                raise ValueError("Invalid PNG header")
            header = struct.unpack(">IIBBBBB", payload)
        elif kind == b"IDAT":
            image_data.extend(payload)
        elif kind == b"IEND":
            if length:
                raise ValueError("Invalid PNG end")
            ended = True
            # Some original IC2R exports retain bytes after their complete PNG image.
            break
        offset = end
    if not ended or not image_data:
        raise ValueError("Incomplete PNG")
    width, height, depth, color, compression, filtering, interlace = header
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
    depths = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8), 4: (8, 16), 6: (8, 16)}
    if not 0 < width <= 16384 or not 0 < height <= 16384 or color not in channels or depth not in depths[color] or compression or filtering or interlace not in (0, 1):
        raise ValueError("Unsupported or invalid PNG header")
    passes = [(0, 0, 1, 1)] if not interlace else [(0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4), (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2)]
    rows = []
    for x, y, step_x, step_y in passes:
        pass_width, pass_height = max(0, (width - x + step_x - 1) // step_x), max(0, (height - y + step_y - 1) // step_y)
        if pass_width:
            rows.extend([1 + (pass_width * channels[color] * depth + 7) // 8] * pass_height)
    expected = sum(rows)
    if expected > 64 * 1024 * 1024:
        raise ValueError("PNG decoded data exceeds 64 MiB")
    decoder = zlib.decompressobj()
    decoded = decoder.decompress(image_data, expected + 1)
    if len(decoded) != expected or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise ValueError("Invalid PNG image stream")
    offset = 0
    for length in rows:
        if decoded[offset] > 4:
            raise ValueError("Invalid PNG scanline filter")
        offset += length


def target_path(name):
    path = RESOURCES / name
    if not path.resolve().is_relative_to(RESOURCES.resolve()):
        raise ValueError("Resource path escapes the project")
    return path


def optional_bytes(path):
    return path.read_bytes() if path.exists() else None


def prepare_crop_models(manifest, baseline_files, source, previous, changes):
    """Keep unchecked legacy stages intact when their texture path is restored."""
    originals = {"assets/ic2/textures/" + path: name for path, name in manifest["mapping"].items()}
    aliases = manifest.setdefault("selection_legacy_aliases", {})
    model_records = manifest.setdefault("modern_model_overrides", {})
    modern = set(manifest["modern_texture_overrides"])
    crop_names = {"eating_plant": "eatingplant", "poppy": "rose", "red_wheat": "redwheat", "sticky_reed": "stickreed"}
    ages = {}
    for original in source.namelist():
        match = re.fullmatch(r"assets/ic2/textures/blocks/crop/(.+)_(\d+)\.png", original)
        if match and not (match[1] == "reed" and match[2] == "33"):
            ages.setdefault(match[1], []).append(int(match[2]))
    for repository_path in sorted(baseline_files):
        if not repository_path.startswith("src/main/resources/assets/ic2/models/block/crop/") or not repository_path.endswith(".json"):
            continue
        model_name = repository_path.removeprefix("src/main/resources/")
        baseline = json.loads(git("show", BASE + ":" + repository_path))
        legacy = json.loads(json.dumps(baseline))
        for key, ref in legacy.get("textures", {}).items():
            match = re.fullmatch(r"ic2:block/crop/(.+)_(\d+)", ref)
            if match:
                name = crop_names.get(match[1], match[1])
                if name in ages:
                    stage = min(int(match[2]) + (min(ages[name]) != 0), max(ages[name]))
                    legacy["textures"][key] = f"ic2:block/crop/{name}_{stage}"

        def desired(selected):
            model = json.loads(json.dumps(legacy))
            for key, ref in legacy.get("textures", {}).items():
                baseline_ref = baseline["textures"][key]
                baseline_target = "assets/ic2/textures/" + baseline_ref.removeprefix("ic2:") + ".png"
                legacy_target = "assets/ic2/textures/" + ref.removeprefix("ic2:") + ".png"
                if baseline_target in selected:
                    model["textures"][key] = baseline_ref
                elif legacy_target in selected:
                    alias = "assets/ic2/textures/block/crop/selection_legacy/" + Path(legacy_target).name
                    model["textures"][key] = "ic2:" + alias.removeprefix("assets/ic2/textures/").removesuffix(".png")
                    original = originals[legacy_target]
                    data = source.read(original)
                    meta = source.read(original + ".mcmeta") if original + ".mcmeta" in source.namelist() else None
                    for target, value in [(alias, data), (alias + ".mcmeta", meta)]:
                        current = optional_bytes(target_path(target))
                        if current is not None and current != value:
                            raise ValueError(f"Refusing to overwrite modified legacy crop alias: {target}")
                        if current != value:
                            changes[target_path(target)] = value
                    aliases[alias] = {"source": original, "sha256": sha(data), "mcmeta_sha256": sha(meta) if meta is not None else None}
            return model

        before = desired(set(previous))
        after = desired(modern)
        path = target_path(model_name)
        current = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_keys)
        if current not in [legacy, before]:
            raise ValueError(f"Refusing to overwrite modified crop model: {model_name}")
        if current != after:
            data = (json.dumps(after, indent=2) + "\n").encode()
            changes[path] = data
            model_records[model_name] = {"base_commit": BASE, "sha256": sha(data)}


def prepare(selection):
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"), object_pairs_hook=unique_keys)
    baseline_files = set(git("ls-tree", "-r", "--name-only", BASE).decode("utf-8").splitlines())
    mappings = {"assets/ic2/textures/" + name: original for name, original in manifest["mapping"].items()}
    mappings.update(manifest["minecraft_overrides"])
    allowed = {name for name in mappings if name.startswith("assets/minecraft/") or "src/main/resources/" + name in baseline_files}
    chosen = validate_selection(selection, allowed)
    archive_path = RESOURCES / manifest["source_archive"]
    if sha(archive_path.read_bytes()) != manifest["source_archive_sha256"]:
        raise ValueError("Original legacy archive is modified")
    overrides = manifest.setdefault("modern_texture_overrides", {})
    previous = dict(overrides)
    changes, messages = {}, []
    with ZipFile(archive_path) as source:
        for name in chosen:
            destination = target_path(name)
            legacy = source.read(mappings[name])
            legacy_meta = source.read(mappings[name] + ".mcmeta") if mappings[name] + ".mcmeta" in source.namelist() else None
            minecraft = name.startswith("assets/minecraft/")
            modern = None if minecraft else git("show", BASE + ":src/main/resources/" + name)
            modern_meta = None if minecraft or "src/main/resources/" + name + ".mcmeta" not in baseline_files else git("show", BASE + ":src/main/resources/" + name + ".mcmeta")
            if modern is not None:
                try:
                    validate_png(modern)
                except (ValueError, zlib.error) as error:
                    raise ValueError(f"Malformed original modern PNG: {name}: {error}") from error
            for meta in (legacy_meta, modern_meta):
                if meta is not None:
                    json.loads(meta.decode("utf-8"), object_pairs_hook=unique_keys)
            entry = {"base_commit": BASE, "removed": True} if minecraft else {"base_commit": BASE, "sha256": sha(modern), "mcmeta_sha256": sha(modern_meta) if modern_meta is not None else None}
            prior = overrides.get(name)
            current = (optional_bytes(destination), optional_bytes(target_path(name + ".mcmeta")))
            known = [(legacy, legacy_meta)]
            if prior and all(prior.get(key) == value for key, value in entry.items()):
                known.append((modern, modern_meta))
            if current not in known:
                raise ValueError(f"Refusing to overwrite modified pixels or animation: {name}")
            if name in STORAGE_MODELS:
                model_name = STORAGE_MODELS[name]
                model_path = target_path(model_name)
                texture = name.removeprefix("assets/ic2/textures/").removesuffix(".png")
                model = (json.dumps({"parent": "minecraft:block/cube_all", "textures": {"all": "ic2:" + texture}}, indent=2) + "\n").encode()
                old_model = git("show", BASE + ":src/main/resources/" + model_name)
                known_models = [old_model]
                if prior and prior.get("untinted_model") == {"path": model_name, "sha256": sha(model)}:
                    known_models.append(model)
                if model_path.read_bytes() not in known_models:
                    raise ValueError(f"Refusing to overwrite modified storage model: {model_name}")
                if model_path.read_bytes() != model:
                    changes[model_path] = model
                entry["untinted_model"] = {"path": model_name, "sha256": sha(model)}
                messages.append(f"Untinted storage box model: {model_name}")
            for path, value in [(destination, modern), (target_path(name + ".mcmeta"), modern_meta)]:
                if optional_bytes(path) != value:
                    changes[path] = value
            overrides[name] = entry
        if any(name.startswith("assets/ic2/textures/block/crop/") for name in chosen):
            prepare_crop_models(manifest, baseline_files, source, previous, changes)
            messages.append("Selected crop stages use modern references; unchecked stages retain protected legacy frames.")
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode()
    if chosen and MANIFEST.read_bytes() != manifest_bytes:
        changes[MANIFEST] = manifest_bytes
    return chosen, changes, messages


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
    path = "assets/ic2/textures/block/bronze_storage_box.png"
    valid = {"schema": 1, "base_commit": BASE, "keep_modern": []}
    assert validate_selection(valid, {path}) == []
    invalid = [{**valid, "schema": True}, {**valid, "schema": 2}, {**valid, "base_commit": "wrong"}, {**valid, "keep_modern": "wrong"}, {**valid, "extra": 1}, *[{**valid, "keep_modern": value} for value in [[path, path], [None], ["../outside.png"], ["assets/ic2/textures/unknown.png"]]]]
    for selection in invalid:
        try:
            validate_selection(selection, {path})
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid selection was accepted")
    png = (RESOURCES / "assets/ic2/textures/gui/creative_section.png").read_bytes()
    validate_png(png)
    try:
        validate_png(png[:-1])
    except ValueError:
        pass
    else:
        raise AssertionError("Malformed PNG was accepted")
    watched = [MANIFEST, RESOURCES / path, RESOURCES / STORAGE_MODELS[path]]
    before = [(file.read_bytes(), file.stat().st_mtime_ns) for file in watched]
    with tempfile.TemporaryDirectory() as temporary:
        file = Path(temporary) / "selection.json"
        for chosen in ([], [path]):
            file.write_text(json.dumps({**valid, "keep_modern": chosen}), encoding="utf-8")
            subprocess.run([sys.executable, __file__, str(file)], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    assert before == [(file.read_bytes(), file.stat().st_mtime_ns) for file in watched], "Dry run mutated the project"
    real_resources, real_manifest = RESOURCES, MANIFEST
    with tempfile.TemporaryDirectory() as temporary:
        try:
            RESOURCES = Path(temporary) / "resources"
            MANIFEST = Path(temporary) / "legacy-textures.json"
            MANIFEST.write_bytes(real_manifest.read_bytes())
            manifest = json.loads(real_manifest.read_bytes())
            selected = [path, "assets/ic2/textures/block/crop/acacia_sapling_1.png", "assets/minecraft/textures/item/copper_ingot.png"]
            files = [manifest["source_archive"], *selected, STORAGE_MODELS[path]]
            for name in files:
                destination = RESOURCES / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(real_resources / name, destination)
            shutil.copytree(real_resources / "assets/ic2/models/block/crop", RESOURCES / "assets/ic2/models/block/crop")
            fixture_selection = {**valid, "keep_modern": selected}
            _, changes, _ = prepare(fixture_selection)
            apply_changes(changes)
            assert (RESOURCES / path).read_bytes() == git("show", BASE + ":src/main/resources/" + path)
            assert not (RESOURCES / selected[2]).exists()
            assert len(json.loads(MANIFEST.read_bytes())["modern_texture_overrides"]) == 3
            crop = json.loads((RESOURCES / "assets/ic2/models/block/crop/acacia_sapling_0.json").read_bytes())
            assert crop["textures"]["cross"] == "ic2:block/crop/selection_legacy/acacia_sapling_1"
            crop = json.loads((RESOURCES / "assets/ic2/models/block/crop/acacia_sapling_1.json").read_bytes())
            assert crop["textures"]["cross"] == "ic2:block/crop/acacia_sapling_1"
            with ZipFile(RESOURCES / manifest["source_archive"]) as original:
                assert (RESOURCES / "assets/ic2/textures/block/crop/selection_legacy/acacia_sapling_1.png").read_bytes() == original.read("assets/ic2/textures/blocks/crop/acacia_sapling_1.png")
            _, changes, _ = prepare(fixture_selection)
            assert changes == {}, "Applying the same selection must be idempotent"
            assert prepare({**valid, "keep_modern": []})[1] == {}, "Empty selection must not undo prior choices"
            png = RESOURCES / path
            png.write_bytes(b"modified")
            try:
                prepare(fixture_selection)
            except ValueError:
                pass
            else:
                raise AssertionError("Modified target pixels were overwritten")
            first, second = Path(temporary) / "first", Path(temporary) / "second"
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
                raise AssertionError("Simulated write failure was ignored")
            assert first.read_bytes() == second.read_bytes() == b"original", "Failed apply must restore originals"
        finally:
            RESOURCES, MANIFEST = real_resources, real_manifest
    assert before == [(file.read_bytes(), file.stat().st_mtime_ns) for file in watched], "Fixture tests touched the project"
    print("PASS: invalid/empty selections, malformed PNG, dry run, isolated crop/storage/copper apply, idempotence, modified-pixel refusal and write-error rollback; real project files unchanged.")


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
            parser.error("Provide an exported selection.json")
        selection = json.loads(args.selection.read_text(encoding="utf-8"), object_pairs_hook=unique_keys)
        chosen, changes, messages = prepare(selection)
        for message in messages:
            print(message)
        for path, data in changes.items():
            print(("REMOVE " if data is None else "WRITE  ") + str(path.relative_to(ROOT)))
        print(f"{'APPLY' if args.apply else 'DRY RUN'}: {len(chosen)} checked textures, {len(changes)} file changes. Choices are additive; unchecked paths remain unchanged.")
        if args.apply:
            apply_changes(changes)
    except (ValueError, UnicodeError, OSError, subprocess.CalledProcessError, zlib.error) as error:
        parser.exit(2, f"Selection rejected: {error}\n")


if __name__ == "__main__":
    main()
