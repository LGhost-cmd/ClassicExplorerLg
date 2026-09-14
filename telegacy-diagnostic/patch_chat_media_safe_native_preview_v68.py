#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_chat_media_safe_native_preview_v68.py <Telegacy source directory>")

root = Path(sys.argv[1]).resolve()
hp = root / "src" / "helpers.cpp"
t = root / "src" / "telegacy.cpp"
for path in (hp, t):
    if not path.exists():
        raise SystemExit(f"Missing expected Telegacy file: {path}")


def read(path):
    return path.read_text(encoding="latin-1")


def write(path, data):
    path.write_text(data, encoding="latin-1", newline="\r\n")


def function_range(source, signature):
    start = source.find(signature)
    if start < 0:
        raise SystemExit(f"Could not locate C++ function: {signature}")
    brace = source.find("{", start)
    if brace < 0:
        raise SystemExit(f"Could not locate opening brace: {signature}")
    depth = 0
    in_string = in_char = in_line = in_block = escaped = False
    i = brace
    while i < len(source):
        c = source[i]
        n = source[i + 1] if i + 1 < len(source) else ""
        if in_line:
            if c == "\n":
                in_line = False
            i += 1
            continue
        if in_block:
            if c == "*" and n == "/":
                in_block = False
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
            in_line = True
            i += 2
            continue
        if c == "/" and n == "*":
            in_block = True
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


s = read(hp)
if "chat_media_safe_native_preview_v68" in s:
    print("Chat safe native preview v6.8 already applied.")
    raise SystemExit(0)
if "chat_media_native_preview_v67" not in s:
    raise SystemExit("Chat native preview v6.7 was not found. Run v6.7 first.")

start, end = function_range(
    s,
    "void get_photo(RequestedCustomEmoji* rce, Document* document, DCInfo* dcInfo)"
)
old = s[start:end]
if "BYTE unenc_query[144]" not in old or "BYTE enc_query[168]" not in old:
    raise SystemExit("Expected legacy 144/168-byte get_photo buffers were not found.")

new = r'''void get_photo(RequestedCustomEmoji* rce, Document* document, DCInfo* dcInfo) {
    // chat_media_safe_native_preview_v68
    // Telegram file_reference values are opaque TL byte strings and can be
    // longer than the tiny fixed buffer used by Telegacy 1.0.4. Keep the
    // native Media/get_photo transport, but build it in a bounded buffer and
    // reject malformed/oversized references instead of overrunning the stack.
    if (!dcInfo || (!rce && !document)) {
        diag_log("get_photo v68 skipped: invalid request context");
        return;
    }

    BYTE* file_reference = rce ? rce->file_reference : document->file_reference;
    if (!file_reference) {
        diag_log("get_photo v68 skipped: null file_reference");
        return;
    }

    int fileref_len = tlstr_len(file_reference, true);
    const int query_capacity = 1024;
    BYTE unenc_query[query_capacity] = {0};
    BYTE enc_query[query_capacity + 24] = {0};

    // 60 bytes precede file_reference; reserve the 12-byte location suffix,
    // 4-byte limit and up to 16 bytes of MTProto padding after it.
    if (fileref_len <= 0 || 60 + fileref_len + 12 + 4 + 16 > query_capacity) {
        diag_log("get_photo v68 skipped: unsafe file_reference TL length=%d", fileref_len);
        return;
    }

    internal_header(dcInfo, unenc_query, true);
    memcpy(rce ? rce->msg_id : document->photo_msg_id, unenc_query + 16, 8);
    write_le(unenc_query + 32, 0xbe5335be, 4);
    write_le(unenc_query + 36, 0, 4);
    write_le(
        unenc_query + 40,
        (rce || document->photo_size == 1 || document->photo_size == 3)
            ? 0xbad07584
            : 0x40181ffe,
        4
    );
    memcpy(unenc_query + 44, rce ? (BYTE*)&rce->id : document->id, 8);
    memcpy(unenc_query + 52, rce ? (BYTE*)&rce->access_hash : document->access_hash, 8);
    memcpy(unenc_query + 60, file_reference, fileref_len);

    int offset_query = 60 + fileref_len;
    memset(unenc_query + offset_query, 0, 12);
    unenc_query[offset_query] = 1;
    unenc_query[offset_query + 1] = 'm';
    offset_query += 12;

    write_le(unenc_query + offset_query, 1048576, 4);
    offset_query += 4;
    write_le(unenc_query + 28, offset_query - 32, 4);

    int padding_len = get_padding(offset_query);
    if (padding_len < 0 || offset_query + padding_len > query_capacity) {
        diag_log(
            "get_photo v68 skipped: unsafe padded request len=%d padding=%d",
            offset_query,
            padding_len
        );
        memset(rce ? rce->msg_id : document->photo_msg_id, 0, 8);
        return;
    }

    fortuna_read(unenc_query + offset_query, padding_len, &prng);
    offset_query += padding_len;

    if (!convert_message(dcInfo, unenc_query, enc_query, offset_query, 0)) {
        diag_log("get_photo v68 convert_message failed dc=%d", dcInfo->dc);
        memset(rce ? rce->msg_id : document->photo_msg_id, 0, 8);
        return;
    }

    int sent = send_query(dcInfo, enc_query, offset_query + 24);
    if (sent <= 0) {
        diag_log("get_photo v68 send_query failed dc=%d len=%d", dcInfo->dc, offset_query + 24);
        memset(rce ? rce->msg_id : document->photo_msg_id, 0, 8);
        return;
    }

    diag_log(
        "get_photo v68 sent dc=%d fileref_tl=%d request=%d kind=%d",
        dcInfo->dc,
        fileref_len,
        offset_query + 24,
        rce ? -1 : (int)(unsigned char)document->photo_size
    );
}'''

s = s[:start] + new + s[end:]
write(hp, s)

s = read(t)
anchor = "// chat_media_native_preview_v67"
if anchor not in s:
    raise SystemExit("Could not locate v6.7 marker for v6.8 audit marker.")
s = s.replace(anchor, anchor + "\n// chat_media_safe_native_preview_v68", 1)
write(t, s)

checks = {
    hp: [
        "chat_media_safe_native_preview_v68",
        "BYTE unenc_query[query_capacity] = {0};",
        "unsafe file_reference TL length",
        "get_photo v68 sent",
    ],
    t: ["chat_media_safe_native_preview_v68"],
}
for path, tokens in checks.items():
    data = read(path)
    for token in tokens:
        if token not in data:
            raise SystemExit(
                f"Chat safe native preview v6.8 verification failed in {path.name}: {token}"
            )

print(
    "Applied chat safe native preview v6.8: Telegacy's native get_photo path now "
    "uses bounded 1024-byte request buffers, validates opaque Telegram "
    "file_reference lengths, and logs/aborts malformed requests instead of "
    "overrunning the stack."
)
