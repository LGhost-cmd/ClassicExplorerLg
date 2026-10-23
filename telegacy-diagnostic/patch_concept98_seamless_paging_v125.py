#!/usr/bin/env python3
"""Concept98 v12.5: preserve chat while media prefetches, single response-time
scroll anchor, guard reentrant top-of-history requests and progressive photos."""
from pathlib import Path
import sys
if len(sys.argv)!=2:raise SystemExit("Usage: patch_concept98_seamless_paging_v125.py <src>")
root=Path(sys.argv[1]).resolve()
paths={name:root/"src"/(name+".cpp") for name in
       ("telegacy","message","response","helpers","procs")}
src={name:p.read_text(encoding="latin-1") for name,p in paths.items()}
if "concept98_seamless_paging_v125" in src["telegacy"]:raise SystemExit(0)
if "concept98_page_stage_v124" not in src["telegacy"]:raise SystemExit("v12.4 required")
def once(name,old,new,why):
    v=src[name];n=v.count(old)
    if n!=1:raise SystemExit("v12.5 "+why+": expected once, got "+str(n))
    src[name]=v.replace(old,new,1)

# A full-size STATIC child was hiding the ENTIRE chat during each prefetch.
# Keep v12.4's 12-second bounded prefetch bookkeeping and the inline loading
# cards but do not create the obscuring HWND at all.
once("telegacy",
     "    if(!concept98_page_veil_v124){",
     "    if(false && !concept98_page_veil_v124){ // concept98_seamless_paging_v125: non-obscuring prefetch",
     "remove modal-like veil")
# The unused HWND remains null, so later repaint and label branches are inert.

# History layout already has a response-time, character-offset-sensitive
# anchor (history_view_anchor_v54). The v86 add-on was restoring a SECOND,
# request-time snapshot after the first restoration, snapping a user who kept
# scrolling back to an obsolete position.
once("response",
     "\t\thistory_v86_restore_viewport(); // chat_viewport_media_stability_v86",
     "\t\t// concept98_seamless_paging_v125: v54 already restored the response-time viewport; never apply a stale v86 snapshot twice.",
     "double scroll restore")
once("helpers",
     "    history_v86_capture_viewport();\n\n    BYTE unenc_query[112];",
     "    // v125: v54 captures the actual viewport when the response arrives.\n\n    BYTE unenc_query[112];",
     "obsolete request-time scroll anchor")

# RichEdit sends many synthetic SB_TOP/SB_THUMBPOSITION notifications during
# prepends. Do not call get_history() again when a request is already pending.
once("procs",
     '''        msg == WM_VSCROLL &&
        current_peer &&
        !no_more_msgs''',
     '''        msg == WM_VSCROLL &&
        current_peer &&
        !no_more_msgs &&
        InterlockedCompareExchange(&history_request_pending,0,0)==0 // v125 suppress reentrant pagination''',
     "reentrant top-of-history scroll")

# Telegram photoSizeProgressive ('j') is valid media. The legacy renderer
# previously excluded it and left photo_size=0, making the full-JPEG pump skip
# it forever. Only accept a progressive entry if its size vector is valid;
# continue rejecting stripped 'i' previews.
old="(size > size_main || size == 'w') && size != 'i' && size != 'j'"
new="""(size > size_main || size == 'w') && size != 'i' &&
                    (size != 'j' ||
                      (photosize_cons == 0xfa3efb95 &&
                       read_le(doc+offset+20,4)>0 &&
                       read_le(doc+offset+20,4)<=64)) /* v125 progressive JPEG eligible */"""
once("message",old,new,"progressive JPEG photo size")

# Record why new media may still be ineligible without making a guess about
# unsupported Telegram image sizes; no speculative OLE substitution.
marker='''    if(newly_added_docs>(int)documents.size())
        newly_added_docs=(int)documents.size();'''
audit='''    if(newly_added_docs>(int)documents.size())
        newly_added_docs=(int)documents.size();
    int zero_size=0,no_ref=0,full=0,bad_range=0,hidden=0,photo=0;
    for(int i=0;i<newly_added_docs;i++){
        const Document* d=&documents[i];
        if(!d->visible){hidden++;continue;}
        if(d->photo_size==0){zero_size++;continue;}
        if(d->photo_size==1 || d->photo_size==3)continue;
        photo++;
        if(!d->file_reference){no_ref++;continue;}
        if(d->min<0 || d->max!=d->min+1)bad_range++;
        if(media_chat_v81_photo_is_full(d))full++;
    }
    diag_log("concept98 v125 page media audit docs=%d photos=%d full=%d no_size=%d no_reference=%d bad_range=%d hidden=%d",
             newly_added_docs,photo,full,zero_size,no_ref,bad_range,hidden);'''
once("telegacy",marker,audit,"per-page eligibility diagnostic")

for name,p in paths.items():p.write_text(src[name],encoding="latin-1",newline="\r\n")
print("v12.5 seamless background media, single response-time viewport restore, guarded history paging, progressive JPEG selection and per-page media audit.")
