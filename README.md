# Kablo Demeti Rotalama Demosu — 3B gövde yüzeyinde EMC duyarlı otomatik rotalama

**Türkçe** | [English](README.en.md)

[![CI](https://github.com/Goktugelbir/Emc-duyarli-kablo-rotalama/actions/workflows/ci.yml/badge.svg)](https://github.com/Goktugelbir/Emc-duyarli-kablo-rotalama/actions/workflows/ci.yml)

**Kabloları demetlerken EMC ayrım mesafesini, ayrıt kapasitesini, minimum bükülme yarıçapını ve yasak
hacimlere güvenlik payını birlikte gözeten bütünleşik rotalama, bu senaryoda demetlemenin yarattığı
5660 EMC ihlal noktasını, 116 kapasite ihlalini ve 15 bükülme ihlalini sıfıra indirirken demetlenme
oranını 0,382'de tutuyor.** Bütünleşik çözümün kablo listesinde ([`outputs/wirelist.csv`](outputs/wirelist.csv))
11 kablonun her biri bağımsız denetimlerle tek tek doğrulanır: hepsi `OK`, en sıkışık EMC ayrım payı +3,9 cm.

![Demetleme ve bütünleşik rotalama karşılaştırması: aynı senaryo, aynı kamera](outputs/comparison.png)

*Gövdeye alttan, kemerin içine bakış. Solda demetleme: kırmızı noktalar bağımsız denetimin bulduğu EMC
ihlalleridir. Sağda bütünleşik rotalama: tüm denetimler 0.*

![Bütünleşik rotalama — kablolar rotalama sırasıyla döşeniyor](outputs/demo.gif)

*Bütünleşik yöntem (e): kablolar, yöntemin onları rotaladığı sırayla tek tek döşenir; kelepçeler sonda belirir.*

## Etkileşimli 3B görünüm

Beş yöntemin 3B görünümü arasında sekmelerle geçilebilen sayfa: **[goktugelbir.github.io/Emc-duyarli-kablo-rotalama](https://goktugelbir.github.io/Emc-duyarli-kablo-rotalama/)**
(yerel kopya: [`docs/index.html`](docs/index.html)).

![Etkileşimli görünüm — açık arka uçtan gövde kesitinin içi](outputs/viewer_inside.png)

Sayfa three.js ile fiziksel tabanlı malzeme, ortam ışığı ve gölgelerle çizilir:

- içi astar boyalı, dışı yarı saydam alüminyum gövde kaplaması; frame, stringer ve zemin (koltuk rayları, zemin kirişleri),
- sınıfa göre kalınlığı değişen boru kablolar; aynı güzergâhı paylaşan kablolar demet içinde yan yana dizilir,
- demetler boyunca kelepçe ve dayanak braketleri, uçlarda konnektörler, kimlik kılıfları ve ekipman rafları,
- yasak hacimlerin içindeki donanım (kırmızı bantlı yakıt borusu, salınan aktüatör kolu, perçinli bakım kapağı)
  ve güvenlik payıyla büyütülmüş sınırları (kesikli kırmızı çizgi),
- **Rotalamayı oynat:** kablolar, yöntemin onları son kez rotaladığı sırayla (söküp yeniden rotalama dahil)
  tek tek döşenir; ihlal noktaları ve kelepçeler sonda belirir,
- bir kablonun üzerine gelince adı, sınıfı, güzergâh uzunluğu ve **doğrulama payları** (EMC ayrım payı, en küçük
  bükülme yarıçapı, yasak hacme uzaklık, `OK`/`CHECK`); tıklayınca bağlandığı ekipman ve diğer sınıflara gereken
  en büyük ayrım mesafesi kadar yarı saydam bir zarf,
- her yöntem için yedi denetim sonucu (EMC, bükülme, yasak hacim, güvenlik payı, kapasite ihlali ve uzunluklar),
- hazır kamera açıları (içeriden, alttan, dışarıdan, üstten), katmanları açıp kapatma, dar ekranlarda
  görüş açısının otomatik ayarlanması.

Bu gerçekçilik öğeleri yalnızca görseldir; kablo güzergâhları, ihlal noktaları ve metrikler doğrudan rotalama ve
bağımsız denetim sonuçlarıdır. Sayfa açılırken bütünleşik yöntemi (e) gösterir.

Pages'i açmak için: depo **Settings → Pages → Build and deployment → Source: "Deploy from a branch"**,
dal `main`, klasör `/docs` seçip kaydedin.

## Giriş

Bu depo, **uçak kablo demetlerinin üç boyutlu gövde geometrisi üzerinde EMC duyarlı otomatik
rotalanması** problemi için hazırlanmış küçük, basitleştirilmiş bir prototiptir. Amaç asıl
problemi çözmek değil; problemi doğru anladığımızı ve test edilebilir, modüler bir yazılım
iskeleti kurabildiğimizi göstermektir. Bu nedenle her sonuç, rotalama kodundan bağımsız
denetimlerle ölçülür; kod otomatik testlerle ve sürekli entegrasyonla (CI) korunur.

## Problem

Bir gövde kesiti üçgen yüzey modeli (mesh) olarak verilir. Her kablonun bir başlangıç ve bir
bitiş noktası ile bir EMC sınıfı (güç / sinyal / veri) vardır. İstenen, tüm kablolar için
yüzey üzerinde güzergâh üretmektir; öyle ki:

- kablolar mümkün olduğunca **demetlensin** (ortak güzergâh → daha az destek/kelepçe, daha az ağırlık),
- farklı EMC sınıfındaki kablolar arasında **ayrım mesafesi** korunsun,
- **yasak hacimlere** (yakıt hattı, hareketli yüzey zarfı, bakım kapağı vb.) girilmesin ve bunlara
  bir **güvenlik payından** daha fazla yaklaşılmasın,
- **minimum bükülme yarıçapı** ve bir güzergâh parçasından geçebilecek **en fazla kablo sayısı (kapasite)** aşılmasın.

Bu hedefler birbiriyle çelişir: demetleme kabloları bir araya toplar, EMC ise ayırmak ister;
kapasite demetin kalınlığını sınırlar, bükülme yarıçapı ise ani dönüşleri yasaklar.
Asıl projede problem kapasiteli Steiner ormanı olarak modellenip Lagrange gevşetmesiyle
çözülecektir; bu demo aynı problemin küçük ve basitleştirilmiş bir halini beş yöntemle ele alır.

## Kapsam

**Demo ne yapıyor**

- Yarıçapı 2 m, uzunluğu 6 m olan yarım silindir şeklinde temsilî bir gövde kesitini
  ~0,10 m aralıklı üçgen mesh olarak üretir (3904 köşe, 7560 üçgen; iç köşelere sabit seed'li
  küçük bir düzensizlik eklenir).
- Üç yasak hacim tanımlar (iki kutu, bir küre). Hacimleri 0,05 m güvenlik payı kadar büyütür; içlerinde
  kalan 429 düğümü ve bu büyütülmüş hacimleri kesen ayrıtları çizgeden çıkarır
  (kalan çizge: 3475 düğüm, 10033 ayrıt).
- 11 kablodan oluşan sentetik bir senaryo kurar (5 + 4 kablo iki yan tarafta paralel akar,
  2 kablo bir yandan diğerine geçer). Komşu uç noktalar farklı sınıftandır ve birbirine yakındır,
  ancak aralarındaki mesafe gereken ayrım mesafesinden büyüktür.
- Beş rotalama yöntemini çalıştırır; sonuçları rotalama kodundan bağımsız beş denetimle kontrol eder.
- Sıralı yöntemlerin kablo sırasına ve uç noktalara ne kadar duyarlı olduğunu 40 denemelik bir
  **sağlamlık testiyle** ölçer.
- Metrikleri tablo olarak yazar; kablo listesini (`wirelist.csv`, kablo başına doğrulama paylarıyla) ve bütün
  güzergâhları 3B olarak (`routes.json`) dışa aktarır.
- Her yöntem için 3B görsel, karşılaştırma görseli, rotalama animasyonu (GIF), metrik grafiği, Lagrange
  yakınsama grafiği, etkileşimli 3B sayfa ve çalışma günlüğü üretir.

**Demo ne yapmıyor**

- Kelepçe aralığı kısıtı yoktur (etkileşimli sayfadaki kelepçeler yalnızca görseldir).
- Gerçek uçak verisi, gerçek CAD geometrisi veya gerçek kablo listesi kullanılmamıştır.
- Ekranlama (shielding) ataması yoktur; EMC yalnızca geometrik ayrım mesafesiyle temsil edilir.
- Lagrange formülasyonu **basitleştirilmiştir** (aşağıya bakınız); Steiner ormanı yapısı,
  kablo kesitleri, demet çapı ve ağırlık modeli yoktur.
- Bükülme yarıçapı yalnızca bütünleşik yöntemde (e) rotalamaya katılır; diğer yöntemlerde sonradan denetlenir.
- Kablolar yüzey üzerinde (mesh köşeleri boyunca) ilerler; yüzeyden uzaklaşan destekler yoktur.
- Güvenlik payı kutular için muhafazakârdır: büyütülmüş kutu, kutuya 0,05 m'den yakın tüm noktaları
  kapsar; köşelerde ise biraz daha fazlasını dışlar.

### Temsilî parametreler

Aşağıdaki değerlerin tamamı **temsilîdir**; herhangi bir standarttan veya gerçek bir uçaktan alınmamıştır.

| Parametre | Değer |
|:---|---:|
| Ayrım mesafesi power–signal | 0,15 m |
| Ayrım mesafesi power–data | 0,20 m |
| Ayrım mesafesi signal–data | 0,10 m |
| Aynı sınıf | 0 m |
| Minimum bükülme yarıçapı | 0,10 m |
| Yasak hacim güvenlik payı | 0,05 m |
| Ayrıt kapasitesi K | 2 kablo (kısıtın etkin olması için bilerek dar seçildi) |
| Demetleme indirim katsayısı | kullanılmış ayrıtın maliyeti × 0,4 |
| EMC cezası | ayrıt uzunluğu × 20 (ek maliyet); her yeniden rotalama turunda × 2 |
| Kapasite cezası (yöntem e) | dolu ayrıtta ayrıt uzunluğu × 1000 (ek maliyet) |
| Söküp yeniden rotalama turu | c: en çok 5, e: en çok 10 |
| Rastgelelik | mesh düzensizliği `seed = 42`, sağlamlık testi `seed = 7` |

## Kurulum ve çalıştırma

Python 3.11+ gerekir. Bağımlılık sürümleri [`requirements.txt`](requirements.txt) içinde **sabitlenmiştir**:
en kısa yol eşitliklerinin hangi yolla bozulacağı kütüphane sürümüne göre değişebilir ve bu, örneğin
Lagrange iterasyon sayısını değiştirir. Yayımlanan çıktılar tam olarak bu sürümlerle üretilmiştir.

```bash
pip install -r requirements.txt
```

```bash
python main.py
```

Bu komut tüm çıktıları yeniden üretir: `outputs/` altındaki metrik ve sağlamlık tabloları, 3B görseller
(`routes_*.png`, `comparison.png`, `viewer_inside.png`, `demo.gif`), 2B grafikler (`metrics_chart.png`,
`lagrangian_convergence.png`), `wirelist.csv`, `routes.json`, `run_log.txt` ve `docs/index.html`. Bizim
makinemizde toplam süre ~40 s'dir: ~11 s sağlamlık testi, ~25 s 3B görsellerin yakalanması, ~2 s 2B grafikler,
~2 s mesh, rotalama, denetimler ve dışa aktarım. `--no-images` ile görseller atlanır (~10–20 s).

Görüntü üretimi sistemde kurulu bir Chrome/Chromium kullanır (yoksa `plotly_get_chrome` komutuyla
indirilebilir). 3B görseller etkileşimli sayfadan yakalandığı ve sayfa three.js'i CDN'den yüklediği için
bu adım **internet bağlantısı** gerektirir; `docs/index.html`'i görüntülemek için de internet gerekir.

### Komut satırı seçenekleri

| Seçenek | Varsayılan | Açıklama |
|:---|:---|:---|
| `--no-images` | kapalı | PNG/GIF üretmez, Chrome gerekmez; metrikler, sağlamlık tablosu, günlük ve etkileşimli sayfa yine yazılır |
| `--trials N` | 20 | sağlamlık testinde her deney ailesi için deneme sayısı; `0` testi atlar |
| `--out DIR` | `outputs/` | çıktı klasörü |
| `--docs DIR` | `docs/` | etkileşimli sayfanın klasörü |
| `--capacity K` | 2 | ayrıt kapasitesi |
| `--clearance M` | 0.05 | yasak hacim güvenlik payı [m] |
| `--order STR` | `input` | kablo önceliklendirme stratejisi (`input`, `critical-first`, `longest-first`, `shortest-first`) |
| `--workers N` | Linux'ta 4, Windows/macOS'ta 1 | sağlamlık testi için paralel işlem sayısı; sonuç işçi sayısından bağımsızdır |

Örneğin yalnızca metrikleri ve sayfayı birkaç saniyede üretmek için:

```bash
python main.py --no-images --trials 0
```

Konsol çıktısının tamamı `outputs/run_log.txt` dosyasına da yazılır (yerel klasör yolları içermez).

### Testler ve sürekli entegrasyon

```bash
pip install -r requirements-dev.txt
```

```bash
pytest
```

[`tests/`](tests) altında 45 test vardır (~12 s; biri isteğe bağlıdır, aşağıya bakınız):

- **Denetimler** (`test_checks.py`): çember yarıçapı, yeniden örnekleme, EMC, bükülme, kapasite,
  yasak hacim ve güvenlik payı sayımları elle hesaplanabilen küçük örneklerde doğrulanır.
- **Geometri ve çizge** (`test_geometry_graph.py`): büyütülmüş hacmin güvenlik payı komşuluğunu
  kapsaması, rotalanabilir düğümlerin paya uyması, hiçbir ayrıtın hacme girmemesi, bağlılık, simetri;
  vektörel ayrıt aramasının yönden bağımsız olması ve komşu olmayan düğümlerde hata vermesi; uçların doğru
  ekipmana atanması.
- **Rotalama** (`test_routing.py`): her yolun geçerli olması (doğru uçlar, gerçek ayrıtlar);
  baseline'ın networkx ile aynı uzunluğu bulması; dönüş çizgesinde U dönüşü ve keskin dönüş
  olmaması; e) yönteminin tüm denetimleri geçmesi; söküp yeniden rotalamanın rastgele sıralarda
  EMC ihlalini sıfırda tutması; Lagrange alt sınırının hiç azalmaması ve üst sınırı geçmemesi;
  uygun çözüm yokken Lagrange'ın NaN üretmeden temiz hata vermesi; sıralama stratejilerinin doğru sıralaması
  ve geçersiz stratejide hata vermesi.
- **Dışa aktarım** (`test_export.py`): kablo listesinin sütunları ve kablo numaraları; doğrulama paylarının
  bağımsız denetimlerle tutarlı olması; `routes.json`'un kompakt, eksiksiz ve byte düzeyinde deterministik olması.
- **Sağlamlık testi** (`test_benchmark.py`): uç nokta sapmasının farklı sınıftan uçları ayrım
  mesafesinin altına düşürmemesi; özet tablonun yapısı; **paralel çalıştırmanın sıralı çalıştırmayla aynı
  sonucu vermesi**; sağlamlık testindeki her yöntem tanımının çalışması.
- **Görüntüleyici** (`test_viewer.py`): üretilen sayfanın tek başına çalışır olması (bütün parçalar gömülü);
  `viewer.js`'in Node ile sözdizimi denetimi (Node yoksa atlanır); görüntüleyicinin okuduğu her `D.<alan>`'ın
  Python'un gömdüğü veride bulunması; `capture.py`'nin çağırdığı her `window.viewer` fonksiyonunun var olması.
  İsteğe bağlı bir test, sayfayı başsız Chrome'da açıp beş yöntemi gezer ve hiçbir JavaScript hatası olmadığını
  doğrular (Chrome ve internet gerektirir: `HARNESS_BROWSER_TESTS=1 pytest`).
- **Regresyon** (`test_regression.py`): yayımlanan metrik tablosunun (aşağıda) aynen üretilmesi.
- **Uçtan uca** (`test_cli.py`): `main.py --no-images` tüm dosyaları yazar, PNG üretmez, günlükte
  yerel yol yoktur, JSON geçerlidir ve sayfaya gömülen veri tutarlıdır.

Test, lint ve tip denetimi ayarları [`pyproject.toml`](pyproject.toml) içindedir. pytest `RuntimeWarning`
uyarılarını hataya çevirir; böylece NaN/sonsuz adımlar fark edilmeden geçemez. Kod [ruff](https://docs.astral.sh/ruff/)
ile denetlenir (`ruff check .`: pycodestyle, pyflakes, import sırası, bugbear, pyupgrade, simplify, ruff) ve
[mypy](https://mypy-lang.org/) ile tip denetiminden geçer (`mypy`; bulgu yok). Denetimler, hacimlerin yalnızca
şeklini bir `Protocol` ile tanımlar; böylece geometri modülünü içe aktarmadan da tip güvenli kalır.
GitHub Actions iş akışı ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) her push ve pull request'te
Python 3.11 ile lint'i, tip denetimini, testleri ve `python main.py --no-images --trials 3 --workers 2` duman
testini (paralel yol dahil) çalıştırır, çıktıları da artefakt olarak saklar.

### Görüntülerle ilgili teknik notlar

- **README'deki tüm 3B görseller etkileşimli sayfanın kendisinden yakalanır** (`harness_demo/capture.py`).
  Sayfa başsız Chrome'da yakalama modunda (`docs/index.html?capture`) açılır; bu modda yalnızca 3B görünüm
  gösterilir ve sayfa, yöntem seçmek, kamerayı yerleştirmek ve rotalama ilerlemesini ayarlamak için bir
  `window.viewer` arayüzü sunar. Chrome, kaleido'nun da kullandığı `choreographer` kütüphanesiyle
  DevTools protokolü üzerinden sürülür. Yani README'de görülen, sayfada etkileşimli olarak görülenle birebir aynıdır.
- Görsellerin başlıklarındaki sayılar sayfaya gömülü metriklerden gelir. Kırmızı noktalar, `checks.py`'nin
  bulduğu EMC ihlal noktalarının kendisidir (yakalama modunda daha görünür olmaları için iki kat büyük çizilir).
  Kod, her yöntem için nokta sayısının tablodaki değerle aynı olduğunu `assert` ile doğrular.
- Pillow yalnızca hazır ekran görüntülerini yan yana yerleştirmek ve GIF karelerini birleştirmek için kullanılır;
  piksel düzeyinde düzenleme yapılmaz. GIF'te kamera sabittir ve tüm kareler ortak bir palet kullanır
  (EMC sınıf renkleri palette garanti edilir). Böylece dosya yalnızca değişen bölgeleri saklar ve küçük kalır
  (~200 KB).
- Metrik grafiği ve Lagrange yakınsama grafiği plotly ile çizilir (`harness_demo/visualize.py`).
- Görüntüleyicinin kaynağı [`harness_demo/viewer/`](harness_demo/viewer) altında üç dosyadır: HTML iskeleti
  (`template.html`), stil (`viewer.css`) ve three.js kodu (`viewer.js`, bir ES modülü). `presentation.py` bunları
  verilerle birlikte tek bir `docs/index.html` dosyasına birleştirir; böylece sayfa hem GitHub Pages'te hem de
  dosyadan açıldığında çalışır. Sayfa, çalışma sırasındaki JavaScript hatalarını `window.__viewerErrors` içinde
  toplar; tarayıcı testi bunun boş kaldığını doğrular.

## Proje yapısı

```
harness_demo/
  geometry.py    # parametrik yarım silindir mesh'i + yasak hacimler (kutu, küre), güvenlik payıyla büyütme
  graph.py       # mesh -> rotalama çizgesi (networkx), yasak düğüm/ayrıt temizliği, CSR çıktısı
  scenarios.py   # 11 kablolu sentetik senaryo, EMC ayrım tablosu, ekipman konumları, uç nokta sapması
  routing/       # 5 rotalama yöntemi (dışarıya tek API: from harness_demo.routing import ...)
    core.py        # sonuç tipi, Dijkstra, güzergâh örnekleme, a) baseline
    turn_graph.py  # bükülmeyi bilen dönüş çizgesi
    sequential.py  # b) demetleme, c) EMC duyarlı, e) bütünleşik; söküp yeniden rotalama
    lagrangian.py  # d) Lagrange gevşetmesi
  checks.py      # bağımsız denetimler (rotalama kodunu kullanmaz) ve denetim ayarları
  metrics.py     # metrikler ve tablo biçimlendirme
  benchmark.py   # sağlamlık testi: rastgele kablo sırası ve uç nokta sapması (isteğe bağlı paralel)
  visualize.py   # 2B grafikler (plotly): metrik grafiği, Lagrange yakınsaması
  presentation.py# etkileşimli sayfa: görüntüleyiciyi ve sonuçları tek bir HTML dosyasına birleştirir
  viewer/        # three.js görüntüleyicinin kaynağı: template.html, viewer.css, viewer.js (yakalama modu dahil)
  capture.py     # README 3B görsellerini sayfadan başsız Chrome ile yakalar (PNG + GIF)
  export.py      # kablo listesi (wirelist.csv, doğrulama paylarıyla) ve 3B güzergâhlar (routes.json)
main.py          # uçtan uca çalıştırma: build_model -> route_all -> report_metrics -> write_exports
                 #   -> run_benchmark -> write_presentation; komut satırı seçenekleri
tests/           # pytest testleri (45 test; biri isteğe bağlı tarayıcı testi)
outputs/         # 3B görseller (PNG, GIF), 2B grafikler, wirelist.csv, routes.json, metrics.md, robustness.md,
                 # lagrangian_history.json, run_log.txt
docs/index.html  # GitHub Pages için tek sayfalık etkileşimli 3B görünüm
.github/workflows/ci.yml   # lint + tip denetimi + testler + duman testi
pyproject.toml   # pytest, ruff ve mypy ayarları
requirements.txt / requirements-dev.txt   # sabitlenmiş sürümler (geliştirme: pytest, ruff, mypy)
```

## Yöntemler

**a) Baseline.** Her kablo için ayrıt ağırlığı = Öklid uzunluğu olan çizgede bağımsız Dijkstra.

**b) Demetleme.** Kablolar senaryo sırasıyla rotalanır; başka bir kablonun kullandığı her
ayrıtın maliyeti 0,4 katsayısıyla düşürülür. Böylece sonraki kablolar mevcut güzergâhlara katılır.

**c) EMC duyarlı demetleme.** (b)'ye ek olarak, bir kablonun güzergâhına
`ayrım mesafesi + 0,03 m` mesafedeki düğümler, diğer EMC sınıfları için "riskli" işaretlenir.
Bu komşuluk `scipy.spatial.cKDTree.query_ball_point` ile yalnızca güzergâhın çevresinde
hesaplanır. Farklı sınıftan bir kablo, riskli düğüme dokunan ayrıtlarda ek ceza öder.
Ceza yumuşaktır: gerekirse ihlal edilebilir, ama pahalıdır.

Sıralı rotalama kablo sırasına bağlıdır: bir kablo yalnızca kendinden önce rotalananları "görür".
Bu yüzden ilk geçişin ardından **söküp yeniden rotalama** (rip-up and reroute) yapılır.
Rotalayıcı kendi çakışma ölçüsüyle (ayrım mesafesinin altına düşen örnek noktalar ve varsa
kapasitesi aşılan ayrıtlar) çakışan kabloları bulur. Bu kabloları, en çok çakışandan başlayarak
sırayla söker ve yeniden rotalar; bu kez **diğer tüm** kabloları görür ve EMC cezası her turda
iki katına çıkar. Çakışma kalmayınca ya da tur sınırına gelince durur. Görülen en iyi çözüm
döndürülür, böylece yeniden rotalama sonucu hiçbir zaman kötüleştiremez. (Rotalayıcının çakışma
ölçüsü yalnızca neyin yeniden rotalanacağına karar verir; raporlanan metrikler bağımsız
denetimlerden gelir.)

**d) Basitleştirilmiş Lagrange gevşetmesi.** Çözülen model şudur:

```
min  Σ_k uzunluk(P_k)              (P_k: k. kablonun yolu)
s.t. yük_e = |{k : e ∈ P_k}| ≤ K   her ayrıt e için
```

Kapasite kısıtı λ_e ≥ 0 çarpanlarıyla amaç fonksiyonuna taşınır:

```
L(λ) = Σ_k SP_k(w + λ) − K · Σ_e λ_e
```

Böylece problem her kablo için bağımsız bir en kısa yol alt problemine ayrışır ve L(λ) her
λ için optimumun **alt sınırıdır**. λ, Polyak adım boyuyla izdüşümlü subgradient
(`g_e = yük_e − K`) ile güncellenir. Her iterasyonda, kapasitesi dolan ayrıtları kapatarak
`w + λ` maliyetleriyle sıralı rotalayan bir onarım sezgiseli uygun bir çözüm, yani **üst sınır**
üretir. Alt ve üst sınır her iterasyonda kaydedilir.

Polyak adımı hedef değer olarak en iyi üst sınırı kullanır. Henüz uygun çözüm bulunmamışsa
(üst sınır sonsuzsa) hedef, en iyi alt sınırın %5 üstü alınır. Böylece adım her zaman sonludur.
(Önceki sürümde bu durumda adım sonsuz olup çarpanlar NaN'a dönüşüyordu; bir test bu durumu korur.)
Bilinmeyen sınırlar `lagrangian_history.json` dosyasına `null` olarak yazılır.

> Bu, asıl projedeki formülasyonun **basitleştirilmiş** halidir: burada amaç yalnızca
> toplam kablo uzunluğudur ve demetleme (paylaşılan ayrıtın bir kez ödenmesi) modelde yoktur.
> Asıl projede amaç kapasiteli Steiner ormanı yapısını, EMC kısıtlarını ve düğüm seçim
> maliyetlerini içerecektir.

**e) Bütünleşik yöntem (EMC + kapasite + bükülme).** (c)'nin demetleme, EMC cezası ve söküp yeniden
rotalama mantığı, bükülmeyi bilen bir **dönüş çizgesi** üzerinde çalıştırılır:

- **Bükülme sert kısıttır.** Dönüş çizgesinin her durumu yönlü bir ayrıttır (u→v); bir geçiş
  (u→v)→(v→w) ancak w ≠ u ise ve u, v, w'den geçen çemberin yarıçapı minimum bükülme yarıçapından
  küçük değilse vardır. Bu, bağımsız bükülme denetiminin test ettiği koşulun ta kendisidir. Bu yüzden
  bulunan her yolun bükülme ihlali yapısal olarak 0'dır. Bu senaryoda 109 924 olası dönüşün %53'ü
  (90°'lik dönüşler gibi) elenir, 51 544'ü kalır. Bir durumun maliyeti o ayrıta girerken ödenir.
  Sanal kaynak, başlangıç düğümünden çıkan tüm ayrıtlara; bitiş düğümüne giren tüm ayrıtlar ise
  sanal hedefe bağlanır, böylece uçlarda dönüş kısıtı yoktur (konnektör).
- **Kapasite**, dolu bir ayrıtta (başka K kablo taşıyan) uzunluğun 1000 katı ek maliyetle
  pratikte serttir. Ama geometri izin vermezse rotalama başarısız olmaz; ihlal raporlanır.
- **EMC ve demetleme** (c)'deki gibidir. Söküp yeniden rotalama kapasite çakışmalarını da hesaba katar
  ve en çok 10 tur sürer.

## Bağımsız denetimler

`checks.py` rotalama modülünü veya çizgeyi kullanmaz; yalnızca düğüm listelerini ve köşe
koordinatlarını alıp her şeyi geometriden yeniden hesaplar:

- **EMC ihlali:** Güzergâhlar 0,05 m aralıkla yeniden örneklenir. Bir örnek nokta, farklı
  sınıftan bir güzergâha gereken ayrım mesafesinden yakınsa ihlal sayılır (her ihlal eden
  güzergâh için bir kez). Birim: nokta.
- **Bükülme:** Ardışık üç köşeden geçen çemberin yarıçapı 0,10 m'den küçükse ihlal (yaklaşık bir ölçüt).
- **Yasak hacim:** 0,05 m aralıklı örnek noktalardan biri bir kutu/küre içindeyse ihlal.
- **Güvenlik payı:** Bir örnek nokta hacmin dışında ama ona 0,05 m'den yakınsa ihlal. Uzaklık
  hacmin ham parametrelerinden tam olarak hesaplanır (kutuya Öklid uzaklığı, küre yüzeyine uzaklık).
  Denetimin gerçekten çalıştığını göstermek için `main.py`, baseline'ı güvenlik payı **olmadan**
  kurulan çizgede de rotalar: bu durumda 69 güvenlik payı ihlal noktası çıkar.
- **Kapasite:** K'dan fazla kablo taşıyan ayrıt sayısı.

## Sonuçlar

`python main.py` çıktısı (`outputs/metrics.md` ile aynı):

| Yöntem | Toplam uzunluk [m] | Benzersiz uzunluk [m] | Demetlenme oranı | EMC ihlali [nokta] | Bükülme ihlali | Yasak hacim ihlali | Boşluk payı ihlali [nokta] | Kapasite ihlali [ayrıt] | Süre [s] |
|:---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| a) Baseline (bağımsız Dijkstra) | 61.66 | 51.65 | 0.162 | 980 | 0 | 0 | 0 | 20 | 0.00 |
| b) Demetleme | 71.84 | 17.80 | 0.752 | 5660 | 15 | 0 | 0 | 116 | 0.01 |
| c) EMC duyarlı demetleme | 66.18 | 35.22 | 0.468 | 0 | 8 | 0 | 0 | 35 | 0.03 |
| d) Lagrange gevşetmesi (K=2) | 61.76 | 53.80 | 0.129 | 887 | 0 | 0 | 0 | 0 | 0.74 |
| e) Bütünleşik (EMC + kapasite + bükülme) | 66.05 | 40.80 | 0.382 | 0 | 0 | 0 | 0 | 0 | 0.06 |

![Demetlenme oranı, EMC ihlali ve kapasite ihlali, yöntem başına](outputs/metrics_chart.png)

Lagrange: 60 iterasyon (iterasyon sınırı); alt sınır 61,7624 m, üst sınır 61,7639 m, fark 0,0014 m (%0,002).
Demetlenme oranı = 1 − benzersiz uzunluk / toplam uzunluk. Süreler yalnızca rotalama
süresidir (denetim ve çizim hariç); makineye göre değişir.

### Yorum

- **Baseline** en kısa toplam uzunluğu verir ama kabloları neredeyse hiç demetlemez (0,162).
  Buna rağmen 980 EMC ihlal noktası vardır: komşu uç noktalardan çıkan en kısa yollar yasak
  hacimlerin kenarında birbirine yaklaşır. EMC farkındalığı olmayan "sadece en kısa yol"
  yaklaşımı bu yüzden yeterli değildir.
- **Demetleme** benzersiz güzergâh uzunluğunu 51,7 m'den 17,8 m'ye indirir (oran 0,752).
  Bunun bedeli toplam kablo uzunluğunda ~%17 artış ve EMC ihlallerinde büyük bir artıştır
  (5660 nokta), çünkü farklı sınıftan kablolar aynı ayrıtları paylaşır. Kapasite ihlali (116 ayrıt)
  ve bükülme ihlali (15) de en yüksektir.
- **EMC duyarlı demetleme** bu senaryoda EMC ihlalini sıfıra indirirken demetlenme oranını
  0,468'de tutar: kablolar sınıf içinde demetlenir, sınıflar arasında ayrı güzergâhlar oluşur.
  Ancak kapasiteyi (35 ayrıt) ve bükülmeyi (8) gözetmez.
- **Lagrange** yöntemi baseline'ın 20 kapasite ihlalini yalnızca 0,11 m (%0,17) ek uzunlukla
  ortadan kaldırır. Alt ve üst sınır arasındaki fark 0,0014 m'dir (%0,002), yani bulunan çözüm bu
  basitleştirilmiş model ve bu çizge için optimuma en fazla 1,4 mm uzaktır. Modelde EMC ve demetleme
  olmadığından EMC ihlalleri baseline düzeyindedir.
- **Bütünleşik yöntem** beş denetimin hepsini aynı anda sağlayan tek yöntemdir: EMC, bükülme,
  yasak hacim, güvenlik payı ve kapasite ihlalleri 0'dır. Toplam uzunluğu (66,05 m) (c)'den bile
  biraz kısadır. Demetlenme oranı (0,382) (c)'den düşüktür, çünkü K = 2 bir ayrıtta en fazla iki
  kablo olmasına izin verir; bu bilerek dar seçilmiş kapasitenin doğal bedelidir.
- Hiçbir yöntem yasak hacim veya güvenlik payı ihlali üretmemiştir; çizgeden büyütülmüş hacimlerin
  içindeki düğümler ve onları kesen ayrıtlar çıkarıldığı için bu beklenen sonuçtur ve bağımsız
  denetimle doğrulanmıştır.

### Sağlamlık testi: sonuç kablo sırasına mı bağlı?

Sıralı yöntemlerde tek bir "0 ihlal" sonucu şans olabilir. `benchmark.py` bunu iki deney ailesiyle
ölçer (her biri 20 deneme, `seed = 7`). **Rastgele sıra:** özgün senaryo, kablolar rastgele sırayla
rotalanır. **Uç nokta sapması:** ayrıca her uç nokta ±0,05 m eksenel ve ±1,5° çevresel kaydırılır.
Bu sınırlar, farklı sınıftan uçları ayrım mesafesinin altına düşürmeyecek kadar küçüktür (bir test
bunu doğrular). Tüm denemeler bağımsız denetimlerle ölçülür (`outputs/robustness.md`):

| Deney | Yöntem | EMC ihlali 0 olan | EMC ort. / en çok [nokta] | Kapasite ort. / en çok [ayrıt] | Bükülme en çok | Tüm denetimler temiz |
|:---|:---|---:|---:|---:|---:|---:|
| Rastgele sıra | c) tek geçiş | 6/20 | 24.1 / 72 | 59.1 / 116 | 13 | 0/20 |
| Rastgele sıra | c) + söküp yeniden rotalama | 20/20 | 0.0 / 0 | 70.7 / 116 | 18 | 0/20 |
| Rastgele sıra | e) Bütünleşik | 16/20 | 1.6 / 10 | 0.0 / 0 | 0 | 16/20 |
| Rastgele sıra + uç nokta sapması | c) tek geçiş | 7/20 | 15.8 / 55 | 57.5 / 108 | 10 | 0/20 |
| Rastgele sıra + uç nokta sapması | c) + söküp yeniden rotalama | 20/20 | 0.0 / 0 | 52.4 / 110 | 16 | 0/20 |
| Rastgele sıra + uç nokta sapması | e) Bütünleşik | 20/20 | 0.0 / 0 | 0.0 / 0 | 0 | 20/20 |

- Söküp yeniden rotalama olmadan (c) yalnızca 40 denemenin 13'ünde EMC açısından temizdir; özgün
  senaryodaki "0 ihlal" sonucu bu yüzden kısmen sıraya bağlıydı. Söküp yeniden rotalamayla
  40 denemenin 40'ında EMC ihlali 0'dır.
- (c) kapasite ve bükülmeyi hiçbir sırada gözetmez; bu yüzden hiçbir denemede tüm denetimlerden temiz geçmez.
- (e) 40 denemenin 36'sında beş denetimin hepsinden temiz geçer. Bükülme ve kapasite her denemede
  sağlanır. Kalan 4 denemede (hepsi özgün uç noktalarla, rastgele sırada) en fazla 10 EMC ihlal
  noktası kalır: dar kapasite, bükülme kısıtı ve EMC ayrımı birlikte bazı sıralarda çakışır.
  Ceza yumuşak olduğundan sıfır ihlal garanti değildir.

### Kablo önceliklendirme stratejileri (`--order`)

Sıralı yöntemlerin (b, c, e) ilk geçişi hangi sırayla yapacağı `--order` ile seçilebilir: `input` (senaryo
sırası, varsayılan), `critical-first` (önce power, sonra data, sonra signal; sınıf içinde uzun kablo önce),
`longest-first` ve `shortest-first` (uç noktalar arasındaki düz mesafeye göre). Bu senaryoda bağımsız
denetimlerle ölçülen sonuç:

| Strateji | c) EMC / kapasite / bükülme | c) toplam uzunluk | e) EMC / kapasite / bükülme | e) toplam uzunluk |
|:---|:---:|---:|:---:|---:|
| `input` | 0 / 35 / 8 | 66,18 m | 0 / 0 / 0 | 66,05 m |
| `critical-first` | 0 / 93 / 9 | 72,07 m | 0 / 0 / 0 | 72,00 m |
| `longest-first` | 0 / 93 / 9 | 72,07 m | 0 / 0 / 0 | 72,00 m |
| `shortest-first` | 0 / 110 / 9 | 79,46 m | 0 / 0 / 0 | 76,73 m |

Bütünleşik yöntem her stratejide tüm denetimlerden temiz geçer; ancak bu senaryoda hiçbir strateji varsayılan
sıradan iyi değildir: kablolar 6–11 m uzar ve (c)'nin kapasite ihlali artar. (`critical-first` ve
`longest-first` farklı sıralar üretse de söküp yeniden rotalamadan sonra c) ve e) için aynı çözüme varır.)
Sıra bağımlılığını asıl azaltan, yukarıdaki sağlamlık testinin gösterdiği gibi söküp yeniden rotalamadır;
stratejiler deneme için bir seçenektir.

## Dışa aktarım: kablo listesi ve güzergâh dosyası

`python main.py` iki makine-okunur dosya da yazar ([`harness_demo/export.py`](harness_demo/export.py)).

**[`outputs/wirelist.csv`](outputs/wirelist.csv): kablo listesi.** Bütünleşik yöntemin (e) her kablosu için bir
satır. Bir üretim kablo listesi gibi uçları ve uzunluğu verir; ayrıca her kablonun kendi doğrulama paylarını
bağımsız denetimlerin yapı taşlarıyla geometriden yeniden hesaplar:

| Sütun | Anlamı |
|:---|:---|
| `wire_id`, `cable_name`, `emc_class` | kablo numarası (W01…), adı, EMC sınıfı |
| `from_location`, `to_location` | bağlandığı ekipman, ör. `Arka raf (sağ)` → `Ön panel (sol)` |
| `from_node`, `from_x_m` … `to_z_m` | uç düğümler ve koordinatları [m] |
| `length_m`, `waypoint_count` | güzergâh uzunluğu ve nokta sayısı |
| `bundled_with`, `shared_length_m`, `sharing_ratio` | yol paylaştığı kablolar, ortak uzunluk ve oranı |
| `min_emc_margin_m` | farklı sınıftan en yakın kabloya uzaklık − gereken ayrım; < 0 ise EMC ihlali |
| `min_bend_radius_m` | güzergâhtaki en küçük üç nokta çember yarıçapı; < 0,10 m ise bükülme ihlali |
| `min_keepout_distance_m` | yasak hacimlere en küçük uzaklık; < 0,05 m ise güvenlik payı ihlali |
| `status` | tüm paylar sağlanıyorsa `OK`, değilse `CHECK` |

Bu senaryoda 11 kablonun 11'i `OK`'dir. Örnek satırlar:

| Kablo | Nereden → nereye | Uzunluk | Demet | EMC payı | En küçük R | Yasak hacme | Durum |
|:---|:---|---:|:---|---:|---:|---:|:---:|
| W01 P1 (power) | Arka raf (sağ) → Ön panel (sağ) | 5,82 m | P2 | +13,1 cm | 0,122 m | 9,3 cm | OK |
| W05 D1 (data) | Arka raf (sağ) → Ön panel (sağ) | 5,53 m | D2, D3 | +3,9 cm | 0,142 m | 7,7 cm | OK |
| W10 D3 (data) | Arka raf (sağ) → Ön panel (sol) | 6,33 m | D1 | +8,7 cm | 0,112 m | 8,1 cm | OK |
| W11 S4 (signal) | Arka raf (sol) → Ön panel (sağ) | 7,86 m | S2, S3 | +3,9 cm | 0,119 m | 8,9 cm | OK |

En sıkışık EMC payı +3,9 cm'dir (D1 ile S4 arasında). Paylar bir testle bağımsız denetimlere bağlanmıştır:
bütünleşik çözümde hepsi `OK`'dir, demetleme çözümünde ise EMC payı negatif olan kablolar tam olarak `CHECK`
işaretlenir. Aynı paylar 3B sayfadaki bilgi kutusunda da gösterilir.

**[`outputs/routes.json`](outputs/routes.json): bütün güzergâhlar.** Beş yöntemin bütün kabloları; CAD/ECAD'e
veya başka analizlere aktarmak için. Her kablo için `waypoints_xyz` (gövde yüzeyindeki mesh köşelerinden geçen
3B kırık çizgi, metre), `node_ids`, uçların ekipmanı, uzunluk ve demet bilgisi; her yöntem için rotalama sırası
ve denetim sonuçları; ayrıca çalıştırma parametreleri (kapasite, bükülme yarıçapı, güvenlik payı, ayrım tablosu,
sıralama stratejisi), birim ve koordinat sistemi. Noktalar denetimlerin değerlendirdiği ham güzergâhtır;
3B sayfadaki kaldırılmış ve yumuşatılmış görünüm yalnızca görseldir ve dosyada yoktur.

Dosya kompakt ve deterministiktir: her dizi tek satırdadır (~700 satır, ~110 KB; önceki sürüm ~20 000 satır,
~395 KB'tı) ve içinde süre gibi çalıştırmaya bağlı bir değer yoktur. Aynı girdiyle her çalıştırma byte düzeyinde
aynı dosyayı üretir (bir test bunu doğrular), bu yüzden git'te yalnızca gerçek değişiklikler görünür.

## Performans

Hesap çekirdeği profil çıkarılarak hızlandırılmıştır. Sonuçlar **bit düzeyinde aynıdır**: regresyon testlerine
ek olarak örnekleme fonksiyonları ve beş yöntemin bütün güzergâhları eski sürümle karşılaştırılarak doğrulandı.

- Güzergâh örnekleme (`routing.densify`, `checks.resample_polyline`) ve bükülme denetimi Python döngüleri
  yerine vektör işlemleriyle yapılır; numpy'nin `linspace` aritmetiği birebir korunur. (İki örnekleme
  fonksiyonu bilerek ayrıdır: denetimler, doğruladıkları rotalama koduna bağımlı olmamalıdır.)
- Sıralı rotalamada her kablo ve her yeniden rotalama turu için tekrar hesaplanan güzergâh geometrisi
  (benzersiz ayrıtlar, örnek noktalar, KD-ağaçları, yakın düğümler) güzergâhın kendisine göre önbelleğe alınır.
- Ayrıt araması, sözlük yerine sıralı anahtarlar üzerinde `searchsorted` ile vektörel yapılır.
- 2B grafikler için başsız tarayıcı yalnızca grafik çizilirken açılır; raporlanan rotalama sürelerini etkilemez.

| | Önce | Sonra |
|:---|---:|---:|
| Sağlamlık testi (40 deneme × 3 yöntem) | 28–41 s | 9–18 s |
| `python main.py --no-images` | 30–45 s | 10–21 s |
| `python main.py` (tüm çıktılar, görseller dahil) | ~65 s | ~40 s |

Ölçümler aynı dizüstü bilgisayarda ardışık çalıştırmalardır; mutlak süreler makinenin yüküne göre değişir, ama
hızlanma her karşılaştırmada 2–3 kattır.

**Paralel sağlamlık testi.** Denemeler birbirinden bağımsız olduğu için `--workers N` ile ayrı işlemlerde
çalışabilir. Denemeler ana işlemde çekildiği için sonuç işçi sayısından bağımsızdır (bir test bunu doğrular).
Ancak kazanç platforma bağlıdır. Windows'ta (ve macOS'ta) işlemler `spawn` ile başlar ve her işçi numpy, scipy,
networkx ve trimesh'i baştan yükler (~1,5–2 s/işçi). Bu, ~10 s'lik bir testte kazancın çoğunu yer: bu makinede
sıralı 10,2 s, 4 işçiyle 8,8 s ölçüldü. İş parçacıkları da GIL yüzünden yalnızca ~1,3 kat hızlandırdığı için
kullanılmadı. Bu yüzden varsayılan değer Windows/macOS'ta 1, işlemlerin ucuzca `fork` edildiği Linux'ta 4'tür.
Linux'taki hızlanma bu makinede ölçülemedi; CI paralel yolu Linux'ta doğruluk için çalıştırır.

Kalan sürenin çoğu scipy'nin Dijkstra algoritmasında (çağrı başına ~0,5 ms) ve görsellerin yakalanmasındadır.

## Tüm yöntemler

| a) Baseline | b) Demetleme |
|:---:|:---:|
| ![Baseline](outputs/routes_baseline.png) | ![Demetleme](outputs/routes_bundled.png) |
| **c) EMC duyarlı demetleme** | **d) Lagrange gevşetmesi** |
| ![EMC duyarlı](outputs/routes_emc_aware.png) | ![Lagrange](outputs/routes_lagrangian.png) |
| **e) Bütünleşik** | |
| ![Bütünleşik](outputs/routes_integrated.png) | |

![Lagrange yakınsaması](outputs/lagrangian_convergence.png)

Tüm görseller aynı kameradan, gövdeye alttan bakılarak etkileşimli sayfadan yakalanmıştır
([`docs/index.html`](docs/index.html), beş yöntem tek sayfada). Görsellerde demet ekseni yüzeyden ~10 cm
kaldırılır, aynı güzergâhı paylaşan kablolar demet içinde yan yana dizilir ve köşeler yumuşatılır; bunlar
yalnızca görseldir, denetimlere ve metriklere girmez. Frame, stringer, kelepçe, konnektör ve ekipman rafları
da görseldir.

## Asıl projede nasıl genişletilir

- **Kapasiteli Steiner ormanı:** Her ayrıt bir kez "açılır" (kanal/destek maliyeti) ve
  üzerinden geçen kablolar kapasiteyle sınırlanır. Bu, demetlemeyi sezgisel indirim yerine
  doğrudan amaç fonksiyonunda temsil eder. Lagrange gevşetmesiyle alt problemler yine en kısa
  yol / Steiner ağacı problemlerine ayrışır; bu alt problemler bükülmeyi bilen dönüş çizgesi
  üzerinde çözülebilir.
- **EMC'nin Lagrange çerçevesine katılması:** Bütünleşik yöntemdeki EMC cezası, ayrım kısıtları
  için ayrı çarpanlarla gevşetilerek sezgisel ceza yerine alt sınır üreten bir modele dönüştürülebilir.
- **Düğüm seçim maliyeti:** Dallanma noktaları, geçiş delikleri ve bağlantı noktaları için
  düğüm maliyetleri; demet ayrılma/birleşme noktalarının sayısının kontrolü.
- **Ekranlama aktif bir rotalama değişkeni olarak:** Ekranlı/ekransız seçim, ayrım mesafesi
  gereksinimini değiştiren ve maliyeti/ağırlığı olan bir karar değişkeni olarak modele girer.
- **Kelepçe aralığı:** Güzergâh boyunca destek noktalarının izin verilen aralıkta
  yerleştirilebilmesi; uygun yapısal bağlantı noktalarına yakınlık.
- **Kablo sırası:** Sağlamlık testi, sıralı yöntemlerin sıraya duyarlılığını ölçer; `--order` ile denenen basit
  sıralama sezgiselleri bu senaryoda varsayılan sıradan iyi sonuç vermemiştir. Asıl projede tamamen eşzamanlı
  (Lagrange tabanlı) yöntemler bu bağımlılığı azaltabilir.
- **Gerçek geometri ve CAD'e aktarım:** Gerçek mesh/CAD verisinin içe alınması, sonuç
  güzergâhların CAD ortamına (ör. STEP/çizgi geometrisi) geri aktarılması. `routes.json` bunun ilk adımıdır:
  güzergâhları birimi ve koordinat sistemi belirtilmiş 3B kırık çizgiler olarak verir.

## English summary

This repository is a small, simplified prototype for **EMC-aware automatic routing of
aircraft wire harnesses on a 3D fuselage mesh**. Full English documentation: [README.en.md](README.en.md).
A half-cylinder section (R = 2 m, L = 6 m) is triangulated, three keep-out volumes plus a 0.05 m
clearance are removed from the routing graph, and 11 synthetic cables are routed with five methods:
independent Dijkstra, sequential bundling, EMC-aware bundling with rip-up-and-reroute, a simplified
Lagrangian relaxation of edge capacity, and an integrated method on a turn-aware graph that satisfies
EMC separation, capacity, bend radius, keep-out and clearance at the same time (bundling ratio 0.382).
Independent checks recompute every violation, a 40-trial robustness benchmark measures order and
terminal sensitivity, a wirelist with per-cable verification margins and all routes as 3D polylines are exported,
and 45 pytest tests plus ruff lint and mypy type checks run in CI with pinned dependencies.

---

Geliştirmede yapay zekâ destekli araçlar kullanılmıştır; tasarım kararları ve doğrulama ekibimize aittir.
