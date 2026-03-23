# Security Policy

## Reporting a Vulnerability

Please **do not** report security vulnerabilities through public GitHub issues.

Instead, use [GitHub's private vulnerability reporting](https://github.com/matthewdeanmartin/pathkeeper/security/advisories/new) to submit a report confidentially.

Include as much of the following as possible:

- Description of the vulnerability and its potential impact
- Steps to reproduce or a proof-of-concept
- Affected versions
- Any suggested fix, if you have one

You can expect an acknowledgement within a few days and a resolution or status update within 30 days.

## Scope

Pathkeeper manages the system `PATH` environment variable, which means vulnerabilities that could allow:

- Arbitrary code execution via PATH manipulation
- Privilege escalation through backup/restore operations
- Unsafe handling of shell config files (`.bashrc`, `.zshrc`, etc.)

are considered in scope and high priority.

## Supported Versions

Only the latest release receives security fixes.

| Version | Supported |
| ------- | --------- |
| latest  | Yes       |
| older   | No        |
