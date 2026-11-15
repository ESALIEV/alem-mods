# Пересобрать каталог по ВСЕМ архивам в mods/ (его запускает GitHub сам, см. .github/workflows/catalog.yml).
#  • новый архив → запись в catalog.json + картинки в previews/<id>/;
#  • архив обновлён (другая контрольная сумма) → запись обновляется;
#  • архив удалён → запись и картинки удаляются.
# Всё о моде берётся из его mod.json — моддер пишет это сам (см. README, раздел «Для моддеров»).
import os, io, json, glob, shutil, subprocess, sys, hashlib

os.chdir(os.path.dirname(os.path.abspath(__file__)))
cat = json.load(io.open('catalog.json', encoding='utf-8')) if os.path.exists('catalog.json') else {'mods': []}
zips = sorted(z.replace(os.sep, '/') for z in glob.glob('mods/*.zip'))

# удалённые архивы — из каталога
keep = []
for e in cat['mods']:
    if e.get('zip') in zips or str(e.get('zip', '')).startswith('https://'):
        keep.append(e)
    else:
        shutil.rmtree(os.path.join('previews', e['id']), ignore_errors=True)
        print('Убран:', e['id'])
cat['mods'] = keep
io.open('catalog.json', 'w', encoding='utf-8').write(json.dumps(cat, ensure_ascii=False, indent=2))

# новые и изменённые архивы
known = {e.get('zip'): e.get('sha256') for e in cat['mods']}
for z in zips:
    sha = hashlib.sha256(open(z, 'rb').read()).hexdigest()
    if known.get(z) == sha:
        continue
    r = subprocess.run([sys.executable, 'add_mod.py', z], capture_output=True, text=True, encoding='utf-8')
    print(r.stdout.strip() or r.stderr.strip())

# ── сборки модов (packs/<id>.json) — в catalog.json рядом с модами (15.11.2026) ──
cat = json.load(io.open('catalog.json', encoding='utf-8'))
ids = {m['id'] for m in cat.get('mods', [])}
packs = []
for f in sorted(glob.glob('packs/*.json')):
    try:
        pk = json.load(io.open(f, encoding='utf-8-sig'))
    except Exception as ex:
        print('Сборка не разобралась:', f, ex); continue
    mods = [m for m in pk.get('mods', []) if m in ids]
    if not pk.get('id') or not mods:
        continue
    packs.append({k: pk[k] for k in ('id', 'name', 'nameEn', 'author', 'desc', 'descEn', 'version') if pk.get(k)} | {'mods': mods})
if packs or cat.get('packs'):
    cat['packs'] = packs
    io.open('catalog.json', 'w', encoding='utf-8').write(json.dumps(cat, ensure_ascii=False, indent=2))
    print('Сборок:', len(packs))
