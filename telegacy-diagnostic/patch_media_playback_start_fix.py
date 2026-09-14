#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_media_playback_start_fix.py <Telegacy source directory>")

root = Path(sys.argv[1]).resolve()
t = root / "src" / "telegacy.cpp"

if not t.exists():
    raise SystemExit(f"Missing expected Telegacy file: {t}")


def read(p):
    return p.read_text(encoding="latin-1")


def write(p, s):
    p.write_text(s, encoding="latin-1", newline="\r\n")


def function_range(source, signature):
    start = source.find(signature)
    if start < 0:
        raise SystemExit(f"Could not locate C++ function: {signature}")

    brace = source.find("{", start)
    if brace < 0:
        raise SystemExit(f"Could not locate opening brace: {signature}")

    depth = 0
    in_string = False
    in_char = False
    in_line_comment = False
    in_block_comment = False
    escaped = False
    i = brace

    while i < len(source):
        c = source[i]
        n = source[i + 1] if i + 1 < len(source) else ""

        if in_line_comment:
            if c == "\n":
                in_line_comment = False
            i += 1
            continue

        if in_block_comment:
            if c == "*" and n == "/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue

        if in_string:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == '"':
                in_string = False
            i += 1
            continue

        if in_char:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == "'":
                in_char = False
            i += 1
            continue

        if c == "/" and n == "/":
            in_line_comment = True
            i += 2
            continue

        if c == "/" and n == "*":
            in_block_comment = True
            i += 2
            continue

        if c == '"':
            in_string = True
            i += 1
            continue

        if c == "'":
            in_char = True
            i += 1
            continue

        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return start, i + 1

        i += 1

    raise SystemExit(f"Could not locate closing brace: {signature}")


def replace_function(source, signature, replacement):
    start, end = function_range(source, signature)
    return source[:start] + replacement + source[end:]


s = read(t)

if "media_playback_start_runtime_v57" in s:
    print("Media playback-start v5.7 fix already applied.")
    raise SystemExit(0)

for required in (
    "media_tabs_av_runtime_v56",
    "media_inline_audio_requested_play_state",
    "media_inline_audio_timer_proc(",
    "bool media_play_request =",
):
    if required not in s:
        raise SystemExit(
            f"Required Media A/V runtime token was not found: {required}"
        )

marker = "// media_tabs_av_runtime_v56"
s = s.replace(
    marker,
    marker + "\n// media_playback_start_runtime_v57",
    1,
)

timer_v57 = r'''static VOID CALLBACK media_inline_audio_timer_proc(
    HWND,
    UINT,
    UINT_PTR,
    DWORD
) {
    if (!media_inline_audio) {
        if (media_inline_audio_timer) {
            KillTimer(NULL, media_inline_audio_timer);
            media_inline_audio_timer = 0;
        }
        return;
    }

    MFP_MEDIAPLAYER_STATE state =
        MFP_MEDIAPLAYER_STATE_EMPTY;

    if (FAILED(media_inline_audio->GetState(&state)))
        return;

    // MFPlay changes state asynchronously. On the first Play() the backend
    // can still report EMPTY/STOPPED when this timer fires. Keep polling while
    // a Play request is pending so elapsed time/progress starts as soon as the
    // backend actually enters PLAYING instead of freezing at 00:00.
    media_inline_audio_apply_visual(false);

    bool play_transition_pending =
        media_inline_audio_requested_play_state == 1;

    if (
        state != MFP_MEDIAPLAYER_STATE_PLAYING &&
        state != MFP_MEDIAPLAYER_STATE_PAUSED &&
        !play_transition_pending
    ) {
        media_inline_audio_apply_visual(true);

        if (media_inline_audio_timer) {
            KillTimer(NULL, media_inline_audio_timer);
            media_inline_audio_timer = 0;
        }
    }
}'''

s = replace_function(
    s,
    "static VOID CALLBACK media_inline_audio_timer_proc(",
    timer_v57,
)

old_play_request = '''                    bool media_play_request =
                        (media_kind == 2 && !media_double_click) ||
                        (media_kind == 1 && media_double_click);'''

new_play_request = '''                    // Unified chat media cards behave like links: one click plays.
                    // Ignore the follow-up double-click notification so video is not
                    // opened twice after the first click has already started it.
                    bool media_play_request =
                        (media_kind == 2 && !media_double_click) ||
                        (media_kind == 1 && !media_double_click);'''

if old_play_request not in s:
    raise SystemExit(
        "Could not locate Media chat click policy for the v5.7 video fix."
    )

s = s.replace(old_play_request, new_play_request, 1)

write(t, s)

check = read(t)
for token in (
    "media_playback_start_runtime_v57",
    "bool play_transition_pending =",
    "media_inline_audio_requested_play_state == 1",
    "(media_kind == 1 && !media_double_click)",
):
    if token not in check:
        raise SystemExit(f"Media v5.7 verification failed: {token}")

print(
    "Applied Media playback-start v5.7: keep inline-audio timer alive during "
    "the asynchronous first Play transition and open in-chat video cards on "
    "a single click."
)
