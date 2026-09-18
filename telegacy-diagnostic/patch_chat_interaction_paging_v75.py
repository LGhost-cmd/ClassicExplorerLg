#!/usr/bin/env python3
from pathlib import Path
import re
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_chat_interaction_paging_v75.py <Telegacy source directory>")

root = Path(sys.argv[1]).resolve()
h = root / "include" / "telegacy.h"
t = root / "src" / "telegacy.cpp"
p = root / "src" / "procs.cpp"
r = root / "src" / "response.cpp"
hp = root / "src" / "helpers.cpp"

for path in (h, t, p, r, hp):
    if not path.exists():
        raise SystemExit(f"Missing expected Telegacy file: {path}")


def read(path):
    return path.read_text(encoding="latin-1")


def write(path, data):
    path.write_text(data, encoding="latin-1", newline="\r\n")


if "chat_interaction_paging_v75" in read(t):
    print("Chat interaction/paging v7.5 already applied.")
    raise SystemExit(0)

for token, path in (
    ("chat_scope_sync_v74", t),
    ("media_inplace_upgrade_v73", t),
    ("chat_video_direct_mouse_proc_v59", p),
    ("history_parser_guard_v69", r),
    ("volatile LONG history_request_pending = 0;", hp),
):
    if token not in read(path):
        raise SystemExit(f"Required predecessor marker missing in {path.name}: {token}")

# ---------------------------------------------------------------------------
# Header declarations used by the RichEdit mouse handler and paging recovery.
# ---------------------------------------------------------------------------
s = read(h)

anchor = "extern volatile LONG history_request_pending;"
if anchor not in s:
    raise SystemExit("Could not locate history_request_pending declaration.")
if "extern volatile LONG history_skip_next;" not in s:
    s = s.replace(
        anchor,
        anchor + "\nextern volatile LONG history_skip_next; // chat_interaction_paging_v75",
        1,
    )

# This declaration is injected near the early media declarations, before the
# full DCInfo definition in Telegacy's legacy header.
if "struct DCInfo;" not in s:
    doc_decl = "struct Document;"
    if doc_decl in s:
        s = s.replace(doc_decl, doc_decl + "\nstruct DCInfo; // chat_interaction_paging_v75", 1)
    else:
        s = s.replace(anchor, anchor + "\nstruct DCInfo; // chat_interaction_paging_v75", 1)

video_decl = "bool media_chat_video_handle_chat_mouse(HWND hWnd, UINT msg, WPARAM wParam, LPARAM lParam);"
if video_decl not in s:
    raise SystemExit("Could not locate direct video mouse declaration.")

extra_decls = (
    "\nbool media_chat_full_photo_begin(Document* document, DCInfo* dcInfo); // chat_interaction_paging_v75"
    "\nbool media_chat_photo_handle_chat_mouse(HWND hWnd, UINT msg, WPARAM wParam, LPARAM lParam); // chat_interaction_paging_v75"
)
if "media_chat_photo_handle_chat_mouse(HWND hWnd" not in s:
    s = s.replace(video_decl, video_decl + extra_decls, 1)

write(h, s)

# ---------------------------------------------------------------------------
# History pagination: carry a one-item server skip after an unparseable object.
# This prevents one modern/unsupported message from becoming a permanent wall.
# ---------------------------------------------------------------------------
s = read(hp)
state_anchor = "volatile LONG history_request_pending = 0;"
if state_anchor not in s:
    raise SystemExit("Could not locate history request state definition.")
if "volatile LONG history_skip_next = 0;" not in s:
    s = s.replace(
        state_anchor,
        state_anchor + "\nvolatile LONG history_skip_next = 0; // chat_interaction_paging_v75",
        1,
    )

get_pos = s.find("void get_history()")
if get_pos < 0:
    raise SystemExit("Could not locate patched get_history().")

# Reset a parser-gap skip when the active peer changes. Doing this inside
# get_history() avoids placing an InterlockedExchange expression at global
# scope (the first textual no_more_msgs=false in telegacy.cpp is a global).
get_signature = "void get_history() {"
if "history_last_peer_id_v75" not in s:
    peer_reset = r'''
    // chat_interaction_paging_v75: a parser-gap skip belongs only to one peer.
    static BYTE history_last_peer_id_v75[8] = {0};
    static bool history_last_peer_valid_v75 = false;
    if (
        current_peer &&
        (
            !history_last_peer_valid_v75 ||
            memcmp(history_last_peer_id_v75, current_peer->id, 8) != 0
        )
    ) {
        InterlockedExchange(&history_skip_next, 0);
        memcpy(history_last_peer_id_v75, current_peer->id, 8);
        history_last_peer_valid_v75 = true;
    }
'''
    if get_signature not in s:
        raise SystemExit("Could not locate get_history() opening brace.")
    s = s.replace(get_signature, get_signature + peer_reset, 1)
    get_pos = s.find("void get_history()")

add_pos = s.find("// add_offset", get_pos)
if add_pos < 0:
    raise SystemExit("Could not locate getHistory add_offset field.")
mem_pos = s.find("memset(", add_pos)
mem_end = s.find(");", mem_pos)
if mem_pos < 0 or mem_end < 0:
    raise SystemExit("Could not locate getHistory add_offset memset block.")
mem_end += 2
line_start = s.rfind("\n", 0, add_pos) + 1
indent = s[line_start:add_pos]
new_add_offset = (
    f"{indent}// add_offset: normally zero; v7.5 uses one item only after a parser gap.\n"
    f"{indent}LONG history_add_offset = InterlockedExchange(&history_skip_next, 0);\n"
    f"{indent}if (history_add_offset < 0) history_add_offset = 0;\n"
    f"{indent}if (history_add_offset > 8) history_add_offset = 8;\n"
    f"{indent}write_le(\n"
    f"{indent}    unenc_query + 44 + offset,\n"
    f"{indent}    history_add_offset,\n"
    f"{indent}    4\n"
    f"{indent});\n"
    f"{indent}if (history_add_offset)\n"
    f"{indent}    diag_log(\"history v75 skipping server items=%ld\", history_add_offset);"
)
s = s[:line_start] + new_add_offset + s[mem_end:]
write(hp, s)

# ---------------------------------------------------------------------------
# History parser: a message whose envelope is valid but whose old renderer does
# not understand its fields is skipped, rather than terminating the whole page.
# If even the safe envelope cannot be decoded, leave history open and skip one
# server item on the next request instead of setting no_more_msgs permanently.
# ---------------------------------------------------------------------------
s = read(r)
handler_pos = s.find("int consumed = media_archive_safe_message_handler(")
if handler_pos < 0:
    raise SystemExit("Could not locate guarded history renderer call.")
cond_token = "consumed != safe_consumed"
cond_pos = s.find(cond_token, handler_pos)
if cond_pos < 0:
    raise SystemExit("Could not locate guarded renderer validation.")
if_pos = s.rfind("if (", handler_pos, cond_pos)
if if_pos < 0:
    raise SystemExit("Could not locate guarded renderer if block.")
if_line_start = s.rfind("\n", 0, if_pos) + 1
offset_pos = s.find("offset_msg += consumed;", cond_pos)
if offset_pos < 0:
    raise SystemExit("Could not locate guarded renderer offset advance.")
offset_line_end = s.find("\n", offset_pos)
if offset_line_end < 0:
    offset_line_end = len(s)
else:
    offset_line_end += 1
indent = s[if_line_start:if_pos]
inner = indent + "\t"
renderer_recovery = (
    f"{indent}if (\n"
    f"{inner}consumed <= 0 ||\n"
    f"{inner}consumed > available ||\n"
    f"{inner}consumed != safe_consumed\n"
    f"{indent}) {{\n"
    f"{inner}diag_log(\n"
    f"{inner}\t\"history v75 renderer skipped item=%d offset=%d available=%d id=%d safe=%d rendered=%d exception=0x%08X\",\n"
    f"{inner}\ti,\n"
    f"{inner}\toffset_msg,\n"
    f"{inner}\tavailable,\n"
    f"{inner}\tsafe_message_id,\n"
    f"{inner}\tsafe_consumed,\n"
    f"{inner}\tconsumed,\n"
    f"{inner}\t(unsigned int)media_archive_last_parse_exception\n"
    f"{inner});\n"
    f"{inner}offset_msg += safe_consumed;\n"
    f"{inner}continue;\n"
    f"{indent}}}\n\n"
    f"{indent}offset_msg += consumed;\n"
)
s = s[:if_line_start] + renderer_recovery + s[offset_line_end:]

failed_pos = s.find("if (history_parse_failed)")
if failed_pos < 0:
    raise SystemExit("Could not locate history parse-failure recovery block.")
no_more_pos = s.find("no_more_msgs = true;", failed_pos)
if no_more_pos < 0:
    raise SystemExit("Could not locate history parse-failure terminal flag.")
no_more_line_start = s.rfind("\n", 0, no_more_pos) + 1
no_more_line_end = s.find("\n", no_more_pos)
if no_more_line_end < 0:
    no_more_line_end = len(s)
else:
    no_more_line_end += 1
fail_indent = s[no_more_line_start:no_more_pos]
replacement = (
    f"{fail_indent}InterlockedExchange(&history_skip_next, 1);\n"
    f"{fail_indent}no_more_msgs = false; // chat_interaction_paging_v75: malformed item is not end-of-history\n"
)
s = s[:no_more_line_start] + replacement + s[no_more_line_end:]
write(r, s)

# ---------------------------------------------------------------------------
# Photo double-click retry + roomier top controls.
# ---------------------------------------------------------------------------
s = read(t)
video_signature = "bool media_chat_video_handle_chat_mouse("
video_pos = s.find(video_signature)
if video_pos < 0:
    raise SystemExit("Could not locate direct video mouse helper insertion point.")

photo_handler = r'''// chat_interaction_paging_v75
// A double click on an ordinary photo card means "retry/upgrade this preview".
// This is intentionally separate from video handling. Clearing photo_msg_id
// makes the item eligible for the existing serial loader even if another photo
// is currently in flight; the normal queue picks it up after that transfer.
bool media_chat_photo_handle_chat_mouse(
    HWND hWnd,
    UINT msg,
    WPARAM,
    LPARAM lParam
) {
    if (!chat || hWnd != chat || msg != WM_LBUTTONDBLCLK)
        return false;

    POINT point = {
        GET_X_LPARAM(lParam),
        GET_Y_LPARAM(lParam)
    };

    LRESULT raw_hit = SendMessageW(
        chat,
        EM_CHARFROMPOS,
        0,
        (LPARAM)&point
    );

    int hit_char = raw_hit >= 0 ? (int)raw_hit : -1;

    for (int i = (int)documents.size() - 1; i >= 0; i--) {
        Document* document = &documents[i];

        if (
            !document->visible ||
            !document->file_reference ||
            document->photo_size == 0 ||
            document->photo_size == 1 ||
            document->photo_size == 3 ||
            document->max <= document->min
        ) {
            continue;
        }

        bool hit = false;

        if (hit_char >= 0) {
            for (int delta = -1; delta <= 1; delta++) {
                int candidate = hit_char + delta;
                if (
                    candidate >= document->min &&
                    candidate <= document->max
                ) {
                    hit = true;
                    break;
                }
            }
        }

        if (!hit) {
            POINTL origin = {0, 0};
            LRESULT pos_result = SendMessageW(
                chat,
                EM_POSFROMCHAR,
                (WPARAM)&origin,
                (LPARAM)document->min
            );

            if (pos_result != -1) {
                int effective_dpi = dpi > 0 ? dpi : 96;
                int card_width = MulDiv(288, effective_dpi, 96);
                int card_height = MulDiv(216, effective_dpi, 96);
                RECT card = {
                    (LONG)origin.x,
                    (LONG)origin.y,
                    (LONG)origin.x + card_width,
                    (LONG)origin.y + card_height
                };
                hit = PtInRect(&card, point) != FALSE;
            }
        }

        if (!hit)
            continue;

        memset(document->photo_msg_id, 0, sizeof(document->photo_msg_id));

        bool started = media_chat_full_photo_begin(
            document,
            &dcInfoMain
        );

        diag_log(
            "chat v75 photo double click index=%d char=%d range=%d..%d started_or_queued=%d",
            i,
            hit_char,
            document->min,
            document->max,
            started ? 1 : 0
        );

        if (!started)
            MessageBeep(MB_ICONASTERISK);

        return true;
    }

    return false;
}

'''
s = s[:video_pos] + photo_handler + s[video_pos:]

# Peer-change reset is handled inside get_history() in helpers.cpp. This is
# deliberate: the first textual no_more_msgs=false in telegacy.cpp is the
# global variable declaration, so inserting an expression after it would
# create invalid C++ at global scope.

# First-row spacing: keep the same controls but give every adjacent classic
# control a real 10-pixel gap. This also slightly increases the chat selector at
# the original 500px minimum window width compared with v7.4.
layout_rules = [
    (r"195,\s*10,\s*115,\s*300", "200, 10, 105, 300", "folder combo"),
    (r"315,\s*10,\s*150,\s*22", "315, 10, 125, 22", "chat search"),
    (r"470,\s*10,\s*width\s*-\s*480,\s*300", "450, 10, width - 460, 300", "chat combo"),
]
for pattern, replacement_text, label in layout_rules:
    s, count = re.subn(pattern, replacement_text, s)
    if count < 1:
        raise SystemExit(f"Could not relax top-bar spacing for {label}.")

# Second row: 12-13px gaps between search, arrows and Media. Media ends 10px
# from the right edge rather than looking glued to the navigation buttons.
second_row_rules = [
    (r"width\s*-\s*205", "width - 280", 2, "message search width"),
    (r"width\s*-\s*190", "width - 258", 2, "previous button x"),
    (r"width\s*-\s*140", "width - 200", 2, "next button x"),
    (r"width\s*-\s*90", "width - 142", 2, "Media button x"),
]
for pattern, replacement_text, expected, label in second_row_rules:
    s, count = re.subn(pattern, replacement_text, s)
    if count != expected:
        raise SystemExit(
            f"Could not relax second-row spacing for {label}: expected {expected}, found {count}."
        )

media_width_pattern = re.compile(
    r"(width\s*-\s*142,\s*40,\s*)80(,\s*22)",
    re.MULTILINE,
)
s, media_width_count = media_width_pattern.subn(r"\g<1>132\2", s)
if media_width_count != 2:
    raise SystemExit(
        f"Could not widen Media button after repositioning: expected 2, found {media_width_count}."
    )

write(t, s)

# ---------------------------------------------------------------------------
# RichEdit direct mouse retry and scroll-top pagination trigger.
# ---------------------------------------------------------------------------
s = read(p)
signature = "LRESULT CALLBACK WndProcChat(HWND hWnd, UINT msg, WPARAM wParam, LPARAM lParam) {"
pos = s.find(signature)
if pos < 0:
    raise SystemExit("Could not locate WndProcChat for v7.5.")
insert_pos = pos + len(signature)

scroll_guard = r'''

    // chat_history_scroll_guard_v75
    // Some RichEdit versions do not send SB_ENDSCROLL after thumb dragging.
    // Treat an explicit top/thumb-to-top command as a history request as well.
    if (
        msg == WM_VSCROLL &&
        current_peer &&
        !no_more_msgs
    ) {
        WORD scroll_code = LOWORD(wParam);
        WORD scroll_pos = HIWORD(wParam);

        if (
            scroll_code == SB_TOP ||
            (
                (scroll_code == SB_THUMBPOSITION || scroll_code == SB_THUMBTRACK) &&
                scroll_pos <= 3
            )
        ) {
            diag_log(
                "history v75 scroll-top trigger code=%u pos=%u pending=%ld",
                (unsigned int)scroll_code,
                (unsigned int)scroll_pos,
                InterlockedCompareExchange(&history_request_pending, 0, 0)
            );
            get_history();
        }
    }
'''
s = s[:insert_pos] + scroll_guard + s[insert_pos:]

video_proc_anchor = "    // chat_video_direct_mouse_proc_v59"
video_proc_pos = s.find(video_proc_anchor, insert_pos)
if video_proc_pos < 0:
    raise SystemExit("Could not locate v5.9 direct mouse block in WndProcChat.")
photo_proc = r'''    // chat_photo_retry_dblclick_proc_v75
    if (
        msg == WM_LBUTTONDBLCLK &&
        media_chat_photo_handle_chat_mouse(
            hWnd,
            msg,
            wParam,
            lParam
        )
    ) {
        return 0;
    }

'''
s = s[:video_proc_pos] + photo_proc + s[video_proc_pos:]
write(p, s)

# ---------------------------------------------------------------------------
# Verification.
# ---------------------------------------------------------------------------
checks = {
    h: [
        "history_skip_next",
        "struct DCInfo;",
        "media_chat_photo_handle_chat_mouse(HWND hWnd",
        "media_chat_full_photo_begin(Document* document, DCInfo* dcInfo)",
    ],
    hp: [
        "history_skip_next = 0",
        "history_last_peer_id_v75",
        "history v75 skipping server items=%ld",
        "history_add_offset",
    ],
    r: [
        "history v75 renderer skipped item=",
        "InterlockedExchange(&history_skip_next, 1)",
        "malformed item is not end-of-history",
    ],
    t: [
        "chat_interaction_paging_v75",
        "chat v75 photo double click",
        "200, 10, 105, 300",
        "450, 10, width - 460, 300",
        "width - 280",
        "width - 258",
        "width - 200",
        "width - 142",
    ],
    p: [
        "chat_history_scroll_guard_v75",
        "chat_photo_retry_dblclick_proc_v75",
        "history v75 scroll-top trigger",
    ],
}
for path, tokens in checks.items():
    data = read(path)
    for token in tokens:
        if token not in data:
            raise SystemExit(f"v7.5 verification failed in {path.name}: {token}")

print(
    "Applied chat interaction/paging v7.5: double-click retries pixelated photo previews "
    "through the full-quality loader, top controls have wider classic-UI spacing, and "
    "history pagination no longer treats one renderer/parser gap or missing SB_ENDSCROLL "
    "as a permanent end of chat history."
)
