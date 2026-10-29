# Çakabey AUV — tamamlanan yazılım incelemesi

29 Ekim 2026. Başlangıç kaynağı: `84f499b6825d0d6a9ce0f63a521b534fc8486829` (10 Temmuz 2026). Bulguların yeni oluştuğu iddia edilmez. Önceki incelemedeki açık yazılım başlıkları bu sürümde ele alındı; fiziksel doğrulama yapılmadı.

## Düzeltilenler

| Alan | Son davranış |
|---|---|
| Gerçek bağlantı / simülasyon | YAML gerçek bağlantı arızasını simülasyonla gizleyemez. `--sim` Pixhawk/GPIO açmadan çalışır. Eski test adresi yerine seri port varsayılanı kullanılır. |
| GPIO / sızıntı | Başlatma, okuma ve geçersiz seviye hataları kilitli acil durumdur; arm engellenir veya görev durdurulur. |
| Komut güvenliği | HMAC-SHA256, imzalı hello/challenge, süreli alıcı nonce'u, oturum kilidi, artan sıra sayısı ve katı JSON şeması. Anahtarsız gerçek komut kanalı başlamaz. |
| Acil dur / bağlantı kaybı | Acil dur gönderici ve alıcıda kilitlidir; hız sınırına takılmaz, kamera öncesi/çıkış öncesi kontrol edilir. Manuel bağlantı kaybı kendiliğinden otonom harekete dönmez. |
| Bağımsız yazılım durdurması | `vehicle_supervisor.py` gerçek MAVLink bağlantısını ayrı süreçte tutar. Ana program kamera/CV/log içinde takılırsa veya aniden ölürse süre dolunca nötr/disarm/kapatma istenir. Süresi dolan süreç geç gelen komutla devam etmez. Zaten arm durumundaki araca yeniden bağlanma da izlenir. |
| Pixhawk durum doğrulaması | Arm/disarm/mod başarıları yeni heartbeat ile doğrulanır. Bilinmeyen/geçersiz batarya reddedilir, heartbeat yaşı ayrıca kontrol edilir, reconnect cache'i temizler. |
| MAVLink güvenliği | İlk otopilot kimliği yapılandırılmış system/component ID ile eşleşir. Ağ bağlantıları MAVLink2 imzası ister; yerel seri bağlantıda ayrıca zorunlu tutulabilir. İmzasız/yanlış anahtarlı/tekrarlı paketler gerçek codec testlerinde reddedilir. pymavlink 2.4.50'nin başarısız imzada değiştirdiği replay state geri alınır; sürüm sabitlenmiştir. |
| Video / telemetri | Kanal ayrımlı HMAC anahtarları, imzalı oturum/sıra/zaman, çözümleme öncesi doğrulama. Bellek/paket/kare/JPEG/decode sınırları ve video yeniden sıralama penceresi vardır. Kısmi gönderim hatası sonrası kare parçalarının sonraki kareyle karışması engellenir. |
| Başlangıç / kapanış | Kaynakların yaşam döngüsü başlangıcı da kapsar. Stop/disarm/kapatma ayrı ayrı denenir; tek hata diğerini engellemez. Eksik/bozuk config, geçersiz zaman ve sonlu olmayan sayılar reddedilir. |
| Kamera / kontrol | CSI gerçek Argus/GStreamer hattını ve seçilen cihazı kullanır. İlk kayıp kare nötr komut ister; detector/FSM istisnasında göreve devam edilmez. Motor çıkışından önce yaş/GPIO/acil dur yeniden kontrol edilir. |
| Anomali algılama | Kontrol hedefinden ayrı inceleme ROI'si hizalı yakın boru parçalarını kapsar. Dönüşe dayanıklı geometri, boru dışı arka planın dışlanması ve renk lekesi sınırlarının çatlak sayılmaması eklendi. Config eşikleri gerçek boru-dedektör/analiz zinciriyle sınandı. |
| Diğer | Telemetri kayıp sayacı eski paketle geri sarılmaz. ABC optimizer geçersiz koloni boyutunu ve boş arama alanını erken reddeder. HSV sınırları/alan/kernel değerleri doğrulanır. |

## Gerçek doğrulama sonuçları

- İlk kaynak: **125 test geçti**.
- İlk geniş düzeltme: **246 test**, GitHub Actions Python 3.10/3.11/3.12 üzerinde geçti.
- Son sürüm yerel tam test çalışması: **444 geçti, 0 atlandı**, 10.16 saniye; Python 3.12.14.
- Ayrı süreç testleri: ana programın hareketsiz kalması, kanalın kapanması, `os._exit` ile aniden ölmesi, önceden arm durumundaki bağlantı, düzenli komut ve temiz kapanış. Gerçek motor kullanılmadı.
- Gerçek CLI `--sim` ile ayrı süreçte açıldı, görüntü işleme başladı ve SIGINT ile hatasız kapandı.
- Anomali zinciri: 5 rastgelelik tohumu × 4 dönüş açısı × 6 sınıf = **120 durumda tam beklenen etiketler**; temiz örneklere yanlış alarm yok. Ayrıca dikkat dağıtıcı nesneler, parçalı ROI, borusuz görüntü ve ayrı HSV gürültü tohumları test edildi.
- Önceki probe beş pozitif anomaliyi kaçırıyordu; son probe algae/rust/crack/break/missing sınıflarının beşini de buluyor ve clean örneğinde boş sonuç veriyor.
- Mevcut sentetik HSV IoU: **0.9414922865** (önceki config: **0.7099763637**), seed 42. Bu saha doğruluk oranı değildir.
- `git diff --check` ve Python derleme kontrolü başarılı.

Yerel bağımlılıklar: pytest 9.2.0, OpenCV paket 5.0.0.93 (cv2 5.0.0), NumPy 2.3.5, PyYAML 6.0.3, pymavlink 2.4.50, pygame 2.6.1. Son commit'in Python 3.10/3.11/3.12 sonuçları GitHub Actions/PR kontrollerinden izlenir; önceki commit sonuçları yeni commit için kanıt sayılmaz.

```bash
pip install -r requirements.txt pygame
python -m pytest tests/ -q -rs
python tests/manual_anomaly_probe.py --config config.yaml
python main.py --sim --no-display
```

## Kurulum sözleşmesi

- `CAKABEY_COMMAND_KEY`: iki uçta aynı rastgele gizli değer, en az 32 byte; komut, video ve telemetri doğrulaması için. Anahtar repoya yazılmaz. Anahtarsız tamamen otonom kullanımda üç ağ kanalını da config'de kapatın.
- `CAKABEY_MAVLINK_KEY`: 64 hex karakter/32 byte; ağ üzerinden Pixhawk için zorunlu. Otopilotun uyumlu MAVLink2 ayarı ve aynı anahtar ayrıca sağlanır. Yerel seri port fiziksel güven varsayımıyla çalışabilir; `vehicle.require_signing: true` bu portta da imza ister. Varsayılan kimlikler system=1/component=1.
- `--sim`: donanım açmaz, imzasız test trafiği sadece loopback'tedir. Video viewer `--sim --rov-ip 127.0.0.1`, telemetri viewer `--sim` kullanır.
- Acil dur ve komut oturum kilidi yeniden başlatmayla temizlenir. Gönderici yeniden başlarsa ilgili alıcı/viewer da yeniden başlatılmalıdır.
- Komut kanalı nonce protokolü ortak duvar saati gerektirmez. Tek yönlü video/telemetri imzalı zaman damgası kullanır: makinelerin saatleri eşitlenmeli; 2 saniye eski / 0.5 saniye gelecek sınırı vardır.

## Donanım olmadan kanıtlanamayacak ve tasarıma ait sınırlar

1. Bağımsız süreç ana kontrol programının takılmasına karşı çalışır. İşletim sistemi/güç kaybı, MAVLink sürücüsünün kendi içinde kilitlenmesi veya kopmuş kablo durumunda fiziksel duruş garantisi vermez. Otopilot failsafe ayarları ve gerçek motor tepkisi bu incelemede değiştirilmedi veya ölçülmedi.
2. İmzalar kimlik/bütünlük sağlar; şifreleme sağlamaz. Komutlarda daha önce alınmamış geçerli yüksek sıra sayılı paket nonce'un iki saniyelik ömründe gecikmeli kabul edilebilir. Video/telemetride viewer yeniden başladıktan sonra aynı kısa tazelik penceresindeki görülmemiş yakalanmış paketler kabul edilebilir. Bu sınırlar sınırsız replay koruması diye sunulmaz.
3. Anomali tespiti sonlu, sezgisel görüntü kurallarıdır; yakın ve aynı eksendeki parçaları gruplar. Gerçek su, aydınlatma, ölçek ve aynı eksendeki ilgisiz nesneler için temsilî kayıtlarla doğrulama gerekir. Sentetik başarı fiziksel kalibrasyon değildir.
4. GPIO'nun kuru seviyesinde takılması, kablo/sensör devresinin elektriksel arızaları, motor yönleri, PWM/RC eşlemesi ve fiziksel joystick bu ortamda sınanmadı. Gerçek Jetson/Pixhawk/SITL çalıştırılmadı.
5. Bu çalışma mevcut kaynak kodun arıza yollarını ve test kapsamını ele alır; tüm gelecekteki bağımlılık sürümleri, dış CVE veritabanları veya olası her saldırı/donanım koşulu için eksiksizlik iddiası yoktur.
