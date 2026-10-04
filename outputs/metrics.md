# Metrikler

| Yöntem | Toplam uzunluk [m] | Benzersiz uzunluk [m] | Demetlenme oranı | EMC ihlali [nokta] | Bükülme ihlali | Yasak hacim ihlali | Kapasite ihlali [ayrıt] | Süre [s] |
|:---|---:|---:|---:|---:|---:|---:|---:|---:|
| a) Baseline (bağımsız Dijkstra) | 61.23 | 52.32 | 0.145 | 952 | 0 | 0 | 17 | 0.01 |
| b) Demetleme | 71.36 | 17.72 | 0.752 | 5572 | 15 | 0 | 116 | 0.01 |
| c) EMC duyarlı demetleme | 67.17 | 34.56 | 0.486 | 0 | 10 | 0 | 50 | 0.05 |
| d) Lagrange gevşetmesi (K=2) | 61.27 | 52.50 | 0.143 | 962 | 0 | 0 | 0 | 1.34 |

- Kapasite K = 2 kablo/ayrıt, minimum bükülme yarıçapı = 0.1 m, EMC ve yasak hacim denetimleri 0.05 m örnekleme ile.
- Lagrange: 56 iterasyon, alt sınır 61.27 m, üst sınır 61.27 m.
