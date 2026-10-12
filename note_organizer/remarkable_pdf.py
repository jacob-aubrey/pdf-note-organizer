"""Turn downloaded PDF stroke layers into a separate, annotated PDF.

The original PDF and cloud data are never rewritten. v6 scenes are read with
rmscene. Unknown page formats fail closed instead of dropping annotations.
"""
from io import BytesIO
import json
import math

import fitz


RENDER_REVISION = 3


class UnsupportedAnnotations(ValueError):
    pass


def page_map(content, pdf_pages):
    if "cPages" in content:
        page_collection = content["cPages"]
        pages = page_collection.get("pages") if isinstance(page_collection, dict) else None
        if not isinstance(pages, list):
            raise UnsupportedAnnotations("Unsupported PDF page map")
        if any(not isinstance(p, dict) for p in pages):
            raise UnsupportedAnnotations("Invalid PDF page record")
        pages = [p for p in pages if not p.get("deleted", {}).get("value", False)]
        if any("idx" in p for p in pages):
            # Partial ordering data must not silently change source page positions.
            indexes = [p.get("idx", {}).get("value") if isinstance(p.get("idx"), dict) else None for p in pages]
            if any(not isinstance(index, str) or not index for index in indexes) or len(set(indexes)) != len(indexes):
                raise UnsupportedAnnotations("Incomplete or duplicate PDF page ordering")
            pages = sorted(pages, key=lambda p: p["idx"]["value"])
        result = [(p["id"], p.get("redir", {}).get("value", -1)) for p in pages]
    else:
        ids = content.get("pages", [])
        redirects = content.get("redirectionPageMap")
        if not ids:
            raise UnsupportedAnnotations("PDF has no page identifiers")
        if redirects is not None and len(redirects) != len(ids):
            raise UnsupportedAnnotations("Incomplete PDF page redirection map")
        result = [(pid, redirects[i] if redirects is not None else i) for i, pid in enumerate(ids)]
    if not result or any(not isinstance(pid, str) or not pid for pid, _ in result):
        raise UnsupportedAnnotations("Empty or invalid PDF page identifiers")
    if len({p[0] for p in result}) != len(result):
        raise UnsupportedAnnotations("Empty or duplicate PDF page identifiers")
    for _, index in result:
        if type(index) is not int or index < -1 or index >= pdf_pages:
            raise UnsupportedAnnotations("Invalid source PDF page reference")
    return result


COLORS = {0: (0, 0, 0), 1: (.5, .5, .5), 2: (1, 1, 1), 3: (1, .84, 0),
          4: (0, .63, 0), 5: (1, .41, .71), 6: (.25, .41, .88), 7: (.88, 0, 0),
          8: (.63, .63, .63), 9: (1, .84, 0), 10: (0, .75, 0),
          11: (0, .81, .82), 12: (1, 0, 1), 13: (1, .84, 0)}


def color(item):
    rgba = getattr(item, "color_rgba", None)
    # Older indexed highlights contain a black RGBA placeholder. Color 9 uses
    # RGBA as its actual color; legacy yellow/pink still use their palette index.
    if rgba and (int(item.color) == 9 or any(rgba[:3])):
        return tuple(v / 255 for v in rgba[:3])
    if int(item.color) not in COLORS:
        raise UnsupportedAnnotations("Unknown Paper Pro pen color")
    return COLORS[int(item.color)]


def scene(data):
    from rmscene import read_blocks
    from rmscene.scene_stream import (build_tree, UnreadableBlock, SceneItemBlock,
                                     SceneTextItemBlock, SceneTombstoneItemBlock)
    from rmscene.scene_tree import SceneTree
    if b"version=6" not in data[:43]:
        raise UnsupportedAnnotations("This annotation layer is not a supported v6 scene")
    blocks = list(read_blocks(BytesIO(data)))
    if any(isinstance(block, UnreadableBlock) for block in blocks):
        raise UnsupportedAnnotations("The PDF contains annotation blocks the reader cannot interpret")
    # Scene metadata extensions are retained in the source archive. Unknown
    # annotation fields or skipped items could lose marks, so require review.
    if any(isinstance(block, SceneItemBlock) and (block.extra_data or block.extra_value_data) for block in blocks):
        raise UnsupportedAnnotations("The PDF contains newer annotation fields the reader cannot interpret")
    if any(isinstance(block, (SceneTextItemBlock, SceneTombstoneItemBlock)) for block in blocks):
        raise UnsupportedAnnotations("The PDF contains annotation items the renderer cannot interpret")
    tree = SceneTree()
    build_tree(tree, blocks)
    return tree


def visible_items(group):
    from rmscene.scene_items import Group
    if not group.visible.value:
        return
    if group.anchor_id is not None:
        raise UnsupportedAnnotations("Text-anchored strokes require an additional layout adapter")
    sequence = {node.item_id: node for node in group.children.sequence_items()}
    for item_id in group.children:
        node = sequence[item_id]
        if node.deleted_length or node.value is None:
            continue
        if isinstance(node.value, Group):
            yield from visible_items(node.value)
        else:
            yield str(node.item_id), node.value


def stamp_id(document, annot, value):
    # Stable scene IDs keep annotation history stable across cloud updates.
    document.xref_set_key(annot.xref, "NM", fitz.get_pdf_str(value))


def apply_scene(document, page, page_id, tree, *, expand_margins=True):
    from rmscene.scene_items import Line, GlyphRange, Pen
    paper_size = getattr(tree.scene_info, "paper_size", None) or (1404, 1872)
    scale = {(1404, 1872): .3177, (1620, 2160): .3144}.get(tuple(paper_size))
    if scale is None:
        raise UnsupportedAnnotations(f"Unsupported annotation coordinate grid: {paper_size}")
    bounds = page.rect * page.derotation_matrix
    original_width, derotation = page.rect.width, page.derotation_matrix
    offset = fitz.Point(0, 0)

    def require_visible(rect):
        if (rect & bounds).is_empty:
            raise UnsupportedAnnotations("Tablet annotations fall outside the visible PDF page; tablet margins or coordinate calibration need review")

    # PDF stroke scenes are centered on the displayed PDF page's horizontal axis.
    # Convert displayed coordinates back to unrotated PDF annotation coordinates.
    def point(x, y):
        if not math.isfinite(x) or not math.isfinite(y):
            raise UnsupportedAnnotations("Invalid stroke coordinates")
        return fitz.Point(x * scale + original_width / 2, y * scale) * derotation + offset

    items = list(visible_items(tree.root))
    text = ""
    if tree.root_text:
        from rmscene.text import TextDocument
        text = "\n".join(str(p) for p in TextDocument.from_scene_item(tree.root_text).contents).strip()
    extent = fitz.Rect(bounds)
    for _, item in items:
        if isinstance(item, GlyphRange):
            for box in item.rectangles:
                rect = fitz.Rect(point(box.x, box.y), point(box.x + box.w, box.y + box.h))
                rect.normalize()
                padding = max(2, rect.height / 4)
                extent |= fitz.Rect(rect.x0 - padding, rect.y0 - padding,
                                    rect.x1 + padding, rect.y1 + padding)
        elif isinstance(item, Line):
            for pen_point in item.points:
                position = point(pen_point.x, pen_point.y)
                # Include the stroke's appearance, rather than only its centerline.
                extent |= fitz.Rect(position.x - 8, position.y - 8, position.x + 8, position.y + 8)
    if text:
        anchor = point(tree.root_text.pos_x, tree.root_text.pos_y)
        extent |= fitz.Rect(anchor.x, anchor.y, anchor.x + 20, anchor.y + 20)
    left, top, right, bottom = (math.ceil(max(0, value)) for value in
                               (bounds.x0 - extent.x0, bounds.y0 - extent.y0,
                                extent.x1 - bounds.x1, extent.y1 - bounds.y1))
    if left + right > bounds.width or top + bottom > bounds.height:
        raise UnsupportedAnnotations("Tablet annotations fall outside the supported PDF margin area; coordinate calibration needs review")
    if not expand_margins:
        # The combined reader first compares annotations in their original
        # coordinates, then expands the finished page once for both sources.
        # Use the validated planned canvas when checking visibility, so marks
        # wholly within an added margin remain available for that final step.
        bounds = extent
    elif any((left, top, right, bottom)):
        if page.rotation or page.cropbox != page.mediabox:
            raise UnsupportedAnnotations("Tablet margins on a rotated or cropped PDF page need an additional layout adapter")
        # Extend only the converted copy. PDF content and existing annotations
        # shift together; scene coordinates receive the same left/top offset.
        media = page.mediabox
        page.set_mediabox(fitz.Rect(media.x0 - left, media.y0 - bottom,
                                  media.x1 + right, media.y1 + top))
        offset = fitz.Point(left, top)
        bounds = page.rect

    for iid, item in items:
        annot = None
        if isinstance(item, GlyphRange):
            rects = []
            for box in item.rectangles:
                rect = fitz.Rect(point(box.x, box.y), point(box.x + box.w, box.y + box.h))
                rect.normalize()
                if rect.is_empty:
                    raise UnsupportedAnnotations("Invalid text highlight rectangle")
                rects.append(rect)
            if not rects:
                raise UnsupportedAnnotations("A text highlight has no page region")
            annot = page.add_highlight_annot(rects)
            annot.set_info(subject="reMarkable highlight")
            # Retain the selected quote without creating a viewer comment popup.
            document.xref_set_key(annot.xref, "RMQuote", fitz.get_pdf_str(item.text))
            # Dark highlight colors must remain translucent over printed text.
            annot.set_opacity(.35)
        elif isinstance(item, Line):
            if item.tool in {Pen.ERASER, Pen.ERASER_AREA}:
                raise UnsupportedAnnotations("An unresolved eraser stroke requires review")
            if not item.points:
                continue
            points = [point(p.x, p.y) for p in item.points]
            if len(points) == 1:
                points.append(points[0] + (.1, .1))
            annot = page.add_ink_annot([[tuple(p) for p in points]])
            width = sum(p.width for p in item.points) / len(points)
            width = max(.5, min(width * .8, 5)) * scale
            if Pen.is_highlighter(item.tool):
                width = max(10, min(sum(p.width for p in item.points) / len(points) * 2, 40)) * scale
                annot.set_opacity(.35)
                annot.set_blendmode("Multiply")
            annot.set_border(width=width)
            annot.set_info(subject="reMarkable pen")
        else:
            raise UnsupportedAnnotations("Unsupported annotation scene item")
        # Partially visible strokes remain intact; wholly invisible marks would
        # otherwise be skipped by the PDF extractor and disappear from Notes.
        require_visible(annot.rect)
        annot.set_colors(stroke=color(item))
        stamp_id(document, annot, "remarkable-" + page_id + "-" + iid)
        annot.update()
    if text:
        anchor = point(tree.root_text.pos_x, tree.root_text.pos_y)
        if not bounds.contains(anchor):
            raise UnsupportedAnnotations("A tablet text note falls outside the visible PDF page; tablet margins or coordinate calibration need review")
        annot = page.add_text_annot(anchor, text)
        annot.set_info(subject="reMarkable typed note")
        stamp_id(document, annot, "remarkable-" + page_id + "-text")
        annot.update()


def annotated_pdf(item, bundle, cancelled=lambda: False, *, expand_margins=True):
    content = json.loads(bundle[item.id + ".content"])
    if content.get("fileType") != "pdf":
        raise UnsupportedAnnotations("Only imported PDFs are supported")
    with fitz.open(stream=bundle[item.id + ".pdf"], filetype="pdf") as original, fitz.open() as output:
        if original.needs_pass:
            raise UnsupportedAnnotations("The source PDF is password protected")
        pages = page_map(content, len(original))
        known_layers = {item.id + "/" + pid + ".rm" for pid, _ in pages}
        if any(name.endswith(".rm") and name not in known_layers for name in bundle):
            raise UnsupportedAnnotations("Annotation layers exist outside the PDF's page map")
        known_highlights = {item.id + ".highlights/" + pid + ".json" for pid, _ in pages}
        if any(".highlights/" in name and name.endswith(".json") and name not in known_highlights for name in bundle):
            raise UnsupportedAnnotations("Highlight data exists outside the PDF's page map")
        labels = []
        for index, (pid, source_index) in enumerate(pages):
            if cancelled():
                raise InterruptedError("reMarkable PDF conversion stopped")
            data = bundle.get(item.id + "/" + pid + ".rm")
            tree = scene(data) if data else None
            if source_index >= 0:
                output.insert_pdf(original, from_page=source_index, to_page=source_index)
                label = original[source_index].get_label() or str(source_index + 1)
            else:
                size = getattr(tree.scene_info, "paper_size", None) if tree else None
                w, h = size or (1404, 1872)
                scale = .3144 if (w, h) == (1620, 2160) else .3177
                output.new_page(width=w * scale, height=h * scale)
                label = f"Added {index + 1}"
            labels.append({"startpage": index, "prefix": label, "style": ""})
            page = output[index]
            if tree:
                apply_scene(output, page, pid, tree, expand_margins=expand_margins)
            legacy = bundle.get(item.id + ".highlights/" + pid + ".json")
            if legacy:
                raise UnsupportedAnnotations("Legacy JSON highlights need an additional annotation adapter")
        output.set_page_labels(labels)
        metadata = dict(original.metadata)
        metadata["keywords"] = (metadata.get("keywords", "") + "; reMarkable imported PDF").strip("; ")
        output.set_metadata(metadata)
        return output.tobytes(garbage=4, deflate=True)
