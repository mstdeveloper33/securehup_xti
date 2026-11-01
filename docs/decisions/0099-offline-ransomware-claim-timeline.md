# 0099 — Ağsız ransomware iddia zaman çizelgesi

**Durum:** Kabul edildi  
**Tarih:** 30 Ekim 2026

## Karar

`ransomware watch-timeline IZLEME_KIMLIGI`, seçilen izlemenin güncel kuruluş/domain tanımını bütün denetlenmiş yerel ransomware snapshot fark geçmişine uygular. Komut internete bağlanmaz, yeni izleme çalışması oluşturmaz ve okuma sırasında veritabanını değiştirmez. Geri çekilmiş izleme tanımı da tarihsel araştırma için kullanılabilir.

Kaynak claim kimliği, kaynak grup adı + kuruluş adı + kaynak keşif zamanının kanonik özetidir. Aynı kimlik bir sonraki başarılı snapshot'ta değişmeden bulunuyorsa yeni olay üretilmez; tekrar gözlem sayacı artar. Aynı kimlik kaynak penceresinden çıktıktan sonra geri gelirse yeni claim yerine `reappeared` olayı üretilir.

Olay türleri şunlardır:

- `first_seen`: kimlik kayıtlı kaynak döneminde ilk kez güncel tanımla eşleşti.
- `updated`: eşleşen claim'in güvenli kaynak alanları değişti.
- `match_started`: mevcut claim güncelleme sonrasında özellikle domain tanımıyla eşleşmeye başladı.
- `match_ended`: mevcut claim güncelleme sonrasında artık tanımla eşleşmiyor.
- `removed`: eşleşen claim kayan kaynak snapshot penceresinden çıktı.
- `reappeared`: daha önce eşleşmiş aynı claim kimliği yeniden kaynak penceresine girdi.

Kompakt kaynak geçmişi değişmeyen claim satırlarını her snapshot'ta çoğaltmaz. Uygulama aktif claim ve aktif eşleşme kümelerini kaynak çalışma sırasıyla yeniden kurar. Her başarılı snapshot'ta değişiklik görmeyen aktif eşleşmeler tekrar gözlem sayılır. Başarısız kaynak çalışması claim durumunu veya tekrar sayısını değiştirmez ve ayrı hata kapsamı olarak raporlanır.

Gösterim sınırı yalnız dönen son olayları daraltır; bütün sınırlı yerel geçmiş önce doğrulanır ve toplamlar tam kapsamdan hesaplanır. Çıkarma kanıtındaki claim durumu, çıkarma öncesindeki aktif durumla aynı olmak zorundadır; farklıysa geçmiş bozuk kabul edilir.

## Sınırlar

Zaman çizelgesi yalnız cihazda saklanan snapshot dönemini kapsar. `discovered_at` kaynağın verdiği iddia zamanıdır; XTI'nin ilk yerel gözlem zamanı değildir. Güncel izleme tanımı geçmişe geriye dönük uygulanır; önceki tanım sürümlerinin o tarihteki davranışı gibi sunulmaz. Kaynak grup, kuruluş veya keşif zamanını değiştirirse aynı gerçek olay ayrı kimlik gibi görünebilir; otomatik benzerlik birleştirmesi yapılmaz. Pencereden çıkış, `delisted` veya eşleşmenin bitmesi iddianın yanlışlandığını, ödemenin yapıldığını ya da olayın çözüldüğünü kanıtlamaz. Bütün kayıtlar doğrulanmamış kamu iddiasıdır.
