#!/usr/bin/env python3
"""Concept98 v10.4: fail-closed WebP OLE replacement, never duplicate a poster."""
from pathlib import Path
import sys
if len(sys.argv)!=2: raise SystemExit("Usage: patch_concept98_static_webp_identity_v104.py <src>")
p=Path(sys.argv[1]).resolve()/"src"/"telegacy.cpp"
s=p.read_text(encoding="latin-1")
if "concept98_static_webp_identity_v104" in s:
    print("v10.4 already applied");raise SystemExit(0)
if "concept98_photo_hit_v103" not in s:raise SystemExit("Requires v10.3")

start=s.find("static bool media_chat_sticker_commit_webp_v86(")
end=s.find("static void media_chat_sticker_",start+10)
if start<0:raise SystemExit("Missing static WebP sticker OLE commit")
if end<0:end=s.find("static bool media_chat_sticker_",start+10)
if end<0:raise SystemExit("Unable to isolate static WebP commit")
block=s[start:end]
point=r'''    CHARRANGE selection = {0};'''
if point not in block:raise SystemExit("WebP initial range marker missing")
inject=r'''    // concept98_static_webp_identity_v104
    // Capture exactly one BITMAP OLE at the intended cp. A nearby photo
    // must never be substituted for a sticker, and a failed deletion must
    // not be followed by insertion of a second OLE.
    IRichEditOle* sticker_ole=NULL;
    SendMessageW(chat,EM_GETOLEINTERFACE,0,(LPARAM)&sticker_ole);
    if (!sticker_ole) {DeleteObject(bitmap);return false;}
    LONG before_count=sticker_ole->GetObjectCount();
    IUnknown* old_identity=NULL;
    int candidates=0;
    for (LONG i=0;i<before_count;i++) {
        REOBJECT reo={0};
        reo.cbStruct=sizeof(reo);
        if (FAILED(sticker_ole->GetObject(
                i,&reo,REO_GETOBJ_POLEOBJ)) || !reo.poleobj)
            continue;
        if ((int)reo.cp==cp) {
            IUnknown* identity=NULL;
            if (media_chat_v87_query_bitmap_identity(
                    reo.poleobj,&identity) && identity) {
                candidates++;
                if (!old_identity) old_identity=identity;
                else identity->Release();
            }
        }
        reo.poleobj->Release();
    }
    sticker_ole->Release();
    if (candidates!=1 || !old_identity) {
        if (old_identity) old_identity->Release();
        DeleteObject(bitmap);
        diag_log("concept98 v104 WebP refused ambiguous OLE cp=%d matches=%d",
                 cp,candidates);
        return false;
    }

'''
block=block.replace(point,inject+point,1)
old=r'''    insert_image(
        chat,
        NULL,
        bitmap
    );

    DeleteObject(bitmap);

    document->min = cp;
    document->max = cp + 1;'''
new=r'''    LONG after_delete_count=media_chat_v87_object_count();
    bool deleted=
        media_chat_v87_find_identity_cp(old_identity)<0 &&
        before_count>0 &&
        after_delete_count==before_count-1;
    old_identity->Release();

    if (deleted) {
        insert_image(chat,NULL,bitmap);
    } else {
        diag_log("concept98 v104 WebP deletion refused cp=%d before=%ld after=%ld",
                 cp,before_count,after_delete_count);
    }
    DeleteObject(bitmap);

    LONG after_insert_count=media_chat_v87_object_count();
    bool inserted=deleted && after_insert_count==before_count &&
        (media_chat_v87_exact_bitmap_at_cp(cp) ||
         media_chat_v87_exact_bitmap_at_cp(cp+1));

    if (inserted) {
        document->min=cp;
        document->max=cp+1;
    }'''
if old not in block:raise SystemExit("WebP unsafe replacement block missing")
block=block.replace(old,new,1)
old=r'''    diag_log(
        "chat v86 static WebP committed OLE cp=%d path=%ls",
        cp,
        path
    );

    return true;'''
new=r'''    if (inserted) {
        diag_log("concept98 v104 WebP replaced exactly cp=%d path=%ls",
                 cp,path);
    } else {
        diag_log("concept98 v104 WebP kept fallback cp=%d after=%ld",
                 cp,after_insert_count);
    }
    return inserted;'''
if old not in block:raise SystemExit("WebP completion confirmation missing")
block=block.replace(old,new,1)
s=s[:start]+block+s[end:]
p.write_text(s,encoding="latin-1",newline="\r\n")
for marker in ("concept98_static_webp_identity_v104","old_identity",
               "after_delete_count==before_count-1","concept98 v104 WebP"):
    if marker not in s:raise SystemExit("v10.4 missing "+marker)
print("Concept98 v10.4: identity-checked static WebP OLE deletion and "
      "insert-count validation; ambiguous media keep existing placeholder.")
