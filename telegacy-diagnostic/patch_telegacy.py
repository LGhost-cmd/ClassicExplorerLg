#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_telegacy.py <Telegacy source directory>")

root = Path(sys.argv[1]).resolve()
h = root / "include" / "telegacy.h"
t = root / "src" / "telegacy.cpp"
r = root / "src" / "response.cpp"
helpers = root / "src" / "helpers.cpp"
conversions = root / "src" / "conversions.cpp"
message = root / "src" / "message.cpp"

for p in (h, t, r, helpers, message, conversions):
    if not p.exists():
        raise SystemExit(f"Missing expected Telegacy v1.0.4 file: {p}")
def read(p):
    # Telegacy 1.0.4 sources are old ANSI/8-bit files rather than UTF-8.
    # latin-1 gives us a lossless 1:1 mapping of every source byte,
    # while all strings modified by this patch are ASCII.
    return p.read_text(encoding="latin-1")

def write(p, s):
    # Preserve the original 8-bit source representation.
    p.write_text(s, encoding="latin-1", newline="\r\n")

# ----- include/telegacy.h -----
s = read(h)

s = s.replace("#include <src/webp/decode.h>", "#include <webp/decode.h>")

for pragma in [
    '#pragma comment(lib, "tomcrypt.lib")',
    '#pragma comment(lib, "miniz.lib")',
    '#pragma comment(lib, "libwebp.lib")',
    '#pragma comment(lib, "qrcodegen.lib")',
    '#pragma comment(lib, "libjpeg.lib")',
	'#pragma comment(lib, "riched20.lib")',
]:
    s = s.replace(pragma, "// diagnostic build: linked by CMake // " + pragma)

anchor = '#include "../res/resource.h"'
if "void diag_log(" not in s:
    if anchor not in s:
        raise SystemExit("Could not find resource.h include in telegacy.h")
    s = s.replace(
        anchor,
        anchor + '\n\n// Diagnostic build: logs parser/state metadata only, never message text.\n'
                 'void diag_log(const char* format, ...);\n'
				'extern volatile LONG history_request_pending;'
    )
write(h, s)

# ----- src/telegacy.cpp -----
s = read(t)
include_anchor = "#include <telegacy.h>"
# Modern Windows SDK declares wWinMain with LPWSTR.
# Telegacy 1.0.4 used LPSTR and then treated it as wchar_t*.
old_entry = (
    "int WINAPI wWinMain(HINSTANCE hInstance, HINSTANCE hPrevInstance, "
    "LPSTR lpCmdLine, int nCmdShow) {"
)

new_entry = (
    "int WINAPI wWinMain(HINSTANCE hInstance, HINSTANCE hPrevInstance, "
    "LPWSTR lpCmdLine, int nCmdShow) {"
)

if old_entry not in s:
    raise SystemExit("Could not find Telegacy wWinMain signature")
s = s.replace(old_entry, new_entry, 1)

diag_impl = r'''
#include <stdarg.h>

// --------------------------------------------------------------------------------------
// Modern RichEdit compatibility
// --------------------------------------------------------------------------------------
// Current Windows SDKs no longer reliably ship Riched20.lib.
// Resolve CreateTextServices from the system DLL at runtime instead.

extern "C" const IID IID_ITextHost = {
    0xc5bdd8d0,
    0xd26e,
    0x11ce,
    {0xa8, 0x9e, 0x00, 0xaa, 0x00, 0x6c, 0xad, 0xc5}
};

extern "C" HRESULT WINAPI CreateTextServices(
    IUnknown* punkOuter,
    ITextHost* pITextHost,
    IUnknown** ppUnk
) {
    typedef HRESULT (WINAPI *CreateTextServicesProc)(
        IUnknown*,
        ITextHost*,
        IUnknown**
    );

    static HMODULE module = NULL;
    static CreateTextServicesProc proc = NULL;

    if (!module) {
        module = LoadLibraryW(L"Msftedit.dll");

        // Fallback for older systems / RichEdit versions.
        if (!module)
            module = LoadLibraryW(L"Riched20.dll");

        if (module) {
            proc = reinterpret_cast<CreateTextServicesProc>(
                GetProcAddress(module, "CreateTextServices")
            );
        }
    }

    if (!proc)
        return HRESULT_FROM_WIN32(ERROR_PROC_NOT_FOUND);

    return proc(punkOuter, pITextHost, ppUnk);
}

// --------------------------------------------------------------------------------------
// Diagnostic logging
// --------------------------------------------------------------------------------------
// The log goes to %TEMP%\Telegacy-diagnostic.log so it is available before
// Telegacy initializes its normal %APPDATA%\Telegacy path.

static void diag_get_path(wchar_t* out, DWORD count) {
    if (!out || count < 32) return;
    DWORD n = GetTempPathW(count, out);
    if (!n || n >= count) {
        lstrcpynW(out, L"C:\\", count);
    }
    size_t len = wcslen(out);
    if (len && out[len - 1] != L'\\' && len + 1 < count) {
        out[len++] = L'\\';
        out[len] = 0;
    }
    lstrcpynW(out + len, L"Telegacy-diagnostic.log", count - (DWORD)len);
}

void diag_log(const char* format, ...) {
    char msg[3072];
    va_list args;
    va_start(args, format);
    _vsnprintf(msg, sizeof(msg) - 1, format, args);
    va_end(args);
    msg[sizeof(msg) - 1] = 0;

    SYSTEMTIME st;
    GetLocalTime(&st);

    char line[3584];
    _snprintf(
        line, sizeof(line) - 1,
        "[%04u-%02u-%02u %02u:%02u:%02u.%03u] [T%lu] %s\r\n",
        st.wYear, st.wMonth, st.wDay,
        st.wHour, st.wMinute, st.wSecond, st.wMilliseconds,
        GetCurrentThreadId(), msg
    );
    line[sizeof(line) - 1] = 0;

    wchar_t path[MAX_PATH];
    diag_get_path(path, MAX_PATH);

    HANDLE file = CreateFileW(
        path,
        FILE_APPEND_DATA,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        NULL,
        OPEN_ALWAYS,
        FILE_ATTRIBUTE_NORMAL,
        NULL
    );
    if (file != INVALID_HANDLE_VALUE) {
        DWORD written = 0;
        WriteFile(file, line, (DWORD)strlen(line), &written, NULL);
        FlushFileBuffers(file);
        CloseHandle(file);
    }
}

static LONG WINAPI diag_unhandled_exception(EXCEPTION_POINTERS* ep) {
    if (!ep || !ep->ExceptionRecord) {
        diag_log("UNHANDLED EXCEPTION: no exception record");
        return EXCEPTION_CONTINUE_SEARCH;
    }

    diag_log(
        "UNHANDLED EXCEPTION code=0x%08lX address=%p flags=0x%08lX",
        ep->ExceptionRecord->ExceptionCode,
        ep->ExceptionRecord->ExceptionAddress,
        ep->ExceptionRecord->ExceptionFlags
    );

#if defined(_M_IX86)
    if (ep->ContextRecord) {
        CONTEXT* c = ep->ContextRecord;
        diag_log(
            "REG EIP=%08lX ESP=%08lX EBP=%08lX EAX=%08lX EBX=%08lX ECX=%08lX EDX=%08lX ESI=%08lX EDI=%08lX",
            c->Eip, c->Esp, c->Ebp, c->Eax, c->Ebx, c->Ecx, c->Edx, c->Esi, c->Edi
        );
    }
#endif

    return EXCEPTION_CONTINUE_SEARCH;
}

class DiagnosticBootstrap {
public:
    DiagnosticBootstrap() {
        wchar_t path[MAX_PATH];
        diag_get_path(path, MAX_PATH);
        DeleteFileW(path);
        SetUnhandledExceptionFilter(diag_unhandled_exception);
        diag_log("=== Telegacy 1.0.4 diagnostic build started ===");
        diag_log("pid=%lu imageBase=%p", GetCurrentProcessId(), GetModuleHandleW(NULL));
    }
};

static DiagnosticBootstrap g_diagnosticBootstrap;
'''

if "DiagnosticBootstrap" not in s:
    if include_anchor not in s:
        raise SystemExit("Could not locate include anchor in telegacy.cpp")
    s = s.replace(include_anchor, include_anchor + "\n" + diag_impl, 1)

# ------------------------------------------------------------------
# Downloads: always use the user's Downloads\Telegram directory
# ------------------------------------------------------------------

download_anchor = (
    '\tGetPrivateProfileString('
    'L"General", L"download_path", L"", '
    'download_path, MAX_PATH, appdata_path);'
)

anchor_pos = s.find(download_anchor)

if anchor_pos < 0:
    raise SystemExit(
        "Could not locate download_path GetPrivateProfileString in telegacy.cpp"
    )

start = s.rfind(
    "\twchar_t download_path[MAX_PATH];",
    0,
    anchor_pos
)

end_marker = "\tSetCurrentDirectory(download_path);"
end = s.find(end_marker, anchor_pos)

if start < 0 or end < 0:
    raise SystemExit(
        "Could not locate Telegacy download_path initialization block"
    )

end += len(end_marker)

new_download_block = """\twchar_t download_path[MAX_PATH] = {0};
\twchar_t downloads_root[MAX_PATH] = {0};

\t// Use the real Windows Downloads known-folder location.
\tHKEY hKey;

\tif (RegOpenKeyExW(
\t\tHKEY_CURRENT_USER,
\t\tL"Software\\\\Microsoft\\\\Windows\\\\CurrentVersion\\\\Explorer\\\\User Shell Folders",
\t\t0,
\t\tKEY_READ,
\t\t&hKey
\t) == ERROR_SUCCESS) {

\t\tDWORD type = 0;
\t\tDWORD size = sizeof(downloads_root);

\t\tif (RegQueryValueExW(
\t\t\thKey,
\t\t\tL"{374DE290-123F-4565-9164-39C4925E467B}",
\t\t\tNULL,
\t\t\t&type,
\t\t\t(LPBYTE)downloads_root,
\t\t\t&size
\t\t) != ERROR_SUCCESS) {
\t\t\tdownloads_root[0] = 0;
\t\t}

\t\tRegCloseKey(hKey);
\t}

\t// The registry usually contains %USERPROFILE%\\Downloads.
\tif (downloads_root[0]) {
\t\twchar_t expanded[MAX_PATH] = {0};

\t\tDWORD expanded_len = ExpandEnvironmentStringsW(
\t\t\tdownloads_root,
\t\t\texpanded,
\t\t\tMAX_PATH
\t\t);

\t\tif (expanded_len > 0 && expanded_len < MAX_PATH) {
\t\t\twcscpy(downloads_root, expanded);
\t\t}
\t}

\t// Fallback to %USERPROFILE%\\Downloads.
\tif (!downloads_root[0]) {
\t\tDWORD len = GetEnvironmentVariableW(
\t\t\tL"USERPROFILE",
\t\t\tdownloads_root,
\t\t\tMAX_PATH
\t\t);

\t\tif (!len || len >= MAX_PATH) {
\t\t\twcscpy(downloads_root, L"C:\\\\");
\t\t}

\t\tif (wcslen(downloads_root) + 11 < MAX_PATH) {
\t\t\twcscat(downloads_root, L"\\\\Downloads");
\t\t}
\t}

\t_snwprintf(
\t\tdownload_path,
\t\tMAX_PATH - 1,
\t\tL"%s\\\\Telegram",
\t\tdownloads_root
\t);

\tdownload_path[MAX_PATH - 1] = 0;

\tDWORD attrs = GetFileAttributesW(download_path);

\tif (
\t\tattrs == INVALID_FILE_ATTRIBUTES ||
\t\t!(attrs & FILE_ATTRIBUTE_DIRECTORY)
\t) {
\t\tif (!CreateDirectoryW(download_path, NULL)) {
\t\t\tDWORD error = GetLastError();

\t\t\tif (error != ERROR_ALREADY_EXISTS) {
\t\t\t\tdiag_log(
\t\t\t\t\t"CreateDirectory Telegram failed error=%lu",
\t\t\t\t\terror
\t\t\t\t);
\t\t\t}
\t\t}
\t}

\tif (!SetCurrentDirectoryW(download_path)) {
\t\tdiag_log(
\t\t\t"SetCurrentDirectory Telegram failed error=%lu",
\t\t\tGetLastError()
\t\t);
\t} else {
\t\tdiag_log(
\t\t\t"Telegram download directory configured"
\t\t);
\t}

\tWritePrivateProfileStringW(
\t\tL"General",
\t\tL"download_path",
\t\tdownload_path,
\t\tappdata_path
\t);"""

s = s[:start] + new_download_block + s[end:]

write(t, s)

# ----- src/response.cpp -----
s = read(r)

diag_log(
    "upload.file state downloads=%d documents=%d custom_emoji=%d",
    (int)downloading_docs.size(),
    (int)documents.size(),
    (int)rces.size()
);

old = "\tunsigned int constructor = read_le(unenc_response, 4);\n\tswitch (constructor) {"
new = (
    "\tunsigned int constructor = read_le(unenc_response, 4);\n"
    "\tdiag_log(\"response_handler ctor=0x%08X length=%d ack=%d peers=%d total=%d folders=%d ptr=%p\", "
    "constructor, length, acknowledgement ? 1 : 0, peers_count, total_peers_count, folders_count, unenc_response);\n"
    "\tswitch (constructor) {"
)
if old not in s:
    raise SystemExit("response_handler constructor anchor not found")
s = s.replace(old, new, 1)

old = "\tcase 0x3072cfa1: { // gzip_packed\n"
s = s.replace(old, old + '\t\tdiag_log("gzip_packed begin length=%d", length);\n', 1)

old = "\t\tresponse_handler(dcInfo, (BYTE*)out_data, false, out_len);\n"
s = s.replace(
    old,
    '\t\tdiag_log("gzip_packed decompressed out_len=%u out=%p", out_len, out_data);\n' + old,
    1
)

old = "\tcase 0xae500895: { // future_salts\n"
s = s.replace(
    old,
    old + '\t\tdiag_log("future_salts begin peers=%d total=%d database_version=%d", peers_count, total_peers_count, database_version);\n',
    1
)

old = "\tcase 0x71e094f3: // messages.dialogsSlice\n"
s = s.replace(
    old,
    old + '\t\tdiag_log("messages.dialogsSlice total_peers_count(raw)=%d", read_le(unenc_response + 4, 4));\n',
    1
)

old = "\tcase 0x15ba6c40: { // messages.dialogs\n"
s = s.replace(
    old,
    old + '\t\tdiag_log("messages.dialogs begin length=%d peers_before=%d total=%d", length, peers_count, total_peers_count);\n',
    1
)

old = "\t\toffset_msg = array_find(unenc_response, message_cons, 4, 2);\n"
if old in s:
    s = s.replace(
        old,
        '\t\tdiag_log("messages.dialogs searching message vector constructor");\n'
        + old +
        '\t\tdiag_log("messages.dialogs message vector offset=%d", offset_msg);\n',
        1
    )

old = "\t\tpeers_count += read_le(unenc_response + offset_msg - 4, 4);\n"
if old in s:
    s = s.replace(
        old,
        old + '\t\tdiag_log("messages.dialogs peer count updated old=%d new=%d total=%d", peers_count_old, peers_count, total_peers_count);\n',
        1
    )

old = "\t\tif (peers_count < total_peers_count) get_dialogs();\n\t\telse get_folders();\n"
if old in s:
    s = s.replace(
        old,
        '\t\tdiag_log("messages.dialogs completed slice peers=%d total=%d next=%s", peers_count, total_peers_count, '
        '(peers_count < total_peers_count) ? "get_dialogs" : "get_folders");\n' + old,
        1
    )

old = "\tcase 0x2ad93719: { // messages.dialogFilters (folders)\n"
s = s.replace(
    old,
    old + '\t\tdiag_log("messages.dialogFilters begin length=%d peers=%d", length, peers_count);\n',
    1
)

old = "\t\tfolders_count = read_le(unenc_response + 12, 4);\n"
if old in s:
    s = s.replace(
        old,
        old + '\t\tdiag_log("messages.dialogFilters folders_count=%d", folders_count);\n',
        1
    )

case_pos = s.find("case 0x2ad93719")
if case_pos >= 0:
    show_pos = s.find("\t\tshow_main();", case_pos)
    if show_pos >= 0:
        s = s[:show_pos] + '\t\tdiag_log("messages.dialogFilters -> show_main");\n' + s[show_pos:]

old = """\t\tif (IMAGELOADPOLICY == 2 && documents_count_old != documents.size()) for (int i = documents.size() - documents_count_old - 1; i >= 0; i--) {
\t\t\tif (!read_le(documents[i].photo_msg_id, 8)) {
\t\t\t\tget_photo(NULL, &documents[i], dcInfo);
\t\t\t\tbreak;
\t\t\t}
\t\t}"""

new = """\t\tif (IMAGELOADPOLICY == 2 && documents_count_old != documents.size()) for (int i = documents.size() - documents_count_old - 1; i >= 0; i--) {

\t\t\t// photo_size == 1 is used for sticker documents.
\t\t\t// Do not download those. Custom emoji are handled through rces.
\t\t\tif (documents[i].photo_size == 1)
\t\t\t\tcontinue;

\t\t\tif (!read_le(documents[i].photo_msg_id, 8)) {
\t\t\t\tget_photo(NULL, &documents[i], dcInfo);
\t\t\t\tbreak;
\t\t\t}
\t\t}"""

if old not in s:
    raise SystemExit("Could not locate history media auto-load block")

s = s.replace(old, new, 1)

old = """\t\tif (messages.size() - messages_count_old < MSGSFETCHCOUNT) no_more_msgs = true;
\t\telse if (SendMessage(chat, EM_GETFIRSTVISIBLELINE, 0, 0) == 0) get_history();"""

new = """\t\tint inserted_count = (int)messages.size() - messages_count_old;

\t\tdiag_log(
\t\t\t"history page raw_count=%d inserted=%d loaded=%d limit=%d",
\t\t\tcount,
\t\t\tinserted_count,
\t\t\t(int)messages.size(),
\t\t\tMSGSFETCHCOUNT
\t\t);

\t\t// The current getHistory request is completely processed.
\t\tInterlockedExchange(&history_request_pending, 0);

\t\t// De-duplication can reduce inserted_count.
\t\t// Only the raw Telegram page size determines end of history.
\t\tif (count < MSGSFETCHCOUNT) {
\t\t\tno_more_msgs = true;

\t\t\tdiag_log(
\t\t\t\t"history reached end raw_count=%d",
\t\t\t\tcount
\t\t\t);
\t\t} else {
\t\t\tno_more_msgs = false;
\t\t}"""

if old not in s:
    raise SystemExit("Could not locate history end test in response.cpp")

s = s.replace(old, new, 1)

old = """\t\tif (count == 0 && messages.size() == 0 && current_peer != NULL) {
\t\t\tremove_peer(current_peer);
\t\t\tbreak;
\t\t}"""

new = """\t\tif (count == 0 && messages.size() == 0 && current_peer != NULL) {
\t\t\tInterlockedExchange(&history_request_pending, 0);
\t\t\tremove_peer(current_peer);
\t\t\tbreak;
\t\t}"""

if old not in s:
    raise SystemExit("Could not locate empty history early exit")

s = s.replace(old, new, 1)

old = """\t\tif (!current_peer || neworrep || memcmp(unenc_response + offset2, current_peer->id, 8) != 0) break;"""

new = """\t\tif (!current_peer || neworrep || memcmp(unenc_response + offset2, current_peer->id, 8) != 0) {
\t\t\tInterlockedExchange(&history_request_pending, 0);
\t\t\tbreak;
\t\t}"""

if old not in s:
    raise SystemExit("Could not locate history peer mismatch exit")

s = s.replace(old, new, 1)

# ----- Harden custom emoji file saving -----

old = """\t\t\tFILE* f = _wfopen(path, L"wb");
\t\t\tfwrite(&dir, sizeof(ICONDIR), 1, f);
\t\t\tfwrite(&entry, sizeof(ICONDIRENTRY), 1, f);
\t\t\tfwrite(&bih, sizeof(BITMAPINFOHEADER), 1, f);
\t\t\tfwrite(bmpBits, 1, bmpSize, f);
\t\t\tfwrite(maskBits, 1, maskSize, f);
\t\t\tfclose(f);"""

new = """\t\t\t// Make sure the custom emoji cache directory exists.
\t\t\twchar_t customEmojiDir[MAX_PATH];
\t\t\twcscpy(
\t\t\t\tcustomEmojiDir,
\t\t\t\tget_path(appdata_path, L"custom_emojis")
\t\t\t);

\t\t\tCreateDirectoryW(customEmojiDir, NULL);

\t\t\tFILE* f = _wfopen(path, L"wb");

\t\t\tif (!f) {
\t\t\t\tdiag_log(
\t\t\t\t\t"custom emoji file open failed id=%I64d error=%d",
\t\t\t\t\trces[0].id,
\t\t\t\t\terrno
\t\t\t\t);

\t\t\t\tfree(bmpBits);
\t\t\t\tfree(maskBits);
\t\t\t\tWebPFreeDecBuffer(&config.output);

\t\t\t\trces.erase(rces.begin());

\t\t\t\tif (rces.size())
\t\t\t\t\tget_photo(&rces[0], NULL, &dcInfoMain);

\t\t\t\tbreak;
\t\t\t}

\t\t\tfwrite(&dir, sizeof(ICONDIR), 1, f);
\t\t\tfwrite(&entry, sizeof(ICONDIRENTRY), 1, f);
\t\t\tfwrite(&bih, sizeof(BITMAPINFOHEADER), 1, f);
\t\t\tfwrite(bmpBits, 1, bmpSize, f);
\t\t\tfwrite(maskBits, 1, maskSize, f);

\t\t\tfclose(f);"""

if old not in s:
    raise SystemExit(
        "Could not locate custom emoji ICO writer in response.cpp"
    )

s = s.replace(old, new, 1)

old = """\t\t\t\tif (memcmp(current_peer->id, rces[0].ceps[0].peer_id, 8) == 0) {"""

new = """\t\t\t\tif (
\t\t\t\t\tcurrent_peer &&
\t\t\t\t\tmemcmp(
\t\t\t\t\t\tcurrent_peer->id,
\t\t\t\t\t\trces[0].ceps[0].peer_id,
\t\t\t\t\t\t8
\t\t\t\t\t) == 0
\t\t\t\t) {"""

if old not in s:
    raise SystemExit(
        "Could not locate custom emoji current_peer comparison"
    )

s = s.replace(old, new, 1)

write(r, s)

# ----- src/helpers.cpp -----
s = read(helpers)
if "volatile LONG history_request_pending = 0;" not in s:
    s = s.replace(
        "#include <telegacy.h>\n",
        "#include <telegacy.h>\n\n"
        "volatile LONG history_request_pending = 0;\n",
        1
    )
folder_anchor = "int folder_handler(BYTE* unenc_response, ChatsFolder* folder, int i, bool update) {\n"
if folder_anchor in s and 'diag_log("folder_handler' not in s:
    s = s.replace(
        folder_anchor,
        folder_anchor + '\tdiag_log("folder_handler i=%d update=%d ptr=%p", i, update ? 1 : 0, unenc_response);\n',
        1
    )

old_array_find = r'''int array_find(BYTE* buf, BYTE* find, int find_len, int find_count) {
	for (int i = 0; ; i += 4) {
		for (int j = 0; j < find_count; j++) {
			if (memcmp(buf + i, find + j * find_len, find_len) == 0) return i;
		}
	}
}'''

new_array_find = r'''int array_find(BYTE* buf, BYTE* find, int find_len, int find_count) {
	// Upstream 1.0.4 scans forever with no buffer length. If the expected TL
	// constructor is absent, it eventually reads unmapped memory and dies with
	// 0xC0000005. The diagnostic build keeps the normal behavior for successful
	// searches, but records and terminates cleanly before an unbounded scan can
	// become an opaque access violation.
	const int DIAG_MAX_SCAN = 16 * 1024 * 1024;

	for (int i = 0; ; i += 4) {
		if (i > DIAG_MAX_SCAN) {
			diag_log(
				"ARRAY_FIND LIMIT buf=%p scanned=%d find_len=%d find_count=%d pattern0=0x%08X",
				buf, i, find_len, find_count,
				(find && find_len >= 4) ? read_le(find, 4) : 0
			);
			ExitProcess(0xE0AF0001);
		}

		if (i && (i % 65536) == 0) {
			diag_log(
				"array_find still scanning buf=%p scanned=%d pattern0=0x%08X",
				buf, i, (find && find_len >= 4) ? read_le(find, 4) : 0
			);
		}

		__try {
			for (int j = 0; j < find_count; j++) {
				if (memcmp(buf + i, find + j * find_len, find_len) == 0) {
					if (i > 4096) {
						diag_log(
							"array_find found after long scan offset=%d pattern0=0x%08X",
							i, (find && find_len >= 4) ? read_le(find, 4) : 0
						);
					}
					return i;
				}
			}
		}
		__except(EXCEPTION_EXECUTE_HANDLER) {
			diag_log(
				"ARRAY_FIND ACCESS VIOLATION buf=%p offset=%d probe=%p find_len=%d find_count=%d pattern0=0x%08X exception=0x%08lX",
				buf, i, buf + i, find_len, find_count,
				(find && find_len >= 4) ? read_le(find, 4) : 0,
				GetExceptionCode()
			);
			ExitProcess(0xE0AF0002);
		}
	}
}'''

if old_array_find not in s:
    raise SystemExit("Exact v1.0.4 array_find implementation was not found; refusing to patch wrong source.")

s = s.replace(old_array_find, new_array_find, 1)
# ----- Fix get_history pagination / duplicate messages -----

start = s.find("void get_history() {")
end = s.find("\nvoid set_typing(", start)

if start < 0 or end < 0:
    raise SystemExit("Could not locate get_history in helpers.cpp")

new_get_history = r'''void get_history() {
    if (InterlockedCompareExchange(
            &history_request_pending,
            1,
            0
        ) != 0) {

        diag_log(
            "get_history skipped: request already pending loaded=%d",
            (int)messages.size()
        );

        return;
    }
    BYTE unenc_query[112];
    BYTE enc_query[136];

    internal_header(unenc_query, true);

    write_le(unenc_query + 32, 0x4423e6c5, 4);

    char offset = place_peer(
        unenc_query + 36,
        current_peer,
        true
    );

    int oldest_id = messages.size() ? messages.front().id : 0;

    // offset_id: continue strictly from the oldest message already loaded.
    write_le(
        unenc_query + 36 + offset,
        oldest_id,
        4
    );

    // offset_date
    memset(
        unenc_query + 40 + offset,
        0,
        4
    );

    // add_offset
    memset(
        unenc_query + 44 + offset,
        0,
        4
    );

    // limit
    write_le(
        unenc_query + 48 + offset,
        MSGSFETCHCOUNT,
        4
    );

    // max_id
    memset(
        unenc_query + 52 + offset,
        0,
        4
    );

    // min_id
    memset(
        unenc_query + 56 + offset,
        0,
        4
    );

    // hash
    memset(
        unenc_query + 60 + offset,
        0,
        8
    );

    diag_log(
        "get_history oldest_id=%d loaded=%d limit=%d",
        oldest_id,
        (int)messages.size(),
        MSGSFETCHCOUNT
    );

    char padding_len = get_padding(68 + offset);

    write_le(
        unenc_query + 28,
        36 + offset,
        4
    );

    fortuna_read(
        unenc_query + 68 + offset,
        padding_len,
        &prng
    );

    char len = 68 + offset + padding_len;

    convert_message(
        unenc_query,
        enc_query,
        len,
        0
    );

    send_query(
        enc_query,
        len + 24
    );
}
'''

s = s[:start] + new_get_history + s[end:]

# ----- Disable obsolete upstream update popup -----

old = """\tset_tray_icon();
\tif (CHECKUPDATES) {
\t\tunsigned threadID;
\t\t_beginthreadex(NULL, 0, UpdateWorker, NULL, 0, &threadID);
\t}
}"""

new = """\tset_tray_icon();

\t// Our build does not use the old Telegacy upstream update checker.
\tif (CHECKUPDATES)
\t\tdiag_log("automatic upstream update check suppressed");
}"""

if old not in s:
    raise SystemExit("Could not locate automatic update checker in helpers.cpp")

s = s.replace(old, new, 1)

write(helpers, s)

# ----- src/message.cpp: protect history against duplicate message IDs -----

s = read(message)

old = """\tint msg_id_int = read_le(msg_id, 4);
\tbool duplicate = (peer && msg_id_int <= peer->last_recv && !to_front);
\tif (!duplicate && !to_front && peer) peer->last_recv = msg_id_int;"""

new = """\tint msg_id_int = read_le(msg_id, 4);

\tbool duplicate = (peer && msg_id_int <= peer->last_recv && !to_front);

\tbool history_duplicate = false;

\tif (to_front &&
\t\tmessage_adding &&
\t\t!editing &&
\t\t!rplhelper &&
\t\tmsg_id_int != 0) {

\t\tfor (int i = 0; i < messages.size(); i++) {
\t\t\tif (messages[i].id == msg_id_int) {
\t\t\t\thistory_duplicate = true;

\t\t\t\tdiag_log(
\t\t\t\t\t"message history duplicate id=%d existing_index=%d loaded=%d",
\t\t\t\t\tmsg_id_int,
\t\t\t\t\ti,
\t\t\t\t\t(int)messages.size()
\t\t\t\t);

\t\t\t\tbreak;
\t\t\t}
\t\t}
\t}

\tif (history_duplicate)
\t\tduplicate = true;

\tif (!duplicate && !to_front && peer)
\t\tpeer->last_recv = msg_id_int;"""

if old not in s:
    raise SystemExit(
        "Could not locate message duplicate-check block in message.cpp"
    )

s = s.replace(old, new, 1)


old = """\tif (message_adding)
\t\tmessage_adder(service, to_front, flags_msg, msg_id, msg_bytes, NULL, chat_member_id, &format_vecs[0], reactions, msgrpl, msgfwd, views, groupmed_end, footer, editing, date);"""

new = """\tif (message_adding && !history_duplicate)
\t\tmessage_adder(service, to_front, flags_msg, msg_id, msg_bytes, NULL, chat_member_id, &format_vecs[0], reactions, msgrpl, msgfwd, views, groupmed_end, footer, editing, date);"""

if old not in s:
    raise SystemExit(
        "Could not locate message_adder call in message.cpp"
    )

s = s.replace(old, new, 1)

old = """\t\t\t} else {
\t\t\t\twchar_t placeholder[] = {0xFE0F, 0};
\t\t\t\triched_write(chat, placeholder);
\t\t\t\tif (!to_front && IMAGELOADPOLICY == 2) get_photo(NULL, &document, &dcInfoMain);
\t\t\t}"""

new = """\t\t\t} else {
\t\t\t\twchar_t placeholder[] = {0xFE0F, 0};
\t\t\t\triched_write(chat, placeholder);

\t\t\t\t// Do not download Telegram stickers.
\t\t\t\t// Custom emoji use RequestedCustomEmoji/rces and are unaffected.
\t\t\t\tif (!sticker && !to_front && IMAGELOADPOLICY == 2)
\t\t\t\t\tget_photo(NULL, &document, &dcInfoMain);
\t\t\t}"""

if old not in s:
    raise SystemExit("Could not locate sticker photo loading in message.cpp")

s = s.replace(old, new, 1)

write(message, s)

# ----- src/telegacy.cpp: media double-click + lazy emoji -----
s = read(t)

# ------------------------------------------------------------------
# Media: recognise both single and double click
# ------------------------------------------------------------------

old = """\t\tif (pNMHDR->hwndFrom == chat && pNMHDR->code == EN_LINK && (pENLink->msg == WM_LBUTTONDOWN)) {
\t\t\tbool found = false;"""

new = """\t\tif (pNMHDR->hwndFrom == chat && pNMHDR->code == EN_LINK &&
\t\t\t(pENLink->msg == WM_LBUTTONDOWN || pENLink->msg == WM_LBUTTONDBLCLK)) {
\t\t\tbool media_double_click = (pENLink->msg == WM_LBUTTONDBLCLK);
\t\t\tbool found = false;"""

if old not in s:
    raise SystemExit(
        "Could not locate chat EN_LINK handler in telegacy.cpp"
    )

s = s.replace(old, new, 1)


# ------------------------------------------------------------------
# Already downloaded media: open only on double click
# ------------------------------------------------------------------

old = """\t\t\t\t\t\t} else {
\t\t\t\t\t\t\tif ((INT_PTR)ShellExecute(NULL, L"open", documents[i].filename, NULL, NULL, SW_SHOWNORMAL) <= 32) {"""

new = """\t\t\t\t\t\t} else if (media_double_click) {
\t\t\t\t\t\t\tif ((INT_PTR)ShellExecute(NULL, L"open", documents[i].filename, NULL, NULL, SW_SHOWNORMAL) <= 32) {"""

if old not in s:
    raise SystemExit(
        "Could not locate downloaded media open branch in telegacy.cpp"
    )

s = s.replace(old, new, 1)


# ------------------------------------------------------------------
# Emoji: don't build hundreds of icon buttons during startup
# ------------------------------------------------------------------

old = """\t\tif (fav_emojis.size() == 0) TabCtrl_SetCurSel(hTabs, 1);
\t\tNMHDR hdr;
\t\thdr.hwndFrom = hTabs;
\t\thdr.code = TCN_SELCHANGE;
\t\tSendMessage(hWnd, WM_NOTIFY, NULL, (LPARAM)&hdr);"""

new = """\t\tif (fav_emojis.size() == 0) TabCtrl_SetCurSel(hTabs, 1);

\t\t// Emoji buttons are populated lazily when the panel is opened."""

if old not in s:
    raise SystemExit(
        "Could not locate eager emoji loading in telegacy.cpp"
    )

s = s.replace(old, new, 1)


# ------------------------------------------------------------------
# Emoji toolbar button (case 5):
# populate the currently selected category on first opening
# ------------------------------------------------------------------

old = """\t\tcase 5: {
\t\t\tif (SendMessage(hToolbar, TB_GETSTATE, 5, 0) & TBSTATE_CHECKED) {
\t\t\t\tShowWindow(hTabs, SW_SHOW);
\t\t\t\tShowWindow(hOverlayTabs, SW_SHOW);
\t\t\t} else {
\t\t\t\tShowWindow(hTabs, SW_HIDE);
\t\t\t\tShowWindow(hOverlayTabs, SW_HIDE);
\t\t\t}
\t\t\tbreak;
\t\t} """

new = """\t\tcase 5: {
\t\t\tif (SendMessage(hToolbar, TB_GETSTATE, 5, 0) & TBSTATE_CHECKED) {
\t\t\t\tShowWindow(hTabs, SW_SHOW);
\t\t\t\tShowWindow(hOverlayTabs, SW_SHOW);

\t\t\t\t// Lazy-load selected emoji category on first opening.
\t\t\t\tif (EMOJIS && GetWindow(emojiStatic, GW_CHILD) == NULL) {
\t\t\t\t\tNMHDR hdr = {0};
\t\t\t\t\thdr.hwndFrom = hTabs;
\t\t\t\t\thdr.code = TCN_SELCHANGE;

\t\t\t\t\tdiag_log(
\t\t\t\t\t\t"emoji picker lazy-load category=%d",
\t\t\t\t\t\tTabCtrl_GetCurSel(hTabs)
\t\t\t\t\t);

\t\t\t\t\tSendMessage(
\t\t\t\t\t\thWnd,
\t\t\t\t\t\tWM_NOTIFY,
\t\t\t\t\t\t0,
\t\t\t\t\t\t(LPARAM)&hdr
\t\t\t\t\t);
\t\t\t\t}
\t\t\t} else {
\t\t\t\tShowWindow(hTabs, SW_HIDE);
\t\t\t\tShowWindow(hOverlayTabs, SW_HIDE);
\t\t\t}
\t\t\tbreak;
\t\t} """

if old not in s:
    raise SystemExit(
        "Could not locate emoji toolbar case 5 in telegacy.cpp"
    )

s = s.replace(old, new, 1)


# IMPORTANT: save all telegacy.cpp changes
write(t, s)

# ----- src/telegacy.cpp: chat/channel search -----
s = read(t)

# ------------------------------------------------------------
# Search helpers
# ------------------------------------------------------------

anchor = "int lang_codepage = 0;\n"

search_helpers = r'''
HWND hChatSearch = NULL;
bool chat_search_updating = false;

static bool chat_name_contains(
    const wchar_t* name,
    const wchar_t* query
) {
    if (!query || !query[0])
        return true;

    if (!name || !name[0])
        return false;

    int name_len = lstrlenW(name);
    int query_len = lstrlenW(query);

    if (query_len > name_len)
        return false;

    for (int i = 0; i <= name_len - query_len; i++) {
        if (
            CompareStringW(
                LOCALE_USER_DEFAULT,
                NORM_IGNORECASE,
                name + i,
                query_len,
                query,
                query_len
            ) == CSTR_EQUAL
        ) {
            return true;
        }
    }

    return false;
}

static void rebuild_chat_combo_by_name(
    const wchar_t* query
) {
    if (!hComboBoxChats)
        return;

    SendMessage(
        hComboBoxChats,
        CB_RESETCONTENT,
        0,
        0
    );

    if (!current_folder)
        return;

    for (int i = 0; i < current_folder->count; i++) {
        Peer* peer =
            &peers[current_folder->peers[i]];

        if (!peer || !peer->name)
            continue;

        if (!chat_name_contains(peer->name, query))
            continue;

        LRESULT item = SendMessage(
            hComboBoxChats,
            CB_ADDSTRING,
            0,
            (LPARAM)peer->name
        );

        if (
            item != CB_ERR &&
            item != CB_ERRSPACE
        ) {
            SendMessage(
                hComboBoxChats,
                CB_SETITEMDATA,
                item,
                (LPARAM)peer
            );
        }
    }
}
'''

if "rebuild_chat_combo_by_name" not in s:
    if anchor not in s:
        raise SystemExit(
            "Could not locate lang_codepage anchor"
        )

    s = s.replace(
        anchor,
        anchor + search_helpers,
        1
    )


# ------------------------------------------------------------
# Add the search edit box to the top bar
# ------------------------------------------------------------

old = '''\
\t\thComboBoxFolders = CreateWindow(L"COMBOBOX", L"", CBS_DROPDOWNLIST | WS_CHILD | WS_VISIBLE | WS_VSCROLL | CBS_OWNERDRAWFIXED, 10, 10, 200, 300, hWnd, (HMENU)2, NULL, NULL);
\t\thComboBoxChats = CreateWindow(L"COMBOBOX", L"", CBS_DROPDOWNLIST | WS_CHILD | WS_VISIBLE | WS_VSCROLL | CBS_OWNERDRAWFIXED, 220, 10, width / 2.5, 300, hWnd, (HMENU)3, NULL, NULL);'''

new = '''\
\t\thComboBoxFolders = CreateWindow(
\t\t\tL"COMBOBOX",
\t\t\tL"",
\t\t\tCBS_DROPDOWNLIST | WS_CHILD | WS_VISIBLE |
\t\t\tWS_VSCROLL | CBS_OWNERDRAWFIXED,
\t\t\t10, 10, 115, 300,
\t\t\thWnd,
\t\t\t(HMENU)2,
\t\t\tNULL,
\t\t\tNULL
\t\t);

\t\thChatSearch = CreateWindowExW(
\t\t\tWS_EX_CLIENTEDGE,
\t\t\tL"EDIT",
\t\t\tL"",
\t\t\tWS_CHILD | WS_VISIBLE | ES_AUTOHSCROLL,
\t\t\t130, 10, 130, 22,
\t\t\thWnd,
\t\t\t(HMENU)30,
\t\t\tNULL,
\t\t\tNULL
\t\t);

\t\thComboBoxChats = CreateWindow(
\t\t\tL"COMBOBOX",
\t\t\tL"",
\t\t\tCBS_DROPDOWNLIST | WS_CHILD | WS_VISIBLE |
\t\t\tWS_VSCROLL | CBS_OWNERDRAWFIXED,
\t\t\t265, 10, width - 275, 300,
\t\t\thWnd,
\t\t\t(HMENU)3,
\t\t\tNULL,
\t\t\tNULL
\t\t);'''

if old not in s:
    raise SystemExit(
        "Could not locate chat/folder combobox creation"
    )

s = s.replace(old, new, 1)


# ------------------------------------------------------------
# Folder change: clear search and rebuild complete list
# ------------------------------------------------------------

old = '''\
\t\t\tSendMessage(hComboBoxChats, CB_RESETCONTENT, 0, 0);
\t\t\tcurrent_folder = (ChatsFolder*)SendMessage(hComboBoxFolders, CB_GETITEMDATA, selIndex, 0);
\t\t\tfor (int i = 0; i < current_folder->count; i++) {
\t\t\t\tSendMessage(hComboBoxChats, CB_ADDSTRING, 0, (LPARAM)peers[current_folder->peers[i]].name);
\t\t\t\tSendMessage(hComboBoxChats, CB_SETITEMDATA, i, (LPARAM)&peers[current_folder->peers[i]]);
\t\t\t}'''

new = '''\
\t\t\tcurrent_folder = (ChatsFolder*)SendMessage(
\t\t\t\thComboBoxFolders,
\t\t\t\tCB_GETITEMDATA,
\t\t\t\tselIndex,
\t\t\t\t0
\t\t\t);

\t\t\tchat_search_updating = true;
\t\t\tSetWindowTextW(hChatSearch, L"");
\t\t\tchat_search_updating = false;

\t\t\trebuild_chat_combo_by_name(L"");'''

if old not in s:
    raise SystemExit(
        "Could not locate folder chat-list rebuild"
    )

s = s.replace(old, new, 1)


# ------------------------------------------------------------
# Search box EN_CHANGE
# ------------------------------------------------------------

old = '''\
\t\tcase 3: {
\t\t\tif (nt3 && HIWORD(wParam) == CBN_DROPDOWN) nt3_combobox_fit(hComboBoxChats);'''

new = '''\
\t\tcase 30: {
\t\t\tif (
\t\t\t\tHIWORD(wParam) != EN_CHANGE ||
\t\t\t\tchat_search_updating
\t\t\t) {
\t\t\t\tbreak;
\t\t\t}

\t\t\twchar_t query[256] = {0};

\t\t\tGetWindowTextW(
\t\t\t\thChatSearch,
\t\t\t\tquery,
\t\t\t\t256
\t\t\t);

\t\t\trebuild_chat_combo_by_name(query);

\t\t\tbreak;
\t\t}

\t\tcase 3: {
\t\t\tif (nt3 && HIWORD(wParam) == CBN_DROPDOWN) nt3_combobox_fit(hComboBoxChats);'''

if old not in s:
    raise SystemExit(
        "Could not locate chat combobox WM_COMMAND handler"
    )

s = s.replace(old, new, 1)


# ------------------------------------------------------------
# Selection must use CB item data after filtering
# ------------------------------------------------------------

old = '''\
\t\t\tint selIndex = SendMessage(hComboBoxChats, CB_GETCURSEL, 0, 0);
\t\t\tSetFocus(msgInput);
\t\t\tif (selIndex == - 1 || (lParam && current_peer == &peers[current_folder->peers[selIndex]])) break;'''

new = '''\
\t\t\tint selIndex = SendMessage(
\t\t\t\thComboBoxChats,
\t\t\t\tCB_GETCURSEL,
\t\t\t\t0,
\t\t\t\t0
\t\t\t);

\t\t\tSetFocus(msgInput);

\t\t\tif (selIndex == -1)
\t\t\t\tbreak;

\t\t\tPeer* selected_peer = (Peer*)SendMessage(
\t\t\t\thComboBoxChats,
\t\t\t\tCB_GETITEMDATA,
\t\t\t\tselIndex,
\t\t\t\t0
\t\t\t);

\t\t\tif (
\t\t\t\t!selected_peer ||
\t\t\t\tselected_peer == (Peer*)CB_ERR
\t\t\t) {
\t\t\t\tbreak;
\t\t\t}

\t\t\tif (
\t\t\t\tlParam &&
\t\t\t\tcurrent_peer == selected_peer
\t\t\t) {
\t\t\t\tbreak;
\t\t\t}'''

if old not in s:
    raise SystemExit(
        "Could not locate chat selection header"
    )

s = s.replace(old, new, 1)

old = '''\
\t\t\tcurrent_peer = (Peer*)SendMessage(hComboBoxChats, CB_GETITEMDATA, selIndex, 0);'''

new = '''\
\t\t\tcurrent_peer = selected_peer;'''

if old not in s:
    raise SystemExit(
        "Could not locate current_peer assignment"
    )

s = s.replace(old, new, 1)


# ------------------------------------------------------------
# Owner draw must also use filtered item data
# ------------------------------------------------------------

old = '''\
\t\t\tif (lpdis->hwndItem == hComboBoxChats) {
\t\t\t\tif (lpdis->itemID == -1 && !current_peer) break;
\t\t\t\tpeer = lpdis->itemID == -1 ? current_peer : &peers[current_folder->peers[lpdis->itemID]];
\t\t\t\tif (!peer) break;
\t\t\t\tname = peer->name;
\t\t\t} else {'''

new = '''\
\t\t\tif (lpdis->hwndItem == hComboBoxChats) {
\t\t\t\tif (lpdis->itemID == -1) {
\t\t\t\t\tpeer = current_peer;
\t\t\t\t} else {
\t\t\t\t\tLRESULT data = SendMessage(
\t\t\t\t\t\thComboBoxChats,
\t\t\t\t\t\tCB_GETITEMDATA,
\t\t\t\t\t\tlpdis->itemID,
\t\t\t\t\t\t0
\t\t\t\t\t);

\t\t\t\t\tif (data != CB_ERR)
\t\t\t\t\t\tpeer = (Peer*)data;
\t\t\t\t}

\t\t\t\tif (!peer)
\t\t\t\t\tbreak;

\t\t\t\tname = peer->name;
\t\t\t} else {'''

if old not in s:
    raise SystemExit(
        "Could not locate chat owner-draw block"
    )

s = s.replace(old, new, 1)


# ------------------------------------------------------------
# Resize the three top controls
# ------------------------------------------------------------

old = '''\
\t\t\thdwp = DeferWindowPos(hdwp, hComboBoxChats, NULL, NULL, NULL, width / 2.5, 300, SWP_NOZORDER | SWP_NOMOVE);'''

new = '''\
\t\t\thdwp = DeferWindowPos(
\t\t\t\thdwp,
\t\t\t\thComboBoxFolders,
\t\t\t\tNULL,
\t\t\t\t10,
\t\t\t\t10,
\t\t\t\t115,
\t\t\t\t300,
\t\t\t\tSWP_NOZORDER
\t\t\t);

\t\t\thdwp = DeferWindowPos(
\t\t\t\thdwp,
\t\t\t\thChatSearch,
\t\t\t\tNULL,
\t\t\t\t130,
\t\t\t\t10,
\t\t\t\t130,
\t\t\t\t22,
\t\t\t\tSWP_NOZORDER
\t\t\t);

\t\t\thdwp = DeferWindowPos(
\t\t\t\thdwp,
\t\t\t\thComboBoxChats,
\t\t\t\tNULL,
\t\t\t\t265,
\t\t\t\t10,
\t\t\t\twidth - 275,
\t\t\t\t300,
\t\t\t\tSWP_NOZORDER
\t\t\t);'''

if old not in s:
    raise SystemExit(
        "Could not locate chat combobox resize"
    )

s = s.replace(old, new, 1)


write(t, s)

# ----- src/conversions.cpp -----
s = read(conversions)

start = s.find(
    "int utf8_to_wide(BYTE* src, wchar_t* str, int length) {"
)
end = s.find(
    "\nvoid wide_to_utf8_one(",
    start
)

if start < 0 or end < 0:
    raise SystemExit("Could not locate utf8_to_wide in conversions.cpp")

new_utf8_to_wide = r'''int utf8_to_wide(BYTE* src, wchar_t* str, int length) {
    if (!src || length <= 0)
        return 0;

    int str_pos = 0;

    for (int i = 0; i < length; ) {
        BYTE lead = src[i];

        unsigned int code = 0xFFFD;
        int cont_bytes = 0;
        bool valid = true;

        if (lead < 0x80) {
            code = lead;
            cont_bytes = 0;
        } else if ((lead & 0xE0) == 0xC0) {
            code = lead & 0x1F;
            cont_bytes = 1;
        } else if ((lead & 0xF0) == 0xE0) {
            code = lead & 0x0F;
            cont_bytes = 2;
        } else if ((lead & 0xF8) == 0xF0) {
            code = lead & 0x07;
            cont_bytes = 3;
        } else {
            valid = false;

            diag_log(
                "UTF8 invalid lead src=%p index=%d length=%d lead=0x%02X",
                src,
                i,
                length,
                (unsigned int)lead
            );
        }

        if (valid && i + cont_bytes >= length) {
            diag_log(
                "UTF8 truncated sequence src=%p index=%d length=%d "
                "lead=0x%02X continuation=%d",
                src,
                i,
                length,
                (unsigned int)lead,
                cont_bytes
            );

            valid = false;
        }

        if (valid) {
            for (int j = 0; j < cont_bytes; ++j) {
                BYTE b = src[i + 1 + j];

                if ((b & 0xC0) != 0x80) {
                    diag_log(
                        "UTF8 invalid continuation src=%p index=%d "
                        "length=%d lead=0x%02X continuation_index=%d "
                        "byte=0x%02X",
                        src,
                        i,
                        length,
                        (unsigned int)lead,
                        j,
                        (unsigned int)b
                    );

                    valid = false;
                    break;
                }

                code = (code << 6) | (b & 0x3F);
            }
        }

        if (valid) {
            bool invalid_codepoint = false;

            if (cont_bytes == 1 && code < 0x80)
                invalid_codepoint = true;
            else if (cont_bytes == 2 && code < 0x800)
                invalid_codepoint = true;
            else if (cont_bytes == 3 && code < 0x10000)
                invalid_codepoint = true;

            if (code >= 0xD800 && code <= 0xDFFF)
                invalid_codepoint = true;

            if (code > 0x10FFFF)
                invalid_codepoint = true;

            if (invalid_codepoint) {
                diag_log(
                    "UTF8 invalid codepoint src=%p index=%d "
                    "length=%d lead=0x%02X code=0x%08X",
                    src,
                    i,
                    length,
                    (unsigned int)lead,
                    code
                );

                valid = false;
            }
        }

        if (!valid) {
            code = 0xFFFD;
            cont_bytes = 0;
        }

        if (str == NULL) {
            str_pos += (code <= 0xFFFF) ? 1 : 2;
        } else if (code <= 0xFFFF) {
            str[str_pos++] = (wchar_t)code;
        } else {
            code -= 0x10000;
            str[str_pos++] =
                (wchar_t)(0xD800 + (code >> 10));
            str[str_pos++] =
                (wchar_t)(0xDC00 + (code & 0x3FF));
        }

        i += cont_bytes + 1;
    }

    return str_pos;
}
'''

s = s[:start] + new_utf8_to_wide + s[end:]
write(conversions, s)

# ----- Fix CImageDataObject COM lifetime -----
s = read(conversions)

start = s.find("class CImageDataObject : IDataObject {")
end = s.find("\n\nvoid insert_image(", start)

if start < 0 or end < 0:
    raise SystemExit("Could not locate CImageDataObject in conversions.cpp")

new_data_object = r'''class CImageDataObject : public IDataObject {
private:
    LONG m_refCount;
    BOOL m_bRelease;
    STGMEDIUM m_stgmed;
    FORMATETC m_format;

public:
    CImageDataObject()
        : m_refCount(1),
          m_bRelease(FALSE)
    {
        ZeroMemory(&m_stgmed, sizeof(m_stgmed));
        ZeroMemory(&m_format, sizeof(m_format));
    }

    virtual ~CImageDataObject() {
        if (m_bRelease && m_stgmed.tymed != TYMED_NULL) {
            ReleaseStgMedium(&m_stgmed);
        }
    }

    STDMETHOD(QueryInterface)(REFIID iid, void** ppvObject) {
        if (!ppvObject)
            return E_POINTER;

        *ppvObject = NULL;

        if (iid == IID_IUnknown || iid == IID_IDataObject) {
            *ppvObject = static_cast<IDataObject*>(this);
            AddRef();
            return S_OK;
        }

        return E_NOINTERFACE;
    }

    STDMETHOD_(ULONG, AddRef)(void) {
        return (ULONG)InterlockedIncrement(&m_refCount);
    }

    STDMETHOD_(ULONG, Release)(void) {
        LONG refs = InterlockedDecrement(&m_refCount);

        if (refs == 0) {
            delete this;
            return 0;
        }

        return (ULONG)refs;
    }

    STDMETHOD(GetData)(
        FORMATETC* pformatetcIn,
        STGMEDIUM* pmedium
    ) {
        if (!pformatetcIn || !pmedium)
            return E_POINTER;

        ZeroMemory(pmedium, sizeof(*pmedium));

        if (pformatetcIn->cfFormat == CF_METAFILEPICT &&
            (pformatetcIn->tymed & TYMED_MFPICT) &&
            m_stgmed.tymed == TYMED_MFPICT) {

            HANDLE hDst = OleDuplicateData(
                m_stgmed.hMetaFilePict,
                CF_METAFILEPICT,
                NULL
            );

            if (!hDst)
                return E_HANDLE;

            pmedium->tymed = TYMED_MFPICT;
            pmedium->hMetaFilePict = (HMETAFILEPICT)hDst;
            pmedium->pUnkForRelease = NULL;

            return S_OK;
        }

        if (pformatetcIn->cfFormat == CF_BITMAP &&
            (pformatetcIn->tymed & TYMED_GDI) &&
            m_stgmed.tymed == TYMED_GDI) {

            HANDLE hDst = OleDuplicateData(
                m_stgmed.hBitmap,
                CF_BITMAP,
                NULL
            );

            if (!hDst)
                return E_HANDLE;

            pmedium->tymed = TYMED_GDI;
            pmedium->hBitmap = (HBITMAP)hDst;
            pmedium->pUnkForRelease = NULL;

            return S_OK;
        }

        return DV_E_FORMATETC;
    }

    STDMETHOD(GetDataHere)(
        FORMATETC*,
        STGMEDIUM*
    ) {
        return E_NOTIMPL;
    }

    STDMETHOD(QueryGetData)(FORMATETC* pformatetc) {
        if (!pformatetc)
            return E_POINTER;

        if (m_stgmed.tymed == TYMED_MFPICT &&
            pformatetc->cfFormat == CF_METAFILEPICT &&
            (pformatetc->tymed & TYMED_MFPICT)) {
            return S_OK;
        }

        if (m_stgmed.tymed == TYMED_GDI &&
            pformatetc->cfFormat == CF_BITMAP &&
            (pformatetc->tymed & TYMED_GDI)) {
            return S_OK;
        }

        return DV_E_FORMATETC;
    }

    STDMETHOD(GetCanonicalFormatEtc)(
        FORMATETC*,
        FORMATETC* pOut
    ) {
        if (pOut)
            pOut->ptd = NULL;

        return E_NOTIMPL;
    }

    STDMETHOD(SetData)(
        FORMATETC* pformatetc,
        STGMEDIUM* pmedium,
        BOOL fRelease
    ) {
        if (!pformatetc || !pmedium)
            return E_POINTER;

        if (m_bRelease && m_stgmed.tymed != TYMED_NULL) {
            ReleaseStgMedium(&m_stgmed);
        }

        m_format = *pformatetc;
        m_stgmed = *pmedium;
        m_bRelease = fRelease;

        return S_OK;
    }

    STDMETHOD(EnumFormatEtc)(
        DWORD,
        IEnumFORMATETC**
    ) {
        return E_NOTIMPL;
    }

    STDMETHOD(DAdvise)(
        FORMATETC*,
        DWORD,
        IAdviseSink*,
        DWORD*
    ) {
        return OLE_E_ADVISENOTSUPPORTED;
    }

    STDMETHOD(DUnadvise)(DWORD) {
        return OLE_E_ADVISENOTSUPPORTED;
    }

    STDMETHOD(EnumDAdvise)(
        IEnumSTATDATA**
    ) {
        return OLE_E_ADVISENOTSUPPORTED;
    }
};
'''

s = s[:start] + new_data_object + s[end:]
write(conversions, s)



# ----- Harden insert_image against failed RichEdit/OLE object creation -----
s = read(conversions)

start = s.find(
    "void insert_image(HWND hRichEdit, HMETAFILEPICT hMetaFilePict, HBITMAP hBitmap) {"
)
end = s.find(
    "\nint utf8_to_wide(",
    start
)

if start < 0 or end < 0:
    raise SystemExit("Could not locate insert_image in conversions.cpp")

new_insert_image = r'''void insert_image(HWND hRichEdit, HMETAFILEPICT hMetaFilePict, HBITMAP hBitmap) {
    HRESULT hr = E_FAIL;
    LPRICHEDITOLE pRichEditOle = NULL;

    if (hRichEdit) {
        LRESULT result = SendMessage(
            hRichEdit,
            EM_GETOLEINTERFACE,
            0,
            (LPARAM)&pRichEditOle
        );

        if (!result || !pRichEditOle) {
            diag_log(
                "insert_image: EM_GETOLEINTERFACE failed hwnd=%p result=%ld",
                hRichEdit,
                (long)result
            );
            return;
        }
    } else {
        if (!textHost || !textHost->textServices) {
            diag_log("insert_image: textHost/textServices is NULL");
            return;
        }

        hr = textHost->textServices->TxSendMessage(
            EM_GETOLEINTERFACE,
            0,
            (LPARAM)&pRichEditOle,
            &hr
        );

        if (!pRichEditOle) {
            diag_log(
                "insert_image: TxSendMessage did not return IRichEditOle hr=0x%08lX",
                (unsigned long)hr
            );
            return;
        }
    }

    LPOLECLIENTSITE pClientSite = NULL;
    hr = pRichEditOle->GetClientSite(&pClientSite);

    if (FAILED(hr) || !pClientSite) {
        diag_log(
            "insert_image: GetClientSite failed hr=0x%08lX",
            (unsigned long)hr
        );
        pRichEditOle->Release();
        return;
    }

    LPLOCKBYTES pLockBytes = NULL;
    hr = CreateILockBytesOnHGlobal(NULL, TRUE, &pLockBytes);

    if (FAILED(hr) || !pLockBytes) {
        diag_log(
            "insert_image: CreateILockBytesOnHGlobal failed hr=0x%08lX",
            (unsigned long)hr
        );
        pClientSite->Release();
        pRichEditOle->Release();
        return;
    }

    LPSTORAGE pStorage = NULL;
    hr = StgCreateDocfileOnILockBytes(
        pLockBytes,
        STGM_SHARE_EXCLUSIVE | STGM_CREATE | STGM_READWRITE,
        0,
        &pStorage
    );

    if (FAILED(hr) || !pStorage) {
        diag_log(
            "insert_image: StgCreateDocfileOnILockBytes failed hr=0x%08lX",
            (unsigned long)hr
        );
        pLockBytes->Release();
        pClientSite->Release();
        pRichEditOle->Release();
        return;
    }

    CImageDataObject* pImageDataObject = new CImageDataObject();

    if (!pImageDataObject) {
        diag_log("insert_image: CImageDataObject allocation failed");
        pStorage->Release();
        pLockBytes->Release();
        pClientSite->Release();
        pRichEditOle->Release();
        return;
    }

    STGMEDIUM stg = {0};
    FORMATETC fmt = {0};

    if (hMetaFilePict) {
        fmt.cfFormat = CF_METAFILEPICT;
        fmt.dwAspect = DVASPECT_CONTENT;
        fmt.lindex = -1;
        fmt.tymed = TYMED_MFPICT;

        stg.tymed = TYMED_MFPICT;
        stg.hMetaFilePict = hMetaFilePict;
    } else if (hBitmap) {
        fmt.cfFormat = CF_BITMAP;
        fmt.dwAspect = DVASPECT_CONTENT;
        fmt.lindex = -1;
        fmt.tymed = TYMED_GDI;

        stg.tymed = TYMED_GDI;
        stg.hBitmap = hBitmap;
    } else {
        diag_log("insert_image: neither metafile nor bitmap supplied");

        pImageDataObject->Release();
        pStorage->Release();
        pLockBytes->Release();
        pClientSite->Release();
        pRichEditOle->Release();
        return;
    }

    hr = pImageDataObject->SetData(&fmt, &stg, FALSE);

    if (FAILED(hr)) {
        diag_log(
            "insert_image: SetData failed hr=0x%08lX",
            (unsigned long)hr
        );
        pImageDataObject->Release();
        pStorage->Release();
        pLockBytes->Release();
        pClientSite->Release();
        pRichEditOle->Release();
        return;
    }

    IDataObject* pDataObject = NULL;
    hr = pImageDataObject->QueryInterface(
        IID_IDataObject,
        (void**)&pDataObject
    );

    if (FAILED(hr) || !pDataObject) {
        diag_log(
            "insert_image: QueryInterface(IDataObject) failed hr=0x%08lX",
            (unsigned long)hr
        );

        pImageDataObject->Release();
        pStorage->Release();
        pLockBytes->Release();
        pClientSite->Release();
        pRichEditOle->Release();
        return;
    }

	pImageDataObject->Release();
	pImageDataObject = NULL;

    LPOLEOBJECT pObject = NULL;

    hr = OleCreateStaticFromData(
    	pDataObject,
    	IID_IOleObject,
    	OLERENDER_FORMAT,
    	&fmt,
    	pClientSite,
    	pStorage,
    	(void**)&pObject
	);
    if (FAILED(hr) || !pObject) {
        diag_log(
            "insert_image: OleCreateStaticFromData failed hr=0x%08lX "
            "metafile=%p bitmap=%p",
            (unsigned long)hr,
            hMetaFilePict,
            hBitmap
        );

        pDataObject->Release();
        pStorage->Release();
        pLockBytes->Release();
        pClientSite->Release();
        pRichEditOle->Release();
        return;
    }

    hr = OleSetContainedObject(pObject, TRUE);

    CLSID clsid = CLSID_NULL;
    hr = pObject->GetUserClassID(&clsid);

    if (FAILED(hr)) {
        diag_log(
            "insert_image: GetUserClassID failed hr=0x%08lX",
            (unsigned long)hr
        );
    } else {
        REOBJECT reobject = { sizeof(REOBJECT) };
        reobject.clsid = clsid;
        reobject.cp = REO_CP_SELECTION;
        reobject.dvaspect = DVASPECT_CONTENT;
        reobject.dwFlags = hMetaFilePict ? REO_BELOWBASELINE : 0;
        reobject.dwUser = 0;
        reobject.poleobj = pObject;
        reobject.polesite = pClientSite;
        reobject.pstg = pStorage;

        SIZEL sizel = {0};
        reobject.sizel = sizel;

        hr = pRichEditOle->InsertObject(&reobject);

        if (FAILED(hr)) {
            diag_log(
                "insert_image: IRichEditOle::InsertObject failed hr=0x%08lX",
                (unsigned long)hr
            );

            wchar_t placeholder[] = {0xFE0F, 0};

            if (hRichEdit)
                riched_write(hRichEdit, placeholder);
        }
    }

    pDataObject->Release();
    pObject->Release();
    pClientSite->Release();
    pStorage->Release();
    pLockBytes->Release();
    pRichEditOle->Release();
}
'''

s = s[:start] + new_insert_image + s[end:]
write(conversions, s)

print("Telegacy v1.0.4 diagnostic patch applied successfully.")
