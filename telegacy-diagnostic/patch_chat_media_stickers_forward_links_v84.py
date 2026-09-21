#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_chat_media_stickers_forward_links_v84.py <Telegacy source directory>")

root = Path(sys.argv[1]).resolve()
h = root / "include" / "telegacy.h"
t = root / "src" / "telegacy.cpp"
m = root / "src" / "message.cpp"
hp = root / "src" / "helpers.cpp"

for p in (h, t, m, hp):
    if not p.exists():
        raise SystemExit(f"Missing expected file: {p}")


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
if "chat_media_stickers_forward_links_v84" in s:
    print("Chat media/stickers/forward links v8.4 already applied.")
    raise SystemExit(0)

for token in (
    "chat_animated_sticker_stability_v83",
    "chat_photo_open_sticker_viewport_v81",
    "chat_media_ole_rebind_v80",
    "chat_scope_sync_v74",
):
    if token not in s:
        raise SystemExit(f"Required predecessor marker missing in telegacy.cpp: {token}")


# ---------------------------------------------------------------------------
# A) Async image replacement: refuse ambiguous nearest-neighbour OLE matches.
# The supplied log showed repeated distance=3/4 replacements with candidates=2;
# that can shift a late thumbnail into the neighbouring media object and produce
# the visually duplicated images. Exact/adjacent matches remain valid. A stale
# range is accepted only when its owning message contains one bitmap OLE.
# ---------------------------------------------------------------------------
fs, fe = function_range(s, "bool media_chat_replace_loaded_bitmap(")

safe_replace = r'''// chat_media_stickers_forward_links_v84
bool media_chat_replace_loaded_bitmap(
    Document* document,
    HBITMAP decoded
) {
    if (!document || !decoded || !chat)
        return false;

    IRichEditOle* ole = NULL;
    SendMessageW(chat, EM_GETOLEINTERFACE, 0, (LPARAM)&ole);
    if (!ole)
        return false;

    int expected = document->min;
    int lower = expected > 96 ? expected - 96 : 0;
    int upper = expected + 96;
    bool message_range = false;

    for (int i = 0; i < (int)messages.size(); i++) {
        if (
            expected >= messages[i].start_char - 4 &&
            expected <= messages[i].end_footer + 4
        ) {
            lower = messages[i].start_char;
            upper = messages[i].end_footer;
            message_range = true;
            break;
        }
    }

    int best_cp = -1;
    int best_distance = INT_MAX;
    int candidates = 0;

    LONG object_count = ole->GetObjectCount();

    for (LONG i = 0; i < object_count; i++) {
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

        IDataObject* data = NULL;
        bool bitmap = false;

        if (
            SUCCEEDED(
                reo.poleobj->QueryInterface(
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

        reo.poleobj->Release();
        reo.poleobj = NULL;

        if (!bitmap)
            continue;

        int cp = (int)reo.cp;

        if (cp < lower || cp > upper)
            continue;

        candidates++;

        int distance =
            cp >= expected
                ? cp - expected
                : expected - cp;

        if (distance < best_distance) {
            best_distance = distance;
            best_cp = cp;
        }
    }

    ole->Release();

    bool unambiguous =
        best_cp >= 0 &&
        (
            best_distance <= 1 ||
            (message_range && candidates == 1)
        );

    if (!unambiguous) {
        diag_log(
            "chat v84 ambiguous native replace skipped expected=%d range=%d..%d candidates=%d distance=%d",
            expected,
            lower,
            upper,
            candidates,
            best_distance
        );
        return false;
    }

    HBITMAP decorated =
        document->photo_size == 3
            ? media_chat_make_video_preview(decoded)
            : media_chat_make_photo_card(decoded);

    HBITMAP display =
        decorated
            ? decorated
            : decoded;

    CHARRANGE selection = {0};
    SendMessageW(
        chat,
        EM_EXGETSEL,
        0,
        (LPARAM)&selection
    );

    POINT media_v84_scroll = {0, 0};

    BOOL media_v84_have_scroll =
        (BOOL)SendMessageW(
            chat,
            EM_GETSCROLLPOS,
            0,
            (LPARAM)&media_v84_scroll
        );

    bool was_drawchat = drawchat;

    if (was_drawchat)
        SendMessageW(
            chat,
            WM_SETREDRAW,
            FALSE,
            0
        );

    SendMessageW(
        chat,
        EM_SETSEL,
        best_cp,
        best_cp + 1
    );

    SendMessageW(
        chat,
        EM_REPLACESEL,
        FALSE,
        (LPARAM)L""
    );

    insert_image(
        chat,
        NULL,
        display
    );

    if (document->photo_size == 3) {
        SendMessageW(
            chat,
            EM_SETSEL,
            best_cp,
            best_cp + 1
        );

        CHARFORMAT2W link_format;
        memset(
            &link_format,
            0,
            sizeof(link_format)
        );

        link_format.cbSize =
            sizeof(link_format);
        link_format.dwMask = CFM_LINK;
        link_format.dwEffects = CFE_LINK;

        SendMessageW(
            chat,
            EM_SETCHARFORMAT,
            SCF_SELECTION,
            (LPARAM)&link_format
        );
    }

    if (decorated)
        DeleteObject(decorated);

    document->min = best_cp;
    document->max = best_cp + 1;

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

    if (media_v84_have_scroll) {
        SendMessageW(
            chat,
            EM_SETSCROLLPOS,
            0,
            (LPARAM)&media_v84_scroll
        );
    }

    if (was_drawchat) {
        SendMessageW(
            chat,
            WM_SETREDRAW,
            TRUE,
            0
        );
        InvalidateRect(
            chat,
            NULL,
            FALSE
        );
    }

    if (media_v84_have_scroll) {
        SendMessageW(
            chat,
            EM_SETSCROLLPOS,
            0,
            (LPARAM)&media_v84_scroll
        );
    }

    diag_log(
        "chat v84 native replaced OLE expected=%d actual=%d distance=%d candidates=%d",
        expected,
        best_cp,
        best_distance,
        candidates
    );

    return true;
}'''

s = s[:fs] + safe_replace + s[fe:]


# ---------------------------------------------------------------------------
# B) Sticker runtime:
# - download static .webp originals too (not just TGS/WebM);
# - display static WebP through the same stable overlay;
# - when no bitmap OLE exists, anchor the overlay to Document::min, which is the
#   exact placeholder character inserted by message.cpp. This is the condition
#   proven by the v8.3 log: WebM was downloaded+activated but never played.
# ---------------------------------------------------------------------------
ks, ke = function_range(s, "static int media_chat_sticker_kind_from_filename(")
kind_func = s[ks:ke]

needle = r'''    if (_wcsicmp(dot, L".webm") == 0)
        return 2;
'''
if needle not in kind_func:
    raise SystemExit("Could not locate WebM sticker-kind branch.")

kind_func = kind_func.replace(
    needle,
    needle
    + r'''
    if (_wcsicmp(dot, L".webp") == 0)
        return 3;
''',
    1,
)

s = s[:ks] + kind_func + s[ke:]


# Cache extension.
cs, ce = function_range(s, "static bool media_chat_sticker_cache_path(")
cache_func = s[cs:ce]

old_ext = r'''    const wchar_t* extension =
        kind == 2
            ? L".webm"
            : L".tgs";'''

new_ext = r'''    const wchar_t* extension =
        kind == 2
            ? L".webm"
            : (
                kind == 3
                    ? L".webp"
                    : L".tgs"
            );'''

if old_ext not in cache_func:
    raise SystemExit("Could not locate v8.3 sticker cache extension selection.")

cache_func = cache_func.replace(
    old_ext,
    new_ext,
    1
)

s = s[:cs] + cache_func + s[ce:]


# Paint static WebP using the same pixel surface used by rlottie.
paint_old = r'''            sticker->kind == 1 &&
            !sticker->pixels.empty()'''

paint_new = r'''            (
                sticker->kind == 1 ||
                sticker->kind == 3
            ) &&
            !sticker->pixels.empty()'''

if paint_old not in s:
    raise SystemExit("Could not locate sticker WM_PAINT TGS condition.")

s = s.replace(
    paint_old,
    paint_new,
    1
)


# Static WebP loader, inserted before the timer callback.
timer_anchor = "static VOID CALLBACK media_chat_sticker_timer_proc_unsafe("
timer_pos = s.find(timer_anchor)
if timer_pos < 0:
    raise SystemExit("Could not locate v8.3 unsafe sticker timer.")

webp_loader = r'''
static bool media_chat_sticker_load_webp_v84(
    ChatAnimatedSticker* sticker
) {
    if (
        !sticker ||
        sticker->kind != 3
    ) {
        return false;
    }

    if (!sticker->pixels.empty())
        return true;

    std::vector<BYTE> bytes;

    if (
        !media_chat_sticker_read_file(
            sticker->path,
            &bytes
        ) ||
        bytes.empty()
    ) {
        diag_log(
            "chat v84 WebP sticker read failed path=%ls",
            sticker->path
        );
        return false;
    }

    WebPDecoderConfig config;

    if (!WebPInitDecoderConfig(&config))
        return false;

    if (
        WebPGetFeatures(
            &bytes[0],
            bytes.size(),
            &config.input
        ) != VP8_STATUS_OK
    ) {
        return false;
    }

    int width =
        media_chat_sticker_card_width();

    int height =
        media_chat_sticker_card_height();

    config.options.use_scaling = 1;
    config.options.scaled_width = width;
    config.options.scaled_height = height;
    config.output.colorspace = MODE_BGRA;

    if (
        WebPDecode(
            &bytes[0],
            bytes.size(),
            &config
        ) != VP8_STATUS_OK
    ) {
        WebPFreeDecBuffer(
            &config.output
        );
        return false;
    }

    BYTE* rgba =
        config.output.u.RGBA.rgba;

    int stride =
        config.output.u.RGBA.stride;

    if (!rgba || stride <= 0) {
        WebPFreeDecBuffer(
            &config.output
        );
        return false;
    }

    sticker->pixels.assign(
        width * height,
        0
    );

    COLORREF background =
        GetSysColor(COLOR_WINDOW);

    unsigned int bg_r =
        GetRValue(background);
    unsigned int bg_g =
        GetGValue(background);
    unsigned int bg_b =
        GetBValue(background);

    for (int y = 0; y < height; y++) {
        BYTE* row =
            rgba + y * stride;

        for (int x = 0; x < width; x++) {
            BYTE* pixel =
                row + x * 4;

            unsigned int blue = pixel[0];
            unsigned int green = pixel[1];
            unsigned int red = pixel[2];
            unsigned int alpha = pixel[3];
            unsigned int inv = 255 - alpha;

            red =
                (
                    red * alpha +
                    bg_r * inv
                ) / 255;

            green =
                (
                    green * alpha +
                    bg_g * inv
                ) / 255;

            blue =
                (
                    blue * alpha +
                    bg_b * inv
                ) / 255;

            sticker->pixels[
                y * width + x
            ] =
                (red << 16) |
                (green << 8) |
                blue;
        }
    }

    WebPFreeDecBuffer(
        &config.output
    );

    diag_log(
        "chat v84 WebP sticker ready path=%ls",
        sticker->path
    );

    return true;
}

'''

s = s[:timer_pos] + webp_loader + s[timer_pos:]


# Timer: allow placeholder-char anchoring if the sticker never received a
# bitmap thumbnail OLE.
ts, te = function_range(s, "static VOID CALLBACK media_chat_sticker_timer_proc_unsafe(")
timer_func = s[ts:te]

old_cp = r'''        int sticker_cp =
            media_chat_sticker_find_ole_cp(
                document
            );

        if (sticker_cp < 0) {
            if (sticker->window)
                ShowWindow(
                    sticker->window,
                    SW_HIDE
                );

            sticker->visible = false;
            continue;
        }'''

new_cp = r'''        int sticker_cp =
            media_chat_sticker_find_ole_cp(
                document
            );

        // Animated stickers can legitimately have no bitmap OLE: Telegram may
        // omit a usable thumbnail. Document::min still points to the placeholder
        // character that message.cpp reserved for this exact sticker.
        if (sticker_cp < 0)
            sticker_cp = document->min;

        if (sticker_cp < 0) {
            if (sticker->window)
                ShowWindow(
                    sticker->window,
                    SW_HIDE
                );

            sticker->visible = false;
            continue;
        }'''

if old_cp not in timer_func:
    raise SystemExit("Could not locate v8.2 sticker OLE-only anchor block.")

timer_func = timer_func.replace(
    old_cp,
    new_cp,
    1
)

old_branch = r'''        if (sticker->kind == 1) {
            if (
                media_chat_sticker_load_lottie(
                    sticker
                )
            ) {
                media_chat_sticker_render_lottie(
                    sticker,
                    now
                );
            }
        } else if (sticker->kind == 2) {'''

new_branch = r'''        if (sticker->kind == 1) {
            if (
                media_chat_sticker_load_lottie(
                    sticker
                )
            ) {
                media_chat_sticker_render_lottie(
                    sticker,
                    now
                );
            }
        } else if (sticker->kind == 3) {
            if (
                media_chat_sticker_load_webp_v84(
                    sticker
                )
            ) {
                InvalidateRect(
                    sticker->window,
                    NULL,
                    FALSE
                );
            }
        } else if (sticker->kind == 2) {'''

if old_branch not in timer_func:
    raise SystemExit("Could not locate v8.2 TGS/WebM timer branch.")

timer_func = timer_func.replace(
    old_branch,
    new_branch,
    1
)

s = s[:ts] + timer_func + s[te:]

# Persist the media/sticker runtime changes before switching to helpers.cpp.
write(t, s)


# ---------------------------------------------------------------------------
# C) Forwarded-from names become in-app links.
# Store them in the existing links[] vector using a private telelegacy-peer:
# target. update_positions() and normal chat cleanup already maintain/free this
# vector, so forwarded links inherit the proven RichEdit range bookkeeping.
# ---------------------------------------------------------------------------
hs, he = function_range(s := read(hp), "int msgfwd_addname(")
fwd_func = s[hs:he]

name_block_start = fwd_func.find("if (name) {")
if name_block_start < 0:
    raise SystemExit("Could not locate msgfwd_addname name-render block.")

return_pos = fwd_func.find("return written_info;", name_block_start)
if return_pos < 0:
    raise SystemExit("Could not locate msgfwd_addname return.")

return_end = return_pos + len("return written_info;")

new_tail = r'''if (name) {
		written_info += riched_write(chat, name);
		int deleted_wchars = 0;
		for (int j = 0; j < wcslen(name); j++)
			j = emoji_adder(
				j,
				name,
				pos_init,
				13,
				chat,
				&deleted_wchars
			);

		written_info -= deleted_wchars;

		SendMessage(
			chat,
			EM_SETSEL,
			pos_init + written_info,
			pos_init + written_info
		);

		if (
			(flags & (1 << 0)) &&
			written_info > 0
		) {
			unsigned int peer_ctor =
				read_le(
					msgfwd + 8,
					4
				);

			int peer_type = 2;

			if (peer_ctor == 0x59511722)
				peer_type = 0;
			else if (peer_ctor == 0x36c6019a)
				peer_type = 1;

			unsigned __int64 peer_id =
				(unsigned __int64)read_le(
					msgfwd + 12,
					8
				);

			if (peer_id != 0) {
				wchar_t target[64] = {0};

				_snwprintf(
					target,
					ARRAYSIZE(target) - 1,
					L"telegacy-peer:%d:%016I64X",
					peer_type,
					peer_id
				);

				TEXTRANGE forward_link;
				forward_link.chrg.cpMin =
					pos_init;
				forward_link.chrg.cpMax =
					pos_init + written_info;
				forward_link.lpstrText =
					_wcsdup(target);

				if (forward_link.lpstrText) {
					links.push_back(
						forward_link
					);

					CHARFORMAT2W cf = {0};
					cf.cbSize = sizeof(cf);
					cf.dwMask =
						CFM_LINK |
						CFM_UNDERLINE |
						CFM_COLOR;
					cf.dwEffects =
						CFE_LINK |
						CFE_UNDERLINE;
					cf.crTextColor =
						RGB(0, 0, 255);

					SendMessageW(
						chat,
						EM_SETSEL,
						forward_link.chrg.cpMin,
						forward_link.chrg.cpMax
					);

					SendMessageW(
						chat,
						EM_SETCHARFORMAT,
						SCF_SELECTION,
						(LPARAM)&cf
					);

					SendMessageW(
						chat,
						EM_SETSEL,
						pos_init + written_info,
						pos_init + written_info
					);

					diag_log(
						"chat v84 forward origin link type=%d id=%016I64X range=%d..%d",
						peer_type,
						peer_id,
						forward_link.chrg.cpMin,
						forward_link.chrg.cpMax
					);
				}
			}
		}
	}

	if (name_allocated)
		free(name);

	return written_info;'''

fwd_func = (
    fwd_func[:name_block_start] +
    new_tail +
    fwd_func[return_end:]
)

s = s[:hs] + fwd_func + s[he:]
write(hp, s)


# ---------------------------------------------------------------------------
# In-app forwarded-origin navigation. Reuse loaded dialogs immediately; when
# the peer is not loaded, switch to All Chats, resolve it through contacts.search
# by the displayed forwarded name, then auto-open the exact matching id.
# Also parse User objects from contacts.Found so forwarded people can resolve,
# not only channels.
# ---------------------------------------------------------------------------
s = read(t)

search_state_anchor = "static std::vector<Peer*> global_chat_search_opened;"
if search_state_anchor not in s:
    raise SystemExit("Could not locate global search state for forward navigation.")

forward_state = r'''
static void global_chat_search_begin(const wchar_t* query);

static bool chat_v84_forward_search_pending = false;
static unsigned __int64 chat_v84_forward_target_id = 0;
static int chat_v84_forward_target_type = -1;

static bool chat_v84_open_peer_pointer(
    Peer* target
) {
    if (!target || !hComboBoxChats)
        return false;

    if (hChatScopeTabs) {
        TabCtrl_SetCurSel(
            hChatScopeTabs,
            global_chat_search_is_result_peer(target)
                ? 1
                : 0
        );
    }

    global_chat_search_mode =
        global_chat_search_is_result_peer(target);

    EnableWindow(
        hComboBoxFolders,
        global_chat_search_mode
            ? FALSE
            : TRUE
    );

    if (!global_chat_search_mode) {
        if (
            folders &&
            folders_count > 0
        ) {
            current_folder = &folders[0];

            SendMessage(
                hComboBoxFolders,
                CB_SETCURSEL,
                0,
                0
            );
        }

        chat_search_updating = true;
        SetWindowTextW(
            hChatSearch,
            target->name
                ? target->name
                : L""
        );
        chat_search_updating = false;

        rebuild_chat_combo_by_name(
            target->name
                ? target->name
                : L""
        );
    }

    int count =
        (int)SendMessage(
            hComboBoxChats,
            CB_GETCOUNT,
            0,
            0
        );

    for (int i = 0; i < count; i++) {
        Peer* item =
            (Peer*)SendMessage(
                hComboBoxChats,
                CB_GETITEMDATA,
                i,
                0
            );

        if (
            item == target ||
            (
                item &&
                item != (Peer*)CB_ERR &&
                item->type == target->type &&
                memcmp(
                    item->id,
                    target->id,
                    8
                ) == 0
            )
        ) {
            SendMessage(
                hComboBoxChats,
                CB_SETCURSEL,
                i,
                0
            );

            PostMessage(
                hMain,
                WM_COMMAND,
                MAKEWPARAM(
                    3,
                    CBN_SELCHANGE
                ),
                (LPARAM)hComboBoxChats
            );

            return true;
        }
    }

    return false;
}

static bool chat_v84_open_forward_origin(
    int type,
    unsigned __int64 id,
    const wchar_t* display_name
) {
    for (int i = 0; i < peers_count; i++) {
        if (
            peers[i].type == type &&
            (unsigned __int64)read_le(
                peers[i].id,
                8
            ) == id
        ) {
            diag_log(
                "chat v84 forward origin resolved locally type=%d id=%016I64X",
                type,
                id
            );

            return chat_v84_open_peer_pointer(
                &peers[i]
            );
        }
    }

    for (
        int i = 0;
        i < (int)global_chat_search_opened.size();
        i++
    ) {
        Peer* peer =
            global_chat_search_opened[i];

        if (
            peer &&
            peer->type == type &&
            (unsigned __int64)read_le(
                peer->id,
                8
            ) == id
        ) {
            return chat_v84_open_peer_pointer(
                peer
            );
        }
    }

    if (
        !display_name ||
        !display_name[0] ||
        !hChatScopeTabs ||
        !hChatSearch
    ) {
        return false;
    }

    chat_v84_forward_search_pending = true;
    chat_v84_forward_target_id = id;
    chat_v84_forward_target_type = type;

    global_chat_search_mode = true;

    TabCtrl_SetCurSel(
        hChatScopeTabs,
        1
    );

    EnableWindow(
        hComboBoxFolders,
        FALSE
    );

    chat_search_updating = true;

    SetWindowTextW(
        hChatSearch,
        display_name
    );

    chat_search_updating = false;

    global_chat_search_begin(
        display_name
    );

    diag_log(
        "chat v84 forward origin resolving globally type=%d id=%016I64X name=%ls",
        type,
        id,
        display_name
    );

    return true;
}

'''

s = s.replace(
    search_state_anchor,
    search_state_anchor + forward_state,
    1
)


# Extend the final v7.9 contacts.Found path without replacing its exact channel
# parser. v7.9 deliberately reconstructs channels by stable peerChannel IDs and
# does not walk modern object tails. For a forwarded PERSON we only need the one
# exact User object requested by the private navigation target, so scan for that
# ctor/id pair and let legacy set_peer_info decode just that single object.
gs, ge = function_range(
    s,
    "bool global_chat_search_handle_found("
)

search_func = s[gs:ge]

final_rebuild = search_func.rfind(
    "global_chat_search_rebuild_combo();"
)
if final_rebuild < 0:
    raise SystemExit(
        "Could not locate final global search combo rebuild."
    )

final_return = search_func.find(
    "return true;",
    final_rebuild
)
if final_return < 0:
    raise SystemExit(
        "Could not locate final global search return."
    )

forward_finish = r'''if (
        chat_v84_forward_search_pending &&
        chat_v84_forward_target_type == 0
    ) {
        for (
            int probe = 4;
            probe + 28 <= length;
            probe += 4
        ) {
            if (
                read_le(
                    response + probe,
                    4
                ) != 0x4b46c37e ||
                (unsigned __int64)read_le(
                    response + probe + 12,
                    8
                ) !=
                    chat_v84_forward_target_id
            ) {
                continue;
            }

            Peer peer = {0};
            peer.type = 0;

            int consumed =
                set_peer_info(
                    response + probe,
                    &peer,
                    false
                );

            if (
                consumed > 0 &&
                consumed <= length - probe &&
                peer.name &&
                peer.name[0]
            ) {
                peer.full = true;
                peer.perm.cansendmsg = false;
                peer.perm.cansendmed = false;
                peer.perm.cansendvoice = false;
                peer.perm.cansendphoto = false;
                peer.perm.cansendvideo = false;
                peer.perm.cansendaudio = false;
                peer.perm.cansenddocs = false;
                peer.reaction_list = NULL;
                peer.chat_users = NULL;

                global_chat_search_results.push_back(
                    peer
                );

                diag_log(
                    "chat v84 global forward user parsed id=%016I64X",
                    chat_v84_forward_target_id
                );
            } else {
                global_chat_search_free_result(
                    &peer
                );
            }

            break;
        }
    }

    diag_log(
        "chat v84 global search parsed peers=%d",
        (int)global_chat_search_results.size()
    );

    global_chat_search_rebuild_combo();

    if (chat_v84_forward_search_pending) {
        int combo_index = 0;

        for (
            int i = 0;
            i < (int)global_chat_search_results.size();
            i++
        ) {
            Peer* peer =
                &global_chat_search_results[i];

            if (!peer->name || !peer->name[0])
                continue;

            if (
                peer->type ==
                    chat_v84_forward_target_type &&
                (unsigned __int64)read_le(
                    peer->id,
                    8
                ) ==
                    chat_v84_forward_target_id
            ) {
                SendMessage(
                    hComboBoxChats,
                    CB_SETCURSEL,
                    combo_index,
                    0
                );

                chat_v84_forward_search_pending =
                    false;

                diag_log(
                    "chat v84 forward origin global match type=%d id=%016I64X",
                    peer->type,
                    chat_v84_forward_target_id
                );

                PostMessage(
                    hMain,
                    WM_COMMAND,
                    MAKEWPARAM(
                        3,
                        CBN_SELCHANGE
                    ),
                    (LPARAM)hComboBoxChats
                );

                break;
            }

            combo_index++;
        }
    }

    '''

search_func = (
    search_func[:final_rebuild] +
    forward_finish +
    search_func[final_return:]
)

s = s[:gs] + search_func + s[ge:]


# Handle private telelegacy-peer target in the existing EN_LINK path.
link_match = (
    "if (links[i].chrg.cpMin == pENLink->chrg.cpMin && "
    "links[i].chrg.cpMax == pENLink->chrg.cpMax) {"
)

link_pos = s.find(link_match)
if link_pos < 0:
    raise SystemExit(
        "Could not locate existing RichEdit links range match."
    )

link_body_pos = (
    link_pos + len(link_match)
)

link_private = r'''
						if (
							links[i].lpstrText &&
							_wcsnicmp(
								links[i].lpstrText,
								L"telegacy-peer:",
								14
							) == 0
						) {
							int target_type = -1;
							unsigned __int64 target_id = 0;

							if (
								swscanf(
									links[i].lpstrText + 14,
									L"%d:%I64X",
									&target_type,
									&target_id
								) == 2
							) {
								int chars =
									pENLink->chrg.cpMax -
									pENLink->chrg.cpMin;

								if (chars < 0)
									chars = 0;
								if (chars > 255)
									chars = 255;

								wchar_t display_name[256] = {0};

								TEXTRANGE forward_name;
								forward_name.chrg =
									pENLink->chrg;
								forward_name.lpstrText =
									display_name;

								SendMessageW(
									chat,
									EM_GETTEXTRANGE,
									0,
									(LPARAM)&forward_name
								);

								display_name[chars] = 0;

								if (
									!chat_v84_open_forward_origin(
										target_type,
										target_id,
										display_name
									)
								) {
									MessageBeep(
										MB_ICONASTERISK
									);
								}
							}

							found = true;
							break;
						}
'''

s = (
    s[:link_body_pos] +
    link_private +
    s[link_body_pos:]
)

write(t, s)


checks = {
    t: [
        "chat_media_stickers_forward_links_v84",
        "chat v84 ambiguous native replace skipped",
        'L".webp"',
        "media_chat_sticker_load_webp_v84",
        "sticker_cp = document->min",
        "chat_v84_open_forward_origin",
        "chat v84 forward origin global match",
        "chat v84 global search parsed peers=",
        'L"telegacy-peer:"',
    ],
    hp: [
        "chat v84 forward origin link",
        'L"telegacy-peer:%d:%016I64X"',
    ],
}

for path, tokens in checks.items():
    data = read(path)
    for token in tokens:
        if token not in data:
            raise SystemExit(
                f"v8.4 verification failed in {path.name}: {token}"
            )

print(
    "Applied v8.4: ambiguous asynchronous bitmap replacements are skipped to "
    "prevent neighbour-media duplication; static WebP sticker originals are "
    "downloaded/rendered and TGS/WebM overlays can anchor to their placeholder "
    "when no thumbnail OLE exists; forwarded-from names are RichEdit links that "
    "open loaded peers directly or resolve exact channels/users through global "
    "Telegram search."
)
