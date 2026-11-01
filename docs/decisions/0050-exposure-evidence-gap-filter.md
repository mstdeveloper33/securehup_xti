# 0050 — Maruziyet destek kanıtı boşluk filtresi

## Durum

Kabul edildi — 29 Ekim 2026.

## Bağlam

Kuyrukta kanıt sayısını görmek tek tek incelemeyi kolaylaştırır; fakat çok sayıda kayıtta
hiç destek kanıtı olmayanları elle ayıklamak yeni bir iş yükü oluşturur. Bu boşluk bir
risk hükmü değildir, yalnız analistin tamamlaması gereken araştırma girdisidir.

## Karar

- `--evidence all` varsayılan tam seçimi, `present` en az bir etkin destek kanıtı olanı,
  `missing` hiç etkin destek kanıtı olmayanı gösterir.
- Filtre kapanmış ve bastırılmış kapsam seçiminden sonra, aynı salt-okunur anlık
  görüntüdeki doğrulanmış etkin kanıtlara uygulanır.
- Toplamlar ve bant sayıları yalnız son filtre kapsamına aittir; uygulanan filtre terminal
  ve JSON çıktısında açıkça taşınır.
- “Kanıt yok” zafiyet, etkilenme, yüksek risk veya kaynakta veri yok hükmü değildir.
  Filtre sıralamayı, bandı veya kalıcı insan kararını değiştirmez.
- Geçersiz değer depo ve saate erişmeden reddedilir. Ağ, yazma veya şema değişikliği
  yoktur; şema 22 korunur.

## Sonuçlar

Analist destek dayanağı eksik incelemeleri tek komutla çalışma listesine çevirebilir.
Hangi kanıt türünün zorunlu olduğu henüz politika değildir; güvenilir üretici/dağıtım
kaynağı ve backport modeli ayrı teslimdir.
