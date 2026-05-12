"""Insert KAYNAKLAR references (from v3) and a new "11. ÖZGÜNLÜK" section
into the merged final docx, before EKLER.

Sources:
  - C:\\Users\\ASUS\\OneDrive\\Desktop\\SON HALİ DTR (yazilim birlesik).docx (base)
  - C:\\Users\\ASUS\\OneDrive\\Desktop\\dtr_6_3_yazilim_birlesik_v3.docx (refs)

Output:
  - C:\\Users\\ASUS\\OneDrive\\Desktop\\SON HALİ DTR (kaynaklar + ozgunluk).docx
"""
from copy import deepcopy
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

from merge_software_into_final import (
    STYLE_ID_MAP,
    remap_style_ids,
    para_text,
)

SRC_BASE = Path(r"C:\Users\ASUS\OneDrive\Desktop\SON HALİ DTR (yazilim birlesik).docx")
SRC_V3 = Path(r"C:\Users\ASUS\OneDrive\Desktop\dtr_6_3_yazilim_birlesik_v3.docx")
OUT = Path(r"C:\Users\ASUS\OneDrive\Desktop\SON HALİ DTR (kaynaklar + ozgunluk).docx")


# ---- Özgünlük section content (11.1 - 11.8) ----

OZGUNLUK = [
    ("11. ÖZGÜNLÜK", "Heading1", None),

    ("11.1 ABC Algoritmasının ROV Parametre Optimizasyonuna Uygulanması", "Heading2", None),
    (None, "Normal",
     "Çakabey AUV yazılım katmanının özgünlüğünün merkezinde, Erciyes Üniversitesi'nden "
     "Prof. Dr. Derviş Karaboğa tarafından 2005 yılında literatüre kazandırılan Yapay Arı "
     "Kolonisi (ABC — Artificial Bee Colony) algoritmasının iki ayrı mühendislik problemine "
     "somut olarak uygulanması yer almaktadır:"),
    (None, "Normal",
     "(a) Boru tespitinde HSV alt/üst sınırlarının IoU (Intersection over Union) metriğini "
     "maksimize edecek şekilde optimize edilmesi (abc_hsv.py + evaluator_hsv.py), ve "
     "(b) yaw kontrolcüsünün ITAE (Integral of Time-weighted Absolute Error) metriğini "
     "minimize edecek Kp/Ki/Kd üçlüsünün optimize edilmesi (abc_pid.py + evaluator_pid.py)."),
    (None, "Normal",
     "Bu uygulama, ulusal bir akademik üretimi (ABC) yerli bir AUV projesinde somut bir "
     "mühendislik probleminin çözümüne dönüştürmesi açısından önemlidir. Algoritmanın "
     "kendisi yeni değildir, ancak sürü zekası tabanlı global optimizasyonun ROV parametre "
     "uzayında — özellikle gradyanı tanımlanmamış HSV maskeleme problemine — uygulanması, "
     "literatürde bu kombinasyonun yaygın bir örneği olmaması nedeniyle özgün bir katkı "
     "olarak konumlandırılmaktadır."),

    ("11.2 Geçerli Çözüm Garantisi: (Merkez, Yarı-Genişlik) Parametrizasyonu", "Heading2", None),
    (None, "Normal",
     "HSV optimizasyonunda klasik (min, max) parametrizasyonu yerine (center, half_width) "
     "yapısı tercih edilmiştir. Bu, ABC tarafından üretilen rastgele her çözümün otomatik "
     "olarak min < max koşulunu sağlamasını garanti eder. Klasik parametrizasyonda ABC'nin "
     "ürettiği rastgele çözümlerin yaklaşık yarısında min > max ihlali oluşur ve bu çözümler "
     "için fitness değerlendirmesi anlamsızlaşır; sürü reddi (rejection sampling) gerekirse "
     "yakınsama ciddi şekilde yavaşlar. Önerilen parametrizasyon, ekstra reddetme mekanizması "
     "olmadan ABC'nin doğrudan geçerli çözüm uzayında dolaşmasını sağlar."),

    ("11.3 Warm-start ile Reprodüktibilite ve Jüri Doğrulanabilirliği", "Heading2", None),
    (None, "Normal",
     "ABC kolonisinin ilk çözümlerine config.yaml içindeki referans değerler enjekte "
     "edilmektedir (warm-start). Bu sayede algoritmanın ürettiği sonuç, mevcut konfigürasyonun "
     "altına asla düşmez; en kötü durumda referans çözüm korunur. Buna ek olarak rastgele "
     "sayı üreteci seed=42 ile sabitlenmiştir. Aynı kodu indiren herhangi bir hakem veya "
     "üçüncü taraf, aynı PID ve HSV sonuçlarını birebir üretebilir. Bu deterministik yapı, "
     "yarışma değerlendirmesinde sayısal iddiaların tekrarlanabilir kanıtla desteklenmesini "
     "mümkün kılar."),

    ("11.4 Anomali Pipeline'ında Yatay-Eğilimli Morfolojik Kapama", "Heading2", None),
    (None, "Normal",
     "Boru kopması (break) tespitinde 49×9 boyutunda yatay-eğilimli MORPH_CLOSE kerneli "
     "kullanılmaktadır. Pas (rust) ve yosun (algae) lekeleri, turuncu boru maskesi içinde "
     "küçük delikler oluşturur. Ham maske üzerinde kontur sayımı yapılırsa, bu küçük "
     "delikler yanlışlıkla \"ayrı kontur\" olarak değerlendirilir ve her pas/yosun durumu "
     "yanlış pozitif kopma raporu üretir. Yatay genişlikte (49 px) kernel ile uygulanan "
     "morfolojik kapama, bu küçük delikleri köprüler; gerçek bir boru kopması ise bu kernel "
     "boyutundan büyük bir boşluk yarattığı için kopma sonrası dahi iki ayrı büyük kontur "
     "olarak kalır. Bu kernel boyutu seçimi, sentetik dataset üzerinde test edilerek, "
     "anomali sınıfları arasındaki kafa karışıklığını minimize eden değer olarak "
     "belirlenmiştir."),

    ("11.5 Çatlak Bastırma Sıralaması (Conditional Crack Suppression)", "Heading2", None),
    (None, "Normal",
     "Aynı frame içinde hem kopma (break) hem çatlak (crack) tespit edildiğinde, çatlak "
     "tespiti bilinçli olarak bastırılmaktadır. Çatlak detektörü Canny kenar tespiti + "
     "Hough çizgi dönüşümü kullanır; ancak boru kopması durumunda kopma sınırındaki kenar "
     "pikselleri Hough'ta çizgi olarak yakalanır ve aynı fiziksel olay (kopma) iki ayrı "
     "anomali sınıfı (break + crack) olarak raporlanır. Önce break detektörünün çalışması, "
     "ardından break tespit edildiyse crack adımının atlanması, bu sahte ikili sınıflamayı "
     "engelleyen non-trivial bir sıralama kararıdır."),

    ("11.6 PID Anti-windup: Integral State Clamping ve time.monotonic()", "Heading2", None),
    (None, "Normal",
     "PID kontrolcüde anti-windup mekanizması olarak literatürdeki standart "
     "back-calculation yöntemi yerine integral değişkeninin doğrudan output_max / Ki "
     "(veya verilirse explicit integral_limit) ile clamp edilmesi tercih edilmiştir. Bu "
     "yaklaşımın özgünlüğü, evaluator_pid.py simülatörünün birebir aynı clamping mantığını "
     "uygulamasıdır: ABC'nin sentetik plant üzerinde bulduğu Kp/Ki/Kd üçlüsü, gerçek "
     "kontrolöre yeniden bir tune'lama gerektirmeden transfer edilebilir."),
    (None, "Normal",
     "Kontrolcüde dt hesaplaması için time.monotonic() kullanılmaktadır. Sistem saatinin "
     "(örneğin NTP senkronizasyonu) geriye sıçraması durumunda time.time() negatif dt "
     "üretebilir; bu PID için yıkıcıdır (integral patlar, türev anlık olarak sonsuza gider). "
     "time.monotonic() daima ileri yönlüdür ve bu sınıf hataları ortadan kaldırır."),

    ("11.7 FSM Histerezis: Bağımsız Frame Sayaçları", "Heading2", None),
    (None, "Normal",
     "SEARCH / APPROACH / TRACK / LOST durumları arasındaki geçişler, histerezis pencereleri "
     "yerine bağımsız frame sayaçları (found_count, lost_count) ile yönetilir. Tek bir "
     "hatalı tespit FSM'i APPROACH'a geçirmez (3 ardışık frame onayı gerekir); tek bir kayıp "
     "tespit FSM'i LOST'a geçirmez (30 ardışık frame zaman aşımı gerekir). Sayaçlar geçişte "
     "sıfırlanır; bu yapı klasik eşik etrafındaki \"jitter zone\" sorununu ortadan kaldırır. "
     "Tüm eşikler config.yaml > fsm altında değiştirilebilir, bu da hakem isteğiyle veya "
     "havuz testinde kolayca yeniden ayarlanmaya açıktır."),

    ("11.8 Deterministik Sentetik Dataset Tasarımı", "Heading2", None),
    (None, "Normal",
     "evaluator_hsv.py ve evaluator_anomaly.py modüllerinde sentetik dataset üretimi, "
     "frame index'e bağlı arka plan tonu ve distractor yerleşimi kullanır; time.time() "
     "veya başka deterministik olmayan bir kaynağa bağlı değildir. seed=42 ile sabitlenmiş "
     "RNG sayesinde aynı 20 frame her koşuda aynı sırada üretilir, ABC fitness "
     "değerlendirmesi koşular arasında karşılaştırılabilir hale gelir. Bu deterministik "
     "altyapı olmadan, ABC'nin ürettiği farklı çözümlerin gerçekten daha iyi olup olmadığı "
     "değerlendirilemez (gürültü tohumu farklılaştığında fitness değişir, sebep-sonuç "
     "ayırt edilemez)."),

    ("11.9 Fire-and-Forget UDP Telemetri Mimarisi", "Heading2", None),
    (None, "Normal",
     "Kara istasyonu telemetrisi UDP üzerinden, ack beklenmeyen ve sequence numarası taşıyan "
     "JSON paketleri ile gönderilmektedir (ground_station.py). Tasarım kararları üç başlıkta "
     "toplanır: (i) Ack beklenmediği için ana kontrol döngüsü asla network gecikmesi "
     "tarafından bloklanmaz; (ii) sequence numarası, kara tarafında paket kaybının tespit "
     "edilmesini sağlar; (iii) socket timeout veya OSError durumlarında istisna sayaca "
     "yazılır ancak ana döngüye fırlatılmaz, network kesintisinde ROV görev üzerinde "
     "kesintisiz devam eder. Bu mimari, gerçek zamanlı kontrol döngüsünün telemetri "
     "katmanından bağımsız bir şekilde sürdürülmesini garanti eder; gecikmenin kabul "
     "edilemez, paket kaybının kabul edilebilir olduğu telemetri use-case'i için uygun "
     "tasarımdır."),

    ("11.10 Donanım-Bağımsız Doğrulama Çerçevesi", "Heading2", None),
    (None, "Normal",
     "Yukarıda belirtilen tüm yazılım kararları, donanım entegrasyonu öncesi laptop "
     "ortamında üretilen sentetik dataset, birim testleri (pytest 82 başarılı) ve uçtan uca "
     "simülasyon ile doğrulanmıştır. Donanım montajı tamamlandığında ABC'nin bulduğu "
     "parametrelerin (özellikle PID kazançları, plant kalibrasyonu K=0.25, τ=0.5 s) "
     "gerçek araç üzerinde ölçülen tepki ile retune edilmesi planlanmaktadır. Bu yaklaşım, "
     "yazılım katmanını donanım gecikmelerinden ayrıştırarak paralel geliştirmeyi mümkün "
     "kılar — projenin özgün mühendislik yönetim kararlarından biridir."),
]


def make_paragraph(text, style_id):
    """Build a w:p element with given text and style id."""
    p = OxmlElement("w:p")
    if style_id:
        pPr = OxmlElement("w:pPr")
        pStyle = OxmlElement("w:pStyle")
        pStyle.set(qn("w:val"), style_id)
        pPr.append(pStyle)
        p.append(pPr)
    if text:
        r = OxmlElement("w:r")
        t = OxmlElement("w:t")
        t.text = text
        t.set(qn("xml:space"), "preserve")
        r.append(t)
        p.append(r)
    return p


def find_anchor(body_children, exact_text):
    for i, el in enumerate(body_children):
        if el.tag == qn("w:p") and para_text(el) == exact_text:
            return i, el
    return None, None


def main():
    base = Document(str(SRC_BASE))
    v3 = Document(str(SRC_V3))

    base_body = base.element.body
    v3_body = v3.element.body
    base_children = list(base_body.iterchildren())
    v3_children = list(v3_body.iterchildren())

    # --- 1. Insert references after KAYNAKLAR title ---
    kayn_idx, kayn_el = find_anchor(base_children, "KAYNAKLAR")
    ekler_idx, ekler_el = find_anchor(base_children, "EKLER (Var ise)")
    if kayn_el is None or ekler_el is None:
        raise SystemExit(f"Could not find KAYNAKLAR ({kayn_idx}) or EKLER ({ekler_idx})")
    print(f"KAYNAKLAR at child {kayn_idx}, EKLER at child {ekler_idx}")

    # Promote KAYNAKLAR and EKLER paragraphs to Heading 1 (originals were 'normal')
    for el in (kayn_el, ekler_el):
        # remove existing pPr/pStyle if any, then add Heading1
        pPr = el.find(qn("w:pPr"))
        if pPr is None:
            pPr = OxmlElement("w:pPr")
            el.insert(0, pPr)
        for ps in pPr.findall(qn("w:pStyle")):
            pPr.remove(ps)
        pStyle = OxmlElement("w:pStyle")
        pStyle.set(qn("w:val"), "Heading1")
        pPr.insert(0, pStyle)
    print("promoted KAYNAKLAR & EKLER to Heading 1")

    # v3 references: child 149-161
    ref_count = 0
    for v3_el in v3_children[149:162]:
        text = para_text(v3_el)
        if not text or text.startswith("―") or text.startswith("Not (takıma)"):
            continue
        new_el = deepcopy(v3_el)
        remap_style_ids(new_el)
        # Insert before EKLER (which preserves order under KAYNAKLAR heading)
        ekler_el.addprevious(new_el)
        ref_count += 1
    print(f"inserted {ref_count} references")

    # --- 2. Insert ÖZGÜNLÜK section before EKLER ---
    oz_count = 0
    for text, style, body_text in OZGUNLUK:
        # rows are tuples of (heading_text, style, None) for headings, or (None, "Normal", body_text) for paragraphs
        if text is not None:
            new_p = make_paragraph(text, style)
        else:
            new_p = make_paragraph(body_text, style)
        ekler_el.addprevious(new_p)
        oz_count += 1
    print(f"inserted {oz_count} ÖZGÜNLÜK paragraphs")

    base.save(str(OUT))
    print(f"saved -> {OUT}")


if __name__ == "__main__":
    main()
