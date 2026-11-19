"""Isolated PDF text worker. Only private local paths supplied by the parent."""
import json
import logging
import os
import resource
import sys
import warnings


def main():
    resource.setrlimit(resource.RLIMIT_CPU, (12, 12))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    if sys.platform.startswith('linux'):
        resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024, 768 * 1024 * 1024))
    logging.disable(logging.CRITICAL)
    warnings.simplefilter('ignore')
    try:
        import pypdf
        if pypdf.__version__ != '7.1.1':
            raise ValueError('version')
        reader = pypdf.PdfReader(sys.argv[1], strict=True)
        if reader.is_encrypted or not 1 <= len(reader.pages) <= 80:
            raise ValueError('encrypted or page limit')
        chunks, size = [], 0
        for page in reader.pages:
            text = page.extract_text(extraction_mode='plain') or ''
            text = ''.join(c for c in text if c.isprintable() or c in '\n\t')
            size += len(text.encode('utf-8')) + (1 if chunks else 0)
            if size > 65536:
                raise ValueError('text limit')
            chunks.append(text)
        text = '\n'.join(chunks).strip()
        if not text:
            raise ValueError('no text')
        title = str((reader.metadata or {}).get('/Title') or '')
        title = ' '.join(title.split())[:500]
        title = ''.join(c for c in title if c.isprintable())
        result = {'text': text, 'title': title, 'page_count': len(reader.pages)}
        with os.fdopen(os.open(sys.argv[2], os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w', encoding='utf-8') as stream:
            json.dump(result, stream, ensure_ascii=True)
    except Exception:
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
