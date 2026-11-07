"""One compiler environment shared by projects and package verification."""
import os
from pathlib import Path
from xml.sax.saxutils import escape


def engine_environment(runtime, data, cache=None):
    runtime, data = Path(runtime), Path(data)
    data.mkdir(parents=True, exist_ok=True)
    cache = Path(cache) if cache is not None else runtime/'cache'
    cache.mkdir(parents=True, exist_ok=True)
    font_cache = cache.parent/'fonts' if cache.name=='tectonic' else cache/'fonts'
    font_cache.mkdir(parents=True, exist_ok=True)
    font_dir = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'Fonts'
    config = data / 'fonts.conf'
    config.write_text('<?xml version="1.0"?><fontconfig><dir>' + escape(font_dir.as_posix()) +
                      '</dir><cachedir>' + escape(font_cache.as_posix()) + '</cachedir></fontconfig>', encoding='utf-8')
    env = os.environ.copy()
    env['TECTONIC_CACHE_DIR'] = str(cache)
    env['FONTCONFIG_FILE'] = str(config)
    temporary=cache.parent/'tmp' if cache.name=='tectonic' else cache/'tmp'
    temporary.mkdir(parents=True,exist_ok=True)
    env.update(TEMP=str(temporary),TMP=str(temporary))
    return env
