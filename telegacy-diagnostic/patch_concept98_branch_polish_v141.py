#!/usr/bin/env python3
"""Concept98 v14.1: compact quotations, sender names for fetched ancestors,
and actual cached Telegram JPEG embedded in a missing-history reply card."""
from pathlib import Path
import sys
if len(sys.argv)!=2:raise SystemExit("Usage: patch_concept98_branch_polish_v141.py <src>")
path=Path(sys.argv[1]).resolve()/"src"/"telegacy.cpp"
s=path.read_text(encoding="latin-1")
if "concept98_branch_polish_v141" in s:raise SystemExit(0)
if "concept98_nested_cards_v140" not in s:raise SystemExit("v14.0 required")
def one(a,b,why):
 global s
 n=s.count(a)
 if n!=1:raise SystemExit("v14.1 "+why+" count="+str(n))
 s=s.replace(a,b,1)
one(r'''    std::wstring body;
    bool media;
    Concept98ReplySnapshot136():parent(0),media(false){}''',
'''    std::wstring body;
    std::wstring author; // concept98_branch_polish_v141
    BYTE photo_id[8],photo_hash[8];
    bool media;
    Concept98ReplySnapshot136():parent(0),media(false){
        memset(photo_id,0,sizeof(photo_id));
        memset(photo_hash,0,sizeof(photo_hash));
    }''',"message snapshot")
one(r'''    concept98_reply_note_v136(id,parent,text,(flags&(1u<<9))!=0);
    free(text);''',
r'''    concept98_reply_note_v136(id,parent,text,(flags&(1u<<9))!=0);
    Concept98ReplySnapshot136& snap=concept98_reply_nodes_v136[id];
    // Actual sender, if the returned Telegram message contains from_id.
    if((flags&(1u<<8)) && len>=28){
        const BYTE* sender=raw+20;
        if(memcmp(sender,myself.id,8)==0 && myself.name)
            snap.author=myself.name;
        else {
            for(int i=0;i<peers_count;i++)
                if(!memcmp(sender,peers[i].id,8) && peers[i].name){
                    snap.author=peers[i].name;break;
                }
        }
    }
    if(snap.author.empty() && current_peer->type==0 && current_peer->name)
        snap.author=current_peer->name;
    // Saved photo reference is scoped to this message, not to the
    // currently selected photo or neighbour RichEdit OLE.
    if((flags&(1u<<9)) && at+encoded+32<=len){
        const BYTE* media=raw+at+encoded;
        if(read_le((BYTE*)media,4)==0x695150d7 &&
           ((unsigned int)read_le((BYTE*)media+4,4)&1u)){
            memcpy(snap.photo_id,media+16,8);
            memcpy(snap.photo_hash,media+24,8);
        }
    }
    free(text);''',"retain sender and photo reference")
one(r'''        int content_height=has_media?310:115;''',
'''        // Compact text block; actual sticker/photo rows retain space for OLE.
        int content_height=has_media?264:75;''',"compact quotation")
one(r'''        const wchar_t* heading=depth?
            L"\x0412 \x043e\x0442\x0432\x0435\x0442 \x043d\x0430":
            L"\x0422\x0435\x043a\x0443\x0449\x0435\x0435 \x0441\x043e\x043e\x0431\x0449\x0435\x043d\x0438\x0435";
        HWND hTitle=CreateWindowExW(0,L"STATIC",heading,''',
r'''        std::wstring heading=depth?
            L"\x0412 \x043e\x0442\x0432\x0435\x0442 \x043d\x0430":
            L"\x0422\x0435\x043a\x0443\x0449\x0435\x0435 \x0441\x043e\x043e\x0431\x0449\x0435\x043d\x0438\x0435";
        if(ready && !it->second.author.empty()){
            heading+=L"  \x2014  ";
            heading+=it->second.author;
        }
        HWND hTitle=CreateWindowExW(0,L"STATIC",heading.c_str(),''',"author in heading")
# Decoded JPEG cache is genuinely the source photo; never substitute an
# unrelated placeholder or an image from a different ID.
one(r'''            if(!copied){
                std::wstring body;''',
r'''            if(!copied){
                bool cached_photo=false;
                if(ready &&
                   read_le((BYTE*)it->second.photo_id,8)!=0 &&
                   read_le((BYTE*)it->second.photo_hash,8)!=0){
                    Document doc={0};
                    memcpy(doc.id,it->second.photo_id,8);
                    memcpy(doc.access_hash,it->second.photo_hash,8);
                    std::vector<BYTE> jpeg;
                    if(concept98_full_photo_load_v101(&doc,&jpeg) &&
                       jpeg.size()>128){
                        HBITMAP decoded=jpg_to_bmp(&jpeg[0],(int)jpeg.size());
                        if(decoded){
                            BITMAP bm={0};GetObject(decoded,sizeof(bm),&bm);
                            int width=bm.bmWidth,height=bm.bmHeight;
                            if(width>0 && height>0){
                                double scale=min(260.0/width,205.0/height);
                                int w=max(1,(int)(width*scale));
                                int h=max(1,(int)(height*scale));
                                HDC screen=GetDC(NULL);
                                HDC src=CreateCompatibleDC(screen);
                                HDC dst=CreateCompatibleDC(screen);
                                HBITMAP small=CreateCompatibleBitmap(screen,w,h);
                                if(src && dst && small){
                                    HGDIOBJ a=SelectObject(src,decoded);
                                    HGDIOBJ b=SelectObject(dst,small);
                                    SetStretchBltMode(dst,HALFTONE);
                                    if(StretchBlt(dst,0,0,w,h,src,0,0,
                                                  width,height,SRCCOPY)){
                                        insert_image(c.rich,NULL,small);
                                        cached_photo=true;
                                    }
                                    SelectObject(src,a);SelectObject(dst,b);
                                }
                                if(small)DeleteObject(small);
                                if(src)DeleteDC(src);
                                if(dst)DeleteDC(dst);
                                if(screen)ReleaseDC(NULL,screen);
                            }
                            DeleteObject(decoded);
                        }
                    }
                }
                std::wstring body;''',"restore cached source photo")
one(r'''                    if(has_media){
                        if(!body.empty())body+=L"\r\n";
                        body+=L"\x0412\x043b\x043e\x0436\x0435\x043d\x0438\x0435 \x043f\x043e\x043b\x0443\x0447\x0435\x043d\x043e \x0438\x0437 Telegram";
                    }''',
r'''                    if(has_media && !cached_photo){
                        if(!body.empty())body+=L"\r\n";
                        body+=L"\x0412\x043b\x043e\x0436\x0435\x043d\x0438\x0435 \x0438\x0437 Telegram: \x043e\x0440\x0438\x0433\x0438\x043d\x0430\x043b \x043d\x0435 \x0437\x0430\x0433\x0440\u0443\u0436\u0435\u043d";
                    }''',"honest media status")
# The unescaped \\u marker above is raw literal C++ \\u0443, legal
# only in standard universal character escapes; leave it intact.
one(r'''                SendMessageW(c.rich,WM_SETTEXT,0,(LPARAM)body.c_str());''',
'''                if(cached_photo){
                    SendMessageW(c.rich,EM_SETSEL,0,0);
                    if(!body.empty()){
                        body+=L"\\r\\n";
                        SendMessageW(c.rich,EM_REPLACESEL,FALSE,(LPARAM)body.c_str());
                    }
                }else
                    SendMessageW(c.rich,WM_SETTEXT,0,(LPARAM)body.c_str());''',
"keep cached photo before caption")
path.write_text(s,encoding="latin-1",newline="\r\n")
print("v14.1 compact Win98 nested quotations, actual sender and cached source photo.")
