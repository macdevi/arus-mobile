"""Domain services. Caller validates settings; no network or background threads."""
from datetime import date, timedelta
from v2_core import amount, convert, payday_in_month, salary_schedule, salary_key
from v2.ledger import atomic, post, balances

def allocate(db, goal_id, currency, delta, occurred_on, rate):
    date.fromisoformat(occurred_on)
    amount(abs(delta), currency)
    if type(delta) is not int or delta == 0:
        raise ValueError('Alokasi harus bilangan bulat bukan nol.')
    with atomic(db):
        goal = db.execute('SELECT currency,target,active FROM v2_goals WHERE id=?',(goal_id,)).fetchone()
        if not goal or not goal[2]:
            raise ValueError('Target tidak ditemukan atau tidak aktif.')
        saved = dict(db.execute('SELECT currency,SUM(delta) FROM v2_allocations WHERE goal_id=? AND voided_at IS NULL GROUP BY currency',(goal_id,)))
        reserved = dict(db.execute('SELECT currency,SUM(delta) FROM v2_allocations WHERE voided_at IS NULL GROUP BY currency'))
        if delta < 0 and saved.get(currency,0) + delta < 0:
            raise ValueError('Alokasi yang dilepas tidak mencukupi.')
        if delta > 0 and balances(db)[currency] - reserved.get(currency,0) < delta:
            raise ValueError('Saldo bebas mata uang ini tidak mencukupi.')
        saved[currency] = saved.get(currency,0) + delta
        total = sum(convert(n, cur, goal[0], rate) for cur,n in saved.items())
        if delta > 0 and total > goal[1]:
            raise ValueError('Alokasi melebihi target pada kurs saat ini.')
        return db.execute('INSERT INTO v2_allocations(goal_id,occurred_on,currency,delta) VALUES(?,?,?,?)',
                          (goal_id,occurred_on,currency,delta)).lastrowid

def pay_installment(db, loan_id, occurred_on, *, rate=None, rate_date=None, rate_source=None, principal=None):
    date.fromisoformat(occurred_on)
    with atomic(db):
        loan = db.execute('SELECT name,currency,installment,remaining_count,next_due,due_day,outstanding_principal,archived FROM v2_loans WHERE id=?',(loan_id,)).fetchone()
        if not loan or loan[7]:
            raise ValueError('Cicilan tidak ditemukan atau diarsipkan.')
        count, principal_paid = db.execute('SELECT COUNT(*),COALESCE(SUM(principal),0) FROM v2_loan_payments WHERE loan_id=? AND voided_at IS NULL',(loan_id,)).fetchone()
        if count >= loan[3]:
            raise ValueError('Semua cicilan terjadwal sudah dibayar.')
        first = date.fromisoformat(loan[4])
        month = first.year*12 + first.month-1 + count
        due = first if count == 0 else payday_in_month(month//12,month%12+1,loan[5])
        if principal is not None:
            amount(principal, loan[1])
            if principal > loan[2] or (loan[6] is not None and principal_paid+principal > loan[6]):
                raise ValueError('Komponen pokok melebihi batas.')
        if balances(db)[loan[1]] < loan[2]:
            raise ValueError('Saldo mata uang pembayaran tidak cukup.')
        tid = post(db,occurred_on=occurred_on,kind='expense',description='Cicilan: '+loan[0],
                   category='Cicilan',entries=[(loan[1],-loan[2])],rate=rate,rate_date=rate_date,rate_source=rate_source)
        db.execute('INSERT INTO v2_loan_payments(loan_id,transaction_id,scheduled_for,amount,principal) VALUES(?,?,?,?,?)',
                   (loan_id,tid,due.isoformat(),loan[2],principal))
        return tid

def process_salary(db, through, rates):
    """rates maps due-date strings to (rate, rate_date, source). Missing dates wait."""
    through = date.fromisoformat(through)
    created, waiting = [], []
    with atomic(db):
        rules = db.execute('SELECT effective_from,amount_krw,payday FROM v2_salary_rules ORDER BY effective_from').fetchall()
        pauses = [(date.fromisoformat(a),date.fromisoformat(b) if b else None) for a,b in db.execute('SELECT starts_on,ends_on FROM v2_salary_pauses')]
        for index,(starts,nominal,payday) in enumerate(rules):
            end = min(through,date.fromisoformat(rules[index+1][0])-timedelta(days=1)) if index+1<len(rules) else through
            for due in salary_schedule(date.fromisoformat(starts),end,payday,pauses):
                period = salary_key(due).split(':',1)[1]
                if db.execute('SELECT 1 FROM v2_transactions WHERE salary_period=?',(period,)).fetchone():
                    continue
                snapshot = rates.get(due.isoformat())
                if snapshot is None:
                    waiting.append(due.isoformat())
                    continue
                rate, rate_date, source = snapshot
                if date.fromisoformat(rate_date) > due:
                    raise ValueError('Kurs gaji tidak boleh berasal dari masa depan transaksi.')
                created.append(post(db,occurred_on=due.isoformat(),kind='income',description='Gaji otomatis',
                    category='Gaji',entries=[('KRW',nominal)],salary_period=period,
                    rate=rate,rate_date=rate_date,rate_source=source))
    return {'created':created,'waiting_for_rate':waiting}
