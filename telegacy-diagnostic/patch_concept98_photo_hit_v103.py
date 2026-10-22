#!/usr/bin/env python3
"""Concept98 v10.3: identity-preserving photo hit correction (<=1 cp only).

A delayed RichEdit OLE can shift by one char. Capture a canonical COM identity
only if the candidate is unique; never target arbitrary nearest photo.
"""
from pathlib import Path
import sys
if len(sys.argv)!=2:raise SystemExit("Usage: patch_concept98_photo_hit_v103.py <src>")
p=Path(sys.argv[1]).resolve()/"src"/"telegacy.cpp"
s=p.read_text(encoding="latin-1")
if "concept98_photo_hit_v103" in s:
    print("v10.3 already applied");raise SystemExit(0)
if "concept98_full_photo_cache_v101" not in s:raise SystemExit("v10.1 required")
start=s.find("static bool media_chat_v87_capture_photo_ole(")
end=s.find("static bool media_chat_upgrade_photo_in_place(",start)
if start<0 or end<0:raise SystemExit("Exact clicked OLE capture unavailable")
block=s[start:end]
a='    int matches = 0;\n    IUnknown* captured = NULL;'
if a not in block:raise SystemExit("OLE capture counter missing")
block=block.replace(a,a+'\n    int resolved_cp_v103 = -1; // concept98_photo_hit_v103',1)
a='if ((int)reo.cp == expected) {'
if a not in block:raise SystemExit("OLE expected cp lookup missing")
block=block.replace(a,'if (abs((int)reo.cp - expected) <= 1) {',1)
a='                matches++;\n\n                if (!captured) {'
if a not in block:raise SystemExit("Captured match counter missing")
block=block.replace(a,'                matches++;\n                if (matches==1) resolved_cp_v103=(int)reo.cp;\n\n                if (!captured) {',1)
a='    media_chat_full_photo_clicked_cp_v87 = expected;\n\n    diag_log('
if a not in block:raise SystemExit("Capture confirmation missing")
block=block.replace(a,'    media_chat_full_photo_clicked_cp_v87 = resolved_cp_v103;\n    if (resolved_cp_v103 != expected) {\n'
                    '        diag_log("concept98 v103 corrected clicked OLE cp=%d->%d",\n'
                    '                 expected,resolved_cp_v103);\n'
                    '        document->min=resolved_cp_v103;\n'
                    '        document->max=resolved_cp_v103+1;\n'
                    '    }\n\n    diag_log(',1)
s=s[:start]+block+s[end:]
p.write_text(s,encoding="latin-1",newline="\r\n")
for t in ("concept98_photo_hit_v103","corrected clicked OLE cp","resolved_cp_v103"):
    if t not in s:raise SystemExit("v10.3 verification missing "+t)
print("Concept98 v10.3: tolerate a unique one-char OLE shift for clicked "
      "photo, retaining exact COM identity and rejecting ambiguous overlaps.")
