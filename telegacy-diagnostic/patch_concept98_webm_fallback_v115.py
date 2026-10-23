#!/usr/bin/env python3
"""Concept98 v11.5: robust, static WebM poster fallback + decode diagnostics.
MF first-frame is preferred; when its decoder is missing, request a Windows
Shell video thumbnail from the *downloaded local file*, never paint a child
video window. Preserve strict RichEdit target safety.
"""
from pathlib import Path
import sys
if len(sys.argv)!=2:raise SystemExit("Usage: patch_concept98_webm_fallback_v115.py <src>")
p=Path(sys.argv[1]).resolve()/"src"/"telegacy.cpp"
s=p.read_text(encoding="latin-1")
if "concept98_sticker_first_frame_v109" not in s:raise SystemExit("requires v10.9")
if "concept98_webm_fallback_v115" in s:raise SystemExit(0)
anchor="static HBITMAP concept98_sticker_first_webm_v109(const wchar_t* path) {"
if s.count(anchor)!=1:raise SystemExit("webm entry changed")
# Shell thumbnail is a fallback, never the primary decoder: Windows chooses the
# representative frame, not necessarily frame zero. MF always tries frame 0.
helper=r'''
// concept98_webm_fallback_v115
static HBITMAP concept98_shell_webm_poster_v115(const wchar_t* path) {
    if (!path || !*path) return NULL;
    IShellItemImageFactory* factory=NULL;
    HBITMAP bitmap=NULL;
    HRESULT hr=SHCreateItemFromParsingName(path,NULL,
                 IID_PPV_ARGS(&factory));
    if(SUCCEEDED(hr)&&factory){
        SIZE size={160,160};
        hr=factory->GetImage(size,SIIGBF_THUMBNAILONLY|SIIGBF_BIGGERSIZEOK,
                            &bitmap);
        factory->Release();
    }
    diag_log("concept98 v115 WebM Shell poster hr=0x%08X image=%d",
             (unsigned)hr,bitmap!=NULL);
    return bitmap;
}
'''
s=s.replace(anchor,helper+"\n"+anchor,1)
# SourceReader metadata errors must be recorded to distinguish missing codecs
# from missing files and invalid OLE anchors. Do not convert errors to GDI flashes.
start=s.index(anchor)
end=s.index("static bool concept98_sticker_commit_frame_v109(",start)
f=s[start:end]
old='''    HRESULT hr=MFStartup(MF_VERSION);
    if(FAILED(hr))return NULL;'''
new='''    HRESULT hr=MFStartup(MF_VERSION);
    if(FAILED(hr)) {
        diag_log("concept98 v115 WebM MFStartup hr=0x%08X",(unsigned)hr);
        return concept98_shell_webm_poster_v115(path);
    }'''
if f.count(old)!=1:raise SystemExit("MFStartup gate missing")
f=f.replace(old,new,1)
# Log the stage of MF failure, while preserving original lifetime cleanup.
f=f.replace('''    HBITMAP result=NULL;
    do {''','''    HBITMAP result=NULL;
    const char* step="open";
    do {''',1)
for a,b in [
('hr=MFCreateSourceReaderFromURL(path,NULL,&reader);','step="open";hr=MFCreateSourceReaderFromURL(path,NULL,&reader);'),
('hr=MFCreateMediaType(&requested);','step="media-type";hr=MFCreateMediaType(&requested);'),
('hr=reader->SetCurrentMediaType(','step="RGB32-converter";hr=reader->SetCurrentMediaType('),
('hr=reader->GetCurrentMediaType(','step="current-video-format";hr=reader->GetCurrentMediaType('),
('hr=MFGetAttributeSize(actual,MF_MT_FRAME_SIZE,&w,&h);','step="video-dimensions";hr=MFGetAttributeSize(actual,MF_MT_FRAME_SIZE,&w,&h);'),
('hr=reader->ReadSample(','step="first-sample";hr=reader->ReadSample('),
('hr=sample->ConvertToContiguousBuffer(&buffer);','step="sample-buffer";hr=sample->ConvertToContiguousBuffer(&buffer);')
]:
    if f.count(a)!=1:raise SystemExit("MF stage missing "+a)
    f=f.replace(a,b,1)
last='''    MFShutdown();
    return result;'''
repl='''    MFShutdown();
    if (!result) {
        diag_log("concept98 v115 WebM MF failed stage=%s hr=0x%08X file=%ls",
                 step,(unsigned)hr,path);
        result=concept98_shell_webm_poster_v115(path);
    } else diag_log("concept98 v115 WebM first frame decoded by MF");
    return result;'''
if f.count(last)!=1:raise SystemExit("MF result marker missing")
f=f.replace(last,repl,1)
s=s[:start]+f+s[end:]
# Track whether fallback was decoded but rejected by stale/inaccurate OLE.
old='''    if(cp<0||abs(cp-document->min)>1||
       !media_chat_v87_exact_bitmap_at_cp(cp))return false;'''
new='''    if(cp<0||abs(cp-document->min)>1||
       !media_chat_v87_exact_bitmap_at_cp(cp)) {
        diag_log("concept98 v115 sticker OLE rejected cp=%d min=%d",
                 cp,document->min);
        return false;
    }'''
if s.count(old)!=1:raise SystemExit("WebM commit guard changed")
s=s.replace(old,new,1)
# Add the Shell COM types, library already in the official CMakeLists.txt.
if '#include <shobjidl.h>' not in s:
    s='#include <shobjidl.h>\n'+s
p.write_text(s,encoding="latin-1",newline="\r\n")
print("Concept98 v11.5: WebM first frame through Media Foundation, Shell static thumbnail fallback, error-stage logs.")
