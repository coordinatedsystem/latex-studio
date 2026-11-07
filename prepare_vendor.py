"""Fetch pinned open-source browser components; run only during setup."""
import io
import json
import tarfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENDOR = ROOT / 'vendor'


def get(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'Local-LaTeX-Studio/1.0'})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def main():
    VENDOR.mkdir(exist_ok=True)
    npm = json.loads(get('https://registry.npmjs.org/monaco-editor/latest'))
    print('Monaco:', npm['version'], flush=True)
    archive = tarfile.open(fileobj=io.BytesIO(get(npm['dist']['tarball'])), mode='r:gz')
    for item in archive.getmembers():
        name = item.name
        if not item.isfile() or not (name.startswith('package/min/vs/') or name == 'package/LICENSE'):
            continue
        relative = name.removeprefix('package/')
        dest = VENDOR / 'monaco' / relative
        if not dest.resolve().is_relative_to(VENDOR.resolve()):
            raise ValueError('Unsafe archive entry')
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(archive.extractfile(item).read())
    release = json.loads(get('https://api.github.com/repos/mozilla/pdf.js/releases/latest'))
    asset = next(a for a in release['assets'] if a['name'].endswith('-legacy-dist.zip'))
    print('PDF.js:', release['tag_name'], asset['name'], flush=True)
    archive = zipfile.ZipFile(io.BytesIO(get(asset['browser_download_url'])))
    for item in archive.infolist():
        if item.is_dir() or item.filename.endswith('.pdf'):
            continue
        dest = VENDOR / 'pdfjs' / item.filename
        if not dest.resolve().is_relative_to(VENDOR.resolve()):
            raise ValueError('Unsafe archive entry')
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(archive.read(item))
    viewer = VENDOR / 'pdfjs' / 'web' / 'viewer.html'
    markup = viewer.read_text(encoding='utf-8')
    markup = markup.replace('<script src="../build/pdf.mjs" type="module"></script>', '<script src="/viewer-bridge.js"></script>\n<script src="../build/pdf.mjs" type="module"></script>')
    viewer.write_text(markup, encoding='utf-8')
    (VENDOR / 'versions.json').write_text(json.dumps({
        'monaco': npm['version'], 'monaco_source': 'https://github.com/microsoft/monaco-editor',
        'pdfjs': release['tag_name'], 'pdfjs_source': 'https://github.com/mozilla/pdf.js', 'pdfjs_build': 'legacy',
    }, indent=2), encoding='utf-8')
    print('Browser components ready.', flush=True)


if __name__ == '__main__':
    main()
