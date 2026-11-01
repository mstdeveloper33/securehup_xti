# 0049 — Maruziyet kuyruğunda destek kanıtı bağlamı

## Durum

Kabul edildi — 29 Ekim 2026.

## Bağlam

Destek kanıtı incelemeye bağlı olsa da çalışma kuyruğu bunu göstermediğinde analist hangi
kayıtların dayanağı bulunduğunu görmek için her incelemeden ayrılmak zorunda kalır.
Kanıt sayısını öncelik puanına dönüştürmek ise çok sayıda zayıf başvuruyu tek güçlü
kanıttan daha önemli gösterebilir.

## Karar

- Kuyruk seçili incelemeleri, zafiyet kaynaklarını ve etkin destek kanıtlarını aynı
  salt-okunur SQLite transaction'ında okur.
- Her satır etkin kanıt sayısını ve tekil türlerini; üst özet kanıtlı inceleme ile etkin
  kanıt toplamını gösterir.
- Kanıt sayısı ve türü yeni dikkat nedeni oluşturmaz, sıralamayı veya dört öncelik bandını
  değiştirmez ve insan kararını yazmaz.
- Kapanmış ve bastırılmış filtreler kanıt sorgusuna da uygulanır; seçilmeyen incelemenin
  kanıtı sayılara karışmaz.
- Seçili etkin kanıtların tamamı en fazla 10.000 kayıt sınırında doğrulanır. Bozuk ilgili
  kanıt kısmi kuyruk üretmez.
- Ağ isteği, veri yazımı veya şema değişikliği yoktur; şema 22 korunur.

## Sonuçlar

Analist kuyruktan ayrılmadan dayanak bulunup bulunmadığını görür. Kanıt kalitesi, kaynak
güveni, güncellik ve çelişki politikası henüz sayısallaştırılmaz; bunlar güvenilir üretici
kaynağı ve backport çalışmasıyla ayrı tasarlanacaktır.
