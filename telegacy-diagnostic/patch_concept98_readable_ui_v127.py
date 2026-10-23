#!/usr/bin/env python3
"""Concept98 v12.7: readable native notification, reliable shutdown and
two-sided Win98 chat formatting without changing the OLE/message offsets."""
from pathlib import Path
import sys
if len(sys.argv)!=2:raise SystemExit("Usage: patch_concept98_readable_ui_v127.py <src>")
root=Path(sys.argv[1]).resolve()
p={key:root/"src"/(key+".cpp") for key in ("helpers","telegacy","message")}
src={key:path.read_text(encoding="latin-1") for key,path in p.items()}
if "concept98_readable_ui_v127" in src["telegacy"]:raise SystemExit(0)
if "concept98_photo_visibility_v126" not in src["message"]:raise SystemExit("requires v12.6")
def one(name,old,new,why):
    s=src[name];n=s.count(old)
    if n!=1:raise SystemExit("v12.7 "+why+" count="+str(n))
    src[name]=s.replace(old,new,1)

# A blank 370x103 STATIC surface could paint on top of author/body controls.
one("helpers",'''        HWND panel=CreateWindowExW(
            WS_EX_CLIENTEDGE,L"STATIC",L"",
            WS_VISIBLE|WS_CHILD|SS_LEFT,
            10,10,370,103,hDlg,(HMENU)9023,NULL,NULL
        );''','''        // concept98_readable_ui_v127: draw recessed border in the dialog,
        // not as a separate child window covering the text.''',"notification cover")
one("helpers","bool paper=(id==9021||id==9022||id==9023);",
    "bool paper=(id==9022);","notification brush")
one("helpers","54, 18, 307, 24, hDlg, (HMENU)9021, NULL, NULL",
    "60, 18, 305, 23, hDlg, (HMENU)9021, NULL, NULL","author position")
one("helpers",'''        HWND body = CreateWindowW(
            L"STATIC", data ? data->szInfo : L"",
            WS_VISIBLE | WS_CHILD | SS_LEFT,
            54, 45, 303, 59, hDlg, (HMENU)9022, NULL, NULL
        );''','''        HWND body = CreateWindowExW(
            0,L"STATIC", data ? data->szInfo : L"",
            WS_VISIBLE|WS_CHILD|SS_LEFT|SS_EDITCONTROL|SS_NOPREFIX,
            21,48,340,59,hDlg,(HMENU)9022,NULL,NULL
        );''',"notification multiline")
one("helpers",'''        SetTimer(hDlg, 1, 12000, NULL);
        diag_log("concept98 v91 new-message popup displayed");''','''        InvalidateRect(title,NULL,TRUE);
        InvalidateRect(body,NULL,TRUE);
        SetTimer(hDlg, 1, 12000, NULL);
        diag_log("concept98 v127 popup visible sender_chars=%d body_chars=%d",
                 data ? (int)wcslen(data->szInfoTitle) : 0,
                 data ? (int)wcslen(data->szInfo) : 0);''',"notification diagnostics")
one("helpers","    if (concept98_enabled && msg == WM_COMMAND) {",'''    if (concept98_enabled && msg == WM_PAINT) {
        PAINTSTRUCT ps={0};HDC dc=BeginPaint(hDlg,&ps);
        RECT frame={10,10,380,114};
        DrawEdge(dc,&frame,EDGE_SUNKEN,BF_RECT);
        EndPaint(hDlg,&ps);
        return TRUE;
    }
    if (concept98_enabled && msg == WM_COMMAND) {''',"noncovering recessed frame")

# In the original code an authorised session stays hidden until a presence
# RPC acknowledges; on timeout its process remains alive invisibly.
one("helpers",'''void exit_telegacy() {
	if (dcInfoMain.authorized) {
		ShowWindow(hMain, SW_HIDE);
		closing = true;
		if (!update_own_status(false)) DestroyWindow(hMain);
	}
}''','''void exit_telegacy() {
    // concept98_readable_ui_v127: do not leave a hidden orphaned process.
    if(closing)return;
    closing=true;
    if(dcInfoMain.authorized)update_own_status(false);
    if(hMain && IsWindow(hMain)){
        diag_log("concept98 v127 main window shutdown");
        DestroyWindow(hMain); // WM_DESTROY saves settings and posts quit.
    }
}''',"synchronous quit")
one("telegacy",'''	case WM_CLOSE:
		if (CLOSETOTRAY) {''','''	case WM_CLOSE:
        // v127: the X closes the app in Concept98, not merely its window.
        if(concept98_enabled){exit_telegacy();return 0;}
		if (CLOSETOTRAY) {''',"classic close command")

# Paragraph formatting never inserts characters, so the JPEG, sticker,
# link, reaction and reply OLE character positions remain unchanged.
one("message",'''	PARAFORMAT2 pf;
	pf.cbSize = sizeof(pf);
	pf.dwMask = PFM_ALIGNMENT;
	pf.wAlignment = service ? PFA_CENTER : PFA_LEFT;
	SendMessage(chat, EM_SETPARAFORMAT, 0, (LPARAM)&pf);''','''    // concept98_readable_ui_v127: outgoing right, incoming left.
    PARAFORMAT2 pf={0};pf.cbSize=sizeof(pf);
    pf.dwMask=PFM_ALIGNMENT|PFM_STARTINDENT|PFM_RIGHTINDENT;
    RECT inner={0};GetClientRect(chat,&inner);
    int gutter=(inner.right-inner.left)*19/100;
    if(gutter<46)gutter=46;
    if(gutter>220)gutter=220;
    pf.wAlignment=service?PFA_CENTER:(message.outgoing?PFA_RIGHT:PFA_LEFT);
    pf.dxStartIndent=service?0:MulDiv(message.outgoing?gutter:8,1440,dpi);
    pf.dxRightIndent=service?0:MulDiv(message.outgoing?8:gutter,1440,dpi);
    SendMessage(chat,EM_SETPARAFORMAT,0,(LPARAM)&pf);''',"two-sided chat")
one("message",'''	message.end_footer = message.end_char + written_info;
	message.start_reactions = message.start_reactions ? (message.end_char + message.start_reactions) : message.end_footer;''','''	message.end_footer = message.end_char + written_info;
    // concept98_readable_ui_v127: distinguish reply/forward context from
    // message text and timestamp without adding bytes or shifting OLE.
    if(!service && (msgrpl || msgfwd) &&
       message.end_footer>message.end_char+2){
        int beg=message.end_char+1;
        int stop=message.end_footer;
        if(stop-beg>320)stop=beg+320;
        wchar_t excerpt[324]={0};
        TEXTRANGEW tr={0};
        tr.chrg.cpMin=beg;tr.chrg.cpMax=stop;tr.lpstrText=excerpt;
        LRESULT copied=SendMessageW(chat,EM_GETTEXTRANGE,0,(LPARAM)&tr);
        if(copied>0){
            int span=0;
            while(span<copied && excerpt[span]!=L'\\r' &&
                  excerpt[span]!=L'\\n')span++;
            if(span>0){
                SendMessage(chat,EM_SETSEL,beg,beg+span);
                CHARFORMAT2 quote={0};quote.cbSize=sizeof(quote);
                quote.dwMask=CFM_BACKCOLOR|CFM_ITALIC|CFM_COLOR;
                quote.dwEffects=CFE_ITALIC;
                quote.crBackColor=GetSysColor(COLOR_BTNFACE);
                quote.crTextColor=GetSysColor(COLOR_BTNTEXT);
                SendMessage(chat,EM_SETCHARFORMAT,SCF_SELECTION,(LPARAM)&quote);
                PARAFORMAT2 inset={0};inset.cbSize=sizeof(inset);
                inset.dwMask=PFM_OFFSET;
                inset.dxOffset=MulDiv(10,1440,dpi);
                SendMessage(chat,EM_SETPARAFORMAT,0,(LPARAM)&inset);
            }
        }
    }
	message.start_reactions = message.start_reactions ? (message.end_char + message.start_reactions) : message.end_footer;''',"semantic quote stripe")
for key,path in p.items():
    path.write_text(src[key],encoding="latin-1",newline="\r\n")
print("v12.7: readable system-color notification, proper close, two-sided native RichEdit chat, compact reply/forward highlights; media unchanged.")
