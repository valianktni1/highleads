"""Authenticated editorial workspace, installed alongside the prospect dashboard."""
from datetime import date
import json

from urllib.parse import urlencode
from fastapi import Request
from fastapi.responses import RedirectResponse

DOMAINS = ('perfectweddingsbymark.uk','ivorydigital.uk','thekitchenfactoryliverpool.uk','wifetobe.co.uk','wifetobe.org')
STAGES = ('Draft','Approved','Submitted','Accepted','Published','Rejected')
FIELDS = ('title','body','target','photos','notes','live','backlink','indexing')
SCHEMA = """
CREATE TABLE IF NOT EXISTS seo_projects(domain TEXT PRIMARY KEY, strategy TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS seo_publications(name TEXT PRIMARY KEY COLLATE NOCASE, contact TEXT, guidelines TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS seo_articles(id INTEGER PRIMARY KEY, source TEXT UNIQUE, domain TEXT NOT NULL, publication TEXT NOT NULL,
title TEXT NOT NULL, body TEXT DEFAULT '', target TEXT DEFAULT '', photos TEXT DEFAULT '', notes TEXT DEFAULT '', live TEXT DEFAULT '',
backlink TEXT DEFAULT '', indexing TEXT DEFAULT '', stage TEXT NOT NULL, submitted TEXT DEFAULT '', published TEXT DEFAULT '', cost REAL DEFAULT 0, revision INTEGER DEFAULT 0);
"""

def import_records(c, records):
    for row in records:
        if row['domain'] not in DOMAINS:
            raise ValueError('Unknown project in submission import.')
        c.execute('INSERT OR IGNORE INTO seo_publications(name,contact) VALUES (?,?)',(row['publication'],row['contact']))
        notes = row['notes'] + '\nSent correspondence: https://mail.google.com/mail/u/0/#sent/' + row['thread']
        c.execute("""INSERT INTO seo_articles(source,domain,publication,title,body,target,notes,stage,submitted)
            VALUES (?,?,?,?,?,?,?,'Submitted',?) ON CONFLICT(source) DO NOTHING""",
            (row['source'],row['domain'],row['publication'],row['title'],row['body'],row['target'],notes,row['submitted']))

def install(app, db, page, form, csrf, field, e, url, data_dir):
    with db() as c:
        c.executescript(SCHEMA)
        c.executemany('INSERT OR IGNORE INTO seo_projects(domain) VALUES (?)',[(x,) for x in DOMAINS])

        archive = data_dir / "november-submissions.json"
        if archive.is_file():
            import_records(c, json.loads(archive.read_text(encoding="utf-8-sig")))

    nav = '<nav class="row"><a href="/seo">Projects</a><a href="/seo/publications">Publication directory</a></nav>'
    def view(title, content):
        return page(title, nav+'<h1>'+e(title)+'</h1>'+content)
    def post(action, content, label):
        return f'<form method="post" action="{action}">{csrf()}{content}<button>{e(label)}</button></form>'
    def area(label,name,value=''):
        return f'<label>{e(label)}<textarea name="{e(name)}">{e(value)}</textarea></label>'
    def select(label,name,values,current=''):
        opts=''.join(f'<option {"selected" if v==current else ""}>{e(v)}</option>' for v in values)
        return f'<label>{label}<select name="{name}">{opts}</select></label>'
    def redirect(path):
        return RedirectResponse(path,status_code=303)
    def project(domain):
        if domain not in DOMAINS:
            raise ValueError('Select a listed SEO project.')
    def article_list(rows):
        return ''.join(f'<div class="card"><small>{e(r["publication"])} · {e(r["stage"])}</small><a href="/seo/article/{r["id"]}">{e(r["title"])}</a></div>' for r in rows) or '<p>No articles recorded.</p>'

    @app.get('/seo')
    def home():
        with db() as c:
            rows=c.execute("""SELECT p.domain,count(a.id) AS total,count(CASE WHEN stage='Published' THEN 1 END) AS live
                FROM seo_projects p LEFT JOIN seo_articles a ON a.domain=p.domain GROUP BY p.domain""").fetchall()
        cards=''.join(f'<section class="card"><h2><a href="/seo/project/{r["domain"]}">{r["domain"]}</a></h2><p>{r["total"]} articles · {r["live"]} published</p></section>' for r in rows)
        return view('SEO & Digital PR','<div class="grid">'+cards+'</div>')

    @app.get('/seo/publications')
    def publications(q:str=''):
        with db() as c:
            rows=c.execute("SELECT * FROM seo_publications WHERE instr(lower(name || ' ' || contact || ' ' || guidelines),lower(?)) ORDER BY name",(q,)).fetchall()
        directory=''.join('<section class="card"><h2>'+e(r['name'])+'</h2><p>'+e(r['contact'])+'</p><p>'+e(r['guidelines'])+'</p></section>' for r in rows)
        editor=field('Publication','name',required=True)+field('Editorial contact or submission route','contact',required=True)+area('Guidelines, regions and sectors','guidelines')
        return view('UK publication directory','<form>'+field('Search publications','q',q)+'<button>Search</button></form><div class="grid">'+directory+'</div><details class="card"><summary>Add or update a publication</summary>'+post('/seo/publications',editor,'Save publication')+'</details>')

    @app.post('/seo/publications')
    async def save_publication(request:Request):
        d=await form(request)
        if not d.get('name','').strip() or not d.get('contact','').strip(): raise ValueError('Enter a publication and contact route.')
        with db() as c:
            c.execute('INSERT INTO seo_publications VALUES(?,?,?) ON CONFLICT(name) DO UPDATE SET contact=excluded.contact,guidelines=excluded.guidelines',(d['name'].strip(),d['contact'],d.get('guidelines','')))
        return redirect('/seo/publications')

    @app.get('/seo/project/{domain}')
    def details(domain:str):
        project(domain)
        with db() as c:
            rows=c.execute('SELECT * FROM seo_articles WHERE domain=? ORDER BY id DESC',(domain,)).fetchall()
            strategy=c.execute('SELECT strategy FROM seo_projects WHERE domain=?',(domain,)).fetchone()[0]
            names=[r[0] for r in c.execute('SELECT name FROM seo_publications ORDER BY name')]
        path='/seo/project/'+domain
        report='<form action="'+path+'/report">'+field('Reporting month','month',date.today().isoformat()[:7],'month',True)+'<button>View client report</button></form>'
        draft=post(path+'/draft',field('Article headline','title',required=True)+select('Publication','publication',names),'Create draft') if names else '<a href="/seo/publications">Add a publication</a>'
        return view(domain,'<div class="grid"><section class="card"><h2>New article</h2>'+draft+'</section><section class="card"><h2>Monthly reporting</h2>'+report+'</section></div><details class="card"><summary>Campaign targeting</summary>'+post(path,area('Locations, keywords and landing pages','strategy',strategy),'Save targeting')+'</details><h2>Editorial tracker</h2>'+article_list(rows))

    @app.post('/seo/project/{domain}')
    async def strategy(domain:str, request:Request):
        project(domain)
        d=await form(request)
        with db() as c: c.execute('UPDATE seo_projects SET strategy=? WHERE domain=?',(d.get('strategy',''),domain))
        return redirect('/seo/project/'+domain)

    @app.post('/seo/project/{domain}/draft')
    async def draft(domain:str,request:Request):
        project(domain)
        d=await form(request)
        with db() as c:
            if not d.get('title','').strip() or not c.execute('SELECT 1 FROM seo_publications WHERE name=?',(d.get('publication'),)).fetchone(): raise ValueError('Choose a publication and enter a title.')
            ident=c.execute("INSERT INTO seo_articles(domain,publication,title,stage) VALUES(?,?,?,'Draft')",(domain,d['publication'],d['title'])).lastrowid
        return redirect('/seo/article/'+str(ident))

    @app.get('/seo/article/{ident}')
    def article(ident:int):
        with db() as c:
            r=c.execute('SELECT a.*,p.contact FROM seo_articles a JOIN seo_publications p ON a.publication=p.name WHERE id=?',(ident,)).fetchone()
        if not r: return page('Article missing','Article not found.',404)
        editor=field('Headline','title',r['title'],required=True)+area('Article text','body',r['body'])
        for name,label in [('target','Target landing page'),('photos','Photo links'),('live','Published article URL'),('backlink','Backlink type and destination'),('indexing','Indexing evidence')]:
            editor+=field(label,name,r[name])
        editor+=area('Correspondence and notes','notes',r['notes'])+select('Editorial status','stage',STAGES,r['stage'])+field('Placement cost (£)','cost',str(r['cost']))+f'<input type="hidden" name="revision" value="{r["revision"]}">'
        route=''
        if r['stage']=='Approved' and '@' in r['contact']:
            from urllib.parse import quote
            route='<p><a class="button" href="mailto:'+e(quote(r['contact'],safe='@.'))+'?'+e(urlencode({'subject':r['title'],'body':r['body']},quote_via=quote))+'">Open submission in email</a></p>'
        return view(r['title'],f'<p><a href="/seo/project/{r["domain"]}">{r["domain"]}</a> · {e(r["publication"])} · {e(r["contact"])}</p>'+route+'<section class="card">'+post('/seo/article/'+str(ident),editor,'Save article')+'</section>')

    @app.post('/seo/article/{ident}')
    async def save_article(ident:int,request:Request):
        d=await form(request)
        stage=d.get('stage')
        import math
        cost=float(d.get('cost') or 0)
        if stage not in STAGES or not d.get('title','').strip() or not math.isfinite(cost) or cost<0: raise ValueError('Check the headline, status and cost.')
        if stage=='Published' and not url(d.get('live')): raise ValueError('Enter the published article URL.')
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            r=c.execute('SELECT * FROM seo_articles WHERE id=?',(ident,)).fetchone()
            if not r or str(r['revision'])!=d.get('revision'): raise ValueError('This article has changed. Reopen it before saving.')
            if r['stage']=='Draft' and stage not in ('Draft','Approved','Rejected'): raise ValueError('Approve the article before submitting it.')
            if stage=='Approved' and not d.get('body','').strip(): raise ValueError('Add the article before approving it.')
            if r['stage']=='Approved' and any(r[k]!=d.get(k,'') for k in ('body','title')) and stage not in ('Approved','Draft'): raise ValueError('Approve the revised text before recording submission.')
            submitted=r['submitted'] or (date.today().isoformat() if stage in ('Submitted','Accepted','Published') else '')
            published=r['published'] or (date.today().isoformat() if stage=='Published' else '')
            c.execute('UPDATE seo_articles SET '+','.join(k+'=?' for k in FIELDS)+', stage=?,cost=?,submitted=?,published=?,revision=revision+1 WHERE id=?',[*(d.get(k,'') for k in FIELDS),stage,cost,submitted,published,ident])
        return redirect('/seo/article/'+str(ident))

    @app.get('/seo/project/{domain}/report')
    def report(domain:str,month:str):
        project(domain)
        date.fromisoformat(month+'-01')
        with db() as c:
            rows=c.execute('SELECT * FROM seo_articles WHERE domain=? AND (substr(submitted,1,7)=? OR substr(published,1,7)=?) ORDER BY submitted',(domain,month,month)).fetchall()
        items=''.join(f'<section class="card"><h2>{e(r["title"])}</h2><p>{e(r["publication"])} · Submitted {e(r["submitted"])}</p><p>{e(r["live"])} {e(r["backlink"])} {e(r["indexing"])}</p></section>' for r in rows)
        sent=sum(r['submitted'].startswith(month) for r in rows)
        live=sum(r['published'].startswith(month) for r in rows)
        return view(domain+' · '+month,f'<p>Ivory Digital monthly SEO report</p><p>{sent} submissions · {live} publications</p>'+items)
