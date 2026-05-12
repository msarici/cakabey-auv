"""Final structural cleanup pass — fixes mechanical/electronic-area issues
that the team hasn't addressed.

Fixes:
1. Insert "2.1 Takım Üyeleri" heading before member list (paragraph 17 area)
2. Promote 6.1.1 from normal to Heading 3
3. Remove stray "." paragraph (line 64)
4. Strip extra whitespace from all heading text
5. Collapse runs of consecutive empty paragraphs in section 4 (8 empties → 2)

Does NOT touch list-intro paragraphs ("Ana döngünün akışı:", etc.) — those are
correct as normal style.
"""
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

SRC = Path(r"C:\Users\ASUS\OneDrive\Desktop\SON HALİ DTR (final).docx")
OUT = Path(r"C:\Users\ASUS\OneDrive\Desktop\SON HALİ DTR (final v2).docx")


def para_text(el):
    if el.tag != qn("w:p"):
        return ""
    return "".join(t.text or "" for t in el.iter(qn("w:t"))).strip()


def set_pstyle(p_element, style_id):
    pPr = p_element.find(qn("w:pPr"))
    if pPr is None:
        pPr = OxmlElement("w:pPr")
        p_element.insert(0, pPr)
    for ps in pPr.findall(qn("w:pStyle")):
        pPr.remove(ps)
    pStyle = OxmlElement("w:pStyle")
    pStyle.set(qn("w:val"), style_id)
    pPr.insert(0, pStyle)


def make_heading(text, style_id):
    p = OxmlElement("w:p")
    pPr = OxmlElement("w:pPr")
    pStyle = OxmlElement("w:pStyle")
    pStyle.set(qn("w:val"), style_id)
    pPr.append(pStyle)
    p.append(pPr)
    r = OxmlElement("w:r")
    t = OxmlElement("w:t")
    t.text = text
    t.set(qn("xml:space"), "preserve")
    r.append(t)
    p.append(r)
    return p


def main():
    doc = Document(str(SRC))
    body = doc.element.body

    # ---- 1. Strip whitespace from all heading text ----
    children = list(body.iterchildren())
    stripped = 0
    for el in children:
        if el.tag != qn("w:p"):
            continue
        pPr = el.find(qn("w:pPr"))
        if pPr is None:
            continue
        ps = pPr.find(qn("w:pStyle"))
        if ps is None or not ps.get(qn("w:val"), "").startswith("Heading"):
            continue
        # Collect all w:t text and trim leading/trailing whitespace + collapse double spaces
        runs = list(el.iter(qn("w:t")))
        if not runs:
            continue
        full = "".join(t.text or "" for t in runs)
        cleaned = " ".join(full.split())  # collapse all whitespace runs to single space
        if full != cleaned:
            # Put cleaned text into first run, blank others
            runs[0].text = cleaned
            for t in runs[1:]:
                t.text = ""
            stripped += 1
    print(f"  stripped whitespace from {stripped} heading(s)")

    # ---- 2. Promote 6.1.1 from normal to Heading 3 ----
    children = list(body.iterchildren())
    for el in children:
        if el.tag != qn("w:p"):
            continue
        if para_text(el).startswith("6.1.1") and "Mekanik Özet" in para_text(el):
            set_pstyle(el, "Heading3")
            print(f"  6.1.1 promoted to Heading 3")
            break

    # ---- 3. Remove stray "." paragraph ----
    children = list(body.iterchildren())
    removed = 0
    for el in children:
        if el.tag != qn("w:p"):
            continue
        if para_text(el) == ".":
            body.remove(el)
            removed += 1
    print(f"  removed {removed} stray '.' paragraph(s)")

    # ---- 4. Insert "2.1 Takım Üyeleri" heading before member list ----
    # Find the first member paragraph (paragraph starting with "Dr. Öğr. Üyesi İbrahim Şafak")
    children = list(body.iterchildren())
    for el in children:
        if el.tag != qn("w:p"):
            continue
        text = para_text(el)
        if text.startswith("Dr. Öğr. Üyesi İbrahim Şafak"):
            new_h = make_heading("2.1 Takım Üyeleri", "Heading2")
            el.addprevious(new_h)
            print(f"  inserted '2.1 Takım Üyeleri' heading")
            break

    # ---- 5. Collapse excessive empty paragraphs in section 4 ----
    # Find consecutive empty paragraphs between section 4 and section 5; keep at most 2
    children = list(body.iterchildren())
    in_sec4 = False
    consecutive_empty = []
    removed_empty = 0
    for el in list(body.iterchildren()):
        if el.tag != qn("w:p"):
            continue
        text = para_text(el)
        if text.startswith("4. İŞ AKIŞ"):
            in_sec4 = True
            continue
        if in_sec4 and text.startswith("5. KAYNAK"):
            # Process collected empties — keep first 2, remove rest
            if len(consecutive_empty) > 2:
                for emp in consecutive_empty[2:]:
                    body.remove(emp)
                    removed_empty += 1
            in_sec4 = False
            consecutive_empty = []
            continue
        if in_sec4:
            if not text:
                consecutive_empty.append(el)
            else:
                consecutive_empty = []  # reset on non-empty
    print(f"  removed {removed_empty} excess empty paragraphs in section 4")

    doc.save(str(OUT))
    print(f"\nsaved -> {OUT}")


if __name__ == "__main__":
    main()
