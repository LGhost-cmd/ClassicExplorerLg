#!/usr/bin/env python3
"""v11.2: Concept98 full-photo queue takes precedence over legacy tiny previews.
Stop sending unused thumbnail RPC requests for ordinary chat photos, but keep
video thumbnail/sticker and non-Concept98 behaviour untouched.
"""
from pathlib import Path
import sys,re
if len(sys.argv)!=2:raise SystemExit("Usage: patch_concept98_skip_hidden_thumbs_v112.py <src>")
root=Path(sys.argv[1]).resolve()
m=root/"src"/"message.cpp"
r=root/"src"/"response.cpp"
p=root/"src"/"telegacy.cpp"
s=m.read_text(encoding="latin-1")
t=r.read_text(encoding="latin-1")
u=p.read_text(encoding="latin-1")
if "concept98_skip_hidden_thumbs_v112" in s:
    print("v11.2 already applied");raise SystemExit(0)
if "concept98_photo_ole_identity_v111" not in u:
    raise SystemExit("v11.1 photo identity binding prerequisite missing")
origin='if (!to_front && IMAGELOADPOLICY != 0) get_photo(NULL, &document, &dcInfoMain); // chat_media_autoload_v65'
replace='if (!to_front && IMAGELOADPOLICY != 0 && !concept98_enabled) get_photo(NULL, &document, &dcInfoMain); // concept98_skip_hidden_thumbs_v112'
if s.count(origin)!=1: raise SystemExit("Expected exactly one normal-photo eager thumbnail gate")
s=s.replace(origin,replace,1)
extern='extern bool concept98_photo_bind_v111(const BYTE*,const BYTE*,int);'
if s.count(extern)!=1:raise SystemExit("Missing v11.1 cross-TU declaration")
s=s.replace(extern,extern+'\nextern bool concept98_enabled;',1)
if 'extern bool concept98_enabled;' not in t:
    header='#include <telegacy.h>'
    if t.count(header)!=1:raise SystemExit("Missing response source include")
    t=t.replace(header,header+'\nextern bool concept98_enabled; // concept98_skip_hidden_thumbs_v112',1)
# In all three history/search paths, skip *only* normal photo thumbnails.
# v11.1 full-photo pump processes all loaded photo docs from the same page.
pat=re.compile(r'(?m)^(?P<indent>[\t ]*)get_photo\(\s*NULL,\s*&documents\[i\],\s*(?P<dc>&dcInfoMain|dcInfo)\s*\);')
def fix(mt):
    prefix=mt.group("indent")
    args=mt.group("dc")
    return (prefix+'if (concept98_enabled && documents[i].photo_size!=3 &&\n'
            +prefix+'    documents[i].photo_size!=1) continue;\n'
            +prefix+'get_photo(NULL,&documents[i],'+args+');')
t,n=pat.subn(fix,t)
if n!=3:raise SystemExit("Expected 3 response.cpp thumbnail loaders, found "+str(n))
m.write_text(s,encoding="latin-1",newline="\r\n")
r.write_text(t,encoding="latin-1",newline="\r\n")
print("v11.2: remove redundant small-photo requests for Concept98; retain video, sticker and legacy mode.")
