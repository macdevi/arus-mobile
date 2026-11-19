PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS v2_transactions (
 id INTEGER PRIMARY KEY,
 occurred_on TEXT NOT NULL,
 kind TEXT NOT NULL CHECK(kind IN ('income','expense','exchange','adjustment')),
 description TEXT NOT NULL,
 category TEXT NOT NULL DEFAULT '',
 salary_period TEXT UNIQUE,
 voided_at TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS v2_entries (
 id INTEGER PRIMARY KEY,
 transaction_id INTEGER NOT NULL REFERENCES v2_transactions(id),
 currency TEXT NOT NULL CHECK(currency IN ('KRW','IDR')),
 delta INTEGER NOT NULL CHECK(typeof(delta)='integer' AND delta != 0 AND abs(delta)<=100000000000000),
 idr_per_krw TEXT,
 rate_date TEXT,
 rate_source TEXT
);
CREATE TABLE IF NOT EXISTS v2_rates (
 id INTEGER PRIMARY KEY,
 rate_date TEXT NOT NULL,
 idr_per_krw TEXT NOT NULL,
 source TEXT NOT NULL,
 fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS v2_salary_rules (
 id INTEGER PRIMARY KEY,
 effective_from TEXT NOT NULL UNIQUE,
 amount_krw INTEGER NOT NULL CHECK(typeof(amount_krw)='integer' AND amount_krw>0 AND amount_krw<=100000000000000),
 payday INTEGER NOT NULL CHECK(payday BETWEEN 1 AND 31),
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS v2_salary_pauses (
 id INTEGER PRIMARY KEY,
 starts_on TEXT NOT NULL,
 ends_on TEXT CHECK(ends_on IS NULL OR ends_on >= starts_on),
 reason TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS v2_entries_transaction ON v2_entries(transaction_id);
CREATE INDEX IF NOT EXISTS v2_transactions_date ON v2_transactions(occurred_on);
