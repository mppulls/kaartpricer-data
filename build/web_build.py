#!/usr/bin/env python3
"""Bouwt de losse app (Cloudflare Pages) uit de Claude versie van de app.

  python3 build/web_build.py UIT_MAP DATA_MAP

UIT_MAP krijgt: public/ (de pagina's, kaartdata en prijzen) en functions/ (het serverdeel).
DATA_MAP bevat catalog.json en prices.json van build/app_data.py, en eventueel seed.json.
"""
import os, re, shutil, sys

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out, data = sys.argv[1], sys.argv[2]
pub = os.path.join(out, "public")
shutil.rmtree(out, ignore_errors=True)
shutil.copytree(os.path.join(root, "web", "public"), pub)
shutil.copytree(os.path.join(root, "web", "functions"), os.path.join(out, "functions"))
for f in ("catalog.json", "prices.json", "seed.json"):
    if os.path.exists(os.path.join(data, f)):
        shutil.copy(os.path.join(data, f), pub)

src = open(os.path.join(root, "app", "index.html"), encoding="utf-8").read()
head_bits = []
for pat in (r"<title>.*?</title>\s*", r'<meta name="claude:[^>]*>\s*', r'<link rel="preconnect"[^>]*>\s*', r'<link rel="stylesheet"[^>]*>\s*'):
    for m in re.findall(pat, src, flags=re.S):
        head_bits.append(m.strip()); src = src.replace(m, "", 1)
html = f"""<!doctype html>
<html lang="nl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover">
<meta name="theme-color" content="#11141b">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Kaartscan">
<link rel="manifest" href="/manifest.webmanifest">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
{chr(10).join(head_bits)}
<style>:root{{color-scheme:light;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}}body{{margin:0;font:14px/1.4 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}}img{{max-width:100%}}[hidden]{{display:none!important}}</style>
<script src="/kp-shim.js"></script>
</head>
<body>
{src.strip()}
<script>if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {{}});</script>
</body>
</html>
"""
open(os.path.join(pub, "index.html"), "w", encoding="utf-8").write(html)
print("klaar:", out, sorted(os.listdir(pub)))
