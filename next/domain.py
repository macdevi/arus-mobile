"""Standalone financial domain reconstructed from the candidate. Retest before deployment."""
import os, json, sqlite3, calendar, time
from pathlib import Path
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from contextlib import contextmanager
from zoneinfo import ZoneInfo
from urllib.request import Request, urlopen

LIMIT=100_000_000_000_000
SCHEMA='''
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS rates(day TEXT PRIMARY KEY,rate TEXT NOT NULL,source TEXT NOT NULL,fetched TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tx(id INTEGER PRIMARY KEY,day TEXT NOT NULL,kind TEXT NOT NULL,currency TEXT NOT NULL CHECK(currency IN ('KRW','IDR')),amount INTEGER NOT NULL CHECK(typeof(amount)='integer' AND amount>0),description TEXT NOT NULL,category TEXT NOT NULL DEFAULT '',other_amount INTEGER,rate TEXT,rate_day TEXT,rate_source TEXT,salary_period TEXT UNIQUE,voided TEXT);
CREATE TABLE IF NOT EXISTS goals(id INTEGER PRIMARY KEY,name TEXT NOT NULL,currency TEXT NOT NULL,target INTEGER NOT NULL CHECK(target>0),active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS allocations(id INTEGER PRIMARY KEY,goal_id INTEGER NOT NULL REFERENCES goals(id),day TEXT NOT NULL,currency TEXT NOT NULL,delta INTEGER NOT NULL CHECK(delta!=0));
CREATE TABLE IF NOT EXISTS loans(id INTEGER PRIMARY KEY,name TEXT NOT NULL,currency TEXT NOT NULL,installment INTEGER NOT NULL CHECK(installment>0),count INTEGER NOT NULL CHECK(count BETWEEN 1 AND 1200),first_due TEXT NOT NULL,due_day INTEGER NOT NULL CHECK(due_day BETWEEN 1 AND 31),principal INTEGER);
CREATE TABLE IF NOT EXISTS payments(id INTEGER PRIMARY KEY,loan_id INTEGER NOT NULL REFERENCES loans(id),tx_id INTEGER NOT NULL UNIQUE REFERENCES tx(id),period TEXT NOT NULL,principal INTEGER,voided TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS payments_live ON payments(loan_id,period) WHERE voided IS NULL;
CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY,fingerprint TEXT NOT NULL,result TEXT NOT NULL);
'''
def today(): return datetime.now(ZoneInfo('Asia/Seoul')).date()
def integer(v,low=0,high=LIMIT):
    if type(v) is not int or not low<=v<=high: raise ValueError('Angka tidak valid.')
    return v
def currency(v):
    if v not in ('KRW','IDR'): raise ValueError('Mata uang harus KRW atau IDR.')
    return v
def text(v,limit=120):
    if not isinstance(v,str) or not v.strip() or len(v)>limit: raise ValueError('Teks wajib diisi dalam batas panjang.')
    return v.strip()
def day(v):
    if not isinstance(v,str): raise ValueError('Tanggal wajib diisi.')
    parsed=date.fromisoformat(v)
    if not 1900<=parsed.year<=2100: raise ValueError('Tahun di luar batas.')
    return parsed.isoformat()
def past(v):
    v=day(v)
    if v>today().isoformat(): raise ValueError('Transaksi aktual tidak boleh bertanggal masa depan.')
    return v
def rate_value(v):
    if isinstance(v,(float,bool)): raise ValueError('Kurs harus teks desimal.')
    try: r=Decimal(v)
    except (TypeError,ValueError,InvalidOperation): raise ValueError('Kurs tidak valid.') from None
    if not r.is_finite() or not Decimal('0.000001')<=r<=Decimal('1000000'): raise ValueError('Kurs tidak valid.')
    return str(r)
def cv(n,source,target,rate):
    if n==0 or source==target: return n
    if rate is None: return None
    r=Decimal(rate_value(rate)); value=Decimal(abs(n))*r if source=='KRW' else Decimal(abs(n))/r
    return (1 if n>=0 else -1)*int(value.quantize(Decimal('1'),rounding=ROUND_HALF_UP))
def due_date(first,dom,index):
    d=date.fromisoformat(first); m=d.year*12+d.month-1+index
    return first if index==0 else date(m//12,m%12+1,min(dom,calendar.monthrange(m//12,m%12+1)[1])).isoformat()
@contextmanager
def db(path,write=False):
    c=sqlite3.connect(path,timeout=15,isolation_level=None); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON')
    try:
        c.execute('BEGIN IMMEDIATE' if write else 'BEGIN'); yield c; c.commit()
    except Exception: c.rollback(); raise
    finally: c.close()
def get(c,k,default=None):
    row=c.execute('SELECT value FROM meta WHERE key=?',(k,)).fetchone()
    return json.loads(row[0]) if row else default
def put(c,k,v): c.execute('INSERT OR REPLACE INTO meta VALUES(?,?)',(k,json.dumps(v)))
def initialize(path):
    Path(path).parent.mkdir(parents=True,exist_ok=True); c=sqlite3.connect(path)
    try: c.executescript(SCHEMA); c.commit()
    finally: c.close()
    os.chmod(path,0o600)
def latest(c,on=None): return c.execute('SELECT * FROM rates WHERE day<=? ORDER BY day DESC LIMIT 1',(on or today().isoformat(),)).fetchone()
def balances(c):
    result={'KRW':0,'IDR':0}
    for t in c.execute('SELECT * FROM tx WHERE voided IS NULL'):
        result[t['currency']]+=t['amount']*(-1 if t['kind'] in ('expense','exchange') else 1)
        if t['kind']=='exchange': result['IDR' if t['currency']=='KRW' else 'KRW']+=t['other_amount']
    return result
def reserved(c):
    r={'KRW':0,'IDR':0}
    for row in c.execute('SELECT currency,SUM(delta) total FROM allocations GROUP BY currency'): r[row['currency']]=row['total']
    return r
def free(c):
    b=balances(c); a=reserved(c); return {k:b[k]-a[k] for k in b}
def insert_tx(c,d,kind=None,salary_period=None):
    k=kind or d.get('kind'); cur=currency(d.get('currency')); n=integer(d.get('amount'),1); when=past(d.get('day'))
    if k not in ('income','expense','exchange','opening'): raise ValueError('Jenis transaksi tidak valid.')
    if k in ('expense','exchange') and free(c)[cur]<n: raise ValueError('Saldo bebas tidak cukup. Lepaskan alokasi dahulu.')
    other=integer(d.get('other_amount'),1) if k=='exchange' else None; fx=latest(c,when)
    if (cur=='KRW' or k=='exchange') and not fx: raise ValueError('Kurs tanggal transaksi belum tersedia.')
    return c.execute('INSERT INTO tx(day,kind,currency,amount,description,category,other_amount,rate,rate_day,rate_source,salary_period) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(when,k,cur,n,text(d.get('description')),text(d.get('category') or 'Lainnya',60),other,fx['rate'] if fx else None,fx['day'] if fx else None,fx['source'] if fx else None,salary_period)).lastrowid
def fetch_rate(on=None):
    when=past(on or today().isoformat()); url='https://api.frankfurter.dev/v2/rate/krw/idr?providers=ecb&date='+when
    with urlopen(Request(url,headers={'User-Agent':'ArusNext/1.0'}),timeout=8) as response: raw=response.read(65537)
    if len(raw)>65536: raise ValueError('Respons kurs terlalu besar.')
    data=json.loads(raw,parse_float=str)
    if not isinstance(data,dict): raise ValueError('Respons kurs bukan objek.')
    if str(data.get('base','KRW')).upper()!='KRW' or str(data.get('quote','IDR')).upper()!='IDR': raise ValueError('Pasangan kurs tidak sesuai.')
    effective=day(data['date'])
    if effective>when: raise ValueError('Tanggal kurs melampaui permintaan.')
    return effective,rate_value(data['rate']),'Frankfurter / ECB'
def refresh(path,on=None,fetcher=None):
    observed,r,source=(fetcher or fetch_rate)(on); observed=past(observed); r=rate_value(r); source=text(source)
    with db(path,True) as c: c.execute('INSERT INTO rates VALUES(?,?,?,?) ON CONFLICT(day) DO UPDATE SET rate=excluded.rate,source=excluded.source,fetched=excluded.fetched',(observed,r,source,datetime.now(ZoneInfo('UTC')).isoformat()))
    return observed
def salary_due(c,through):
    rules=get(c,'salary_rules',[]); pauses=get(c,'pauses',[]); result={}
    for i,rule in enumerate(rules):
        start=date.fromisoformat(rule['effective_from']); end=through
        if i+1<len(rules): end=min(end,date.fromisoformat(rules[i+1]['effective_from'])-timedelta(days=1))
        y,m=start.year,start.month
        while (y,m)<=(end.year,end.month):
            due=date(y,m,min(rule['payday'],calendar.monthrange(y,m)[1])); period=due.strftime('%Y-%m')
            paused=any(p['start']<=due.isoformat() and (p['end'] is None or due.isoformat()<=p['end']) for p in pauses)
            if start<=due<=end and not paused and period not in result and not c.execute('SELECT 1 FROM tx WHERE salary_period=?',(period,)).fetchone(): result[period]=(due.isoformat(),rule['amount'])
            y,m=(y+1,1) if m==12 else (y,m+1)
    return result
def tick(path,fetcher=None,budget=3):
    errors=[]
    try: refresh(path,fetcher=fetcher)
    except Exception as e: errors.append(type(e).__name__)
    with db(path) as c: candidates=salary_due(c,today())
    for when,_ in list(candidates.values())[:budget]:
        with db(path) as c: found=latest(c,when)
        if not found:
            try: refresh(path,when,fetcher)
            except Exception as e: errors.append(type(e).__name__)
    created=[]; waiting=[]
    with db(path,True) as c:
        for period,(when,n) in salary_due(c,today()).items():
            if not latest(c,when): waiting.append(when); continue
            created.append(insert_tx(c,dict(currency='KRW',amount=n,day=when,description='Gaji otomatis',category='Gaji'),'income',period))
    return dict(created=created,waiting_for_rate=waiting,errors=errors)
def loan_info(c,l):
    paid=c.execute('SELECT COUNT(*) n,SUM(principal) p,SUM(principal IS NULL) unknown FROM payments WHERE loan_id=? AND voided IS NULL',(l['id'],)).fetchone(); count=max(0,l['count']-paid['n'])
    principal=None if l['principal'] is None or paid['unknown'] else l['principal']-(paid['p'] or 0)
    return dict(l,remaining_count=count,remaining_payments=count*l['installment'],next_due=due_date(l['first_due'],l['due_day'],paid['n']) if count else None,remaining_principal=principal)
def snapshot(c,month):
    if not isinstance(month,str) or len(month)!=7: raise ValueError('Bulan harus YYYY-MM.')
    day(month+'-01'); fx=latest(c); r=fx['rate'] if fx else None
    def total(values):
        numbers=[cv(n,k,'IDR',r) for k,n in values.items()]; return None if None in numbers else sum(numbers)
    b=balances(c); a=reserved(c); f=free(c); monthly={'income':0,'expense':0}
    for t in c.execute("SELECT * FROM tx WHERE voided IS NULL AND day LIKE ? AND kind IN ('income','expense')",(month+'-%',)):
        n=cv(t['amount'],t['currency'],'IDR',t['rate']); monthly[t['kind']]=None if n is None or monthly[t['kind']] is None else monthly[t['kind']]+n
    goals=[]
    for g in c.execute('SELECT * FROM goals ORDER BY id DESC'):
        values={row['currency']:row['n'] for row in c.execute('SELECT currency,SUM(delta) n FROM allocations WHERE goal_id=? GROUP BY currency',(g['id'],))}; converted=[cv(n,k,g['currency'],r) for k,n in values.items()]; saved=None if None in converted else sum(converted)
        goals.append(dict(g,saved=saved,allocations=values,percent=None if saved is None else round(saved/g['target']*100,1)))
    loans=[loan_info(c,l) for l in c.execute('SELECT * FROM loans ORDER BY id DESC')]; debt={cur:sum(l['remaining_payments'] for l in loans if l['currency']==cur) for cur in ('KRW','IDR')}
    settings=dict(salary_rules=get(c,'salary_rules',[]),pauses=get(c,'pauses',[]),opening_set=get(c,'opening_set',False))
    return dict(month=month,balances=b,reserved=a,free=f,balance_idr=total(b),free_idr=total(f),monthly=monthly,goals=goals,loans=loans,debt=debt,debt_idr=total(debt),rate=dict(fx) if fx else None,settings=settings,transactions=[dict(t) for t in c.execute('SELECT * FROM tx ORDER BY day DESC,id DESC LIMIT 100')])
def action(c,d):
    op=d.get('op')
    if op=='transaction': return {'id':insert_tx(c,d)}
    if op=='opening':
        if get(c,'opening_set',False) or c.execute('SELECT 1 FROM tx').fetchone(): raise ValueError('Saldo awal hanya sebelum transaksi pertama.')
        for cur in ('KRW','IDR'):
            n=integer(d.get(cur,0))
            if n: insert_tx(c,dict(currency=cur,amount=n,day=d.get('day'),description='Saldo awal',category='Saldo awal'),'opening')
        put(c,'opening_set',True); return {'ok':True}
    if op=='salary':
        start=day(d.get('effective_from')); n=integer(d.get('amount'),1); dom=integer(d.get('payday'),1,31)
        if c.execute('SELECT 1 FROM tx WHERE salary_period IS NOT NULL AND day>=?',(start,)).fetchone(): raise ValueError('Aturan baru tidak boleh menimpa gaji tercatat.')
        rules=[r for r in get(c,'salary_rules',[]) if r['effective_from']!=start]; rules.append(dict(effective_from=start,amount=n,payday=dom)); put(c,'salary_rules',sorted(rules,key=lambda r:r['effective_from'])); return {'ok':True}
    if op=='pause':
        start=day(d.get('start')); end=day(d['end']) if d.get('end') else None
        if end and end<start: raise ValueError('Akhir jeda mendahului awal.')
        if c.execute('SELECT 1 FROM tx WHERE salary_period IS NOT NULL AND day>=? AND (? IS NULL OR day<=?)',(start,end,end)).fetchone(): raise ValueError('Batalkan gaji tercatat sebelum menjeda periode tersebut.')
        pauses=get(c,'pauses',[]); pauses.append(dict(start=start,end=end)); put(c,'pauses',pauses); return {'ok':True}
    if op=='resume':
        resume=day(d.get('day')); pauses=get(c,'pauses',[])
        for p in pauses:
            if p['end'] is None:
                if resume<=p['start']: raise ValueError('Tanggal aktif kembali harus setelah awal jeda.')
                p['end']=(date.fromisoformat(resume)-timedelta(days=1)).isoformat()
        put(c,'pauses',pauses); return {'ok':True}
    if op=='goal': return {'id':c.execute('INSERT INTO goals(name,currency,target) VALUES(?,?,?)',(text(d.get('name')),currency(d.get('currency')),integer(d.get('target'),1))).lastrowid}
    if op=='allocate':
        gid=integer(d.get('goal_id'),1); cur=currency(d.get('currency')); delta=d.get('delta'); integer(abs(delta) if type(delta) is int else None,1)
        g=c.execute('SELECT * FROM goals WHERE id=? AND active=1',(gid,)).fetchone()
        if not g: raise ValueError('Target tidak ditemukan.')
        saved={r['currency']:r['n'] for r in c.execute('SELECT currency,SUM(delta) n FROM allocations WHERE goal_id=? GROUP BY currency',(gid,))}
        if delta>0 and free(c)[cur]<delta: raise ValueError('Saldo bebas tidak cukup.')
        if delta<0 and saved.get(cur,0)<-delta: raise ValueError('Alokasi tidak cukup untuk dilepas.')
        saved[cur]=saved.get(cur,0)+delta; fx=latest(c); values=[cv(n,k,g['currency'],fx['rate'] if fx else None) for k,n in saved.items()]
        if delta>0 and (None in values or sum(values)>g['target']): raise ValueError('Kurs belum tersedia atau alokasi melebihi target.')
        c.execute('INSERT INTO allocations(goal_id,day,currency,delta) VALUES(?,?,?,?)',(gid,past(d.get('day')),cur,delta)); return {'ok':True}
    if op=='loan':
        principal=integer(d['principal']) if d.get('principal') is not None else None
        return {'id':c.execute('INSERT INTO loans(name,currency,installment,count,first_due,due_day,principal) VALUES(?,?,?,?,?,?,?)',(text(d.get('name')),currency(d.get('currency')),integer(d.get('installment'),1),integer(d.get('count'),1,1200),day(d.get('first_due')),integer(d.get('due_day'),1,31),principal)).lastrowid}
    if op=='pay':
        lid=integer(d.get('loan_id'),1); period=day(d.get('period')); when=past(d.get('day')); principal=d.get('principal')
        old=c.execute('SELECT p.*,t.day FROM payments p JOIN tx t ON t.id=p.tx_id WHERE loan_id=? AND period=? AND p.voided IS NULL',(lid,period)).fetchone()
        if old:
            if old['day']!=when or old['principal']!=principal: raise ValueError('Periode sudah dibayar dengan rincian berbeda.')
            return {'id':old['tx_id']}
        l=c.execute('SELECT * FROM loans WHERE id=?',(lid,)).fetchone()
        if not l: raise ValueError('Cicilan tidak ditemukan.')
        info=loan_info(c,l)
        if period!=info['next_due']: raise ValueError('Pilih periode cicilan berikutnya.')
        if principal is not None:
            integer(principal,0,l['installment']); known=c.execute('SELECT COALESCE(SUM(principal),0) FROM payments WHERE loan_id=? AND voided IS NULL',(lid,)).fetchone()[0]
            if l['principal'] is not None and principal+known>l['principal']: raise ValueError('Pokok pembayaran melebihi sisa pokok.')
        tid=insert_tx(c,dict(currency=l['currency'],amount=l['installment'],day=when,description='Cicilan: '+l['name'],category='Cicilan'),'expense'); c.execute('INSERT INTO payments(loan_id,tx_id,period,principal) VALUES(?,?,?,?)',(lid,tid,period,principal)); return {'id':tid}
    if op=='void':
        tid=integer(d.get('id'),1); t=c.execute('SELECT * FROM tx WHERE id=?',(tid,)).fetchone()
        if not t: raise ValueError('Transaksi tidak ditemukan.')
        if t['voided']: return {'ok':True}
        p=c.execute('SELECT * FROM payments WHERE tx_id=? AND voided IS NULL',(tid,)).fetchone()
        if p and c.execute('SELECT 1 FROM payments WHERE loan_id=? AND period>? AND voided IS NULL',(p['loan_id'],p['period'])).fetchone(): raise ValueError('Batalkan cicilan mulai periode terakhir.')
        c.execute('UPDATE tx SET voided=? WHERE id=?',(today().isoformat(),tid)); c.execute('UPDATE payments SET voided=? WHERE tx_id=?',(today().isoformat(),tid))
        if any(n<0 for n in free(c).values()): raise ValueError('Pembatalan membuat saldo bebas negatif.')
        return {'ok':True}
    if op=='manual_rate':
        observed=past(d.get('day')); r=rate_value(d.get('rate')); c.execute('INSERT INTO rates VALUES(?,?,?,?) ON CONFLICT(day) DO UPDATE SET rate=excluded.rate,source=excluded.source,fetched=excluded.fetched',(observed,r,'Manual',datetime.now(ZoneInfo('UTC')).isoformat())); return {'ok':True}
    raise ValueError('Operasi tidak dikenali.')
