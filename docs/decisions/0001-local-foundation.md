# Karar 0001 — Ayrılmış Yerel Temel

**28 Ekim 2026 · İlk sürümde uygulandı.**

Kişisel kullanım, ücretli hizmet bütçesi olmaması ve terminalden yönetim için Python 3.11+ ve SQLite seçildi. Domain, uygulama, port, adaptör ve terminal ayrıdır. İlk çalışan dilim kayıt/tekrar kontrolü, tanılama ve yedek/restore işidir.

Terminal argparse, testler unittest ile yazıldı; çalışma ve test için dış paket gerekmez. Roadmap'teki Typer/Rich ve pytest önerileri gerçek ihtiyaç oluştuğunda değerlendirilecek. İş mantığı bu araçlara bağlı değildir.

Runtime bağımlılığı olmadığı için lock dosyası henüz gerekmiyor. Build backend pyproject içinde tanımlı; paket dağıtım hattı etkinleştirilirken build bağımlılıkları sabitlenecek ve kurulmuş paket ayrıca test edilecek. Şu an doğrulanan yol depodan `./xti` çalıştırmaktır.

İlk terminal sadedir. IDNA, canlı kaynak, arka plan işleri, çoklu kullanıcı ve şema yükseltmesi uygulanmadı. Bilinmeyen şema sessizce dönüştürülmez. Yedek yayını hard-link destekli yerel dosya sistemi ister; destek yoksa açık hata verir. Otomatik yedek ve kanıt dosyaları sonraki kapsamdır.

Kararı yeniden açacak ihtiyaçlar: etkileşimli terminal; gerçek dış kütüphane ihtiyacı; yeni şema sürümü; ölçülen yazma/arama yükü; çok makine; paket dağıtımı veya müşteri kullanımı.

