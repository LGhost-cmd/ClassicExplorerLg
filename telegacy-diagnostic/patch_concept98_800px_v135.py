#!/usr/bin/env python3
"""Concept98 v13.5: choose a Telegram PhotoSize near 800 pixels for automatic
chat preview. Explicit original/open remains backed by largest PhotoSize.
No stripped thumbnails, no fabricated previews, and no OLE geometry changes."""
from pathlib import Path
import sys
if len(sys.argv)!=2: raise SystemExit("Usage: patch_concept98_800px_v135.py <src>")
root=Path(sys.argv[1]).resolve()
h=root/"include"/"telegacy.h"; m=root/"src"/"message.cpp"; t=root/"src"/"telegacy.cpp"
src={p:p.read_text(encoding="latin-1") for p in (h,m,t)}
if "concept98_preview_size_v135" in src[m]: raise SystemExit(0)
if "concept98_reply_links_v134" not in src[t]: raise SystemExit("v13.4 required")
def one(p,a,b,why):
 n=src[p].count(a)
 if n!=1:raise SystemExit("v13.5 "+why+" matches="+str(n))
 src[p]=src[p].replace(a,b,1)

one(h,"char photo_size;\n\tbool visible;",
"""char photo_size;
    // concept98_preview_size_v135: largest Telegram PhotoSize retained.
    char concept98_original_photo_size_v135;
    int concept98_original_photo_bytes_v135;
    bool visible;""","Document dimensions fields")
one(m,"\t\t\tchar size_main = 0;",
r'''            // v13.5: smaller network PhotoSize only when Telegram
            // supplies known dimensions. Prefer the largest <=800px.
            char concept98_preview_size_v135=0;
            int concept98_best_under_v135=0;
            int concept98_best_over_v135=100000;
            int concept98_preview_bytes_v135=0;
            int concept98_original_bytes_v135=0;
			char size_main = 0;''',"photo selection fields")
one(m,"""\t\t\t\tchar size = (char)doc[offset + 5];""",
r'''				char size = (char)doc[offset + 5];
                if(concept98_enabled && size!='i' && size!='j' &&
                   (photosize_cons==0x75c78e60 || photosize_cons==0xfa3efb95)){
                    // photoSize and photoSizeProgressive: type is a TL
                    // one-byte string padded to four bytes, then w/h.
                    const int w_v135=(int)read_le(doc+offset+8,4);
                    const int h_v135=(int)read_le(doc+offset+12,4);
                    if(w_v135>0 && h_v135>0 &&
                       w_v135<20000 && h_v135<20000){
                        int longest=w_v135>h_v135?w_v135:h_v135;
                        int candidate=0;
                        if(photosize_cons==0xfa3efb95){
                            int levels=(int)read_le(doc+offset+20,4);
                            if(levels>0 && levels<=32)
                                candidate=(int)read_le(doc+offset+20+levels*4,4);
                        }else candidate=(int)read_le(doc+offset+16,4);
                        const bool under=longest<=800;
                        if((under && longest>concept98_best_under_v135) ||
                           (!under && concept98_best_under_v135==0 &&
                            longest<concept98_best_over_v135)){
                            concept98_preview_size_v135=size;
                            concept98_preview_bytes_v135=candidate;
                            if(under)concept98_best_under_v135=longest;
                            else concept98_best_over_v135=longest;
                        }
                    }
                }''',"read photoSize geometry")
one(m,"""\t\t\tdocument.photo_size = size_main;""",
r'''            // Preserve the original for explicit double-click. Preview
            // bytes remain a separate request, never an upscaled strip.
            document.concept98_original_photo_size_v135=size_main;
            document.concept98_original_photo_bytes_v135=(int)document.size;
			document.photo_size =
                concept98_enabled && concept98_preview_size_v135?
                    concept98_preview_size_v135:size_main;
            if(concept98_enabled && concept98_preview_size_v135 &&
               concept98_preview_bytes_v135>0)
                document.size=concept98_preview_bytes_v135;
            diag_log("concept98 v135 PhotoSize preview=%c original=%c",
                     document.photo_size,size_main);''',"choose preview only")
# Set newly introduced fields on all other documents, and preserve them across
# existing copy/move of Document structs. This avoids junk in non-photo media.
if "Document document = {};" not in src[m]:
    raise SystemExit("v13.5 requires zero-initialized media Document")
# Request the true original when the user explicitly double clicks, including
# after automatic smaller-size preview was cached.
defn="static bool media_chat_full_photo_user_action(\n    Document* document,\n    bool save_and_open\n) {"
one(t,defn,defn+'''
    const bool original_v135=save_and_open &&
        document && document->concept98_original_photo_size_v135;
''',"photo user action original setting")
# A double-click during automatic preview must start a new transfer, not
# simply convert the preview into a downloaded "original".
one(t,"""    if (same_active) {
        if (save_and_open)""",
"""    if (same_active && original_v135 &&
        media_chat_full_photo_size != document->concept98_original_photo_size_v135) {
        media_chat_full_photo_reset(true);
        same_active=false;
    }
    if (same_active) {
        if (save_and_open)""","upgrade medium in progress")
one(t,"""    bool started = media_chat_full_photo_begin(
        document,
        preferred
    );""",
"""    Document exact_v135=*document;
    if(original_v135){
        exact_v135.photo_size=document->concept98_original_photo_size_v135;
        exact_v135.size=document->concept98_original_photo_bytes_v135;
    }
    bool started=media_chat_full_photo_begin(
        original_v135?&exact_v135:document,
        preferred
    );""","original photo begin")
# FILE_MIGRATE must retain original size across DC migration.
one(t,"""    bool restarted =
        media_chat_full_photo_begin(
            document,
            target_dc
        );""",
"""    Document exact_v135=*document;
    if(media_chat_full_photo_open_when_done &&
       document->concept98_original_photo_size_v135){
        exact_v135.photo_size=document->concept98_original_photo_size_v135;
        exact_v135.size=document->concept98_original_photo_bytes_v135;
    }
    bool restarted =
        media_chat_full_photo_begin(
            &exact_v135,
            target_dc
        );""","original photo DC migration")

for p,body in src.items():
 p.write_text(body,encoding="latin-1",newline="\r\n")
print("v13.5: Telegram 800px PhotoSize for normal chat; original on explicit open.")
