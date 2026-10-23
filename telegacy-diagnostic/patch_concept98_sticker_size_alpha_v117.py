#!/usr/bin/env python3
"""Concept98 v11.7: one predictable sticker size for TGS, WebM and WebP.
GDI/OLE CF_BITMAP cannot preserve true alpha. Decode BGRA where available,
alpha-composite onto the current Telegacy chat background, then clear ONLY
black matte connected to all four corners (rounded sticker letterboxing).
"""
from pathlib import Path
import sys
if len(sys.argv)!=2:raise SystemExit("Usage: patch_concept98_sticker_size_alpha_v117.py <src>")
p=Path(sys.argv[1]).resolve()/"src"/"telegacy.cpp"
s=p.read_text(encoding="latin-1")
if "concept98_sticker_size_alpha_v117" in s:
    print("v11.7 already applied");raise SystemExit(0)
if "concept98_webm_fallback_v115" not in s:raise SystemExit("requires v11.5")
sig="static void media_chat_sticker_activate(\n    Document* document,\n    const wchar_t* path\n) {"
if s.count(sig)!=1:raise SystemExit("sticker activate position changed")
helpers=r'''
// concept98_sticker_size_alpha_v117
// Normalize fallback thumbnails before inserting into RichEdit, avoiding
// Shell-provided 512px bitmaps displayed as 512px stickers next to 180px ones.
static HBITMAP concept98_normalize_sticker_v117(HBITMAP incoming) {
    if(!incoming)return NULL;
    BITMAP src={0};
    if(!GetObjectW(incoming,sizeof(src),&src) ||
       src.bmWidth<1||src.bmHeight<1||
       src.bmWidth>4096||src.bmHeight>4096)return NULL;
    int side=media_chat_sticker_card_width();
    if(side<32||side>768)return NULL;
    BITMAPINFO sinfo={0};
    sinfo.bmiHeader.biSize=sizeof(BITMAPINFOHEADER);
    sinfo.bmiHeader.biWidth=src.bmWidth;
    sinfo.bmiHeader.biHeight=-src.bmHeight;
    sinfo.bmiHeader.biPlanes=1;
    sinfo.bmiHeader.biBitCount=32;
    sinfo.bmiHeader.biCompression=BI_RGB;
    std::vector<unsigned int> pixels((size_t)src.bmWidth*src.bmHeight,0);
    HDC screen=GetDC(NULL);
    if(!screen)return NULL;
    BOOL have=GetDIBits(screen,incoming,0,(UINT)src.bmHeight,
                        &pixels[0],&sinfo,DIB_RGB_COLORS);
    ReleaseDC(NULL,screen);
    if(!have)return NULL;
    size_t partial=0,transparent=0,opaque=0;
    for(size_t i=0;i<pixels.size();i++){
        BYTE a=(BYTE)(pixels[i]>>24);
        if(a==0)++transparent;
        else if(a==255)++opaque;
        else ++partial;
    }
    // BI_RGB sources frequently leave the high byte at zero.  Treat alpha
    // as genuine only when values mix or contain intermediate opacity.
    bool has_alpha=partial>0||(transparent>0 && opaque>0);
    COLORREF back=colors[1];
    unsigned int br=GetRValue(back),bg=GetGValue(back),bb=GetBValue(back);
    unsigned int paper=(br<<16)|(bg<<8)|bb;
    int tw=side,th=side;
    if(src.bmWidth>src.bmHeight)
        th=MulDiv(side,src.bmHeight,src.bmWidth);
    else if(src.bmHeight>src.bmWidth)
        tw=MulDiv(side,src.bmWidth,src.bmHeight);
    if(tw<1)tw=1;if(th<1)th=1;
    int x0=(side-tw)/2,y0=(side-th)/2;
    std::vector<unsigned int> out((size_t)side*side,paper);
    for(int y=0;y<th;y++){
        int sy=(int)((__int64)y*src.bmHeight/th);
        for(int x=0;x<tw;x++){
            int sx=(int)((__int64)x*src.bmWidth/tw);
            unsigned int pixel=pixels[(size_t)sy*src.bmWidth+sx];
            unsigned int a=has_alpha?(pixel>>24):255;
            unsigned int r=(pixel>>16)&255,g=(pixel>>8)&255,b=pixel&255;
            out[(size_t)(y0+y)*side+(x0+x)]=
                (((r*a+br*(255-a))/255)<<16) |
                (((g*a+bg*(255-a))/255)<<8) |
                ((b*a+bb*(255-a))/255);
        }
    }
    // Windows Shell video thumbnails sometimes contain black outside the
    // rounded sticker. Remove ONLY near-black pixels contiguous with corners.
    // Abort the cleanup if the region is mostly black (real dark sticker).
    const int corners[4]={0,side-1,side*(side-1),side*side-1};
    bool black_corners=true;
    for(int i=0;i<4;i++){
        unsigned int v=out[corners[i]];
        if(((v>>16)&255)>24||((v>>8)&255)>24||(v&255)>24)
            black_corners=false;
    }
    if(black_corners && !has_alpha){
        std::vector<unsigned char> seen((size_t)side*side,0);
        std::vector<int> queue;
        queue.reserve(side*side/4);
        for(int i=0;i<4;i++){queue.push_back(corners[i]);seen[corners[i]]=1;}
        for(size_t head=0;head<queue.size();head++){
            int pos=queue[head],x=pos%side,y=pos/side;
            int adj[4]={pos-1,pos+1,pos-side,pos+side};
            for(int d=0;d<4;d++){
                if((d==0&&x==0)||(d==1&&x==side-1)||
                   (d==2&&y==0)||(d==3&&y==side-1))continue;
                int next=adj[d];
                if(seen[next])continue;
                unsigned int v=out[next];
                if(((v>>16)&255)>24||((v>>8)&255)>24||(v&255)>24)
                    continue;
                seen[next]=1;queue.push_back(next);
            }
            if(queue.size()>(size_t)side*side/3)break;
        }
        if(queue.size()<=(size_t)side*side/3)
            for(size_t k=0;k<queue.size();k++)out[queue[k]]=paper;
    }
    BITMAPINFO dinfo={0};
    dinfo.bmiHeader.biSize=sizeof(BITMAPINFOHEADER);
    dinfo.bmiHeader.biWidth=side;
    dinfo.bmiHeader.biHeight=-side;
    dinfo.bmiHeader.biPlanes=1;
    dinfo.bmiHeader.biBitCount=32;
    dinfo.bmiHeader.biCompression=BI_RGB;
    void* ptr=NULL;
    HDC dc=GetDC(chat);
    HBITMAP final=CreateDIBSection(dc,&dinfo,DIB_RGB_COLORS,&ptr,NULL,0);
    if(dc)ReleaseDC(chat,dc);
    if(!final||!ptr){if(final)DeleteObject(final);return NULL;}
    memcpy(ptr,&out[0],out.size()*sizeof(unsigned int));
    diag_log("concept98 v117 sticker normalized %dx%d to %dx%d alpha=%d",
             src.bmWidth,src.bmHeight,side,side,has_alpha?1:0);
    return final;
}
'''
s=s.replace(sig,helpers+"\n"+sig,1)
old=r'''        HBITMAP first=kind==1
            ? concept98_sticker_first_tgs_v109(document,path)
            : concept98_sticker_first_webm_v109(path);
        bool committed=first &&
            concept98_sticker_commit_frame_v109(document,first);
        if(first)DeleteObject(first);'''
new=r'''        HBITMAP first=kind==1
            ? concept98_sticker_first_tgs_v109(document,path)
            : concept98_sticker_first_webm_v109(path);
        // MF images and large Shell posters now share the same DPI-aware
        // 180px display dimensions and the selected chat background.
        HBITMAP normalized=concept98_normalize_sticker_v117(first);
        bool committed=normalized &&
            concept98_sticker_commit_frame_v109(document,normalized);
        if(normalized)DeleteObject(normalized);
        if(first)DeleteObject(first);'''
if s.count(old)!=1:raise SystemExit("sticker first-frame activation changed")
s=s.replace(old,new,1)
p.write_text(s,encoding="latin-1",newline="\r\n")
print("v11.7: WebM/TGS sizes normalized; alpha blended over Telegacy theme, bounded corner matte cleanup.")
