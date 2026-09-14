#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_chat_media_layout_v61.py <Telegacy source directory>")

root = Path(sys.argv[1]).resolve()
repo_root = Path(__file__).resolve().parent.parent

# Preserve the tested v6.2 layout/HQ-thumbnail patch, then layer the v6.3
# full-photo chat loader on top. The workflow checks out full helper history.
V62_BLOB_SHA = "a1615b1495e524d764f78ff25943240b4f9f06c6"

try:
    source = subprocess.check_output(
        ["git", "cat-file", "blob", V62_BLOB_SHA],
        cwd=str(repo_root),
        stderr=subprocess.STDOUT,
    ).decode("utf-8")
except Exception as exc:
    raise SystemExit(
        "Could not obtain the pinned chat media v6.2 patch "
        f"({V62_BLOB_SHA}) from local git history: {exc}"
    )

old_argv = sys.argv[:]
namespace = {
    "__name__": "__main__",
    "__file__": "patch_chat_media_layout_v62_pinned.py",
}

try:
    sys.argv = [
        "patch_chat_media_layout_v62_pinned.py",
        str(root),
    ]
    try:
        exec(
            compile(
                source,
                "patch_chat_media_layout_v62_pinned.py",
                "exec",
            ),
            namespace,
            namespace,
        )
    except SystemExit as exc:
        if exc.code not in (None, 0):
            raise
finally:
    sys.argv = old_argv

h = root / "include" / "telegacy.h"
t = root / "src" / "telegacy.cpp"
hp = root / "src" / "helpers.cpp"
r = root / "src" / "response.cpp"

for path in (h, t, hp, r):
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


if "chat_media_hq_preview_v62" not in read(t):
    raise SystemExit(
        "Pinned chat media v6.2 patch finished, but its marker was not found."
    )
if "chat_media_full_photo_v63" in read(t):
    print("Chat full-photo v6.3 already applied.")
    raise SystemExit(0)

# ---------------------------------------------------------------------------
# Public cross-file hooks.
# ---------------------------------------------------------------------------
s = read(h)
anchor = "HBITMAP media_chat_make_photo_card(HBITMAP source);"
if anchor not in s:
    raise SystemExit("Could not locate chat photo-card declaration in telegacy.h.")

extra = (
    "\nbool media_chat_full_photo_begin(Document* document);"
    "\nbool media_chat_full_photo_handle_upload(const BYTE* rpc_id, BYTE* response, int length);"
    " // chat_media_full_photo_v63"
)
if "media_chat_full_photo_begin(Document* document);" not in s:
    s = s.replace(anchor, anchor + extra, 1)
write(h, s)

# ---------------------------------------------------------------------------
# telegacy.cpp: use the same inputPhotoFileLocation + 1 MiB chunk strategy as
# Media's full-photo downloader, but decode into the chat card instead of
# opening an external viewer. Only one chat photo is active at once; existing
# chat loading already advances serially, and after completion we explicitly
# start the next unrequested visible photo.
# ---------------------------------------------------------------------------
s = read(t)
insert_pos = s.find("static void media_player_queue_chat_autoplay(")
if insert_pos < 0:
    raise SystemExit("Could not locate chat media helper insertion point.")

full_loader = r'''
// chat_media_full_photo_v63
static bool media_chat_full_photo_active = false;
static BYTE media_chat_full_photo_rpc_id[8] = {0};
static BYTE media_chat_full_photo_id[8] = {0};
static BYTE media_chat_full_photo_access_hash[8] = {0};
static BYTE* media_chat_full_photo_file_reference = NULL;
static char media_chat_full_photo_size = 0;
static LONGLONG media_chat_full_photo_expected_size = 0;
static LONGLONG media_chat_full_photo_offset = 0;
static std::vector<BYTE> media_chat_full_photo_bytes;

static void media_chat_full_photo_reset(
    bool allow_retry
) {
    if (allow_retry) {
        for (int i = 0; i < (int)documents.size(); i++) {
            if (
                memcmp(documents[i].id, media_chat_full_photo_id, 8) == 0 &&
                memcmp(documents[i].access_hash, media_chat_full_photo_access_hash, 8) == 0
            ) {
                memset(documents[i].photo_msg_id, 0, 8);
                break;
            }
        }
    }

    free(media_chat_full_photo_file_reference);
    media_chat_full_photo_file_reference = NULL;
    media_chat_full_photo_active = false;
    media_chat_full_photo_size = 0;
    media_chat_full_photo_expected_size = 0;
    media_chat_full_photo_offset = 0;
    media_chat_full_photo_bytes.clear();
    memset(media_chat_full_photo_rpc_id, 0, 8);
    memset(media_chat_full_photo_id, 0, 8);
    memset(media_chat_full_photo_access_hash, 0, 8);
}

static bool media_chat_full_photo_send_chunk() {
    if (
        !media_chat_full_photo_active ||
        !media_chat_full_photo_file_reference ||
        !media_chat_full_photo_size
    ) {
        return false;
    }

    BYTE unenc_query[192] = {0};
    BYTE enc_query[216] = {0};

    internal_header(
        unenc_query,
        true
    );

    memcpy(
        media_chat_full_photo_rpc_id,
        unenc_query + 16,
        8
    );

    // upload.getFile#be5335be
    write_le(unenc_query + 32, 0xbe5335be, 4);
    write_le(unenc_query + 36, 0, 4);

    // inputPhotoFileLocation#40181ffe -- identical to Media full photos.
    write_le(unenc_query + 40, 0x40181ffe, 4);
    memcpy(unenc_query + 44, media_chat_full_photo_id, 8);
    memcpy(unenc_query + 52, media_chat_full_photo_access_hash, 8);

    int file_ref_len =
        tlstr_len(
            media_chat_full_photo_file_reference,
            true
        );

    if (
        file_ref_len <= 0 ||
        60 + file_ref_len + 16 > (int)sizeof(unenc_query)
    ) {
        return false;
    }

    memcpy(
        unenc_query + 60,
        media_chat_full_photo_file_reference,
        file_ref_len
    );

    int offset = 60 + file_ref_len;

    // Request the largest PhotoSize parsed from the message, not a thumbnail.
    memset(unenc_query + offset, 0, 12);
    unenc_query[offset] = 1;
    unenc_query[offset + 1] =
        (BYTE)media_chat_full_photo_size;

    write_le(
        unenc_query + offset + 4,
        media_chat_full_photo_offset,
        8
    );
    offset += 12;

    write_le(unenc_query + offset, 1048576, 4);
    offset += 4;

    write_le(unenc_query + 28, offset - 32, 4);

    int padding_len = get_padding(offset);
    fortuna_read(unenc_query + offset, padding_len, &prng);
    offset += padding_len;

    if (!convert_message(
        unenc_query,
        enc_query,
        offset,
        0
    )) {
        return false;
    }

    int sent =
        send_query(
            enc_query,
            offset + 24
        );

    diag_log(
        "chat full photo request size=%c offset=%I64d expected=%I64d sent=%d",
        media_chat_full_photo_size,
        media_chat_full_photo_offset,
        media_chat_full_photo_expected_size,
        sent
    );

    return sent > 0;
}

bool media_chat_full_photo_begin(
    Document* document
) {
    if (
        !document ||
        !document->visible ||
        !document->file_reference ||
        document->photo_size == 0 ||
        document->photo_size == 1 ||
        document->photo_size == 3
    ) {
        return false;
    }

    // A current full-photo transfer owns the single serial slot. The caller's
    // document remains unmarked, so completion scanning will pick it next.
    if (media_chat_full_photo_active)
        return true;

    int file_ref_len =
        tlstr_len(
            document->file_reference,
            true
        );

    if (file_ref_len <= 0)
        return false;

    media_chat_full_photo_file_reference =
        (BYTE*)malloc(file_ref_len);

    if (!media_chat_full_photo_file_reference)
        return false;

    memcpy(
        media_chat_full_photo_file_reference,
        document->file_reference,
        file_ref_len
    );
    memcpy(media_chat_full_photo_id, document->id, 8);
    memcpy(media_chat_full_photo_access_hash, document->access_hash, 8);

    media_chat_full_photo_size = document->photo_size;
    media_chat_full_photo_expected_size = document->size;
    media_chat_full_photo_offset = 0;
    media_chat_full_photo_bytes.clear();
    media_chat_full_photo_active = true;

    if (!media_chat_full_photo_send_chunk()) {
        media_chat_full_photo_reset(false);
        return false;
    }

    // Non-zero means "already requested" to Telegacy's existing serial loader.
    memcpy(
        document->photo_msg_id,
        media_chat_full_photo_rpc_id,
        8
    );

    return true;
}

bool media_chat_full_photo_handle_upload(
    const BYTE* rpc_id,
    BYTE* response,
    int length
) {
    if (
        !media_chat_full_photo_active ||
        !rpc_id ||
        !response ||
        length < 13 ||
        memcmp(
            rpc_id,
            media_chat_full_photo_rpc_id,
            8
        ) != 0
    ) {
        return false;
    }

    int size =
        tlstr_len(
            response + 12,
            false
        );

    int prefix =
        size >= 254
            ? 4
            : 1;

    int data_pos = 12 + prefix;

    if (
        size < 0 ||
        data_pos < 0 ||
        data_pos + size > length
    ) {
        diag_log(
            "chat full photo malformed upload.file size=%d length=%d",
            size,
            length
        );
        media_chat_full_photo_reset(true);
        return true;
    }

    if (size > 0) {
        media_chat_full_photo_bytes.insert(
            media_chat_full_photo_bytes.end(),
            response + data_pos,
            response + data_pos + size
        );
    }

    media_chat_full_photo_offset += size;

    bool more =
        size >= 1048576 &&
        (
            media_chat_full_photo_expected_size <= 0 ||
            media_chat_full_photo_offset <
                media_chat_full_photo_expected_size
        );

    if (more) {
        if (!media_chat_full_photo_send_chunk()) {
            diag_log("chat full photo next chunk failed");
            media_chat_full_photo_reset(true);
        }
        return true;
    }

    int target = -1;

    for (int i = 0; i < (int)documents.size(); i++) {
        if (
            documents[i].visible &&
            memcmp(documents[i].id, media_chat_full_photo_id, 8) == 0 &&
            memcmp(documents[i].access_hash, media_chat_full_photo_access_hash, 8) == 0
        ) {
            target = i;
            break;
        }
    }

    diag_log(
        "chat full photo complete bytes=%I64d expected=%I64d target=%d",
        media_chat_full_photo_offset,
        media_chat_full_photo_expected_size,
        target
    );

    if (
        target >= 0 &&
        !media_chat_full_photo_bytes.empty()
    ) {
        HBITMAP full_bitmap =
            jpg_to_bmp(
                &media_chat_full_photo_bytes[0],
                (int)media_chat_full_photo_bytes.size()
            );

        if (full_bitmap) {
            CHARRANGE cr;
            cr.cpMin = documents[target].min;
            cr.cpMax = documents[target].max;

            replace_in_chat(
                NULL,
                &cr,
                NULL,
                full_bitmap,
                NULL,
                NULL,
                NULL
            );

            DeleteObject(full_bitmap);
        } else {
            diag_log("chat full photo JPEG decode failed");
        }
    }

    // Keep the completed document marked as requested, then release transfer
    // storage before starting the next zero-id chat photo.
    media_chat_full_photo_reset(false);

    if (IMAGELOADPOLICY != 0) {
        for (int i = (int)documents.size() - 1; i >= 0; i--) {
            if (
                documents[i].visible &&
                documents[i].photo_size != 0 &&
                documents[i].photo_size != 1 &&
                documents[i].photo_size != 3 &&
                documents[i].file_reference &&
                !read_le(documents[i].photo_msg_id, 8)
            ) {
                get_photo(
                    NULL,
                    &documents[i],
                    &dcInfoMain
                );
                break;
            }
        }
    }

    return true;
}

'''

s = s[:insert_pos] + full_loader + s[insert_pos:]
write(t, s)

# ---------------------------------------------------------------------------
# helpers.cpp: normal visible chat photos bypass get_photo()'s thumbnail path
# completely. Stickers, custom emoji and video/document thumbnails retain the
# original implementation.
# ---------------------------------------------------------------------------
s = read(hp)
start, end = function_range(s, "void get_photo(")
func = s[start:end]
brace = func.find("{")
if brace < 0:
    raise SystemExit("Could not locate get_photo opening brace.")

intercept = r'''

    // chat_media_full_photo_v63
    if (
        !rce &&
        document &&
        document->visible &&
        document->photo_size != 0 &&
        document->photo_size != 1 &&
        document->photo_size != 3 &&
        IMAGELOADPOLICY != 0
    ) {
        if (media_chat_full_photo_begin(document))
            return;
    }
'''

func = func[:brace + 1] + intercept + func[brace + 1:]
s = s[:start] + func + s[end:]
write(hp, s)

# ---------------------------------------------------------------------------
# response.cpp: claim our upload.file RPC before Media's independent full-photo
# state and before the legacy thumbnail/document branches.
# ---------------------------------------------------------------------------
s = read(r)
anchor = '''        // media_tabs_av_response_v3
        if (
            media_archive_handle_full_photo_upload('''
if anchor not in s:
    raise SystemExit("Could not locate Media full-photo upload handler.")

chat_handler = r'''        // chat_media_full_photo_response_v63
        if (
            media_chat_full_photo_handle_upload(
                last_rpcresult_msgid,
                unenc_response,
                length
            )
        ) {
            break;
        }

'''

s = s.replace(anchor, chat_handler + anchor, 1)
write(r, s)

# Marker is kept in telegacy.cpp for artifact verification.
s = read(t)
marker = "// chat_media_hq_preview_v62"
if marker not in s:
    raise SystemExit("Could not locate v6.2 marker in telegacy.cpp.")
# The loader block itself already contains the marker; no second marker needed.
write(t, s)

checks = {
    h: [
        "media_chat_full_photo_begin(Document* document);",
        "media_chat_full_photo_handle_upload(const BYTE* rpc_id, BYTE* response, int length);",
    ],
    hp: [
        "chat_media_full_photo_v63",
        "media_chat_full_photo_begin(document)",
    ],
    r: [
        "chat_media_full_photo_response_v63",
        "media_chat_full_photo_handle_upload(",
    ],
    t: [
        "chat_media_full_photo_v63",
        "inputPhotoFileLocation#40181ffe -- identical to Media full photos",
        "media_chat_full_photo_send_chunk()",
        "media_chat_full_photo_bytes.insert(",
        "jpg_to_bmp(",
        "replace_in_chat(",
    ],
}

for path, tokens in checks.items():
    data = read(path)
    for token in tokens:
        if token not in data:
            raise SystemExit(
                f"Chat full-photo v6.3 verification failed in "
                f"{path.name}: {token}"
            )

print(
    "Applied chat media v6.3: normal visible chat photos now use the same "
    "chunked full PhotoSize download strategy as Media, then render the full "
    "JPEG into the existing 288x216 framed chat card."
)
