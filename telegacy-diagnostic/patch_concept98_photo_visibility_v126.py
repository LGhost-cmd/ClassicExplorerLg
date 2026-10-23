#!/usr/bin/env python3
"""Concept98 v12.6: fix uninitialised photo visibility and media bookkeeping."""
from pathlib import Path
import sys
if len(sys.argv)!=2: raise SystemExit("Usage: patch_concept98_photo_visibility_v126.py <src>")
p=Path(sys.argv[1]).resolve()/"src"/"message.cpp"
s=p.read_text(encoding="latin-1")
if "concept98_photo_visibility_v126" in s:
    print("Concept98 v12.6 already applied.")
    raise SystemExit(0)
# The upstream Document POD has no default initialisers. The photo branch
# never writes visible at all, so it inherits an arbitrary stack byte.
# Nearly all downstream code (auto-pump, completion target, click handlers,
# staging) requires document.visible == true.
a="\tDocument document;\n\tdocument.photo_msg_id[0] = 1;"
b="\tDocument document = {}; // concept98_photo_visibility_v126: fully initialise POD\n\tdocument.photo_msg_id[0] = 1;"
if s.count(a)!=1:raise SystemExit("v12.6: Document POD initializer not found exactly once")
s=s.replace(a,b,1)
photo_start="} else if (doc != NULL && read_le(doc, 4) == 0x695150d7 && (read_le(doc + 4, 4) & (1 << 0))) {"
if s.count(photo_start)!=1:raise SystemExit("v12.6: photo branch missing")
i=s.index(photo_start)
tail=s[i:]
a="\t\tif (!same_photo) {\n\t\t\tint flags = read_le(doc + 12, 4);"
b="\t\tif (!same_photo) {\n\t\t\tdocument.visible = true; // concept98_photo_visibility_v126: full-image eligible\n\t\t\tint flags = read_le(doc + 12, 4);"
if tail.count(a)!=1:raise SystemExit("v12.6: photo branch field assignment unexpected")
tail=tail.replace(a,b,1)
s=s[:i]+tail
assert "document.visible = true; // concept98_photo_visibility_v126" in s
assert "Document document = {}; // concept98_photo_visibility_v126" in s
p.write_text(s,encoding="latin-1",newline="\r\n")
print("v12.6: initialised Document POD and made Telegram messageMediaPhoto entries visible to full-JPEG queue, exact OLE replacement, cache recovery and click handling.")
