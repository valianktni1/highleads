import base64, csv, io, os, tempfile, unittest
from unittest.mock import patch
os.environ['ADMIN_PASSWORD']='example-password-for-testing-only'
os.environ['APP_SECRET']='example-test-secret-with-at-least-32-characters'
os.environ['DATA_DIR']=tempfile.mkdtemp()
os.environ['CLIENT_FILES_DIR']=tempfile.mkdtemp()
from fastapi.testclient import TestClient
import app

class AppTests(unittest.TestCase):
    def setUp(self):
        with app.db() as c:
            c.execute('DELETE FROM leads'); c.execute('DELETE FROM searches')
        self.client=TestClient(app.app)
        self.client.auth=('mark',os.environ['ADMIN_PASSWORD'])

    def post(self,path,data):
        return self.client.post(path,data={'csrf':app.CSRF,**data},follow_redirects=False)

    def lead(self,name='Example Garage'):
        self.post('/lead',{'name':name,'area':'Manchester','industry':'Garage','phone':'0161 123 4567'})
        with app.db() as c: return c.execute('SELECT id FROM leads').fetchone()[0]

    def publish(self,lid,**changes):
        self.post(f'/lead/{lid}/preview',{'theme':'stone','published':'1','expires':'2099-01-01','services':'Repairs\nServicing',**changes})
        return app.get_lead(lid)

    def test_auth_and_csrf(self):
        self.assertEqual(TestClient(app.app).get('/').status_code,401)
        self.assertEqual(self.client.post('/lead',data={'name':'Bad'}).status_code,400)
        self.assertEqual(self.client.get('/').status_code,200)

    def test_unicode_password_authentication(self):
        password = 'Long-password-with-£-é-🔒'
        def header(user, candidate):
            token = base64.b64encode((user+':'+candidate).encode('utf-8')).decode('ascii')
            return {'Authorization': 'Basic '+token}
        client = TestClient(app.app)
        with patch.object(app, 'PASSWORD', password):
            self.assertEqual(client.get('/', headers=header('mark', password)).status_code, 200)
            self.assertEqual(client.get('/', headers=header('mark', password+'wrong')).status_code, 401)
            self.assertEqual(client.get('/', headers=header('wrong-user', password)).status_code, 401)
            self.assertEqual(client.get('/', headers={'Authorization':'Basic invalid!'}).status_code, 401)

    def test_preview_draft_token_expiry_and_escaping(self):
        lid=self.lead('<script>alert(1)</script>')
        self.assertEqual(self.client.get('/p/unknown?t=wrong').status_code,404)
        r=self.publish(lid)
        self.assertTrue((app.CLIENT_FILES / r['slug'] / 'index.html').is_file())
        self.assertNotIn(r['token'], (app.CLIENT_FILES / r['slug'] / 'index.html').read_text())
        public=TestClient(app.app)
        link=f'/p/{r["slug"]}?t={r["token"]}'
        response=public.get(link)
        self.assertEqual(response.status_code,200)
        self.assertNotIn('<script>',response.text)
        self.assertIn('&lt;script&gt;',response.text)
        self.assertEqual(public.get('/p/'+r['slug']+'?t=wrong').status_code,404)
        self.assertNotIn('source_key',response.text)
        self.assertIn('noindex',response.headers['x-robots-tag'])
        self.publish(lid,published='0')
        self.assertEqual(public.get(link).status_code,404)
        self.publish(lid,expires='2020-01-01')
        self.assertEqual(public.get(link).status_code,404)

    def test_import_duplicate_and_csv_formula(self):
        data='name,area,phone\nExample Garage,Manchester,0161\nExample Garage,Manchester,0161\n=SUM(A1),Test,0123\n'
        self.assertEqual(self.post('/import',{'csv':data}).status_code,303)
        with app.db() as c: self.assertEqual(c.execute('SELECT count(*) FROM leads').fetchone()[0],2)
        rows=list(csv.reader(io.StringIO(self.client.get('/export').text)))
        self.assertTrue(rows[2][0].startswith("'="))

    def test_no_contact_suppression(self):
        lid=self.lead(); self.publish(lid)
        self.post(f'/lead/{lid}',{'name':'Example Garage','stage':'Do not contact','notes':'PRIVATE NOTE'})
        self.assertIn('records are suppressed',self.client.get(f'/lead/{lid}').text)
        r=app.get_lead(lid)
        response=TestClient(app.app).get(f'/p/{r["slug"]}?t={r["token"]}')
        self.assertNotIn('PRIVATE NOTE',response.text)

    def test_search_connector_and_repeated_import(self):
        def provider(path,payload=None):
            if path.startswith('acts/'):
                self.assertIn('maxTotalChargeUsd=0.25',path)
                self.assertFalse(payload['scrapeContacts'])
                self.assertEqual(payload['maxCrawledPlacesPerSearch'],25)
                return {'data':{'id':'run123','status':'RUNNING'}}
            if path.startswith('actor-runs/'):
                return {'data':{'status':'SUCCEEDED','defaultDatasetId':'dataset123'}}
            return [{'title':'Example Motors','city':'Bury','placeId':'place123','url':'https://maps.google.com/?cid=123'}]
        with patch.dict(os.environ,{'APIFY_TOKEN':'test-token'}), patch.object(app,'apify',side_effect=provider):
            self.assertEqual(self.post('/search',{'query':'garage','area':'Bury'}).status_code,303)
            self.assertEqual(self.post('/search',{'query':'garage','area':'Bury'}).status_code,400)
            with app.db() as c: sid=c.execute('SELECT id FROM searches').fetchone()[0]
            self.assertEqual(self.post(f'/search/{sid}/refresh',{}).status_code,303)
            self.assertEqual(self.post(f'/search/{sid}/refresh',{}).status_code,303)
        with app.db() as c: self.assertEqual(c.execute('SELECT count(*) FROM leads').fetchone()[0],1)

    def test_missing_token_creates_no_search(self):
        with patch.dict(os.environ,{'APIFY_TOKEN':''}):
            self.assertEqual(self.post('/search',{'query':'garage','area':'Bury'}).status_code,400)
        with app.db() as c: self.assertEqual(c.execute('SELECT count(*) FROM searches').fetchone()[0],0)

    def test_uncertain_search_blocks_retry(self):
        with patch.dict(os.environ,{'APIFY_TOKEN':'test'}), patch.object(app,'apify',side_effect=ValueError('Uncertain outcome')) as provider:
            self.assertEqual(self.post('/search',{'query':'garage','area':'Bury'}).status_code,400)
            self.assertEqual(self.post('/search',{'query':'garage','area':'Bury'}).status_code,400)
            self.assertEqual(provider.call_count,1)

if __name__=='__main__': unittest.main()
