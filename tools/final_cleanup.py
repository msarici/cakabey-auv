"""Final structural cleanup of the consolidated DTR docx.

Fixes:
1. 6.2 / 6.3 demoted from Heading 1 to Heading 2
2. 6.1.2 / 6.1.4 promoted from normal to Heading 3
3. Empty Heading 3 paragraph removed
4. "3.ÖTR" → "3. ÖTR" cosmetic spacing
5. 10. BÜTÇE placeholder section inserted (currently missing — no software content)
6. KAYNAKLAR + references moved to end (after 11. ÖZGÜNLÜK, before EKLER)

Final order: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 → KAYNAKLAR → EKLER
"""
from copy import deepcopy
from pathlib import Path

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from insert_references_and_originality import find_anchor, make_paragraph

SRC = Path(r"C:\Users\ASUS\OneDrive\Desktop\SON HALİ DTR (7-9 + 11 + kaynaklar).docx")
OUT = Path(r"C:\Users\ASUS\OneDrive\Desktop\SON HALİ DTR (final).docx")


def para_text(el):
    if el.tag != qn("w:p"):
        return ""
    return "".join(t.text or "" for t in el.iter(qn("w:t"))).strip()


def set_pstyle(p_element, style_id):
    """Force paragraph style to given style id."""
    pPr = p_element.find(qn("w:pPr"))
    if pPr is None:
        pPr = OxmlElement("w:pPr")
        p_element.insert(0, pPr)
    for ps in pPr.findall(qn("w:pStyle")):
        pPr.remove(ps)
    pStyle = OxmlElement("w:pStyle")
    pStyle.set(qn("w:val"), style_id)
    pPr.insert(0, pStyle)


def find_para_by_exact(children, text):
    for i, el in enumerate(children):
        if el.tag == qn("w:p") and para_text(el) == text:
            return i, el
    return None, None


def find_para_by_prefix(children, prefix):
    for i, el in enumerate(children):
        if el.tag == qn("w:p") and para_text(el).startswith(prefix):
            return i, el
    return None, None


# 10. Bütçe placeholder content
BUTCE = [
    ("10. BÜTÇE", "Heading1", None),
    (None, "Normal",
     "Çakabey AUV projesinin bütçe planlaması, ÖTR sonrası yapılan donanım "
     "revizyonları (itki sistemi yerlileştirmesi, sensör mimarisi optimizasyonu) "
     "ışığında güncellenmiştir. Detaylı kalem bazında bütçe tablosu ve maliyet "
     "kırılımı, tedarik süreçlerini doğrudan yürüten mekanik ve elektronik takım "
     "üyeleri tarafından bu başlık altında sunulacaktır."),
    (None, "Normal",
     "Yazılım katmanı açısından lisans maliyeti bulunmamaktadır: kullanılan tüm "
     "kütüphaneler ve çatılar (Python 3, OpenCV, NumPy, pymavlink, ABC algoritması, "
     "ArduPilot Sub) açık kaynaklı ve serbest kullanım lisanslarına sahiptir. "
     "Yazılım kalemi için ayrılması gereken bütçe sıfırdır; bu, projenin maliyet-etkin "
     "donanım vizyonuyla doğrudan uyumludur."),
]


def main():
    doc = Document(str(SRC))
    body = doc.element.body
    children = list(body.iterchildren())

    # ---- 1. Heading hierarchy fixes ----
    fixes_h1_to_h2 = [
        "6.2 Elektronik Sistem Mimarisi ve Güç Dağıtımı:",
        "6.3 Yazılım, Otonomi ve Algoritma Mimarisi",
    ]
    fixes_normal_to_h3 = [
        "6.1.2 Temel Mekanik Tasarım ve Malzeme Seçimleri",
        "6.1.4 İleri Mühendislik Analizleri",
    ]

    for text in fixes_h1_to_h2:
        idx, el = find_para_by_exact(children, text)
        if el is not None:
            set_pstyle(el, "Heading2")
            print(f"  H1→H2: {text[:50]}")
        else:
            print(f"  WARN: not found: {text[:50]}")

    for text in fixes_normal_to_h3:
        idx, el = find_para_by_exact(children, text)
        if el is not None:
            set_pstyle(el, "Heading3")
            print(f"  normal→H3: {text[:50]}")
        else:
            print(f"  WARN: not found: {text[:50]}")

    # ---- 2. Remove empty Heading 3 ----
    removed_empty = 0
    for el in list(body.iterchildren()):
        if el.tag != qn("w:p"):
            continue
        if para_text(el):
            continue
        pPr = el.find(qn("w:pPr"))
        if pPr is None:
            continue
        ps = pPr.find(qn("w:pStyle"))
        if ps is None:
            continue
        if ps.get(qn("w:val")) in ("Heading3", "Heading2", "Heading1"):
            body.remove(el)
            removed_empty += 1
    print(f"  removed {removed_empty} empty heading(s)")

    # ---- 3. Cosmetic: "3.ÖTR" → "3. ÖTR" ----
    children = list(body.iterchildren())  # refresh
    idx, el = find_para_by_exact(children, "3.ÖTR SONRASI YAPILAN DEĞİŞİKLİKLER VE İYİLEŞTİRMELER")
    if el is not None:
        # Find text run and rewrite
        for t in el.iter(qn("w:t")):
            if t.text and "3.ÖTR" in t.text:
                t.text = t.text.replace("3.ÖTR", "3. ÖTR")
                print(f"  cosmetic: 3.ÖTR → 3. ÖTR")
                break

    # ---- 4. Move KAYNAKLAR + references after 11. ÖZGÜNLÜK (before EKLER) ----
    # Do this BEFORE inserting 10. BÜTÇE, otherwise BÜTÇE gets swept along with KAYNAKLAR.
    children = list(body.iterchildren())
    kayn_idx, kayn_el = find_para_by_exact(children, "KAYNAKLAR")
    oz_idx, oz_el = find_para_by_exact(children, "11. ÖZGÜNLÜK")
    ekler_idx, ekler_el = find_para_by_exact(children, "EKLER (Var ise)")

    if kayn_el is None or oz_el is None or ekler_el is None:
        raise SystemExit(f"Anchors not found: kayn={kayn_idx} oz={oz_idx} ekler={ekler_idx}")

    # Range to move: [kayn_idx, oz_idx) — KAYNAKLAR title + 13 refs (everything before 11. ÖZGÜNLÜK)
    to_move = children[kayn_idx:oz_idx]
    print(f"  moving {len(to_move)} elements (KAYNAKLAR block) from {kayn_idx} to before EKLER ({ekler_idx})")

    # Detach
    for el in to_move:
        body.remove(el)

    # Re-insert before EKLER
    for el in to_move:
        ekler_el.addprevious(el)

    # ---- 5. Insert 10. BÜTÇE before 11. ÖZGÜNLÜK (now that KAYNAKLAR is out of the way) ----
    children = list(body.iterchildren())
    oz_idx, oz_el = find_para_by_exact(children, "11. ÖZGÜNLÜK")
    if oz_el is None:
        raise SystemExit("11. ÖZGÜNLÜK not found after move")

    inserted_butce = 0
    for text, style, body_text in BUTCE:
        content = text if text is not None else body_text
        new_p = make_paragraph(content, style)
        oz_el.addprevious(new_p)
        inserted_butce += 1
    print(f"  inserted {inserted_butce} paragraphs for 10. BÜTÇE")

    # ---- Save ----
    doc.save(str(OUT))
    print(f"\nsaved -> {OUT}")


if __name__ == "__main__":
    main()
