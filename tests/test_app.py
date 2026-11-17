import os, tempfile, unittest, json
os.environ['SECRET_KEY']='test-only-secret-'*5
os.environ['COOKIE_SECURE']='false'
_tmp=tempfile.TemporaryDirectory()
os.environ['DB_PATH']=os.path.join(_tmp.name,'test.sqlite3')
from app import app, db, initial
from werkzeug.security import generate_password_hash

class Tests(unittest.TestCase):
    def setUp(self):
        self.c=app.test_client()
        with db(True) as c:
            c.execute('UPDATE state SET body=? WHERE id=1',(json.dumps(initial()),))
            c.execute('DELETE FROM throttle')
            c.execute('INSERT OR REPLACE INTO config VALUES(?,?)',('password_hash',generate_password_hash('test-password-long')))
            c.execute('INSERT OR REPLACE INTO config VALUES(?,?)',('auth_version','v1'))
        self.token=self.c.get('/api/session').json['csrf']
    def post(self,path,data):
        return self.c.post('/api/'+path,json=data,headers={'X-CSRF-Token':self.token})
    def login(self):
        r=self.post('login',{'password':'test-password-long'})
        self.assertEqual(r.status_code,200)
        self.token=r.json['csrf']
    def write(self,**data):
        return self.post('change',data)
    def fund(self):
        self.assertEqual(self.write(op='transaction',name='Gaji',kind='income',amount=10000000,category='Gaji',date='2026-11-01').status_code,200)
    def test_auth_and_csrf(self):
        self.assertEqual(self.c.get('/api/state').status_code,401)
        self.assertEqual(self.c.post('/api/login',json={}).status_code,403)
    def test_goal_allocation(self):
        self.login();self.fund()
        self.assertEqual(self.write(op='goal',kind='dream',mode='fixed',name='Laptop',base=0,months=1,target=10000000,saved=0,deadline='2027-12-31',method='fixed',contribution=1000000,priority='Sedang',account='Bank',active=True).status_code,200)
        gid=self.c.get('/api/state').json['goals'][0]['id']
        self.assertEqual(self.write(op='allocate',id=gid,direction='add',amount=2000000).status_code,200)
        self.assertEqual(self.c.get('/api/state').json['totals'],dict(balance=10000000,allocated=2000000,free=8000000))
        self.assertEqual(self.write(op='allocate',id=gid,direction='add',amount=9000000).status_code,400)
    def test_receivable_principal(self):
        self.login();self.fund()
        self.assertEqual(self.write(op='obligation',kind='receivable',name='Budi',total=2000000,source='now',date='2026-11-01',due='2026-12-01').status_code,200)
        oid=self.c.get('/api/state').json['obligations'][0]['id']
        self.assertEqual(self.write(op='pay',id=oid,amount=500000,date='2026-11-20').status_code,200)
        s=self.c.get('/api/state').json
        self.assertEqual(s['totals']['balance'],8500000)
        self.assertEqual(s['transactions'][-1]['kind'],'receivable_in')
    def test_integer_validation_and_throttle(self):
        self.login()
        self.assertEqual(self.write(op='transaction',name='X',kind='income',amount=True,category='X',date='2026-11-01').status_code,400)
        self.post('logout',{})
        self.token=self.c.get('/api/session').json['csrf']
        for _ in range(5):
            self.assertEqual(self.post('login',{'password':'wrong'}).status_code,401)
        self.assertEqual(self.post('login',{'password':'wrong'}).status_code,429)
    def test_reset_revokes_session(self):
        self.login()
        with db(True) as c:
            c.execute("UPDATE config SET value='v2' WHERE key='auth_version'")
        self.assertEqual(self.c.get('/api/state').status_code,401)
    def test_html_nonce(self):
        r=self.c.get('/')
        self.assertEqual(r.status_code,200)
        self.assertIn('nonce-',r.headers['Content-Security-Policy'])
        self.assertNotIn(b'{{ nonce }}',r.data)
if __name__=='__main__':
    unittest.main()
