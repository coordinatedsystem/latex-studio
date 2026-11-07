"""Single version source for server, installer and update checks."""
from pathlib import Path
import json
INFO=json.loads(Path(__file__).with_name('version.json').read_text('utf-8'))
VERSION=INFO['version']
BUILD=INFO['build']
REPOSITORY=INFO['repository']
