#!/usr/bin/env python3
"""Zet een export van de Claude app database (ArtifactData met out_dir) om naar web/seed.json voor de losse app.

  python3 build/export_seed.py EXPORT_MAP web/seed.json

In de losse app: menu, "Lijsten uit Claude importeren".
"""
import json, os, sys
root, out = sys.argv[1], sys.argv[2]
docs = []
for d, _, files in os.walk(root):
    for f in files:
        if f.endswith(".json"):
            rel = os.path.relpath(os.path.join(d, f), root)[:-5].replace(os.sep, "/")
            docs.append({"path": rel, "data": json.load(open(os.path.join(d, f), encoding="utf-8"))})
docs.sort(key=lambda x: x["path"].count("/"))          # eerst lijsten, dan scans en inkopen
json.dump({"docs": docs}, open(out, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print(len(docs), "documenten naar", out)
