# Добавить мод в каталог мастерской: python add_mod.py mods/имя.zip
# Читает mod.json из архива, считает размер и контрольную сумму, пишет запись в catalog.json.
import sys, json, zipfile, hashlib, os, io
zp = sys.argv[1]
with zipfile.ZipFile(zp) as z:
    names = [n for n in z.namelist() if n.endswith('mod.json')]
    if not names: sys.exit('В архиве нет mod.json')
    info = json.loads(z.read(sorted(names, key=len)[0]).decode('utf-8-sig'))
sha = hashlib.sha256(open(zp, 'rb').read()).hexdigest()
cat = json.load(io.open('catalog.json', encoding='utf-8'))
e = next((m for m in cat['mods'] if m['id'] == info['id']), None)
if e is None:
    e = {'id': info['id']}; cat['mods'].append(e)
e.update({'name': info.get('name', info['id']), 'author': info.get('author', ''),
          'version': info.get('version', '1.0'), 'desc': info.get('desc', ''),
          'zip': zp.replace('\', '/'), 'size': os.path.getsize(zp), 'sha256': sha})
e.setdefault('nameEn', ''); e.setdefault('descEn', ''); e.setdefault('minGame', '')
io.open('catalog.json', 'w', encoding='utf-8').write(json.dumps(cat, ensure_ascii=False, indent=2))
print('Готово:', info['id'], info.get('version'))
