#!/usr/bin/env python3
"""Concept 98 v9.5: native pixel-art action glyphs without bundled IP assets."""
from pathlib import Path
import sys
if len(sys.argv)!=2:
    raise SystemExit("Usage: patch_concept98_pixel_icons_v95.py <Telegacy src>")
p=Path(sys.argv[1]).resolve()/"src"/"telegacy.cpp"
s=p.read_text(encoding="latin-1")
if "concept98_pixel_icons_v95" in s:
    print("Concept 98 pixels already applied");raise SystemExit(0)
if "concept98_sticker_anchors_v94" not in s:
    raise SystemExit("Concept 98 v9.4 is required")
anchor="static bool concept98_draw_row("
if anchor not in s: raise SystemExit("Could not locate row drawer")
icons=r'''// concept98_pixel_icons_v95: original 16x16 GDI pixel glyphs referencing
// the classic search/contact/control-panel silhouette, not copied assets.
static void concept98_pixel_glyph_v95(
    HDC dc, int x, int y, int id
) {
    COLORREF ink=RGB(32,32,48);
    COLORREF rim=RGB(250,250,249);
    COLORREF fill=RGB(90,143,182);
    HPEN dark=CreatePen(PS_SOLID,1,ink);
    HPEN highlight=CreatePen(PS_SOLID,1,rim);
    HBRUSH face=CreateSolidBrush(fill);
    HGDIOBJ oldp=SelectObject(dc,dark);
    HGDIOBJ oldb=SelectObject(dc,face);

    if (id==8912) {
        // Magnifier: a bevelled glass, short diagonal handle.
        Ellipse(dc,x+2,y+1,x+11,y+10);
        SelectObject(dc,highlight);
        MoveToEx(dc,x+4,y+3,NULL);
        LineTo(dc,x+7,y+3);
        SelectObject(dc,dark);
        MoveToEx(dc,x+10,y+9,NULL);LineTo(dc,x+15,y+14);
        MoveToEx(dc,x+9,y+10,NULL);LineTo(dc,x+13,y+15);
    } else if (id==8913) {
        // Two-colour contact portrait, familiar 1990s address-book motif.
        Ellipse(dc,x+5,y+1,x+11,y+8);
        Rectangle(dc,x+3,y+9,x+13,y+15);
        SelectObject(dc,highlight);
        MoveToEx(dc,x+5,y+10,NULL);
        LineTo(dc,x+10,y+10);
    } else {
        // Small control panel/cog with square punched details.
        Rectangle(dc,x+3,y+3,x+13,y+13);
        SelectObject(dc,highlight);
        MoveToEx(dc,x+5,y+5,NULL);LineTo(dc,x+10,y+5);
        SelectObject(dc,dark);
        MoveToEx(dc,x+1,y+8,NULL);LineTo(dc,x+15,y+8);
        MoveToEx(dc,x+8,y+1,NULL);LineTo(dc,x+8,y+15);
        Rectangle(dc,x+6,y+6,x+10,y+10);
    }

    SelectObject(dc,oldp);
    SelectObject(dc,oldb);
    DeleteObject(dark);
    DeleteObject(highlight);
    DeleteObject(face);
}

static bool concept98_action_button_v95(
    const DRAWITEMSTRUCT* dis
) {
    if (!dis) return false;
    int id=(int)dis->CtlID;
    if (id!=8912 && id!=8913 && id!=8914) return false;

    HDC dc=dis->hDC;
    RECT rc=dis->rcItem;
    UINT state=DFCS_BUTTONPUSH;
    if (dis->itemState & ODS_SELECTED) state |= DFCS_PUSHED;
    if (dis->itemState & ODS_DISABLED) state |= DFCS_INACTIVE;
    DrawFrameControl(dc,&rc,DFC_BUTTON,state);

    const wchar_t* caption=id==8912
        ? L"\x041f\x043e\x0438\x0441\x043a"
        : id==8913 ? L"\x041f\x0440\x043e\x0444\x0438\x043b\x044c"
                   : L"\x0415\x0449\x0451...";
    int ofs=(dis->itemState & ODS_SELECTED) ? 1 : 0;
    concept98_pixel_glyph_v95(dc,rc.left+6+ofs,rc.top+5+ofs,id);

    RECT text={rc.left+25+ofs,rc.top+2+ofs,
               rc.right-4+ofs,rc.bottom-3+ofs};
    int oldmode=SetBkMode(dc,TRANSPARENT);
    COLORREF oldcolor=SetTextColor(
        dc,GetSysColor(
            dis->itemState & ODS_DISABLED
               ? COLOR_GRAYTEXT : COLOR_BTNTEXT
        )
    );
    HFONT oldfont=(HFONT)SelectObject(dc,hFonts[2]);
    DrawTextW(dc,caption,-1,&text,DT_SINGLELINE|DT_VCENTER|DT_CENTER);
    SelectObject(dc,oldfont);
    SetTextColor(dc,oldcolor);
    SetBkMode(dc,oldmode);
    if (dis->itemState & ODS_FOCUS) {
        RECT focus=rc;
        InflateRect(&focus,-3,-3);
        DrawFocusRect(dc,&focus);
    }
    return true;
}

'''
s=s.replace(anchor,icons+anchor,1)
target='panel | BS_PUSHBUTTON, 0,0,88,27'
if s.count(target)!=3:raise SystemExit("Unexpected button style count: "+str(s.count(target)))
s=s.replace(target,'panel | BS_OWNERDRAW, 0,0,88,27')
old='if (concept98_enabled && concept98_draw_row(lpdis)) return TRUE;'
if old not in s:raise SystemExit("WM_DRAWITEM handler missing")
s=s.replace(old,'if (concept98_enabled && concept98_action_button_v95(lpdis)) return TRUE;\n\t\t'+old,1)
p.write_text(s,encoding="latin-1",newline="\r\n")
for marker in ("concept98_pixel_icons_v95","concept98_action_button_v95",
               "panel | BS_OWNERDRAW","concept98_pixel_glyph_v95"):
    if marker not in s: raise SystemExit("v9.5 marker missing "+marker)
print("Concept 98 v9.5: three native owner-drawn search/profile/options "
      "pixel icons, scale-consistent with classic Windows bevelled buttons.")
