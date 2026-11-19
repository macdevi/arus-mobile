# Arus Next: candidate under validation

Standalone source, saved directly in the development branch. No dependency on the old app/database.
Includes UI, domain, authenticated API, account CLI, salary worker, integration tests and CI.
Not declared production ready until CI, live FX, staging and rollback are verified.
Previous ZIP test counts do not certify this reconstructed source.

## Tests
From next/: pip install -r requirements.txt
Run python -m unittest discover -s tests -v. Missing Flask fails; tests are not silently skipped.
GitHub Actions also builds Docker and runs a Chromium mobile smoke flow.
Browser test is CI-only: it creates an explicitly named disposable arus-next-ci container account.
Do not run browser_smoke.py against a production container.
Network FX parsing is mocked in unit tests. Live provider connectivity still requires verification.

## Staging boundary
Use only compose.staging.yaml from this directory, project arus-next-staging, separate next_data volume.
Only 127.0.0.1:18081 is published. No public 80/443/8443/18080, no Caddy, no Nginx edits.
COOKIE_SECURE=false is for loopback staging via SSH tunnel only, not public use.
Before starting, check listener availability and RAM. The existing VPS has about 1 GiB RAM.
Separate projects still share host CPU/RAM/Docker; no zero-impact guarantee.
Do not restart Docker globally or touch PHP-FPM/billing workers.

## Account and storage
Set SECRET_KEY to a permanent random value of at least 48 characters. Never commit .env.
Use ARUS_NEXT_DB separate from old data. No automatic migration from old Arus.
Account creation: python server.py init-admin (interactive, 14-256 character password).
No default password. Entrypoint: gunicorn 'server:create_app()'.
Worker: python server.py worker, checks every 300 seconds; gaji waits when no usable historical FX exists.
CLI backup: python server.py backup NEW_DESTINATION. Backup contains credentials/data.
JSON export excludes password hashes but is not an account backup.

## Known limitations
Transaction correction uses cancellation/re-entry. No edit/archive form for existing goals/loans yet.
No partial installment payments, early settlement calculation, bank integration, multiuser, or external notifications.
Outstanding scheduled payments are not equivalent to outstanding principal.
Automatic FX refresh can replace a manual rate on the same date; transaction snapshots remain unchanged.
Date/source of cached FX must be checked; it may be older than the transaction date.

## Cutover
Not authorized by committing these files. Requires backup, successful tests, staging review,
HTTPS with COOKIE_SECURE=true, Nginx baseline validation and an explicit cutover approval.
No deletion of old Arus, volumes, certificates or billing files is included.
