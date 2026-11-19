"""Pure helpers for the rewrite. Not connected to the live application."""
from calendar import monthrange
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from zoneinfo import ZoneInfo

CURRENCIES = frozenset(('KRW', 'IDR'))
MAX_AMOUNT = 100_000_000_000_000

def amount(value, currency):
    if currency not in CURRENCIES:
        raise ValueError('Mata uang harus KRW atau IDR.')
    if type(value) is not int or not 0 <= value <= MAX_AMOUNT:
        raise ValueError('Nominal harus bilangan bulat nonnegatif dalam batas.')
    return value

def exchange_rate(value):
    if isinstance(value, (bool, float)):
        raise ValueError('Kurs harus teks desimal atau Decimal, bukan float.')
    try:
        rate = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError('Kurs tidak valid.') from None
    if not rate.is_finite() or not Decimal('0.000001') <= rate <= Decimal('1000000'):
        raise ValueError('Kurs di luar batas.')
    return rate

def convert(value, source, target, idr_per_krw):
    amount(value, source)
    if target not in CURRENCIES:
        raise ValueError('Mata uang tujuan tidak valid.')
    if source == target:
        return value
    rate = exchange_rate(idr_per_krw)
    with_value = Decimal(value) * rate if source == 'KRW' else Decimal(value) / rate
    return int(with_value.quantize(Decimal('1'), rounding=ROUND_HALF_UP))

def payday_in_month(year, month, payday):
    if type(payday) is not int or not 1 <= payday <= 31:
        raise ValueError('Tanggal gaji harus 1 sampai 31.')
    return date(year, month, min(payday, monthrange(year, month)[1]))

def seoul_today():
    return datetime.now(ZoneInfo('Asia/Seoul')).date()

def salary_schedule(start, through, payday, blocked=()):
    """Return due dates; blocked ranges are inclusive and may have no end."""
    payday_in_month(start.year, start.month, payday)
    for first, last in blocked:
        if last is not None and last < first:
            raise ValueError('Rentang jeda tidak valid.')
    year, month = start.year, start.month
    while (year, month) <= (through.year, through.month):
        due = payday_in_month(year, month, payday)
        if start <= due <= through and not any(
            first <= due and (last is None or due <= last)
            for first, last in blocked
        ):
            yield due
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)

def salary_key(due):
    """Persistence must enforce this key with a UNIQUE constraint."""
    return 'salary:' + due.strftime('%Y-%m')
