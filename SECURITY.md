# Security Policy

## Supported versions

Security fixes are applied to `main` and, when practical, to the latest published release. GameArchiveManager is currently a release candidate; users should review the [known limitations](docs/SECURITY.md#已知限制) before processing untrusted archives.

## Reporting a vulnerability

Please do not disclose an unpatched vulnerability, exploit, private archive, password, log, or full local path in a public issue.

1. Open the repository **Security** tab and use **Report a vulnerability** when that option is available.
2. If private vulnerability reporting is unavailable, open a minimal issue asking the maintainer for a private contact channel. Do not include exploit details or personal data.
3. Include the affected version, operating system, archive format, impact, and minimal reproduction steps. Use a synthetic archive whenever possible.

The maintainer will acknowledge a complete report, assess its impact, prepare regression coverage, and coordinate disclosure after a fix is available. No response-time guarantee is currently offered by this volunteer-maintained project.

## Scope

Reports are especially useful for:

- archive path traversal or absolute-path extraction;
- symbolic-link, junction, or reparse-point escapes;
- extraction limits and decompression-denial-of-service cases;
- password exposure in logs, history, reports, or process arguments;
- unsafe external-tool discovery or invocation;
- unintended file deletion, overwrite, or access outside the selected task tree;
- unexpected network communication or privacy-sensitive data collection.

Third-party vulnerabilities in 7-Zip, WinRAR, LZ4, Python, or PyInstaller should also be reported to their upstream maintainers. Please report any unsafe integration behavior in this repository as well.

The implementation boundaries and remaining limitations are documented in [`docs/SECURITY.md`](docs/SECURITY.md). The latest source audit summary is [`docs/SECURITY_AUDIT_2026-08-24.md`](docs/SECURITY_AUDIT_2026-08-24.md).
