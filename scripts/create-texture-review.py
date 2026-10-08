#!/usr/bin/env python3
"""Build an offline texture review; requires Pillow (available in Codex's bundled Python)."""

import argparse
import hashlib
import io
import json
import struct
import subprocess
import zipfile
from collections import Counter
from pathlib import Path

try:
    from PIL import Image, PngImagePlugin
except ImportError:
    raise SystemExit("Pillow is required. Run this script with a Python environment that has Pillow, such as Codex's bundled Python.")

ROOT = Path(__file__).resolve().parents[1]
RESOURCES = ROOT / "src/main/resources"
BASE_COMMIT = "417fddb1fd23b926accc02b380cd658121f5c9e1"
DEFAULT_OUTPUT = Path.home() / "Downloads/IC2R-texture-review"

HTML = r'''<!doctype html>
<html lang="ru">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>IC2R — выбор текстур</title>
<style>
:root{color-scheme:dark;font:15px/1.5 system-ui,sans-serif;background:#11161e;color:#eaf0f7}
*{box-sizing:border-box}body{margin:0}button,input,select{font:inherit}button,select,.import{color:inherit;background:#263344;border:1px solid #485c74;border-radius:8px;padding:8px 12px}button,.import{cursor:pointer}button:hover,.import:hover{background:#35475f}a{color:#9dc8ff}header{padding:24px 28px 16px;max-width:1120px;margin:auto}h1{font-size:26px;margin:0 0 6px}p{margin:6px 0;color:#acbdcf}.summary{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}.summary span{background:#1e2937;padding:5px 10px;border-radius:7px}.controls{position:sticky;top:0;z-index:2;background:#151d29f5;border-bottom:1px solid #344458;backdrop-filter:blur(12px);padding:12px 28px}.controls-inner{max-width:1064px;margin:auto;display:flex;gap:10px;align-items:center;flex-wrap:wrap}#search{flex:1;min-width:190px;background:#0c121a;border:1px solid #485c74;border-radius:8px;padding:9px 12px;color:inherit}.filter-label{display:flex;align-items:center;gap:6px;white-space:nowrap}input[type=checkbox]{width:19px;height:19px;accent-color:#8bc4ff}.status{max-width:1064px;margin:8px auto 0;color:#c6d5e5;min-height:23px}.columns{display:grid;grid-template-columns:1fr 1fr;gap:16px;max-width:1064px;margin:16px auto 0;padding:0 16px;color:#c2dcff;font-weight:650}.list{max-width:1120px;margin:auto;padding:10px 28px 28px}.row{border:1px solid #344458;border-radius:12px;background:#182230;margin:0 0 12px;overflow:hidden}.row-head{display:flex;gap:12px;align-items:center;justify-content:space-between;padding:10px 14px;border-bottom:1px solid #304055}.path{font:13px/1.4 ui-monospace,monospace;overflow-wrap:anywhere}.category{font-size:12px;color:#9db4ce;display:block;margin-top:3px}.keep{display:flex;gap:7px;align-items:center;white-space:nowrap;font-size:13px}.keep:has(input:disabled){color:#70839a}.row.checked{border-color:#86bfff;box-shadow:0 0 0 1px #86bfff}.images{display:grid;grid-template-columns:1fr 1fr;gap:16px;padding:14px}.preview{display:flex;min-height:128px;align-items:center;justify-content:center;border-radius:8px;background-color:#29323e;background-image:linear-gradient(45deg,#374250 25%,transparent 25%),linear-gradient(-45deg,#374250 25%,transparent 25%),linear-gradient(45deg,transparent 75%,#374250 75%),linear-gradient(-45deg,transparent 75%,#374250 75%);background-size:20px 20px;background-position:0 0,0 10px,10px -10px,-10px 0;text-decoration:none;padding:8px}.preview img{image-rendering:pixelated;image-rendering:crisp-edges;width:128px;height:128px;max-width:100%;max-height:176px;object-fit:contain}.caption{color:#9eb2c9;font-size:12px;margin:7px 0 0;overflow-wrap:anywhere}.missing{color:#bbcadb;text-align:center;background:#202d3e;line-height:1.45}.empty{padding:50px;text-align:center;color:#bac9db}.hidden,[hidden]{display:none!important}footer{max-width:1064px;margin:0 auto 30px;font-size:13px;color:#9eb2c9;padding:0 16px}@media(max-width:650px){header,.controls{padding-left:14px;padding-right:14px}.list{padding:10px 14px}.row-head{align-items:flex-start;flex-direction:column}.images{gap:8px;padding:9px}.preview{min-height:104px}.columns{font-size:13px;gap:8px}.preview img{max-height:130px}}
</style>
<header>
<h1>Выбери, какие текстуры 1.12.2 перенести</h1>
<p>Слева — исходный IC2R для 1.21.1. Справа — оригинальные текстуры IC2 2.8.222 для 1.12.2, которые можно перенести выборочно.</p>
<p>По умолчанию остаются современные текстуры. Отметь «Перенести 1.12.2» только у нужных, затем экспортируй выбор. Нажатие на изображение открывает его в полном размере.</p>
<div id="summary" class="summary"></div>
</header>
<section class="controls" aria-label="Поиск и выбор">
<div class="controls-inner">
<input id="search" type="search" placeholder="Поиск: drill, quantum, generator…" aria-label="Поиск по пути текстуры">
<select id="category" aria-label="Группа текстур"></select>
<label class="filter-label"><input id="onlyChecked" type="checkbox"> Только отмеченные</label>
<label class="filter-label"><input id="onlyDifferent" type="checkbox" checked> Только отличаются</label>
<button id="export">Экспорт выбора JSON</button>
<button id="importButton">Импорт выбора</button><input id="import" type="file" accept="application/json,.json" hidden>
</div>
<div id="status" class="status" role="status" aria-live="polite"></div>
</section>
<div class="columns"><span>1.21.1 · современная</span><span>1.12.2 · старая</span></div>
<main id="list" class="list"></main>
<div id="empty" class="empty" hidden>Ничего не найдено. Попробуй другой запрос или группу.</div>
<footer>Выбор сохраняется в этом браузере. Для передачи выбора используй JSON. Без флажка остаётся вариант 1.21.1. Новый JSON задаёт полный набор старых текстур для переноса. Старый JSON «Оставить 1.21.1» здесь не импортируется. Здесь показаны файлы текстур; их внешний вид в игре зависит также от моделей, оттенков и анимации. <a href="modern-originals.zip" download>Архив исходных текстур</a>.</footer>
<script>
const DATA = __DATA__;
const SCHEMA = 2;
const BASE_COMMIT = __BASE_COMMIT__;
const STORAGE_KEY = 'ic2r-texture-selection:schema2:' + BASE_COMMIT;
const selectable = new Set(DATA.rows.filter(row => row.selectable).map(row => row.path));
let selected = new Set();
const $ = id => document.getElementById(id);
function parseSelection(value) {
  if (value && value.schema === 1) throw new Error('Старый JSON «Оставить 1.21.1» не подходит для выбора «Перенести 1.12.2» и не импортируется.');
  if (!value || typeof value !== 'object' || Array.isArray(value) || value.schema !== SCHEMA || value.base_commit !== BASE_COMMIT || !Array.isArray(value.use_legacy)) throw new Error('Этот JSON относится к другой версии сравнения.');
  if (value.use_legacy.some(path => typeof path !== 'string' || !selectable.has(path))) throw new Error('В JSON есть неизвестная текстура или файл без современного варианта.');
  if (new Set(value.use_legacy).size !== value.use_legacy.length) throw new Error('В JSON есть повторяющиеся пути.');
  return new Set(value.use_legacy);
}
function selection() {return {schema: SCHEMA, base_commit: BASE_COMMIT, use_legacy: [...selected].sort()};}
function save() {
  try {localStorage.setItem(STORAGE_KEY, JSON.stringify(selection()));} catch (_) { $('status').textContent = 'Браузер не сохраняет выбор локально. Экспортируй JSON, чтобы сохранить его.'; }
}
try {const stored = localStorage.getItem(STORAGE_KEY); if (stored) selected = parseSelection(JSON.parse(stored));} catch (_) {}
const labels = {pairs:'Сравнение 1.21.1 ↔ 1.12.2', added:'Архив 1.12.2 без современного аналога', modern_only:'Современная 1.21.1 без старого аналога', fork:'Добавлена в нашем форке'};
for (const [value,label] of [['pairs','Сравнение'],['all','Все'],['added','Архив без аналога'],['modern_only','Без замены из 1.21.1'],['fork','Текстуры форка']]) {
 const option = new Option(label + ' · ' + (value === 'all' ? DATA.rows.length : DATA.counts[value]), value); $('category').add(option);
}
$('summary').replaceChildren(...[
 `Сравнений: ${DATA.counts.pairs}`, `Архив без аналога: ${DATA.counts.added}`, `Без замены: ${DATA.counts.modern_only}`, `Форк: ${DATA.counts.fork}`, `Совпадают: ${DATA.identical}`
].map(text => {const el=document.createElement('span');el.textContent=text;return el;}));
function picture(row, side) {
 const col=document.createElement('div');
 const preview=document.createElement(row[side] ? 'a' : 'div');preview.className='preview';
 if (row[side]) {
  preview.href=row[side];preview.target='_blank';preview.rel='noopener';
  const img=document.createElement('img');img.src=row[side];img.loading='lazy';img.decoding='async';img.alt=(side==='modern'?'1.21.1: ':'1.12.2: ')+row.path;
  img.width=128;img.height=128;
  preview.append(img);
 } else {
  preview.classList.add('missing');preview.textContent=side==='modern' ? 'В исходном IC2R такого файла нет' : row.category==='modern_only' ? 'В 1.12.2 старого варианта нет' : 'Текстура нашего форка';
 }
 const caption=document.createElement('div');caption.className='caption';
 if(side==='modern') caption.textContent=row.minecraft ? 'Оригинальная текстура Minecraft 1.21.1. Флажок заменит её старым вариантом во всей игре.' : row.modern ? `${row.modern_size[0]} × ${row.modern_size[1]} px · IC2R 1.21.1` : 'Добавленный путь без исходного аналога';
 else caption.textContent=row.category==='modern_only' ? 'Уже используется современная текстура' : row.category==='fork' ? 'Новая служебная текстура форка; не из IC2 1.12.2' : `${row.legacy_size[0]} × ${row.legacy_size[1]} px · ${row.source}`;
 col.append(preview,caption);return col;
}
const fragment=document.createDocumentFragment();
for(const row of DATA.rows) {
 const article=document.createElement('article');article.className='row';
 const head=document.createElement('div');head.className='row-head';
 const name=document.createElement('div');const path=document.createElement('div');path.className='path';path.textContent=row.path;
 const category=document.createElement('span');category.className='category';category.textContent=labels[row.category]+(row.identical?' · пиксели одинаковые':'');name.append(path,category);
 const label=document.createElement('label');label.className='keep';const input=document.createElement('input');input.type='checkbox';input.disabled=!row.selectable;input.checked=selected.has(row.path);input.setAttribute('aria-label','Перенести 1.12.2: '+row.path);
 label.append(input,document.createTextNode(row.selectable?'Перенести 1.12.2':row.category==='modern_only'?'1.21.1 без старого аналога':row.category==='added'?'Архив 1.12.2':'Текстура форка'));
 if(!row.selectable)label.title=row.category==='modern_only'?'В 1.12.2 такого варианта нет':'Архивная текстура без современного аналога; в этом выборе не переносится';
 input.addEventListener('change',()=>{if(input.checked)selected.add(row.path);else selected.delete(row.path);save();filter();});head.append(name,label);
 const images=document.createElement('div');images.className='images';images.append(picture(row,'modern'),picture(row,'legacy'));
 article.append(head,images);row.element=article;row.input=input;fragment.append(article);
}
$('list').append(fragment);
function filter(message='') {
 const query=$('search').value.trim().toLowerCase();const category=$('category').value;let visible=0;
 for(const row of DATA.rows) {
  const checked=selected.has(row.path);row.input.checked=checked;row.element.classList.toggle('checked',checked);
  const show=(category==='all'||row.category===category)&&(!$('onlyChecked').checked||checked)&&(!$('onlyDifferent').checked||!row.identical)&&(!query||row.search.includes(query));
  row.element.hidden=!show;if(show)visible++;
 }
 $('empty').hidden=visible>0;$('status').textContent=(message?message+' ':'')+`Показано ${visible} из ${DATA.rows.length} · Перенести 1.12.2: ${selected.size}`;
}
$('search').addEventListener('input',()=>filter());$('category').addEventListener('change',()=>filter());$('onlyChecked').addEventListener('change',()=>filter());$('onlyDifferent').addEventListener('change',()=>filter());
$('export').addEventListener('click',()=>{const blob=new Blob([JSON.stringify(selection(),null,2)+'\n'],{type:'application/json'});const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download='ic2r-texture-selection.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);filter('Выбор экспортирован.');});
$('importButton').addEventListener('click',()=>$('import').click());
$('import').addEventListener('change',async event=>{const file=event.target.files[0];if(!file)return;try{if(file.size>2*1024*1024)throw new Error('JSON слишком большой.');const imported=parseSelection(JSON.parse(await file.text()));selected=imported;save();filter('Выбор импортирован.');}catch(error){$('status').textContent=error.message;}finally{event.target.value='';}});
console.assert(parseSelection({schema:2,base_commit:BASE_COMMIT,use_legacy:[]}).size===0);
console.assert(selectable.size===DATA.counts.pairs);
filter();
</script>
</html>
'''


def png_size(data):
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "Not a PNG"
    return list(struct.unpack(">II", data[16:24]))


def same_pixels(first, second):
    if first == second:
        return True
    return raw_pixels(first) == raw_pixels(second)


def raw_pixels(data):
    # Compare raw pixels without ICC profiles; the original storage-box profile has a bad CRC.
    cleaned = bytearray(data[:8])
    offset = 8
    while offset < len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        end = offset + length + 12
        assert end <= len(data), "Truncated PNG chunk"
        kind = data[offset + 4 : offset + 8]
        if kind != b"iCCP":
            cleaned.extend(data[offset:end])
        if kind == b"IEND":
            break
        offset = end
    with Image.open(io.BytesIO(cleaned)) as image:
        return image.size, image.convert("RGBA").tobytes()


def check_pixel_comparison():
    image = Image.new("RGBA", (2, 2), (10, 20, 30, 40))
    first, second, different = io.BytesIO(), io.BytesIO(), io.BytesIO()
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("test", "Different PNG metadata, identical pixels")
    image.save(first, format="PNG", compress_level=0)
    image.save(second, format="PNG", compress_level=9, pnginfo=metadata)
    assert first.getvalue() != second.getvalue()
    assert same_pixels(first.getvalue(), second.getvalue())
    bad_icc = b"\x00\x00\x00\x03iCCPbad\x00\x00\x00\x00"
    png_with_bad_profile = first.getvalue()[:33] + bad_icc + first.getvalue()[33:]
    assert same_pixels(first.getvalue(), png_with_bad_profile)
    bad_header = bytearray(first.getvalue())
    bad_header[29] ^= 1
    try:
        raw_pixels(bytes(bad_header))
    except OSError:
        pass
    else:
        raise AssertionError("Critical PNG header CRC must remain validated")
    image.putpixel((0, 0), (11, 20, 30, 40))
    image.save(different, format="PNG")
    assert not same_pixels(first.getvalue(), different.getvalue())
    reshaped = io.BytesIO()
    Image.new("RGBA", (4, 1), (10, 20, 30, 40)).save(reshaped, format="PNG")
    assert not same_pixels(first.getvalue(), reshaped.getvalue())


def generate(output):
    check_pixel_comparison()
    manifest = json.loads((ROOT / "docs/legacy-textures.json").read_text())
    archive = subprocess.check_output(
        ["git", "archive", "--format=zip", BASE_COMMIT, "src/main/resources/assets"],
        cwd=ROOT,
    )
    originals = {}
    with zipfile.ZipFile(io.BytesIO(archive)) as source:
        for info in source.infolist():
            if info.filename.endswith((".png", ".png.mcmeta")):
                originals[info.filename.removeprefix("src/main/resources/")] = source.read(info)
    original_textures = {path for path in originals if path.startswith("assets/ic2/textures/") and path.endswith(".png")}
    mappings = {"assets/ic2/textures/" + path: source for path, source in manifest["mapping"].items()}
    overrides = manifest.get("minecraft_overrides", {})
    mappings.update(overrides)
    selectable_mapping = manifest["selectable_legacy_mapping"]
    mappings.update(selectable_mapping)
    source_archive = Path(manifest["source_archive"])
    if source_archive.is_absolute() or ".." in source_archive.parts:
        raise ValueError("Legacy source archive path must stay inside the resources directory")
    source_bytes = (RESOURCES / source_archive).read_bytes()
    if hashlib.sha256(source_bytes).hexdigest() != manifest["source_archive_sha256"]:
        raise ValueError("Legacy source archive checksum differs")
    with zipfile.ZipFile(io.BytesIO(source_bytes)) as legacy_zip:
        legacy_sources = {source: legacy_zip.read(source) for source in set(mappings.values())}
    builtin_found = False
    cache = Path.home() / ".gradle/caches"
    candidates = [cache / "fabric-loom/1.21.1/neoforge/21.1.233/client-extra.jar", *sorted((cache / "neoformruntime/intermediate_results").glob("stripClient_*_resourcesOutput.jar"))]
    for candidate in candidates:
        if not candidate.is_file():
            continue
        with zipfile.ZipFile(candidate) as client:
            names = set(client.namelist())
            if "version.json" not in names or json.loads(client.read("version.json")).get("id") != "1.21.1":
                continue
            if all(path in names for path in overrides):
                for path in overrides:
                    originals[path] = client.read(path)
                builtin_found = True
                break
    fork_paths = {"assets/ic2/textures/" + path for path in manifest.get("fork_native_textures", {})}
    all_paths = sorted(original_textures | set(mappings) | fork_paths)
    output.mkdir(parents=True, exist_ok=True)
    for side in ("modern", "legacy"):
        (output / side).mkdir(exist_ok=True)
    rows = []
    for path in all_paths:
        assert path.startswith(("assets/ic2/textures/", "assets/minecraft/textures/")) and ".." not in Path(path).parts
        current = RESOURCES / path
        is_minecraft = path in overrides
        category = "pairs" if path in selectable_mapping else "added" if path in mappings and path not in original_textures else "fork" if path in fork_paths else "modern_only"
        modern_data = originals.get(path)
        legacy_data = legacy_sources[mappings[path]] if path in mappings else current.read_bytes() if category == "fork" else None
        row = {"path": path, "source": mappings.get(path, ""), "category": category, "selectable": category == "pairs", "minecraft": is_minecraft, "modern": None, "legacy": None, "identical": bool(modern_data and legacy_data and same_pixels(modern_data, legacy_data))}
        for side, data in (("modern", modern_data), ("legacy", legacy_data)):
            if data:
                destination = output / side / path
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
                row[side] = side + "/" + path
                row[side + "_size"] = png_size(data)
        row["search"] = (path + " " + row["source"]).lower()
        rows.append(row)
    counts = Counter(row["category"] for row in rows)
    assert len({row["path"] for row in rows}) == len(rows)
    assert counts["pairs"] + counts["added"] == manifest["mapped_png_count"] + len(overrides)
    assert counts["modern_only"] == manifest["modern_native_png_count"]
    assert counts["fork"] == manifest.get("fork_native_png_count", 0)
    assert {row["path"] for row in rows if row["selectable"]} == set(selectable_mapping)
    assert all(row["modern"] or row["minecraft"] for row in rows if row["selectable"])
    data = {"rows": rows, "counts": dict(counts), "identical": sum(row["identical"] for row in rows)}
    html = HTML.replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")).replace("__BASE_COMMIT__", json.dumps(BASE_COMMIT))
    (output / "index.html").write_text(html)
    with zipfile.ZipFile(output / "modern-originals.zip", "w", zipfile.ZIP_DEFLATED) as modern_zip:
        for path, content in sorted(originals.items()):
            modern_zip.writestr(path, content)
    sample = {"schema": 2, "base_commit": BASE_COMMIT, "use_legacy": []}
    (output / "ic2r-texture-selection-example.json").write_text(json.dumps(sample, indent=2) + "\n")
    print(json.dumps({"page": str(output / "index.html"), "counts": dict(counts), "identical": data["identical"], "total": len(rows), "original_archive_files": len(originals), "minecraft_builtin_found": builtin_found}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, nargs="?", default=DEFAULT_OUTPUT)
    generate(parser.parse_args().output.resolve())
