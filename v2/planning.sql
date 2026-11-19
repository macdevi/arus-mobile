PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS v2_goals (
 id INTEGER PRIMARY KEY,
 name TEXT NOT NULL,
 currency TEXT NOT NULL CHECK(currency IN ('KRW','IDR')),
 target INTEGER NOT NULL CHECK(typeof(target)='integer' AND target>0 AND target<=100000000000000),
 deadline TEXT,
 active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1))
);
CREATE TABLE IF NOT EXISTS v2_allocations (
 id INTEGER PRIMARY KEY,
 goal_id INTEGER NOT NULL REFERENCES v2_goals(id),
 occurred_on TEXT NOT NULL,
 currency TEXT NOT NULL CHECK(currency IN ('KRW','IDR')),
 delta INTEGER NOT NULL CHECK(typeof(delta)='integer' AND delta!=0 AND abs(delta)<=100000000000000),
 voided_at TEXT
);
CREATE TABLE IF NOT EXISTS v2_loans (
 id INTEGER PRIMARY KEY,
 name TEXT NOT NULL,
 currency TEXT NOT NULL CHECK(currency IN ('KRW','IDR')),
 installment INTEGER NOT NULL CHECK(typeof(installment)='integer' AND installment>0 AND installment<=100000000000000),
 remaining_count INTEGER NOT NULL CHECK(typeof(remaining_count)='integer' AND remaining_count BETWEEN 1 AND 1200),
 next_due TEXT NOT NULL,
 due_day INTEGER NOT NULL CHECK(due_day BETWEEN 1 AND 31),
 outstanding_principal INTEGER CHECK(outstanding_principal IS NULL OR (typeof(outstanding_principal)='integer' AND outstanding_principal BETWEEN 0 AND 100000000000000)),
 archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0,1))
);
CREATE TABLE IF NOT EXISTS v2_loan_payments (
 id INTEGER PRIMARY KEY,
 loan_id INTEGER NOT NULL REFERENCES v2_loans(id),
 transaction_id INTEGER NOT NULL UNIQUE REFERENCES v2_transactions(id),
 scheduled_for TEXT NOT NULL,
 amount INTEGER NOT NULL CHECK(typeof(amount)='integer' AND amount>0 AND amount<=100000000000000),
 principal INTEGER CHECK(principal IS NULL OR (typeof(principal)='integer' AND principal BETWEEN 0 AND amount)),
 voided_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS v2_loan_active_period ON v2_loan_payments(loan_id,scheduled_for) WHERE voided_at IS NULL;
CREATE INDEX IF NOT EXISTS v2_allocations_goal ON v2_allocations(goal_id);
