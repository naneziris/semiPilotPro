"""Lets `python -m semipilot` work, same as the `semipilot` command."""
import sys

from .cli import main

sys.exit(main())
