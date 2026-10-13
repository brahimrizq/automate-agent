#!/usr/bin/env python3
import json
import sys

from agentwrap import health

if __name__ == "__main__":
    result = health()
    print(json.dumps(result, sort_keys=True))
    sys.exit(0 if result["process"] == "healthy" else 1)
