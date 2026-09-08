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

for p in (h, t, r, helpers):
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
                 'void diag_log(const char* format, ...);'
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
write(t, s)

# ----- src/response.cpp -----
s = read(r)

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

write(r, s)

# ----- src/helpers.cpp -----
s = read(helpers)

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
write(helpers, s)

print("Telegacy v1.0.4 diagnostic patch applied successfully.")
