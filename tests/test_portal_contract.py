"""Portal UI contract regression tests.

Guards the failure modes that previously produced blank/stuck portal pages:
  1) JS syntax errors -> script never executes, #app stays empty
  2) render root (#app) mismatch between HTML and JS selector
  3) api() must surface HTTP 401 so stale tokens force re-login (invalid_token bug)
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

PORTALS = Path(__file__).resolve().parents[1] / "portals"
PORTAL_NAMES = ("admin", "merchant", "investigator")


def _node_check(file: Path) -> None:
    if shutil.which("node") is None:
        pytest.skip("node binary not available")
    res = subprocess.run(["node", "--check", str(file)], capture_output=True, text=True)
    assert res.returncode == 0, f"node --check FAILED for {file}:\n{res.stderr}"


def test_portal_html_has_app_root_before_script():
    for p in PORTAL_NAMES:
        html = (PORTALS / p / "index.html").read_text(encoding="utf-8")
        assert 'id="app"' in html, f'{p}/index.html: missing <div id="app">'
        assert "app.js" in html, f"{p}/index.html: missing app.js <script>"
        assert html.find('id="app"') < html.find("app.js"), (
            f"{p}/index.html: <script> must come after the #app div"
        )


def test_portal_app_js_syntax_is_valid():
    for p in PORTAL_NAMES:
        _node_check(PORTALS / p / "app.js")


def test_portal_bootstrap_queries_app_at_top_level():
    for p in PORTAL_NAMES:
        lines = (PORTALS / p / "app.js").read_text(encoding="utf-8").splitlines()
        query_idx = [i for i, l in enumerate(lines) if '"#app"' in l]
        bootstrap = [i for i, l in enumerate(lines) if l.strip() == "render();"]
        assert query_idx, f"{p}: JS never queries #app"
        assert bootstrap, f"{p}: no top-level render() bootstrap call"
        assert query_idx[0] < bootstrap[-1], f"{p}: #app queried after bootstrap render()"


def test_portal_api_handles_http_401():
    """Every portal api()/apiRoot() must detect r.status === 401 and clear the
    session so a stale token (invalid_token) can never strand the user on an
    empty dashboard."""
    for p in PORTAL_NAMES:
        js = (PORTALS / p / "app.js").read_text(encoding="utf-8")
        assert re.search(r"r\.status === 401", js), (
            f"{p}: api() does not branch on HTTP 401 — stale tokens will show "
            f"'invalid_token' forever instead of forcing re-login"
        )
        guard_zone = js[js.find("r.status === 401") : js.find("r.status === 401") + 400]
        assert "localStorage.removeItem" in guard_zone, f"{p}: 401 branch must clear stored token(s)"
