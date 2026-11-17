"""One process-wide lock for PDFium.

PDFium keeps global library state and is not thread-safe. Two documents loaded from
different threads at the same time can put the whole process into a permanent
"Data format error" state: after that every later load fails, including preview page
images, until the application is restarted. All PDFium use therefore goes through
this lock, covering the whole open -> render -> close sequence.
"""
import threading

LOCK = threading.RLock()
