import sqlite3
import unittest
from v2.ledger import initialize, post, balances, atomic

class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:', isolation_level=None)
        initialize(self.db)
    def tearDown(self):
        self.db.close()
    def post(self, kind, entries, **kw):
        return post(self.db, occurred_on='2026-11-25', kind=kind, description='Test', entries=entries, **kw)
    def krw(self, **kw):
        return self.post('income',[('KRW',100)],rate='11.5',rate_date='2026-11-25',rate_source='test',**kw)
    def test_initialize_twice(self):
        initialize(self.db)
    def test_balances(self):
        self.krw()
        self.post('income',[('IDR',200)])
        self.assertEqual(balances(self.db),{'KRW':100,'IDR':200})
    def test_salary_duplicate(self):
        self.krw(salary_period='2026-11')
        with self.assertRaises(sqlite3.IntegrityError):
            self.krw(salary_period='2026-11')
        self.assertEqual(balances(self.db)['KRW'],100)
    def test_snapshot_saved(self):
        self.krw()
        self.assertEqual(self.db.execute('SELECT idr_per_krw,rate_date,rate_source FROM v2_entries').fetchone(),('11.5','2026-11-25','test'))
    def test_krw_requires_snapshot(self):
        with self.assertRaises(ValueError):
            self.post('income',[('KRW',100)])
    def test_invalid_exchange(self):
        with self.assertRaises(ValueError):
            self.post('exchange',[('IDR',100),('KRW',100)])
    def test_atomic_rollback(self):
        with self.assertRaises(RuntimeError):
            with atomic(self.db):
                self.krw()
                raise RuntimeError('cancel')
        self.assertEqual(balances(self.db)['KRW'],0)
    def test_boolean_rejected(self):
        with self.assertRaises(ValueError):
            self.post('income',[('IDR',True)])
    def test_invalid_goal_currency(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("INSERT INTO v2_goals(name,currency,target) VALUES('Goal','USD',100)")

if __name__=='__main__':
    unittest.main()
