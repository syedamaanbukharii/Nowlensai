"""Test suite package.

Declaring ``tests`` as a package lets the test modules use absolute imports
such as ``from tests.conftest import EMBED_DIM`` regardless of how pytest is
launched. With this file present, pytest's default ("prepend") import mode adds
the repository root to ``sys.path`` and imports the shared ``conftest`` exactly
once under its canonical name ``tests.conftest`` -- so fixtures and the helpers
imported by name resolve to the same module object.
"""
