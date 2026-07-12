# WP6 golden fixtures

`repos/` contains static source-only repositories. `manifests/` is the semantic oracle outside each indexed root. G08 is generated in temporary directories by `tests/support/wp6_golden.py`; it is not committed.

The fixture digests deliberately hash raw bytes and normalized repository-relative paths. Update a manifest intentionally whenever fixture content changes.
