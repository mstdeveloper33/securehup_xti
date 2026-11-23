# ADR 0188 — CTI çıkarımları hüküm değil, sürümlü inceleme adayıdır

21 Kasım 2026. P04 uygulanmadan önce kabul edildi.

CTI analiz katmanı yeni bir hakikat deposu oluşturmayacaktır. Özgün CTI/IOC
iddiaları ve MITRE ATT&CK kataloğu değişmeden kalır; entity-resolution, TTP,
atıf, etiket ve kuruluş önceliği sonuçları bunlara başvuran değişmez analiz
kanıtlarıdır. Bir adayın kabulü kaynak kaydı fiziksel olarak birleştirmez veya
özgün iddiayı yeniden yazmaz.

Confidence; kaynak güveni, kaynağın beyan ettiği confidence, güncellik ve
bağımsız kaynak desteğinden oluşan açıklanabilir bir inceleme ölçüsüdür. Risk
olasılığı veya zararlılık yüzdesi değildir. Kaynak güven kuralları firma
profilinde sürümlenir; yeni eşik geçmiş turun anlamını değiştirmez.

ATT&CK TTP önerisi yalnız açık teknik kimliği/metin parçası ya da insanın
`same_entity` olarak kabul ettiği CTI↔ATT&CK kimliği ile resmî `uses` ilişkisi
üzerinden oluşur. Etiketler kontrollü sözlük ve özgün alıntıyla `source_claim`
olarak saklanır; ülke kökeni veya gerçek hedef sektör ilan edilmez.

Atıf adayı açık `attributed-to` ilişkisiyle veya en az iki farklı kanıt
ankrajı ve iki bağımsız kaynak grubuyla üretilebilir. Tek ortak IP, tek alias
veya tek kaynağın tekrarı atıf için yeterli değildir. Karşı kanıt ve eksik
kapsam aday gövdesinde görünürdür.

İlk tur sessiz baseline'dır. Trend yalnız aynı kaynak kapsamındaki turları
karşılaştırır; kaynak, ATT&CK sürümü veya profil değişimi ayrı `coverage_change`
olarak gösterilir. Bildirim, otomatik hüküm değil inceleme kuyruğu girdisidir.

Terminal, engine ve company platform aynı uygulama servisini çağırır. Firma
seçimi güvenilen platform başlatıcısındadır; JSON ile başka workspace seçilemez.
Veri modeli saklı geçmişi istek başına tavanla karıştırmaz, bütün listeleri
sequence cursor ve yanıt boyutu sınırıyla sayfalar.
