import struct
import sys

if sys.version_info[:2] != (3, 12):
    raise SystemExit("Python 3.12 required; detected " + sys.version)
if struct.calcsize("P") != 8:
    raise SystemExit("64-bit Python required")

import tkinter
import venv
import ensurepip

print(sys.executable)
