import zipfile, shutil, itertools
import sqlite3 as sql
import json, os, datetime, re, tempfile
import csv, string, random, hashlib
import click

from os.path import join as p_join


def unpack(src_path, unpack_dir):
    src_path, unpack_dir = os.path.abspath(src_path), os.path.abspath(unpack_dir)
    with zipfile.ZipFile(src_path, 'r') as z:

        # unpack media
        media = z.read('media').decode()
        media = json.loads(media)

        media_dir = p_join(unpack_dir, 'media')
        os.makedirs(media_dir)
        for i in media:
            fm = z.read(i)
            media_path = p_join(media_dir, media[i])
            with open(media_path, 'wb') as f:
                f.write(fm)

        # unpack others
        db = z.read('collection.anki2')

        with open(p_join(unpack_dir, 'collection.anki2'), 'w+b') as df:
            df.write(db)

        with sql.connect(df.name) as dbconn:
            # 获取设置
            cursor = dbconn.cursor()
            models = cursor.execute('SELECT models FROM col').fetchone()
            models = json.loads(models[0])

            # debug
            # debug_models, debug_decks = cursor.execute('SELECT models, decks FROM col').fetchone()
            # with open(p_join(unpack_dir, 'models.json'), 'w') as f:
            #     f.write(debug_models)
            # with open(p_join(unpack_dir, 'decks.json'), 'w') as f:
            #     f.write(debug_decks)

            # unpack each model
            for (mid, model) in models.items():
                model_dir = p_join(unpack_dir, model['name'])
                os.makedirs(model_dir)
                # get csv headline
                flds_name = sorted(model['flds'], key=lambda x: x['ord'])
                flds_name = list(map(lambda x: x['name'], flds_name))
                flds_name.append('tags')
                # csv content
                notes = cursor.execute('SELECT flds, tags \
                                       FROM notes \
                                       WHERE mid = ?',
                                       (mid,)).fetchall()
                notes = list(map(lambda x: x[0].split('\x1f') + [x[1].strip()], notes))
                # write to file
                with open(p_join(model_dir, 'notes.csv'), 'w', encoding='utf8', newline='\n') as f:
                    w = csv.writer(f, dialect='excel-tab')
                    w.writerow(flds_name)
                    w.writerows(notes)
                # tmpls
                for tmpl in model['tmpls']:
                    with open(p_join(model_dir, '{}.txt'.format(tmpl['name'])), 'w', encoding='utf8',
                              newline='\n') as f:
                        f.write(tmpl['qfmt'])
                        f.write('\n<====================>\n')
                        f.write('<====================>\n')
                        f.write(tmpl['afmt'])
                # css
                with open(p_join(model_dir, 'cards.css'), 'w', encoding='utf8', newline='\n') as f:
                    f.write(model['css'])
        dbconn.close()
        os.remove(p_join(unpack_dir, 'collection.anki2'))


def timestamp():
    return int(datetime.datetime.now().timestamp())


def msstamp():
    return int(datetime.datetime.now().timestamp() * 1000)


def make_conf(curModel=None, curDeck=1, activeDecks=None):
    activeDecks = activeDecks if activeDecks else [curDeck]
    conf = {
        'activeDecks': activeDecks,
        'addToCur': True,
        'collapseTime': 1200,
        'curDeck': curDeck,
        'curModel': curModel if curModel else str(msstamp()),
        'dueCounts': True,
        'estTimes': True,
        'newBury': True,
        'newSpread': 0,
        'nextPos': 1,
        'sortBackwards': False,
        'sortType': 'noteFld',
        'timeLim': 0}
    return conf


def make_dconf(deck_id=1):
    return {'{}'.format(deck_id):
                {'autoplay': True,
                 'id': 1,
                 'lapse': {
                     'delays': [10],
                     'leechAction': 0,
                     'leechFails': 8,
                     'minInt': 1,
                     'mult': 0},
                 'maxTaken': 60,
                 'mod': 0,
                 'name': 'Default',
                 'new': {
                     'bury': True,
                     'delays': [1, 10],
                     'initialFactor': 2500,
                     'ints': [1, 4, 7],
                     'order': 1,
                     'perDay': 20,
                     'separate': True},
                 'replayq': True,
                 'rev': {
                     'bury': True,
                     'ease4': 1.3,
                     'fuzz': 0.05,
                     'ivlFct': 1,
                     'maxIvl': 36500,
                     'minSpace': 1,
                     'perDay': 100},
                 'timer': 0,
                 'usn': 0}}


def make_decks(deck_id=1, name=None, mod=None):
    decks = {
        "{}".format(deck_id): {
            "name": name if name else "default",
            "extendRev": 50,
            "usn": 0,
            "collapsed": False,
            "newToday": [
                0,
                0
            ],
            "timeToday": [
                0,
                0
            ],
            "dyn": 0,
            "extendNew": 10,
            "conf": 1,
            "revToday": [
                0,
                0
            ],
            "lrnToday": [
                0,
                0
            ],
            "id": 1,
            "mod": mod if mod else timestamp(),
            "desc": ""
        }
    }
    return decks


def check_cloze(tmpl_text):
    return True if re.match('{{cloze:[^}]+}}', tmpl_text) else False


def make_flds(flds_list):
    flds = list([{
                     "name": name,
                     "media": [],
                     "sticky": False,
                     "rtl": False,
                     "ord": i,
                     "font": "Arial",
                     "size": 20
                 } for i, name in enumerate(flds_list)])
    return flds


def make_req(tmpls):
    return list([[i, "any", [0]] for i in range(len(tmpls))])


def make_header(src_path, tags=True):
    with open(src_path, encoding='utf8') as csvfile:
        reader = csv.reader(csvfile, dialect='excel-tab')
        header = next(reader)

        if tags and len(header) > 1 and header[-1] == 'tags':
            header = header[:-1]
        return make_flds(header)


def make_tmpls(tmpls_dict, did=1):
    '''{"卡片 1": "text1", "卡片 2": "text2"}'''
    tmpls = []
    for (i, (name, text)) in enumerate(tmpls_dict.items()):
        tmpl = {
            'afmt': "",
            'bafmt': "",
            'bqfmt': "",
            'did': did,
            'name': "{}".format(name),
            'ord': i,
            'qfmt': ""
        }
        m = re.fullmatch(r'(.*)(\n[<]={10,}[>])\2\n(.*)',
                         text, flags=re.DOTALL)
        if m:
            r = m.groups()
            if len(r) == 3:
                tmpl["qfmt"] = r[0]
                tmpl["afmt"] = r[2]
        tmpls.append(tmpl)
    if tmpls:
        tmpls[0]['did'] = None

    return tmpls


#
# tmpls_list (name, qfmt, afmt)
def make_model(mid, flds, tmpls, name=None, css=None, mod=None):
    CSS = ".card {\n font-family: arial;\n font-size: 20px;\n text-align: center;\n" \
          " color: black;\n background-color: white;\n}\n\n.cloze {\n font-weight: bold;\n color: blue;\n}"
    CSS = css if css else CSS
    latexPre = "\\documentclass[12pt]{article}\n\\special{papersize=3in,5in}\n" \
               "\\usepackage[utf8]{inputenc}\n\\usepackage{amssymb,amsmath}\n\\pagestyle{empty}\n" \
               "\\setlength{\\parindent}{0in}\n\\begin{document}\n"

    model = {
        "id": mid,
        "vers": [],
        "tags": [],
        "did": 1,
        "usn": -1,
        "sortf": 0,
        "latexPre": latexPre,
        "latexPost": "\\end{document}",

        "name": name if name else str(msstamp()),
        "flds": flds,
        "tmpls": tmpls,
        "mod": mod if mod else timestamp(),
        "type": 0,
        "css": CSS,
    }

    cloze_flag = False
    for tmpl in model['tmpls']:
        if check_cloze(tmpl['afmt']) or check_cloze(tmpl['qfmt']):
            cloze_flag = True
            break
    if cloze_flag:
        model['type'] = 1
        model['tmpls'] = [tmpl]
        model['tmpls'][0]['ord'] = 0
    else:
        model['req'] = make_req(model['tmpls'])
    return str(mid), model


def make_model_from_dir(dir_path, csv_path=None, tmpl_paths=None,
                        css_path=None, name=None, temp_dir=None):
    def read_text(path):
        with open(path, encoding='utf8') as f:
            text = f.read()
        return text

    mid = msstamp()
    _csv_path = csv_path if csv_path else p_join(dir_path, 'notes.csv')
    flds = make_header(_csv_path)
    tmpl_paths = tmpl_paths if tmpl_paths else filter( \
        lambda p: p.endswith('.txt'), os.listdir(dir_path))

    tmpl_paths = (p_join(dir_path, tmpl_path) for tmpl_path in tmpl_paths)
    _tmpls_dict = {
        os.path.basename(tmpl_path)[:-4]: read_text(tmpl_path)
        for tmpl_path in tmpl_paths
        }
    tmpls = make_tmpls(_tmpls_dict)
    name = name if name else os.path.basename(dir_path)
    if css_path:
        css = read_text(css_path)
    else:
        _css_path = tuple(filter(lambda p: p.endswith('.css'), os.listdir(dir_path)))
        css = read_text(p_join(dir_path, _css_path[0])) if _css_path else None

    model = make_model(mid, flds, tmpls, name=name, css=css)
    if temp_dir:
        with open(p_join(temp_dir, str(mid) + '.csv'), 'w', newline='\n', encoding='utf8') as csv:
            with open(_csv_path, newline='\n', encoding='utf8') as f:
                csv.write(f.read())
    return model


def make_models_from_dirs(dir_paths, temp_dir=None):
    models = (make_model_from_dir(path, temp_dir=temp_dir) for path in dir_paths)
    models = {mid: context for mid, context in models}
    return dict(models)


# make col
def make_col(models, decks=None, conf=None, tags=None, dconf=None, crt=None, name='default'):
    crt = crt if crt else timestamp()
    col = {
        'id': 1,
        'crt': crt,
        'mod': crt * 1000,
        'scm': crt * 1000,
        'ver': 11, #第11版
        'dty': 0,
        'usn': 0,
        'ls': 0,
        'conf': conf if conf else make_conf(),
        'models': models,
        'decks': decks if decks else make_decks(name=name),
        'dconf': dconf if dconf else make_dconf(),
        'tags': tags if tags else {},
    }
    return col


# without media
def make_col_from_dir(dir_path, temp_dir=None, name='default'):
    isdir = lambda p: os.path.isdir(p_join(dir_path, p))
    mod_paths = [p_join(dir_path, mod_path)
                 for mod_path
                 in os.listdir(dir_path)
                 if isdir(mod_path) and mod_path != 'media']
    models = make_models_from_dirs(mod_paths, temp_dir=temp_dir)
    col = make_col(models, name=name)
    return col


def guid():
    # 64 位
    chars = string.ascii_letters + string.digits + "!#"
    g = ""
    x = random.randint(1, 2 ** 60)
    while x > 0:
        g += chars[x & 63]
        x = x >> 6
    return g


id_start = msstamp()
n_id_gen = itertools.count(id_start)
c_id_gen = itertools.count(id_start)


def gen_note(mid, flds, tags=""):
    #     print(flds)
    n_id = next(n_id_gen)
    n_guid = guid()
    n_mid = mid
    n_mod = n_id // 1000
    n_usn = -1
    n_tags = tags
    n_flds = '\x1f'.join(flds)
    n_sfld = flds[0]
    n_csum = int(hashlib.sha1(bytes(flds[0], 'utf8')).hexdigest()[:8], 16)
    n_flags = 0
    n_data = ''
    return (n_id, n_guid, n_mid,
            n_mod, n_usn, n_tags,
            n_flds, n_sfld, n_csum,
            n_flags, n_data)


def gen_note_cards(nid, ords, did=1):
    cards = []
    for t_ord in ords:
        c_id = next(c_id_gen)
        c_nid = nid
        c_did = did
        c_ord = t_ord
        c_mod = c_id // 1000
        c_usn = -1
        c_type = 0
        c_queue = 0
        c_due = nid - id_start + 1
        c_ivl = 0
        c_factor = 0
        c_reps = 0
        c_lapses = 0
        c_left = 0
        c_odue = 0
        c_odid = 0
        c_flags = 0
        c_data = ''
        cards.append((c_id, c_nid, c_did, c_ord, c_mod,
                      c_usn, c_type, c_queue, c_due, c_ivl,
                      c_factor, c_reps, c_lapses, c_left, c_odue,
                      c_odid, c_flags, c_data))

    return cards


def cloze_ords(note):
    flds = note[6].split('\x1f')
    ords = set()
    for fld in flds:
        for t_ord in re.findall('{{c(\d+)::.+?}}', fld):
            ords.add(int(t_ord) - 1)
    if not ords:
        ords = {0, }
    return ords


def gen_cards(notes, model):
    if model['type'] == 1:
        cards_list = [gen_note_cards(note[0], cloze_ords(note), did=model['did'])
                      for note in notes]
    else:
        ords = set(map(lambda x: x['ord'], model['tmpls']))
        cards_list = [gen_note_cards(note[0], ords, did=model['did'])
                      for note in notes]
    cards = itertools.chain(*cards_list)
    return list(cards)


def read_csv(mid, src_path, tags=True):
    if os.path.isdir(src_path):
        src_path = p_join(src_path, '{}.csv'.format(mid))

    with open(src_path, encoding='utf8') as csvfile:
        reader = csv.reader(csvfile, dialect='excel-tab')
        header = next(reader)
        notes = [note for note in reader]
        if tags and len(header) > 1 and header[-1] == 'tags':
            header = header[:-1]
            create_cards = lambda note: gen_note(mid, note[:-1], note[-1])
        else:
            create_cards = lambda note: gen_note(mid, note, '')
        notes = [create_cards(note) for note in notes]

    return list(notes)


def package_media(media_dir=None, zfile=None):

    def write_media(zfile, media):
        zfile.writestr('media', json.dumps(media))
        for i, m in media.items():
            zfile.write(p_join(media_dir, m), arcname=i)

    media_dir = os.path.abspath(media_dir)
    if media_dir and os.path.isdir(media_dir):
        media = dict(((str(i), m)
                      for i, m
                      in enumerate(os.listdir(media_dir))
                      if os.path.isfile(p_join(media_dir, m))))
    else:
        media = dict()

    if isinstance(zfile, zipfile.ZipFile):
        write_media(zfile, media)
    else:
        if not zfile:
            zpath='default.apkg'
        elif os.path.isdir(os.path.abspath(zfile)):
            zpath= p_join(os.path.abspath(zfile), 'default.apkg')
        else:
            zpath = zfile
        zpath = os.path.abspath(zpath)
        if os.path.commonpath([zpath, media_dir]) == media_dir:
            zpath = os.path.abspath(p_join(media_dir, '..', 'default.apkg'))
        with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED) as zfile:
            write_media(zfile, media)


def read_csvs(models, src_path, tags=True):
    models = list([mid for mid in models.values()])
    notes = []
    cards = []
    for model in models:
        mod_notes = read_csv(model['id'], src_path=src_path, tags=tags)
        mod_cards = gen_cards(mod_notes, model)
        notes.append(mod_notes)
        cards.append(mod_cards)
    notes = list(itertools.chain(*notes))
    cards = list(itertools.chain(*cards))

    return notes, cards


NEW_DB = '''
CREATE TABLE col (
    id              integer primary key,
    crt             integer not null,
    mod             integer not null,
    scm             integer not null,
    ver             integer not null,
    dty             integer not null,
    usn             integer not null,
    ls              integer not null,
    conf            text not null,
    models          text not null,
    decks           text not null,
    dconf           text not null,
    tags            text not null
);
CREATE TABLE notes (
    id              integer primary key,   /* 0 */
    guid            text not null,         /* 1 */
    mid             integer not null,      /* 2 */
    mod             integer not null,      /* 3 */
    usn             integer not null,      /* 4 */
    tags            text not null,         /* 5 */
    flds            text not null,         /* 6 */
    sfld            integer not null,      /* 7 */
    csum            integer not null,      /* 8 */
    flags           integer not null,      /* 9 */
    data            text not null          /* 10 */
);
CREATE TABLE cards (
    id              integer primary key,   /* 0 */
    nid             integer not null,      /* 1 */
    did             integer not null,      /* 2 */
    ord             integer not null,      /* 3 */
    mod             integer not null,      /* 4 */
    usn             integer not null,      /* 5 */
    type            integer not null,      /* 6 */
    queue           integer not null,      /* 7 */
    due             integer not null,      /* 8 */
    ivl             integer not null,      /* 9 */
    factor          integer not null,      /* 10 */
    reps            integer not null,      /* 11 */
    lapses          integer not null,      /* 12 */
    left            integer not null,      /* 13 */
    odue            integer not null,      /* 14 */
    odid            integer not null,      /* 15 */
    flags           integer not null,      /* 16 */
    data            text not null          /* 17 */
);
CREATE TABLE revlog (
    id              integer primary key,
    cid             integer not null,
    usn             integer not null,
    ease            integer not null,
    ivl             integer not null,
    lastIvl         integer not null,
    factor          integer not null,
    time            integer not null,
    type            integer not null
);
CREATE TABLE graves (
    usn             integer not null,
    oid             integer not null,
    type            integer not null
);
CREATE INDEX ix_notes_usn on notes (usn);
CREATE INDEX ix_cards_usn on cards (usn);
CREATE INDEX ix_revlog_usn on revlog (usn);
CREATE INDEX ix_cards_nid on cards (nid);
CREATE INDEX ix_cards_sched on cards (did, queue, due);
CREATE INDEX ix_revlog_cid on revlog (cid);
CREATE INDEX ix_notes_csum on notes (csum);
'''


def create_db(col, src_path, db_path):
    models = col['models']
    if os.path.isdir(db_path):
        db_path = p_join(os.path.abspath(db_path), 'collection.anki2')

    if os.path.isfile(db_path):
        os.remove(db_path)

    conn = sql.connect(db_path)

    cursor = conn.cursor()
    cursor.executescript(NEW_DB)
    conn.commit()

    cursor.execute('INSERT INTO col(id,crt,mod,scm,ver,'
                   'dty,usn,ls,conf,models,'
                   'decks,dconf,tags)'
                   ' VALUES (?,?,?,?,?,'
                   '?,?,?,?,?,'
                   '?,?,?)',
                   (col['id'], col['crt'], col['mod'], col['scm'], col['ver'],
                   col['dty'], col['usn'], col['ls'], json.dumps(col['conf']), json.dumps(col['models']),
                   json.dumps(col['decks']), json.dumps(col['dconf']), json.dumps(col['tags'])))
    notes, cards = read_csvs(models, src_path)
    cursor.executemany("INSERT INTO notes(id, guid, mid, mod, usn, tags, flds, sfld, csum, flags, data)"
                       " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", notes)
    cursor.executemany("INSERT INTO cards"
                       "(id,nid,did,ord,mod,"
                       "usn,type,queue,due,ivl,"
                       "factor,reps,lapses,left,odue,"
                       "odid,flags,data)"
                       " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", cards)


    conn.commit()
    conn.close()


def package(taget_path, src_path, temp_dir, media_dir=None, deck_name='default'):
    ''''''
    col = make_col_from_dir(src_path, temp_dir, name=deck_name)
    create_db(col, temp_dir, temp_dir)
    if not media_dir:
        media_dir = p_join(src_path, 'media')

    zpath = p_join(os.path.abspath(temp_dir), deck_name+'.apkg')
    with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED) as zfile:
        package_media(media_dir=media_dir, zfile=zfile)
        zfile.write(p_join(temp_dir, 'collection.anki2'), arcname='collection.anki2')
    shutil.move(zpath, taget_path)


@click.group()
def cli():
    pass


@cli.command("upkg")
@click.argument('apkg_path', nargs=1)
@click.option('-e', '--unpack_dir', help='解压位置', default='.')
def cli_unpack(apkg_path, unpack_dir):
    """解压缩 apkg 文件"""
    unpack(apkg_path, unpack_dir)


@cli.command("pkg")
@click.argument('taget_path')
@click.argument('src_path')
@click.option('-t', '-temp_dir', help='缓存文件夹', default='.')
@click.option('-m', '-media_dir', help='媒体文件夹', default='.')
@click.option('-n', '-deck_name', help='牌组名称，若目标位置包含[name].apkg，牌组名为[name]', default='default')
def cli_package(taget_path, src_path, temp_dir, media_dir, deck_name):
    """打包 apkg 文件"""
    taget_name = os.path.basename(os.path.abspath(taget_path))
    if deck_name == 'default' and len(taget_name)>5 and taget_name.endswith('.apkg'):
        deck_name = taget_name[:-5]
    if os.path.isdir(temp_dir):
        package(taget_path, src_path, temp_dir, media_dir, deck_name)
    else:
        with tempfile.TemporaryDirectory() as tmpdirname:
            package(taget_path, src_path, tmpdirname, media_dir, deck_name)


if __name__ == '__main__':
    cli()
