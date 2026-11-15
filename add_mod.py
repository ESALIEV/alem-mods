# Добавить или обновить мод в мастерской:  python add_mod.py mods/имя.zip
#
# Что делает:
#  • читает mod.json из архива (id, name, author, version, desc, requires);
#  • вынимает картинки preview.png, preview1..3.png (и icon.png) в previews/<id>/ — их покажет мастерская;
#  • сам определяет категорию по файлам мода (weapons.json → «Оружие» и т. д.);
#  • считает размер и контрольную сумму, ставит дату обновления;
#  • пишет запись в catalog.json. Поля, которые вы дописали руками (nameEn, descEn, rating,
#    featured, changelog, category...), при обновлении НЕ затираются.
#
# После запуска залейте на GitHub: catalog.json, папку previews и сам архив в mods/.
import sys, json, zipfile, hashlib, os, io, datetime

CATS = [  # (файл в моде, категория) — первая найденная становится главной
    ('weapons.json', 'weapons'), ('apparel.json', 'apparel'), ('furniture.json', 'buildings'),
    ('buildings.json', 'buildings'), ('animals.json', 'animals'), ('wild_animals.json', 'animals'),
    ('enemies.json', 'enemies'), ('events.json', 'events'), ('missions.json', 'events'),
    ('foods.json', 'items'), ('resources.json', 'items'), ('recipes.json', 'items'),
    ('biomes.json', 'world'), ('structures.json', 'world'), ('techs.json', 'tech'),
    ('pawns.json', 'people'), ('needs.json', 'people'), ('spells.json', 'magic'),
]

zp = sys.argv[1].replace(chr(92), '/')
with zipfile.ZipFile(zp) as z:
    names = z.namelist()
    mj = sorted([n for n in names if n.replace(chr(92), '/').split('/')[-1].lower() == 'mod.json'], key=len)
    if not mj: sys.exit('В архиве нет mod.json')
    root = mj[0][:-len('mod.json')]          # мод может лежать в папке внутри архива
    info = json.loads(z.read(mj[0]).decode('utf-8-sig'))
    mid = info['id']
    rel = [n[len(root):] for n in names if n.startswith(root)]
    low = [r.lower() for r in rel]
    tags = []
    for f, c in CATS:
        if f in low and c not in tags: tags.append(c)
    if any(r.endswith('.lua') for r in low) and 'scripts' not in tags: tags.append('scripts')
    if not tags: tags.append('other')
    # картинки
    out = os.path.join('previews', mid)
    os.makedirs(out, exist_ok=True)
    images = []
    for pic in ['preview.png', 'preview1.png', 'preview2.png', 'preview3.png', 'preview.jpg', 'preview1.jpg', 'preview2.jpg', 'preview3.jpg']:
        if pic in low:
            src = root + rel[low.index(pic)]
            dst = os.path.join(out, pic)
            open(dst, 'wb').write(z.read(src))
            images.append('previews/%s/%s' % (mid, pic))
    icon = ''
    if 'icon.png' in low:
        open(os.path.join(out, 'icon.png'), 'wb').write(z.read(root + rel[low.index('icon.png')]))
        icon = 'previews/%s/icon.png' % mid
    elif images:
        icon = images[0]

sha = hashlib.sha256(open(zp, 'rb').read()).hexdigest()
cat = json.load(io.open('catalog.json', encoding='utf-8'))
e = next((m for m in cat['mods'] if m['id'] == mid), None)
fresh = e is None
if fresh:
    e = {'id': mid}; cat['mods'].append(e)
old_ver = e.get('version')
e.update({'name': info.get('name', mid), 'author': info.get('author', ''),
          'version': info.get('version', '1.0'), 'desc': info.get('desc', ''),
          'zip': zp, 'size': os.path.getsize(zp), 'sha256': sha,
          'images': images, 'icon': icon, 'tags': tags,
          'requires': info.get('requires') or []})
# необязательные поля, которые моддер пишет в mod.json сам — они главнее автоопределения
for k in ['nameEn', 'descEn', 'minGame', 'changelog', 'changelogEn']:
    if info.get(k): e[k] = info[k]
if info.get('category'): e['category'] = info['category']
elif fresh or e.get('category') in (None, '', 'other'): e['category'] = tags[0]
if old_ver != e['version'] or fresh:
    e['updated'] = datetime.date.today().isoformat()
for k, v in [('nameEn', ''), ('descEn', ''), ('minGame', ''), ('category', tags[0]), ('rating', 0),
             ('featured', False), ('changelog', ''), ('changelogEn', ''), ('added', datetime.date.today().isoformat())]:
    e.setdefault(k, v)
io.open('catalog.json', 'w', encoding='utf-8').write(json.dumps(cat, ensure_ascii=False, indent=2))
print('Готово:', mid, e['version'], '| категория:', e['category'], '| картинок:', len(images))
