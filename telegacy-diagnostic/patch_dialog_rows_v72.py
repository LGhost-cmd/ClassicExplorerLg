#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_dialog_rows_v72.py <Telegacy source directory>")

root = Path(sys.argv[1]).resolve()
hdr = root / "include" / "telegacy.h"
t = root / "src" / "telegacy.cpp"
r = root / "src" / "response.cpp"

for p in (hdr, t, r):
    if not p.exists():
        raise SystemExit(f"Missing expected Telegacy file: {p}")


def read(p):
    return p.read_text(encoding="latin-1")


def write(p, s):
    p.write_text(s, encoding="latin-1", newline="\r\n")


if "dialog_rows_v72" in read(t):
    print("Dialog row fix v7.2 already applied.")
    raise SystemExit(0)

# The earlier Media patch already introduced a non-destructive phantom-row
# hider, but its validity test accepted any non-NUL wchar and it was not
# guaranteed to run after every dialog slice. Modern/unsupported Telegram peer
# data can therefore produce a full-height combo row whose name is empty,
# whitespace, a zero-width character, or U+FFFD.
s = read(t)
old_predicate = r'''static bool telegacy_chat_combo_peer_is_named(
    Peer* peer
) {
    if (!peer || peer == (Peer*)CB_ERR)
        return false;

    bool known = false;

    for (int i = 0; i < peers_count; i++) {
        if (peer == &peers[i]) {
            known = true;
            break;
        }
    }

    return
        known &&
        peer->name &&
        peer->name[0];
}'''

new_predicate = r'''static bool telegacy_chat_combo_peer_is_named(
    Peer* peer
) {
    if (!peer || peer == (Peer*)CB_ERR)
        return false;

    bool known = false;

    for (int i = 0; i < peers_count; i++) {
        if (peer == &peers[i]) {
            known = true;
            break;
        }
    }

    if (!known || !peer->name)
        return false;

    // dialog_rows_v72: a technically non-empty string can still render as a
    // completely blank row (control/space/zero-width/replacement characters).
    // Require at least one visibly renderable code unit. Surrogate-based emoji
    // and ordinary non-Latin names pass this test normally.
    for (int i = 0; i < 256 && peer->name[i]; i++) {
        wchar_t c = peer->name[i];
        if (
            c > 0x20 &&
            c != 0x7F &&
            c != 0xFFFD &&
            c != 0x200B &&
            c != 0x200C &&
            c != 0x200D &&
            c != 0xFEFF
        ) {
            return true;
        }
    }

    return false;
}'''

if old_predicate not in s:
    raise SystemExit("Could not locate phantom-chat row predicate from Media patch.")
s = s.replace(old_predicate, new_predicate, 1)

old_hide_sig = "static void telegacy_hide_phantom_chat_rows() {"
new_hide_sig = "void telegacy_hide_phantom_chat_rows() { // dialog_rows_v72"
if old_hide_sig not in s:
    raise SystemExit("Could not locate phantom-chat row hider.")
s = s.replace(old_hide_sig, new_hide_sig, 1)
write(t, s)

# Export the refresh helper so the network response boundary can refresh row
# heights whenever a new dialog slice, peer update, or folder update arrives.
s = read(hdr)
anchor = "extern wchar_t status_str[100];"
if anchor not in s:
    raise SystemExit("Could not locate dialog-row declaration anchor in telegacy.h.")
s = s.replace(
    anchor,
    anchor + "\nvoid telegacy_hide_phantom_chat_rows(); // dialog_rows_v72",
    1,
)
write(hdr, s)

# v7.1 wraps the full response parser. Refresh the combo after every successful
# packet rather than trying to guess which Telegram constructor changed dialogs.
s = read(r)
anchor = r'''        response_handler_unsafe(
            dcInfo,
            unenc_response,
            acknowledgement,
            length
        );'''
replacement = anchor + r'''

        // dialog_rows_v72: collapse invalid/visually-empty peers immediately
        // after any response which may have changed the dialog list.
        telegacy_hide_phantom_chat_rows();'''
if s.count(anchor) != 1:
    raise SystemExit(f"Expected one v7.1 response call site, found {s.count(anchor)}.")
s = s.replace(anchor, replacement, 1)
write(r, s)

checks = {
    hdr: ["telegacy_hide_phantom_chat_rows(); // dialog_rows_v72"],
    t: [
        "dialog_rows_v72",
        "void telegacy_hide_phantom_chat_rows()",
        "c != 0xFFFD",
        "c != 0x200B",
    ],
    r: [
        "dialog_rows_v72: collapse invalid/visually-empty peers immediately",
        "telegacy_hide_phantom_chat_rows();",
    ],
}
for p, tokens in checks.items():
    data = read(p)
    for token in tokens:
        if token not in data:
            raise SystemExit(f"Dialog row v7.2 verification failed in {p.name}: {token}")

print(
    "Applied dialog row v7.2: visually empty/invalid peer names collapse to a "
    "1-pixel non-content row and the dialog combo is refreshed after every "
    "successful Telegram response, preventing full-height blank selections."
)
