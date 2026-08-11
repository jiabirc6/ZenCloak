from zencloak.core.extensions import build_newtab_extension


def test_newtab_html_uses_external_redirect_script(tmp_path):
    profile = {"id": "aaaaaaaaaaaa", "start_url": "https://example.com/path?q=1"}
    ext_dir = build_newtab_extension(profile, tmp_path)
    html = (ext_dir / "newtab.html").read_text(encoding="utf-8")
    js = (ext_dir / "newtab.js").read_text(encoding="utf-8")
    assert 'src="newtab.js"' in html
    assert "https://example.com/path?q=1" in html
    assert "location.replace" in js


def test_newtab_html_escapes_url_in_attribute(tmp_path):
    profile = {"id": "bbbbbbbbbbbb", "start_url": "https://example.com/?a=1&b=2"}
    ext_dir = build_newtab_extension(profile, tmp_path)
    html = (ext_dir / "newtab.html").read_text(encoding="utf-8")
    assert "&amp;" in html
