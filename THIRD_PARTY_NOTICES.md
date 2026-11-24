# Üçüncü Taraf Bildirimleri

## P11 Lunar veri kaynağı ve AIL Framework

0.193.0 yeni üçüncü taraf Python paketi veya vendored kod eklemez.
Lunar/Webz.io Domain Exposure yalnız resmî HTTPS veri kaynağı olarak toplu
domain sayaçları için çağrılır; sağlayıcı kodu veya ham veri bu depoda
dağıtılmaz. [Resmî açıklama](https://docs.webz.io/docs/webz/dea-introduction)
ve [API sözleşmesi](https://docs.webz.io/docs/webz/dea-api-reference).

AIL Framework v7.1 ayrı sistem adayıdır ve bu dağıtıma dahil değildir.
İncelenen upstream commit:
`4b94304bcd4d3d08b9e0c0772be4773e6bbbd350`.

Lisans: AGPL-3.0

[Özgün lisans](https://github.com/ail-project/ail-framework/blob/v7.1/LICENSE) ·
[sürüm](https://github.com/ail-project/ail-framework/releases/tag/v7.1) ·
[proje](https://www.ail-project.org/)

XTI AIL kodunu kopyalamaz, kurmaz veya çalıştırmaz; yalnız küçültülmüş
`xti-ail-v1` kanıt zarfını içe alabilir. Bu yazılım lisansı AIL ile erişilen
üçüncü taraf içeriğin lisansı değildir.

**21 Kasım 2026 — P03 / 0.182.0:** ImageHash4.3.2 (BSD-2-Clause),
Pillow13.0.0 (MIT-CMU/HPND bildirimi), Playwright1.65.2 (Apache-2.0),
google-play-scraper1.2.7 (MIT). Görsel hesaplamalar SciPy1.16.3 (BSD-3-Clause),
PyWavelets1.9.0 (MIT), mevcut Python koşullu NumPy2.4.6/2.5.4 ve greenlet3.5.0
(MIT/Python-2.0) kullanır. Wheel içindeki ek native lisanslar da geçerlidir;
kurulu paketlerin lisans dosyaları korunur. [Tam hash listesi](requirements/brand-protection.txt).
Chromium revision1255, SDK1.65.2 ile seçilir; Chromium/üçüncü taraf
bildirimleri dağıtımda korunur. SDK kod lisansı tarayıcıdaki bütün native
bileşenlerin lisansını tek başına tanımlamaz. Tarayıcı ayrı upstream arşiv
hash piniyle sunulmuyor; resmî SDK TLS indirimi ve yerel hash makbuzu var.
Mağaza ve açık sayfa verilerinin hakları bunlardan ayrıdır: [N-046](NOTES.md#n-046--p03-marka-koruması-görsel-kanıt-ve-mağaza-kaynakları).
Google kitaplığı motor TLS ayarını değiştirmemesi için yalnız ağsız parser
alt sürecinde kullanılır; kaynak HTTPS taşımasını XTI yapar. Kaynaklardan
APK/IPA veya çalıştırılabilir phishing kit alınmaz.


## P02 kanal kitaplıkları

0.181.0 sürümünde aşağıdaki resmî Python dağıtımları sürüm/dosya hash'iyle
kurulur. Özgün lisans ve telif metinleri dağıtımların `dist-info`/lisans
dosyalarında korunur; yeniden dağıtımda bunlar da korunmalıdır.

| Dağıtım | Sürüm | Lisans | Resmî dağıtım |
|---|---|---|---|
| Telethon | 1.46.0 | MIT | [PyPI](https://pypi.org/project/Telethon/1.46.0/) |
| irctokens | 2.0.2 | MIT | [PyPI](https://pypi.org/project/irctokens/2.0.2/) |
| pyaes | 1.6.1 | MIT | [PyPI](https://pypi.org/project/pyaes/1.6.1/) |
| rsa | 4.9.1 | Apache-2.0 | [PyPI](https://pypi.org/project/rsa/4.9.1/) |
| pyasn1 | 0.6.5 | BSD-2-Clause | [PyPI](https://pypi.org/project/pyasn1/0.6.5/) |
| setuptools (derleme) | 84.2.1 | MIT | [PyPI](https://pypi.org/project/setuptools/84.2.1/) |

pyaes yalnız kaynak paketi sunduğundan hash doğrulamasından sonra sabit
derleyiciyle `--no-build-isolation` kullanılır; değişken bağımlılık
çözümlemesiyle bir kanal sürümü seçilmez. Hash listeleri
[channels](requirements/channels.txt) ve [channels-build](requirements/channels-build.txt).
Bu yazılım izinleri kanal/publisher içeriklerinin yeniden yayın hakkı
değildir. [N-045](NOTES.md#n-045--p02-kaynak-kanal-ve-teslim-kapsamı).

## Betterleaks

0.180.0 kod/paste incelemesi [Betterleaks1.10.1](https://github.com/betterleaks/betterleaks)
native ikilisini ayrı süreçte kullanır. İncelenen commit:
`39d5bdcf34db54e944facac5cf6e8b03db5e2b99`.

Lisans: MIT

[Özgün lisans](https://github.com/betterleaks/betterleaks/blob/39d5bdcf34db54e944facac5cf6e8b03db5e2b99/LICENSE)
kurulum arşivinden ikiliyle birlikte saklanır. Platform arşiv SHA256'ları
[pin dosyasındadır](src/xti/domain/betterleaks_pin.py). Kaynak kodu
kopyalanmaz; araç değiştirilmez. Credential validation ve otomatik kaynak
config'i kapalıdır. Kaynak dosyalar çalıştırılmaz.

Araç MIT izni, GitHub/GitLab/Pastebin'de bulunan içeriklerin ticari
gösterim/saklama hakkı değildir; [N-044](NOTES.md#n-044--p01--a03-kaynak-erişimi-ve-secret-inceleme-aracı)
bu yeni veri kaynaklarının açık değerlendirmesini tutar.

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
