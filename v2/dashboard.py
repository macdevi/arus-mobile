from datetime import date
from v2_core import convert, payday_in_month
from v2.ledger import balances

def build_dashboard(db, month, rate=None):
    if not isinstance(month,str) or len(month)!=7:
        raise ValueError('Bulan harus YYYY-MM.')
    date.fromisoformat(month+'-01')
    def estimate(values):
        if values.get('KRW',0) and rate is None:
            return None
        return sum((1 if n>=0 else -1)*convert(abs(n),cur,'IDR',rate) for cur,n in values.items() if n)
    cash = balances(db)
    reserved = {'KRW':0,'IDR':0}
    reserved.update(db.execute('SELECT currency,SUM(delta) FROM v2_allocations WHERE voided_at IS NULL GROUP BY currency'))
    free = {cur:cash[cur]-reserved[cur] for cur in cash}
    monthly = {'income':0,'expense':0}
    missing = False
    for kind,cur,delta,snapshot in db.execute("SELECT t.kind,e.currency,e.delta,e.idr_per_krw FROM v2_entries e JOIN v2_transactions t ON t.id=e.transaction_id WHERE t.voided_at IS NULL AND t.occurred_on LIKE ? AND t.kind IN ('income','expense')",(month+'-%',)):
        if cur=='KRW' and snapshot is None:
            missing = True
            continue
        monthly[kind] += convert(abs(delta),cur,'IDR',snapshot)
    goals=[]
    for gid,name,cur,target in db.execute('SELECT id,name,currency,target FROM v2_goals WHERE active=1 ORDER BY id'):
        saved=dict(db.execute('SELECT currency,SUM(delta) FROM v2_allocations WHERE goal_id=? AND voided_at IS NULL GROUP BY currency',(gid,)))
        value=None if rate is None and any(k!=cur and n for k,n in saved.items()) else sum(convert(n,k,cur,rate) for k,n in saved.items() if n)
        goals.append(dict(id=gid,name=name,currency=cur,target=target,saved=saved,estimated_saved=value))
    loans=[]
    remaining={'KRW':0,'IDR':0}
    for lid,name,cur,installment,total,first,day in db.execute('SELECT id,name,currency,installment,remaining_count,next_due,due_day FROM v2_loans WHERE archived=0 ORDER BY id'):
        paid=db.execute('SELECT COUNT(*) FROM v2_loan_payments WHERE loan_id=? AND voided_at IS NULL',(lid,)).fetchone()[0]
        count=max(0,total-paid)
        start=date.fromisoformat(first)
        index=start.year*12+start.month-1+paid
        due=None if count==0 else (start if paid==0 else payday_in_month(index//12,index%12+1,day)).isoformat()
        remaining[cur]+=count*installment
        loans.append(dict(id=lid,name=name,currency=cur,remaining_count=count,remaining_payments=count*installment,next_due=due))
    return dict(month=month,balances=cash,reserved=reserved,free=free,estimated_balance_idr=estimate(cash),estimated_free_idr=estimate(free),monthly_idr=None if missing else monthly,net_flow_idr=None if missing else monthly['income']-monthly['expense'],goals=goals,loans=loans,remaining_payments=remaining,estimated_remaining_payments_idr=estimate(remaining))

def register_dashboard(app, authorize, db_path):
    from flask import request, jsonify, render_template_string
    from v2.ledger import connect
    from v2_core import seoul_today
    import secrets
    def snapshot():
        month=request.args.get('month',seoul_today().strftime('%Y-%m'))
        with connect(db_path) as db:
            db.execute('BEGIN')
            latest=db.execute('SELECT idr_per_krw,rate_date,source FROM v2_rates ORDER BY rate_date DESC,id DESC LIMIT 1').fetchone()
            data=build_dashboard(db,month,latest[0] if latest else None)
            data['rate']=dict(value=latest[0],date=latest[1],source=latest[2]) if latest else None
            return data
    @app.get('/api/v2/dashboard')
    @authorize
    def v2_dashboard_api():
        return jsonify(snapshot())
    @app.get('/v2')
    @authorize
    def v2_dashboard_page():
        data=snapshot()
        nonce=secrets.token_urlsafe(24)
        template='''<!doctype html><html lang="id"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Arus v2</title><style nonce="{{ nonce }}">body{font:16px system-ui;background:#f4f6f8;color:#172b3a;margin:0}main{max-width:1000px;margin:auto;padding:24px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:14px}article,section{background:white;padding:20px;border-radius:16px;margin:14px 0}small{color:#506577}strong{font-size:24px;display:block;margin-top:10px}button,input{padding:10px}li{margin:12px 0}</style><main><h1>Arus</h1><p>Pratinjau dashboard, hanya baca.</p><form><input type="month" name="month" value="{{ d.month }}"><button>Lihat</button></form><section>Saldo saat ini<strong>{{ money(d.estimated_balance_idr) }}</strong><p>KRW {{ d.balances.KRW }} · IDR {{ d.balances.IDR }}</p><small>Belum dialokasikan: {{ money(d.estimated_free_idr) }}</small></section><div class="grid"><article>Pemasukan bulan ini<strong>{{ money(d.monthly_idr.income if d.monthly_idr else none) }}</strong></article><article>Pengeluaran bulan ini<strong>{{ money(d.monthly_idr.expense if d.monthly_idr else none) }}</strong></article><article>Target tabungan aktif<strong>{{ d.goals|length }}</strong><small>Rincian progres di bawah</small></article><article>Sisa pembayaran cicilan<strong>{{ money(d.estimated_remaining_payments_idr) }}</strong><small>Bukan sisa pokok pinjaman</small></article></div><section><h2>Tabungan</h2><ul>{% for g in d.goals %}<li>{{ g.name }}: {{ g.estimated_saved if g.estimated_saved is not none else 'Menunggu kurs' }} / {{ g.target }} {{ g.currency }}</li>{% else %}<li>Belum ada target.</li>{% endfor %}</ul></section><section><h2>Cicilan</h2><ul>{% for l in d.loans %}<li>{{ l.name }}: {{ l.remaining_payments }} {{ l.currency }}, {{ l.remaining_count }} kali. Jatuh tempo: {{ l.next_due or 'Lunas' }}</li>{% else %}<li>Belum ada cicilan.</li>{% endfor %}</ul></section><p>{% if d.rate %}Kurs acuan: 1 KRW = {{ d.rate.value }} IDR · {{ d.rate.date }} · {{ d.rate.source }}{% else %}Kurs belum tersedia. Total lintas mata uang belum dihitung.{% endif %}</p><a href="/">Kembali ke aplikasi lama / login</a></main></html>'''
        def money(value):
            return 'Menunggu kurs' if value is None else 'Rp '+format(value,',').replace(',','.')
        response=app.make_response(render_template_string(template,d=data,nonce=nonce,money=money))
        response.headers['Content-Security-Policy']=f"default-src 'none'; style-src 'nonce-{nonce}'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
        return response
