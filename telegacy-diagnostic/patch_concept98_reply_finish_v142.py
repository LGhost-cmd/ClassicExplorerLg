#!/usr/bin/env python3
"""Concept98 v14.2: exact reply-header link highlighting and clean read-only
reply branches. Leave the original chat text, emoji and RichEdit OLE alone."""
from pathlib import Path
import sys
if len(sys.argv)!=2:
    raise SystemExit("Usage: patch_concept98_reply_finish_v142.py <src>")
root=Path(sys.argv[1]).resolve()
message=root/"src"/"message.cpp"
ui=root/"src"/"telegacy.cpp"
m=message.read_text(encoding="latin-1")
t=ui.read_text(encoding="latin-1")
if "concept98_reply_finish_v142" in m and "concept98_reply_finish_v142" in t:
    print("v14.2 already applied")
    raise SystemExit(0)
if "concept98_branch_polish_v141" not in t:
    raise SystemExit("v14.2 requires Concept98 v14.1")
def replace_exact(text,old,new,label):
    count=text.count(old)
    if count!=1:raise SystemExit("v14.2 "+label+" matches="+str(count))
    return text.replace(old,new,1)

# The previous v13.2 style code estimated the RichEdit CP from text lengths.
# On some incoming sender headers the estimate lands on the second character
# and leaves the first Cyrillic "O" outside the styled link.
# Use RichEdit's own text search instead; this is the same coordinate system
# used by EN_LINK and avoids changing the stored message offsets.
m=replace_exact(m,
r'''            int a=message.start_char+ordinary_header_len_v128+(int)where;
            int b=a+(int)label.size();
            if(a>=message.start_char && b<=message.end_header){
                SendMessageW(chat,EM_SETSEL,a,b);''',
r'''            // concept98_reply_finish_v142: actual RichEdit character
            // positions, not guessed header lengths (incoming/outgoing can
            // differ by a CR/paragraph character).
            FINDTEXTEXW link_v142={0};
            link_v142.chrg.cpMin=message.start_char;
            link_v142.chrg.cpMax=message.end_header;
            link_v142.lpstrText=(LPWSTR)label.c_str();
            LRESULT pos_v142=SendMessageW(chat,EM_FINDTEXTEXW,FR_DOWN,
                                          (LPARAM)&link_v142);
            if(pos_v142>=0 &&
               link_v142.chrgText.cpMin>=message.start_char &&
               link_v142.chrgText.cpMax<=message.end_header &&
               link_v142.chrgText.cpMax-link_v142.chrgText.cpMin==
                   (LONG)label.size()){
                SendMessageW(chat,EM_SETSEL,link_v142.chrgText.cpMin,
                                  link_v142.chrgText.cpMax);''',
"reply label exact hyperlink")

# A copied RTF message includes the compact chat-context label. In an
# expanded chain it is redundant, so strip it only from the popup copy.
# Restrict search to the original message header to avoid erasing a person's
# literal words "Ответ на сообщение" in the message body.
anchor=r'''static bool concept98_branch_copy_rtf_v140(HWND destination,
                                           const Message& row){'''
helper=r'''// concept98_reply_finish_v142: delete only the chat-link heading in
// the COPIED child control. Do not touch source chat RichEdit or its OLE CP.
static void concept98_branch_strip_reply_v142(HWND destination,
                                               const Message& row){
    if(!destination || !IsWindow(destination))return;
    const int n=GetWindowTextLengthW(destination);
    if(n<=0 || row.end_header<=row.start_char)return;
    const wchar_t* label=
        L"\x041e\x0442\x0432\x0435\x0442 \x043d\x0430 \x0441\x043e\x043e\x0431\x0449\x0435\x043d\x0438\x0435";
    FINDTEXTEXW hit={0};
    hit.chrg.cpMin=0;
    hit.chrg.cpMax=min(n,max(0,row.end_header-row.start_char+3));
    hit.lpstrText=(LPWSTR)label;
    if(SendMessageW(destination,EM_FINDTEXTEXW,FR_DOWN,
                    (LPARAM)&hit)<0)return;
    if(hit.chrgText.cpMin<0 || hit.chrgText.cpMax>hit.chrg.cpMax)return;
    CHARRANGE cut=hit.chrgText;
    // Remove one following paragraph boundary, so the next message line
    // sits immediately below its author. OLE media remain untouched.
    if(cut.cpMax<n){
        wchar_t next[3]={0};
        TEXTRANGEW tr={0};
        tr.chrg.cpMin=cut.cpMax;
        tr.chrg.cpMax=min(n,cut.cpMax+1);
        tr.lpstrText=next;
        if(SendMessageW(destination,EM_GETTEXTRANGE,0,(LPARAM)&tr)>0 &&
           (next[0]==L'\r'||next[0]==L'\n'))
            ++cut.cpMax;
    }
    SendMessageW(destination,EM_EXSETSEL,0,(LPARAM)&cut);
    SendMessageW(destination,EM_REPLACESEL,FALSE,(LPARAM)L"");
    SendMessageW(destination,EM_SETSEL,0,0);
}
'''
t=replace_exact(t,anchor,helper+anchor,"viewer-only label stripping helper")

# This executes only when a source RTF+OLE was actually streamed. Plain-text
# Telegram snapshots do not contain chat-context labels in the first place.
t=replace_exact(t,
r'''            bool copied=row&&concept98_branch_copy_rtf_v140(c.rich,*row);
            if(!copied){''',
r'''            bool copied=row&&concept98_branch_copy_rtf_v140(c.rich,*row);
            if(copied)
                concept98_branch_strip_reply_v142(c.rich,*row);
            if(!copied){''',
"strip heading from every expanded card")

message.write_text(m,encoding="latin-1",newline="\r\n")
ui.write_text(t,encoding="latin-1",newline="\r\n")
print("v14.2: whole reply label linked; redundant reply heading stripped only inside branches.")
