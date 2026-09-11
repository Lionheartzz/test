"""No server/CAD imports. PDF JavaScript is never enabled."""
import hashlib
import io
import json
import math
from pathlib import Path
import sys
from PIL import Image


def main():
    source, target, media, side, limit = sys.argv[1:]
    target = Path(target)
    side, limit = int(side), int(limit)
    pages = []

    def save(image, number):
        image = image.convert('RGB')
        image.thumbnail((side, side), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        image.save(output, format='PNG')
        data = output.getvalue()
        name = f'page-{number:03}.png'
        (target / name).write_bytes(data)
        pages.append(dict(page=number, file=name, width=image.width, height=image.height,
                          sha256=hashlib.sha256(data).hexdigest()))

    if media == 'application/pdf':
        import pypdfium2 as pdfium
        with pdfium.PdfDocument(source) as pdf:
            if not 1 <= len(pdf) <= limit:
                raise ValueError('Page limit exceeded')
            for index in range(len(pdf)):
                page = pdf[index]
                try:
                    width, height = page.get_size()
                    if not all(math.isfinite(v) and v > 0 for v in (width, height)):
                        raise ValueError('Invalid page size')
                    bitmap = page.render(scale=min(3, side / max(width, height)))
                    try:
                        save(bitmap.to_pil(), index + 1)
                    finally:
                        bitmap.close()
                finally:
                    page.close()
    else:
        with Image.open(source) as image:
            if image.width * image.height > 40_000_000:
                raise ValueError('Image too large')
            # Preserve raw image orientation, matching the original evidence viewer.
            save(image, 1)
    (target / 'pages.json').write_text(json.dumps(dict(page_count=len(pages), pages=pages)), encoding='utf-8')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # No document content, raw parser diagnostics or local paths on stderr.
        sys.exit(2)
