# Üçüncü Taraf Bildirimleri

## RIPEstat / RIPE NCC RIS

0.164.0 isteğe bağlı IP ağ bağlamını resmî `network-info` API'sinden alır.
Sağlayıcı kodu kopyalanmaz; kaynak yanıtı, atıf ve çalışma zamanı saklanır.
API erişimi ücretsiz ticari yeniden kullanım izni değildir. 18 Kasım 2026
incelemesinde ticari kullanım için yazılı izin gereksinimi kaydedildi;
ürünleşme öncesi N-022 tamamlanmalıdır.

[Uç belgesi](https://stat.ripe.net/docs/data-api/api-endpoints/network-info),
[hizmet şartları](https://www.ripe.net/about-us/legal/ripestat-service-terms-and-conditions/),
[takip notu](NOTES.md#n-022--ripestat-ticari-kullanım-izni).

## theHarvester

İsteğe bağlı pasif arşiv keşfi, theHarvester'ı resmî
`laramies/theHarvester` deposunun
`6790b147f52309e4eee22ed941db1d285ab2ec23` commit'inden ayrı araç alanına
kurar. theHarvester kodu XTI kaynak deposuna kopyalanmamıştır.

Resmî depo: https://github.com/laramies/theHarvester  
Lisans: GPL-2.0-only  
Lisans metni: https://github.com/laramies/theHarvester/blob/6790b147f52309e4eee22ed941db1d285ab2ec23/LICENSE

XTI yalnız Common Crawl ve Wayback Archive P0 hostname sonuçlarını kullanır;
aktif hedef özelliklerini çalıştırmaz. Kurulan üçüncü taraf yazılımı dağıtmak
veya değiştirmek GPL-2.0-only koşullarına tabidir.

Arşiv v2 işçisi, aynı sabit kurulumdan indeks seçimi, hostname ve sayfa
ayrıştırma yardımcılarını ayrı süreçte çağırır. XTI'a ait HTTP/sayfalama
katmanı upstream dosyalarını değiştirmez. Kaynak protokolleri ve sınırlar
[0126 numaralı kararda](docs/decisions/0126-bounded-archive-transport.md) kayıtlıdır.

## Sherlock

İsteğe bağlı sosyal kullanıcı adı önizlemesi Sherlock 0.16.2'yi resmî
`sherlock-project/sherlock` reposunun
`a38ba54fda799cd786a2ab67a50143e1a63169e6` commit'inden kurar ve yalnız
incelenmiş küçük platform listesi için ayrı süreçte çalıştırır. Sherlock kodu
XTI kaynak deposuna kopyalanmamıştır.

Resmî depo: https://github.com/sherlock-project/sherlock  
Lisans: MIT

MIT License

Copyright (c) 2019 Sherlock Project

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Maigret

İsteğe bağlı sosyal kullanıcı adı önizlemesi Maigret 0.6.6'yı resmî
`soxoj/maigret` reposunun
`b8747b98820f4df9d1baf23235db7b2cb55d0198` commit'inden kurar ve ayrı süreçte
çalıştırır. Maigret kodu XTI kaynak deposuna kopyalanmamıştır.

Resmî depo: https://github.com/soxoj/maigret  
Lisans: MIT

MIT License

Copyright (c) 2020-2026 Soxoj

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## RansomLook açık ransomware gönderi akışı

XTI, kullanıcı açıkça `ransomware recent --source ransomlook` komutunu
çalıştırdığında RansomLook'un açık son-yedi-gün JSON API yanıtını salt okunur
olarak alır. Kaynak verisi bu depoda paketlenmez veya yeniden yayımlanmaz.
RansomLook yazılım kodu XTI'a dahil edilmemiştir.

RansomLook, web sitesi, API yanıtları ve veri kümelerini CC BY 4.0 koşuluyla
sunar. Atıf: RansomLook — https://www.ransomlook.io

API belgesi: https://www.ransomlook.io/doc/  
Resmî depo: https://github.com/RansomLook/RansomLook  
CC BY 4.0: https://creativecommons.org/licenses/by/4.0/

## MITRE ATT&CK

XTI, kullanıcı açıkça `cti attack-sync` komutunu çalıştırdığında resmî MITRE ATT&CK Enterprise STIX verisini indirir. ATT&CK veri dosyası bu kaynak deposunda paketlenmez.

This project makes use of ATT&CK®.

© 2026 The MITRE Corporation. This work is reproduced and distributed with the permission of The MITRE Corporation.

Kullanım ve yeniden dağıtım MITRE'nin ATT&CK lisansı ve sorumluluk reddine tabidir: https://github.com/mitre-attack/attack-stix-data/blob/master/LICENSE.txt

Resmî veri deposu: https://github.com/mitre-attack/attack-stix-data

## ThreatCluster açık ransomware iddia akışı

XTI, kullanıcı açıkça `ransomware recent` veya `ransomware refresh` komutunu çalıştırdığında ThreatCluster'ın herkese açık ransomware victim JSON akışını okur. `refresh`, ham leak-site adresini veya içeriğini değil yalnız güvenli alanları ve snapshot farkını yerel veritabanında tutar. Kaynak verisi bu depoda paketlenmez veya yeniden yayımlanmaz.

Akış yanıtı veriyi `CC-BY 4.0 — attribution: ThreatCluster (https://threatcluster.io)` olarak etiketler. ThreatCluster kullanım koşulları kamu akışlarını TLP:CLEAR olarak tanımlar ve atıfla kullanıma izin verir. Müşterilere veri sunan ticari ürün veya hizmete gömme koşulları ayrıca değerlendirilmelidir.

Akış ve biçim açıklaması: https://threatcluster.io/feeds  
Güncel kullanım koşulları: https://threatcluster.io/terms  
CC BY 4.0: https://creativecommons.org/licenses/by/4.0/
