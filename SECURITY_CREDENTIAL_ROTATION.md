# AAWCL Banking: credential exposure response

This repository previously contained a database hostname, user, password and
JWT signing key directly in the public Python source. Do not continue using
these values in any accessible service.

## Owner actions required

1. **Rotate the Azure SQL or equivalent database password immediately**.
2. **Replace the JWT signing key**; invalidate existing tokens and sessions.
3. Check DB access logs, remove unnecessary permissions, and narrow the
   firewall/network allowlist. Review billing and connected services.
4. Check historical Git commits, forks, logs, caches and other exposed files.
5. Consider coordinated history cleanup only after rotating; old clones and
   cached commits may still contain the original credentials.

Removing literals from HEAD is necessary but **does not revoke them**.

## Running locally

The Python app now fails closed without these environment variables:
AAWCL_DB_SERVER, AAWCL_DB_NAME, AAWCL_DB_USER, AAWCL_DB_PASSWORD,
AAWCL_JWT_SECRET_KEY (at least 32 characters). Optionally configure
AAWCL_ALLOWED_ORIGINS for trusted browser origins; defaults to
http://localhost:4200.

On PowerShell use fresh values, for example:
`$env:AAWCL_DB_SERVER = "server.example"`
`$env:AAWCL_JWT_SECRET_KEY = "<generated strong random secret>"`

The backend still requires a suitable ODBC driver and an actual SQL schema.
Those services are not available in this CI check. CORS is **not**
authentication.

## Other security issues to address before demo/public hosting

The legacy API exposes user lookup/update/delete routes without adequate
authorization and performs account updates that need transaction isolation.
Do not deploy as a banking service or use actual customer/financial data.

This commit is credential containment, not a complete security assessment.
