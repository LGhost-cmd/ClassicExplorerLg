#!/usr/bin/env python3
"""Concept98 v12.9: open sender profile only when clicking the actual glyph bounds.
Do not let quote/forward context, whitespace, or message text trigger profile.
"""
from pathlib import Path
import sys
if len(sys.argv)!=2:raise SystemExit("Usage: patch_concept98_nickname_hit_v129.py <src>")
p=Path(sys.argv[1]).resolve()/"src"/"procs.cpp"
s=p.read_text(encoding="latin-1")
if "concept98_nickname_hit_v129" in s:raise SystemExit(0)
needle='''        for (int i = (int)messages.size() - 1; i >= 0; i--) {
            if (
                character >= messages[i].start_char &&
                character < messages[i].end_header
            ) {
                Peer* sender = profile_nav_sender_for_message(messages[i].id);'''
repl='''        for (int i = (int)messages.size() - 1; i >= 0; i--) {
            if (
                character >= messages[i].start_char &&
                character < messages[i].end_header
            ) {
                // concept98_nickname_hit_v129: end_header includes quote,
                // forward context and newlines. Only the visible name glyphs
                // are an active profile link.
                int first=messages[i].start_char;
                int limit=messages[i].end_header;
                if(limit-first>160)limit=first+160;
                if(limit<=first)break;
                wchar_t name[164]={0};
                TEXTRANGEW tr={0};
                tr.chrg.cpMin=first;
                tr.chrg.cpMax=limit;
                tr.lpstrText=name;
                LRESULT got=SendMessageW(hWnd,EM_GETTEXTRANGE,0,(LPARAM)&tr);
                if(got<=0)break;
                name[got<162?got:162]=0;
                int name_len=0;
                while(name_len<got && name[name_len]!=L':' &&
                      name[name_len]!=L'\\n' && name[name_len]!=L'\\r')
                    name_len++;
                if(name_len<=0 || character>=first+name_len)break;
                POINTL a={0},z={0};
                SendMessageW(hWnd,EM_POSFROMCHAR,(WPARAM)&a,first);
                SendMessageW(hWnd,EM_POSFROMCHAR,(WPARAM)&z,first+name_len);
                int x0=(int)a.x,x1=(int)z.x;
                if(x1<x0){int t=x0;x0=x1;x1=t;}
                // RichEdit may snap clicks in blank space to the nearest
                // character. Check the PIXEL rect too, not only the char.
                HDC dc=GetDC(hWnd);
                int glyph_h=16;
                if(dc){
                    HGDIOBJ prev=SelectObject(dc,hFonts[0]);
                    TEXTMETRICW tm={0};
                    if(GetTextMetricsW(dc,&tm))glyph_h=tm.tmHeight+tm.tmExternalLeading;
                    SelectObject(dc,prev);
                    ReleaseDC(hWnd,dc);
                }
                if(point.x<x0-2 || point.x>x1+2 ||
                   point.y<(int)a.y-2 || point.y>(int)a.y+glyph_h+3)
                    break;
                Peer* sender = profile_nav_sender_for_message(messages[i].id);'''
if s.count(needle)!=1:raise SystemExit("v12.9: original profile click block not found once: "+str(s.count(needle)))
s=s.replace(needle,repl,1)
p.write_text(s,encoding="latin-1",newline="\r\n")
print("v12.9: exact nickname glyph hit; inactive whitespace and quote area.")
