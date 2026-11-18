# 0165 — Pasif alt alan adayları ve insan sınıflandırmasını araştırmaya bağlama

18 Kasım 2026 · 0.161.0 · Uygulandı.

## İhtiyaç

Pasif keşif alt alan adayını ve karar geçmişini zaten saklıyordu; ortak
araştırma bu bilgiyi göstermiyordu. Arşivde bir adın geçmesi, insanın
`owned` kararı ve ayrıca verilmiş aktif kontrol onayı birbirinden ayrılmalı.

## Karar

- Yeni kaynak veya keşif çalıştırılmaz. `surface_candidates`, kaynakları
  ve olayları mevcut araştırmanın aynı SQLite okuma transaction'ında okunur.
  `research_discovery` saf dönüşüm/geçiş denetimini, `StoredDiscoveryLinks`
  seçili ve sınırlı okumayı yapar. Yeni bağımlılık veya şema geçişi yoktur.
- Kök domain → aday domain `passive_subdomain/candidate_context` bağıdır.
  Ayrı `subdomain_classification/human_decision` bağı insan kararlarını
  taşır. Otomatik ilk `discovered` olayı insan kararı sayılmaz.
  Böylece kök → aday → kayıtlı DNS IP'si iki adımda araştırılabilir.
- Başka kök altında aynı adın aday kaydı ve kararları ayrı kalır. Özgün
  yön korunur; ters arama yalnız kaydedilmiş bağlantıları okur. Salt ad
  son ekinden ilişki veya joker kaydından yeni host üretilmez.
- Pasif kanıtta özgün kaynak satırı kimliği, sağlayıcı, ham ad, URL ve
  kaynak SHA-256 korunur. Gözlem tarihi yoksa kayıt/alınma tarihi açıkça
  `response_received_at` olur. Aday özeti `stored_seen_range` kullanır;
  karar `decision_recorded_at` ile gösterilir. Yeni karar veya aynı kaydın
  yeniden keşfi eski kaynak zamanını güncellemez.
- İnsan kanıtında `current` son ilgili karardır; `owned`, `rejected` veya
  `pending` ayrıca okunur. Eski kararlar saklanır. Aktif varlık/kapsam
  tablolarına yazılmaz; reddetmek bağımsız aktif kapsamı da kendiliğinden
  kaldırmaz. Karar sahibi kimliği mevcut kayıtta yoksa üretilmez.
- Aday domain düğümünün `references` alanı mevcut
  `domain/surface_candidate/passive-discovery` `record.get` başvurusunu
  kullanır. Terminal özgün `surface candidate show` komutunu verir.
- Adayın tam seçili kaynak/karar zinciri, ilk keşfi, durum/gerekçe
  projeksiyonu, görülme aralığı ve kök kaydı kontrol edilir. Karar sırası
  olay ekleme sırasıdır; saat gerilemesi sırayı değiştirmez. Bugünkü IDNA
  kuralları tarihî ham ada yeniden uygulanmaz. Kaynak payload'ı bu tablolarda
  bulunmadığından SHA-256 içerikten tekrar hesaplanmış veya sağlayıcının
  imzası doğrulanmış sayılmaz; kaynak çalışması bağı tahmin edilmez.
- Düğüm başına 200 aday seçilir; her aday en fazla iki bağ verir. Mevcut
  araştırma genelindeki 100 düğüm/200 bağ/iki adım sınırları ayrıca işler.
  İstekte 10.000 satır/16 MiB ön kontrol ve aday başına mevcut 1.000 olay
  sınırı korunur. Bütçeye sığmayan geçmişin tamamı atlanır, kısmi kapsam
  açıklanır. Bozuk seçili veri `storage_error` olur.
- Bağ başına 50 kanıt gösterilir. Pasif özeti önce, kaynaklar gözlem/alınma
  zamanına göre en yeni önce; kararda son eklenen önce gelir. Toplamlar
  korunur. Eski arşiv kaydının geç ithali yeni gözlemi sınırın dışına itmez.

## Sürüm ve sınırlar

Araştırma/değerlendirme modeli 2, istek/zarf v1, çekirdek 75 ve kuyruk 2
kalır. Politika `research-priority-v4` olur. Eski incelemeler özgün okunur;
ilk v4 kaydı yeni politika başlangıcıdır. Yeni aday inceleme bekliyorsa
doğrulama gerekçesi olur; insanın `owned/rejected` kararı tehdit puanı değildir.

Keşif çalışmasının hata/boş sonucu bu görünümde adayı silmez veya kaynak
zamanını yenilemez. Güncel çalışma sağlığı mevcut keşif durumu komutunda
kalır. Sınıflandırma aktif izin değildir; mevcut kayıt tutarlılığı denetimi
imzalı veya bütün olası tarihçe silinmelerini kanıtlayan bir audit sistemi
değildir. Kaynak toplama, risk kartları, abonelik ve platform oturumu değişmez.

## Kabul

Kontrollü SQLite, terminal, engine/platform ve yedek testleri: kaynak/karar
ayrımı, yeniden keşif, karar düzeltme, ters yol, iki kök/iki firma ayrımı,
bozuk kayıt reddi, okuma bütçeleri, aynı kesitte okuma ve eski inceleme uyumu.
Sonuçlar [kabul belgesinde](../ACCEPTANCE_REVIEW.md) tutulur.
