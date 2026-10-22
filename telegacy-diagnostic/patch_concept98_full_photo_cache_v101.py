#!/usr/bin/env python3
"""Concept98 v10.1: cache verified full-quality JPEGs for repeat photo clicks.

Cache is account-scoped and bounded to <=32 files (8MB each), never to be used
for replacing an unverified OLE; a failed cache read goes through Telegram.
"""
from pathlib import Path
import sys
if len(sys.argv)!=2:raise SystemExit("Usage: patch_concept98_full_photo_cache_v101.py <src>")
p=Path(sys.argv[1]).resolve()/"src"/"telegacy.cpp"
s=p.read_text(encoding="latin-1")
if "concept98_full_photo_cache_v101" in s:
    print("v10.1 already applied");raise SystemExit(0)
if "concept98_viewport_v100" not in s:
    raise SystemExit("v10.0 prerequisite missing")

def sub(old,new,label):
    global s
    if old not in s:raise SystemExit("v10.1 missing "+label)
    s=s.replace(old,new,1)

# The upload.file completion handler is defined above the photo click action,
# so forward-declare the cache writer before that earlier response function.
proto="static DCInfo* media_chat_full_photo_dc = NULL; // chat_media_dc_retry_v66"
if proto not in s:raise SystemExit("Full photo state anchor unavailable")
s=s.replace(proto,proto+"\nstatic void concept98_full_photo_save_v101(\n"
    "    const BYTE* id,const BYTE* hash,const std::vector<BYTE>& jpeg);",
    1)

helpers=r'''// concept98_full_photo_cache_v101
static bool concept98_full_photo_path_v101(
    const BYTE* id,const BYTE* hash,wchar_t* out,size_t cap
) {
    if (!id || !hash || !out || !cap || !appdata_path[0])
        return false;
    wchar_t folder[MAX_PATH]={0};
    _snwprintf_s(folder,ARRAYSIZE(folder),_TRUNCATE,
                 L"%s\\photo_cache98",appdata_path);
    CreateDirectoryW(folder,NULL);
    _snwprintf_s(out,cap,_TRUNCATE,
       L"%s\\%016I64X-%016I64X-%016I64X.jpg",
       folder,(unsigned __int64)read_le(myself.id,8),
       (unsigned __int64)read_le((BYTE*)id,8),
       (unsigned __int64)read_le((BYTE*)hash,8));
    return wcslen(out)<MAX_PATH-4;
}
static void concept98_full_photo_prune_v101(const wchar_t* folder) {
    if (!folder || !folder[0]) return;
    wchar_t search[MAX_PATH]={0};
    _snwprintf_s(search,ARRAYSIZE(search),_TRUNCATE,L"%s\\*.jpg",folder);
    WIN32_FIND_DATAW item={0};
    HANDLE find=FindFirstFileW(search,&item);
    if (find==INVALID_HANDLE_VALUE) return;
    int count=0;
    FILETIME oldest={0};
    wchar_t filename[MAX_PATH]={0};
    do {
        if (item.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) continue;
        count++;
        if (!filename[0] ||
            CompareFileTime(&item.ftLastWriteTime,&oldest)<0) {
            oldest=item.ftLastWriteTime;
            wcscpy_s(filename,item.cFileName);
        }
    } while (FindNextFileW(find,&item));
    FindClose(find);
    if (count>=32 && filename[0]) {
        wchar_t full[MAX_PATH]={0};
        _snwprintf_s(full,ARRAYSIZE(full),_TRUNCATE,
                     L"%s\\%s",folder,filename);
        DeleteFileW(full);
    }
}
static void concept98_full_photo_save_v101(
    const BYTE* id,const BYTE* hash,const std::vector<BYTE>& jpeg
) {
    if (jpeg.size()<128 || jpeg.size()>8*1024*1024 ||
        jpeg[0]!=0xFF || jpeg[1]!=0xD8) return;
    wchar_t path[MAX_PATH]={0};
    if (!concept98_full_photo_path_v101(id,hash,path,ARRAYSIZE(path)))
        return;
    wchar_t folder[MAX_PATH]={0};
    wcscpy_s(folder,path);
    wchar_t* sep=wcsrchr(folder,L'\\');
    if (!sep) return;
    *sep=0;
    concept98_full_photo_prune_v101(folder);
    FILE* file=_wfopen(path,L"wb");
    if (!file) return;
    size_t written=fwrite(&jpeg[0],1,jpeg.size(),file);
    fclose(file);
    if (written!=jpeg.size()) DeleteFileW(path);
    else diag_log("concept98 v101 cached full photo bytes=%Iu",
                  jpeg.size());
}
static bool concept98_full_photo_load_v101(
    const Document* document,std::vector<BYTE>* jpeg
) {
    if (!document || !jpeg) return false;
    wchar_t path[MAX_PATH]={0};
    if (!concept98_full_photo_path_v101(document->id,
        document->access_hash,path,ARRAYSIZE(path))) return false;
    FILE* file=_wfopen(path,L"rb");
    if (!file) return false;
    _fseeki64(file,0,SEEK_END);
    __int64 bytes=_ftelli64(file);
    if (bytes<128 || bytes>8*1024*1024) {fclose(file);return false;}
    _fseeki64(file,0,SEEK_SET);
    jpeg->resize((size_t)bytes);
    bool ok=fread(&(*jpeg)[0],1,(size_t)bytes,file)==(size_t)bytes;
    fclose(file);
    if (!ok || (*jpeg)[0]!=0xFF || (*jpeg)[1]!=0xD8) {
        jpeg->clear();
        return false;
    }
    return true;
}
'''
anchor="static bool media_chat_full_photo_user_action(\n    Document* document,\n    bool save_and_open\n) {"
if anchor not in s:raise SystemExit("Photo user action definition missing")
s=s.replace(anchor,helpers+"\n"+anchor,1)
# Capturing the actual clicked OLE via the existing v8.7 identity helper
# is mandatory; this avoids replacing a neighbouring album image.
anchor=r'''    media_chat_v87_capture_photo_ole(
        document
    );

    bool same_active ='''
if anchor not in s:raise SystemExit("Exact OLE click capture missing")
s=s.replace(anchor,r'''    media_chat_v87_capture_photo_ole(document);
    if (!save_and_open && !media_chat_v81_photo_is_full(document)) {
        std::vector<BYTE> jpeg;
        if (concept98_full_photo_load_v101(document,&jpeg)) {
            HBITMAP decoded=jpg_to_bmp(&jpeg[0],(int)jpeg.size());
            if (decoded) {
                bool replaced=media_chat_upgrade_photo_in_place(
                    document,decoded);
                DeleteObject(decoded);
                if (replaced) {
                    media_chat_v81_mark_photo_full(document);
                    diag_log("concept98 v101 full photo restored from cache");
                    return true;
                }
            }
        }
    }

    bool same_active =''',1)
# Store only fully decoded JPEG data; no speculative low-quality thumbnail.
marker=r'''            if (replaced) {
                media_chat_v81_mark_photo_full(
                    &documents[target]
                );'''
if marker not in s:raise SystemExit("Full-photo completion marker unavailable")
s=s.replace(marker,r'''            if (replaced) {
                concept98_full_photo_save_v101(
                    media_chat_full_photo_id,
                    media_chat_full_photo_access_hash,
                    media_chat_full_photo_bytes
                );
                media_chat_v81_mark_photo_full(
                    &documents[target]
                );''',1)
# Avoid falsely declaring a photo full in another chat merely because a
# deque Document address was re-used and its media id matched.
marker='        media_chat_animated_sticker_clear();\n        concept98_bootstrap_begin_v100(hWnd);'
if marker not in s:raise SystemExit("Peer switch hook unavailable")
s=s.replace(marker,'        media_chat_animated_sticker_clear();\n'
                   '        media_chat_v86_loaded_full_instances.clear();\n'
                   '        concept98_bootstrap_begin_v100(hWnd);',1)

p.write_text(s,encoding="latin-1",newline="\r\n")
for m in ["concept98_full_photo_cache_v101","concept98_full_photo_load_v101",
          "concept98_full_photo_save_v101","concept98 v101 full photo restored"]:
    if m not in s:raise SystemExit("v10.1 check missing "+m)
print("Concept98 v10.1: reuse decoded full JPEG with exact OLE identity, "
      "account-scoped bounded disk cache, no stale full flag across chat switch.")
