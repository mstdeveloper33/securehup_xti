# 0087 — Eklemeli CTI avcılık etiketi ve analist defteri

## Durum

30 Ekim 2026 tarihinde kabul edildi.

## Bağlam

Kayıtlı CTI sorguları çalıştırılabiliyor, farkları ve bildirimleri korunabiliyordu; fakat analist bir aramayı konu/öncelik ile sınıflandıramıyor veya araştırma düşüncesini belirli çalışma kanıtına bağlayamıyordu. Sorgu tanımına serbest metin eklemek karşılaştırma tabanını gereksiz yere sıfırlardı. Sessizce değiştirilebilen notlar da karar izini zayıflatırdı.

## Karar

Etiket ve analist notları sorgu tanımından ayrı `CtiHuntingJournalRepository` sınırında tutulur. Etiket 2–40 karakterlik kanonik bir anahtarla tekilleşir; bir aramada en fazla 50 etkin etiket olabilir. Ekleme, görünüm güncelleme, kaldırma ve yeniden etkinleştirme olayları silinmez.

Not `observation`, `hypothesis`, `conclusion` veya `follow-up` türündedir ve 2–2000 karakterlik güvenli metin taşır. Not yalnız eklenir; genel kayıtlı aramaya veya aynı aramaya ait mevcut bir çalışma kimliğine bağlanabilir. Yanlış arama–çalışma ilişkisi reddedilir. Not ve etiket tehdit kararı değildir; sorgu tanımı özetine katılmaz ve fark tabanını sıfırlamaz.

SQLite adaptörü bütün etiket, olay ve not geçmişini üst sınırlar içinde doğrular. Şema 38 üç tablo ekler. Şema 37 ve öncesi yalnız açık, yedekli `migrate` ile yükselir; geçmiş sorgulardan etiket veya not uydurulmaz.

## Sonuçlar

Kişisel kullanıcı aramaları konu ve önceliğe göre düzenleyebilir; hipotez ve sonuçları değişmez çalışma kanıtına bağlayabilir. Not düzenleme/silme, etiketle toplu filtreleme, kullanıcı kimliği ve takım işbirliği bu dilimin dışındadır.
