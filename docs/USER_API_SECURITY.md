# User API access control

This change prevents anonymous disclosure and mutation of user account records.

- Bulk user listing returns 403, even when authenticated.
- A single user lookup requires a JWT and scopes results to the current token
  subject; it returns only explicit profile fields, not password hashes.
- Updating a user's profile requires the user's own JWT and an allowlisted set
  of fields. The duplicate insecure password-update route has been removed.
- User deletion is disabled until identity confirmation, ledger reconciliation
  and a database integration test are implemented.
- Card listings no longer return CVV values in API responses.

CI verifies source structure and required decorators **without** connecting
to the original database. This is not a production authorization pentest.

The legacy transfer code still performs multiple commits and needs atomic
transactions, validation, concurrent-balance tests and additional auditing.
Do not use real customer information or live balances.
