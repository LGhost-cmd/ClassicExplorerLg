#!/usr/bin/env python3
"""v10.9: animated TGS / WebM sticker -> static first frame in RichEdit.
No child HWND/player: first-frame bitmap replaces its own square OLE anchor.
"""
from pathlib import Path
import sys
if len(sys.argv)!=2: raise SystemExit("Usage: patch_concept98_sticker_first_frame_v109.py <src>")
p=Path(sys.argv[1]).resolve()/"src"/"telegacy.cpp"
s=p.read_text(encoding="latin-1")
if "concept98_sticker_first_frame_v109" in s:
    print("v10.9 already applied"); raise SystemExit(0)
if "concept98_auto_full_photo_pump_v106" not in s:
    raise SystemExit("Requires v10.8")
anchor="static void media_chat_sticker_activate(\n    Document* document,\n    const wchar_t* path\n) {"
if s.count(anchor)!=1:raise SystemExit("Cannot find sticker activation")
helpers=r'''
// concept98_sticker_first_frame_v109
// Media Foundation source reader is used only to decode ONE sample, no video
// child windows are created. TGS similarly renders rlottie frame 0 only.
static HBITMAP concept98_sticker_bitmap_v109(
    const unsigned int* pixels, int w,int h
) {
    if (!pixels || w<=0 || h<=0 || w>4096 || h>4096) return NULL;
    int side=media_chat_sticker_card_width();
    if (side<=0 || side>1024) return NULL;
    BITMAPINFO info={0};
    info.bmiHeader.biSize=sizeof(BITMAPINFOHEADER);
    info.bmiHeader.biWidth=side;
    info.bmiHeader.biHeight=-side;
    info.bmiHeader.biPlanes=1;
    info.bmiHeader.biBitCount=32;
    info.bmiHeader.biCompression=BI_RGB;
    HDC dc=GetDC(chat);
    void* bits=NULL;
    HBITMAP bmp=CreateDIBSection(dc,&info,DIB_RGB_COLORS,&bits,NULL,0);
    if(dc)ReleaseDC(chat,dc);
    if(!bmp || !bits){if(bmp)DeleteObject(bmp);return NULL;}
    unsigned int* out=(unsigned int*)bits;
    COLORREF bg=GetSysColor(COLOR_WINDOW);
    unsigned int bgpixel=(GetRValue(bg)<<16)|
                         (GetGValue(bg)<<8)|GetBValue(bg);
    for(int i=0;i<side*side;i++)out[i]=bgpixel;
    // Letterbox rather than stretching a nonsquare animation to a square.
    int tw=side,th=side;
    if(w>h)th=(int)((__int64)side*h/w);
    else if(h>w)tw=(int)((__int64)side*w/h);
    if(tw<1)tw=1;if(th<1)th=1;
    int x0=(side-tw)/2,y0=(side-th)/2;
    for(int y=0;y<th;y++){
        int sy=(int)((__int64)y*h/th);
        for(int x=0;x<tw;x++){
            int sx=(int)((__int64)x*w/tw);
            out[(y0+y)*side+(x0+x)]=pixels[sy*w+sx]&0xFFFFFF;
        }
    }
    return bmp;
}
static HBITMAP concept98_sticker_first_tgs_v109(
    Document* document,const wchar_t* path
) {
    ChatAnimatedSticker item={};
    item.kind=1;
    item.anchor_min=document->min;
    memcpy(item.id,document->id,8);
    wcsncpy_s(item.path,ARRAYSIZE(item.path),path,_TRUNCATE);
    if(!media_chat_sticker_load_lottie(&item) || !item.lottie){
        if(item.lottie)delete item.lottie;
        return NULL;
    }
    int w=media_chat_sticker_card_width();
    int h=media_chat_sticker_card_height();
    std::vector<unsigned int> pixels((size_t)w*h,0);
    rlottie::Surface surface(&pixels[0],w,h,w*4);
    item.lottie->renderSync(0,surface,true);
    delete item.lottie;
    COLORREF bg=GetSysColor(COLOR_WINDOW);
    unsigned int br=GetRValue(bg),bgc=GetGValue(bg),bb=GetBValue(bg);
    for(size_t i=0;i<pixels.size();i++){
        unsigned int v=pixels[i],a=v>>24,iv=255-a;
        unsigned int r=((v>>16&255)*a+br*iv)/255;
        unsigned int g=((v>>8&255)*a+bgc*iv)/255;
        unsigned int b=((v&255)*a+bb*iv)/255;
        pixels[i]=(r<<16)|(g<<8)|b;
    }
    return concept98_sticker_bitmap_v109(&pixels[0],w,h);
}
static HBITMAP concept98_sticker_first_webm_v109(const wchar_t* path) {
    // Unlike MFPlay, SourceReader produces pixel data without an HWND.
    HRESULT hr=MFStartup(MF_VERSION);
    if(FAILED(hr))return NULL;
    IMFSourceReader* reader=NULL;
    IMFMediaType* requested=NULL;
    IMFMediaType* actual=NULL;
    IMFSample* sample=NULL;
    IMFMediaBuffer* buffer=NULL;
    IMF2DBuffer* plane=NULL;
    HBITMAP result=NULL;
    do {
        hr=MFCreateSourceReaderFromURL(path,NULL,&reader);
        if(FAILED(hr)||!reader)break;
        hr=MFCreateMediaType(&requested);
        if(FAILED(hr)||!requested)break;
        requested->SetGUID(MF_MT_MAJOR_TYPE,MFMediaType_Video);
        requested->SetGUID(MF_MT_SUBTYPE,MFVideoFormat_RGB32);
        hr=reader->SetCurrentMediaType(
            MF_SOURCE_READER_FIRST_VIDEO_STREAM,NULL,requested);
        if(FAILED(hr))break;
        hr=reader->GetCurrentMediaType(
            MF_SOURCE_READER_FIRST_VIDEO_STREAM,&actual);
        if(FAILED(hr)||!actual)break;
        UINT32 w=0,h=0;
        hr=MFGetAttributeSize(actual,MF_MT_FRAME_SIZE,&w,&h);
        if(FAILED(hr)||!w||!h||w>4096||h>4096)break;
        for(int i=0;i<16;i++){
            DWORD stream=0,flags=0;LONGLONG time=0;
            hr=reader->ReadSample(
                MF_SOURCE_READER_FIRST_VIDEO_STREAM,0,
                &stream,&flags,&time,&sample);
            if(FAILED(hr)||(flags&MF_SOURCE_READERF_ENDOFSTREAM))break;
            if(sample)break;
        }
        if(!sample)break;
        hr=sample->ConvertToContiguousBuffer(&buffer);
        if(FAILED(hr)||!buffer)break;
        BYTE* scan=NULL;
        LONG stride=(LONG)(w*4);
        bool locked2d=false;
        if(SUCCEEDED(buffer->QueryInterface(
                IID_PPV_ARGS(&plane)))&&plane){
            locked2d=SUCCEEDED(plane->Lock2D(&scan,&stride));
        }
        DWORD maxbytes=0,currentbytes=0;
        bool lockedplain=false;
        if(!locked2d){
            lockedplain=SUCCEEDED(
                buffer->Lock(&scan,&maxbytes,&currentbytes));
            stride=(LONG)(w*4);
            if(lockedplain && currentbytes<(size_t)stride*h){
                buffer->Unlock();lockedplain=false;scan=NULL;
            }
        }
        if(scan){
            std::vector<unsigned int> pixels((size_t)w*h,0);
            for(UINT32 y=0;y<h;y++){
                BYTE* line=scan+(ptrdiff_t)y*stride;
                for(UINT32 x=0;x<w;x++){
                    BYTE* p=line+x*4;
                    pixels[(size_t)y*w+x]=
                        ((unsigned int)p[2]<<16)|
                        ((unsigned int)p[1]<<8)|p[0];
                }
            }
            result=concept98_sticker_bitmap_v109(
                &pixels[0],(int)w,(int)h);
        }
        if(locked2d)plane->Unlock2D();
        if(lockedplain)buffer->Unlock();
    }while(false);
    if(plane)plane->Release();
    if(buffer)buffer->Release();
    if(sample)sample->Release();
    if(actual)actual->Release();
    if(requested)requested->Release();
    if(reader)reader->Release();
    MFShutdown();
    return result;
}
static bool concept98_sticker_commit_frame_v109(
    Document* document,HBITMAP bitmap
) {
    if(!document||!bitmap||!chat)return false;
    int cp=media_chat_sticker_find_ole_cp(document);
    if(cp<0||abs(cp-document->min)>1||
       !media_chat_v87_exact_bitmap_at_cp(cp))return false;
    CHARRANGE old={0};POINT scroll={0,0};
    SendMessageW(chat,EM_EXGETSEL,0,(LPARAM)&old);
    BOOL has_scroll=(BOOL)SendMessageW(chat,EM_GETSCROLLPOS,0,(LPARAM)&scroll);
    bool redraw=drawchat;
    if(redraw)SendMessageW(chat,WM_SETREDRAW,FALSE,0);
    SendMessageW(chat,EM_SETSEL,cp,cp+1);
    SendMessageW(chat,EM_REPLACESEL,FALSE,(LPARAM)L"");
    insert_image(chat,NULL,bitmap);
    document->min=cp;document->max=cp+1;
    SendMessageW(chat,EM_EXSETSEL,0,(LPARAM)&old);
    if(has_scroll)SendMessageW(chat,EM_SETSCROLLPOS,0,(LPARAM)&scroll);
    if(redraw){
        SendMessageW(chat,WM_SETREDRAW,TRUE,0);
        InvalidateRect(chat,NULL,FALSE);
    }
    return true;
}
'''
s=s.replace(anchor,helpers+"\n"+anchor,1)
needle='''    if (kind == 3) {
        if (
            !media_chat_sticker_commit_webp_v86('''
if s.count(needle)!=1:raise SystemExit("Static WebP branch missing")
s=s.replace(needle,r'''    if (kind==1 || kind==2) {
        HBITMAP first=kind==1
            ? concept98_sticker_first_tgs_v109(document,path)
            : concept98_sticker_first_webm_v109(path);
        bool committed=first &&
            concept98_sticker_commit_frame_v109(document,first);
        if(first)DeleteObject(first);
        diag_log("concept98 v109 sticker frame kind=%d committed=%d",
                 kind,committed?1:0);
        // Do not create MFPlay/child overlay when first-frame decode fails.
        // Telegram's normal bitmap thumbnail can still replace the anchor.
        return;
    }

'''+needle,1)
if "#include <mfreadwrite.h>" not in s:
    s='#include <mfapi.h>\n#include <mfidl.h>\n#include <mfreadwrite.h>\n#pragma comment(lib, "mfplat.lib")\n#pragma comment(lib, "mfreadwrite.lib")\n#pragma comment(lib, "mfuuid.lib")\n'+s
p.write_text(s,encoding="latin-1",newline="\r\n")
print("v10.9: TGS frame 0 and Media Foundation WebM first frame committed as static OLE; no child video windows.")
