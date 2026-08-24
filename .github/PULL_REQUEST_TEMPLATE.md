## Summary

Describe the problem and the focused change that solves it.

## Verification

- [ ] I ran `py -B -m unittest discover -s tests -p "test_*.py" -v`.
- [ ] I added or updated regression tests where behavior changed.
- [ ] I used only synthetic, redistributable fixtures.
- [ ] I updated relevant user, configuration, security, or release documentation.

## Safety review

- [ ] I considered archive path traversal, links/reparse points, limits, deletion, and overwrite behavior.
- [ ] I considered passwords, logs, local paths, network activity, and other privacy effects.
- [ ] I considered external-tool discovery, arguments, timeouts, and failure behavior.
- [ ] This change does not add secrets, private paths, real user archives, logs, or generated build output.

If an item does not apply, explain why below.

## Remaining limitations

List any unverified platform, skipped tool-dependent test, compatibility risk, or known limitation.
