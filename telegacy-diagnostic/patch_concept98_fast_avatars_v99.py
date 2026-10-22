#!/usr/bin/env python3
"""v9.9: parallel avatar fetching, thumbnail disk cache, reduced UI latency."""
from pathlib import Path
import sys
if len(sys.argv)!=2:raise SystemExit("Usage: patch_concept98_fast_avatars_v99.py <src>")
root=Path(sys.argv[1]).resolve()
hp=root/"src"/"helpers.cpp"
cp=root/"src"/"telegacy.cpp"

def read(p):return p.read_text(encoding="latin-1")
def save(p,t):p.write_text(t,encoding="latin-1",newline="\r\n")
def replace(s,a,b,label):
    if a not in s:raise SystemExit("v9.9 missing "+label)
    return s.replace(a,b,1)

h=read(hp)
if "concept98_fast_avatars_v99" in h:
    print("v9.9 already applied");raise SystemExit(0)
if "concept98_avatar_thread_safety_v98" not in h:
    raise SystemExit("v9.8 prerequisite missing")
h=replace(h,"static DWORD concept98_request_after_v96=0;",
r'''static DWORD concept98_request_after_v96=0;
// concept98_fast_avatars_v99: no global head-of-line blocking
struct ConceptAvatarPending99 {
    ConceptAvatar96Key key;
    DWORD tick;
};
static std::map<__int64,ConceptAvatarPending99> concept98_pending_v99;

static bool concept98_avatar_disk_path_v99(
    ConceptAvatar96Key key, __int64 photo, wchar_t* path, size_t size
) {
    if (!path || !size || !appdata_path[0]) return false;
    wchar_t folder[MAX_PATH]={0};
    _snwprintf_s(folder,ARRAYSIZE(folder),_TRUNCATE,
                 L"%s\\avatar_cache98",appdata_path);
    CreateDirectoryW(folder,NULL);
    _snwprintf_s(path,size,_TRUNCATE,
        L"%s\\%016I64X-%d-%016I64X-%016I64X.bmp",
        folder,(unsigned __int64)read_le(myself.id,8),key.first,
        (unsigned __int64)key.second,(unsigned __int64)photo);
    return wcslen(path)<MAX_PATH-4;
}
static HBITMAP concept98_avatar_disk_load_v99(
    ConceptAvatar96Key key, __int64 photo
) {
    wchar_t path[MAX_PATH]={0};
    if (!concept98_avatar_disk_path_v99(key,photo,path,ARRAYSIZE(path)))
        return NULL;
    HBITMAP image=(HBITMAP)LoadImageW(
        NULL,path,IMAGE_BITMAP,0,0,LR_LOADFROMFILE|LR_CREATEDIBSECTION);
    if (!image) return NULL;
    BITMAP bm={0};
    if (!GetObjectW(image,sizeof(bm),&bm) ||
        bm.bmWidth!=40 || bm.bmHeight!=40) {
        DeleteObject(image); return NULL;
    }
    return image;
}
static void concept98_avatar_disk_save_v99(
    ConceptAvatar96Key key, __int64 photo, HBITMAP image
) {
    if (!image) return;
    wchar_t path[MAX_PATH]={0};
    if (!concept98_avatar_disk_path_v99(key,photo,path,ARRAYSIZE(path)))
        return;
    // Windows-compatible, uncompressed 40x40 BGRA bitmap; no original
    // private full-resolution avatar data are persisted to disk.
    BITMAPINFO info={0};
    info.bmiHeader.biSize=sizeof(BITMAPINFOHEADER);
    info.bmiHeader.biWidth=40;
    info.bmiHeader.biHeight=40;
    info.bmiHeader.biPlanes=1;
    info.bmiHeader.biBitCount=32;
    info.bmiHeader.biCompression=BI_RGB;
    BYTE pixels[40*40*4]={0};
    HDC dc=GetDC(NULL);
    if (!dc) return;
    bool decoded=GetDIBits(dc,image,0,40,pixels,&info,DIB_RGB_COLORS)==40;
    ReleaseDC(NULL,dc);
    if (!decoded) return;
    HANDLE file=CreateFileW(path,GENERIC_WRITE,0,NULL,CREATE_ALWAYS,
                            FILE_ATTRIBUTE_NORMAL,NULL);
    if (file==INVALID_HANDLE_VALUE) return;
    BITMAPFILEHEADER bmp={0};
    bmp.bfType=0x4D42;
    bmp.bfOffBits=sizeof(BITMAPFILEHEADER)+sizeof(BITMAPINFOHEADER);
    bmp.bfSize=bmp.bfOffBits+sizeof(pixels);
    DWORD written=0;
    BOOL good=WriteFile(file,&bmp,sizeof(bmp),&written,NULL) &&
              written==sizeof(bmp);
    good=good && WriteFile(file,&info.bmiHeader,sizeof(info.bmiHeader),
                           &written,NULL) &&
              written==sizeof(info.bmiHeader);
    good=good && WriteFile(file,pixels,sizeof(pixels),&written,NULL) &&
              written==sizeof(pixels);
    CloseHandle(file);
    if (!good) DeleteFileW(path);
}
''',"disk cache definition")
h=replace(h,"    concept98_pending_v96=false;\n    memset(concept98_pending_rpc_v96,0,8);",
"""    concept98_pending_v96=false;
    concept98_pending_v99.clear();
    memset(concept98_pending_rpc_v96,0,8);""","clear pending requests")
h=replace(h,"    concept98_pending_key_v96=concept98_key_v96(peer);\n    memcpy(concept98_pending_rpc_v96,query+16,8);\n    concept98_pending_v96=true;\n    concept98_pending_tick_v96=GetTickCount();\n    concept98_request_after_v96=GetTickCount()+1400;",
r'''    ConceptAvatarPending99 pending;
    pending.key=concept98_key_v96(peer);
    pending.tick=GetTickCount();
    concept98_pending_v99[(__int64)read_le(query+16,8)]=pending;
    concept98_request_after_v96=GetTickCount()+210;''',"parallel request map")
start=h.index("    if (concept98_pending_v96) {",h.index("void concept98_avatar_pump_v93("))
end=h.index("    if ((LONG)(now-concept98_request_after_v96)<0) return;",start)
h=h[:start]+r'''    for (std::map<__int64,ConceptAvatarPending99>::iterator it=
             concept98_pending_v99.begin();it!=concept98_pending_v99.end();) {
        if (now-it->second.tick>14000) {
            concept98_avatar_failure_v96(it->second.key);
            diag_log("concept98 v99 avatar request timeout");
            it=concept98_pending_v99.erase(it);
        } else ++it;
    }
    if (concept98_pending_v99.size()>=4) return;
'''+h[end:]
needle="            concept98_cache_v96[key]=entry;\n            it=concept98_cache_v96.find(key);"
h=replace(h,needle,needle+r'''
            // Disk thumbnails are 40x40 and keyed by account, chat kind,
            // stable chat id and Telegram photo id. Warm startup is local.
            it->second.bitmap=concept98_avatar_disk_load_v99(key,photo_id);
            if (it->second.bitmap) {
                HWND list_ui=hMain ? GetDlgItem(hMain,8910) : NULL;
                HWND heading=hMain ? GetDlgItem(hMain,8996) : NULL;
                if (list_ui) InvalidateRect(list_ui,NULL,FALSE);
                if (heading) InvalidateRect(heading,NULL,FALSE);
                diag_log("concept98 v99 avatar disk hit type=%d",key.first);
                continue;
            }''',"warm local cache")
start=h.index("    if (!concept98_pending_v96 || !request_id ||",h.index("bool concept98_avatar_handle_upload_v93("))
end=h.index("    if (!response || length<17) {",start)
h=h[:start]+r'''    if (!request_id) return false;
    __int64 rpc=(__int64)read_le((BYTE*)request_id,8);
    std::map<__int64,ConceptAvatarPending99>::iterator pending=
        concept98_pending_v99.find(rpc);
    if (pending==concept98_pending_v99.end()) return false;
    ConceptAvatar96Key key=pending->second.key;
    concept98_pending_v99.erase(pending);
'''+h[end:]
needle='    it->second.last_use=GetTickCount();\n    HWND list=hMain ? GetDlgItem(hMain,8910) : NULL;'
h=replace(h,needle,'    it->second.last_use=GetTickCount();\n    concept98_avatar_disk_save_v99(key,it->second.photo_id,thumb);\n    HWND list=hMain ? GetDlgItem(hMain,8910) : NULL;', "persist thumbnail")
save(hp,h)

s=read(cp)
needle='    SetTimer(hwnd, CONCEPT98_TIMER, 1800, NULL);'
s=replace(s,needle,needle+'\n    SetTimer(hwnd, 8998, 240, NULL);',"background avatar tick")
needle='    if (msg == WM_TIMER && wParam == CONCEPT98_TIMER) {'
s=replace(s,needle,r'''    if (msg == WM_TIMER && wParam == 8998) {
        if (concept98_enabled && dcInfoMain.ready)
            concept98_avatar_pump_v93(
                concept98_list,concept98_folder_indices,
                global_chat_search_mode
            );
        return 0;
    }
'''+needle,"independent avatar timer")
needle='\t\tKillTimer(hWnd, CONCEPT98_TIMER);'
s=replace(s,needle,needle+'\n\t\tKillTimer(hWnd, 8998);',"avatar timer cleanup")
# The slow old 1.8s tick becomes just chat list synchronization.
needle='        concept98_avatar_pump_v93(concept98_list,concept98_folder_indices,global_chat_search_mode);'
s=replace(s,needle,'        // v9.9 avatar loading runs on its own lightweight 240ms timer.',
          "no duplicate avatar queue tick")
save(cp,s)
for p,checks in {hp:("concept98_fast_avatars_v99","concept98_pending_v99",
                     "concept98_avatar_disk_load_v99","concept98_avatar_disk_save_v99"),
                 cp:("SetTimer(hwnd, 8998, 240, NULL)","KillTimer(hWnd, 8998)")}.items():
    data=read(p)
    for c in checks:
        if c not in data:raise SystemExit("v9.9 check missing "+c)
print("Concept 98 v9.9: four simultaneous avatar requests, staggered 210ms, "
      "40x40 account/photo-scoped warm disk cache and independent timer.")
