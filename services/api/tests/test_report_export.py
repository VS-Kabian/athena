from athena.report.export import to_markdown_bytes, to_pdf_bytes

def test_markdown_bytes():
    b = to_markdown_bytes("# Hello\n\nWorld")
    assert b.startswith(b"# Hello")

def test_pdf_bytes_are_pdf():
    b = to_pdf_bytes("# Hello\n\nWorld")
    assert b[:4] == b"%PDF"
