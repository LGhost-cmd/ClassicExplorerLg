#!/usr/bin/env python3
"""Concept 98 v9.8: synchronize avatar cache across network/UI threads."""
from pathlib import Path
import sys
if len(sys.argv)!=2:
    raise SystemExit("Usage: patch_concept98_avatar_thread_safety_v98.py <src>")
root=Path(sys.argv[1]).resolve()
p=root/"src"/"helpers.cpp"
s=p.read_text(encoding="latin-1")
if "concept98_avatar_thread_safety_v98" in s:
    print("v9.8 already applied");raise SystemExit(0)
if "concept98_integrity_v96" not in s:
    raise SystemExit("v9.6 required")
if "#include <mutex>" not in s:
    anchor="#include <map>\n"
    if anchor not in s:raise SystemExit("map header unavailable")
    s=s.replace(anchor,anchor+"#include <mutex>\n",1)

anchor="static std::map<ConceptAvatar96Key, ConceptAvatar96> concept98_cache_v96;"
if anchor not in s: raise SystemExit("Avatar cache declaration unavailable")
s=s.replace(anchor,anchor+"""
// concept98_avatar_thread_safety_v98
// Network response_handler and Win32 owner-draw may run on different threads.
static std::recursive_mutex concept98_avatar_mutex_v98;
""",1)

def patch_func(name):
    global s
    start=s.find(name)
    if start<0:raise SystemExit("No v9.8 function "+name)
    brace=s.find("{",start)
    if brace<0:raise SystemExit("No brace "+name)
    inject="\n    std::lock_guard<std::recursive_mutex> cache_guard(concept98_avatar_mutex_v98);\n"
    s=s[:brace+1]+inject+s[brace+1:]
for signature in (
    "void concept98_avatar_clear_v93()",
    "bool concept98_avatar_draw_v93(",
    "void concept98_avatar_pump_v93(",
    "bool concept98_avatar_handle_upload_v93(",
):
    patch_func(signature)
# Helpers evict/failure/request are only called by guarded code paths; no
# duplicate locks are necessary, and a recursive mutex handles callbacks that
# immediately re-enter from the Win32 window procedure.
p.write_text(s,encoding="latin-1",newline="\r\n")
if s.count("cache_guard(concept98_avatar_mutex_v98)")!=4:
    raise SystemExit("Avatar lock coverage incomplete")
print("Applied v9.8: avatar cache protected through UI draw, worker reply, "
      "timer retry and logout cleanup.")
