# 0176 — Kaynak adaylarından kanıtlı sosyal profil sonucuna

Tarih: 19 Kasım 2026 · Durum: Uygulandı · Sürüm: 0.171.0 / şema81.

Canlı testte Maigret bir Instagram hesabını kaçırdı; Sherlock'un HackerNews
iddiası açık sayfayla çelişti. Bir araç çıktısını doğrudan hesap varlığı olarak
sunmak yerine şirket/domain keşfi, kaynak iddiası ve bağımsız profil kanıtı
aynı sonuçta ayrı tutulur. Firecrawl kullanıcı kararıyla ertelendi.

`SocialDiscoveryService`, toplama, kamuya açık sayfa ve makbuz depo portlarına
bağlıdır. Domain kuralları URL kimliğini, kapsamı, durumları ve karar kanıtını
doğrular. Pinned Maigret/Sherlock adaptörleri mevcut süreç sınırlarıyla kullanılır;
ikinci katman genel IP'ye sabitlenmiş HTTPS üzerinden çalışır. Tavily `advanced`
ve alan filtreleri yalnız açık web-search seçimiyle kullanılır; eski basic
firma araması payload/sözleşmesi korunur. Kaynak hataları diğer kanıtı silmez.

Şema81 tek yeni tablo/index ile önce işlem anahtarını ayırır, sonra tamamlanan
kanıtı atomik yazar. Replay anahtar/kapsam bazlıdır; kesintiden sonra otomatik
ağ tekrarı yoktur. Tamamlanmış rapor değiştirilmez; eski karar kuralı gerektiğinde
yeni policy/model ile genişletilir. Yedekli migration eski satırları korur.

CLI ve platform aynı servisi kullanır. Firma yazması workspace çiti ve yazıcı
kilidi ister. Engine okumaları ağsızdır. Platform manifesti, eşzamanlı ağ
çağırabilen işlemleri ayrıca listeler. İşin .NET/UI tarafında arka planda
çalıştırılması tüketici platformun sorumluluğudur; bu sürüm ayrı iş kuyruğu
veya web sunucusu eklemez.

Tamamlanmış profil doğrulaması otomatik sahiplik veya taklit kararı değildir.
Genel doğruluk yüzdesi yerine bilinen pozitif/negatif örnekler, erişilemeyen
kapsam, kaynak katkısı, gerçek süre, tekrar trafiği ve kredi belirsizliği ölçülür.
[Kullanım, sözleşme, sınırlar ve canlı kabul](../SOCIAL_DISCOVERY.md).
