"""Ivory Leads: single-owner foundation. No messages are sent by this version."""
import base64, csv, hashlib, hmac, io, json, os, re, secrets, sqlite3, time
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from html import escape
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen
from fastapi import FastAPI, Request as WebRequest
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from starlette.concurrency import run_in_threadpool

PASSWORD = os.environ.get('ADMIN_PASSWORD', '')
SECRET = os.environ.get('APP_SECRET', '')
if len(PASSWORD) < 16 or len(SECRET) < 32:
    raise RuntimeError('Set ADMIN_PASSWORD (16+ characters) and APP_SECRET (32+ characters).')
DB = Path(os.environ.get('DATA_DIR', './data')) / 'ivory.sqlite3'
DB.parent.mkdir(parents=True, exist_ok=True)
CLIENT_FILES = Path(os.environ.get('CLIENT_FILES_DIR', './client-files'))
CLIENT_FILES.mkdir(parents=True, exist_ok=True)
CSRF = hmac.new(SECRET.encode(), b'ivory-forms-v1', hashlib.sha256).hexdigest()
STAGES = ['New', 'Researching', 'Contacted', 'Preview shared', 'Quote sent', 'Won', 'Lost', 'Do not contact']
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

@contextmanager
def db():
    conn = sqlite3.connect(DB, timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

with db() as c:
    c.executescript('''PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS leads(id INTEGER PRIMARY KEY, name TEXT NOT NULL, industry TEXT DEFAULT '', area TEXT DEFAULT '', phone TEXT DEFAULT '', email TEXT DEFAULT '', website TEXT DEFAULT '', source TEXT DEFAULT '', source_key TEXT UNIQUE, checked TEXT NOT NULL, stage TEXT DEFAULT 'New', notes TEXT DEFAULT '', follow_up TEXT DEFAULT '', services TEXT DEFAULT '', headline TEXT DEFAULT '', intro TEXT DEFAULT '', theme TEXT DEFAULT 'stone', slug TEXT UNIQUE, token TEXT, published INTEGER DEFAULT 0, expires TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS searches(id INTEGER PRIMARY KEY, query TEXT, area TEXT, run_id TEXT, status TEXT, created TEXT, imported INTEGER DEFAULT 0);
''')

def e(value):
    return escape(str(value or ''), quote=True)

def field(label, name, value='', kind='text', required=False):
    return f'<label>{e(label)}<input type="{kind}" name="{name}" value="{e(value)}" maxlength="1000" {"required" if required else ""}></label>'

def csrf():
    return f'<input type="hidden" name="csrf" value="{CSRF}">'

def url(value):
    return value if urlsplit(value or '').scheme in ('http', 'https') else ''

CSS = '''*{box-sizing:border-box}body{margin:0;background:#f5f4ef;color:#1d2927;font:16px/1.6 system-ui,sans-serif}a{color:#24574a;text-underline-offset:4px}header{background:#183d34;color:white;padding:20px 4%;display:flex;justify-content:space-between;align-items:center;gap:16px}header a{color:white}header strong{font-size:22px;letter-spacing:-.5px}main{width:94%;max-width:1600px;margin:32px auto 64px}h1{font:42px/1.15 Georgia,serif;letter-spacing:-1px;margin:0 0 14px}h2{font-size:22px;margin:0 0 18px}p{max-width:72ch}.muted{color:#626e68}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));gap:22px}.card{background:white;border:1px solid #dfe3dc;border-radius:14px;padding:26px;margin-bottom:22px}.stat{font-size:32px;font-weight:650}.row{display:flex;flex-wrap:wrap;gap:12px;align-items:center}label{display:block;font-weight:600;font-size:14px;margin-bottom:14px}input,select,textarea{display:block;width:100%;padding:12px;margin-top:6px;font:inherit;border:1px solid #b9c5bb;border-radius:7px;background:white;color:#172e25}textarea{min-height:110px;resize:vertical}button,.button{display:inline-block;border:0;border-radius:7px;background:#235b49;color:white;padding:12px 20px;font:600 15px system-ui;cursor:pointer;text-decoration:none}button:hover,.button:hover{background:#163e32}:focus-visible{outline:3px solid #a47a38;outline-offset:3px}.pill{background:#edf2eb;padding:4px 10px;border-radius:30px;font-size:13px}.table{overflow:auto}table{border-collapse:collapse;width:100%;min-width:720px}th,td{text-align:left;padding:15px 10px;border-bottom:1px solid #e8eae4}th{font-size:13px;color:#526259}.notice{padding:14px 20px;background:#f3ebd9;border-radius:8px;margin-bottom:20px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f5f4ef;padding:18px}small{display:block}.preview-hero{min-height:58vh;padding:9vh 6%;background:var(--hero);color:var(--ink)}.preview-hero h1{font-size:clamp(44px,7vw,88px);max-width:1000px}.preview-hero p{font-size:21px}.eyebrow{font-size:14px;letter-spacing:2px;text-transform:uppercase}.preview main{max-width:1350px}.preview footer{padding:36px 4%;border-top:1px solid #ddd}.preview .card{border-radius:0}.preview header{background:white;color:#1d2927}.preview header a{color:#1d2927}@media(max-width:650px){main{width:94%;margin-top:22px}.card{padding:19px}h1{font-size:34px}header{align-items:flex-start}.preview-hero{padding:60px 5%}}'''

def page(title, content, status=200):
    return HTMLResponse(f'<!doctype html><html lang="en-GB"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>{e(title)} | Ivory Leads</title><style>{CSS}</style></head><body><header><strong>Ivory Digital <span style="font-weight:400">/ Leads</span></strong><a href="/">Your dashboard</a></header><main>{content}</main></body></html>', status_code=status)

@app.middleware('http')
async def protect(request, call_next):
    private = not request.url.path.startswith('/p/')
    if private:
        try:
            scheme, payload = request.headers.get('authorization', '').split(' ', 1)
            user, password = base64.b64decode(payload, validate=True).decode().split(':', 1)
            valid = scheme.lower() == 'basic' and hmac.compare_digest(user, 'mark') and hmac.compare_digest(password, PASSWORD)
        except Exception:
            valid = False
        if not valid:
            return Response('Sign in to Ivory Leads', 401, headers={'WWW-Authenticate':'Basic realm="Ivory Leads", charset="UTF-8"'})
    response = await call_next(request)
    response.headers.update({'X-Robots-Tag':'noindex, nofollow, noarchive', 'Referrer-Policy':'no-referrer', 'X-Content-Type-Options':'nosniff', 'Cache-Control':'no-store', 'Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"})
    return response

async def form(request):
    raw = await request.body()
    if len(raw) > 1_000_000:
        raise ValueError('This form is too large. Import a smaller batch.')
    data = {k:v[0] for k,v in parse_qs(raw.decode(), keep_blank_values=True).items()}
    if not hmac.compare_digest(data.pop('csrf', ''), CSRF):
        raise ValueError('The form could not be verified. Reload the page and try again.')
    return data

@app.exception_handler(ValueError)
async def invalid(request, exc):
    return page('Please check', f'<h1>Please check this</h1><p>{e(str(exc))}</p><a href="/">Back to dashboard</a>', 400)

def add_lead(c, values):
    name = str(values.get('name') or values.get('title') or '').strip()[:200]
    if not name:
        raise ValueError('A business name is required.')
    area = str(values.get('area') or values.get('city') or '')[:200]
    phone = str(values.get('phone') or '')[:80]
    key = str(values.get('placeId') or values.get('source_key') or re.sub(r'\W+', '', (name+area+phone).lower()))
    emails = values.get('emails') or []
    email = str(values.get('email') or (emails[0] if emails else ''))[:200]
    data = (name,str(values.get('industry') or values.get('categoryName') or '')[:200],area,phone,email,url(str(values.get('website') or ''))[:1000],url(str(values.get('source') or values.get('url') or ''))[:1000],key,datetime.now(timezone.utc).isoformat())
    return c.execute('INSERT OR IGNORE INTO leads(name,industry,area,phone,email,website,source,source_key,checked) VALUES(?,?,?,?,?,?,?,?,?)', data).rowcount

def get_lead(lead_id):
    with db() as c:
        row = c.execute('SELECT * FROM leads WHERE id=?',(lead_id,)).fetchone()
    if not row:
        raise ValueError('This lead could not be found.')
    return row

@app.get('/')
def dashboard(q: str='', stage: str='', missing: str=''):
    with db() as c:
        rows = c.execute('SELECT * FROM leads WHERE (name LIKE ? OR area LIKE ?) ORDER BY id DESC',('%'+q+'%','%'+q+'%')).fetchall()
        total = c.execute('SELECT count(*) FROM leads').fetchone()[0]
        won = c.execute("SELECT count(*) FROM leads WHERE stage='Won'").fetchone()[0]
        due = c.execute("SELECT count(*) FROM leads WHERE follow_up!='' AND follow_up<=? AND stage NOT IN ('Won','Lost','Do not contact')",(date.today().isoformat(),)).fetchone()[0]
        searches = c.execute('SELECT * FROM searches ORDER BY id DESC LIMIT 10').fetchall()
    rows = [r for r in rows if (not stage or r['stage']==stage) and (not missing or not r['website'])]
    stats = ''.join(f'<div class="card"><div class="muted">{label}</div><div class="stat">{n}</div></div>' for label,n in [('Businesses',total),('Follow-ups due',due),('Customers won',won)])
    table = ''.join(f'<tr><td><a href="/lead/{r["id"]}"><strong>{e(r["name"])}</strong></a><small>{e(r["industry"])}</small></td><td>{e(r["area"])}</td><td>{e(r["stage"])}</td><td>{"Website listed" if r["website"] else "No website listed · verify"}</td><td>{e(r["follow_up"])}</td></tr>' for r in rows)
    history = ''.join(f'<div class="row"><p>{e(s["query"])} · {e(s["area"])} <span class="pill">{e(s["status"])}</span></p><form method="post" action="/search/{s["id"]}/refresh">{csrf()}<button>Check results</button></form></div>' for s in searches)
    return page('Dashboard',f'''<h1>Turn the next conversation into a customer.</h1><p class="muted">Find a business, prepare their preview and keep the next step in view.</p><div class="grid">{stats}</div>
<div class="grid"><section class="card"><h2>Find businesses</h2><p>Small Google Maps searches through Apify. Each search requests a $0.25 provider charge limit and up to 25 places. Contact enrichment, reviews and images are off.</p><form action="/search" method="post">{csrf()}{field('Business type','query','garages',required=True)}{field('Town or area','area','Manchester, United Kingdom',required=True)}<button>Find up to 25 businesses</button></form><small>{'Apify connected' if os.environ.get('APIFY_TOKEN') else 'Connect APIFY_TOKEN in your server settings to enable searches.'}</small>{history}</section>
<section class="card"><h2>Add a prospect</h2><form method="post" action="/lead">{csrf()}{field('Business name','name',required=True)}{field('Industry','industry')}{field('Town','area')}{field('Business phone','phone')}{field('Business email','email',kind='email')}{field('Website, if known','website',kind='url')}<button>Add business</button></form></section></div>
<section class="card"><h2>Your pipeline</h2><form method="get" class="row">{field('Search businesses','q',q)}<label>Stage<select name="stage"><option value="">All stages</option>{''.join(f'<option {"selected" if stage==s else ""}>{s}</option>' for s in STAGES)}</select></label><label>Website<select name="missing"><option value="">All businesses</option><option value="yes" {'selected' if missing else ''}>No website listed</option></select></label><button>Filter</button><a href="/export">Export CSV</a></form><div class="table"><table><thead><tr><th>Business</th><th>Area</th><th>Stage</th><th>Website</th><th>Follow-up</th></tr></thead><tbody>{table or '<tr><td colspan="5">Start with a small search or add your first prospect.</td></tr>'}</tbody></table></div></section>
<details class="card"><summary>Import a CSV</summary><p>Paste CSV with headers: name,industry,area,phone,email,website,source. Existing source keys are skipped. No contacts are sent messages.</p><form method="post" action="/import">{csrf()}<label>CSV<textarea name="csv" required></textarea></label><button>Import businesses</button></form></details>''')

@app.post('/lead')
async def create(request: WebRequest):
    data = await form(request)
    with db() as c: add_lead(c, data)
    return RedirectResponse('/',303)

@app.get('/lead/{lead_id}')
def detail(lead_id: int):
    r = get_lead(lead_id)
    preview = f'/p/{r["slug"]}?t={r["token"]}' if r['slug'] else ''
    public_base = os.environ.get('PUBLIC_URL','').rstrip('/')
    link = public_base + preview
    draft = f'Hi, it’s Mark from Ivory Digital. I’ve put together a website idea for {r["name"]}. If you’d like a look, here’s the preview: {link or "[create a preview first]"}. Happy to have a chat if it looks useful.'
    source = f'<a href="{e(url(r["source"]))}" target="_blank" rel="noopener noreferrer">Research source</a>' if url(r['source']) else 'Added manually'
    return page(r['name'], f'''<h1>{e(r['name'])}</h1><p class="muted">{e(r['industry'])} · {e(r['area'])}</p><p>{source} · Recorded {e(r['checked'][:10])}</p><div class="grid"><section class="card"><h2>Business & next step</h2><form method="post" action="/lead/{lead_id}">{csrf()}{''.join(field(label,k,r[k],kind) for label,k,kind in [('Business name','name','text'),('Industry','industry','text'),('Area','area','text'),('Business phone','phone','text'),('Business email','email','email'),('Website','website','url')])}<label>Stage<select name="stage">{''.join(f'<option {"selected" if s==r["stage"] else ""}>{s}</option>' for s in STAGES)}</select></label>{field('Next follow-up','follow_up',r['follow_up'],'date')}<label>Notes<textarea name="notes">{e(r['notes'])}</textarea></label><button>Save business</button></form></section>
<section class="card"><h2>Website preview</h2><p>Create an editable one-page concept from the business details. Add confirmed services and wording before sharing.</p><form method="post" action="/lead/{lead_id}/preview">{csrf()}{field('Headline (optional)','headline',r['headline'])}<label>Introduction<textarea name="intro">{e(r['intro'])}</textarea></label><label>Services · one per line<textarea name="services">{e(r['services'])}</textarea></label><label>Design<select name="theme">{''.join(f'<option value="{v}" {"selected" if r["theme"]==v else ""}>{label}</option>' for v,label in [('stone','Stone · warm editorial'),('forest','Forest · classic business'),('midnight','Midnight · modern trade')])}</select></label>{field('Preview expires','expires',r['expires'] or (date.today()+timedelta(days=30)).isoformat(),'date')}<label>Visibility<select name="published"><option value="0">Private draft</option><option value="1" {'selected' if r['published'] else ''}>Enable share link</option></select></label><button>Generate / save preview</button></form>{f'<p><a href="{e(preview)}" target="_blank" rel="noopener noreferrer">Open website preview</a></p><p>Share link: <code>{e(link)}</code></p>' if r['published'] else ''}</section></div>
<section class="card"><h2>Outreach draft</h2><p>Draft only. Check the business type, contact permission and the preview before using it. “Do not contact” records stay in your suppression list.</p><pre>{e(draft) if r['published'] and r['stage']!='Do not contact' else 'Enable a preview before preparing a message. Do not contact records are suppressed.'}</pre></section>''')

@app.post('/lead/{lead_id}')
async def update(lead_id: int, request: WebRequest):
    get_lead(lead_id)
    d = await form(request)
    if d.get('stage') not in STAGES or not d.get('name','').strip(): raise ValueError('Choose a stage and provide a business name.')
    if d.get('follow_up'): date.fromisoformat(d['follow_up'])
    cols=['name','industry','area','phone','email','website','stage','follow_up','notes']
    d['website']=url(d.get('website',''))
    with db() as c: c.execute('UPDATE leads SET '+','.join(k+'=?' for k in cols)+' WHERE id=?',[d.get(k,'')[:10000] for k in cols]+[lead_id])
    return RedirectResponse(f'/lead/{lead_id}',303)

@app.post('/lead/{lead_id}/preview')
async def generate(lead_id: int, request: WebRequest):
    r=get_lead(lead_id); d=await form(request)
    if d.get('theme') not in ('stone','forest','midnight'): raise ValueError('Choose a design.')
    date.fromisoformat(d.get('expires',''))
    slug=r['slug'] or (re.sub('[^a-z0-9]+','-',r['name'].lower()).strip('-')[:60] or 'business')+'-'+str(lead_id)
    with db() as c:
        c.execute('UPDATE leads SET headline=?,intro=?,services=?,theme=?,slug=?,token=?,published=?,expires=? WHERE id=?',(d.get('headline','')[:300],d.get('intro','')[:4000],d.get('services','')[:4000],d['theme'],slug,r['token'] or secrets.token_urlsafe(24),int(d.get('published')=='1'),d['expires'],lead_id))
    saved = get_lead(lead_id)
    folder = CLIENT_FILES / saved['slug']
    folder.mkdir(parents=True, exist_ok=True)
    temporary = folder / 'index.html.tmp'
    temporary.write_text(render_preview(saved), encoding='utf-8')
    temporary.replace(folder / 'index.html')
    return RedirectResponse(f'/lead/{lead_id}',303)

@app.get('/p/{slug}')
def public(slug: str,t: str=''):
    with db() as c: r=c.execute('SELECT * FROM leads WHERE slug=?',(slug,)).fetchone()
    if not r or not r['published'] or not hmac.compare_digest(r['token'] or '',t) or r['expires']<date.today().isoformat():
        return HTMLResponse('This preview is not available.',404)
    return HTMLResponse(render_preview(r))

def render_preview(r):
    hero,ink={'stone':('#e9e2d3','#25352c'),'forest':('#1c483b','#ffffff'),'midnight':('#192939','#ffffff')}[r['theme']]
    services=''.join(f'<article class="card"><h2>{e(s)}</h2><p>Speak to {e(r["name"])} to discuss your requirements.</p></article>' for s in r['services'].splitlines() if s.strip())
    phone=re.sub(r'[^+0-9]','',r['phone'])
    contact=f'<a class="button" href="tel:{e(phone)}">Call {e(r["phone"])}</a>' if phone else ''
    content=f'''<!doctype html><html lang="en-GB"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>{e(r['name'])} · Website concept</title><style>{CSS}</style></head><body class="preview" style="--hero:{hero};--ink:{ink}"><div class="notice" style="margin:0;border-radius:0;text-align:center">Website concept by Ivory Digital · Prepared for discussion</div><header><strong>{e(r['name'])}</strong><a href="#contact">Get in touch</a></header><section class="preview-hero"><div class="eyebrow">{e(r['industry'])} · {e(r['area'])}</div><h1>{e(r['headline'] or r['name'])}</h1><p>{e(r['intro'] or 'A new website concept for '+r['name']+'.')}</p><a class="button" href="#contact">Discuss your requirements</a></section><main>{f'<h2>Services</h2><div class="grid">{services}</div>' if services else ''}<section class="card" id="contact"><h2>Let’s talk about your project.</h2><p>{e(r['name'])} · {e(r['area'])}</p>{contact}</section><section class="card"><h2>Like this direction for your website?</h2><p>Mark at Ivory Digital can tailor the pages, photography and wording to your business.</p><a class="button" href="https://ivorydigital.uk/web-design-seo/">Discuss your website with Ivory Digital</a></section></main><footer>Website concept by <a href="https://ivorydigital.uk/web-design-seo/">Ivory Digital</a></footer></body></html>'''
    return content

@app.post('/import')
async def import_csv(request: WebRequest):
    d=await form(request); rows=list(csv.DictReader(io.StringIO(d.get('csv',''))))
    if len(rows)>500: raise ValueError('Import up to 500 businesses per batch.')
    with db() as c:
        for row in rows: add_lead(c,row)
    return RedirectResponse('/',303)

@app.get('/export')
def export():
    with db() as c: rows=c.execute('SELECT name,industry,area,phone,email,website,source,stage,follow_up,notes FROM leads').fetchall()
    out=io.StringIO(); writer=csv.writer(out); writer.writerow(['name','industry','area','phone','email','website','source','stage','follow_up','notes'])
    for r in rows: writer.writerow(["'"+str(v) if str(v).lstrip().startswith(('=','+','-','@')) else v for v in r])
    return Response(out.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="ivory-leads.csv"'})

def apify(path, payload=None):
    token=os.environ.get('APIFY_TOKEN')
    if not token: raise ValueError('Add APIFY_TOKEN in your server settings to connect lead search.')
    req=Request('https://api.apify.com/v2/'+path,data=json.dumps(payload).encode() if payload is not None else None,headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
    try:
        with urlopen(req,timeout=30) as response: return json.load(response)
    except Exception:
        raise ValueError('Apify did not confirm the request. Check the Apify console before retrying; a search may already have started.')

@app.post('/search')
async def search(request: WebRequest):
    d=await form(request)
    if not os.environ.get('APIFY_TOKEN'): raise ValueError('Add APIFY_TOKEN in server settings before searching.')
    query=d.get('query','').strip()[:120]; area=d.get('area','').strip()[:200]
    if not query or not area: raise ValueError('Enter a business type and location.')
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        if c.execute("SELECT count(*) FROM searches WHERE status IN ('STARTING','RUNNING','READY','UNCERTAIN')").fetchone()[0]: raise ValueError('Resolve your existing search before starting another one. Check the Apify console if its status is uncertain.')
        sid=c.execute('INSERT INTO searches(query,area,status,created) VALUES(?,?,?,?)',(query,area,'STARTING',datetime.now(timezone.utc).isoformat())).lastrowid
    try:
        result=await run_in_threadpool(apify,'acts/compass~crawler-google-places/runs?'+urlencode({'maxTotalChargeUsd':0.25,'timeout':300}),{'searchStringsArray':[query],'locationQuery':area,'maxCrawledPlacesPerSearch':25,'language':'en','scrapeContacts':False,'maximumLeadsEnrichmentRecords':0,'maxReviews':0,'maxImages':0})
        run=result['data']
    except ValueError:
        with db() as c: c.execute("UPDATE searches SET status='UNCERTAIN' WHERE id=?",(sid,))
        raise
    with db() as c: c.execute('UPDATE searches SET run_id=?,status=? WHERE id=?',(run['id'],run['status'],sid))
    return RedirectResponse('/',303)

@app.post('/search/{sid}/refresh')
async def refresh(sid: int, request: WebRequest):
    await form(request)
    with db() as c: s=c.execute('SELECT * FROM searches WHERE id=?',(sid,)).fetchone()
    if not s or not s['run_id']: raise ValueError('No confirmed run ID. Check the Apify console; do not retry the search until its outcome is known.')
    result=await run_in_threadpool(apify,'actor-runs/'+s['run_id'])
    run=result['data']; imported=s['imported']
    if run['status']=='SUCCEEDED' and not imported:
        items=await run_in_threadpool(apify,'datasets/'+run['defaultDatasetId']+'/items?clean=true&limit=25')
        with db() as c:
            for item in items:
                if not item.get('permanentlyClosed') and not item.get('temporarilyClosed'): add_lead(c,item)
            c.execute('UPDATE searches SET imported=1 WHERE id=?',(sid,))
    with db() as c: c.execute('UPDATE searches SET status=? WHERE id=?',(run['status'],sid))
    return RedirectResponse('/',303)
