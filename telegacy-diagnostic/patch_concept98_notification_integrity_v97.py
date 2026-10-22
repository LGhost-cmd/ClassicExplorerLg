#!/usr/bin/env python3
"""Concept 98 v9.7: suppress only notification UI/audio, not unread semantics."""
from pathlib import Path
import sys
if len(sys.argv)!=2: raise SystemExit("Usage: patch_concept98_notification_integrity_v97.py <src>")
root=Path(sys.argv[1]).resolve()
hp=root/"src"/"helpers.cpp"
cp=root/"src"/"telegacy.cpp"
def read(p): return p.read_text(encoding="latin-1")
def write(p,s): p.write_text(s,encoding="latin-1",newline="\r\n")
s=read(hp)
if "concept98_notification_integrity_v97" in s:
    print("v9.7 already applied");raise SystemExit(0)
begin=s.find("void new_msg_notification(Peer* peer, BYTE* msg_bytes, bool groupmed) {")
end=s.find("void update_total_unread_msgs_count(",begin)
if begin<0 or end<0:raise SystemExit("Notification implementation unavailable")
func=s[begin:end]
old=r'''    if (concept98_enabled && concept98_dnd_active_v93()) {
        if (!peer || memcmp(peer->id,myself.id,8)==0) return;
        if (!peer->mute_until && !muted_types[peer->type])
            update_total_unread_msgs_count(1);
        peer->unread_msgs_count++;
        return;
    }
'''
if old not in func:raise SystemExit("DND early-return path missing")
func=func.replace(old,r'''    // concept98_notification_integrity_v97
    // A notification is presentation only. DND must not bypass Telegram's
    // existing group-media, channel-PTS, muted and unread handling.
    const bool suppress_toast =
        concept98_enabled && concept98_dnd_active_v93();
    if (!groupmed && dcInfoMain.ready &&
        peer && peer->type==2 && peer->channel_msg_id[7]) return;
''',1)
old='if (!groupmed && dcInfoMain.ready) {'
if old not in func:raise SystemExit("Original popup branch unavailable")
func=func.replace(old,'if (!suppress_toast && !groupmed && dcInfoMain.ready) {',1)
s=s[:begin]+func+s[end:]
write(hp,s)

s=read(cp)
# Inactive state is reflected in the native Tools menu whenever it opens.
needle='    if (msg == WM_COMMAND && LOWORD(wParam) == 8991) {'
if needle not in s: raise SystemExit("Concept 98 DND menu action unavailable")
s=s.replace(needle,r'''    if (msg == WM_INITMENUPOPUP && concept98_enabled) {
        HMENU popup=(HMENU)wParam;
        if (popup && GetMenuState(popup,8991,MF_BYCOMMAND)!=(UINT)-1) {
            CheckMenuItem(
                popup,8991,MF_BYCOMMAND |
                (concept98_dnd_active_v93() ? MF_CHECKED : MF_UNCHECKED)
            );
        }
    }
'''+needle,1)
old=r'''    if (msg == WM_COMMAND && LOWORD(wParam) == 8991) {
        concept98_dnd_set_v93(
            concept98_dnd_active_v93() ? 0 : 60
        );
        return 0;
    }'''
new=r'''    if (msg == WM_COMMAND && LOWORD(wParam) == 8991) {
        bool enable=!concept98_dnd_active_v93();
        concept98_dnd_set_v93(enable ? 60 : 0);
        if (enable && current_notification)
            remove_notification();
        diag_log("concept98 v97 notification mute toggled active=%d",
                 enable ? 1 : 0);
        return 0;
    }'''
if old not in s: raise SystemExit("DND toggle code unavailable")
s=s.replace(old,new,1)
write(cp,s)
assert "concept98_notification_integrity_v97" in read(hp)
assert "concept98 v97 notification mute toggled" in read(cp)
print("Applied v9.7: do-not-disturb blocks toast/sound only, keeps stock "
      "unread/muted/channel/group-media semantics and menu check state.")
