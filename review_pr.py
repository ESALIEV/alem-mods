# Проверка заявки моддера (Pull Request). Запускает GitHub сам — .github/workflows/review.yml.
#
# ВАЖНО ПРО БЕЗОПАСНОСТЬ: код из заявки НИКОГДА не запускается. Архивы читаются как данные
# (git show → файл → zipfile), распаковываются только после проверки путей.
#
# Решение (пишется в decision.txt):
#   auto   — обновление уже одобренного мода от его же автора, все проверки пройдены → принять само;
#   manual — новый мод, чужой мод, или нейросеть заподозрила картинку → ждёт автора игры;
#   reject — запрещённые файлы, вирус, битый mod.json, версия не поднята… → моддер исправляет.
# Текст для заявки — в review.md (по-русски и по-английски).
#
# Режим --register: после принятия заявки записать автора НОВЫХ модов в owners.json.
import argparse, io, json, os, re, subprocess, sys, zipfile, shutil

MAX_ZIP = 60 * 1024 * 1024          # архив
MAX_UNPACKED = 250 * 1024 * 1024     # распакованный (защита от «zip-бомбы»)
ALLOWED = {'.json', '.lua', '.png', '.jpg', '.jpeg', '.wav', '.ogg', '.mp3', '.txt', '.md'}
NSFW_CLASSES = {'FEMALE_BREAST_EXPOSED', 'FEMALE_GENITALIA_EXPOSED', 'MALE_GENITALIA_EXPOSED',
                'BUTTOCKS_EXPOSED', 'ANUS_EXPOSED'}
NSFW_SCORE = 0.45                    # ниже — не считаем (ложные срабатывания на пиксель-арте)
MIN_IMG = 48                         # меньше 48 px — иконки и тайлы, нейросеть по ним гадает
NAME_RE = re.compile(r'^[A-Za-z0-9_.\-]+\.zip$')

def sh(*a):
    return subprocess.run(a, capture_output=True, text=True, encoding='utf-8', errors='replace')

def load(path, default):
    return json.load(io.open(path, encoding='utf-8')) if os.path.exists(path) else default

def vkey(v):
    out = []
    for p in str(v or '').split('.'):
        m = re.match(r'\d+', p)
        out.append(int(m.group()) if m else 0)
    return out

def magic_ok(name, data):
    ext = os.path.splitext(name)[1].lower()
    if ext == '.png':  return data[:8] == b'\x89PNG\r\n\x1a\n'
    if ext in ('.jpg', '.jpeg'): return data[:3] == b'\xff\xd8\xff'
    if ext == '.wav':  return data[:4] == b'RIFF' and data[8:12] == b'WAVE'
    if ext == '.ogg':  return data[:4] == b'OggS'
    if ext == '.mp3':  return data[:3] == b'ID3' or (len(data) > 1 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0)
    # текстовые: должны читаться как UTF-8 и не содержать нулевых байтов (не переименованная программа)
    if b'\x00' in data[:4096]: return False
    try: data[:65536].decode('utf-8-sig'); return True
    except UnicodeDecodeError: return False

def review(args):
    catalog = load('catalog.json', {'mods': []})
    owners = load('owners.json', {})
    by_id = {m['id']: m for m in catalog['mods']}
    by_zip = {m.get('zip'): m for m in catalog['mods']}

    diff = sh('git', 'diff', '--no-renames', '--name-status', 'origin/main...' + args.pr_ref).stdout.strip().splitlines()
    rejects, manual, notes, oks = [], [], [], []
    zips = []
    for line in diff:
        parts = line.split('\t')
        st, path = parts[0], parts[-1]
        if path.startswith('mods/') and path.endswith('.zip') and st[0] in 'AM':
            zips.append(path)
        elif path.startswith('mods/') and st[0] == 'D':
            manual.append('удаление `%s` — решает автор игры / deleting a mod needs the game author' % path)
        else:
            rejects.append('в заявке можно менять только архивы в `mods/`, а изменён `%s` / only `mods/*.zip` may be changed' % path)
    if not zips and not rejects and not manual:
        rejects.append('в заявке нет архива мода / no mod archive in this pull request')

    work = 'pr_unpack'
    shutil.rmtree(work, ignore_errors=True); os.makedirs(work)
    images = []
    for zp in zips:
        name = os.path.basename(zp)
        if not NAME_RE.match(name):
            rejects.append('`%s`: имя архива — латиница, цифры, _ - . без пробелов / archive name: latin letters, digits, _ - . no spaces' % name)
            continue
        data = subprocess.run(['git', 'show', '%s:%s' % (args.pr_ref, zp)], capture_output=True).stdout
        if len(data) > MAX_ZIP:
            rejects.append('`%s`: больше 60 МБ / larger than 60 MB' % name); continue
        local = os.path.join(work, name); open(local, 'wb').write(data)
        try: z = zipfile.ZipFile(local)
        except zipfile.BadZipFile:
            rejects.append('`%s`: это не zip-архив / not a zip archive' % name); continue
        bad = False; total = 0; mj = None
        for info in z.infolist():
            n = info.filename
            if n.endswith('/'): continue
            if n.startswith('/') or '..' in n.replace('\\', '/').split('/') or ':' in n:
                rejects.append('`%s`: опасный путь внутри архива `%s` / unsafe path' % (name, n)); bad = True; break
            total += info.file_size
            ext = os.path.splitext(n)[1].lower()
            if ext not in ALLOWED:
                rejects.append('`%s`: запрещённый файл `%s` (можно: %s) / file type not allowed' % (name, n, ' '.join(sorted(ALLOWED)))); bad = True; continue
            head = z.open(info).read(65536)
            if not magic_ok(n, head):
                rejects.append('`%s`: файл `%s` не тот, за кого себя выдаёт / file content does not match its extension' % (name, n)); bad = True
            if n.replace(chr(92), '/').split('/')[-1].lower() == 'mod.json' and (mj is None or len(n) < len(mj)): mj = n
        if total > MAX_UNPACKED:
            rejects.append('`%s`: распакованный больше 250 МБ / unpacked size over 250 MB' % name); continue
        if bad: continue
        if mj is None:
            rejects.append('`%s`: нет mod.json / no mod.json' % name); continue
        try: info = json.loads(z.read(mj).decode('utf-8-sig'))
        except Exception as ex:
            rejects.append('`%s`: mod.json не читается: %s / mod.json is not valid JSON' % (name, ex)); continue
        miss = [k for k in ('id', 'name', 'version') if not str(info.get(k) or '').strip()]
        if miss:
            rejects.append('`%s`: в mod.json не заполнено: %s / missing in mod.json' % (name, ', '.join(miss))); continue
        mid = info['id']
        dest = os.path.join(work, 'x_' + re.sub(r'[^A-Za-z0-9_-]', '_', mid))
        z.extractall(dest)
        for root, _, files in os.walk(dest):
            for f in files:
                if f.lower().endswith(('.png', '.jpg', '.jpeg')): images.append((name, os.path.join(root, f), os.path.relpath(os.path.join(root, f), dest)))
        root_files = {os.path.basename(i.filename).lower() for i in z.infolist()}
        if 'preview.png' not in root_files and 'preview.jpg' not in root_files:
            notes.append('`%s`: нет preview.png — в Мастерской будет «Нет картинки» / no preview.png' % name)
        if not info.get('category'):
            notes.append('`%s`: нет `category` — раздел определится сам / no category, it will be guessed' % name)

        old = by_id.get(mid)
        same_zip = by_zip.get(zp)
        if same_zip and same_zip['id'] != mid:
            rejects.append('`%s`: этот архив уже занят модом `%s` / this archive name belongs to another mod' % (name, same_zip['id'])); continue
        if old is None:
            manual.append('`%s` — **новый мод** `%s`: первый раз его проверяет автор игры / new mod, the game author reviews it first' % (name, mid))
            continue
        if vkey(info['version']) <= vkey(old.get('version')):
            rejects.append('`%s`: версия %s не выше прошлой %s — поднимите `version` в mod.json / bump the version' % (name, info['version'], old.get('version'))); continue
        if old.get('zip') != zp:
            manual.append('`%s`: мод `%s` раньше лежал в `%s` — переименование решает автор игры / archive renamed' % (name, mid, old.get('zip')))
            continue
        owner = owners.get(mid)
        if not owner or owner.lower() != args.author.lower():
            manual.append('`%s`: мод `%s` записан за другим автором (%s) — решает автор игры / the mod belongs to another author' % (name, mid, owner or '—'))
            continue
        oks.append('`%s`: обновление `%s` %s → %s' % (name, mid, old.get('version'), info['version']))

    # антивирус (ClamAV): база может не скачаться — тогда честно пишем, что не проверено
    if not rejects and os.path.isdir(work) and shutil.which('clamscan'):
        r = sh('clamscan', '-r', '--infected', '--no-summary', work)
        if r.returncode == 1:
            rejects.append('антивирус нашёл угрозу / antivirus found a threat:\n```\n%s\n```' % r.stdout.strip()[:1500])
        elif r.returncode != 0:
            manual.append('антивирус не смог проверить архив — проверьте вручную / antivirus check failed')
    elif not rejects:
        manual.append('антивирус недоступен — проверьте вручную / antivirus unavailable')

    # нейросеть по картинкам
    flagged = []
    if not rejects and images:
        try:
            from nudenet import NudeDetector
            from PIL import Image
            det = NudeDetector()
            for zname, path, rel in images:
                try:
                    with Image.open(path) as im:
                        if min(im.size) < MIN_IMG: continue
                except Exception:
                    continue
                for d in det.detect(path):
                    if d.get('class') in NSFW_CLASSES and d.get('score', 0) >= NSFW_SCORE:
                        flagged.append('`%s` → `%s` (%s %.0f%%)' % (zname, rel, d['class'], d['score'] * 100)); break
        except Exception as ex:
            manual.append('проверка картинок не запустилась (%s) — посмотрите их вручную / image check failed' % ex)
    if flagged:
        manual.append('нейросеть просит посмотреть картинки / please look at these images:\n' + '\n'.join('- ' + f for f in flagged))

    decision = 'reject' if rejects else 'manual' if manual else 'auto'
    md = ['### Проверка мода / Mod check']
    if decision == 'auto':   md.append('✅ **Принято автоматически** — через пару минут обновление будет в Мастерской. / Accepted automatically.')
    if decision == 'manual': md.append('⏸ **Ждёт проверки автора игры.** / Waiting for the game author.')
    if decision == 'reject': md.append('❌ **Не принято — исправьте и загрузите архив заново в эту же заявку.** / Not accepted - fix and upload again to this pull request.')
    for title, items in (('Ошибки / Errors', rejects), ('Нужна ручная проверка / Manual review', manual), ('Всё в порядке / OK', oks), ('Советы / Tips', notes)):
        if items: md.append('\n**%s**\n' % title + '\n'.join('- ' + i for i in items))
    io.open('review.md', 'w', encoding='utf-8').write('\n'.join(md) + '\n')
    io.open('decision.txt', 'w').write(decision)
    print(decision); print('\n'.join(md))

def register(args):
    # после принятия заявки: новые моды записать за автором заявки
    owners = load('owners.json', {})
    changed = False
    for zp in args.files:
        if not (zp.startswith('mods/') and zp.endswith('.zip') and os.path.exists(zp)): continue
        with zipfile.ZipFile(zp) as z:
            mj = sorted([n for n in z.namelist() if n.replace(chr(92), '/').split('/')[-1].lower() == 'mod.json'], key=len)
            if not mj: continue
            mid = json.loads(z.read(mj[0]).decode('utf-8-sig')).get('id')
        if mid and mid not in owners:
            owners[mid] = args.author; changed = True; print('владелец', mid, '=', args.author)
    if changed:
        io.open('owners.json', 'w', encoding='utf-8').write(json.dumps(owners, ensure_ascii=False, indent=2, sort_keys=True))

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--pr-ref'); ap.add_argument('--author', required=True)
    ap.add_argument('--register', action='store_true'); ap.add_argument('files', nargs='*')
    a = ap.parse_args()
    register(a) if a.register else review(a)
