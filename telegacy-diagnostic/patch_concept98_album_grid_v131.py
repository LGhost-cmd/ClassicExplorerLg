#!/usr/bin/env python3
"""Concept98 v13.1: two-column in-chat layout of incoming live photo albums.
Non-destructive: replace one RichEdit paragraph break with one tab, preserving
ALL message/document CP indices and one exact OLE object per image.
Older paged history/narrow windows deliberately keep safe vertical layout.
"""
from pathlib import Path
import sys
if len(sys.argv)!=2:raise SystemExit("Usage: patch_concept98_album_grid_v131.py <src>")
p=Path(sys.argv[1]).resolve()/"src"/"message.cpp"
s=p.read_text(encoding="latin-1")
if "concept98_album_grid_v131" in s:raise SystemExit(0)
if "concept98_forward_view_v130" not in s:raise SystemExit("v13.0 required")
def once(old,new,label):
 global s
 n=s.count(old)
 if n!=1:raise SystemExit("v13.1 "+label+" count="+str(n))
 s=s.replace(old,new,1)

# Parse the already existing Telegram grouped_id without adding characters or
# changing the Telegram envelope. A different group or single message resets.
needle='''void message_adder(bool service, bool to_front, int flags, BYTE* msg_id, BYTE* msg_bytes, EDITSTREAM* es, BYTE* chat_member_id, std::vector<int>* format_vecs, BYTE* reactions, BYTE* msgrpl, BYTE* msgfwd, BYTE* views, bool groupmed_end, bool footer, bool editing, int date) {'''
replacement='''// concept98_album_grid_v131: source group id and parity for live messages.
static unsigned __int64 concept98_album_id_v131=0;
static BYTE concept98_album_peer_v131[8]={0};
static int concept98_album_slot_v131=-1;
void message_adder(bool service, bool to_front, int flags, BYTE* msg_id, BYTE* msg_bytes, EDITSTREAM* es, BYTE* chat_member_id, std::vector<int>* format_vecs, BYTE* reactions, BYTE* msgrpl, BYTE* msgfwd, BYTE* views, bool groupmed_end, bool footer, bool editing, int date) {'''
once(needle,replacement,"declare group ordinal")
# Grouped-id is available in message_handler before offset_msg += 8.
needle='''	if (flags_msg & (1 << 17)) {
		if (!duplicate && !rplhelper && !editing) {'''
new='''	if (flags_msg & (1 << 17)) {
        // v131: consecutive live messages with the same album id form rows
        // of two pictures. No multipart aggregation or extra OLE states.
        if(!to_front && !editing && !rplhelper && !duplicate){
            unsigned __int64 id=0;
            memcpy(&id,message+offset_msg,8);
            if(id && id==concept98_album_id_v131 &&
               memcmp(concept98_album_peer_v131,peer_id,8)==0)
                concept98_album_slot_v131++;
            else {
                concept98_album_id_v131=id;
                memcpy(concept98_album_peer_v131,peer_id,8);
                concept98_album_slot_v131=0;
            }
        } else concept98_album_slot_v131=-1;
		if (!duplicate && !rplhelper && !editing) {'''
once(needle,new,"read Telegram grouped media id")
needle='''	} else if (!rplhelper && to_front) {
		if (memcmp(zero_arr, group_id_tofront, 8) != 0) groupmed_end = true;'''
new='''	} else if (!rplhelper && to_front) {
        concept98_album_slot_v131=-1;
		if (memcmp(zero_arr, group_id_tofront, 8) != 0) groupmed_end = true;'''
once(needle,new,"reset on historical ungrouped content")
# Only true photos may take a two-column row. Document videos/audio/stickers
# remain separate and retain their fixed geometry/click mapping.
needle='''	bool group_media = (flags & (1 << 17)) ? true : false;
	bool header ='''
new='''	bool group_media = (flags & (1 << 17)) ? true : false;
	bool header ='''
# insertion after header evaluation rather than before:
needle='''	bool groupmed_end_nottofront = false;
	if (!to_front && groupmed_end) {'''
new='''    // v131: only live, second/fourth/... photo in a wide chat pane.
    // The OLE card is 288px wide; the body needs at least ~650px.
    RECT grid_area_v131={0};GetClientRect(chat,&grid_area_v131);
    BYTE* grid_doc_v131=(!service && (flags & (1<<9)) && msg_bytes)?
                         msg_bytes+tlstr_len(msg_bytes,true):NULL;
    bool grid_photo_v131=grid_doc_v131 &&
                      read_le(grid_doc_v131,4)==0x695150d7;
    bool inline_album_v131=concept98_enabled && !to_front && !editing &&
        !es && group_media && !header && grid_photo_v131 &&
        concept98_album_slot_v131>0 &&
        (concept98_album_slot_v131%2)==1 &&
        (grid_area_v131.right-grid_area_v131.left)>=950;
	bool groupmed_end_nottofront = false;
	if (!to_front && groupmed_end) {'''
once(needle,new,"grid eligibility")
# Replace the newline immediately before the second image with an equal-length
# tab. Never delete or insert chars: all RichEdit OLE cp ranges stay identical.
# Verify the character is actually newline, else fall back to vertical.
needle='''	int written = riched_write(chat, msg);
	if (es) written +='''
new='''    if(inline_album_v131 && cr_startmsg.cpMin>0) {
        wchar_t previous[3]={0};
        TEXTRANGEW range={0};
        range.chrg.cpMin=cr_startmsg.cpMin-1;
        range.chrg.cpMax=cr_startmsg.cpMin;
        range.lpstrText=previous;
        LRESULT count=SendMessageW(chat,EM_GETTEXTRANGE,0,(LPARAM)&range);
        if(count==1 && (previous[0]==L'\\r'||previous[0]==L'\\n')) {
            SendMessageW(chat,EM_SETSEL,cr_startmsg.cpMin-1,
                                   cr_startmsg.cpMin);
            SendMessageW(chat,EM_REPLACESEL,FALSE,(LPARAM)L"\\t");
            SendMessageW(chat,EM_SETSEL,cr_startmsg.cpMin,
                                   cr_startmsg.cpMin);
            diag_log("concept98 v131 album tile side-by-side cp=%d slot=%d",
                     cr_startmsg.cpMin,concept98_album_slot_v131);
        } else inline_album_v131=false;
    }
	int written = riched_write(chat, msg);
	if (es) written +='''
once(needle,new,"equal-length album row separator")
# The photo insertion helper normally forces the OLE onto a new line; do not
# do so for a second tile already separated by a tab.
needle='''		written += media_chat_ensure_line_start(chat);
		document.min = cr_startmsg.cpMin + written;'''
new='''        if(!inline_album_v131)
            written += media_chat_ensure_line_start(chat);
		document.min = cr_startmsg.cpMin + written;'''
once(needle,new,"do not force newline between tiled OLE cards")
p.write_text(s,encoding="latin-1",newline="\r\n")
print("v13.1 two-column live photo group in-place using same-length tab and distinct OLE; safe fallback for narrow/old pages.")
