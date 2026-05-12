"""Replace 6.3 software section in SON HALİ docx with the complete v3 version.

Keeps everything else (1-6.2, KAYNAKLAR title, EKLER) untouched.
Properly remaps image relationship IDs so embedded figures travel with the copy.
"""
from copy import deepcopy
from io import BytesIO
from pathlib import Path

from docx import Document
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml.ns import qn

SRC_FINAL = Path(r"C:\Users\ASUS\OneDrive\Desktop\SON HALİ DTR (EKSİK VAR).docx")
SRC_V3 = Path(r"C:\Users\ASUS\OneDrive\Desktop\dtr_6_3_yazilim_birlesik_v3.docx")
OUT = Path(r"C:\Users\ASUS\OneDrive\Desktop\SON HALİ DTR (yazilim birlesik).docx")


def para_text(el):
    if el.tag != qn("w:p"):
        return ""
    return "".join(t.text or "" for t in el.iter(qn("w:t"))).strip()


def find_section_bounds(body_children, start_prefix, end_prefixes):
    start = end = None
    for i, el in enumerate(body_children):
        text = para_text(el)
        if start is None and text.startswith(start_prefix):
            start = i
        elif start is not None and any(text.startswith(p) for p in end_prefixes):
            end = i
            break
    if end is None:
        end = len(body_children)
    return start, end


STYLE_ID_MAP = {
    "Balk1": "Heading1",
    "Balk2": "Heading2",
    "Balk3": "Heading3",
    "Balk4": "Heading4",
    "Balk5": "Heading5",
    "Balk6": "Heading6",
    "Balk7": "Heading7",
    "Balk8": "Heading8",
    "Balk9": "Heading9",
    "KonuBal": "Title",
    "Altyaz": "Subtitle",
    "ListeParagraf": "ListParagraph",
}


def remap_style_ids(new_element):
    """Rewrite Turkish style IDs (v3) to English IDs used by SON HALİ."""
    for ps in new_element.iter(qn("w:pStyle")):
        old = ps.get(qn("w:val"))
        if old in STYLE_ID_MAP:
            ps.set(qn("w:val"), STYLE_ID_MAP[old])
    for rs in new_element.iter(qn("w:rStyle")):
        old = rs.get(qn("w:val"))
        if old in STYLE_ID_MAP:
            rs.set(qn("w:val"), STYLE_ID_MAP[old])
    for ts in new_element.iter(qn("w:tblStyle")):
        old = ts.get(qn("w:val"))
        if old in STYLE_ID_MAP:
            ts.set(qn("w:val"), STYLE_ID_MAP[old])


def remap_image_rids(new_element, src_part, dst_part, rid_cache):
    """Walk new_element for a:blip refs; copy image bytes into dst with fresh partnames."""
    for blip in new_element.iter(qn("a:blip")):
        old_rid = blip.get(qn("r:embed"))
        if not old_rid:
            continue
        if old_rid not in rid_cache:
            src_image_part = src_part.related_parts[old_rid]
            image_bytes = src_image_part.blob
            new_image_part = dst_part.package.image_parts.get_or_add_image_part(BytesIO(image_bytes))
            new_rid = dst_part.relate_to(new_image_part, RT.IMAGE)
            rid_cache[old_rid] = new_rid
        blip.set(qn("r:embed"), rid_cache[old_rid])


def main():
    final = Document(str(SRC_FINAL))
    v3 = Document(str(SRC_V3))

    final_body = final.element.body
    v3_body = v3.element.body

    final_children = list(final_body.iterchildren())
    v3_children = list(v3_body.iterchildren())

    f_start, f_end = find_section_bounds(
        final_children, "6.3 Yazılım", ["KAYNAKLAR", "EKLER", "7.", "8.", "9."]
    )
    v_start, v_end = find_section_bounds(
        v3_children, "6.3 Yazılım", ["KAYNAKLAR"]
    )
    if f_start is None or v_start is None:
        raise SystemExit(f"Could not find 6.3 boundaries: final={f_start},{f_end} v3={v_start},{v_end}")

    print(f"final 6.3: children[{f_start}:{f_end}]  ({f_end - f_start} elements)")
    print(f"v3    6.3: children[{v_start}:{v_end}]  ({v_end - v_start} elements)")

    anchor = final_children[f_end]  # element to insert before (KAYNAKLAR or first post-6.3)
    print(f"insertion anchor: <{anchor.tag.split('}')[-1]}> '{para_text(anchor)[:60]}'")

    # Remove old 6.3
    for el in final_children[f_start:f_end]:
        final_body.remove(el)

    # Copy v3 6.3 elements before the anchor
    rid_cache = {}
    inserted = 0
    for el in v3_children[v_start:v_end]:
        new_el = deepcopy(el)
        remap_style_ids(new_el)
        remap_image_rids(new_el, v3.part, final.part, rid_cache)
        anchor.addprevious(new_el)
        inserted += 1

    print(f"inserted {inserted} elements; remapped {len(rid_cache)} image rels")

    final.save(str(OUT))
    print(f"saved -> {OUT}")


if __name__ == "__main__":
    main()
