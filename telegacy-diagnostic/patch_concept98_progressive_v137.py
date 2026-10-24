#!/usr/bin/env python3
"""Concept98 v13.7: render chat immediately while photo previews load
independently; no 12-second full-screen history veil. Treat only verified
original PhotoSize as downloadable original (a cached 800px preview is not it).
Do not touch OLE positions or GIF/WebM playback."""
from pathlib import Path
import sys
if len(sys.argv)!=2:raise SystemExit("Usage: patch_concept98_progressive_v137.py <src>")
p=Path(sys.argv[1]).resolve()/"src"/"telegacy.cpp"
s=p.read_text(encoding="latin-1")
if "concept98_progressive_v137" in s:raise SystemExit(0)
if "concept98_reply_chain_v136" not in s:raise SystemExit("v13.6 required")
def one(a,b,label):
 global s
 n=s.count(a)
 if n!=1:raise SystemExit("v13.7 "+label+" matches="+str(n))
 s=s.replace(a,b,1)
one("void concept98_page_stage_v124(int newly_added_docs){",
"""void concept98_page_stage_v124(int newly_added_docs){
    // concept98_progressive_v137: never mask already rendered chat text
    // while Telegram downloads photos one-by-one in the background.
    concept98_page_unveil_v124("progressive text-first");
    return;""",
"remove history veil")
one("""    if(save_and_open){
        std::vector<BYTE> local;
        if(concept98_full_photo_load_v101(document,&local)){""",
"""    if(save_and_open &&
       !(document->concept98_original_photo_size_v135 &&
         document->photo_size != document->concept98_original_photo_size_v135)){
        std::vector<BYTE> local;
        if(concept98_full_photo_load_v101(document,&local)){""",
"do not open reduced PhotoSize as original")
p.write_text(s,encoding="latin-1",newline="\r\n")
print("v13.7: chat text visible immediately; photo loads progressive; original preserved.")
