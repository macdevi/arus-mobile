import sys, tempfile, unittest, io, threading
from pathlib import Path
from datetime import date
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import domain as D
from server import create_app
from werkzeug.security import generate_password_hash

class DomainTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.path=str(Path(self.tmp.name)/'test.sqlite3'); D.initialize(self.path)
        self.clock=patch.object(D,'today',return_value=date(2026,11,30)); self.clock.start()
        with D.db(self.path,True) as c:
            c.execute("INSERT INTO rates VALUES('2026-11-01','11.5','test','test')")
            D.action(c,dict(op='opening',KRW=10000,IDR=1000000,day='2026-11-01'))
    def tearDown(self): self.clock.stop(); self.tmp.cleanup()
    def act(self,**d):
        with D.db(self.path,True) as c: return D.action(c,d)
    def snap(self,month='2026-11'):
        with D.db(self.path) as c: return D.snapshot(c,month)
    def goal(self): return self.act(op='goal',name='Target',currency='IDR',target=1000000)['id']
    def loan(self,cur='IDR'): return self.act(op='loan',name='Pinjaman',currency=cur,installment=100,count=2,first_due='2026-11-30',due_day=31,principal=None)['id']
    def pay(self,lid): return self.act(op='pay',loan_id=lid,day='2026-11-30',period='2026-11-30')
    def transaction(self,**kw):
        d=dict(op='transaction',kind='income',amount=100,currency='IDR',day='2026-11-20',description='Test'); d.update(kw); return self.act(**d)
    def test_opening_not_income(self): self.assertEqual(self.snap()['monthly']['income'],0)
    def test_invalid_money(self):
        for n in (True,-1,0,1.2,'100'):
            with self.subTest(n=n),self.assertRaises(ValueError): self.transaction(amount=n)
    def test_invalid_rates(self):
        for n in ('NaN','Infinity','0','-1',None,True,11.5):
            with self.subTest(n=n),self.assertRaises(ValueError): D.rate_value(n)
    def test_conversion(self):
        self.assertEqual(D.cv(1,'KRW','IDR','11.5'),12); self.assertEqual(D.cv(0,'KRW','IDR',None),0); self.assertIsNone(D.cv(1,'KRW','IDR',None))
    def test_future_date(self):
        with self.assertRaises(ValueError): self.transaction(day='2026-12-01')
    def test_exchange_not_income(self):
        self.transaction(kind='exchange',currency='KRW',other_amount=1100); self.assertEqual(self.snap()['balances'],{'KRW':9900,'IDR':1001100}); self.assertEqual(self.snap()['monthly']['income'],0)
    def test_historical_snapshot(self):
        self.transaction(currency='KRW'); self.act(op='manual_rate',day='2026-11-25',rate='12'); self.assertEqual(self.snap()['monthly']['income'],1150)
    def test_month_filter(self): self.transaction(); self.assertEqual(self.snap('2026-12')['monthly']['income'],0)
    def test_allocation_not_expense(self):
        self.act(op='allocate',goal_id=self.goal(),currency='IDR',delta=400,day='2026-11-20'); self.assertEqual(self.snap()['balances']['IDR'],1000000); self.assertEqual(self.snap()['free']['IDR'],999600)
    def test_savings_protected(self):
        self.act(op='allocate',goal_id=self.goal(),currency='IDR',delta=1000000,day='2026-11-20')
        with self.assertRaises(ValueError): self.pay(self.loan())
        with self.assertRaises(ValueError): self.transaction(kind='expense')
    def test_release_allocation(self):
        gid=self.goal(); self.act(op='allocate',goal_id=gid,currency='IDR',delta=400,day='2026-11-20'); self.act(op='allocate',goal_id=gid,currency='IDR',delta=-100,day='2026-11-20'); self.assertEqual(self.snap()['goals'][0]['saved'],300)
    def test_payment_retry(self):
        lid=self.loan(); self.assertEqual(self.pay(lid),self.pay(lid)); self.assertEqual(self.snap()['balances']['IDR'],999900)
    def test_krw_payment(self): self.pay(self.loan('KRW')); self.assertEqual(self.snap()['balances']['KRW'],9900)
    def test_next_due(self): self.pay(self.loan()); self.assertEqual(self.snap()['loans'][0]['next_due'],'2026-12-31')
    def test_wrong_period(self):
        with self.assertRaises(ValueError): self.act(op='pay',loan_id=self.loan(),day='2026-11-30',period='2026-12-31')
    def test_void_payment(self):
        lid=self.loan(); self.act(op='void',id=self.pay(lid)['id']); self.assertEqual(self.snap()['balances']['IDR'],1000000); self.assertEqual(self.snap()['loans'][0]['next_due'],'2026-11-30')
    def test_short_month(self): self.assertEqual(D.due_date('2028-01-31',31,1),'2028-02-29')
    def salary(self): self.act(op='salary',amount=2500000,payday=25,effective_from='2026-11-01')
    def tick(self): return D.tick(self.path,fetcher=lambda on:(on or '2026-11-30','11.5','test'))
    def test_salary_retry(self): self.salary(); self.assertEqual(len(self.tick()['created']),1); self.assertEqual(self.tick()['created'],[])
    def test_salary_pause_resume(self):
        self.salary(); self.act(op='pause',start='2026-11-01',end=None); self.assertEqual(self.tick()['created'],[]); self.act(op='resume',day='2026-11-20'); self.assertEqual(len(self.tick()['created']),1)
    def test_salary_missing_rate(self):
        self.salary()
        with D.db(self.path,True) as c: c.execute('DELETE FROM rates')
        def fail(on): raise OSError('offline')
        self.assertEqual(D.tick(self.path,fetcher=fail)['waiting_for_rate'],['2026-11-25'])
    def test_salary_concurrent(self):
        self.salary(); errors=[]
        def run():
            try: self.tick()
            except Exception as e: errors.append(e)
        threads=[threading.Thread(target=run) for _ in range(2)]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertEqual(errors,[])
        with D.db(self.path) as c: self.assertEqual(c.execute('SELECT COUNT(*) FROM tx WHERE salary_period IS NOT NULL').fetchone()[0],1)
    def test_provider_payload(self):
        with patch.object(D,'urlopen',return_value=io.BytesIO(b'{"date":"2026-11-27","base":"KRW","quote":"IDR","rate":11.5}')): self.assertEqual(D.fetch_rate('2026-11-30')[1],'11.5')

class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.path=str(Path(self.tmp.name)/'web.sqlite3'); self.app=create_app(dict(TESTING=True,SECRET_KEY='x'*64,DATABASE=self.path,SESSION_COOKIE_SECURE=False)); self.client=self.app.test_client()
        with D.db(self.path,True) as c: D.put(c,'password_hash',generate_password_hash('secure-password-123')); D.put(c,'auth_version','v1')
        self.csrf=self.client.get('/api/session').json['csrf']
    def tearDown(self): self.tmp.cleanup()
    def post(self,path,d): return self.client.post(path,json=d,headers={'X-CSRF-Token':self.csrf})
    def login(self):
        result=self.post('/api/login',{'password':'secure-password-123'}); self.assertEqual(result.status_code,200); self.csrf=result.json['csrf']
    def test_auth(self): self.assertEqual(self.client.get('/api/data').status_code,401)
    def test_csrf(self): self.assertEqual(self.client.post('/api/login',json={}).status_code,403)
    def test_login(self): self.login(); self.assertEqual(self.client.get('/api/data').status_code,200)
    def test_template_nonce(self):
        r=self.client.get('/'); self.assertEqual(r.status_code,200); self.assertIn('nonce-',r.headers['Content-Security-Policy']); self.assertNotIn(b'{{ nonce }}',r.data)
    def test_throttle(self):
        for _ in range(5): self.assertEqual(self.post('/api/login',{'password':'bad'}).status_code,401)
        self.assertEqual(self.post('/api/login',{'password':'bad'}).status_code,429)
    def test_request_dedup(self):
        self.login(); d=dict(op='transaction',kind='income',currency='IDR',amount=100,description='Income',day=D.today().isoformat(),request_id='same')
        one=self.post('/api/action',d); two=self.post('/api/action',d); self.assertEqual(one.status_code,200); self.assertEqual(one.json,two.json); self.assertEqual(self.client.get('/api/data').json['balances']['IDR'],100)
    def test_request_conflict(self):
        self.login(); d=dict(op='manual_rate',day=D.today().isoformat(),rate='11.5',request_id='same'); self.assertEqual(self.post('/api/action',d).status_code,200); d['rate']='12'; self.assertEqual(self.post('/api/action',d).status_code,400)
    def test_export(self): self.login(); self.assertNotIn('password_hash',str(self.client.get('/api/export').json))
    def test_password_revokes(self):
        self.login(); self.assertEqual(self.post('/api/action',dict(op='password',current_password='secure-password-123',new_password='new-secure-password',request_id='pw')).status_code,200); self.assertEqual(self.client.get('/api/data').status_code,401)
    def test_network_failure(self):
        self.login()
        with patch.object(D,'fetch_rate',side_effect=OSError('offline')): self.assertEqual(self.post('/api/rate/refresh',{}).status_code,502)
if __name__=='__main__': unittest.main(verbosity=2)
