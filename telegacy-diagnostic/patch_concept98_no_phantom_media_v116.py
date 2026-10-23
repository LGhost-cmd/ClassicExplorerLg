#!/usr/bin/env python3
"""Concept98 v11.6: remove phantom U+FE0F after successful media OLE insert.
The v11.2 cache-first photo path accidentally appended an *extra* FE0F when
the JPEG was not yet cached, despite inserting a placeholder OLE. This caused
small square glyphs, stale Document offsets and footer text beside the image.
Keep an invisible fallback only when there is no bitmap to insert.
"""
from pathlib import Path
import sys
if len(sys.argv)!=2:raise SystemExit("Usage: patch_concept98_no_phantom_media_v116.py <src>")
p=Path(sys.argv[1]).resolve()/"src"/"message.cpp"
s=p.read_text(encoding="latin-1")
if "concept98_no_phantom_media_v116" in s:
    print("v11.6 already applied");raise SystemExit(0)
if "concept98_photo_bind_v111" not in s:raise SystemExit("requires photo identity v11.1")
old='''\t\t\tif (cached_card)
\t\t\t\tDeleteObject(cached_card);
\t\t\telse {
\t\t\t\twchar_t placeholder[] = {0xFE0F, 0};
\t\t\t\triched_write(chat, placeholder);
\t\t\t}

\t\t\tif (media_card)'''
new='''\t\t\tif (cached_card)
\t\t\t\tDeleteObject(cached_card);
\t\t\t// concept98_no_phantom_media_v116:
\t\t\t// insert_image above already inserted ONE OLE character.  Adding
\t\t\t// FE0F a second time created the tiny empty square after each photo
\t\t\t// and shifted all subsequent rich text positions by one.
\t\t\tif (!display_bitmap) {
\t\t\t\twchar_t fallback[] = {0xFE0F, 0};
\t\t\t\triched_write(chat, fallback);
\t\t\t}

\t\t\tif (media_card)'''
if s.count(old)!=1:raise SystemExit("Unexpected photo insert layout; abort")
s=s.replace(old,new,1)
p.write_text(s,encoding="latin-1",newline="\r\n")
print("v11.6: no double-character photo OLE/FE0F, footer positions remain in sync.")
