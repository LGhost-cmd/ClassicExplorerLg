#!/usr/bin/env python3
"""Concept98 v10.2: deliberate sixteen-pixel classic Windows-style toolbar art.

Pixel patterns are original GDI artwork informed by period icon design
rather than redistributed Microsoft/Tumblr images.
"""
from pathlib import Path
import sys
if len(sys.argv)!=2:raise SystemExit("Usage: patch_concept98_visual_finish_v102.py <src>")
p=Path(sys.argv[1]).resolve()/"src"/"telegacy.cpp"
s=p.read_text(encoding="latin-1")
if "concept98_visual_finish_v102" in s:
    print("v10.2 already applied");raise SystemExit(0)
if "concept98_full_photo_cache_v101" not in s:
    raise SystemExit("v10.1 prerequisite missing")
a=s.find("static void concept98_pixel_glyph_v95(")
b=s.find("static bool concept98_action_button_v95(",a)
if a<0 or b<0:raise SystemExit("Owner-drawn classic action bar missing")
new=r'''// concept98_visual_finish_v102
// Source references for the silhouette vocabulary:
// oldwindowsicons.tumblr.com (Windows 95/98 Explorer, Saved Search,
// Notepad, Control Panel, ICQ). No external icon data included.
static void concept98_pixel_glyph_v95(HDC dc,int x,int y,int id) {
    static const char* search[16]={
        "................",
        "....KKKKK.......",
        "...KWWWWWK......",
        "..KWWWWWBBK.....",
        "..KWCCCCBBK.....",
        ".KWCCCCCCBK.....",
        ".KWCWCCCBK......",
        ".KWWCCCBBK......",
        "..KWWBBBK.......",
        "...KBBBK........",
        "....KKKSK.......",
        "......KSKK......",
        ".......KSSK.....",
        "........KSSK....",
        ".........KKK....",
        "................"
    };
    static const char* profile[16]={
        "................",
        "..KKKKKKKKKK....",
        ".KWBBBBBBBBBK...",
        ".KBYYYYYYBBBK...",
        ".KBYYKKYYBBBK...",
        ".KBYYRRYYBBBK...",
        ".KBBBRRBBBBBK...",
        ".KBBBKKBBBBBK...",
        ".KBSSSSSSSBBK...",
        ".KBSKSSSKSBBK...",
        ".KBSSSSSSSBBK...",
        ".KBBBBBBBBBBK...",
        ".KBBBBBBBBBBK...",
        ".KWWWWWWWWWWK...",
        "..KKKKKKKKKK....",
        "................"
    };
    static const char* options[16]={
        "................",
        "......KKKK......",
        ".....KSSSSK.....",
        "..KKKSGGSGKKK...",
        ".KWWWKSSKWWWK...",
        ".KWCCKKKKCCWK...",
        ".KWCSKYYKSCWK...",
        ".KWCWKKKKWCWK...",
        ".KWCSKYYKSCWK...",
        ".KWCCKKKKCCWK...",
        ".KWWWKSSKWWWK...",
        "..KKKSGGSGKKK...",
        ".....KSSSSK.....",
        "......KKKK......",
        "................",
        "................"
    };
    const char** sprite=id==8912?search:(id==8913?profile:options);
    for (int row=0;row<16;row++) {
        const char* line=sprite[row];
        for (int col=0;col<16 && line[col];col++) {
            COLORREF color=0;
            switch(line[col]) {
            case 'K': color=RGB(24,34,47);break;
            case 'W': color=RGB(250,250,247);break;
            case 'B': color=RGB(66,109,157);break;
            case 'C': color=RGB(146,197,219);break;
            case 'S': color=RGB(113,122,139);break;
            case 'Y': color=RGB(228,199,120);break;
            case 'R': color=RGB(185,111,95);break;
            case 'G': color=RGB(104,145,95);break;
            default:continue;
            }
            SetPixelV(dc,x+col,y+row,color);
        }
    }
}

'''
s=s[:a]+new+s[b:]
old="concept98_pixel_glyph_v95(dc,rc.left+6+ofs,rc.top+5+ofs,id);"
if old not in s:raise SystemExit("Action icon viewport missing")
s=s.replace(old,"concept98_pixel_glyph_v95(dc,rc.left+5+ofs,rc.top+5+ofs,id);",1)
old='    RECT text={rc.left+25+ofs,rc.top+2+ofs,'
if old not in s:raise SystemExit("Button text spacing missing")
s=s.replace(old,'    RECT text={rc.left+23+ofs,rc.top+2+ofs,',1)
# Brand title is subdued period software identity, not a giant empty banner.
old='L"TELEGACY  /  TELEGRAM 98",'
if old not in s:raise SystemExit("Brand label unavailable")
s=s.replace(old,'L"Telegacy 98  |  Telegram Client",',1)
# For compact screens, the text labels remain fully legible with 16px icons.
# Avoid rendering duplicate system shadows over bitmap transparency.
p.write_text(s,encoding="latin-1",newline="\r\n")
for token in ("concept98_visual_finish_v102","oldwindowsicons.tumblr.com",
              "static const char* profile[16]","SetPixelV(dc,x+col,y+row,color)"):
    if token not in s:raise SystemExit("v10.2 missing "+token)
print("Concept98 v10.2: new original pixel-perfect multicolour 16px toolbar "
      "sprites with Windows 95/98-inspired drawing, consistent bevel/spacing.")
