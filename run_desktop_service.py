"""Frozen sidecar entry: console subsystem preserves anonymous protocol pipes.

The desktop parent uses CREATE_NO_WINDOW, so normal users never see a console.
No application settings are imported before the parent installs the profile.
"""

import multiprocessing
import sys

from app.desktop.service import serve_from_parent_streams

if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(serve_from_parent_streams(sys.stdin, sys.stdout))
