# Metrikler

| Yöntem | Toplam uzunluk [m] | Benzersiz uzunluk [m] | Demetlenme oranı | EMC ihlali [nokta] | Bükülme ihlali | Yasak hacim ihlali | Boşluk payı ihlali [nokta] | Kapasite ihlali [ayrıt] | Süre [s] |
|:---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| a) Baseline (bağımsız Dijkstra) | 61.66 | 51.65 | 0.162 | 980 | 0 | 0 | 0 | 20 | 0.01 |
| b) Demetleme | 71.84 | 17.80 | 0.752 | 5660 | 15 | 0 | 0 | 116 | 0.01 |
| c) EMC duyarlı demetleme | 66.18 | 35.22 | 0.468 | 0 | 8 | 0 | 0 | 35 | 0.05 |
| d) Lagrange gevşetmesi (K=2) | 61.76 | 53.80 | 0.129 | 887 | 0 | 0 | 0 | 0 | 1.08 |
| e) Bütünleşik (EMC + kapasite + bükülme) | 66.05 | 40.80 | 0.382 | 0 | 0 | 0 | 0 | 0 | 0.09 |

- Kapasite K = 2 kablo/ayrıt, minimum bükülme yarıçapı = 0.1 m, yasak hacim güvenlik payı = 0.05 m; EMC, yasak hacim ve boşluk denetimleri 0.05 m örnekleme ile.
- Lagrange: 60 iterasyon, alt sınır 61.7624 m, üst sınır 61.7639 m, fark 0.0014 m (%0.002).
- Güvenlik payı olmadan kurulan çizgede baseline 69 boşluk payı ihlali noktası üretir (boşluk denetiminin çalıştığını gösterir).
