import sqlite3
import unittest
from v2.ledger import initialize, post, balances
from v2.services import allocate, pay_installment, process_salary

class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:',isolation_level=None)
        initialize(self.db)
        post(self.db,occurred_on='2026-11-01',kind='income',description='Awal',entries=[('IDR',1000)])
    def tearDown(self):
        self.db.close()
    def goal(self):
        return self.db.execute("INSERT INTO v2_goals(name,currency,target) VALUES('Target','IDR',1000)").lastrowid
    def loan(self):
        return self.db.execute("INSERT INTO v2_loans(name,currency,installment,remaining_count,next_due,due_day) VALUES('Pinjaman','IDR',100,2,'2026-11-30',31)").lastrowid
    def test_allocation_preserves_cash(self):
        gid=self.goal()
        allocate(self.db,gid,'IDR',400,'2026-11-20','11.5')
        self.assertEqual(balances(self.db)['IDR'],1000)
        allocate(self.db,gid,'IDR',-100,'2026-11-20','11.5')
        self.assertEqual(self.db.execute('SELECT SUM(delta) FROM v2_allocations').fetchone()[0],300)
    def test_overallocation_rejected(self):
        with self.assertRaises(ValueError):
            allocate(self.db,self.goal(),'IDR',1001,'2026-11-20','11.5')
    def test_installments(self):
        lid=self.loan()
        pay_installment(self.db,lid,'2026-11-30')
        pay_installment(self.db,lid,'2026-12-31')
        self.assertEqual(balances(self.db)['IDR'],800)
        self.assertEqual(self.db.execute('SELECT scheduled_for FROM v2_loan_payments ORDER BY id DESC LIMIT 1').fetchone()[0],'2026-12-31')
        with self.assertRaises(ValueError):
            pay_installment(self.db,lid,'2027-01-31')
    def test_salary_idempotent(self):
        self.db.execute("INSERT INTO v2_salary_rules(effective_from,amount_krw,payday) VALUES('2026-11-01',2500000,25)")
        rates={'2026-11-25':('11.5','2026-11-25','test')}
        self.assertEqual(len(process_salary(self.db,'2026-11-30',rates)['created']),1)
        self.assertEqual(process_salary(self.db,'2026-11-30',rates)['created'],[])
        self.assertEqual(balances(self.db)['KRW'],2500000)
    def test_salary_waits_without_rate(self):
        self.db.execute("INSERT INTO v2_salary_rules(effective_from,amount_krw,payday) VALUES('2026-11-01',100,25)")
        self.assertEqual(process_salary(self.db,'2026-11-30',{})['waiting_for_rate'],['2026-11-25'])
    def test_indefinite_salary_pause(self):
        self.db.execute("INSERT INTO v2_salary_rules(effective_from,amount_krw,payday) VALUES('2026-11-01',100,25)")
        self.db.execute("INSERT INTO v2_salary_pauses(starts_on,reason) VALUES('2026-11-01','Jeda')")
        self.assertEqual(process_salary(self.db,'2026-12-31',{})['waiting_for_rate'],[])

if __name__=='__main__':
    unittest.main()
