"""Stub. Upstream cyaml.py binds the libyaml C extension; the bundled copy is pure Python only,
so this raises ImportError and yaml/__init__.py takes its pure-Python path."""
raise ImportError("bundled PyYAML has no libyaml bindings")
