#!/usr/bin/env python3
"""Concept98 v11.8: make long, media-heavy conversations calmer to read.
Muting saturated author blue/red is a paint-only change: do not disturb spans,
RichEdit OLE, message positions, chat media cache or text reconstruction.
Maintain original Win98 bevels and system theme color for chrome.
"""
from pathlib import Path
import sys
if len(sys.argv)!=2:raise SystemExit("Usage: patch_concept98_typography_v118.py <src>")
root=Path(sys.argv[1]).resolve()
m=root/"src"/"message.cpp"
s=m.read_text(encoding="latin-1")
if "concept98_no_phantom_media_v116" not in s:raise SystemExit("requires v11.6")
old="cf.crTextColor = RGB(message.outgoing ? 255 : 0, 0, message.outgoing ? 0 : 255);"
new="""// concept98_typography_v118: readable but recognizably Win98 authors.
        cf.crTextColor = message.outgoing ? RGB(160,49,47) : RGB(30,64,131);"""
if s.count(old)!=1:raise SystemExit("sender coloring changed")
s=s.replace(old,new,1)
old="cf.crTextColor = RGB(messages[0].outgoing ? 255 : 0, 0, messages[0].outgoing ? 0 : 255);"
new="cf.crTextColor = messages[0].outgoing ? RGB(160,49,47) : RGB(30,64,131);"
if s.count(old)!=1:raise SystemExit("grouped sender coloring changed")
s=s.replace(old,new,1)
m.write_text(s,encoding="latin-1",newline="\r\n")
print("v11.8: toned-down author colors, no change to layout spans or media.")
