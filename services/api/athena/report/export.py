import io
import logging
from markdown_it import MarkdownIt
from xhtml2pdf import pisa

_log = logging.getLogger(__name__)
_md = MarkdownIt()
_CSS = "body{font-family:Helvetica,Arial,sans-serif;max-width:760px;margin:40px auto;line-height:1.6;color:#111}"

def to_markdown_bytes(markdown: str) -> bytes:
    return markdown.encode("utf-8")

def to_pdf_bytes(markdown: str) -> bytes:
    html = f"<html><head><meta charset='utf-8'><style>{_CSS}</style></head><body>{_md.render(markdown)}</body></html>"
    buf = io.BytesIO()
    # Capture the render status: on error xhtml2pdf leaves partial/empty bytes in `buf`. Surfacing
    # that as an exception keeps the route from returning a corrupt 200 PDF (F-003).
    status = pisa.CreatePDF(src=html, dest=buf, encoding="utf-8")
    if status.err:
        _log.error("PDF render failed: %s error(s) from xhtml2pdf", status.err)
        raise RuntimeError(f"PDF render failed ({status.err} error(s))")
    return buf.getvalue()
