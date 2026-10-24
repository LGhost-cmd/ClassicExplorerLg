#!/usr/bin/env python3
"""Source-level regression contracts for generated Telegacy Concept 98.

This is intentionally deterministic/offline: GitHub CI cannot use a customer's
Telegram session. Runtime scenarios still require a real Windows GUI pass.
"""
from pathlib import Path
import argparse

def method(data, marker):
    i=data.find(marker)
    if i<0: raise AssertionError(f"Missing function {marker}")
    b=data.find("{",i)
    if b<0: raise AssertionError(f"No opening brace: {marker}")
    depth=0
    quote=False
    escaped=False
    for j in range(b,len(data)):
        c=data[j]
        if c=='"' and not escaped: quote=not quote
        if not quote:
            if c=='{':depth+=1
            if c=='}':
                depth-=1
                if depth==0:return data[i:j+1]
        if c=='\\' and not escaped:escaped=True
        else:escaped=False
    raise AssertionError(f"No closing brace: {marker}")

def require(ok, message):
    if not ok: raise AssertionError(message)

def main(root):
    cpp=(root/"src"/"telegacy.cpp").read_text(encoding="latin-1")
    helpers=(root/"src"/"helpers.cpp").read_text(encoding="latin-1")
    response=(root/"src"/"response.cpp").read_text(encoding="latin-1")
    header=(root/"include"/"telegacy.h").read_text(encoding="latin-1")
    results=[]

    timer=method(cpp,"static VOID CALLBACK media_chat_sticker_timer_proc_unsafe(")
    require("media_chat_sticker_find_ole_cp" in timer,"Sticker OLE anchor lookup removed")
    require("media_chat_sticker_ensure_anchor_ole_v85" not in timer,
            "Animation timer may write a duplicate OLE")
    require("insert_image(" not in timer,
            "Animation timer must not insert images")
    require("sticker_cp == sticker->last_cp_v88" in timer,
            "Cached geometry must belong to the same anchor")
    require("distance != 0 || !large_object" in cpp,
            "Loose photo/sticker overlap selection reintroduced")
    results.append("Sticker: no timer OLE writes, same-cp geometry, bounded search")

    require("concept98_static_webp_identity_v104" in cpp and
            "after_delete_count==before_count-1" in cpp,
            "Static WebP replacement must verify exact OLE removal")
    require("concept98 v104 WebP deletion refused" in cpp,
            "Static WebP duplicate media guard lacks refused diagnostic")

    require("media_chat_full_photo_ole_identity_v87" in cpp,
            "Full JPEG replacement lost exact captured OLE identity")
    require("chat v87 full photo replaced exact" in cpp,
            "No full photo replacement confirmation")
    require("media_chat_replace_loaded_bitmap_unsafe_v88" in cpp,
            "Async OLE mutation exception boundary removed")
    require("media_chat_jpeg_error_exit_v89" in helpers,
            "Malformed JPEG would terminate the process")
    require("media_chat_v89_webp_to_bmp" in response,
            "WebP thumbnail has lost ownership-safe decoder")
    require("WebPFree(owned_rgba)" not in response,
            "Double-free reintroduced in WebP decoding")
    message=(root/"src"/"message.cpp").read_text(encoding="latin-1")
    # Concept98 chat layout/interaction guards (applied after v13.2).
    require("concept98_author_id_v132" in header and
            "memcpy(&identity_v132,id_bytes_v132,8)" in message and
            "messages.front().concept98_author_id_v132" in message and
            "messages.back().concept98_author_id_v132" in message,
            "Speaker gaps must distinguish group participants, not just outgoing flags")
    require("pf.wAlignment=service?PFA_CENTER:PFA_LEFT" in message and
            "author_changed_v132?150" in message,
            "Traditional single-column chat with speaker transitions missing")
    require("concept98_reply_hit_v132" in cpp and
            "concept98_forward_hit_v130(pENLink)" in cpp and
            "concept98_open_forward_v130((int)j,true)" in cpp,
            "Reply and forward links must use the actual EN_LINK dispatcher and viewer")
    require("SetWindowTextW(concept98_forward_win_v130,reply_view_v132?" in cpp,
            "Reply popup must be labeled as reply, not forwarded message")
    require("concept98_nickname_hit_v129" in
            (root/"src"/"procs.cpp").read_text(encoding="latin-1"),
            "Nickname-only profile click boundary missing")
    results.append("Concept98: per-sender gaps, reply/forward click, popup title")

    require("concept98_clean_media_v105" in message,
            "Clean full-quality chat photo policy missing")
    require("if (size == 'i' && IMAGELOADPOLICY)" not in message,
            "Telegram low-resolution stripped photo preview re-enabled")
    require("Full quality  |  Loading..." in message,
            "Loading card lost its neutral fallback UI")
    require("concept98_clean_media_v105" in timer,
            "Fresh RichEdit geometry requirement missing")
    require("origin.x -=" not in timer and "origin.y -=" not in timer,
            "Sticker overlay may still extrapolate an old scroll position")
    require("bool inferred_geometry = false;" in timer,
            "Sticker runtime can animate without verified OLE position")
    results.append("Photos: exact OLE identity, bounded decoding, one buffer owner")

    require("typedef std::pair<int, __int64> ConceptAvatar96Key;" in helpers,
            "Avatar cache does not separate users, groups and channels")
    require("it->second.photo_id!=photo_id" in helpers,
            "Changed profile photo would remain stale")
    require("concept98_avatar_failure_v96" in helpers,
            "Avatar failures would never retry")
    require("concept98_pending_rpc_v96" in helpers,
            "Avatar replies must not consume an unrelated upload.file")
    require("concept98_fast_avatars_v99" in helpers and
            "concept98_pending_v99" in helpers,
            "Avatar requests must be pipelined with a bounded queue")
    require("concept98_avatar_disk_load_v99" in helpers and
            "concept98_avatar_disk_save_v99" in helpers,
            "Warm avatar thumbnails must use the 40px disk cache")
    require("concept98_avatar_mutex_v98" in helpers,
            "Avatar cache no longer synchronized between worker and UI")
    require(helpers.count("cache_guard(concept98_avatar_mutex_v98)") == 4,
            "Avatar cache lock must guard paint/pump/reply/cleanup")
    require("concept98_avatar_clear_v93();" in method(helpers,"void logout_cleanup()"),
            "Avatar cache must be freed on account logout")
    require("concept98_avatar_request_v96" in helpers,
            "Real avatar loader missing")
    require("concept98_avatar_draw_v93" in cpp,
            "Avatar list rendering missing")
    require("concept98_draw_header_v96" in cpp and "(HMENU)8996" in cpp,
            "Chat header no longer shows the cached photo")
    require("profile_gallery_handle_upload" in response,
            "Existing profile-gallery RPC handler lost")
    require("profile_gallery_fit_bitmap" in helpers,
            "Existing profile-gallery resize lost")
    results.append("Avatars: identity, changed photo, retry, list/header/profile")

    notifications=method(helpers,"void new_msg_notification(")
    require("!suppress_toast && !groupmed && dcInfoMain.ready" in notifications,
            "DND must only suppress UI/audio")
    require(notifications.count("peer->unread_msgs_count++")==1,
            "DND must not duplicate individual unread counts")
    require(notifications.count("update_total_unread_msgs_count(1)")==1,
            "DND must not duplicate total unread count updates")
    require("concept98_dnd_active_v93" in notifications,
            "DND check missing from native notification handler")
    dlg=method(helpers,"INT_PTR CALLBACK DlgProcNotification(")
    require("LOWORD(wParam) == 3" in dlg and "LOWORD(wParam) == 4" in dlg,
            "Hide and Do-Not-Disturb buttons are not bound")
    require("WM_CLOSE" in dlg and "WM_TIMER" in dlg,
            "Notification close/timeout missing")
    require("GetMenuState(popup,8991" in cpp,
            "DND menu no longer reflects current state")
    results.append("Notifications: Hide/Close/Timeout/DND and one unread update")

    require("concept98_previous_public_count_v91" in cpp and
            "CB_GETITEMDATA" in cpp,"Global Telegram search is not live")
    require("concept98_divider_proc_v92" in cpp and
            "sidebar_width" in cpp,"Resizable/sidebar persistence missing")
    require("concept98_pixel_glyph_v95" in cpp,"Classic UI icons missing")
    require("concept98_bootstrap_tick_v100" in cpp and
            "concept98_bootstrap_begin_v100" in cpp,
            "Initial chat viewport settling missing")
    require("concept98_full_photo_load_v101" in cpp and
            "concept98_full_photo_save_v101" in cpp,
            "Repeated full-quality photo clicks must be cached")
    require("concept98_move_v91" in cpp and
            "concept98_apply_layout" in cpp,"Responsive layout removed")
    require("msg.wParam == 'K'" in cpp and "msg.wParam == 'F'" in cpp,
            "Search hotkeys lost")
    require("WM_CONTEXTMENU" in cpp,"Chat context menu lost")
    require("concept98_enabled" in header,"Concept UI toggle not exported")
    results.append("UI: real global search, resizing, controls, menu, keyboard")

    for idx,msg in enumerate(results,1):
        print(f"OK {idx}/{len(results)}: {msg}")
    print("PASS: offline Concept 98 source-level regression contracts.")
    print("NOTE: live Telegram session / Windows visual runtime are NOT covered.")

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("root",type=Path)
    main(parser.parse_args().root.resolve())
