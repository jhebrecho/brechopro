from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import sqlite3, os, shutil, hashlib, secrets
from pathlib import Path
from datetime import datetime, date
import qrcode

BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = Path(os.getenv('BRECHOPRO_STORAGE_DIR', str(BASE_DIR / 'data'))).resolve()
DB_PATH = STORAGE_DIR / 'brechopro.db'
UPLOAD_DIR = STORAGE_DIR / 'uploads'
LABEL_DIR = STORAGE_DIR / 'labels'
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
LABEL_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title='BrechóPro MVP v2')
app.add_middleware(SessionMiddleware, secret_key=os.getenv('BRECHOPRO_SECRET', secrets.token_hex(32)))
app.mount('/static', StaticFiles(directory=str(BASE_DIR / 'static')), name='static')
app.mount('/uploads', StaticFiles(directory=str(UPLOAD_DIR)), name='uploads')
app.mount('/labels', StaticFiles(directory=str(LABEL_DIR)), name='labels')
templates = Jinja2Templates(directory=str(BASE_DIR / 'templates'))


def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    return con


def password_hash(password: str, salt: str = '') -> str:
    return hashlib.sha256((salt + password).encode('utf-8')).hexdigest()


def add_column_if_missing(con, table, column, definition):
    cols = [r['name'] for r in con.execute(f'PRAGMA table_info({table})').fetchall()]
    if column not in cols:
        con.execute(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = db()
    con.executescript('''
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      email TEXT UNIQUE NOT NULL,
      password_hash TEXT NOT NULL,
      salt TEXT NOT NULL,
      role TEXT NOT NULL DEFAULT 'admin',
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS consignors (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL, phone TEXT, email TEXT,
      commission_percent REAL NOT NULL DEFAULT 50,
      active INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS customers (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL, phone TEXT, email TEXT,
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS items (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      code TEXT UNIQUE, name TEXT NOT NULL, category TEXT, brand TEXT, size TEXT,
      price REAL NOT NULL, cost REAL NOT NULL DEFAULT 0,
      consignor_id INTEGER, commission_percent REAL,
      status TEXT NOT NULL DEFAULT 'em_estoque', image_path TEXT, notes TEXT,
      created_at TEXT NOT NULL,
      FOREIGN KEY(consignor_id) REFERENCES consignors(id)
    );
    CREATE TABLE IF NOT EXISTS sales (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      customer_id INTEGER, subtotal REAL NOT NULL, discount REAL NOT NULL DEFAULT 0,
      total REAL NOT NULL, payment_method TEXT NOT NULL, notes TEXT,
      created_at TEXT NOT NULL,
      FOREIGN KEY(customer_id) REFERENCES customers(id)
    );
    CREATE TABLE IF NOT EXISTS sale_items (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      sale_id INTEGER NOT NULL, item_id INTEGER NOT NULL, price REAL NOT NULL,
      consignor_amount REAL NOT NULL DEFAULT 0,
      FOREIGN KEY(sale_id) REFERENCES sales(id), FOREIGN KEY(item_id) REFERENCES items(id)
    );
    CREATE TABLE IF NOT EXISTS expenses (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      description TEXT NOT NULL, amount REAL NOT NULL, category TEXT,
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS payouts (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      consignor_id INTEGER NOT NULL, amount REAL NOT NULL, note TEXT,
      created_at TEXT NOT NULL,
      FOREIGN KEY(consignor_id) REFERENCES consignors(id)
    );
    CREATE TABLE IF NOT EXISTS cash_closings (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      closing_date TEXT NOT NULL,
      expected_cash REAL NOT NULL DEFAULT 0,
      counted_cash REAL NOT NULL DEFAULT 0,
      difference REAL NOT NULL DEFAULT 0,
      note TEXT,
      created_at TEXT NOT NULL
    );
    ''')
    # Migrations for databases created by v1
    add_column_if_missing(con, 'consignors', 'active', 'INTEGER NOT NULL DEFAULT 1')
    add_column_if_missing(con, 'items', 'image_path', 'TEXT')
    add_column_if_missing(con, 'items', 'notes', 'TEXT')
    add_column_if_missing(con, 'sales', 'notes', 'TEXT')
    add_column_if_missing(con, 'expenses', 'category', 'TEXT')

    now = datetime.now().isoformat(timespec='seconds')
    if con.execute('SELECT COUNT(*) c FROM users').fetchone()['c'] == 0:
        admin_email = os.getenv('BRECHOPRO_ADMIN_EMAIL', 'admin@brechopro.local').strip()
        admin_password = os.getenv('BRECHOPRO_ADMIN_PASSWORD', 'admin123')
        salt = secrets.token_hex(8)
        con.execute('INSERT INTO users(name,email,password_hash,salt,role,created_at) VALUES (?,?,?,?,?,?)',
                    ('Administradora',admin_email,password_hash(admin_password, salt),salt,'admin',now))
    demo_data = os.getenv('BRECHOPRO_DEMO_DATA', 'false').lower() in {'1','true','yes','sim'}
    if demo_data and con.execute('SELECT COUNT(*) c FROM consignors').fetchone()['c'] == 0:
        con.execute('INSERT INTO consignors(name,phone,email,commission_percent,created_at) VALUES (?,?,?,?,?)', ('Carla Mendes','(11) 98765-4321','carla@email.com',50,now))
        con.execute('INSERT INTO consignors(name,phone,email,commission_percent,created_at) VALUES (?,?,?,?,?)', ('Mariana Costa','(11) 91234-5678','mariana@email.com',50,now))
        con.execute('INSERT INTO customers(name,phone,email,created_at) VALUES (?,?,?,?)', ('Ana Paula','(11) 99876-5432','ana@email.com',now))
        consignors = con.execute('SELECT id FROM consignors ORDER BY id').fetchall()
        cid, mid = consignors[0]['id'], consignors[1]['id']
        samples = [('Jaqueta Jeans Vintage','Roupas',"Levi's",'M',120,cid),('Vestido Floral','Roupas','Zara','P',95,mid),('Bolsa Couro Marrom','Bolsas','Arezzo','Único',180,cid),('Tênis Branco','Calçados','Adidas','38',150,mid),('Camiseta Estampada','Roupas','Nike','G',70,cid)]
        for i,(name,cat,brand,size,price,cons_id) in enumerate(samples, start=1):
            con.execute('''INSERT INTO items(code,name,category,brand,size,price,consignor_id,commission_percent,status,created_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?)''', (f'P{i:06d}',name,cat,brand,size,price,cons_id,50,'em_estoque',now))
    con.commit(); con.close()


@app.on_event('startup')
def startup(): init_db()


def money(v):
    v = float(v or 0)
    return f"R$ {v:,.2f}".replace(',', 'X').replace('.', ',').replace('X','.')

templates.env.filters['money'] = money


def current_user(request: Request):
    return request.session.get('user')


def guard(request: Request):
    if not current_user(request):
        return RedirectResponse('/login', status_code=303)
    return None


@app.get('/login', response_class=HTMLResponse)
def login_page(request: Request):
    if current_user(request): return RedirectResponse('/', status_code=303)
    return templates.TemplateResponse('login.html', {'request':request, 'error':None})

@app.post('/login', response_class=HTMLResponse)
def login(request: Request, email: str = Form(...), password: str = Form(...)):
    con=db(); u=con.execute('SELECT * FROM users WHERE lower(email)=lower(?)',(email.strip(),)).fetchone(); con.close()
    if not u or password_hash(password,u['salt']) != u['password_hash']:
        return templates.TemplateResponse('login.html', {'request':request,'error':'E-mail ou senha inválidos.'}, status_code=401)
    request.session['user']={'id':u['id'],'name':u['name'],'email':u['email'],'role':u['role']}
    return RedirectResponse('/',status_code=303)

@app.get('/logout')
def logout(request: Request):
    request.session.clear(); return RedirectResponse('/login',status_code=303)


@app.get('/health')
def health():
    return {'status': 'ok'}


@app.get('/', response_class=HTMLResponse)
def dashboard(request: Request):
    if (g:=guard(request)): return g
    con=db(); stats={}
    stats['stock']=con.execute("SELECT COUNT(*) c FROM items WHERE status='em_estoque'").fetchone()['c']
    stats['sold']=con.execute("SELECT COUNT(*) c FROM items WHERE status='vendida'").fetchone()['c']
    stats['sales_total']=con.execute("SELECT COALESCE(SUM(total),0) s FROM sales").fetchone()['s']
    stats['customers']=con.execute("SELECT COUNT(*) c FROM customers").fetchone()['c']
    stats['to_pay']=con.execute('''SELECT COALESCE(SUM(si.consignor_amount),0)-COALESCE((SELECT SUM(amount) FROM payouts),0) s FROM sale_items si''').fetchone()['s'] or 0
    recent=con.execute('''SELECT s.id,s.total,s.payment_method,s.created_at,COALESCE(c.name,'Cliente avulso') customer FROM sales s LEFT JOIN customers c ON c.id=s.customer_id ORDER BY s.id DESC LIMIT 8''').fetchall()
    con.close(); return templates.TemplateResponse('dashboard.html', {'request':request,'stats':stats,'recent':recent,'user':current_user(request)})


@app.get('/estoque', response_class=HTMLResponse)
def estoque(request: Request, q: str = '', status: str = ''):
    if (g:=guard(request)): return g
    con=db(); where=[]; params=[]
    if q:
        where.append('(lower(i.name) LIKE ? OR lower(i.code) LIKE ? OR lower(COALESCE(i.brand,"")) LIKE ?)'); v=f'%{q.lower()}%'; params += [v,v,v]
    if status: where.append('i.status=?'); params.append(status)
    w=('WHERE '+' AND '.join(where)) if where else ''
    items=con.execute(f'''SELECT i.*,COALESCE(c.name,'Próprio') consignor_name FROM items i LEFT JOIN consignors c ON c.id=i.consignor_id {w} ORDER BY i.id DESC''',params).fetchall()
    consignors=con.execute('SELECT * FROM consignors WHERE active=1 ORDER BY name').fetchall(); con.close()
    return templates.TemplateResponse('inventory.html', {'request':request,'items':items,'consignors':consignors,'q':q,'status':status,'user':current_user(request)})

@app.post('/estoque/novo')
async def novo_item(request: Request, name: str=Form(...), category: str=Form(''), brand: str=Form(''), size: str=Form(''), price: float=Form(...), cost: float=Form(0), consignor_id: str=Form(''), commission_percent: float=Form(50), notes: str=Form(''), photo: UploadFile|None=File(None)):
    if (g:=guard(request)): return g
    con=db(); now=datetime.now().isoformat(timespec='seconds'); next_id=con.execute('SELECT COALESCE(MAX(id),0)+1 n FROM items').fetchone()['n']; code=f'P{next_id:06d}'; cid=int(consignor_id) if consignor_id else None
    image_path=None
    if photo and photo.filename:
        ext=Path(photo.filename).suffix.lower() or '.jpg'; filename=f'{code}{ext}'; dest=UPLOAD_DIR/filename
        with dest.open('wb') as f: shutil.copyfileobj(photo.file,f)
        image_path=f'/uploads/{filename}'
    con.execute('''INSERT INTO items(code,name,category,brand,size,price,cost,consignor_id,commission_percent,status,image_path,notes,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',(code,name,category,brand,size,price,cost,cid,commission_percent,'em_estoque',image_path,notes,now)); con.commit(); con.close()
    return RedirectResponse('/estoque',status_code=303)

@app.get('/estoque/{item_id}/editar', response_class=HTMLResponse)
def editar_item_page(request: Request, item_id:int):
    if (g:=guard(request)): return g
    con=db(); item=con.execute('SELECT * FROM items WHERE id=?',(item_id,)).fetchone(); consignors=con.execute('SELECT * FROM consignors WHERE active=1 ORDER BY name').fetchall(); con.close()
    if not item: return RedirectResponse('/estoque',status_code=303)
    return templates.TemplateResponse('item_edit.html', {'request':request,'item':item,'consignors':consignors,'user':current_user(request)})

@app.post('/estoque/{item_id}/editar')
async def editar_item(request: Request, item_id:int, name:str=Form(...), category:str=Form(''), brand:str=Form(''), size:str=Form(''), price:float=Form(...), cost:float=Form(0), consignor_id:str=Form(''), commission_percent:float=Form(50), status:str=Form('em_estoque'), notes:str=Form(''), photo:UploadFile|None=File(None)):
    if (g:=guard(request)): return g
    con=db(); old=con.execute('SELECT * FROM items WHERE id=?',(item_id,)).fetchone(); cid=int(consignor_id) if consignor_id else None; image_path=old['image_path'] if old else None
    if photo and photo.filename and old:
        ext=Path(photo.filename).suffix.lower() or '.jpg'; filename=f"{old['code']}{ext}"; dest=UPLOAD_DIR/filename
        with dest.open('wb') as f: shutil.copyfileobj(photo.file,f)
        image_path=f'/uploads/{filename}'
    con.execute('''UPDATE items SET name=?,category=?,brand=?,size=?,price=?,cost=?,consignor_id=?,commission_percent=?,status=?,image_path=?,notes=? WHERE id=?''',(name,category,brand,size,price,cost,cid,commission_percent,status,image_path,notes,item_id)); con.commit(); con.close(); return RedirectResponse('/estoque',status_code=303)

@app.post('/estoque/{item_id}/excluir')
def excluir_item(request: Request, item_id:int):
    if (g:=guard(request)): return g
    con=db(); sold=con.execute('SELECT COUNT(*) c FROM sale_items WHERE item_id=?',(item_id,)).fetchone()['c']
    if sold==0: con.execute('DELETE FROM items WHERE id=?',(item_id,)); con.commit()
    con.close(); return RedirectResponse('/estoque',status_code=303)

@app.get('/estoque/{item_id}/etiqueta', response_class=HTMLResponse)
def etiqueta(request: Request, item_id:int):
    if (g:=guard(request)): return g
    con=db(); item=con.execute('SELECT * FROM items WHERE id=?',(item_id,)).fetchone(); con.close()
    if not item: return RedirectResponse('/estoque',status_code=303)
    qr_path=LABEL_DIR/f"{item['code']}.png"
    if not qr_path.exists(): qrcode.make(item['code']).save(qr_path)
    return templates.TemplateResponse('label.html', {'request':request,'item':item,'qr':f"/labels/{item['code']}.png"})


@app.get('/consignantes', response_class=HTMLResponse)
def consignantes(request: Request):
    if (g:=guard(request)): return g
    con=db(); rows=con.execute('''SELECT c.*, (SELECT COUNT(*) FROM items i WHERE i.consignor_id=c.id) pieces,
      COALESCE((SELECT SUM(si.consignor_amount) FROM sale_items si JOIN items i ON i.id=si.item_id WHERE i.consignor_id=c.id),0)-COALESCE((SELECT SUM(p.amount) FROM payouts p WHERE p.consignor_id=c.id),0) balance
      FROM consignors c ORDER BY c.name''').fetchall(); con.close()
    return templates.TemplateResponse('consignors.html', {'request':request,'rows':rows,'user':current_user(request)})

@app.post('/consignantes/novo')
def novo_consignante(request: Request, name:str=Form(...), phone:str=Form(''), email:str=Form(''), commission_percent:float=Form(50)):
    if (g:=guard(request)): return g
    con=db(); con.execute('INSERT INTO consignors(name,phone,email,commission_percent,created_at) VALUES (?,?,?,?,?)',(name,phone,email,commission_percent,datetime.now().isoformat(timespec='seconds'))); con.commit(); con.close(); return RedirectResponse('/consignantes',status_code=303)

@app.post('/consignantes/{cid}/repasse')
def repasse(request: Request, cid:int, amount:float=Form(...), note:str=Form('')):
    if (g:=guard(request)): return g
    con=db(); con.execute('INSERT INTO payouts(consignor_id,amount,note,created_at) VALUES (?,?,?,?)',(cid,amount,note,datetime.now().isoformat(timespec='seconds'))); con.commit(); con.close(); return RedirectResponse('/consignantes',status_code=303)

@app.get('/consignantes/{cid}', response_class=HTMLResponse)
def consignante_detalhe(request: Request, cid:int):
    if (g:=guard(request)): return g
    con=db(); c=con.execute('SELECT * FROM consignors WHERE id=?',(cid,)).fetchone(); items=con.execute('SELECT * FROM items WHERE consignor_id=? ORDER BY id DESC',(cid,)).fetchall(); movements=con.execute('''SELECT s.created_at date,'Venda #'||printf('%06d',s.id) description,si.consignor_amount amount,'credito' kind FROM sale_items si JOIN sales s ON s.id=si.sale_id JOIN items i ON i.id=si.item_id WHERE i.consignor_id=? UNION ALL SELECT created_at,'Repasse '||COALESCE(note,''),amount,'debito' FROM payouts WHERE consignor_id=? ORDER BY date DESC''',(cid,cid)).fetchall(); balance=sum((r['amount'] if r['kind']=='credito' else -r['amount']) for r in movements); con.close()
    return templates.TemplateResponse('consignor_detail.html', {'request':request,'c':c,'items':items,'movements':movements,'balance':balance,'user':current_user(request)})


@app.get('/clientes', response_class=HTMLResponse)
def clientes(request: Request):
    if (g:=guard(request)): return g
    con=db(); rows=con.execute('''SELECT c.*,COUNT(s.id) purchases,COALESCE(SUM(s.total),0) spent FROM customers c LEFT JOIN sales s ON s.customer_id=c.id GROUP BY c.id ORDER BY c.id DESC''').fetchall(); con.close()
    return templates.TemplateResponse('customers.html', {'request':request,'rows':rows,'user':current_user(request)})

@app.post('/clientes/novo')
def novo_cliente(request: Request, name:str=Form(...), phone:str=Form(''), email:str=Form('')):
    if (g:=guard(request)): return g
    con=db(); con.execute('INSERT INTO customers(name,phone,email,created_at) VALUES (?,?,?,?)',(name,phone,email,datetime.now().isoformat(timespec='seconds'))); con.commit(); con.close(); return RedirectResponse('/clientes',status_code=303)


@app.get('/pdv', response_class=HTMLResponse)
def pdv(request: Request):
    if (g:=guard(request)): return g
    con=db(); items=con.execute("SELECT * FROM items WHERE status='em_estoque' ORDER BY id DESC").fetchall(); customers=con.execute('SELECT * FROM customers ORDER BY name').fetchall(); con.close()
    return templates.TemplateResponse('pdv.html', {'request':request,'items':items,'customers':customers,'user':current_user(request)})

@app.post('/pdv/finalizar')
def finalizar_venda(request: Request, item_ids:str=Form(...), customer_id:str=Form(''), discount:float=Form(0), payment_method:str=Form('Pix'), notes:str=Form('')):
    if (g:=guard(request)): return g
    ids=[int(x) for x in item_ids.split(',') if x.strip().isdigit()]
    if not ids: return RedirectResponse('/pdv',status_code=303)
    con=db(); q=','.join('?' for _ in ids); items=con.execute(f"SELECT * FROM items WHERE id IN ({q}) AND status='em_estoque'",ids).fetchall(); subtotal=sum(r['price'] for r in items); discount=max(0,min(discount,subtotal)); total=subtotal-discount; cid=int(customer_id) if customer_id else None; now=datetime.now().isoformat(timespec='seconds')
    cur=con.execute('INSERT INTO sales(customer_id,subtotal,discount,total,payment_method,notes,created_at) VALUES (?,?,?,?,?,?,?)',(cid,subtotal,discount,total,payment_method,notes,now)); sale_id=cur.lastrowid; ratio=(total/subtotal) if subtotal else 1
    for r in items:
        effective=r['price']*ratio; pct=r['commission_percent'] or 0; consignor_amount=effective*(pct/100) if r['consignor_id'] else 0
        con.execute('INSERT INTO sale_items(sale_id,item_id,price,consignor_amount) VALUES (?,?,?,?)',(sale_id,r['id'],effective,consignor_amount)); con.execute("UPDATE items SET status='vendida' WHERE id=?",(r['id'],))
    con.commit(); con.close(); return RedirectResponse(f'/vendas/{sale_id}',status_code=303)

@app.get('/vendas/{sale_id}', response_class=HTMLResponse)
def venda_detalhe(request: Request, sale_id:int):
    if (g:=guard(request)): return g
    con=db(); sale=con.execute('''SELECT s.*,COALESCE(c.name,'Cliente avulso') customer FROM sales s LEFT JOIN customers c ON c.id=s.customer_id WHERE s.id=?''',(sale_id,)).fetchone(); items=con.execute('''SELECT i.code,i.name,si.price FROM sale_items si JOIN items i ON i.id=si.item_id WHERE si.sale_id=?''',(sale_id,)).fetchall(); con.close(); return templates.TemplateResponse('sale_detail.html', {'request':request,'sale':sale,'items':items,'user':current_user(request)})


@app.get('/financeiro', response_class=HTMLResponse)
def financeiro(request: Request):
    if (g:=guard(request)): return g
    con=db(); income=con.execute('SELECT COALESCE(SUM(total),0) s FROM sales').fetchone()['s']; expenses=con.execute('SELECT COALESCE(SUM(amount),0) s FROM expenses').fetchone()['s']; payouts=con.execute('SELECT COALESCE(SUM(amount),0) s FROM payouts').fetchone()['s']; movements=con.execute('SELECT id,total,payment_method,created_at FROM sales ORDER BY id DESC LIMIT 20').fetchall(); exp_rows=con.execute('SELECT * FROM expenses ORDER BY id DESC LIMIT 20').fetchall(); closings=con.execute('SELECT * FROM cash_closings ORDER BY id DESC LIMIT 10').fetchall(); cash_today=con.execute("SELECT COALESCE(SUM(total),0) s FROM sales WHERE payment_method='Dinheiro' AND substr(created_at,1,10)=?",(date.today().isoformat(),)).fetchone()['s']; con.close()
    return templates.TemplateResponse('finance.html', {'request':request,'income':income,'expenses':expenses,'payouts':payouts,'profit':income-expenses-payouts,'movements':movements,'exp_rows':exp_rows,'closings':closings,'cash_today':cash_today,'user':current_user(request)})

@app.post('/financeiro/despesa')
def nova_despesa(request: Request, description:str=Form(...), amount:float=Form(...), category:str=Form('Geral')):
    if (g:=guard(request)): return g
    con=db(); con.execute('INSERT INTO expenses(description,amount,category,created_at) VALUES (?,?,?,?)',(description,amount,category,datetime.now().isoformat(timespec='seconds'))); con.commit(); con.close(); return RedirectResponse('/financeiro',status_code=303)

@app.post('/financeiro/fechamento')
def fechamento_caixa(request: Request, counted_cash:float=Form(...), note:str=Form('')):
    if (g:=guard(request)): return g
    con=db(); d=date.today().isoformat(); expected=con.execute("SELECT COALESCE(SUM(total),0) s FROM sales WHERE payment_method='Dinheiro' AND substr(created_at,1,10)=?",(d,)).fetchone()['s']; diff=counted_cash-expected; con.execute('INSERT INTO cash_closings(closing_date,expected_cash,counted_cash,difference,note,created_at) VALUES (?,?,?,?,?,?)',(d,expected,counted_cash,diff,note,datetime.now().isoformat(timespec='seconds'))); con.commit(); con.close(); return RedirectResponse('/financeiro',status_code=303)


@app.get('/relatorios', response_class=HTMLResponse)
def relatorios(request: Request):
    if (g:=guard(request)): return g
    con=db(); categories=con.execute('''SELECT COALESCE(i.category,'Sem categoria') category,COUNT(*) qty,COALESCE(SUM(si.price),0) total FROM sale_items si JOIN items i ON i.id=si.item_id GROUP BY COALESCE(i.category,'Sem categoria') ORDER BY total DESC''').fetchall(); payments=con.execute('SELECT payment_method,COUNT(*) qty,SUM(total) total FROM sales GROUP BY payment_method ORDER BY total DESC').fetchall(); top_items=con.execute('''SELECT i.code,i.name,si.price,s.created_at FROM sale_items si JOIN items i ON i.id=si.item_id JOIN sales s ON s.id=si.sale_id ORDER BY s.created_at DESC LIMIT 30''').fetchall(); con.close()
    return templates.TemplateResponse('reports.html', {'request':request,'categories':categories,'payments':payments,'top_items':top_items,'user':current_user(request)})


@app.get('/configuracoes', response_class=HTMLResponse)
def settings(request: Request):
    if (g:=guard(request)): return g
    return templates.TemplateResponse('settings.html', {'request':request,'user':current_user(request)})

@app.post('/configuracoes/senha')
def change_password(request: Request, current_password:str=Form(...), new_password:str=Form(...)):
    if (g:=guard(request)): return g
    con=db(); u=con.execute('SELECT * FROM users WHERE id=?',(current_user(request)['id'],)).fetchone()
    if u and password_hash(current_password,u['salt'])==u['password_hash'] and len(new_password)>=6:
        salt=secrets.token_hex(8); con.execute('UPDATE users SET password_hash=?,salt=? WHERE id=?',(password_hash(new_password,salt),salt,u['id'])); con.commit()
    con.close(); return RedirectResponse('/configuracoes',status_code=303)

@app.get('/backup')
def backup(request: Request):
    if (g:=guard(request)): return g
    backup_dir=STORAGE_DIR/'backups'; backup_dir.mkdir(parents=True,exist_ok=True); out=backup_dir/f"brechopro-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.db"; shutil.copy2(DB_PATH,out); return FileResponse(out,filename=out.name,media_type='application/octet-stream')
