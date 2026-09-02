from flask import Flask, render_template, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from pathlib import Path
import sqlite3, json, uuid

BASE = Path(__file__).resolve().parent
DB = BASE / 'mobiles.db'
UPLOADS = BASE / 'static' / 'uploads'
UPLOADS.mkdir(parents=True, exist_ok=True)
app = Flask(__name__)

ALLOWED = {'png','jpg','jpeg','webp','gif','pdf'}

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn

def init_db():
    with get_db() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS entregas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            documento_path TEXT NOT NULL,
            data_entrega TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS mobiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entrega_id INTEGER NOT NULL,
            numero TEXT NOT NULL,
            FOREIGN KEY (entrega_id) REFERENCES entregas(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_mobiles_numero ON mobiles(numero);
        CREATE INDEX IF NOT EXISTS idx_mobiles_entrega ON mobiles(entrega_id);
        ''')

def normalize(v):
    return ' '.join(str(v or '').strip().split())

def allowed_file(name):
    return '.' in name and name.rsplit('.', 1)[1].lower() in ALLOWED

@app.get('/')
def index():
    return render_template('index.html')

@app.post('/api/entregas')
def criar_entrega():
    nome = normalize(request.form.get('nome'))
    try:
        quantidade = int(request.form.get('quantidade', '0'))
    except ValueError:
        quantidade = 0
    try:
        numeros = [normalize(x) for x in json.loads(request.form.get('numeros', '[]'))]
    except Exception:
        numeros = []
    arquivo = request.files.get('documento')
    if not nome:
        return jsonify(error='Informe o nome do responsável.'), 400
    if quantidade < 1 or quantidade > 50 or len(numeros) != quantidade or any(not x for x in numeros):
        return jsonify(error='Informe corretamente a quantidade e os números dos mobiles.'), 400
    if len(set(numeros)) != len(numeros):
        return jsonify(error='Não repita o mesmo número de mobile nesta entrega.'), 400
    if not arquivo or not arquivo.filename:
        return jsonify(error='Selecione a foto/scan do documento.'), 400
    if not allowed_file(arquivo.filename):
        return jsonify(error='Formato de arquivo não permitido.'), 400
    ext = arquivo.filename.rsplit('.', 1)[1].lower()
    filename = f'{uuid.uuid4().hex}.{ext}'
    relpath = filename
    arquivo.save(UPLOADS / filename)
    try:
        with get_db() as db:
            cur = db.execute('INSERT INTO entregas (nome, documento_path) VALUES (?, ?)', (nome, relpath))
            entrega_id = cur.lastrowid
            db.executemany('INSERT INTO mobiles (entrega_id, numero) VALUES (?, ?)', [(entrega_id, n) for n in numeros])
        return jsonify(ok=True, entrega_id=entrega_id)
    except Exception as exc:
        try: (UPLOADS / filename).unlink(missing_ok=True)
        except Exception: pass
        return jsonify(error=f'Erro ao salvar no banco: {exc}'), 500

@app.get('/api/entregas/buscar')
def buscar():
    numero = normalize(request.args.get('numero'))
    if not numero:
        return jsonify([])
    with get_db() as db:
        rows = db.execute('''
            SELECT e.id AS entrega_id, e.nome, e.documento_path, e.data_entrega,
                   m.numero,
                   (SELECT COUNT(*) FROM mobiles mh WHERE mh.numero = m.numero) AS total_retiradas,
                   (SELECT GROUP_CONCAT(m2.numero, '||') FROM mobiles m2 WHERE m2.entrega_id = e.id) AS mobiles
            FROM mobiles m
            JOIN entregas e ON e.id = m.entrega_id
            WHERE m.numero = ?
            ORDER BY e.data_entrega DESC, e.id DESC
        ''', (numero,)).fetchall()
    out=[]
    for r in rows:
        d=dict(r)
        d['mobiles'] = d['mobiles'].split('||') if d['mobiles'] else []
        out.append(d)
    return jsonify(out)

@app.get('/uploads/<path:filename>')
def uploads(filename):
    return send_from_directory(UPLOADS, filename)

if __name__ == '__main__':
    init_db()
    print('Controle de Mobiles iniciado em http://127.0.0.1:5000')
    import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
    
