#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_chat_animated_sticker_stability_v83.py <Telegacy source directory>")

root = Path(sys.argv[1]).resolve()
t = root / "src" / "telegacy.cpp"

if not t.exists():
    raise SystemExit(f"Missing expected Telegacy file: {t}")


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
    in_string = False
    in_char = False
    in_line = False
    in_block = False
    escaped = False
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


s = read(t)

if "chat_animated_sticker_stability_v83" in s:
    print("Animated sticker stability v8.3 already applied.")
    raise SystemExit(0)

for token in (
    "chat_animated_stickers_v82",
    "media_chat_sticker_cache_path(",
    "media_chat_animated_sticker_queue(",
    "media_chat_sticker_timer_proc(",
):
    if token not in s:
        raise SystemExit(f"Required v8.2 marker/function missing: {token}")


# ---------------------------------------------------------------------------
# 1) Cache path: appdata_path is a mutable Telegacy scratch path.
# get_path() rewrites its last component, so at runtime it can be
# ...\session.dat, ...\options.ini, etc. v8.2 incorrectly appended a directory
# to that full filename, producing:
#   ...\session.dat\animated_stickers\123.webm
# Derive the parent directory first and never mutate appdata_path here.
# ---------------------------------------------------------------------------
cs, ce = function_range(
    s,
    "static bool media_chat_sticker_cache_path("
)

cache_func = r'''// chat_animated_sticker_stability_v83
static bool media_chat_sticker_cache_path(
    const Document* document,
    int kind,
    wchar_t* out,
    int out_count
) {
    if (
        !document ||
        !out ||
        out_count < 32 ||
        !appdata_path[0]
    ) {
        return false;
    }

    wchar_t base[MAX_PATH] = {0};

    wcsncpy(
        base,
        appdata_path,
        ARRAYSIZE(base) - 1
    );

    base[ARRAYSIZE(base) - 1] = 0;

    wchar_t* last_slash =
        wcsrchr(
            base,
            L'\\'
        );

    if (!last_slash) {
        diag_log(
            "chat v83 sticker cache rejected appdata path=%ls",
            appdata_path
        );
        return false;
    }

    *last_slash = 0;

    wchar_t folder[MAX_PATH] = {0};

    int folder_chars =
        _snwprintf(
            folder,
            ARRAYSIZE(folder) - 1,
            L"%s\\animated_stickers",
            base
        );

    folder[ARRAYSIZE(folder) - 1] = 0;

    if (
        folder_chars <= 0 ||
        folder_chars >=
            ARRAYSIZE(folder) - 1
    ) {
        diag_log(
            "chat v83 sticker cache folder path too long"
        );
        return false;
    }

    DWORD attrs =
        GetFileAttributesW(
            folder
        );

    if (
        attrs ==
        INVALID_FILE_ATTRIBUTES
    ) {
        if (
            !CreateDirectoryW(
                folder,
                NULL
            ) &&
            GetLastError() !=
                ERROR_ALREADY_EXISTS
        ) {
            diag_log(
                "chat v83 sticker cache mkdir failed error=%u folder=%ls",
                (unsigned int)GetLastError(),
                folder
            );
            return false;
        }
    } else if (
        !(attrs & FILE_ATTRIBUTE_DIRECTORY)
    ) {
        diag_log(
            "chat v83 sticker cache path is not a directory folder=%ls",
            folder
        );
        return false;
    }

    const wchar_t* extension =
        kind == 2
            ? L".webm"
            : L".tgs";

    int path_chars =
        _snwprintf(
            out,
            out_count - 1,
            L"%s\\%016I64X%s",
            folder,
            (unsigned __int64)read_le(
                (BYTE*)document->id,
                8
            ),
            extension
        );

    out[out_count - 1] = 0;

    if (
        path_chars <= 0 ||
        path_chars >= out_count - 1
    ) {
        diag_log(
            "chat v83 sticker cache file path too long"
        );
        out[0] = 0;
        return false;
    }

    return true;
}'''

s = s[:cs] + cache_func + s[ce:]


# ---------------------------------------------------------------------------
# 2) Queue hardening: reject malformed/oversized sticker metadata and prove the
# cache file can actually be created BEFORE registering an asynchronous
# downloading_docs entry. This prevents the legacy downloader from retrying
# forever against an impossible filename.
# ---------------------------------------------------------------------------
qs, qe = function_range(
    s,
    "void media_chat_animated_sticker_queue("
)

queue_func = s[qs:qe]

validation_anchor = r'''    int kind =
        media_chat_sticker_kind_from_filename(
            document->filename
        );

    if (!kind)
        return;
'''

if validation_anchor not in queue_func:
    raise SystemExit("Could not locate v8.2 sticker queue kind validation.")

queue_func = queue_func.replace(
    validation_anchor,
    validation_anchor
    + r'''
    if (
        document->size <= 0 ||
        document->size >
            16LL * 1024LL * 1024LL
    ) {
        diag_log(
            "chat v83 sticker download rejected invalid size=%I64d",
            document->size
        );
        return;
    }
''',
    1,
)

fileref_anchor = r'''    int file_reference_length =
        tlstr_len(
            document->file_reference,
            true
        );

    copy.file_reference = NULL;
'''

if fileref_anchor not in queue_func:
    raise SystemExit("Could not locate v8.2 file_reference length block.")

queue_func = queue_func.replace(
    fileref_anchor,
    r'''    int file_reference_length =
        tlstr_len(
            document->file_reference,
            true
        );

    if (
        file_reference_length <= 0 ||
        file_reference_length > 4096
    ) {
        diag_log(
            "chat v83 sticker download rejected file_reference bytes=%d",
            file_reference_length
        );
        return;
    }

    copy.file_reference = NULL;
''',
    1,
)

delete_anchor = "    DeleteFileW(cache_path);\n\n    Document copy =\n"
if delete_anchor not in queue_func:
    raise SystemExit("Could not locate v8.2 cache reset before Document copy.")

queue_func = queue_func.replace(
    delete_anchor,
    r'''    DeleteFileW(cache_path);

    HANDLE cache_probe =
        CreateFileW(
            cache_path,
            GENERIC_WRITE,
            FILE_SHARE_READ,
            NULL,
            CREATE_ALWAYS,
            FILE_ATTRIBUTE_NORMAL,
            NULL
        );

    if (
        cache_probe ==
        INVALID_HANDLE_VALUE
    ) {
        diag_log(
            "chat v83 sticker cache file create failed error=%u path=%ls",
            (unsigned int)GetLastError(),
            cache_path
        );
        return;
    }

    CloseHandle(cache_probe);

    diag_log(
        "chat v83 sticker cache ready path=%ls",
        cache_path
    );

    Document copy =
''',
    1,
)

s = s[:qs] + queue_func + s[qe:]


# ---------------------------------------------------------------------------
# 3) Timer crash boundary. The animation timer touches RichEdit OLE, rlottie
# and MFPlay. A decoder/COM/access violation should stop sticker animation, not
# terminate the entire Telegram client.
# ---------------------------------------------------------------------------
ts, te = function_range(
    s,
    "static VOID CALLBACK media_chat_sticker_timer_proc("
)

timer_func = s[ts:te]

old_sig = "static VOID CALLBACK media_chat_sticker_timer_proc("
if old_sig not in timer_func:
    raise SystemExit("Could not locate v8.2 sticker timer signature.")

timer_func = timer_func.replace(
    old_sig,
    "static VOID CALLBACK media_chat_sticker_timer_proc_unsafe(",
    1,
)

timer_wrapper = r'''

static VOID CALLBACK media_chat_sticker_timer_proc(
    HWND hwnd,
    UINT msg,
    UINT_PTR timer_id,
    DWORD tick
) {
    __try {
        media_chat_sticker_timer_proc_unsafe(
            hwnd,
            msg,
            timer_id,
            tick
        );
    }
    __except (EXCEPTION_EXECUTE_HANDLER) {
        diag_log(
            "chat v83 recovered animated-sticker timer exception"
        );

        if (media_chat_sticker_timer) {
            KillTimer(
                NULL,
                media_chat_sticker_timer
            );

            media_chat_sticker_timer = 0;
        }
    }
}'''

s = s[:ts] + timer_func + timer_wrapper + s[te:]

write(t, s)

checks = [
    "chat_animated_sticker_stability_v83",
    "chat v83 sticker cache ready path=",
    "chat v83 sticker cache file create failed",
    "document->size >",
    "file_reference_length > 4096",
    "media_chat_sticker_timer_proc_unsafe",
    "chat v83 recovered animated-sticker timer exception",
]

data = read(t)

for token in checks:
    if token not in data:
        raise SystemExit(
            f"v8.3 verification failed in telegacy.cpp: {token}"
        )

print(
    "Applied animated sticker stability v8.3: cache files are rooted in the "
    "actual Telegacy app-data directory instead of the mutable session.dat path, "
    "cache writability is verified before asynchronous download, malformed "
    "sticker metadata is rejected, and the inline animation timer has an SEH "
    "crash boundary."
)
