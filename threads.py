#!/usr/bin/env python3
"""Thin CLI shim so `python threads.py` runs the ThreadServe server.

All real implementation lives in the threadserve package.
"""

from threadserve.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
