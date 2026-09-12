#!/usr/bin/env python3
from pathlib import Path
import sys
import base64
import json
import subprocess
import urllib.request

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_media_tabs_av.py <Telegacy source directory>")

root = Path(sys.argv[1]).resolve()
h = root / "include" / "telegacy.h"
t = root / "src" / "telegacy.cpp"
r = root / "src" / "response.cpp"
m = root / "src" / "message.cpp"

for p in (h, t, r, m):
    if not p.exists():
        raise SystemExit(f"Missing expected Telegacy file: {p}")


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


# -----------------------------------------------------------------------------
# Single-file replacement mode.
#
# This file replaces the old patch_media_tabs_av.py in the repository.  It
# first applies the exact previous v1 patch, then immediately applies v2.
# Therefore the workflow continues to contain ONE command only:
#
#   python "telegacy-diagnostic\patch_media_tabs_av.py" "telegacy-src"
#
# The previous v1 patch is pinned by Git blob SHA so replacing this file on
# master cannot make the bootstrap download itself recursively.
# -----------------------------------------------------------------------------

V1_BLOB_SHA = "b54ddc7af64c5a43143254c00d566c187aa609fb"
V1_BLOB_API = (
    "https://api.github.com/repos/LGhost-cmd/ClassicExplorerLg/git/blobs/"
    + V1_BLOB_SHA
)


def load_previous_v1_patch():
    # Fast/offline path: the old blob may already be present in the local
    # checkout's object database.
    try:
        repo_root = Path(__file__).resolve().parent.parent

        data = subprocess.check_output(
            ["git", "cat-file", "blob", V1_BLOB_SHA],
            cwd=str(repo_root),
            stderr=subprocess.DEVNULL,
        )

        if data:
            return data.decode("utf-8")
    except Exception:
        pass

    # GitHub Actions has network access because the workflow already clones
    # Telegacy and restores dependencies.  Fetch the immutable old blob rather
    # than the current file path.
    try:
        request = urllib.request.Request(
            V1_BLOB_API,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "ClassicExplorerLg-Telegacy-patcher",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))

        encoded = payload.get("content", "")
        encoding = payload.get("encoding", "")

        if encoding != "base64" or not encoded:
            raise RuntimeError("GitHub returned an unexpected blob representation")

        return base64.b64decode(encoded).decode("utf-8")

    except Exception as exc:
        raise SystemExit(
            "Could not obtain the pinned Media A/V v1 patch "
            f"({V1_BLOB_SHA}). Error: {exc}"
        )


def apply_previous_v1_if_needed():
    if "media_tabs_av_runtime_v1" in read(t):
        return

    print(
        "Media A/V v1 is not present; applying the pinned previous "
        "patch_media_tabs_av.py first..."
    )

    source = load_previous_v1_patch()

    namespace = {
        "__name__": "__main__",
        "__file__": "patch_media_tabs_av_v1_pinned.py",
    }

    try:
        exec(
            compile(
                source,
                "patch_media_tabs_av_v1_pinned.py",
                "exec",
            ),
            namespace,
            namespace,
        )
    except SystemExit as exc:
        if exc.code not in (None, 0):
            raise

    if "media_tabs_av_runtime_v1" not in read(t):
        raise SystemExit(
            "Pinned Media A/V v1 patch finished, but its runtime marker "
            "was not found in telegacy.cpp."
        )


apply_previous_v1_if_needed()

s = read(t)
if "media_tabs_av_runtime_v2" in s:
    print("Media A/V v2 already applied.")
    raise SystemExit(0)


# -----------------------------------------------------------------------------
# telegacy.h: MFPlay / cross-file declarations
# -----------------------------------------------------------------------------

s = read(h)

s = s.replace("#define _WIN32_WINNT 0x0400", "#define _WIN32_WINNT 0x0601", 1)
s = s.replace("#define WINVER 0x0500", "#define WINVER 0x0601", 1)

if "#include <mfplay.h>" not in s:
    anchor = "#include <dshow.h>"
    if anchor not in s:
        raise SystemExit("Could not locate #include <dshow.h> in telegacy.h")
    s = s.replace(
        anchor,
        anchor + "\n#include <mfplay.h>\n#pragma comment(lib, \"mfplay.lib\")",
        1,
    )

if "media_archive_preserve_on_chat_clear" not in s:
    anchor = "void media_player_chat_download_complete(\n    const wchar_t* path\n);"
    if anchor not in s:
        raise SystemExit("Could not locate media_player_chat_download_complete declaration")
    s = s.replace(
        anchor,
        anchor
        + "\n\nextern bool media_archive_preserve_on_chat_clear;"
        + "\nbool media_player_is_music_path(const wchar_t* path);"
        + "\nbool media_inline_audio_toggle(const wchar_t* path);",
        1,
    )

write(h, s)

# pragma comment is enough for MSVC, but keep CMake explicit too.
cmake = root / "CMakeLists.txt"
if cmake.exists():
    cm = cmake.read_text(encoding="utf-8")
    if "mfplay" not in cm.lower():
        if "    strmiids\n" in cm:
            cm = cm.replace("    strmiids\n", "    strmiids\n    mfplay\n", 1)
        elif "    ole32\n" in cm:
            cm = cm.replace("    ole32\n", "    ole32\n    mfplay\n", 1)
        cmake.write_text(cm, encoding="utf-8", newline="\n")


# -----------------------------------------------------------------------------
# telegacy.cpp: MFPlay-first video + inline audio + classic controls
# -----------------------------------------------------------------------------

s = read(t)

player_global = "static IVideoWindow* media_player_video = NULL;"
if player_global not in s:
    raise SystemExit("Could not locate media_player_video global")

s = s.replace(
    player_global,
    player_global
    + r'''

// media_tabs_av_runtime_v2
static IMFPMediaPlayer* media_player_mf = NULL;
static IMFPMediaPlayer* media_inline_audio = NULL;
static int media_player_backend = 0; // 0 none, 1 MFPlay, 2 DirectShow
static wchar_t media_inline_audio_path[MAX_PATH] = {0};
bool media_archive_preserve_on_chat_clear = false;
''',
    1,
)

helper_pos = s.find("static void media_player_release_graph()")
if helper_pos < 0:
    raise SystemExit("Could not locate media_player_release_graph")

helpers = r'''
static HRESULT media_mf_create_player(
    const wchar_t* path,
    HWND video_window,
    IMFPMediaPlayer** out_player
) {
    if (!path || !path[0] || !out_player)
        return E_INVALIDARG;

    *out_player = NULL;

    HRESULT hr =
        MFPCreateMediaPlayer(
            NULL,
            FALSE,
            MFP_OPTION_NONE,
            NULL,
            video_window,
            out_player
        );

    if (FAILED(hr) || !*out_player)
        return FAILED(hr) ? hr : E_FAIL;

    IMFPMediaItem* item = NULL;

    hr =
        (*out_player)->CreateMediaItemFromURL(
            path,
            TRUE,
            0,
            &item
        );

    if (SUCCEEDED(hr) && item)
        hr = (*out_player)->SetMediaItem(item);

    if (item)
        item->Release();

    if (FAILED(hr)) {
        (*out_player)->Shutdown();
        (*out_player)->Release();
        *out_player = NULL;
    }

    return hr;
}

static void media_inline_audio_release() {
    if (media_inline_audio) {
        media_inline_audio->Stop();
        media_inline_audio->Shutdown();
        media_inline_audio->Release();
        media_inline_audio = NULL;
    }

    media_inline_audio_path[0] = 0;
}

bool media_player_is_music_path(
    const wchar_t* path
) {
    if (!path || !path[0])
        return false;

    const wchar_t* leaf = wcsrchr(path, L'\\');
    leaf = leaf ? leaf + 1 : path;

    // Don't turn Telegacy's generated voice-note files into music rows.
    if (_wcsnicmp(leaf, L"voice", 5) == 0)
        return false;

    const wchar_t* dot = wcsrchr(leaf, L'.');
    if (!dot)
        return false;

    return
        _wcsicmp(dot, L".mp3") == 0 ||
        _wcsicmp(dot, L".m4a") == 0 ||
        _wcsicmp(dot, L".aac") == 0 ||
        _wcsicmp(dot, L".wav") == 0 ||
        _wcsicmp(dot, L".wma") == 0 ||
        _wcsicmp(dot, L".ogg") == 0 ||
        _wcsicmp(dot, L".opus") == 0 ||
        _wcsicmp(dot, L".flac") == 0;
}

bool media_inline_audio_toggle(
    const wchar_t* path
) {
    if (!media_player_is_music_path(path))
        return false;

    if (
        media_inline_audio &&
        media_inline_audio_path[0] &&
        _wcsicmp(media_inline_audio_path, path) == 0
    ) {
        MFP_MEDIAPLAYER_STATE state = MFP_MEDIAPLAYER_STATE_EMPTY;

        if (SUCCEEDED(media_inline_audio->GetState(&state))) {
            HRESULT hr = S_OK;

            if (state == MFP_MEDIAPLAYER_STATE_PLAYING)
                hr = media_inline_audio->Pause();
            else
                hr = media_inline_audio->Play();

            diag_log(
                "inline audio toggle state=%d hr=0x%08X path=%ls",
                (int)state,
                (unsigned int)hr,
                path
            );

            return SUCCEEDED(hr);
        }
    }

    media_inline_audio_release();
    CoInitialize(NULL);

    HRESULT hr =
        media_mf_create_player(
            path,
            NULL,
            &media_inline_audio
        );

    if (SUCCEEDED(hr) && media_inline_audio) {
        media_inline_audio->SetVolume(0.85f);
        hr = media_inline_audio->Play();
    }

    diag_log(
        "inline audio open hr=0x%08X path=%ls",
        (unsigned int)hr,
        path
    );

    if (FAILED(hr) || !media_inline_audio) {
        media_inline_audio_release();
        return false;
    }

    wcsncpy(
        media_inline_audio_path,
        path,
        ARRAYSIZE(media_inline_audio_path) - 1
    );
    media_inline_audio_path[ARRAYSIZE(media_inline_audio_path) - 1] = 0;

    return true;
}

static bool media_player_get_time(
    LONGLONG* position,
    LONGLONG* duration
) {
    if (!position || !duration)
        return false;

    *position = 0;
    *duration = 0;

    if (media_player_backend == 1 && media_player_mf) {
        PROPVARIANT p = {0};
        PROPVARIANT d = {0};

        HRESULT hp = media_player_mf->GetPosition(MFP_POSITIONTYPE_100NS, &p);
        HRESULT hd = media_player_mf->GetDuration(MFP_POSITIONTYPE_100NS, &d);

        if (
            SUCCEEDED(hp) &&
            SUCCEEDED(hd) &&
            p.vt == VT_I8 &&
            d.vt == VT_I8
        ) {
            *position = p.hVal.QuadPart;
            *duration = d.hVal.QuadPart;
            return *duration > 0;
        }

        return false;
    }

    if (media_player_backend == 2 && media_player_seeking) {
        return
            SUCCEEDED(media_player_seeking->GetCurrentPosition(position)) &&
            SUCCEEDED(media_player_seeking->GetDuration(duration)) &&
            *duration > 0;
    }

    return false;
}

static void media_player_set_position_v2(LONGLONG target) {
    if (media_player_backend == 1 && media_player_mf) {
        PROPVARIANT value = {0};
        value.vt = VT_I8;
        value.hVal.QuadPart = target;
        media_player_mf->SetPosition(MFP_POSITIONTYPE_100NS, &value);
        return;
    }

    if (media_player_backend == 2 && media_player_seeking) {
        media_player_seeking->SetPositions(
            &target,
            AM_SEEKING_AbsolutePositioning,
            NULL,
            AM_SEEKING_NoPositioning
        );
    }
}

static void media_player_draw_transport(DRAWITEMSTRUCT* dis) {
    if (!dis)
        return;

    RECT rc = dis->rcItem;
    FillRect(dis->hDC, &rc, GetSysColorBrush(COLOR_BTNFACE));

    DrawEdge(
        dis->hDC,
        &rc,
        (dis->itemState & ODS_SELECTED) ? EDGE_SUNKEN : EDGE_RAISED,
        BF_RECT
    );

    InflateRect(&rc, -7, -5);
    if (dis->itemState & ODS_SELECTED)
        OffsetRect(&rc, 1, 1);

    COLORREF color = GetSysColor(COLOR_BTNTEXT);
    HBRUSH brush = CreateSolidBrush(color);
    HPEN pen = CreatePen(PS_SOLID, 1, color);
    HGDIOBJ old_brush = SelectObject(dis->hDC, brush);
    HGDIOBJ old_pen = SelectObject(dis->hDC, pen);

    int cx = (rc.left + rc.right) / 2;
    int cy = (rc.top + rc.bottom) / 2;

    if (dis->CtlID == 10) {
        POINT tri[3] = {
            {cx - 5, cy - 7},
            {cx - 5, cy + 7},
            {cx + 7, cy}
        };
        Polygon(dis->hDC, tri, 3);
    } else if (dis->CtlID == 11) {
        Rectangle(dis->hDC, cx - 7, cy - 7, cx - 2, cy + 8);
        Rectangle(dis->hDC, cx + 2, cy - 7, cx + 7, cy + 8);
    } else if (dis->CtlID == 12) {
        Rectangle(dis->hDC, cx - 6, cy - 6, cx + 7, cy + 7);
    }

    SelectObject(dis->hDC, old_pen);
    SelectObject(dis->hDC, old_brush);
    DeleteObject(pen);
    DeleteObject(brush);
}

'''

s = s[:helper_pos] + helpers + s[helper_pos:]

release_v2 = r'''static void media_player_release_graph() {
    if (media_player_mf) {
        media_player_mf->Stop();
        media_player_mf->Shutdown();
        media_player_mf->Release();
        media_player_mf = NULL;
    }

    if (media_player_control)
        media_player_control->Stop();

    if (media_player_video) {
        media_player_video->put_Visible(OAFALSE);
        media_player_video->put_Owner((OAHWND)NULL);
        media_player_video->Release();
        media_player_video = NULL;
    }

    if (media_player_audio) {
        media_player_audio->Release();
        media_player_audio = NULL;
    }

    if (media_player_seeking) {
        media_player_seeking->Release();
        media_player_seeking = NULL;
    }

    if (media_player_control) {
        media_player_control->Release();
        media_player_control = NULL;
    }

    if (media_player_graph) {
        media_player_graph->Release();
        media_player_graph = NULL;
    }

    media_player_backend = 0;
}'''

s = replace_function(s, "static void media_player_release_graph()", release_v2)

update_v2 = r'''static void media_player_update_controls() {
    if (!hMediaPlayerSeek)
        return;

    LONGLONG position = 0;
    LONGLONG duration = 0;

    if (!media_player_get_time(&position, &duration))
        return;

    if (!media_player_user_seeking) {
        int slider = (int)(position * 1000LL / duration);
        SendMessageW(hMediaPlayerSeek, TBM_SETPOS, TRUE, slider);
    }

    if (hMediaPlayerTime) {
        wchar_t now_text[32] = {0};
        wchar_t total_text[32] = {0};
        wchar_t combined[80] = {0};

        media_player_format_time(position, now_text, ARRAYSIZE(now_text));
        media_player_format_time(duration, total_text, ARRAYSIZE(total_text));

        _snwprintf(
            combined,
            ARRAYSIZE(combined) - 1,
            L"%s / %s",
            now_text,
            total_text
        );
        combined[ARRAYSIZE(combined) - 1] = 0;
        SetWindowTextW(hMediaPlayerTime, combined);
    }
}'''

s = replace_function(s, "static void media_player_update_controls()", update_v2)

layout_v2 = r'''static void media_player_layout_video() {
    if (media_player_backend == 1 && media_player_mf) {
        media_player_mf->UpdateVideo();
        return;
    }

    if (
        media_player_backend != 2 ||
        !media_player_video ||
        !hMediaPlayerVideoHost
    ) {
        return;
    }

    RECT rc;
    GetClientRect(hMediaPlayerVideoHost, &rc);
    media_player_video->SetWindowPosition(0, 0, rc.right, rc.bottom);
}'''

s = replace_function(s, "static void media_player_layout_video()", layout_v2)

player_window_v2 = r'''static LRESULT CALLBACK TelegacyMediaPlayerWindow(
    HWND hwnd,
    UINT msg,
    WPARAM wParam,
    LPARAM lParam
) {
    switch (msg) {
        case WM_CREATE: {
            HFONT font = (HFONT)GetStockObject(DEFAULT_GUI_FONT);

            hMediaPlayerVideoHost = CreateWindowExW(
                WS_EX_CLIENTEDGE,
                L"STATIC",
                L"",
                WS_CHILD | WS_VISIBLE | SS_BLACKRECT,
                8, 8, 544, 306,
                hwnd,
                (HMENU)1,
                NULL,
                NULL
            );

            hMediaPlayerPlay = CreateWindowW(
                L"BUTTON", L"",
                WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_OWNERDRAW,
                8, 324, 42, 24,
                hwnd, (HMENU)10, NULL, NULL
            );

            hMediaPlayerPause = CreateWindowW(
                L"BUTTON", L"",
                WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_OWNERDRAW,
                55, 324, 42, 24,
                hwnd, (HMENU)11, NULL, NULL
            );

            hMediaPlayerStop = CreateWindowW(
                L"BUTTON", L"",
                WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_OWNERDRAW,
                102, 324, 42, 24,
                hwnd, (HMENU)12, NULL, NULL
            );

            hMediaPlayerVolume = CreateWindowExW(
                0,
                TRACKBAR_CLASSW,
                L"",
                WS_CHILD | WS_VISIBLE | TBS_HORZ | TBS_NOTICKS,
                152, 324, 160, 24,
                hwnd, (HMENU)15, NULL, NULL
            );

            hMediaPlayerTime = CreateWindowW(
                L"STATIC",
                L"00:00 / 00:00",
                WS_CHILD | WS_VISIBLE | SS_RIGHT | SS_CENTERIMAGE,
                398, 324, 154, 24,
                hwnd, (HMENU)13, NULL, NULL
            );

            hMediaPlayerSeek = CreateWindowExW(
                0,
                TRACKBAR_CLASSW,
                L"",
                WS_CHILD | WS_VISIBLE | TBS_HORZ | TBS_NOTICKS,
                8, 354, 544, 28,
                hwnd, (HMENU)14, NULL, NULL
            );

            SendMessageW(hMediaPlayerSeek, TBM_SETRANGE, TRUE, MAKELPARAM(0, 1000));
            SendMessageW(hMediaPlayerVolume, TBM_SETRANGE, TRUE, MAKELPARAM(0, 100));
            SendMessageW(hMediaPlayerVolume, TBM_SETPOS, TRUE, 85);
            SendMessageW(hMediaPlayerTime, WM_SETFONT, (WPARAM)font, TRUE);

            SetTimer(hwnd, MEDIA_PLAYER_TIMER, 250, NULL);
            return 0;
        }

        case WM_SIZE: {
            RECT rc;
            GetClientRect(hwnd, &rc);

            int client_w = rc.right - rc.left;
            int client_h = rc.bottom - rc.top;
            int controls_y = client_h - 84;
            int seek_y = client_h - 48;

            MoveWindow(hMediaPlayerVideoHost, 8, 8, client_w - 16, controls_y - 16, TRUE);
            MoveWindow(hMediaPlayerPlay, 8, controls_y, 42, 24, TRUE);
            MoveWindow(hMediaPlayerPause, 55, controls_y, 42, 24, TRUE);
            MoveWindow(hMediaPlayerStop, 102, controls_y, 42, 24, TRUE);
            MoveWindow(hMediaPlayerVolume, 152, controls_y, 160, 24, TRUE);
            MoveWindow(hMediaPlayerTime, client_w - 162, controls_y, 154, 24, TRUE);
            MoveWindow(hMediaPlayerSeek, 8, seek_y, client_w - 16, 28, TRUE);

            media_player_layout_video();
            return 0;
        }

        case WM_DRAWITEM: {
            DRAWITEMSTRUCT* dis = (DRAWITEMSTRUCT*)lParam;
            if (dis && (dis->CtlID == 10 || dis->CtlID == 11 || dis->CtlID == 12)) {
                media_player_draw_transport(dis);
                return TRUE;
            }
            break;
        }

        case WM_COMMAND:
            switch (LOWORD(wParam)) {
                case 10:
                    if (media_player_backend == 1 && media_player_mf)
                        media_player_mf->Play();
                    else if (media_player_control)
                        media_player_control->Run();
                    return 0;

                case 11:
                    if (media_player_backend == 1 && media_player_mf)
                        media_player_mf->Pause();
                    else if (media_player_control)
                        media_player_control->Pause();
                    return 0;

                case 12:
                    if (media_player_backend == 1 && media_player_mf)
                        media_player_mf->Stop();
                    else if (media_player_control) {
                        media_player_control->Stop();
                        media_player_set_position_v2(0);
                    }
                    media_player_update_controls();
                    return 0;
            }
            break;

        case WM_HSCROLL: {
            HWND source = (HWND)lParam;

            if (source == hMediaPlayerSeek) {
                int code = LOWORD(wParam);
                if (code == TB_THUMBTRACK || code == TB_THUMBPOSITION || code == TB_ENDTRACK) {
                    media_player_user_seeking = true;

                    int slider = (int)SendMessageW(hMediaPlayerSeek, TBM_GETPOS, 0, 0);
                    LONGLONG position = 0;
                    LONGLONG duration = 0;

                    if (media_player_get_time(&position, &duration))
                        media_player_set_position_v2(duration * slider / 1000LL);

                    if (code == TB_ENDTRACK || code == TB_THUMBPOSITION)
                        media_player_user_seeking = false;

                    media_player_update_controls();
                }
                return 0;
            }

            if (source == hMediaPlayerVolume) {
                int value = (int)SendMessageW(hMediaPlayerVolume, TBM_GETPOS, 0, 0);

                if (media_player_backend == 1 && media_player_mf) {
                    media_player_mf->SetVolume((float)value / 100.0f);
                } else if (media_player_audio) {
                    long volume = value <= 0 ? -10000 : -5000 + value * 50;
                    if (volume > 0)
                        volume = 0;
                    media_player_audio->put_Volume(volume);
                }

                return 0;
            }

            break;
        }

        case WM_TIMER:
            if (wParam == MEDIA_PLAYER_TIMER) {
                media_player_update_controls();
                return 0;
            }
            break;

        case WM_CLOSE:
            DestroyWindow(hwnd);
            return 0;

        case WM_DESTROY:
            KillTimer(hwnd, MEDIA_PLAYER_TIMER);
            media_player_release_graph();

            hMediaPlayerWindow = NULL;
            hMediaPlayerVideoHost = NULL;
            hMediaPlayerInfo = NULL;
            hMediaPlayerPlay = NULL;
            hMediaPlayerPause = NULL;
            hMediaPlayerStop = NULL;
            hMediaPlayerSeek = NULL;
            hMediaPlayerVolume = NULL;
            hMediaPlayerTime = NULL;
            return 0;
    }

    return DefWindowProcW(hwnd, msg, wParam, lParam);
}'''

s = replace_function(s, "static LRESULT CALLBACK TelegacyMediaPlayerWindow(", player_window_v2)

player_open_v2 = r'''static bool media_player_open(
    const wchar_t* path,
    bool video
) {
    if (!path || !path[0])
        return false;

    // Music never opens a separate window anymore.
    if (!video)
        return media_inline_audio_toggle(path);

    if (hMediaPlayerWindow && IsWindow(hMediaPlayerWindow))
        DestroyWindow(hMediaPlayerWindow);

    media_player_release_graph();
    media_player_is_video = true;

    HINSTANCE instance = GetModuleHandleW(NULL);

    WNDCLASSEXW wc = {0};
    wc.cbSize = sizeof(wc);
    wc.lpfnWndProc = TelegacyMediaPlayerWindow;
    wc.hInstance = instance;
    wc.hCursor = LoadCursor(NULL, IDC_ARROW);
    wc.hbrBackground = (HBRUSH)(COLOR_BTNFACE + 1);
    wc.lpszClassName = L"TelegacyMediaPlayer98";

    WNDCLASSEXW existing = {0};
    existing.cbSize = sizeof(existing);

    if (!GetClassInfoExW(instance, wc.lpszClassName, &existing)) {
        if (!RegisterClassExW(&wc))
            return false;
    }

    const wchar_t* leaf = wcsrchr(path, L'\\');
    leaf = leaf ? leaf + 1 : path;

    wchar_t title[360] = {0};
    _snwprintf(
        title,
        ARRAYSIZE(title) - 1,
        L"%s - Telegacy Media Player",
        leaf
    );

    hMediaPlayerWindow = CreateWindowExW(
        WS_EX_TOOLWINDOW,
        wc.lpszClassName,
        title,
        WS_OVERLAPPEDWINDOW | WS_VISIBLE,
        CW_USEDEFAULT,
        CW_USEDEFAULT,
        600,
        455,
        hMain,
        NULL,
        instance,
        NULL
    );

    if (!hMediaPlayerWindow)
        return false;

    CoInitialize(NULL);

    HRESULT mf_hr =
        media_mf_create_player(
            path,
            hMediaPlayerVideoHost,
            &media_player_mf
        );

    if (SUCCEEDED(mf_hr) && media_player_mf) {
        media_player_backend = 1;
        media_player_mf->SetVolume(0.85f);
        mf_hr = media_player_mf->Play();
    }

    diag_log(
        "media player MFPlay hr=0x%08X path=%ls",
        (unsigned int)mf_hr,
        path
    );

    if (SUCCEEDED(mf_hr) && media_player_mf) {
        media_player_layout_video();
        media_player_update_controls();
        SetForegroundWindow(hMediaPlayerWindow);
        return true;
    }

    if (media_player_mf) {
        media_player_mf->Shutdown();
        media_player_mf->Release();
        media_player_mf = NULL;
    }

    HRESULT ds_hr =
        CoCreateInstance(
            CLSID_FilterGraph,
            NULL,
            CLSCTX_INPROC_SERVER,
            IID_IGraphBuilder,
            (void**)&media_player_graph
        );

    if (SUCCEEDED(ds_hr) && media_player_graph)
        ds_hr = media_player_graph->RenderFile(path, NULL);

    diag_log(
        "media player DirectShow fallback hr=0x%08X path=%ls",
        (unsigned int)ds_hr,
        path
    );

    if (SUCCEEDED(ds_hr) && media_player_graph) {
        media_player_graph->QueryInterface(IID_IMediaControl, (void**)&media_player_control);
        media_player_graph->QueryInterface(IID_IMediaSeeking, (void**)&media_player_seeking);
        media_player_graph->QueryInterface(IID_IBasicAudio, (void**)&media_player_audio);
        media_player_graph->QueryInterface(IID_IVideoWindow, (void**)&media_player_video);

        media_player_backend = 2;

        if (media_player_video && hMediaPlayerVideoHost) {
            media_player_video->put_Owner((OAHWND)hMediaPlayerVideoHost);
            media_player_video->put_WindowStyle(WS_CHILD | WS_CLIPSIBLINGS | WS_CLIPCHILDREN);
            media_player_video->put_Visible(OATRUE);
        }

        if (media_player_audio)
            media_player_audio->put_Volume(-750);

        if (media_player_control)
            media_player_control->Run();

        media_player_layout_video();
        media_player_update_controls();
        SetForegroundWindow(hMediaPlayerWindow);
        return true;
    }

    wchar_t error[420] = {0};
    _snwprintf(
        error,
        ARRAYSIZE(error) - 1,
        L"Windows could not decode this video.\r\n\r\nMedia Foundation: 0x%08X\r\nDirectShow: 0x%08X",
        (unsigned int)mf_hr,
        (unsigned int)ds_hr
    );

    MessageBoxW(
        hMediaPlayerWindow,
        error,
        L"Telegacy Media Player",
        MB_OK | MB_ICONERROR
    );

    DestroyWindow(hMediaPlayerWindow);
    return false;
}'''

s = replace_function(s, "static bool media_player_open(", player_open_v2)

kind_v2 = r'''static int media_player_kind_from_path(
    const wchar_t* path
) {
    if (!path || !path[0])
        return 0;

    const wchar_t* dot = wcsrchr(path, L'.');
    if (!dot)
        return 0;

    if (
        _wcsicmp(dot, L".mp4") == 0 ||
        _wcsicmp(dot, L".m4v") == 0 ||
        _wcsicmp(dot, L".mov") == 0 ||
        _wcsicmp(dot, L".avi") == 0 ||
        _wcsicmp(dot, L".mkv") == 0 ||
        _wcsicmp(dot, L".webm") == 0 ||
        _wcsicmp(dot, L".wmv") == 0
    ) {
        return 1;
    }

    if (media_player_is_music_path(path))
        return 2;

    return 0;
}'''

s = replace_function(s, "static int media_player_kind_from_path(", kind_v2)

try_chat_v2 = r'''static bool media_player_try_open_chat_path(
    const wchar_t* path
) {
    int kind = media_player_kind_from_path(path);

    if (!kind)
        return false;

    media_chat_autoplay_path[0] = 0;
    media_chat_autoplay_kind = 0;

    if (kind == 2)
        return media_inline_audio_toggle(path);

    return media_player_open(path, true);
}'''

s = replace_function(s, "static bool media_player_try_open_chat_path(", try_chat_v2)

chat_complete_v2 = r'''void media_player_chat_download_complete(
    const wchar_t* path
) {
    if (
        !path ||
        !path[0] ||
        !media_chat_autoplay_path[0] ||
        media_chat_autoplay_kind == 0 ||
        _wcsicmp(path, media_chat_autoplay_path) != 0
    ) {
        return;
    }

    int kind = media_chat_autoplay_kind;
    media_chat_autoplay_path[0] = 0;
    media_chat_autoplay_kind = 0;

    if (kind == 2)
        media_inline_audio_toggle(path);
    else if (kind == 1)
        media_player_open(path, true);
}'''

s = replace_function(s, "void media_player_chat_download_complete(", chat_complete_v2)

# Prevent a Media jump from destroying the gallery cache.
clear_v2 = r'''void message_search_clear_chat_view() {
    for (int i = (int)documents.size() - 1; i >= 0; i--) {
        free(documents[i].filename);
        free(documents[i].file_reference);
    }

    documents.clear();

    for (int i = (int)links.size() - 1; i >= 0; i--)
        free(links[i].lpstrText);

    links.clear();
    messages.clear();

    memset(group_id_tofront, 0, sizeof(group_id_tofront));
    memset(group_id, 0, sizeof(group_id));

    if (chat)
        SendMessageW(chat, WM_SETTEXT, 0, (LPARAM)L"");

    if (!media_archive_preserve_on_chat_clear)
        media_archive_clear();
}'''

s = replace_function(s, "void message_search_clear_chat_view()", clear_v2)

# Make the already-existing refresh less destructive visually.
refresh_start, refresh_end = function_range(s, "static void media_archive_refresh() {")
refresh_func = s[refresh_start:refresh_end]
refresh_func = refresh_func.replace("RDW_ERASE |\n", "")
refresh_func = refresh_func.replace("RDW_ERASE |\r\n", "")
s = s[:refresh_start] + refresh_func + s[refresh_end:]

write(t, s)


# -----------------------------------------------------------------------------
# response.cpp: preserve Media on jump + request video document thumbnails
# -----------------------------------------------------------------------------

s = read(r)

jump_start, jump_end = function_range(s, "static void media_archive_handle_jump_response(")
jump_func = s[jump_start:jump_end]

old = "    message_search_clear_chat_view();"
if old not in jump_func:
    raise SystemExit("Could not locate chat clear inside Media jump response")

jump_func = jump_func.replace(
    old,
    "    media_archive_preserve_on_chat_clear = true;\n"
    "    message_search_clear_chat_view();\n"
    "    media_archive_preserve_on_chat_clear = false;",
    1,
)
s = s[:jump_start] + jump_func + s[jump_end:]

# Document flags bit 0 means thumbs are present in the Document constructor.
parser_start, parser_end = function_range(s, "static bool media_tabs_extract_document(")
parser = s[parser_start:parser_end]

old = "    document->photo_size = 0;"
if old in parser:
    parser = parser.replace(
        old,
        "    document->photo_size =\n"
        "        (kind == 1 && (doc_flags & (1 << 0))) ? 2 : 0;",
        1,
    )

s = s[:parser_start] + parser + s[parser_end:]
write(r, s)


# -----------------------------------------------------------------------------
# message.cpp: music gets a compact inline Win98-ish play row
# -----------------------------------------------------------------------------

s = read(m)

if "media_inline_music_row_v2" not in s:
    old = "\t\tbool voice = false, gif = false, round = false, sticker = false;"
    if old not in s:
        raise SystemExit("Could not locate document media flags in message.cpp")

    s = s.replace(
        old,
        "\t\tbool voice = false, gif = false, round = false, sticker = false, music = false; // media_inline_music_row_v2",
        1,
    )

    old = "\t\t\t\t\t\tvoice = (att_flags & (1 << 10)) ? true : false;"
    if old not in s:
        raise SystemExit("Could not locate DocumentAttributeAudio voice flag")

    s = s.replace(old, old + "\n\t\t\t\t\t\tmusic = !voice;", 1)

    old = (
        "\t\t\tdocument.min = cr_startmsg.cpMin + written;\n"
        "\t\t\twritten += riched_write(chat, document.filename);\n"
        "\t\t\tdocument.max = cr_startmsg.cpMin + written;\n"
        "\t\t\tif (duration_str[0] == ' ') written += riched_write(chat, &duration_str[0]);\n"
        "\t\t\twritten += riched_write(chat, &size_str[0]);"
    )

    new = (
        "\t\t\tdocument.min = cr_startmsg.cpMin + written;\n"
        "\t\t\tif (music) written += riched_write(chat, L\"[>] \" );\n"
        "\t\t\twritten += riched_write(chat, document.filename);\n"
        "\t\t\tif (duration_str[0] == ' ') written += riched_write(chat, &duration_str[0]);\n"
        "\t\t\twritten += riched_write(chat, &size_str[0]);\n"
        "\t\t\tdocument.max = cr_startmsg.cpMin + written;"
    )

    if old not in s:
        raise SystemExit("Could not locate document row rendering block")

    s = s.replace(old, new, 1)

write(m, s)


# -----------------------------------------------------------------------------
# Chat click behavior: one click on music; double click on video.
# This is deliberately a small textual rewrite so the v1 download machinery stays.
# -----------------------------------------------------------------------------

s = read(t)

queue_old = '''\t\t\t\t\tif (\n\t\t\t\t\t\tmedia_double_click &&\n\t\t\t\t\t\tmedia_player_kind_from_path(documents[i].filename) != 0\n\t\t\t\t\t) {\n\t\t\t\t\t\tmedia_player_queue_chat_autoplay(\n\t\t\t\t\t\t\tdocuments[i].filename\n\t\t\t\t\t\t);\n\t\t\t\t\t}\n'''

if queue_old in s:
    queue_new = '''\t\t\t\t\tint media_kind = media_player_kind_from_path(documents[i].filename);\n\t\t\t\t\tbool media_play_request =\n\t\t\t\t\t\t(media_kind == 2 && !media_double_click) ||\n\t\t\t\t\t\t(media_kind == 1 && media_double_click);\n\n\t\t\t\t\tif (media_play_request) {\n\t\t\t\t\t\tmedia_player_queue_chat_autoplay(\n\t\t\t\t\t\t\tdocuments[i].filename\n\t\t\t\t\t\t);\n\t\t\t\t\t}\n'''
    s = s.replace(queue_old, queue_new, 1)

    # Existing v1 has two guards that prevent an in-progress double-click from
    # cancelling its own download. Extend those guards to music single-click.
    s = s.replace(
        "media_double_click &&\n\t\t\t\t\t\t\t\t\tmedia_player_kind_from_path(documents[i].filename) != 0",
        "media_play_request",
        1,
    )
    s = s.replace(
        "media_double_click &&\n\t\t\t\t\t\t\t\tmedia_player_kind_from_path(documents[i].filename) != 0",
        "media_play_request",
        1,
    )

    open_old = '''\t\t\t\t\t\t} else if (media_double_click) {\n\t\t\t\t\t\t\tif (!media_player_try_open_chat_path(documents[i].filename)) {\n\t\t\t\t\t\t\t\tif ((INT_PTR)ShellExecute(NULL, L"open", documents[i].filename, NULL, NULL, SW_SHOWNORMAL) <= 32) {\n\t\t\t\t\t\t\t\t\twchar_t cmd[MAX_PATH * 2];\n\t\t\t\t\t\t\t\t\tswprintf(cmd, L"shell32.dll,OpenAs_RunDLL %s", documents[i].filename);\n\t\t\t\t\t\t\t\t\tShellExecute(NULL, L"open", L"rundll32.exe", cmd, NULL, SW_SHOWNORMAL);\n\t\t\t\t\t\t\t\t}\n\t\t\t\t\t\t\t}\n\t\t\t\t\t\t}\n'''

    open_new = '''\t\t\t\t\t\t} else if (media_play_request) {\n\t\t\t\t\t\t\tmedia_player_try_open_chat_path(documents[i].filename);\n\t\t\t\t\t\t} else if (media_double_click && media_kind == 0) {\n\t\t\t\t\t\t\tif ((INT_PTR)ShellExecute(NULL, L"open", documents[i].filename, NULL, NULL, SW_SHOWNORMAL) <= 32) {\n\t\t\t\t\t\t\t\twchar_t cmd[MAX_PATH * 2];\n\t\t\t\t\t\t\t\tswprintf(cmd, L"shell32.dll,OpenAs_RunDLL %s", documents[i].filename);\n\t\t\t\t\t\t\t\tShellExecute(NULL, L"open", L"rundll32.exe", cmd, NULL, SW_SHOWNORMAL);\n\t\t\t\t\t\t\t}\n\t\t\t\t\t\t}\n'''

    if open_old in s:
        s = s.replace(open_old, open_new, 1)

write(t, s)


# -----------------------------------------------------------------------------
# Final diagnostics / marker
# -----------------------------------------------------------------------------

s = read(t)
if "media_tabs_av_runtime_v2" not in s:
    raise SystemExit("Media v2 marker missing after patch")

for token in (
    "MFPCreateMediaPlayer",
    "media_inline_audio_toggle",
    "media_archive_preserve_on_chat_clear",
    "BS_OWNERDRAW",
):
    if token not in s:
        raise SystemExit(f"Media v2 verification failed: {token}")

print(
    "Applied Media A/V v2: MFPlay-first video, DirectShow fallback, "
    "inline chat music, classic transport buttons, Media state preservation, "
    "and reduced redraw/flicker."
)


# =============================================================================
# Media A/V v3.1 (compile-order fixes)
# - truly atomic Media page swaps (no empty-page flash / per-thumb repaint)
# - full-size photo download on double click (not the cached preview)
# - Telegram document thumbnails for video in Media and in the chat
# - visible two-line inline music player with live progress
# - keep Media contents intact while jumping to a message
# =============================================================================

g = root / "src" / "helpers.cpp"
if not g.exists():
    raise SystemExit(f"Missing expected Telegacy file: {g}")

# -----------------------------------------------------------------------------
# telegacy.h declarations
# -----------------------------------------------------------------------------

s = read(h)

if "media_tabs_av_v3" not in s:
    anchor = "bool media_inline_audio_toggle(const wchar_t* path);"
    if anchor not in s:
        raise SystemExit("Could not locate Media v2 declarations in telegacy.h")

    s = s.replace(
        anchor,
        anchor
        + "\nstruct DCInfo;"
        + "\nvoid media_archive_request_video_thumbnail(Document* document, DCInfo* dcInfo);"
        + "\nbool media_archive_handle_full_photo_upload(const BYTE* rpc_id, BYTE* response, int length);"
        + "\n// media_tabs_av_v3",
        1,
    )

write(h, s)


# -----------------------------------------------------------------------------
# helpers.cpp: photo_size == 3 is our JPEG document-thumbnail sentinel.
# It must use inputDocumentFileLocation, like stickers, but is decoded as JPEG
# by response.cpp because only photo_size == 1 takes the WebP sticker path.
# -----------------------------------------------------------------------------

s = read(g)

old = "(rce || document->photo_size == 1) ? 0xbad07584 : 0x40181ffe"
new = "(rce || document->photo_size == 1 || document->photo_size == 3) ? 0xbad07584 : 0x40181ffe"

if old in s:
    s = s.replace(old, new, 1)
elif new not in s:
    raise SystemExit("Could not locate input file-location selection in get_photo().")

write(g, s)


# -----------------------------------------------------------------------------
# telegacy.cpp
# -----------------------------------------------------------------------------

s = read(t)

if "media_tabs_av_runtime_v3" not in s:
    # Extend MediaArchiveItem. Images now keep the original Photo location too,
    # while bitmap remains only the lightweight preview used by the grid.
    struct_old = r'''struct MediaArchiveItem {
    __int64 document_id;
    int message_id;
    int page_index;
    HBITMAP bitmap;
    wchar_t file_path[MAX_PATH];

    // media_tabs_av_runtime_v1
    int media_kind;        // 0 image, 1 video, 2 music
    int duration;
    bool has_document;
    Document av_document;
    wchar_t display_name[260];
};'''

    struct_new = r'''struct MediaArchiveItem {
    __int64 document_id;
    int message_id;
    int page_index;
    HBITMAP bitmap;
    wchar_t file_path[MAX_PATH];

    // media_tabs_av_runtime_v1
    int media_kind;        // 0 image, 1 video, 2 music
    int duration;
    bool has_document;
    bool full_file_ready;  // media_tabs_av_runtime_v3
    Document av_document;
    wchar_t display_name[260];
};'''

    if struct_old not in s:
        raise SystemExit("Could not locate MediaArchiveItem v1/v2 layout.")

    s = s.replace(struct_old, struct_new, 1)

    global_anchor = "bool media_archive_preserve_on_chat_clear = false;"
    if global_anchor not in s:
        raise SystemExit("Could not locate Media v2 globals.")

    globals_v3 = r'''

// media_tabs_av_runtime_v3
static int media_full_photo_pending_item = -1;
static LONGLONG media_full_photo_offset = 0;
static BYTE media_full_photo_rpc_id[8] = {0};
static wchar_t media_full_photo_path[MAX_PATH] = {0};

static UINT_PTR media_inline_audio_timer = 0;
static int media_inline_audio_last_second = -1;
'''

    s = s.replace(global_anchor, global_anchor + globals_v3, 1)

    # Forward declaration because add_document() occurs after the Media window
    # helpers and calls this when the last preview arrives.
    forward_anchor = r'''static bool media_archive_request_server_page(
    int offset_id
);'''
    if forward_anchor not in s:
        raise SystemExit("Could not locate Media request forward declaration.")

    s = s.replace(
        forward_anchor,
        forward_anchor
        + "\n\nstatic bool media_archive_server_queue_empty();"
        + "\nstatic void media_archive_update_nav();"
        + "\nstatic void media_archive_commit_ready_page();",
        1,
    )

    # -------------------------------------------------------------------------
    # Video document thumbnail request + full Photo downloader + inline audio UI
    # -------------------------------------------------------------------------

    insert_at = s.find("static void media_player_release_graph()")
    if insert_at < 0:
        raise SystemExit("Could not locate player helper insertion point.")

    helpers_v3 = r'''
static void media_archive_shell_open(
    const wchar_t* path
) {
    if (!path || !path[0])
        return;

    HINSTANCE result =
        ShellExecuteW(
            hMediaArchiveWindow
                ? hMediaArchiveWindow
                : hMain,
            L"open",
            path,
            NULL,
            NULL,
            SW_SHOWNORMAL
        );

    if ((INT_PTR)result <= 32)
        MessageBeep(MB_ICONASTERISK);
}

void media_archive_request_video_thumbnail(
    Document* document,
    DCInfo* dcInfo
) {
    if (
        !document ||
        !dcInfo ||
        !document->file_reference
    ) {
        return;
    }

    BYTE unenc_query[192] = {0};
    BYTE enc_query[216] = {0};

    internal_header(
        dcInfo,
        unenc_query,
        true
    );

    memcpy(
        document->photo_msg_id,
        unenc_query + 16,
        8
    );

    // upload.getFile#be5335be
    write_le(unenc_query + 32, 0xbe5335be, 4);
    write_le(unenc_query + 36, 0, 4);

    // inputDocumentFileLocation#bad07584
    write_le(unenc_query + 40, 0xbad07584, 4);
    memcpy(unenc_query + 44, document->id, 8);
    memcpy(unenc_query + 52, document->access_hash, 8);

    int file_ref_len =
        tlstr_len(
            document->file_reference,
            true
        );

    if (
        file_ref_len <= 0 ||
        60 + file_ref_len + 16 >
            (int)sizeof(unenc_query)
    ) {
        memset(document->photo_msg_id, 0, 8);
        return;
    }

    memcpy(
        unenc_query + 60,
        document->file_reference,
        file_ref_len
    );

    int offset = 60 + file_ref_len;

    // thumb_size:string = "m"
    memset(unenc_query + offset, 0, 12);
    unenc_query[offset] = 1;
    unenc_query[offset + 1] = 'm';
    offset += 12; // 4-byte TL string + offset:long(0)

    write_le(unenc_query + offset, 1048576, 4);
    offset += 4;

    write_le(unenc_query + 28, offset - 32, 4);

    int padding_len = get_padding(offset);
    fortuna_read(unenc_query + offset, padding_len, &prng);
    offset += padding_len;

    if (!convert_message(dcInfo, unenc_query, enc_query, offset, 0)) {
        memset(document->photo_msg_id, 0, 8);
        return;
    }

    send_query(
        dcInfo,
        enc_query,
        offset + 24
    );
}

static bool media_archive_send_full_photo_chunk() {
    if (
        media_full_photo_pending_item < 0 ||
        media_full_photo_pending_item >=
            (int)media_archive_items.size()
    ) {
        return false;
    }

    MediaArchiveItem* item =
        &media_archive_items[
            media_full_photo_pending_item
        ];

    if (
        item->media_kind != 0 ||
        !item->has_document ||
        !item->av_document.file_reference ||
        item->av_document.photo_size <= 1
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
        media_full_photo_rpc_id,
        unenc_query + 16,
        8
    );

    // upload.getFile#be5335be
    write_le(unenc_query + 32, 0xbe5335be, 4);
    write_le(unenc_query + 36, 0, 4);

    // inputPhotoFileLocation#40181ffe
    write_le(unenc_query + 40, 0x40181ffe, 4);
    memcpy(unenc_query + 44, item->av_document.id, 8);
    memcpy(unenc_query + 52, item->av_document.access_hash, 8);

    int file_ref_len =
        tlstr_len(
            item->av_document.file_reference,
            true
        );

    if (
        file_ref_len <= 0 ||
        60 + file_ref_len + 16 >
            (int)sizeof(unenc_query)
    ) {
        return false;
    }

    memcpy(
        unenc_query + 60,
        item->av_document.file_reference,
        file_ref_len
    );

    int offset = 60 + file_ref_len;

    // thumb_size:string = the largest size found in the Telegram Photo object.
    memset(unenc_query + offset, 0, 12);
    unenc_query[offset] = 1;
    unenc_query[offset + 1] =
        (BYTE)item->av_document.photo_size;

    // upload.getFile offset:long follows the padded 4-byte TL string.
    write_le(
        unenc_query + offset + 4,
        media_full_photo_offset,
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
        "media full photo request item=%d size=%c offset=%I64d sent=%d",
        media_full_photo_pending_item,
        item->av_document.photo_size,
        media_full_photo_offset,
        sent
    );

    return sent > 0;
}

static bool media_archive_begin_full_photo_download(
    int item_index
) {
    if (
        item_index < 0 ||
        item_index >=
            (int)media_archive_items.size()
    ) {
        return false;
    }

    MediaArchiveItem* item =
        &media_archive_items[item_index];

    if (item->media_kind != 0)
        return false;

    if (
        item->full_file_ready &&
        item->file_path[0] &&
        GetFileAttributesW(item->file_path) !=
            INVALID_FILE_ATTRIBUTES
    ) {
        media_archive_shell_open(item->file_path);
        return true;
    }

    if (
        !item->has_document ||
        !item->av_document.file_reference ||
        item->av_document.photo_size <= 1
    ) {
        // Fallback only for legacy/cached entries that don't have the Photo
        // location metadata. Never intentionally prefer the grid thumbnail.
        if (item->file_path[0]) {
            media_archive_shell_open(item->file_path);
            return true;
        }
        return false;
    }

    if (media_full_photo_pending_item >= 0) {
        MessageBeep(MB_ICONASTERISK);
        return false;
    }

    wchar_t temp_dir[MAX_PATH] = {0};
    DWORD len =
        GetTempPathW(
            ARRAYSIZE(temp_dir),
            temp_dir
        );

    if (!len || len >= ARRAYSIZE(temp_dir))
        return false;

    if (wcslen(temp_dir) + 16 >= ARRAYSIZE(temp_dir))
        return false;

    wcscat(temp_dir, L"TelegacyMedia");
    CreateDirectoryW(temp_dir, NULL);

    _snwprintf(
        media_full_photo_path,
        ARRAYSIZE(media_full_photo_path) - 1,
        L"%s\\photo_%016I64X.jpg",
        temp_dir,
        item->document_id
    );
    media_full_photo_path[
        ARRAYSIZE(media_full_photo_path) - 1
    ] = 0;

    DeleteFileW(media_full_photo_path);

    media_full_photo_pending_item = item_index;
    media_full_photo_offset = 0;
    memset(media_full_photo_rpc_id, 0, 8);

    if (!media_archive_send_full_photo_chunk()) {
        media_full_photo_pending_item = -1;
        media_full_photo_path[0] = 0;
        return false;
    }

    return true;
}

bool media_archive_handle_full_photo_upload(
    const BYTE* rpc_id,
    BYTE* response,
    int length
) {
    if (
        media_full_photo_pending_item < 0 ||
        !rpc_id ||
        !response ||
        length < 13 ||
        memcmp(
            rpc_id,
            media_full_photo_rpc_id,
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
        diag_log("media full photo malformed upload.file size=%d length=%d", size, length);
        media_full_photo_pending_item = -1;
        return true;
    }

    FILE* f =
        _wfopen(
            media_full_photo_path,
            media_full_photo_offset == 0
                ? L"wb"
                : L"ab"
        );

    if (!f) {
        media_full_photo_pending_item = -1;
        return true;
    }

    if (size > 0) {
        fwrite(
            response + data_pos,
            1,
            size,
            f
        );
    }

    fclose(f);

    media_full_photo_offset += size;

    MediaArchiveItem* item = NULL;

    if (
        media_full_photo_pending_item >= 0 &&
        media_full_photo_pending_item <
            (int)media_archive_items.size()
    ) {
        item =
            &media_archive_items[
                media_full_photo_pending_item
            ];
    }

    bool more =
        size >= 1048576 &&
        (
            !item ||
            item->av_document.size <= 0 ||
            media_full_photo_offset <
                item->av_document.size
        );

    if (more) {
        if (!media_archive_send_full_photo_chunk()) {
            media_full_photo_pending_item = -1;
        }
        return true;
    }

    int finished_item =
        media_full_photo_pending_item;

    media_full_photo_pending_item = -1;
    memset(media_full_photo_rpc_id, 0, 8);

    if (
        finished_item >= 0 &&
        finished_item <
            (int)media_archive_items.size()
    ) {
        MediaArchiveItem* finished =
            &media_archive_items[finished_item];

        wcsncpy(
            finished->file_path,
            media_full_photo_path,
            ARRAYSIZE(finished->file_path) - 1
        );
        finished->file_path[
            ARRAYSIZE(finished->file_path) - 1
        ] = 0;
        finished->full_file_ready = true;
    }

    diag_log(
        "media full photo complete item=%d bytes=%I64d path=%ls",
        finished_item,
        media_full_photo_offset,
        media_full_photo_path
    );

    media_archive_shell_open(
        media_full_photo_path
    );

    return true;
}

static void media_inline_audio_apply_visual(
    bool force
) {
    if (
        !chat ||
        !media_inline_audio ||
        !media_inline_audio_path[0]
    ) {
        return;
    }

    MFP_MEDIAPLAYER_STATE state =
        MFP_MEDIAPLAYER_STATE_EMPTY;

    media_inline_audio->GetState(&state);

    PROPVARIANT p = {0};
    PROPVARIANT d = {0};

    LONGLONG position = 0;
    LONGLONG duration = 0;

    if (
        SUCCEEDED(
            media_inline_audio->GetPosition(
                MFP_POSITIONTYPE_100NS,
                &p
            )
        ) &&
        p.vt == VT_I8
    ) {
        position = p.hVal.QuadPart;
    }

    if (
        SUCCEEDED(
            media_inline_audio->GetDuration(
                MFP_POSITIONTYPE_100NS,
                &d
            )
        ) &&
        d.vt == VT_I8
    ) {
        duration = d.hVal.QuadPart;
    }

    int current_second =
        (int)(position / 10000000LL);

    if (
        !force &&
        current_second ==
            media_inline_audio_last_second
    ) {
        return;
    }

    media_inline_audio_last_second =
        current_second;

    for (
        int i = 0;
        i < (int)documents.size();
        i++
    ) {
        if (
            !documents[i].filename ||
            _wcsicmp(
                documents[i].filename,
                media_inline_audio_path
            ) != 0 ||
            documents[i].max <=
                documents[i].min
        ) {
            continue;
        }

        LONG count =
            documents[i].max -
            documents[i].min;

        if (count < 10 || count > 2048)
            continue;

        wchar_t* text =
            (wchar_t*)calloc(
                count + 2,
                sizeof(wchar_t)
            );

        if (!text)
            return;

        TEXTRANGE range = {0};
        range.chrg.cpMin = documents[i].min;
        range.chrg.cpMax = documents[i].max;
        range.lpstrText = text;

        SendMessageW(
            chat,
            EM_GETTEXTRANGE,
            0,
            (LPARAM)&range
        );

        wchar_t* newline =
            wcschr(text, L'\n');

        CHARRANGE saved = {0};
        SendMessageW(
            chat,
            EM_EXGETSEL,
            0,
            (LPARAM)&saved
        );

        bool playing =
            state ==
            MFP_MEDIAPLAYER_STATE_PLAYING;

        SendMessageW(
            chat,
            EM_SETSEL,
            documents[i].min,
            documents[i].min + 4
        );

        SendMessageW(
            chat,
            EM_REPLACESEL,
            FALSE,
            (LPARAM)(
                playing
                    ? L"[II]"
                    : L"[>] "
            )
        );

        if (newline) {
            int newline_offset =
                (int)(newline - text);

            const int cells = 20;
            int filled = 0;

            if (duration > 0) {
                filled =
                    (int)(
                        position * cells /
                        duration
                    );
            }

            if (filled < 0)
                filled = 0;
            if (filled > cells)
                filled = cells;

            wchar_t progress[64] = {0};
            wchar_t bar[cells + 1];

            for (int k = 0; k < cells; k++) {
                bar[k] =
                    k < filled
                        ? L'='
                        : L'-';
            }
            bar[cells] = 0;

            int hours = current_second / 3600;
            int minutes = (current_second / 60) % 60;
            int seconds = current_second % 60;

            _snwprintf(
                progress,
                ARRAYSIZE(progress) - 1,
                L"\n    [%s] %02d:%02d:%02d",
                bar,
                hours,
                minutes,
                seconds
            );
            progress[ARRAYSIZE(progress) - 1] = 0;

            SendMessageW(
                chat,
                EM_SETSEL,
                documents[i].min + newline_offset,
                documents[i].max
            );

            SendMessageW(
                chat,
                EM_REPLACESEL,
                FALSE,
                (LPARAM)progress
            );
        }

        CHARFORMAT2 cf;
        memset(
            &cf,
            0,
            sizeof(cf)
        );
        cf.cbSize = sizeof(cf);
        cf.dwMask =
            CFM_LINK |
            CFM_COLOR |
            CFM_UNDERLINE;
        cf.dwEffects =
            CFE_LINK |
            CFE_UNDERLINE;
        cf.crTextColor = RGB(0, 128, 128);

        SendMessageW(
            chat,
            EM_SETSEL,
            documents[i].min,
            documents[i].max
        );
        SendMessageW(
            chat,
            EM_SETCHARFORMAT,
            SCF_SELECTION,
            (LPARAM)&cf
        );

        SendMessageW(
            chat,
            EM_EXSETSEL,
            0,
            (LPARAM)&saved
        );

        free(text);
        break;
    }
}

static VOID CALLBACK media_inline_audio_timer_proc(
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

    media_inline_audio_apply_visual(false);

    if (
        state != MFP_MEDIAPLAYER_STATE_PLAYING &&
        state != MFP_MEDIAPLAYER_STATE_PAUSED
    ) {
        media_inline_audio_apply_visual(true);

        if (media_inline_audio_timer) {
            KillTimer(NULL, media_inline_audio_timer);
            media_inline_audio_timer = 0;
        }
    }
}

static void media_inline_audio_start_timer() {
    if (!media_inline_audio_timer) {
        media_inline_audio_timer =
            SetTimer(
                NULL,
                0,
                500,
                media_inline_audio_timer_proc
            );
    }

    media_inline_audio_apply_visual(true);
}

'''

    s = s[:insert_at] + helpers_v3 + s[insert_at:]

    # The v2 audio functions are textually before the v3 visual/timer helper
    # definitions. Add forward declarations before replacing those functions.
    audio_release_pos = s.find("static void media_inline_audio_release()")
    if audio_release_pos < 0:
        raise SystemExit("Could not locate media_inline_audio_release() for v3 forward declarations.")

    audio_forward_decls = (
        "static void media_inline_audio_apply_visual(bool force);\n"
        "static void media_inline_audio_start_timer();\n\n"
    )

    if "static void media_inline_audio_apply_visual(bool force);" not in s[:audio_release_pos]:
        s = (
            s[:audio_release_pos]
            + audio_forward_decls
            + s[audio_release_pos:]
        )

    # Replace v2 audio release/toggle so the visual state is updated as well.
    release_audio_v3 = r'''static void media_inline_audio_release() {
    if (media_inline_audio) {
        media_inline_audio_apply_visual(true);
        media_inline_audio->Stop();
        media_inline_audio_apply_visual(true);
        media_inline_audio->Shutdown();
        media_inline_audio->Release();
        media_inline_audio = NULL;
    }

    if (media_inline_audio_timer) {
        KillTimer(NULL, media_inline_audio_timer);
        media_inline_audio_timer = 0;
    }

    media_inline_audio_path[0] = 0;
    media_inline_audio_last_second = -1;
}'''
    s = replace_function(s, "static void media_inline_audio_release()", release_audio_v3)

    toggle_audio_v3 = r'''bool media_inline_audio_toggle(
    const wchar_t* path
) {
    if (!media_player_is_music_path(path))
        return false;

    if (
        media_inline_audio &&
        media_inline_audio_path[0] &&
        _wcsicmp(media_inline_audio_path, path) == 0
    ) {
        MFP_MEDIAPLAYER_STATE state =
            MFP_MEDIAPLAYER_STATE_EMPTY;

        if (SUCCEEDED(media_inline_audio->GetState(&state))) {
            HRESULT hr = S_OK;

            if (state == MFP_MEDIAPLAYER_STATE_PLAYING) {
                hr = media_inline_audio->Pause();
            } else {
                hr = media_inline_audio->Play();
            }

            diag_log(
                "inline audio toggle state=%d hr=0x%08X path=%ls",
                (int)state,
                (unsigned int)hr,
                path
            );

            media_inline_audio_start_timer();
            return SUCCEEDED(hr);
        }
    }

    media_inline_audio_release();
    CoInitialize(NULL);

    HRESULT hr =
        media_mf_create_player(
            path,
            NULL,
            &media_inline_audio
        );

    if (SUCCEEDED(hr) && media_inline_audio) {
        media_inline_audio->SetVolume(0.85f);
        hr = media_inline_audio->Play();
    }

    diag_log(
        "inline audio open hr=0x%08X path=%ls",
        (unsigned int)hr,
        path
    );

    if (FAILED(hr) || !media_inline_audio) {
        media_inline_audio_release();
        return false;
    }

    wcsncpy(
        media_inline_audio_path,
        path,
        ARRAYSIZE(media_inline_audio_path) - 1
    );
    media_inline_audio_path[
        ARRAYSIZE(media_inline_audio_path) - 1
    ] = 0;

    media_inline_audio_last_second = -1;
    media_inline_audio_start_timer();

    return true;
}'''
    s = replace_function(s, "bool media_inline_audio_toggle(", toggle_audio_v3)

    # -------------------------------------------------------------------------
    # Atomic page commit and video-thumbnail queue.
    # -------------------------------------------------------------------------

    finish_av_old_sig = "void media_archive_finish_av_page()"
    finish_pos = s.find(finish_av_old_sig)
    if finish_pos < 0:
        raise SystemExit("Could not locate media_archive_finish_av_page().")

    commit_helper = r'''
static void media_archive_commit_ready_page() {
    int total_pages =
        media_archive_total_pages();

    if (
        total_pages > 0 &&
        (int)media_archive_loaded_pages.size() <
            total_pages
    ) {
        media_archive_loaded_pages.resize(
            total_pages,
            0
        );
    }

    if (
        media_archive_request_page >= 0 &&
        media_archive_request_page <
            (int)media_archive_loaded_pages.size()
    ) {
        media_archive_loaded_pages[
            media_archive_request_page
        ] = 1;
    }

    media_archive_previous_page =
        media_archive_current_page;

    media_archive_current_page =
        media_archive_request_page;

    media_archive_page_loading = false;

    media_archive_refresh();
    media_archive_update_nav();

    diag_log(
        "media atomic commit kind=%d page=%d items=%d",
        media_archive_kind,
        media_archive_current_page,
        (int)media_archive_items.size()
    );
}

'''

    s = s[:finish_pos] + commit_helper + s[finish_pos:]

    finish_av_v3 = r'''void media_archive_finish_av_page() {
    if (
        media_archive_kind == 1 &&
        !media_archive_server_queue_empty()
    ) {
        media_archive_start_next_download();
        return;
    }

    media_archive_commit_ready_page();
}'''
    s = replace_function(s, "void media_archive_finish_av_page()", finish_av_v3)

    navigate_v3 = r'''static bool media_archive_navigate_to_page(
    int page_index
) {
    int total_pages =
        media_archive_total_pages();

    if (
        page_index < 0 ||
        total_pages <= 0 ||
        page_index >= total_pages
    ) {
        MessageBeep(MB_ICONASTERISK);
        media_archive_update_nav();
        return false;
    }

    if (
        media_archive_search_pending ||
        media_archive_page_loading
    ) {
        return false;
    }

    if (page_index == media_archive_current_page) {
        media_archive_update_nav();
        return true;
    }

    if (media_archive_page_is_loaded(page_index)) {
        media_archive_previous_page =
            media_archive_current_page;
        media_archive_current_page =
            page_index;
        media_archive_request_page =
            page_index;
        media_archive_refresh();
        return true;
    }

    media_archive_previous_page =
        media_archive_current_page;
    media_archive_request_page =
        page_index;

    // Do NOT change current_page and do NOT clear/repaint the ListView here.
    // The old page remains visible until the new page is fully ready.
    int add_offset = page_index * 20;

    if (!media_archive_request_server_page_ex(0, add_offset)) {
        media_archive_request_page =
            media_archive_current_page;
        media_archive_page_loading = false;
        media_archive_update_nav();
        return false;
    }

    return true;
}'''
    s = replace_function(s, "static bool media_archive_navigate_to_page(", navigate_v3)

    finish_server_v3 = r'''void media_archive_finish_server_page(
    int last_id,
    int count,
    int total
) {
    if (total > 0)
        media_archive_total = total;

    int total_pages =
        media_archive_total_pages();

    if (
        total_pages > 0 &&
        (int)media_archive_loaded_pages.size() <
            total_pages
    ) {
        media_archive_loaded_pages.resize(
            total_pages,
            0
        );
    }

    media_archive_loaded_count += count;

    if (last_id > 0)
        media_archive_next_offset_id = last_id;

    media_archive_no_more =
        count < 20 ||
        (
            total_pages > 0 &&
            media_archive_request_page + 1 >=
                total_pages
        );

    if (count <= 0) {
        media_archive_page_loading = false;
        media_archive_request_page =
            media_archive_current_page;
        MessageBeep(MB_ICONASTERISK);
    }

    media_archive_update_nav();

    diag_log(
        "media metadata ready kind=%d request=%d visible=%d count=%d total=%d",
        media_archive_kind,
        media_archive_request_page,
        media_archive_current_page,
        count,
        media_archive_total
    );
}'''
    s = replace_function(s, "void media_archive_finish_server_page(", finish_server_v3)

    start_download_v3 = r'''void media_archive_start_next_download() {
    if (!media_archive_server_active)
        return;

    for (
        int i = (int)documents.size() - 1;
        i >= 0;
        i--
    ) {
        if (
            documents[i].visible ||
            documents[i].photo_size <= 1
        ) {
            continue;
        }

        if (!read_le(documents[i].photo_msg_id, 8)) {
            if (documents[i].photo_size == 3) {
                media_archive_request_video_thumbnail(
                    &documents[i],
                    &dcInfoMain
                );
            } else {
                get_photo(
                    NULL,
                    &documents[i],
                    &dcInfoMain
                );
            }

            diag_log(
                "media preview start kind=%d page=%d index=%d msg=%d sentinel=%d",
                media_archive_kind,
                media_archive_request_page,
                i,
                documents[i].min < 0
                    ? -documents[i].min
                    : 0,
                documents[i].photo_size
            );

            return;
        }
    }

    media_archive_commit_ready_page();
}'''
    s = replace_function(s, "void media_archive_start_next_download()", start_download_v3)

    # -------------------------------------------------------------------------
    # A/V item metadata + video preview queue.
    # -------------------------------------------------------------------------

    add_av_v3 = r'''void media_archive_add_av_document(
    Document* document,
    int message_id,
    int kind,
    const wchar_t* display_name,
    int duration
) {
    if (
        !document ||
        message_id <= 0 ||
        (kind != 1 && kind != 2)
    ) {
        return;
    }

    __int64 document_id = 0;
    memcpy(&document_id, document->id, 8);

    for (
        int i = 0;
        i < (int)media_archive_items.size();
        i++
    ) {
        if (
            media_archive_items[i].document_id == document_id &&
            media_archive_items[i].media_kind == kind
        ) {
            return;
        }
    }

    MediaArchiveItem item = {0};
    item.document_id = document_id;
    item.message_id = message_id;
    item.page_index = media_archive_request_page;
    item.media_kind = kind;
    item.duration = duration;
    item.has_document = true;
    item.full_file_ready = false;

    item.av_document = *document;
    item.av_document.filename =
        document->filename
            ? _wcsdup(document->filename)
            : NULL;

    int file_ref_len =
        document->file_reference
            ? tlstr_len(document->file_reference, true)
            : 0;

    item.av_document.file_reference = NULL;

    if (file_ref_len > 0) {
        item.av_document.file_reference =
            (BYTE*)malloc(file_ref_len);

        if (item.av_document.file_reference) {
            memcpy(
                item.av_document.file_reference,
                document->file_reference,
                file_ref_len
            );
        }
    }

    if (display_name && display_name[0]) {
        wcsncpy(
            item.display_name,
            display_name,
            ARRAYSIZE(item.display_name) - 1
        );
    } else if (document->filename) {
        wcsncpy(
            item.display_name,
            document->filename,
            ARRAYSIZE(item.display_name) - 1
        );
    }

    item.display_name[
        ARRAYSIZE(item.display_name) - 1
    ] = 0;

    media_archive_items.push_back(item);

    // Telegram Document thumbnails are fetched independently from the full
    // video file. photo_size==3 means JPEG document preview.
    if (
        kind == 1 &&
        document->photo_size == 3 &&
        document->file_reference &&
        file_ref_len > 0
    ) {
        Document thumb = {0};
        thumb = *document;
        thumb.visible = false;
        thumb.min = -message_id;
        thumb.max = -message_id;
        thumb.photo_size = 3;
        memset(thumb.photo_msg_id, 0, 8);

        thumb.filename =
            document->filename
                ? _wcsdup(document->filename)
                : NULL;

        thumb.file_reference =
            (BYTE*)malloc(file_ref_len);

        if (thumb.file_reference) {
            memcpy(
                thumb.file_reference,
                document->file_reference,
                file_ref_len
            );
            documents.push_front(thumb);
        } else {
            free(thumb.filename);
        }
    }
}'''
    s = replace_function(s, "void media_archive_add_av_document(", add_av_v3)

    # -------------------------------------------------------------------------
    # Images/video previews: retain full Photo location, attach document thumbs,
    # and never repaint once per thumbnail.
    # -------------------------------------------------------------------------

    add_document_v3 = r'''void media_archive_add_document(
    Document* document,
    HBITMAP bitmap
) {
    if (
        !document ||
        !bitmap ||
        document->photo_size == 1
    ) {
        return;
    }

    __int64 document_id = 0;
    memcpy(
        &document_id,
        document->id,
        sizeof(document_id)
    );

    // photo_size == 3 is a video Document thumbnail. It is useful both in the
    // chat and the Video tab, but must never become an Images-tab entry.
    if (document->photo_size == 3) {
        for (
            int i = 0;
            i < (int)media_archive_items.size();
            i++
        ) {
            if (
                media_archive_items[i].media_kind == 1 &&
                media_archive_items[i].document_id == document_id &&
                media_archive_items[i].page_index ==
                    media_archive_request_page
            ) {
                if (!media_archive_items[i].bitmap) {
                    media_archive_items[i].bitmap =
                        (HBITMAP)CopyImage(
                            bitmap,
                            IMAGE_BITMAP,
                            0,
                            0,
                            LR_CREATEDIBSECTION
                        );
                }
                break;
            }
        }

        if (
            !document->visible &&
            media_archive_server_active &&
            media_archive_server_queue_empty()
        ) {
            media_archive_commit_ready_page();
        }

        return;
    }

    if (
        media_archive_server_active &&
        document->visible
    ) {
        return;
    }

    if (
        !media_archive_server_active &&
        !document->visible
    ) {
        return;
    }

    for (
        int i = 0;
        i < (int)media_archive_items.size();
        i++
    ) {
        if (
            media_archive_items[i].media_kind == 0 &&
            media_archive_items[i].document_id == document_id
        ) {
            return;
        }
    }

    int message_id = 0;

    if (!document->visible && document->min < 0)
        message_id = -document->min;

    if (document->visible) {
        for (
            int i = 0;
            i < (int)messages.size();
            i++
        ) {
            if (
                document->min >= messages[i].start_char &&
                document->max <= messages[i].end_footer
            ) {
                message_id = messages[i].id;
                break;
            }
        }
    }

    HBITMAP copy =
        (HBITMAP)CopyImage(
            bitmap,
            IMAGE_BITMAP,
            0,
            0,
            LR_CREATEDIBSECTION
        );

    if (!copy)
        return;

    MediaArchiveItem item = {0};
    item.document_id = document_id;
    item.media_kind = 0;
    item.message_id = message_id;
    item.page_index =
        media_archive_server_active
            ? media_archive_request_page
            : 0;
    item.bitmap = copy;
    item.file_path[0] = 0;
    item.has_document = true;
    item.full_file_ready = false;

    item.av_document = *document;
    item.av_document.filename =
        document->filename
            ? _wcsdup(document->filename)
            : NULL;

    int file_ref_len =
        document->file_reference
            ? tlstr_len(document->file_reference, true)
            : 0;

    item.av_document.file_reference = NULL;

    if (file_ref_len > 0) {
        item.av_document.file_reference =
            (BYTE*)malloc(file_ref_len);

        if (item.av_document.file_reference) {
            memcpy(
                item.av_document.file_reference,
                document->file_reference,
                file_ref_len
            );
        }
    }

    media_archive_items.push_back(item);

    if (
        media_archive_server_active &&
        media_archive_server_queue_empty()
    ) {
        media_archive_commit_ready_page();
    } else {
        media_archive_update_nav();
    }
}'''
    s = replace_function(s, "void media_archive_add_document(", add_document_v3)

    # -------------------------------------------------------------------------
    # Classic video cards + music list. Avoid FRAMECHANGED when the view mode
    # didn't actually change; this was another source of flashing.
    # -------------------------------------------------------------------------

    refresh_pos = s.find("static void media_archive_refresh() {")
    if refresh_pos < 0:
        raise SystemExit("Could not locate Media refresh function.")

    video_thumb_helper = r'''
static HBITMAP media_archive_make_video_thumbnail(
    HBITMAP source
) {
    HBITMAP result =
        source
            ? media_archive_make_thumbnail(source, 96)
            : NULL;

    if (!result) {
        HDC screen = GetDC(NULL);
        if (!screen)
            return NULL;

        result = CreateCompatibleBitmap(screen, 96, 96);
        ReleaseDC(NULL, screen);

        if (!result)
            return NULL;

        HDC dc = CreateCompatibleDC(NULL);
        HGDIOBJ old = SelectObject(dc, result);
        RECT all = {0, 0, 96, 96};
        FillRect(dc, &all, GetSysColorBrush(COLOR_3DFACE));
        DrawEdge(dc, &all, EDGE_SUNKEN, BF_RECT);
        SelectObject(dc, old);
        DeleteDC(dc);
    }

    HDC dc = CreateCompatibleDC(NULL);
    if (!dc)
        return result;

    HGDIOBJ old_bitmap = SelectObject(dc, result);

    RECT button = {34, 34, 62, 62};
    FillRect(dc, &button, GetSysColorBrush(COLOR_BTNFACE));
    DrawEdge(dc, &button, EDGE_RAISED, BF_RECT);

    POINT tri[3] = {
        {43, 41},
        {56, 48},
        {43, 55}
    };

    HBRUSH brush = CreateSolidBrush(GetSysColor(COLOR_BTNTEXT));
    HGDIOBJ old_brush = SelectObject(dc, brush);
    Polygon(dc, tri, 3);
    SelectObject(dc, old_brush);
    DeleteObject(brush);

    SelectObject(dc, old_bitmap);
    DeleteDC(dc);

    return result;
}

'''

    s = s[:refresh_pos] + video_thumb_helper + s[refresh_pos:]

    refresh_v3 = r'''static void media_archive_refresh() {
    if (!hMediaArchiveList)
        return;

    SendMessageW(
        hMediaArchiveList,
        WM_SETREDRAW,
        FALSE,
        0
    );

    bool icon_grid =
        media_archive_kind == 0 ||
        media_archive_kind == 1;

    LONG_PTR old_style =
        GetWindowLongPtrW(
            hMediaArchiveList,
            GWL_STYLE
        );

    LONG_PTR desired_type =
        icon_grid
            ? LVS_ICON
            : LVS_LIST;

    if ((old_style & LVS_TYPEMASK) != desired_type) {
        LONG_PTR new_style =
            (old_style & ~LVS_TYPEMASK) |
            desired_type;

        SetWindowLongPtrW(
            hMediaArchiveList,
            GWL_STYLE,
            new_style
        );
    }

    ListView_DeleteAllItems(
        hMediaArchiveList
    );

    HIMAGELIST old_images =
        hMediaArchiveImages;

    hMediaArchiveImages = NULL;

    if (icon_grid) {
        hMediaArchiveImages =
            ImageList_Create(
                96,
                96,
                ILC_COLOR32,
                20,
                16
            );

        if (hMediaArchiveImages) {
            ListView_SetImageList(
                hMediaArchiveList,
                hMediaArchiveImages,
                LVSIL_NORMAL
            );

            SendMessageW(
                hMediaArchiveList,
                LVM_SETICONSPACING,
                0,
                MAKELPARAM(116, 120)
            );
        }
    } else {
        ListView_SetImageList(
            hMediaArchiveList,
            NULL,
            LVSIL_NORMAL
        );
    }

    if (old_images)
        ImageList_Destroy(old_images);

    for (
        int i = 0;
        i < (int)media_archive_items.size();
        i++
    ) {
        MediaArchiveItem* archive_item =
            &media_archive_items[i];

        if (
            archive_item->media_kind != media_archive_kind ||
            archive_item->page_index != media_archive_current_page
        ) {
            continue;
        }

        LVITEMW item = {0};
        item.iItem =
            ListView_GetItemCount(
                hMediaArchiveList
            );
        item.lParam = i;

        wchar_t label[340] = {0};

        if (icon_grid) {
            HBITMAP thumb =
                media_archive_kind == 1
                    ? media_archive_make_video_thumbnail(
                        archive_item->bitmap
                    )
                    : media_archive_make_thumbnail(
                        archive_item->bitmap,
                        96
                    );

            if (!thumb || !hMediaArchiveImages) {
                if (thumb)
                    DeleteObject(thumb);
                continue;
            }

            int image_index =
                ImageList_Add(
                    hMediaArchiveImages,
                    thumb,
                    NULL
                );

            DeleteObject(thumb);

            if (image_index < 0)
                continue;

            if (media_archive_kind == 1) {
                if (archive_item->duration > 0) {
                    _snwprintf(
                        label,
                        ARRAYSIZE(label) - 1,
                        L"%02d:%02d",
                        archive_item->duration / 60,
                        archive_item->duration % 60
                    );
                } else {
                    wcscpy(label, L"Video");
                }
            } else if (archive_item->message_id > 0) {
                _snwprintf(
                    label,
                    ARRAYSIZE(label) - 1,
                    L"#%d",
                    archive_item->message_id
                );
            }

            item.mask =
                LVIF_IMAGE |
                LVIF_PARAM |
                LVIF_TEXT;
            item.iImage = image_index;
        } else {
            if (archive_item->duration > 0) {
                _snwprintf(
                    label,
                    ARRAYSIZE(label) - 1,
                    L"[>]  %s    %02d:%02d",
                    archive_item->display_name,
                    archive_item->duration / 60,
                    archive_item->duration % 60
                );
            } else {
                _snwprintf(
                    label,
                    ARRAYSIZE(label) - 1,
                    L"[>]  %s",
                    archive_item->display_name
                );
            }

            item.mask =
                LVIF_PARAM |
                LVIF_TEXT;
        }

        label[ARRAYSIZE(label) - 1] = 0;
        item.pszText = label;

        SendMessageW(
            hMediaArchiveList,
            LVM_INSERTITEMW,
            0,
            (LPARAM)&item
        );
    }

    media_archive_update_nav();

    SendMessageW(
        hMediaArchiveList,
        WM_SETREDRAW,
        TRUE,
        0
    );

    RedrawWindow(
        hMediaArchiveList,
        NULL,
        NULL,
        RDW_INVALIDATE |
        RDW_UPDATENOW |
        RDW_ALLCHILDREN
    );
}'''
    s = replace_function(s, "static void media_archive_refresh() {", refresh_v3)

    # Double-click image -> fetch the actual largest Telegram Photo size.
    open_item_v3 = r'''static void media_archive_open_item(
    int item_index
) {
    if (
        item_index < 0 ||
        item_index >=
            (int)media_archive_items.size()
    ) {
        return;
    }

    MediaArchiveItem* item =
        &media_archive_items[item_index];

    if (item->media_kind == 0) {
        if (!media_archive_begin_full_photo_download(item_index))
            MessageBeep(MB_ICONASTERISK);
        return;
    }

    media_archive_begin_av_download(
        item_index
    );
}'''
    s = replace_function(s, "static void media_archive_open_item(", open_item_v3)

    # Reopening an already-open Media window should not rebuild the current
    # ListView merely to bring the window forward.
    show_start, show_end = function_range(s, "void media_archive_show()")
    show_func = s[show_start:show_end]

    existing_refresh = r'''        media_archive_refresh();

        ShowWindow(
            hMediaArchiveWindow,
            SW_SHOW
        );'''

    if existing_refresh in show_func:
        show_func = show_func.replace(
            existing_refresh,
            r'''        ShowWindow(
            hMediaArchiveWindow,
            SW_SHOW
        );''',
            1,
        )

    s = s[:show_start] + show_func + s[show_end:]

write(t, s)


# -----------------------------------------------------------------------------
# response.cpp
# -----------------------------------------------------------------------------

s = read(r)

if "media_tabs_av_response_v3" not in s:
    # Document has a normal JPEG thumbnail vector. Sentinel 3 tells get_photo()
    # to use inputDocumentFileLocation while retaining JPEG decoding.
    parser_start, parser_end = function_range(
        s,
        "static bool media_tabs_extract_document("
    )
    parser = s[parser_start:parser_end]

    old_variants = [
        "    document->photo_size =\n        (kind == 1 && (doc_flags & (1 << 0))) ? 2 : 0;",
        "    document->photo_size =\n        (kind == 1 && (doc_flags & (1 << 0)))\n            ? 2\n            : 0;",
    ]

    replaced_sentinel = False
    for old in old_variants:
        if old in parser:
            parser = parser.replace(
                old,
                "    document->photo_size =\n        (kind == 1 && (doc_flags & (1 << 0))) ? 3 : 0;",
                1,
            )
            replaced_sentinel = True
            break

    if not replaced_sentinel and "? 3 : 0;" not in parser:
        raise SystemExit("Could not locate A/V thumbnail sentinel assignment.")

    s = s[:parser_start] + parser + s[parser_end:]

    # Both Images and Video need their preview queues drained before the page
    # is atomically committed. Music has no preview queue.
    handler_start, handler_end = function_range(
        s,
        "static void media_archive_handle_server_response("
    )
    handler = s[handler_start:handler_end]

    old_tail = r'''    if (
        media_archive_kind == 0 &&
        added_count > 0
    ) {
        media_archive_start_next_download();
    } else {
        media_archive_finish_av_page();
    }'''

    new_tail = r'''    if (
        (
            media_archive_kind == 0 ||
            media_archive_kind == 1
        ) &&
        added_count > 0
    ) {
        media_archive_start_next_download();
    } else {
        media_archive_finish_av_page();
    }'''

    if old_tail not in handler:
        raise SystemExit("Could not locate Media response preview-dispatch tail.")

    handler = handler.replace(old_tail, new_tail, 1)
    s = s[:handler_start] + handler + s[handler_end:]

    # Full-size Photo requests have their own rpc id and must be consumed before
    # the ordinary downloading_docs / thumbnail routing.
    upload_case = s.find("case 0x96a18d5: { // upload.file")
    if upload_case < 0:
        raise SystemExit("Could not locate upload.file case.")

    diag_text = "\"upload.file state downloads=%d documents=%d custom_emoji=%d\""
    diag_pos = s.find(diag_text, upload_case)
    if diag_pos < 0:
        raise SystemExit("Could not locate upload.file diagnostic string.")

    insert_pos = s.find(");", diag_pos)
    if insert_pos < 0:
        raise SystemExit("Could not locate upload.file diagnostic close.")
    insert_pos += 2

    upload_insertion = r'''

        // media_tabs_av_response_v3
        if (
            media_archive_handle_full_photo_upload(
                last_rpcresult_msgid,
                unenc_response,
                length
            )
        ) {
            break;
        }'''

    s = s[:insert_pos] + upload_insertion + s[insert_pos:]

write(r, s)


# -----------------------------------------------------------------------------
# message.cpp: visible two-line inline audio player + video preview in chat.
# -----------------------------------------------------------------------------

s = read(m)

if "media_inline_player_v3" not in s:
    # Helper draws a classic 160x90 placeholder until Telegram's real video
    # document thumbnail arrives and replace_in_chat() swaps it in.
    handler_pos = s.find("int message_handler(")
    if handler_pos < 0:
        raise SystemExit("Could not locate message_handler().")

    message_helper = r'''
// media_inline_player_v3
static HBITMAP media_chat_video_placeholder() {
    HDC screen = GetDC(NULL);
    if (!screen)
        return NULL;

    HBITMAP bitmap =
        CreateCompatibleBitmap(
            screen,
            160,
            90
        );

    ReleaseDC(NULL, screen);

    if (!bitmap)
        return NULL;

    HDC dc = CreateCompatibleDC(NULL);
    HGDIOBJ old_bitmap = SelectObject(dc, bitmap);

    RECT all = {0, 0, 160, 90};
    FillRect(dc, &all, GetSysColorBrush(COLOR_3DFACE));
    DrawEdge(dc, &all, EDGE_SUNKEN, BF_RECT);

    RECT button = {64, 28, 96, 60};
    FillRect(dc, &button, GetSysColorBrush(COLOR_BTNFACE));
    DrawEdge(dc, &button, EDGE_RAISED, BF_RECT);

    POINT tri[3] = {
        {75, 36},
        {88, 44},
        {75, 52}
    };

    HBRUSH brush = CreateSolidBrush(GetSysColor(COLOR_BTNTEXT));
    HGDIOBJ old_brush = SelectObject(dc, brush);
    Polygon(dc, tri, 3);
    SelectObject(dc, old_brush);
    DeleteObject(brush);

    SelectObject(dc, old_bitmap);
    DeleteDC(dc);

    return bitmap;
}

'''

    s = s[:handler_pos] + message_helper + s[handler_pos:]

    # Track whether this document is a normal video and has Telegram thumbs.
    flags_old = "\t\tbool voice = false, gif = false, round = false, sticker = false, music = false; // media_inline_music_row_v2"
    flags_new = "\t\tbool voice = false, gif = false, round = false, sticker = false, music = false, video = false, video_has_thumb = false; // media_inline_music_row_v2"

    if flags_old not in s:
        raise SystemExit("Could not locate document media flags in message.cpp.")
    s = s.replace(flags_old, flags_new, 1)

    outer_old = "\tbool added_doc = false, added_photo = false;\n"
    outer_new = outer_old + "\tDocument video_thumb_document = {0};\n\tbool added_video_thumb = false;\n"
    if outer_old not in s:
        raise SystemExit("Could not locate outer message document flags.")
    s = s.replace(outer_old, outer_new, 1)

    doc_flags_old = "\t\t\tint doc_flags = read_le(doc + offset, 4);\n\t\t\toffset += 4;"
    doc_flags_new = "\t\t\tint doc_flags = read_le(doc + offset, 4);\n\t\t\tvideo_has_thumb = (doc_flags & (1 << 0)) ? true : false;\n\t\t\toffset += 4;"

    if doc_flags_old not in s:
        raise SystemExit("Could not locate document flags parsing.")
    s = s.replace(doc_flags_old, doc_flags_new, 1)

    video_attr_old = "\t\t\t\t\telse {\n\t\t\t\t\t\tdouble duration_double;"
    video_attr_new = "\t\t\t\t\telse {\n\t\t\t\t\t\tvideo = true;\n\t\t\t\t\t\tdouble duration_double;"

    if video_attr_old not in s:
        raise SystemExit("Could not locate video attribute parsing.")
    s = s.replace(video_attr_old, video_attr_new, 1)

    # Replace the simple music row with an unmistakable in-chat player. The
    # second line has fixed length, so the timer can update it without shifting
    # any subsequent message positions.
    row_old = '''\t\t\tdocument.min = cr_startmsg.cpMin + written;\n\t\t\tif (music) written += riched_write(chat, L"[>] " );\n\t\t\twritten += riched_write(chat, document.filename);\n\t\t\tif (duration_str[0] == ' ') written += riched_write(chat, &duration_str[0]);\n\t\t\twritten += riched_write(chat, &size_str[0]);\n\t\t\tdocument.max = cr_startmsg.cpMin + written;'''

    row_new = r'''			document.min = cr_startmsg.cpMin + written;

			if (video && video_has_thumb && !same_photo) {
				video_thumb_document = document;
				video_thumb_document.filename = document.filename ? _wcsdup(document.filename) : NULL;

				int thumb_ref_len =
					document.file_reference
						? tlstr_len(document.file_reference, true)
						: 0;

				video_thumb_document.file_reference = NULL;

				if (thumb_ref_len > 0) {
					video_thumb_document.file_reference = (BYTE*)malloc(thumb_ref_len);
					if (video_thumb_document.file_reference) {
						memcpy(video_thumb_document.file_reference, document.file_reference, thumb_ref_len);
					}
				}

				video_thumb_document.photo_size = 3;
				video_thumb_document.visible = true;
				memset(video_thumb_document.photo_msg_id, 0, 8);
				video_thumb_document.min = cr_startmsg.cpMin + written;

				HBITMAP placeholder = media_chat_video_placeholder();
				if (placeholder) {
					insert_image(chat, NULL, placeholder);
					DeleteObject(placeholder);
					written++;
				}

				video_thumb_document.max = cr_startmsg.cpMin + written;

				if (
					video_thumb_document.file_reference &&
					video_thumb_document.max > video_thumb_document.min
				) {
					added_video_thumb = true;
				} else {
					free(video_thumb_document.filename);
					free(video_thumb_document.file_reference);
					memset(&video_thumb_document, 0, sizeof(video_thumb_document));
				}

				written += riched_write(chat, L"\n");
				document.min = cr_startmsg.cpMin + written;
			}

			if (music)
				written += riched_write(chat, L"[>] " );

			written += riched_write(chat, document.filename);

			if (duration_str[0] == ' ')
				written += riched_write(chat, &duration_str[0]);

			written += riched_write(chat, &size_str[0]);

			if (music) {
				written += riched_write(
					chat,
					L"\n    [--------------------] 00:00:00"
				);
			}

			document.max = cr_startmsg.cpMin + written;'''

    if row_old not in s:
        raise SystemExit("Could not locate v2 document row rendering block.")
    s = s.replace(row_old, row_new, 1)

    adjust_old = "\t\tif (added_doc) {\n\t\t\tdocument.min -= deleted_wchars;\n\t\t\tdocument.max -= deleted_wchars;\n\t\t}\n"
    adjust_new = adjust_old + "\t\tif (added_video_thumb) {\n\t\t\tvideo_thumb_document.min -= deleted_wchars;\n\t\t\tvideo_thumb_document.max -= deleted_wchars;\n\t\t}\n"

    if adjust_old not in s:
        raise SystemExit("Could not locate document emoji-position adjustment.")
    s = s.replace(adjust_old, adjust_new, 1)

    final_push_old = "\t\tif (added_doc) {\n\t\t\tif (to_front) documents.push_front(document);\n\t\t\telse documents.push_back(document);\n\t\t}\n"
    final_push_new = final_push_old + "\t\tif (added_video_thumb) {\n\t\t\tif (to_front) documents.push_front(video_thumb_document);\n\t\t\telse documents.push_back(video_thumb_document);\n\n\t\t\tif (!to_front && IMAGELOADPOLICY == 2) {\n\t\t\t\tfor (int k = (int)documents.size() - 1; k >= 0; k--) {\n\t\t\t\t\tif (documents[k].photo_size == 3 && memcmp(documents[k].id, video_thumb_document.id, 8) == 0 && !read_le(documents[k].photo_msg_id, 8)) {\n\t\t\t\t\t\tmedia_archive_request_video_thumbnail(&documents[k], &dcInfoMain);\n\t\t\t\t\t\tbreak;\n\t\t\t\t\t}\n\t\t\t\t}\n\t\t\t}\n\t\t}\n"

    if final_push_old not in s:
        raise SystemExit("Could not locate final document push block.")
    s = s.replace(final_push_old, final_push_new, 1)

write(m, s)


# -----------------------------------------------------------------------------
# Final v3 validation
# -----------------------------------------------------------------------------

checks_v3 = {
    h: [
        "media_tabs_av_v3",
        "media_archive_handle_full_photo_upload",
        "media_archive_request_video_thumbnail",
    ],
    g: [
        "document->photo_size == 3",
    ],
    t: [
        "media_tabs_av_runtime_v3",
        "media_archive_commit_ready_page",
        "media_archive_make_video_thumbnail",
        "media_archive_begin_full_photo_download",
        "media full photo complete",
        "media_inline_audio_apply_visual",
        "media_inline_audio_timer_proc",
        "old page remains visible",
    ],
    r: [
        "media_tabs_av_response_v3",
        "? 3",
        "media_archive_kind == 1",
    ],
    m: [
        "media_inline_player_v3",
        "media_chat_video_placeholder",
        "[--------------------] 00:00:00",
        "video_thumb_document.photo_size = 3",
    ],
}

for p, tokens in checks_v3.items():
    text = read(p)
    for token in tokens:
        if token not in text:
            raise SystemExit(
                f"Media v3 verification failed in {p.name}: {token}"
            )

print(
    "Applied Media A/V v3: atomic no-flicker page swaps, full-size photo open, "
    "video previews in Media/chat, and visible inline audio player with progress."
)
