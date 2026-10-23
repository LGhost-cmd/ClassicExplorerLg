#!/usr/bin/env python3
"""v10.8: cache-first chat media and whole-loaded-page JPEG scheduling.
No thumbnail is painted; full JPEGs are verified and fitted into RichEdit's
fixed-size OLE card before the document is inserted, avoiding late cp drift.
"""
from pathlib import Path
import sys
if len(sys.argv)!=2: raise SystemExit("Usage: patch_concept98_cache_first_v108.py <src>")
root=Path(sys.argv[1]).resolve()
p=root/"src"/"telegacy.cpp"
m=root/"src"/"message.cpp"
t=p.read_text(encoding="latin-1")
s=m.read_text(encoding="latin-1")
if "concept98_cache_first_v108" in s:
    print("v10.8 already applied"); raise SystemExit(0)
if "concept98_auto_full_photo_pump_v106" not in t:
    raise SystemExit("Requires v10.7 patch chain")
anchor="static HBITMAP media_chat_photo_placeholder() {"
if s.count(anchor)!=1: raise SystemExit("v10.8 missing photo placeholder")
extra=r'''
// concept98_cache_first_v108: load the verified full JPEG BEFORE inserting
// this message's RichEdit OLE, never guess another object's text position.
static HBITMAP concept98_cached_photo_card_v108(const Document* document) {
    if (!document || !read_le(document->id,8) ||
        !read_le(document->access_hash,8) || !appdata_path[0])
        return NULL;
    wchar_t path[MAX_PATH]={0};
    _snwprintf_s(path,ARRAYSIZE(path),_TRUNCATE,
        L"%s\\photo_cache98\\%016I64X-%016I64X-%016I64X.jpg",
        appdata_path,
        (unsigned __int64)read_le(myself.id,8),
        (unsigned __int64)read_le(document->id,8),
        (unsigned __int64)read_le(document->access_hash,8));
    FILE* file=_wfopen(path,L"rb");
    if (!file) return NULL;
    _fseeki64(file,0,SEEK_END);
    __int64 count=_ftelli64(file);
    if (count<128 || count>8*1024*1024) {
        fclose(file); return NULL;
    }
    _fseeki64(file,0,SEEK_SET);
    std::vector<BYTE> bytes((size_t)count);
    bool ok=fread(&bytes[0],1,bytes.size(),file)==bytes.size();
    fclose(file);
    if (!ok || bytes[0]!=0xFF || bytes[1]!=0xD8) return NULL;
    HBITMAP decoded=jpg_to_bmp(&bytes[0],(int)bytes.size());
    if (!decoded) return NULL;
    HBITMAP card=media_chat_make_photo_card(decoded);
    if (card) DeleteObject(decoded);
    if (card) diag_log("concept98 v108 cache-first photo loaded");
    return card ? card : decoded;
}

'''
s=s.replace(anchor,extra+anchor,1)
old=r'''			loading_card = media_chat_photo_placeholder();
			display_bitmap = loading_card;

			if (display_bitmap)
				insert_image(chat, NULL, display_bitmap);'''
new=r'''			HBITMAP cached_card=concept98_cached_photo_card_v108(&document);
			if (cached_card) {
				display_bitmap=cached_card;
			} else {
				loading_card=media_chat_photo_placeholder();
				display_bitmap=loading_card;
			}

			if (display_bitmap)
				insert_image(chat, NULL, display_bitmap);
			if (cached_card)
				DeleteObject(cached_card);'''
if s.count(old)!=1: raise SystemExit("v10.8 photo card insert block changed")
s=s.replace(old,new,1)
# v10.6 skipped photos outside the live viewport, even if the current
# history page already contained them. Fetch every loaded page photo once.
old=r'''        POINTL pos={0,0};
        if (SendMessageW(chat,EM_POSFROMCHAR,
                         (WPARAM)&pos,(LPARAM)d->min)==-1) continue;
        if (pos.y>view.bottom || pos.y+216<view.top) continue;'''
new=r'''        // Page-wide prefetch: do not require intersection with the viewport.
        // Every loaded message page is eligible, like the Media gallery.
        // The exact OLE at d->min must still exist before any replacement.'''
if t.count(old)!=1: raise SystemExit("v10.8 photo viewport gate missing")
t=t.replace(old,new,1)
old='if (count>=32 && filename[0]) {'
if t.count(old)!=1: raise SystemExit("v10.8 cache prune threshold missing")
t=t.replace(old,'if (count>=256 && filename[0]) { // concept98_cache_first_v108',1)
m.write_text(s,encoding="latin-1",newline="\r\n")
p.write_text(t,encoding="latin-1",newline="\r\n")
print("v10.8: cache-first full JPEG cards; 256-file cache; prefetch all loaded history photos.")
