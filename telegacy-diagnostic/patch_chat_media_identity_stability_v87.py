#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_chat_media_identity_stability_v87.py <Telegacy source directory>")

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
if "chat_media_identity_stability_v87" in s:
    print("Chat media identity/sticker stability v8.7 already applied.")
    raise SystemExit(0)

for token in (
    "chat_viewport_media_stability_v86",
    "media_chat_full_photo_target_v86",
    "media_chat_sticker_scroll_event_v86",
    "media_chat_sticker_timer_proc_unsafe",
    "media_chat_upgrade_photo_in_place",
):
    if token not in s:
        raise SystemExit(f"Required v8.6 predecessor marker missing: {token}")

# ---------------------------------------------------------------------------
# A) Full-photo replacement is bound to the exact RichEdit OLE object clicked
# by the user. v8.6 still had a positional fallback (unique/nearest bitmap in a
# message range); the runtime log proves that fallback can pick the neighbour at
# cp+2, leaving the clicked thumbnail in place and inserting a duplicate.
# Keep the canonical COM IUnknown identity alive across the async transfer.
# ---------------------------------------------------------------------------
state_anchor = (
    "static Document* media_chat_full_photo_target_v86 = NULL; "
    "// chat_viewport_media_stability_v86"
)
if state_anchor not in s:
    raise SystemExit("Could not locate v8.6 full-photo target state.")

state_extra = r'''
// chat_media_identity_stability_v87
static IUnknown* media_chat_full_photo_ole_identity_v87 = NULL;
static int media_chat_full_photo_clicked_cp_v87 = -1;
'''
s = s.replace(state_anchor, state_anchor + state_extra, 1)

upgrade_pos = s.find("static bool media_chat_upgrade_photo_in_place(")
if upgrade_pos < 0:
    raise SystemExit("Could not locate in-place photo upgrade helper.")

identity_helpers = r'''
static bool media_chat_v87_query_bitmap_identity(
    IOleObject* object,
    IUnknown** identity
) {
    if (identity)
        *identity = NULL;

    if (!object)
        return false;

    IDataObject* data = NULL;
    bool bitmap = false;

    if (
        SUCCEEDED(
            object->QueryInterface(
                IID_IDataObject,
                (void**)&data
            )
        ) &&
        data
    ) {
        FORMATETC format = {
            CF_BITMAP,
            NULL,
            DVASPECT_CONTENT,
            -1,
            TYMED_GDI
        };

        bitmap =
            SUCCEEDED(
                data->QueryGetData(
                    &format
                )
            );

        data->Release();
    }

    if (!bitmap)
        return false;

    if (!identity)
        return true;

    return SUCCEEDED(
        object->QueryInterface(
            IID_IUnknown,
            (void**)identity
        )
    ) && *identity;
}

static int media_chat_v87_find_identity_cp(
    IUnknown* wanted
) {
    if (!chat || !wanted)
        return -1;

    IRichEditOle* ole = NULL;

    SendMessageW(
        chat,
        EM_GETOLEINTERFACE,
        0,
        (LPARAM)&ole
    );

    if (!ole)
        return -1;

    int found = -1;
    LONG count = ole->GetObjectCount();

    for (LONG i = 0; i < count; i++) {
        REOBJECT reo = {0};
        reo.cbStruct = sizeof(reo);

        if (
            FAILED(
                ole->GetObject(
                    i,
                    &reo,
                    REO_GETOBJ_POLEOBJ
                )
            ) ||
            !reo.poleobj
        ) {
            continue;
        }

        IUnknown* identity = NULL;

        // The object was verified as a bitmap at click time. Match canonical
        // COM identity here without re-querying CF_BITMAP: some RichEdit OLE
        // wrappers transiently stop advertising that format while an async
        // media request is completing, even though the same OLE is still alive.
        if (
            SUCCEEDED(
                reo.poleobj->QueryInterface(
                    IID_IUnknown,
                    (void**)&identity
                )
            ) &&
            identity
        ) {
            if (identity == wanted)
                found = (int)reo.cp;

            identity->Release();
        }

        reo.poleobj->Release();

        if (found >= 0)
            break;
    }

    ole->Release();
    return found;
}

static bool media_chat_v87_exact_bitmap_at_cp(
    int cp
) {
    if (!chat || cp < 0)
        return false;

    IRichEditOle* ole = NULL;

    SendMessageW(
        chat,
        EM_GETOLEINTERFACE,
        0,
        (LPARAM)&ole
    );

    if (!ole)
        return false;

    bool found = false;
    LONG count = ole->GetObjectCount();

    for (LONG i = 0; i < count; i++) {
        REOBJECT reo = {0};
        reo.cbStruct = sizeof(reo);

        if (
            FAILED(
                ole->GetObject(
                    i,
                    &reo,
                    REO_GETOBJ_POLEOBJ
                )
            ) ||
            !reo.poleobj
        ) {
            continue;
        }

        if (
            (int)reo.cp == cp &&
            media_chat_v87_query_bitmap_identity(
                reo.poleobj,
                NULL
            )
        ) {
            found = true;
        }

        reo.poleobj->Release();

        if (found)
            break;
    }

    ole->Release();
    return found;
}

static LONG media_chat_v87_object_count() {
    if (!chat)
        return -1;

    IRichEditOle* ole = NULL;

    SendMessageW(
        chat,
        EM_GETOLEINTERFACE,
        0,
        (LPARAM)&ole
    );

    if (!ole)
        return -1;

    LONG count = ole->GetObjectCount();
    ole->Release();
    return count;
}

static bool media_chat_v87_capture_photo_ole(
    Document* document
) {
    if (media_chat_full_photo_ole_identity_v87) {
        media_chat_full_photo_ole_identity_v87->Release();
        media_chat_full_photo_ole_identity_v87 = NULL;
    }

    media_chat_full_photo_clicked_cp_v87 = -1;

    if (!chat || !document || document->min < 0)
        return false;

    IRichEditOle* ole = NULL;

    SendMessageW(
        chat,
        EM_GETOLEINTERFACE,
        0,
        (LPARAM)&ole
    );

    if (!ole)
        return false;

    int expected = document->min;
    int matches = 0;
    IUnknown* captured = NULL;
    LONG count = ole->GetObjectCount();

    for (LONG i = 0; i < count; i++) {
        REOBJECT reo = {0};
        reo.cbStruct = sizeof(reo);

        if (
            FAILED(
                ole->GetObject(
                    i,
                    &reo,
                    REO_GETOBJ_POLEOBJ
                )
            ) ||
            !reo.poleobj
        ) {
            continue;
        }

        if ((int)reo.cp == expected) {
            IUnknown* identity = NULL;

            if (
                media_chat_v87_query_bitmap_identity(
                    reo.poleobj,
                    &identity
                ) &&
                identity
            ) {
                matches++;

                if (!captured) {
                    captured = identity;
                } else {
                    identity->Release();
                }
            }
        }

        reo.poleobj->Release();
    }

    ole->Release();

    if (matches != 1 || !captured) {
        if (captured)
            captured->Release();

        diag_log(
            "chat v87 photo OLE capture refused cp=%d matches=%d",
            expected,
            matches
        );
        return false;
    }

    media_chat_full_photo_ole_identity_v87 = captured;
    media_chat_full_photo_clicked_cp_v87 = expected;

    diag_log(
        "chat v87 photo OLE captured cp=%d ptr=%p",
        expected,
        captured
    );

    return true;
}

'''
s = s[:upgrade_pos] + identity_helpers + s[upgrade_pos:]

rs, re = function_range(s, "static void media_chat_full_photo_reset(")
reset_func = s[rs:re]
brace = reset_func.find("{")
if brace < 0:
    raise SystemExit("Could not locate full-photo reset brace.")

reset_guard = r'''
    if (media_chat_full_photo_ole_identity_v87) {
        media_chat_full_photo_ole_identity_v87->Release();
        media_chat_full_photo_ole_identity_v87 = NULL;
    }
    media_chat_full_photo_clicked_cp_v87 = -1;
'''
reset_func = reset_func[:brace + 1] + "\n" + reset_guard + reset_func[brace + 1:]
s = s[:rs] + reset_func + s[re:]

user_action_definition = """static bool media_chat_full_photo_user_action(
    Document* document,
    bool save_and_open
) {"""
us, ue = function_range(s, user_action_definition)
user_func = s[us:ue]

same_anchor = "    bool same_active ="
if same_anchor not in user_func:
    raise SystemExit("Could not locate same-active photo branch.")
user_func = user_func.replace(
    same_anchor,
    r'''    media_chat_v87_capture_photo_ole(
        document
    );

    bool same_active =''',
    1,
)

memset_anchor = r'''    memset(
        document->photo_msg_id,'''
if memset_anchor not in user_func:
    raise SystemExit("Could not locate new-transfer photo state reset.")
user_func = user_func.replace(
    memset_anchor,
    r'''    // A different active transfer may have called reset() above.
    media_chat_v87_capture_photo_ole(
        document
    );

    memset(
        document->photo_msg_id,''',
    1,
)
s = s[:us] + user_func + s[ue:]

ps, pe = function_range(s, "static bool media_chat_upgrade_photo_in_place(")
photo_replace = r'''static bool media_chat_upgrade_photo_in_place(
    Document* document,
    HBITMAP decoded
) {
    if (!document || !decoded || !chat)
        return false;

    if (!media_chat_full_photo_ole_identity_v87) {
        diag_log(
            "chat v87 photo replacement refused: no clicked OLE identity min=%d",
            document->min
        );
        return false;
    }

    int target_cp =
        media_chat_v87_find_identity_cp(
            media_chat_full_photo_ole_identity_v87
        );

    if (target_cp < 0) {
        diag_log(
            "chat v87 photo replacement refused: clicked OLE vanished captured=%d current=%d",
            media_chat_full_photo_clicked_cp_v87,
            document->min
        );
        return false;
    }

    HBITMAP card =
        media_chat_make_photo_card(
            decoded
        );

    HBITMAP display =
        card
            ? card
            : decoded;

    CHARRANGE selection = {0};

    SendMessageW(
        chat,
        EM_EXGETSEL,
        0,
        (LPARAM)&selection
    );

    POINT scroll = {0, 0};

    BOOL have_scroll =
        (BOOL)SendMessageW(
            chat,
            EM_GETSCROLLPOS,
            0,
            (LPARAM)&scroll
        );

    bool was_drawchat = drawchat;

    if (was_drawchat) {
        SendMessageW(
            chat,
            WM_SETREDRAW,
            FALSE,
            0
        );
    }

    SendMessageW(
        chat,
        EM_SETSEL,
        target_cp,
        target_cp + 1
    );

    SendMessageW(
        chat,
        EM_REPLACESEL,
        FALSE,
        (LPARAM)L""
    );

    int lingering_cp =
        media_chat_v87_find_identity_cp(
            media_chat_full_photo_ole_identity_v87
        );

    bool replaced = false;
    int actual_cp = -1;

    if (lingering_cp < 0) {
        LONG count_before_insert =
            media_chat_v87_object_count();

        bool plus_one_occupied_before =
            media_chat_v87_exact_bitmap_at_cp(
                target_cp + 1
            );

        insert_image(
            chat,
            NULL,
            display
        );

        LONG count_after_insert =
            media_chat_v87_object_count();

        bool inserted_one =
            count_before_insert >= 0 &&
            count_after_insert == count_before_insert + 1;

        if (
            inserted_one &&
            media_chat_v87_exact_bitmap_at_cp(target_cp)
        ) {
            actual_cp = target_cp;
        } else if (
            inserted_one &&
            !plus_one_occupied_before &&
            media_chat_v87_exact_bitmap_at_cp(target_cp + 1)
        ) {
            actual_cp = target_cp + 1;
        }

        replaced = actual_cp >= 0;
    } else {
        diag_log(
            "chat v87 photo replacement refused: exact OLE delete failed cp=%d",
            lingering_cp
        );
    }

    if (card)
        DeleteObject(card);

    if (replaced) {
        document->min = actual_cp;
        document->max = actual_cp + 1;
    }

    if (
        selection.cpMin >= 0 &&
        selection.cpMax >= 0
    ) {
        SendMessageW(
            chat,
            EM_EXSETSEL,
            0,
            (LPARAM)&selection
        );
    }

    if (have_scroll) {
        SendMessageW(
            chat,
            EM_SETSCROLLPOS,
            0,
            (LPARAM)&scroll
        );
    }

    if (was_drawchat) {
        SendMessageW(
            chat,
            WM_SETREDRAW,
            TRUE,
            0
        );

        RedrawWindow(
            chat,
            NULL,
            NULL,
            RDW_INVALIDATE |
                RDW_ERASE |
                RDW_ALLCHILDREN
        );
    }

    if (have_scroll) {
        SendMessageW(
            chat,
            EM_SETSCROLLPOS,
            0,
            (LPARAM)&scroll
        );
    }

    if (replaced) {
        diag_log(
            "chat v87 full photo replaced exact captured=%d old=%d new=%d",
            media_chat_full_photo_clicked_cp_v87,
            target_cp,
            actual_cp
        );
    } else {
        diag_log(
            "chat v87 photo replacement refused: insert verification failed old=%d",
            target_cp
        );
    }

    return replaced;
}'''
s = s[:ps] + photo_replace + s[pe:]

ts, te = function_range(s, "static VOID CALLBACK media_chat_sticker_timer_proc_unsafe(")
timer_func = s[ts:te]

release_call = r'''                media_chat_sticker_release_video_v85(
                    sticker
                );'''
pause_call = r'''                if (
                    sticker->video &&
                    !sticker->video_paused_for_visibility
                ) {
                    sticker->video->Pause();
                    sticker->video_paused_for_visibility = true;

                    diag_log(
                        "chat v87 WebM paused without release path=%ls",
                        sticker->path
                    );
                }'''

release_count = timer_func.count(release_call)
if release_count != 3:
    raise SystemExit(
        f"Expected three v8.5 WebM release sites in timer, found {release_count}."
    )
timer_func = timer_func.replace(release_call, pause_call)
s = s[:ts] + timer_func + s[te:]

ss, se = function_range(s, "void media_chat_sticker_scroll_event_v86()")
scroll_event = r'''void media_chat_sticker_scroll_event_v86() {
    if (!chat)
        return;

    media_chat_sticker_scroll_quiet_until_v86 = 0;

    PostMessageW(
        chat,
        WM_APP + 0x37B,
        0,
        0
    );
}'''
s = s[:ss] + scroll_event + s[se:]

ws, we = function_range(s, "static VOID CALLBACK media_chat_sticker_timer_proc(")
after_scroll = r'''

void media_chat_sticker_after_scroll_v87() {
    media_chat_sticker_scroll_quiet_until_v86 = 0;

    media_chat_sticker_timer_proc(
        NULL,
        0,
        0,
        GetTickCount()
    );
}
'''
s = s[:we] + after_scroll + s[we:]

write(t, s)

s = read(h)
decl_anchor = "void media_chat_sticker_scroll_event_v86(); // chat_viewport_media_stability_v86"
if decl_anchor not in s:
    raise SystemExit("Could not locate v8.6 sticker scroll declaration.")
if "media_chat_sticker_after_scroll_v87" not in s:
    s = s.replace(
        decl_anchor,
        decl_anchor +
        "\nvoid media_chat_sticker_after_scroll_v87(); // chat_media_identity_stability_v87",
        1,
    )
write(h, s)

s = read(p)
wnd_sig = "LRESULT CALLBACK WndProcChat(HWND hWnd, UINT msg, WPARAM wParam, LPARAM lParam) {"
wnd_pos = s.find(wnd_sig)
if wnd_pos < 0:
    raise SystemExit("Could not locate WndProcChat for v8.7 scroll completion.")
insert_at = wnd_pos + len(wnd_sig)

post_scroll_hook = r'''

    // chat_media_identity_stability_v87
    if (
        hWnd == chat &&
        msg == WM_APP + 0x37B
    ) {
        media_chat_sticker_after_scroll_v87();
        return 0;
    }
'''
s = s[:insert_at] + post_scroll_hook + s[insert_at:]
write(p, s)

checks = {
    t: [
        "chat_media_identity_stability_v87",
        "media_chat_full_photo_ole_identity_v87",
        "chat v87 photo OLE captured",
        "chat v87 full photo replaced exact",
        "chat v87 photo replacement refused",
        "chat v87 WebM paused without release",
        "media_chat_sticker_after_scroll_v87",
        "WM_APP + 0x37B",
    ],
    h: [
        "media_chat_sticker_after_scroll_v87",
        "chat_media_identity_stability_v87",
    ],
    p: [
        "chat_media_identity_stability_v87",
        "msg == WM_APP + 0x37B",
        "media_chat_sticker_after_scroll_v87();",
    ],
}

for path, tokens in checks.items():
    data = read(path)
    for token in tokens:
        if token not in data:
            raise SystemExit(f"v8.7 verification failed in {path.name}: {token}")

print(
    "Applied chat media identity/stability v8.7: single-click full-photo upgrades "
    "are transactionally bound to the exact clicked RichEdit OLE COM identity "
    "with no nearest/unique positional fallback, and animated WebM stickers keep "
    "their MFPlay instance across viewport changes while scroll repositioning is "
    "performed immediately after RichEdit consumes the scroll event."
)
