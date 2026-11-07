"""Use Mozilla's official compatibility build, retaining the viewer and licenses."""
import hashlib
import io
import json
from pathlib import Path
import urllib.request
import zipfile

root = Path(__file__).resolve().parent / 'vendor'
version = json.loads((root / 'versions.json').read_text(encoding='utf-8'))
tag = version['pdfjs']
url = f'https://github.com/mozilla/pdf.js/releases/download/{tag}/pdfjs-{tag.lstrip("v")}-legacy-dist.zip'
request = urllib.request.Request(url, headers={'User-Agent': 'Local-LaTeX-Studio/1.1'})
print('Downloading the official PDF.js compatibility build...', flush=True)
with urllib.request.urlopen(request, timeout=120) as response:
    archive_bytes = response.read()
archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
for entry in archive.infolist():
    if entry.is_dir() or entry.filename.endswith(('.pdf', '.map')):
        continue
    target = root / 'pdfjs' / entry.filename
    if not target.resolve().is_relative_to((root / 'pdfjs').resolve()):
        raise ValueError('Unsafe archive entry')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(archive.read(entry))
viewer = root / 'pdfjs' / 'web' / 'viewer.html'
markup = viewer.read_text(encoding='utf-8')
markup = markup.replace('<script src="../build/pdf.mjs" type="module"></script>', '<script src="/viewer-bridge.js"></script>\n<script src="../build/pdf.mjs" type="module"></script>')
viewer.write_text(markup, encoding='utf-8')
version.update(pdfjs_build='legacy', pdfjs_archive=url, pdfjs_archive_sha256=hashlib.sha256(archive_bytes).hexdigest())
(root / 'versions.json').write_text(json.dumps(version, indent=2), encoding='utf-8')
print('PDF.js compatibility build installed.', flush=True)
