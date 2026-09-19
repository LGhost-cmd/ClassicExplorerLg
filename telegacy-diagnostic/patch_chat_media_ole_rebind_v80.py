#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("Usage: patch_chat_media_ole_rebind_v80.py <Telegacy source directory>")

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

if "chat_media_ole_rebind_v80" in s:
    print("Chat media OLE rebind v8.0 already applied.")
    raise SystemExit(0)

for token in (
    "chat_global_peer_photo_hit_v79",
    "chat_photo_click_download_v78",
    "media_chat_v79_clicked_photo_document",
):
    if token not in s:
        raise SystemExit(f"Required predecessor marker missing: {token}")

start, end = function_range(
    s,
    "static int media_chat_v79_clicked_photo_document("
)

replacement = r'''// chat_media_ole_rebind_v80
static bool media_chat_v80_is_bitmap_ole(
    IRichEditOle* ole,
    LONG index,
    REOBJECT* out_reo
) {
    if (!ole)
        return false;

    REOBJECT reo = {0};
    reo.cbStruct = sizeof(reo);

    if (
        FAILED(
            ole->GetObject(
                index,
                &reo,
                REO_GETOBJ_POLEOBJ
            )
        ) ||
        !reo.poleobj
    ) {
        return false;
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

    if (bitmap && out_reo)
        *out_reo = reo;

    return bitmap;
}

static int media_chat_v80_clicked_bitmap_cp(
    POINT point,
    std::vector<int>* bitmap_cps,
    int* clicked_rank
) {
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

    std::vector<int> cps;

    LONG object_count =
        ole->GetObjectCount();

    for (
        LONG i = 0;
        i < object_count;
        i++
    ) {
        REOBJECT reo = {0};

        if (
            !media_chat_v80_is_bitmap_ole(
                ole,
                i,
                &reo
            )
        ) {
            continue;
        }

        cps.push_back(
            (int)reo.cp
        );
    }

    ole->Release();

    // RichEdit normally enumerates in character order, but do not depend on it.
    for (
        int i = 0;
        i < (int)cps.size();
        i++
    ) {
        for (
            int j = i + 1;
            j < (int)cps.size();
            j++
        ) {
            if (cps[j] < cps[i]) {
                int temp = cps[i];
                cps[i] = cps[j];
                cps[j] = temp;
            }
        }
    }

    if (bitmap_cps)
        *bitmap_cps = cps;

    int effective_dpi =
        dpi > 0
            ? dpi
            : 96;

    int card_width =
        MulDiv(
            288,
            effective_dpi,
            96
        );

    int card_height =
        MulDiv(
            216,
            effective_dpi,
            96
        );

    for (
        int rank = 0;
        rank < (int)cps.size();
        rank++
    ) {
        POINTL origin = {0, 0};

        if (
            SendMessageW(
                chat,
                EM_POSFROMCHAR,
                (WPARAM)&origin,
                (LPARAM)cps[rank]
            ) == -1
        ) {
            continue;
        }

        RECT card = {
            (LONG)origin.x,
            (LONG)origin.y,
            (LONG)origin.x + card_width,
            (LONG)origin.y + card_height
        };

        if (
            PtInRect(
                &card,
                point
            )
        ) {
            if (clicked_rank)
                *clicked_rank = rank;

            return cps[rank];
        }
    }

    // Fallback for RichEdit builds whose bitmap origin is reported oddly:
    // resolve the character under the cursor to the nearest bitmap object.
    LRESULT raw_hit =
        SendMessageW(
            chat,
            EM_CHARFROMPOS,
            0,
            (LPARAM)&point
        );

    if (raw_hit >= 0 && !cps.empty()) {
        int hit_char =
            (int)raw_hit;

        int best_rank = -1;
        int best_distance = INT_MAX;

        for (
            int rank = 0;
            rank < (int)cps.size();
            rank++
        ) {
            int distance =
                cps[rank] >= hit_char
                    ? cps[rank] - hit_char
                    : hit_char - cps[rank];

            if (distance < best_distance) {
                best_distance = distance;
                best_rank = rank;
            }
        }

        if (
            best_rank >= 0 &&
            best_distance <= 4
        ) {
            if (clicked_rank)
                *clicked_rank = best_rank;

            return cps[best_rank];
        }
    }

    return -1;
}

static int media_chat_v80_bind_bitmap_to_document(
    int clicked_cp,
    int clicked_rank,
    const std::vector<int>& bitmap_cps
) {
    if (clicked_cp < 0)
        return -1;

    std::vector<int> doc_indices;

    for (
        int i = 0;
        i < (int)documents.size();
        i++
    ) {
        Document* document =
            &documents[i];

        // photo_size==0 is a textual file attachment. Every non-zero visible
        // Document is represented by a bitmap OLE when its media is visible:
        // 1=sticker/special, 3=video thumbnail, other values=photo size chars.
        if (
            !document->visible ||
            !document->file_reference ||
            document->photo_size == 0
        ) {
            continue;
        }

        doc_indices.push_back(i);
    }

    // Keep the document rank tied to RichEdit text order even when min/max have
    // drifted by thousands of characters after repeated history prepends.
    for (
        int i = 0;
        i < (int)doc_indices.size();
        i++
    ) {
        for (
            int j = i + 1;
            j < (int)doc_indices.size();
            j++
        ) {
            if (
                documents[doc_indices[j]].min <
                documents[doc_indices[i]].min
            ) {
                int temp = doc_indices[i];
                doc_indices[i] = doc_indices[j];
                doc_indices[j] = temp;
            }
        }
    }

    // First accept an actually-near document. This preserves the proven path
    // for chats whose ranges are still synchronized.
    int best = -1;
    int best_distance = INT_MAX;

    for (
        int rank = 0;
        rank < (int)doc_indices.size();
        rank++
    ) {
        int index =
            doc_indices[rank];

        Document* document =
            &documents[index];

        int distance = 0;

        if (clicked_cp < document->min) {
            distance =
                document->min - clicked_cp;
        } else if (clicked_cp > document->max) {
            distance =
                clicked_cp - document->max;
        }

        if (distance < best_distance) {
            best_distance = distance;
            best = index;
        }
    }

    if (
        best >= 0 &&
        best_distance <= 96
    ) {
        int old_min =
            documents[best].min;

        int old_max =
            documents[best].max;

        documents[best].min =
            clicked_cp;

        documents[best].max =
            clicked_cp + 1;

        diag_log(
            "chat v80 OLE direct rebind cp=%d document=%d old=%d..%d distance=%d bitmaps=%d docs=%d",
            clicked_cp,
            best,
            old_min,
            old_max,
            best_distance,
            (int)bitmap_cps.size(),
            (int)doc_indices.size()
        );

        return best;
    }

    // The diagnostic log shows drift of 1000-2600 characters while the visible
    // OLE itself is correct. When bitmap OLE and visual Document counts agree,
    // their ordinal position is the stable identity we can trust.
    if (
        clicked_rank >= 0 &&
        clicked_rank < (int)bitmap_cps.size() &&
        bitmap_cps.size() == doc_indices.size() &&
        clicked_rank < (int)doc_indices.size()
    ) {
        int index =
            doc_indices[clicked_rank];

        int old_min =
            documents[index].min;

        int old_max =
            documents[index].max;

        documents[index].min =
            clicked_cp;

        documents[index].max =
            clicked_cp + 1;

        diag_log(
            "chat v80 OLE ordinal rebind cp=%d rank=%d/%d document=%d old=%d..%d",
            clicked_cp,
            clicked_rank,
            (int)bitmap_cps.size(),
            index,
            old_min,
            old_max
        );

        return index;
    }

    // If one or two media placeholders have not materialized yet, use a
    // proportional ordinal only when it still points to a valid visual
    // Document. This is preferable to the old arbitrary character-distance
    // cutoff and remains deterministic.
    int bitmap_count =
        (int)bitmap_cps.size();

    int doc_count =
        (int)doc_indices.size();

    int count_gap =
        bitmap_count >= doc_count
            ? bitmap_count - doc_count
            : doc_count - bitmap_count;

    if (
        clicked_rank >= 0 &&
        bitmap_count > 0 &&
        doc_count > 0 &&
        count_gap <= 2
    ) {
        int mapped_rank = 0;

        if (
            bitmap_count > 1 &&
            doc_count > 1
        ) {
            mapped_rank =
                (
                    clicked_rank *
                    (doc_count - 1) +
                    (bitmap_count - 1) / 2
                ) /
                (bitmap_count - 1);
        }

        if (mapped_rank < 0)
            mapped_rank = 0;
        if (mapped_rank >= doc_count)
            mapped_rank = doc_count - 1;

        int index =
            doc_indices[mapped_rank];

        int old_min =
            documents[index].min;

        int old_max =
            documents[index].max;

        documents[index].min =
            clicked_cp;

        documents[index].max =
            clicked_cp + 1;

        diag_log(
            "chat v80 OLE proportional rebind cp=%d bitmap_rank=%d/%d doc_rank=%d/%d document=%d old=%d..%d",
            clicked_cp,
            clicked_rank,
            bitmap_count,
            mapped_rank,
            doc_count,
            index,
            old_min,
            old_max
        );

        return index;
    }

    diag_log(
        "chat v80 OLE rebind failed cp=%d rank=%d bitmaps=%d docs=%d nearest=%d",
        clicked_cp,
        clicked_rank,
        bitmap_count,
        doc_count,
        best_distance
    );

    return -1;
}

static int media_chat_v79_clicked_photo_document(
    POINT point
) {
    std::vector<int> bitmap_cps;

    int clicked_rank = -1;

    int clicked_cp =
        media_chat_v80_clicked_bitmap_cp(
            point,
            &bitmap_cps,
            &clicked_rank
        );

    if (clicked_cp < 0) {
        diag_log(
            "chat v80 no bitmap OLE under click"
        );

        return -1;
    }

    int document_index =
        media_chat_v80_bind_bitmap_to_document(
            clicked_cp,
            clicked_rank,
            bitmap_cps
        );

    if (
        document_index < 0 ||
        document_index >= (int)documents.size()
    ) {
        return -1;
    }

    // Leave video and sticker/special OLEs to their existing handlers.
    if (
        documents[document_index].photo_size == 3 ||
        documents[document_index].photo_size == 1
    ) {
        diag_log(
            "chat v80 bitmap belongs to non-photo document=%d type=%d",
            document_index,
            (int)documents[document_index].photo_size
        );

        return -1;
    }

    diag_log(
        "chat v80 photo OLE mapped cp=%d rank=%d document=%d range=%d..%d size=%c",
        clicked_cp,
        clicked_rank,
        document_index,
        documents[document_index].min,
        documents[document_index].max,
        documents[document_index].photo_size
    );

    return document_index;
}'''

s = s[:start] + replacement + s[end:]

write(t, s)

checks = [
    "chat_media_ole_rebind_v80",
    "media_chat_v80_is_bitmap_ole",
    "QueryGetData",
    "CF_BITMAP",
    "chat v80 OLE ordinal rebind",
    "chat v80 photo OLE mapped",
]

data = read(t)
for token in checks:
    if token not in data:
        raise SystemExit(f"v8.0 verification failed in telegacy.cpp: {token}")

print(
    "Applied chat media OLE rebind v8.0: clicks enumerate only real CF_BITMAP "
    "RichEdit media objects, bind them to visual Documents by stable ordinal "
    "when stale min/max ranges have drifted, repair the clicked Document range "
    "before the full-photo request, and leave video/sticker OLEs to their own "
    "handlers."
)
