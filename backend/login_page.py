"""The page the browser shows after the Spotify login (answer of the callback server).

One self-contained HTML document (no external files), in the colours of the app.
"""
from html import escape

from .config import APP_NAME, T, current_language

# Same window-with-arrow icon as img/app-icon.svg.
_LOGO = ('<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M0 26.016q0 2.496 1.76 4.224t4.256 1.76h4.992'
         'l-2.496-4h-2.496q-0.832 0-1.44-0.576t-0.576-1.408v-14.016h24v14.016q0 0.832-0.576 1.408t-1.408 0.576h-2.528'
         'l-2.496 4h5.024q2.464 0 4.224-1.76t1.76-4.224v-20q0-2.496-1.76-4.256t-4.224-1.76h-20q-2.496 0-4.256 1.76'
         't-1.76 4.256v20zM4 10.016v-4q0-0.832 0.576-1.408t1.44-0.608h20q0.8 0 1.408 0.608t0.576 1.408v4h-24zM6.016 8'
         'h1.984v-1.984h-1.984v1.984zM10.016 24l5.984 8 6.016-8h-4v-8h-4v8h-4zM10.016 8h1.984v-1.984h-1.984v1.984z'
         'M14.016 8h12v-1.984h-12v1.984z"/></svg>')
_CHECK = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>'
_CROSS = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/></svg>'

_PAGE = """<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{app}</title>
<style>
:root {{ color-scheme: dark; --tone: {tone}; --tone-dim: {tone_dim}; }}
* {{ box-sizing: border-box; }}
body {{
  margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center;
  background: radial-gradient(ellipse at 50% 0%, #161b22 0%, #0d1117 65%);
  color: #e6edf3; font-family: "Segoe UI", system-ui, sans-serif;
}}
.card {{
  width: min(440px, calc(100% - 32px)); padding: 36px 32px 30px; text-align: center;
  background: #161b22; border: 1px solid #30363d; border-radius: 16px;
  box-shadow: 0 24px 64px rgba(0, 0, 0, 0.5);
}}
.brand {{
  display: inline-flex; align-items: center; gap: 10px; margin-bottom: 30px;
  color: #8b949e; font-size: 14px; font-weight: 600; letter-spacing: 0.2px;
}}
.brand svg {{ width: 22px; height: 22px; fill: #8b949e; }}
.badge {{
  width: 76px; height: 76px; margin: 0 auto 22px; display: flex; align-items: center; justify-content: center;
  border-radius: 50%; background: var(--tone-dim); box-shadow: 0 0 0 8px rgba(255, 255, 255, 0.02);
}}
.badge svg {{ width: 38px; height: 38px; fill: none; stroke: var(--tone); stroke-width: 2.6; stroke-linecap: round; stroke-linejoin: round; }}
.badge path {{ stroke-dasharray: 32; stroke-dashoffset: 32; animation: draw 0.5s 0.15s ease-out forwards; }}
@keyframes draw {{ to {{ stroke-dashoffset: 0; }} }}
h1 {{ margin: 0 0 10px; font-size: 24px; font-weight: 700; }}
p {{ margin: 0; color: #8b949e; font-size: 14.5px; line-height: 1.55; }}
</style>
</head>
<body>
<main class="card">
  <div class="brand">{logo}<span>{app}</span></div>
  <div class="badge">{icon}</div>
  <h1>{title}</h1>
  <p>{text}</p>
</main>
</body>
</html>
"""


def render_login_page(ok: bool) -> str:
    """The page for a finished login (`ok`) or a login Spotify did not grant."""
    return _PAGE.format(
        lang=escape(current_language()),
        app=escape(APP_NAME),
        logo=_LOGO,
        icon=_CHECK if ok else _CROSS,
        tone="#1db954" if ok else "#f85149",
        tone_dim="rgba(29, 185, 84, 0.14)" if ok else "rgba(248, 81, 73, 0.14)",
        title=escape(T("rec_login_done_title" if ok else "rec_login_failed_title")),
        text=escape(T("rec_login_done" if ok else "rec_login_failed")),
    )
