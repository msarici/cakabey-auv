"""Insert "8. TEST VE TECRÜBE" and "9. RİSK YÖNETİMİ" with software sub-sections
before KAYNAKLAR. Sections 10. Bütçe is intentionally omitted (no software content).
"""
from pathlib import Path

from docx import Document

from insert_references_and_originality import find_anchor, make_paragraph

SRC_BASE = Path(r"C:\Users\ASUS\OneDrive\Desktop\SON HALİ DTR (7 + 11 + kaynaklar).docx")
OUT = Path(r"C:\Users\ASUS\OneDrive\Desktop\SON HALİ DTR (7-9 + 11 + kaynaklar).docx")


TEST_SECTION = [
    ("8. TEST VE TECRÜBE", "Heading1", None),

    (None, "Normal",
     "Çakabey AUV'nin tasarım doğrulama süreci üç paralel test hattı üzerinden "
     "yürütülmektedir: (i) mekanik testler (basınç odası sızdırmazlık testi, kelepçe "
     "sabitleme dayanım testi, hidrostatik denge ölçümü), (ii) elektronik testler "
     "(motor sürüm karakterizasyonu, ESC arm prosedürü, voltaj regülatörü ripple "
     "ölçümü, brownout testleri) ve (iii) yazılım doğrulama testleri (birim, "
     "entegrasyon, sentetik dataset ve uçtan uca simülasyon). Bu raporun yazıldığı "
     "aşamada (donanım entegrasyonu öncesi) tam olarak yazılı durumda olan tek hat "
     "yazılım doğrulamadır; mekanik ve elektronik test sonuçları ilgili takım üyeleri "
     "tarafından 8.1 ve 8.2 alt başlıklarına eklenecektir."),

    ("8.3 Yazılım Doğrulama Testleri", "Heading2", None),

    (None, "Normal",
     "Yazılım doğrulama, donanım gerektirmeden laptop ortamında deterministik olarak "
     "yürütülebilen dört seviyeli bir test piramidi üzerine kuruludur. Tüm test "
     "rastgele süreçleri seed=42 ile sabitlenmiş; aynı kodu indiren herhangi bir "
     "üçüncü taraf aynı sayısal sonuçları üretebilir."),

    ("8.3.1 Birim ve Entegrasyon Testleri (pytest)", "Heading3", None),

    (None, "Normal",
     "Test paketi pytest çatısı altında çalıştırılır ve şu kapsamı doğrular: FSM "
     "durum geçişleri (SEARCH/APPROACH/TRACK/LOST mantığı, frame sayaç eşikleri), "
     "PID matematiği (anti-windup integral clamping, time.monotonic() dt hesaplaması, "
     "output saturation), vehicle modülü konfigürasyon doğrulaması (RC kanal/PWM "
     "aralığı), distance hesapları (pinhole projeksiyonu W·f/w ve paralel lazer "
     "baseline B·f/g), ground station UDP paket bütünlüğü (sequence numarası, "
     "NumPy serileştirme), ground viewer dayanıklılığı (eksik/hatalı paket "
     "işleme), safety modülü kararları (batarya iki-kademeli eşik, watchdog timeout, "
     "leak GPIO sarmalayıcı) ve anomali algılama regresyonları (5 sınıf + clean + "
     "distractor)."),

    (None, "Normal",
     "Mevcut test koşusu çıktısı:"),

    (None, "Normal",
     "    $ python -m pytest -q\n    82 passed in 3.71s"),

    (None, "Normal",
     "82 testin tamamı başarıyla geçmektedir. Bu rakam, kod katmanına eklenen "
     "her yeni özellik için regresyon güvencesi sağlar; herhangi bir değişiklik "
     "mevcut davranışı bozarsa pytest derhal raporlar."),

    ("8.3.2 Sentetik Dataset Doğrulama Testleri", "Heading3", None),

    (None, "Normal",
     "HSV boru tespit pipeline'ı, distractor (sarı ve kırmızı bloklar) ve Gaussian "
     "gürültü içeren 20 sentetik frame üzerinde IoU (Intersection over Union) "
     "metriği ile ölçülmüştür. Mevcut config.yaml referans değerlerinde ortalama "
     "IoU = 0.9468 ölçülürken, ABC optimizasyonu sonrası bu değer 1.0000'a "
     "çıkmıştır (bkz. Tablo 6.3.6). Sentetik %100 IoU mutlak saha başarısı "
     "değildir; deterministik kontrollü dataset üzerinde algoritmanın lokal "
     "optimuma takılmadan yönlendiğini ölçer."),

    (None, "Normal",
     "Anomali algılama, seed=42 ile üretilen 6 etiket × frame matrisi üzerinde "
     "5×5 diyagonal sınıflandırma doğruluğu ile doğrulanmıştır (Tablo 6.3.4). "
     "Tüm sınıflar (algae, rust, crack, break, missing) doğru tahmin edilmiş; "
     "clean frame ile boru dışı turuncu distractor frame'lerinde sıfır yanlış "
     "pozitif üretilmiştir. Bu sonuç, 6.3.6'da açıklanan iki tasarım kararının "
     "(yatay-eğilimli morfolojik kapama ve break sonrası crack bastırma) "
     "doğru çalıştığının regresyon kanıtıdır."),

    ("8.3.3 ABC Optimizasyon Koşusu Doğrulaması", "Heading3", None),

    (None, "Normal",
     "PID optimizasyonu (koloni 20, iterasyon 30, anti-windup ON, birinci dereceden "
     "ROV yaw modeli, 5 s @ 50 Hz simülasyon): ITAE referans 998.89 → ABC sonucu "
     "51.11 (%94.9 azalma). HSV optimizasyonu (koloni 20, iterasyon 30, sentetik 20 "
     "frame): ortalama IoU 0.9468 → 1.0000. Tüm rakamlar deterministiktir; ABC "
     "her koşturulduğunda aynı sonuçları üretir (warm-start + seed=42). Detaylı "
     "tablolar 6.3.7 ABC bölümünde verilmiştir."),

    ("8.3.4 Uçtan Uca Simülasyon Testi", "Heading3", None),

    (None, "Normal",
     "    $ python main.py --sim --no-display"),

    (None, "Normal",
     "Bu komut, gerçek kamera ve Pixhawk bağlantısı yokken sentetik kamera üretimi → "
     "boru tespiti → anomali tespiti → FSM → PID → telemetri zincirini ana döngüde "
     "tam olarak çalıştırır. Her modülün çıktısı bir sonrakine girdi olarak verilir; "
     "modüller arası API uyumsuzluğu veya sessiz bir hata anında ortaya çıkar. Bu "
     "test, donanım entegrasyonu öncesi ana akışın regresyona karşı korunmasını "
     "sağlar — herhangi bir yeni modül eklendiğinde aynı komut yeniden koşturularak "
     "tüm zincirin kararlı çalıştığı doğrulanır."),

    ("8.3.5 Donanım Sonrası Planlanan Testler", "Heading3", None),

    (None, "Normal",
     "Donanım entegrasyonu sonrasında aşağıdaki saha testleri yürütülecektir: "
     "(a) gerçek havuz görüntüleri ile HSV alt/üst sınırlarının ve anomali "
     "eşiklerinin yeniden kalibrasyonu (sentetik dataset su altı ışık "
     "sönümlenmesini ve kırılma indeksi etkilerini tam temsil etmez); "
     "(b) Pixhawk üzerinde MAVLink loop testi (RCMAP_YAW, RCMAP_FORWARD eşleşme "
     "doğrulaması, düşük PWM'de ESC arm prosedürü, motor yön kontrolü); "
     "(c) gerçek motor dinamiği üzerinde step response ölçümü ve ABC'nin yeniden "
     "koşturulması (mevcut PID kazançları K=0.25, τ=0.5 s plant modeline "
     "kalibrelidir); (d) yeşil lazer modülü monte edildiğinde paralel baseline "
     "mesafe ölçümünün pinhole hattıyla karşılaştırılması; (e) gerçek leak sensörü "
     "ile Jetson GPIO entegrasyon testi. Bu testlerin her biri için kontrol listesi "
     "ve kabul kriteri 6.3.10'da listelenen sınırlılıklar maddesinden takip "
     "edilebilir."),
]


RISK_SECTION = [
    ("9. RİSK YÖNETİMİ", "Heading1", None),

    (None, "Normal",
     "Çakabey AUV projesinde risk yönetimi mekanik (yapısal hasar, sızıntı, motor "
     "arızası), elektronik (kısa devre, batarya tükenmesi, sensör arızası) ve yazılım "
     "(kontrol döngüsü hatası, sensör veri bütünlüğü, kalibrasyon kayması) eksenlerinde "
     "tanımlanmıştır. 9.1 (mekanik) ve 9.2 (elektronik) risk kalemleri ilgili takım "
     "üyeleri tarafından doldurulacaktır; aşağıdaki 9.3 yazılım kaynaklı riskleri ve "
     "uygulanan hafifletme stratejilerini içermektedir."),

    ("9.3 Yazılım Kaynaklı Riskler ve Hafifletme Stratejileri", "Heading2", None),

    (None, "Normal",
     "Yazılım katmanından kaynaklanan veya yazılım katmanı ile hafifletilen riskler "
     "aşağıda kategori bazında listelenmiştir. Her risk için (i) tetikleyici koşul, "
     "(ii) etki ve (iii) uygulanan ya da planlanan hafifletme tanımlanmıştır."),

    ("9.3.1 Sensör Veri Kaybı / Bayat Veri Riski", "Heading3", None),

    (None, "Normal",
     "Tetikleyici: Pixhawk SYS_STATUS mesajının 2.0 saniyeden uzun süredir "
     "güncellenmemesi (bağlantı kopması, MAVLink paket kaybı veya Pixhawk donması). "
     "Etki: bayat sensör verisi ile araç komut üretmeye devam ederse kontrolden "
     "çıkmış AUV gerçek durumu tersine raporlayabilir. "
     "Hafifletme: safety.py içindeki watchdog (7.3.2) bu durumu uyarı değil "
     "emergency olarak işler; motor stop tetiklenir ve telemetriye not düşülür. "
     "Sensör çağrılarının ana döngüden bağımsız kontrolü, bu riskin yakalanma "
     "olasılığını her döngü iterasyonunda %100 yapar."),

    ("9.3.2 Kamera Frame Kaybı Riski", "Heading3", None),

    (None, "Normal",
     "Tetikleyici: CSI/USB kamera bağlantısının kopması veya driver seviyesinde "
     "kareye erişilememesi. "
     "Etki: pipe_detector boş frame ile çağrılırsa tespit yok; FSM hatalı şekilde "
     "LOST'a geçer ve gereksiz arama davranışı sergiler. "
     "Hafifletme: ana döngü ardışık 30 boş frame sonrası güvenli durdurma uygular; "
     "bu eşik, geçici frame drop'ları (örneğin USB jitter) ile gerçek kamera "
     "kopmasını ayırt etmek için seçilmiştir."),

    ("9.3.3 MAVLink Bağlantı Kaybı Riski", "Heading3", None),

    (None, "Normal",
     "Tetikleyici: vehicle.py'nin Pixhawk'a göndermeye çalıştığı RC_CHANNELS_OVERRIDE "
     "veya heartbeat mesajının iletilmemesi (USB/serial kopması). "
     "Etki: PID çıktısı üretilse bile araç PWM komutunu almaz; motor son geçerli "
     "komutu sürdürmeye devam eder (ArduPilot Sub davranışı). "
     "Hafifletme: heartbeat watchdog ile sensör katmanından zaten yakalanır "
     "(9.3.1). Ek olarak ArduPilot Sub'un kendi failsafe modu (RC override "
     "timeout sonrası HOLD veya STABILIZE) yedek katman oluşturur."),

    ("9.3.4 Görsel Algılama Lokal Optimum Riski (ABC)", "Heading3", None),

    (None, "Normal",
     "Tetikleyici: ABC'nin sentetik dataset üzerinde lokal optimuma takılması ve "
     "gerçek su altı dağılımında düşük performans göstermesi. "
     "Etki: HSV alt/üst sınırları sentetik dataset'e overfit olabilir; gerçek "
     "havuzda su rengi/aydınlatma değişkenliği nedeniyle IoU düşer. "
     "Hafifletme: warm-start mekanizması (11.3) referans çözümün altına düşmeyi "
     "engeller — en kötü durumda mevcut config performansı korunur. Donanım "
     "entegrasyonu sonrası ABC, gerçek havuz frame'leri ile yeniden koşturulacak "
     "ve sentetik vs gerçek dataset performansı karşılaştırılacaktır."),

    ("9.3.5 PID Kazanç Kayması Riski", "Heading3", None),

    (None, "Normal",
     "Tetikleyici: ABC'nin bulduğu Kp/Ki/Kd üçlüsü plant modeli (K=0.25, τ=0.5 s) "
     "üzerinde optimaldir; gerçek araç dinamiği farklıysa overshoot veya "
     "underdamping oluşabilir. "
     "Etki: agresif kazançlarda boru takibinde oscillasyon, tutarsız kazançlarda "
     "yavaş yanıt. "
     "Hafifletme: gerçek havuz testinde step response ölçülecek, plant parametreleri "
     "güncellenecek, ABC tekrar koşturulacaktır. Ayrıca evaluator_pid.py simülatörü "
     "kontrolör mantığını birebir uyguladığı için, yeni plant ile bulunan kazançlar "
     "gerçek kontrolöre yeniden tune'lamadan transfer edilebilir."),

    ("9.3.6 Telemetri Paket Kaybı / Kara İstasyonu Bağlantı Riski", "Heading3", None),

    (None, "Normal",
     "Tetikleyici: CAT6 tether üzerinden UDP telemetri paketlerinin iletilmemesi "
     "veya kara istasyonu yazılımının çökmesi. "
     "Etki: operatör araç durumunu göremez; ancak araç görev üzerinde devam etmeye "
     "yetkilidir. "
     "Hafifletme: ground_station.py fire-and-forget UDP mimarisi (11.9) ana döngüyü "
     "asla bloklamaz; socket timeout veya OSError sayaca yazılır. ground_viewer.py "
     "bozuk veya eksik UDP paketlerine karşı dayanıklı kılınmıştır (seq alanı "
     "eksik/hatalı tipte olduğunda viewer paketi güvenli şekilde işler)."),

    ("9.3.7 Kalibrasyon Kayması Riski (Yazılım-Donanım Entegrasyon Sonrası)", "Heading3", None),

    (None, "Normal",
     "Tetikleyici: laptop ortamında doğrulanmış parametrelerin (HSV alt/üst, anomali "
     "eşikleri, PID kazançları, leak GPIO pin numarası, watchdog süreleri) gerçek "
     "donanımda farklı davranması. "
     "Etki: tek bir parametrenin yanlış kalibrasyonu görev başarısızlığına yol açabilir. "
     "Hafifletme: tüm parametreler config.yaml üzerinden kod değişikliği gerektirmeden "
     "ayarlanabilir kılınmıştır; kalibrasyon prosedürü 6.3.10 sınırlılıklar maddesinde "
     "ve 8.3.5'te listelenmiştir. Her parametre için kabul kriteri ve test prosedürü "
     "donanım entegrasyonu sonrası bir kez yürütülecektir."),
]


def main():
    base = Document(str(SRC_BASE))
    base_body = base.element.body
    base_children = list(base_body.iterchildren())

    kayn_idx, kayn_el = find_anchor(base_children, "KAYNAKLAR")
    if kayn_el is None:
        raise SystemExit("Could not find KAYNAKLAR anchor")
    print(f"KAYNAKLAR at child {kayn_idx} (insertion point)")

    inserted = 0
    for entries in (TEST_SECTION, RISK_SECTION):
        for text, style, body_text in entries:
            content = text if text is not None else body_text
            new_p = make_paragraph(content, style)
            kayn_el.addprevious(new_p)
            inserted += 1
    print(f"inserted {inserted} paragraphs (TEST + RISK) before KAYNAKLAR")

    base.save(str(OUT))
    print(f"saved -> {OUT}")


if __name__ == "__main__":
    main()
