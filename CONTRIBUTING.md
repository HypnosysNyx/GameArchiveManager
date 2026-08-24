# Contributing to GameArchiveManager

Thank you for helping improve GameArchiveManager. The project handles untrusted archives and local user files, so correctness, privacy, and conservative filesystem behavior take priority over convenience.

## Before opening an issue

- Search existing issues and the [known issues](docs/KNOWN_ISSUES.md).
- Do not upload copyrighted game packages, private archives, passwords, raw logs, or screenshots containing full local paths.
- Reproduce problems with a minimal synthetic archive whenever possible.
- Report security vulnerabilities through the process in [`SECURITY.md`](SECURITY.md), not in a public issue.

## Development setup

Requirements:

- Windows 10 or 11
- Python 3.10 or newer; Python 3.12 is used for release builds
- 64-bit 7-Zip for ZIP, RAR, and 7Z integration tests
- optional official LZ4 CLI for LZ4 end-to-end tests

The runtime has no third-party Python dependency. Build dependencies are separate:

```powershell
py -m pip install -r requirements-build.txt
```

Run the application from source:

```powershell
py main.py
```

Run the complete automated test suite:

```powershell
py -B -m unittest discover -s tests -p "test_*.py" -v
```

Tool-dependent tests may skip when the corresponding trusted CLI is unavailable. New behavior should still have deterministic unit coverage that does not require private or copyrighted fixtures.

## Pull requests

Keep each pull request focused and explain:

- the problem and intended behavior;
- privacy, security, filesystem, password, or external-process impact;
- tests added or updated;
- documentation or compatibility changes;
- any known limitation that remains.

Before submitting:

1. Run the full test suite.
2. Avoid `shell=True`, command-string construction, unbounded recursion, implicit deletion, overwrite-by-default behavior, and archive-member paths that escape the task output.
3. Preserve the rule that source archives are not modified or deleted.
4. Keep secrets, passwords, usernames, private paths, real user archives, logs, build output, and local configuration out of commits.
5. Update security or user documentation when behavior changes.

Maintainers may request a smaller change, additional regression tests, or a synthetic fixture before merging.

## Commit and documentation style

- Use a short imperative commit subject.
- Prefer small, reviewable commits.
- Keep public behavior and limitations accurate in both code and documentation.
- Do not claim a test, platform, format, or security property that was not verified.

By contributing, you agree that your contribution is licensed under the repository's [MIT License](LICENSE).
