"""Import PyYAML, falling back to the bundled copy when it is not installed.

Every module in semipilot does `from ._yaml import yaml` instead of `import yaml`, so the tool
works from a plain download of this folder on a machine with no pip and no pyyaml.
"""
try:
    import yaml  # the installed package (pipx / pip installs bring it in as a dependency)
except ImportError:  # no pip on this machine — use the pure-Python copy in _vendor/
    from ._vendor import yaml  # type: ignore[no-redef]

__all__ = ["yaml"]
