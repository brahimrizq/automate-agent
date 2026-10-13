#!/usr/bin/env python3
"""Container command interface. No installer or credential is ever logged."""
import sys

from agentwrap import main

if __name__ == "__main__":
    sys.exit(main())
