#!/usr/bin/env python3
"""Concept98 v10.7: authentic bundled Windows 98 icons on native buttons.

Transparent multi-size .ico assets are loaded from the executable's adjacent
icons98 folder, cached for the process lifetime. Fallback remains the old
pixel GDI glyph whenever the icon folder is absent.
"""
from pathlib import Path
import sys
if len(sys.argv)!=2:raise SystemExit("Usage: patch_concept98_borrowed_icons_v107.py <src>")
p=Path(sys.argv[1]).resolve()/"src"/"telegacy.cpp"
s=p.read_text(encoding="latin-1")
if "concept98_borrowed_icons_v107" in s:
    print("v10.7 already applied");raise SystemExit(0)
if "concept98_auto_full_photo_pump_v106" not in s:
    raise SystemExit("v10.6 prerequisite missing")

sig="static void concept98_pixel_glyph_v95(HDC dc,int x,int y,int id) {"
if s.count(sig)!=1:raise SystemExit("v10.2 pixel-glyph entry unavailable")
prefix=r'''// concept98_borrowed_icons_v107
// Actual PNG/ICO files were extracted by bundle_win98_icons.py from
// the third-party vintage-icons Win98 collection, not painted from scratch.
static HICON concept98_asset_icon_v107(int id) {
    struct IconSlot { int id; const wchar_t* name; HICON icon; bool tried; };
    static IconSlot slots[] = {
        {8912,L"search.ico",NULL,false},
        {8913,L"profile.ico",NULL,false},
        {8914,L"options.ico",NULL,false}
    };
    for (int i=0;i<(int)ARRAYSIZE(slots);++i) {
        IconSlot* slot=&slots[i];
        if (slot->id!=id) continue;
        if (!slot->tried) {
            slot->tried=true;
            wchar_t exe[MAX_PATH]={0};
            DWORD len=GetModuleFileNameW(NULL,exe,ARRAYSIZE(exe));
            if (len>0 && len<ARRAYSIZE(exe)) {
                wchar_t* slash=wcsrchr(exe,L'\\');
                if (slash) {
                    *(slash+1)=0;
                    wchar_t path[MAX_PATH]={0};
                    _snwprintf_s(path,ARRAYSIZE(path),_TRUNCATE,
                                 L"%sicons98\\%s",exe,slot->name);
                    slot->icon=(HICON)LoadImageW(
                        NULL,path,IMAGE_ICON,16,16,LR_LOADFROMFILE
                    );
                }
            }
            if (!slot->icon)
                diag_log("concept98 v107 icon unavailable id=%d",id);
        }
        return slot->icon;
    }
    return NULL;
}

'''
s=s.replace(sig,prefix+sig+"""\n    HICON native=concept98_asset_icon_v107(id);\n    if(native) {DrawIconEx(dc,x,y,native,16,16,0,NULL,DI_NORMAL);return;}""",1)
p.write_text(s,encoding="latin-1",newline="\r\n")
print("v10.7 uses actual archived Win98 icons for Search/Profile/More "
      "with the original pixel-art fallback if the files are unavailable.")
