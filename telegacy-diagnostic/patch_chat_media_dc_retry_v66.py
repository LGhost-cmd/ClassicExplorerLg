#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_chat_media_dc_retry_v66.py <Telegacy source directory>")

root = Path(sys.argv[1]).resolve()
t = root / "src" / "telegacy.cpp"
hp = root / "src" / "helpers.cpp"

for path in (t, hp):
    if not path.exists():
        raise SystemExit(f"Missing expected Telegacy file: {path}")


def read(path):
    return path.read_text(encoding="latin-1")


def write(path, data):
    path.write_text(data, encoding="latin-1", newline="\r\n")


if "chat_media_full_photo_v64" not in read(t):
    raise SystemExit("Chat full-photo v6.4 was not found. Run patch_chat_media_layout_v64.py first.")
if "chat_media_dc_retry_v66" in read(t):
    print("Chat media DC retry v6.6 already applied.")
    raise SystemExit(0)

# helpers.cpp: pass the actual connection selected by Telegacy into the full
# photo loader. This is essential after Telegram returns FILE_MIGRATE_X.
s = read(hp)
old = "bool media_chat_full_photo_begin(Document* document); // chat_media_full_photo_v64"
new = "bool media_chat_full_photo_begin(Document* document, DCInfo* dcInfo); // chat_media_full_photo_v64 chat_media_dc_retry_v66"
if old not in s:
    raise SystemExit("Could not locate chat full-photo forward declaration in helpers.cpp.")
s = s.replace(old, new, 1)

old = "if (media_chat_full_photo_begin(document))"
new = "if (media_chat_full_photo_begin(document, dcInfo))"
if old not in s:
    raise SystemExit("Could not locate get_photo full-photo interception call.")
s = s.replace(old, new, 1)
write(hp, s)

# telegacy.cpp: bind upload.getFile to the DCInfo that Telegacy selected. When
# rpc_error FILE_MIGRATE_X causes get_photo() to be called again with an active
# media DC, restart the same photo from offset 0 on that DC instead of silently
# returning because a transfer is already marked active.
s = read(t)

old = "static std::vector<BYTE> media_chat_full_photo_bytes;"
new = "static std::vector<BYTE> media_chat_full_photo_bytes;\nstatic DCInfo* media_chat_full_photo_dc = NULL; // chat_media_dc_retry_v66"
if old not in s:
    raise SystemExit("Could not locate chat full-photo state block.")
s = s.replace(old, new, 1)

old = "    media_chat_full_photo_bytes.clear();\n    memset(media_chat_full_photo_rpc_id, 0, 8);"
new = "    media_chat_full_photo_bytes.clear();\n    media_chat_full_photo_dc = NULL;\n    memset(media_chat_full_photo_rpc_id, 0, 8);"
if old not in s:
    raise SystemExit("Could not locate chat full-photo reset block.")
s = s.replace(old, new, 1)

old = "    BYTE unenc_query[192] = {0};\n    BYTE enc_query[216] = {0};\n    internal_header(unenc_query, true);"
new = "    if (!media_chat_full_photo_dc)\n        return false;\n\n    BYTE unenc_query[192] = {0};\n    BYTE enc_query[216] = {0};\n    internal_header(media_chat_full_photo_dc, unenc_query, true);"
if old not in s:
    raise SystemExit("Could not locate chat full-photo request header construction.")
s = s.replace(old, new, 1)

old = "    if (!convert_message(unenc_query, enc_query, offset, 0))\n        return false;\n\n    int sent = send_query(enc_query, offset + 24);"
new = "    if (!convert_message(media_chat_full_photo_dc, unenc_query, enc_query, offset, 0))\n        return false;\n\n    int sent = send_query(media_chat_full_photo_dc, enc_query, offset + 24);"
if old not in s:
    raise SystemExit("Could not locate chat full-photo encryption/send block.")
s = s.replace(old, new, 1)

old = '        "chat full photo request size=%c offset=%I64d expected=%I64d sent=%d",\n        media_chat_full_photo_size,\n        media_chat_full_photo_offset,\n        media_chat_full_photo_expected_size,\n        sent'
new = '        "chat full photo request dc=%d size=%c offset=%I64d expected=%I64d sent=%d",\n        media_chat_full_photo_dc ? media_chat_full_photo_dc->dc : -1,\n        media_chat_full_photo_size,\n        media_chat_full_photo_offset,\n        media_chat_full_photo_expected_size,\n        sent'
if old not in s:
    raise SystemExit("Could not locate chat full-photo request diagnostic.")
s = s.replace(old, new, 1)

old = "bool media_chat_full_photo_begin(Document* document) {"
new = "bool media_chat_full_photo_begin(Document* document, DCInfo* dcInfo) {"
if old not in s:
    raise SystemExit("Could not locate chat full-photo begin signature.")
s = s.replace(old, new, 1)

old = "        !document ||\n        !document->visible ||"
new = "        !document ||\n        !dcInfo ||\n        !document->visible ||"
if old not in s:
    raise SystemExit("Could not locate chat full-photo begin validation.")
s = s.replace(old, new, 1)

old = "    if (media_chat_full_photo_active)\n        return true;"
new = r'''    if (media_chat_full_photo_active) {
        bool same_photo =
            memcmp(document->id, media_chat_full_photo_id, 8) == 0 &&
            memcmp(document->access_hash, media_chat_full_photo_access_hash, 8) == 0;

        if (same_photo && media_chat_full_photo_dc != dcInfo) {
            // Telegram answered FILE_MIGRATE_X. The normal Telegacy rpc_error
            // path has now selected/authorized the target media DC and called
            // get_photo() again with that DCInfo. Restart this same photo there.
            media_chat_full_photo_dc = dcInfo;
            media_chat_full_photo_offset = 0;
            media_chat_full_photo_bytes.clear();
            memset(media_chat_full_photo_rpc_id, 0, 8);

            if (!media_chat_full_photo_send_chunk()) {
                diag_log(
                    "chat full photo DC retry failed dc=%d",
                    dcInfo->dc
                );
                media_chat_full_photo_reset(true);
                return false;
            }

            memcpy(
                document->photo_msg_id,
                media_chat_full_photo_rpc_id,
                8
            );

            diag_log(
                "chat full photo migrated retry dc=%d size=%c",
                dcInfo->dc,
                media_chat_full_photo_size
            );
        }

        // A different photo simply waits in the existing serial queue.
        return true;
    }'''
if old not in s:
    raise SystemExit("Could not locate chat full-photo active-transfer guard.")
s = s.replace(old, new, 1)

old = "    media_chat_full_photo_bytes.clear();\n    media_chat_full_photo_active = true;"
new = "    media_chat_full_photo_bytes.clear();\n    media_chat_full_photo_dc = dcInfo;\n    media_chat_full_photo_active = true;"
if old not in s:
    raise SystemExit("Could not locate chat full-photo begin state initialization.")
s = s.replace(old, new, 1)

# Audit marker near the existing full-photo marker.
marker = "// chat_media_full_photo_v64"
if marker not in s:
    raise SystemExit("Could not locate chat full-photo v6.4 marker.")
s = s.replace(marker, marker + "\n// chat_media_dc_retry_v66", 1)
write(t, s)

checks = {
    hp: [
        "media_chat_full_photo_begin(Document* document, DCInfo* dcInfo)",
        "media_chat_full_photo_begin(document, dcInfo)",
    ],
    t: [
        "chat_media_dc_retry_v66",
        "static DCInfo* media_chat_full_photo_dc = NULL",
        "internal_header(media_chat_full_photo_dc, unenc_query, true)",
        "convert_message(media_chat_full_photo_dc, unenc_query, enc_query, offset, 0)",
        "send_query(media_chat_full_photo_dc, enc_query, offset + 24)",
        "chat full photo migrated retry dc=%d size=%c",
    ],
}
for path, tokens in checks.items():
    data = read(path)
    for token in tokens:
        if token not in data:
            raise SystemExit(f"Chat media DC retry v6.6 verification failed in {path.name}: {token}")

print(
    "Applied chat media DC retry v6.6: full chat photos now follow Telegacy's "
    "FILE_MIGRATE media-DC retry path instead of stalling the serial image queue."
)
