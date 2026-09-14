#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit(
        "Usage: patch_chat_video_direct_mouse.py <Telegacy source directory>"
    )

root = Path(sys.argv[1]).resolve()
h = root / "include" / "telegacy.h"
t = root / "src" / "telegacy.cpp"
p = root / "src" / "procs.cpp"

for path in (h, t, p):
    if not path.exists():
        raise SystemExit(f"Missing expected Telegacy file: {path}")


def read(path):
    return path.read_text(encoding="latin-1")


def write(path, data):
    path.write_text(data, encoding="latin-1", newline="\r\n")


# ---------------------------------------------------------------------------
# The v5.8 fix correctly knows how to download the full Telegram Document, but
# it is entered from EN_LINK. RichEdit OLE images do not reliably emit EN_LINK,
# so the play-overlay can be perfectly visible while no click event ever reaches
# the download code. Export the helper and invoke it from WndProcChat itself.
# ---------------------------------------------------------------------------

s = read(t)

if "chat_video_direct_mouse_v59" in s:
    print("Chat video direct-mouse v5.9 fix already applied.")
    raise SystemExit(0)

for required in (
    "chat_video_full_download_reactions_v58",
    "static bool media_chat_video_start_full_document(",
    "media_chat_video_start_full_document(",
):
    if required not in s:
        raise SystemExit(
            f"Required v5.8 video token was not found: {required}"
        )

s = s.replace(
    "static bool media_chat_video_start_full_document(\n",
    "bool media_chat_video_start_full_document(\n",
    1,
)

helper_end_anchor = "\n    return true;\n}\n"
helper_start = s.find("bool media_chat_video_start_full_document(")
if helper_start < 0:
    raise SystemExit("Could not locate exported chat video download helper.")

helper_end = s.find(helper_end_anchor, helper_start)
if helper_end < 0:
    raise SystemExit("Could not locate end of chat video download helper.")
helper_end += len(helper_end_anchor)

mouse_handler = r'''

// chat_video_direct_mouse_v59
bool media_chat_video_handle_chat_mouse(
    HWND hWnd,
    UINT msg,
    WPARAM,
    LPARAM lParam
) {
    if (
        !chat ||
        hWnd != chat ||
        (
            msg != WM_LBUTTONDOWN &&
            msg != WM_LBUTTONDBLCLK
        )
    ) {
        return false;
    }

    POINT point = {
        GET_X_LPARAM(lParam),
        GET_Y_LPARAM(lParam)
    };

    LRESULT raw_hit =
        SendMessageW(
            chat,
            EM_CHARFROMPOS,
            0,
            (LPARAM)&point
        );

    int hit_char =
        raw_hit >= 0
            ? (int)raw_hit
            : -1;

    for (
        int i = (int)documents.size() - 1;
        i >= 0;
        i--
    ) {
        Document* document =
            &documents[i];

        if (
            document->photo_size != 3 ||
            !document->visible ||
            document->max <= document->min
        ) {
            continue;
        }

        bool hit = false;

        // EM_CHARFROMPOS normally resolves an OLE bitmap to the single U+FFFC
        // character representing it. Accept the exact character and the two
        // adjacent boundary positions because RichEdit differs by one at the
        // left/right edge depending on version and DPI scaling.
        if (hit_char >= 0) {
            for (int delta = -1; delta <= 1; delta++) {
                int candidate =
                    hit_char + delta;

                if (
                    candidate >= document->min &&
                    candidate <= document->max
                ) {
                    hit = true;
                    break;
                }
            }
        }

        // Fallback for RichEdit builds that return a nearby text character for
        // OLE content: the chat card is deliberately fixed at 112x84 at 96 DPI.
        // Use the application's current DPI so the rectangle follows Windows
        // scaling (e.g. 168x126 at 150%).
        if (!hit) {
            POINTL origin = {0, 0};

            LRESULT pos_result =
                SendMessageW(
                    chat,
                    EM_POSFROMCHAR,
                    (WPARAM)&origin,
                    (LPARAM)document->min
                );

            if (pos_result != -1) {
                int effective_dpi =
                    dpi > 0
                        ? dpi
                        : 96;

                int card_width =
                    MulDiv(
                        112,
                        effective_dpi,
                        96
                    );

                int card_height =
                    MulDiv(
                        84,
                        effective_dpi,
                        96
                    );

                RECT card = {
                    (LONG)origin.x,
                    (LONG)origin.y,
                    (LONG)origin.x + card_width,
                    (LONG)origin.y + card_height
                };

                hit =
                    PtInRect(
                        &card,
                        point
                    ) != FALSE;
            }
        }

        if (!hit)
            continue;

        // WM_LBUTTONDOWN already performs the action. Consume the subsequent
        // WM_LBUTTONDBLCLK notification so a fast double click cannot cancel,
        // restart, or open the same video twice.
        if (msg == WM_LBUTTONDBLCLK) {
            diag_log(
                "chat video direct mouse swallowed double click index=%d",
                i
            );
            return true;
        }

        bool started =
            media_chat_video_start_full_document(
                document
            );

        diag_log(
            "chat video direct mouse hit index=%d char=%d range=%d..%d started=%d path=%ls",
            i,
            hit_char,
            document->min,
            document->max,
            started ? 1 : 0,
            document->filename
                ? document->filename
                : L"(null)"
        );

        // Even on a failed start the click belongs to the video card. Consume
        // it so RichEdit cannot move the caret/select the OLE object instead.
        if (!started)
            MessageBeep(MB_ICONASTERISK);

        return true;
    }

    return false;
}
'''

s = s[:helper_end] + mouse_handler + s[helper_end:]
write(t, s)


# ---------------------------------------------------------------------------
# Header declaration for procs.cpp.
# ---------------------------------------------------------------------------

s = read(h)

if "media_chat_video_handle_chat_mouse(" not in s:
    anchor = "bool media_inline_audio_handle_chat_mouse(HWND hWnd, UINT msg, WPARAM wParam, LPARAM lParam);"

    if anchor not in s:
        raise SystemExit(
            "Could not locate inline-audio chat mouse declaration in telegacy.h."
        )

    s = s.replace(
        anchor,
        anchor
        + "\nbool media_chat_video_handle_chat_mouse(HWND hWnd, UINT msg, WPARAM wParam, LPARAM lParam);"
        + "\n// chat_video_direct_mouse_v59",
        1,
    )

write(h, s)


# ---------------------------------------------------------------------------
# Direct RichEdit mouse interception. This runs before the existing inline
# audio handler and before RichEdit/EN_LINK processing.
# ---------------------------------------------------------------------------

s = read(p)

if "chat_video_direct_mouse_proc_v59" not in s:
    signature = "LRESULT CALLBACK WndProcChat(HWND hWnd, UINT msg, WPARAM wParam, LPARAM lParam) {"
    pos = s.find(signature)

    if pos < 0:
        raise SystemExit("Could not locate WndProcChat in procs.cpp.")

    insert_pos = pos + len(signature)

    direct_mouse = r'''

    // chat_video_direct_mouse_proc_v59
    if (
        (
            msg == WM_LBUTTONDOWN ||
            msg == WM_LBUTTONDBLCLK
        ) &&
        media_chat_video_handle_chat_mouse(
            hWnd,
            msg,
            wParam,
            lParam
        )
    ) {
        return 0;
    }
'''

    s = s[:insert_pos] + direct_mouse + s[insert_pos:]

write(p, s)


# ---------------------------------------------------------------------------
# Verification.
# ---------------------------------------------------------------------------

checks = {
    h: [
        "chat_video_direct_mouse_v59",
        "media_chat_video_handle_chat_mouse(HWND hWnd",
    ],
    t: [
        "chat_video_direct_mouse_v59",
        "bool media_chat_video_start_full_document(",
        "bool media_chat_video_handle_chat_mouse(",
        "EM_CHARFROMPOS",
        "EM_POSFROMCHAR",
        "chat video direct mouse hit",
    ],
    p: [
        "chat_video_direct_mouse_proc_v59",
        "media_chat_video_handle_chat_mouse(",
    ],
}

for path, tokens in checks.items():
    data = read(path)
    for token in tokens:
        if token not in data:
            raise SystemExit(
                f"Chat video v5.9 verification failed in {path.name}: {token}"
            )

print(
    "Applied chat video v5.9: video OLE cards are hit-tested directly in "
    "WndProcChat and no longer depend on RichEdit EN_LINK notifications."
)
