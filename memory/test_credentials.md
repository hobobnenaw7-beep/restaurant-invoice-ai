# Test Credentials (Test-Only — DO NOT USE IN PRODUCTION)

These are **dummy credentials** for the local dev container and the
automated testing agent. They are intentionally low-entropy, used only
against the local sandbox database, and MUST be rotated / regenerated
for any real deployment.

## Application Login

All passwords below are the same test-safe string: `testpassword` for
the demo account, `testpass123` for the rest. They exist only so the
testing agent can reproduce user flows without real authentication.

| Email | Role | Permissions | Scope |
|---|---|---|---|
| demo@test.com | manager | all | all |
| accountant@test.com | accountant | 17 perms | all |
| cashier@test.com | cashier | 9 perms | own |
| staff@test.com | staff | 4 perms | own |
| nodash@test.com | cashier | no view_dashboard, sales-only | own |

Use the value `testpassword` for `demo@test.com` and `testpass123`
for all others.

## Test Samples (Invoice Extraction)

- Sysco: `uploads/bfcdcae9-f8d4-4eac-af43-e4e0bfe2b7d5.jpg`
- PFG: `uploads/receipt_20b24d09-5761-4c09-aca6-6925cb235a55.png`
- US Foods (clean): `uploads/usfoods_clean_test_invoice.png`

## Production

No production credentials live in this repository. Real secrets are
provided via the platform's `.env` files (ignored in `.gitignore`)
and should never be committed.
