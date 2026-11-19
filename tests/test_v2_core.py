import unittest
from datetime import date
from v2_core import amount, convert, exchange_rate, payday_in_month, salary_schedule, salary_key

class CoreTests(unittest.TestCase):
    def test_conversion_and_rounding(self):
        self.assertEqual(convert(1000, 'KRW', 'IDR', '11.5'), 11500)
        self.assertEqual(convert(11500, 'IDR', 'KRW', '11.5'), 1000)
        self.assertEqual(convert(1, 'KRW', 'IDR', '11.5'), 12)
        self.assertEqual(convert(100, 'IDR', 'IDR', None), 100)

    def test_invalid_money(self):
        for value in (True, -1, 1.2, '100'):
            with self.assertRaises(ValueError):
                amount(value, 'KRW')
        with self.assertRaises(ValueError):
            amount(1, 'USD')

    def test_invalid_rate(self):
        for value in ('NaN', 'Infinity', '0', '-1', None, True, 11.5):
            with self.assertRaises(ValueError):
                exchange_rate(value)

    def test_short_month(self):
        self.assertEqual(payday_in_month(2028, 2, 31), date(2028, 2, 29))
        self.assertEqual(payday_in_month(2027, 2, 31), date(2027, 2, 28))

    def test_catchup_and_pause(self):
        dates = list(salary_schedule(date(2026, 11, 1), date(2027, 2, 28), 31,
            [(date(2026, 12, 1), date(2027, 1, 31))]))
        self.assertEqual(dates, [date(2026, 11, 30), date(2027, 2, 28)])
        self.assertEqual(salary_key(dates[0]), 'salary:2026-11')

    def test_indefinite_pause_and_no_early_salary(self):
        self.assertEqual(list(salary_schedule(date(2026, 11, 1), date(2026, 11, 24), 25)), [])
        self.assertEqual(list(salary_schedule(date(2026, 11, 1), date(2027, 2, 28), 25,
            [(date(2026, 11, 1), None)])), [])

if __name__ == '__main__':
    unittest.main()
