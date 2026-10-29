# Çakabey AUV — kod ve güvenlik değerlendirmesi

Tarih: 29 Ekim 2026. İncelenen kaynak: `84f499b6825d0d6a9ce0f63a521b534fc8486829` (main, 10 Temmuz 2026). Bulguların yeni oluştuğu iddia edilmez. Bu rapor kaynak kod incelemesi, sahte donanımla hata enjeksiyonu, yerel UDP testleri ve sentetik görüntü ölçümüdür; fiziksel aracın güvenlik sertifikasyonu değildir.

## Sonuç

İlk iki bulgu doğrudur; komut kanalı ve görev yaşam döngüsünde başka önemli eksikler de doğrulanmıştır. Bu değişiklik güvenli hata davranışını ve test kapsamını iyileştirir. Fiziksel motor durdurma, bağımsız watchdog ve gerçek sualtı görüntülerindeki algılama doğruluğu henüz doğrulanmadığı için araç için "tam güvenli / sahaya hazır" sonucu çıkarılamaz.

Öncelikler: **P1** doğrudan yetkisiz hareket, durdurmanın atlanması veya donanım durumunun yanlış kabulü; **P2** doğruluk, kullanılabilirlik veya savunma derinliği; **P3** çevrimdışı araç/izleme sorunları. Bunlar bağlama göre mühendislik öncelikleridir; CVSS puanı değildir.

## Doğrulanan ve düzeltilen bulgular

| Öncelik | Kaynak / önceki davranış | Bu yamadaki sonuç |
|---|---|---|
| P1 | `config.yaml`, `main.py`, `vehicle.py`: gerçek bağlantı kurulamayınca YAML üzerinden simülasyona düşülebiliyordu. | Gerçek mod fallback kapalı; `--sim` doğrudan yazılım simülasyonu, Pixhawk/GPIO açılmaz. Varsayılan seri port `/dev/ttyACM0`; eski `tcp:127.0.0.1:1` test adresi kaldırıldı. |
| P1 | `safety.py`: GPIO başlatma/okuma hatası sızıntı yok gibi ele alınıyordu. | Arıza kilitli acil durum; başlatmada arm engellenir. Gerçek uygulamada sensörün açıkça devre dışı bırakılması da reddedilir. |
| P1 | `command_link.py`: ağ erişimi olan herhangi bir gönderen manuel hareket/mod komutu verebiliyordu. | HMAC-SHA256, ortak gizli anahtar, imzalı hello/challenge ve alıcı nonce'u. Anahtar yoksa etkin gerçek komut kanalı başlatılmaz. |
| P1 | `command_link.py`: eski/tekrarlanan/sırası bozuk komutlar son komutu ezip bağlantıyı canlı tutabiliyordu. | Oturum kilidi, artan sıra sayısı ve süreli nonce; alıcı yeniden başladığında eski nonce geçersiz. Hiç alınmamış yeni sıra sayılı geçerli paket, iki saniyelik nonce süresi içinde gecikmeli kabul edilebilir. |
| P1 | `command_link.py`: sınırsız UDP boşaltma güvenlik döngüsünü meşgul edebiliyordu; gevşek JSON şeması geçersiz alanları kabul ediyordu. | Poll başına 64 paket ve 2048 byte sınırı; yinelenen JSON alanları, yanlış türler, geçersiz eksenler ve kimliksiz paketler reddedilir. |
| P1 | `command_link.py`, `main.py`: acil dur hız sınırlamasına takılabilir, sonraki paketle ezilebilir veya kamera yolunda gecikebilirdi. | Gönderici/alıcıda kalıcı acil dur; TX hız sınırı atlanır; ana döngü kamera öncesi ve motor çıkışı öncesi kontrol eder, görevi bitirir ve stop/disarm ister. |
| P1 | `main.py`: manuel komut bağlantısı eskidiğinde otomatik SEARCH hareketine dönülüyordu. | Manuel bağlantı kaybı görevi bitirir; kendiliğinden otonom hareket başlamaz. Açıkça seçilmiş otonom görevin davranışı korunur. |
| P1 | `vehicle.py`: mod/arm/disarm gönderimi hemen başarılı sayılıyordu. | Bağlı otopilottan yeni heartbeat ile hedef durumun görülmesi gerekir; zaman aşımı başarısızlık sayılır. Arm onayı yokluğu "kesin arm olmadı" sayılmaz; kapanışta disarm yine denenir. |
| P1 | `vehicle.py`, `safety.py`: başka MAVLink kaynakları telemetriyi yenileyebilir; bilinmeyen batarya `65535` sağlıklı `65.535V` olabilirdi. | Bağlı otopilot system/component eşleşmesi, geçersiz batarya verisinin reddi, ayrı heartbeat yaş kontrolü ve reconnect öncesi cache sıfırlama. Kimlik eşleşmesi kriptografik MAVLink doğrulaması değildir. |
| P1 | `main.py`: kısmi başlangıç hatası/tek cleanup istisnası durdurma ve diğer kapatmaları atlatabilirdi. | Kaynak yaşam döngüsü bütün başlangıcı kapsar; stop, disarm, bağlantı/GPIO/kamera/ağ/log kapatma bağımsız denenir. |
| P1 | `main.py`: görüntü kaybında önceki hareket sürebilir; tespit/FSM istisnası arama dönüşüne yol açabilirdi. | İlk kayıp karede nötr komut istenir; işlem istisnasında görev durur; işleme sonrası eski güvenlik verisi motor komutuna izin vermez. |
| P2 | `main.py`: okunamayan config varsayılanlarla devam ediyor; NaN/sonsuz değerler zaman sınırlarını bozabiliyordu. | Eksik/bozuk config başlangıcı durdurur; sonlu değerler, pozitif zaman ve kayıp sınırları doğrulanır; gerçek modda test kamera fallback kapalıdır. |
| P2 | `camera.py`: CSI seçimi GStreamer hattını kullanmıyor, cihaz 0'ı açıyordu. | Argus/GStreamer hattı, seçilen sensor-id ve FPS kullanılır; başarısız capture serbest bırakılır. Donanımda denenmedi. |
| P2 | `video_viewer.py`: sınırsız UDP/reassembly ve kontrolsüz chunk başlıkları kaynak tüketimini artırıyordu. | Paket/decode, frame, chunk ve JPEG boyut sınırları; beklenen kaynak IP filtresi, sıra/tekrar/rollover denetimi. Video hâlâ kriptografik doğrulanmaz. |
| P3 | `abc_optimizer.py`: colony_size=1 komşu seçiminde sonsuz döngü oluşturuyordu. | Geçersiz koloni boyutu ve boş arama alanı erken reddedilir. |

## Açık kalanlar — sonraki çalışma

1. **P1, bağımsız durdurma doğrulaması:** `camera.read()`, görüntü işleme veya dosya yazımı aynı thread'i durdurursa Python watchdog'u da çalışamaz. Çıkış öncesi tekrar kontrol yalnızca fonksiyon geri döndüğünde fayda sağlar. ArduSub iletişim/RC kaybı failsafe ayarları, GCS heartbeat politikası ve bağımsız watchdog fiziksel donanımda ölçülmelidir. Bu yama bunları yapılandırmaz. Kopmuş bağlantıda stop/disarm paketinin ulaşacağı garanti edilemez.
2. **P2, anomali uçtan uca doğruluğu:** gerçek `PipeDetector(config) -> AnomalyDetector(config)` akışı kendi sentetik veri kümesinde algae, rust, crack, break ve missing örneklerinin beşinde de boş sonuç verdi. Mevcut birim testleri gerçek dedektör yerine doğru kabul edilen bbox kullanıyor. Özellikle `pipe_detector.py` en büyük konturu seçiyor; `anomaly_detector.py` bu ROI'ye kırptığı için kırık borunun diğer parçası dışarıda kalıyor. Gerçek etiketli sualtı görüntüleriyle ROI/tespit tasarımını yeniden değerlendirmek gerekir; bu yamada eşikler tahminle değiştirilmedi.
3. **P2, kalibrasyon iddiaları:** mevcut HSV config ile sentetik IoU **0.7099763637**, yorumdaki eski **1.0000** sonucu yeniden elde edilemedi. Ortam OpenCV 5.0.0/NumPy 2.3.5, seed 42. Eski bağımlılık sürümlerinin etkisi test edilmedi; saha başarısı veya tarihsel performans kaybı diye yorumlanamaz. Config yorumu bu ölçümle düzeltildi.
4. **P2, kalan ağ güven sınırı:** telemetri/video şifreli veya kriptografik doğrulanmış değildir. MAVLink kaynak ID filtresi imza değildir; ilk otopilot kimliği keşfedilir. HMAC komutları da şifrelemez. Tether ağına erişen taraf için bu sınırlar sürer. Anahtar güvenli ve repo dışında saklanmalıdır.
5. **P2, kuruluma bağlı sınırlar:** ArduSub firmware, RC kanal yönleri/PWM, GPIO kablolaması ve sensörün açık/kısa devre davranışı fiziksel test ister. Dijital GPIO'nun sabit kuru seviyesinde takılması yazılımla kesin teşhis edilemez.
6. **P3, telemetri gözlemlenebilirliği:** ground viewer sıra takibi sırası bozulan paketlerde kayıp sayısını yüksek hesaplayabilir; motor kontrol etkisi gösterilmedi.
7. **P2, tekrarlanabilir bağımlılıklar:** requirements yalnızca alt sürüm sınırları içeriyor; tek Python/bağımlılık ortamındaki sonuçlar diğer sürümlere genellenemez. Bu incelemede haricî CVE veritabanı taraması yapılmadı.

## Gerçek test sonuçları

Yerel ortam: Python 3.12.14, pytest 9.2.0, OpenCV paket 5.0.0.93 (cv2 5.0.0), NumPy 2.3.5, PyYAML 6.0.3, pymavlink 2.4.50, pygame 2.6.1.

- Özgün SHA: **125 geçti**, 0 atlandı; 2.92 saniye.
- Entegre yama: **246 geçti**, 0 atlandı; 3.10 saniye.
- `git diff --check`: başarılı.
- Tanısal anomali probe'u: beş pozitif örnek kaçırıldı; clean örneği boş sonuç verdi. Bu sonuç pytest sayısına katılmadı ve başarı sayılmadı.
- Önceki dar yamada pygame yoktu ve 1 modül atlanmıştı. Burada pygame kuruldu, manuel giriş testleri de çalıştı.
- Python 3.10/3.11, gerçek Jetson/Pixhawk, SITL, fiziksel joystick, su testi ve ağ üzerinde canlı saldırı testi yapılmadı. CI matrisi ayrı sonuç üretir; yerel testler CI geçti anlamına gelmez.

Tekrar çalıştırma (depo kökünde):

```bash
pip install -r requirements.txt pygame
python -m pytest tests/ -q -rs
python tests/manual_anomaly_probe.py --config config.yaml
git diff --check
```

Kapsam: mevcut Python modülleri, YAML, tests, CI ve README; kontrol/başlatma/kapanış, GPIO/MAVLink, komut/telemetri/video, kamera/görüntü/FSM/PID, manuel giriş, kayıt, mesafe, optimizasyon ve değerlendirme araçları incelendi. Öncelikli arıza yolları için test eklendi; bütün olası durumların veya fiziksel sistemin eksiksiz kanıtı değildir.

## Kurulumdaki davranış değişiklikleri

- Gerçek mod: `CAKABEY_COMMAND_KEY` en az 32 byte; iki uçta aynı rastgele gizli değer. Kaynak kodda anahtar yoktur. Tam otonom ve komutsuz kullanım için `command.enabled: false` açıkça seçilir.
- `--sim`: gerçek Pixhawk/GPIO kullanılmaz, komut alıcısı loopback'te çalışır. Viewer: `--sim --rov-ip 127.0.0.1`. Video hedefini de yerel simulation config'de loopback yapın.
- Acil dur veya sender yeniden başlatılması sonrası iki ucu yeniden başlatın. Oturum kilidi ve acil dur kilidi otomatik temizlenmez.
- Gerçek modda `source: test`, kamera fallback ve `leak_pin: null` kabul edilmez. `--sim` gerçek SITL bağlantısı kurmaz.
