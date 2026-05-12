"""Insert "7. GÜVENLİK ÖNLEMLERİ" with the software safety sub-section
before KAYNAKLAR in the current consolidated docx.

Mechanical and electronic safety sub-sections are intentionally left as
placeholders for the relevant team members to fill in. Software content
(safety.py — battery monitoring, sensor watchdog, leak detection, emergency
mode) is written here as 7.3.
"""
from copy import deepcopy
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

from insert_references_and_originality import find_anchor, make_paragraph

SRC_BASE = Path(r"C:\Users\ASUS\OneDrive\Desktop\SON HALİ DTR (kaynaklar + ozgunluk).docx")
OUT = Path(r"C:\Users\ASUS\OneDrive\Desktop\SON HALİ DTR (7 + 11 + kaynaklar).docx")


GUVENLIK = [
    ("7. GÜVENLİK ÖNLEMLERİ", "Heading1", None),

    (None, "Normal",
     "Çakabey AUV'nin güvenlik mimarisi üç katmanın paralel çalışması ile sağlanır: "
     "(i) mekanik katman (gövde sızdırmazlığı, kelepçe sabitlemeleri, alt koruma kızağı, "
     "titreşim sönümleyici pedler), (ii) elektronik katman (güç dağıtım kartı sigortaları, "
     "voltaj regülatörü brownout koruması, ESC arm prosedürü, lazer modülü çift kademeli "
     "filtreleme), ve (iii) yazılım katmanı (kontrol döngüsü içi watchdog, batarya izleme, "
     "sızıntı algılama ve emergency mode). Her katman bir diğerinin yedeği değil, "
     "birbirinin tamamlayıcısı olarak tasarlanmıştır."),

    (None, "Normal",
     "Aşağıda 7.1 (mekanik) ve 7.2 (elektronik) güvenlik önlemleri ilgili takım üyeleri "
     "tarafından detaylandırılacaktır. Bu raporun yazıldığı aşamada yazılım katmanı "
     "(7.3) doğrudan kontrol döngüsü içinde test edilebilir tek katman olduğu için "
     "tam olarak yazılı durumdadır."),

    ("7.3 Yazılım Güvenlik Katmanı", "Heading2", None),

    (None, "Normal",
     "Yazılım güvenlik katmanı, ana kontrol döngüsünün her iterasyonunda araç sensör "
     "verisini değerlendiren safety.py modülü ile uygulanmaktadır. Modül, dört kategoride "
     "bağımsız kontroller yürütür ve sonucu {emergency: bool, reason: str, "
     "warnings: List[str]} formatında üretir. Bu yapı, ana döngünün tek bir if dalı ile "
     "emergency durumlarını yakalamasına imkân verir; uyarılar (örneğin düşük batarya) "
     "telemetriye yazılır ancak görev devam eder. Olay eşikleri ve tepki tablosu "
     "Tablo 6.3.7'de detaylıca verilmiştir."),

    ("7.3.1 Batarya İzleme: İki Kademeli Eşik", "Heading3", None),

    (None, "Normal",
     "Batarya voltajı iki ayrı eşikte değerlendirilir: warn_voltage = 13.0 V altında "
     "uyarı (4S Jetfire batarya için yaklaşık %20 SoC), critical_voltage = 12.0 V "
     "altında ise emergency (motor stop + döngü çıkışı). İki kademeli yapı, hücre "
     "dengesizliğinden kaynaklı geçici voltaj düşüşlerinde aracın gereksiz yere "
     "durmasını engellerken; gerçek bir tükenme durumunda batarya zarar görmeden "
     "(LiPo için kritik 3.0 V/hücre eşiği aşılmadan) görev sonlandırmayı garanti eder."),

    ("7.3.2 Sensör Watchdog: Bayat Veri Engellemesi", "Heading3", None),

    (None, "Normal",
     "Pixhawk'tan alınan SYS_STATUS mesajının zaman damgası ile mevcut zaman arasındaki "
     "fark watchdog_timeout = 2.0 saniyeyi aşarsa, modül emergency üretir. Bu kararın "
     "ardındaki mantık şudur: bayat sensör verisi ile araca komut göndermeye devam etmek, "
     "fiziksel olarak kontrolden çıkmış bir AUV'nin kontrolde sanılmasına yol açar; "
     "bu durum yalnızca bir uyarı değil acil durum kabul edilmiştir. Watchdog süresi "
     "config.yaml > safety > watchdog_timeout altında ayarlanabilir."),

    ("7.3.3 Sızıntı Algılama: GPIO Tabanlı Donanım Entegrasyonuna Hazır", "Heading3", None),

    (None, "Normal",
     "Su kaçağı sensörü için Jetson.GPIO sarmalayıcısı eklenmiştir. Donanım yokken "
     "modül pasif placeholder olarak çalışır ve _leak_warned_once mekanizması ile bir "
     "kez \"sensör pasif\" uyarısı verip telemetriye not düşer (sürekli uyarı spam "
     "etmez). Donanım entegrasyonu sırasında yalnızca config.yaml > safety > leak_pin "
     "BCM pin numarasının ve leak_active_high (HIGH/LOW algılama yönünün) doğrulanması "
     "yeterlidir; sensör HIGH okuduğu anda emergency tetiklenir ve motor stop edilir. "
     "Program kapanışında cleanup() çağrısı GPIO kaynaklarını serbest bırakır."),

    ("7.3.4 Emergency Mode: Tek Komuta Motor Stop", "Heading3", None),

    (None, "Normal",
     "Yukarıdaki herhangi bir kontrol emergency durumunu işaret ederse, ana döngü "
     "vehicle.stop() çağrısı ile tüm motor PWM değerlerini nötr 1500'e çeker, "
     "ground_station üzerinden emergency olayını telemetriye iletir ve while True "
     "döngüsünden temiz çıkış yapar. Bu yaklaşım, herhangi bir alt sistemin "
     "(detector, FSM, PID) emergency durumda kontrol komutu üretmeye devam edip "
     "edemeyeceğine bakmaksızın motor bağlantısını fiziksel olarak nötrler — yazılım "
     "katmanı tek noktadan müdahale ile tüm aracı güvenli duruma getirir."),

    ("7.3.5 Vehicle Konfigürasyon Doğrulaması", "Heading3", None),

    (None, "Normal",
     "Vehicle modülünün başlangıcında RC kanal numaraları (yaw_channel, "
     "forward_channel) ve PWM aralığı (pwm_min < pwm_base < pwm_max) erken doğrulanır. "
     "Hatalı veya tutarsız bir konfigürasyonun (örneğin pwm_base > pwm_max) görev "
     "sırasında değil program başlangıcında yakalanması, çalışma anında oluşacak "
     "kontrol kaybı riskini ortadan kaldırır."),

    (None, "Normal",
     "Yazılım güvenlik katmanı laptop ortamında pytest ile birim ve entegrasyon "
     "testlerinden geçmiştir; donanım entegrasyonu sonrasında watchdog süresi ve "
     "leak sensörü pin doğrulaması fiziksel test ile son kez teyit edilecektir."),
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
    for text, style, body_text in GUVENLIK:
        content = text if text is not None else body_text
        new_p = make_paragraph(content, style)
        kayn_el.addprevious(new_p)
        inserted += 1
    print(f"inserted {inserted} GÜVENLİK paragraphs before KAYNAKLAR")

    base.save(str(OUT))
    print(f"saved -> {OUT}")


if __name__ == "__main__":
    main()
