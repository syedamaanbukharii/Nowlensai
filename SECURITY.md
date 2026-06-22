# Security Policy

## Reporting a vulnerability

Please **do not** open a public issue for security vulnerabilities.

Instead, report them privately to the maintainers (e.g. via the repository's security advisory feature or the contact listed in the project metadata). Include:

- A description of the issue and its impact.
- Steps to reproduce (a minimal proof of concept if possible).
- Affected version/commit and environment details.

We aim to acknowledge reports promptly, keep you informed of progress, and credit reporters who wish to be credited once a fix is released.

## Scope

This policy covers the NowLens application code in this repository. Vulnerabilities in third-party dependencies should be reported upstream; if a dependency issue affects NowLens, let us know so we can pin or patch.

## Supported versions

NowLens is pre-1.0; security fixes are applied to the latest `main`. Pin to a released tag for stability and watch the [CHANGELOG](CHANGELOG.md) for security-relevant updates.

## Hardening

See [docs/SECURITY.md](docs/SECURITY.md) for the security model and a production hardening checklist (JWT secret management, TLS, CORS, metrics exposure, rate-limit sharing, least-privilege DB roles).
