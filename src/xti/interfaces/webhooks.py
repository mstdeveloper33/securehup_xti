"""Plain Turkish terminal rendering for webhook configuration and evidence."""

from xti.adapters.webhook_secret_file import WebhookSecretArtifact
from xti.domain.webhooks import (
    WebhookDelivery,
    WebhookDeliveryDetails,
    WebhookDeliveryPage,
    WebhookDeliveryResult,
    WebhookDestination,
    WebhookDestinationMutation,
)
from xti.interfaces.text import safe_text


_STATUS = {
    "queued": "Kuyrukta",
    "retryable": "Yeniden denenebilir",
    "failed": "Başarısız",
    "delivered": "Teslim edildi",
}


def secret_lines(artifact: WebhookSecretArtifact) -> list[str]:
    return [
        "Webhook gizli anahtar dosyası oluşturuldu.",
        f"Konum: {safe_text(artifact.destination)}",
        "Dosya yalnız sahibi tarafından okunabilir; alıcı tarafla güvenli biçimde paylaşın.",
        "Anahtar değeri terminal çıktısına yazılmadı.",
    ]


def destination_lines(destination: WebhookDestination) -> list[str]:
    return [
        f"Webhook hedefi: {safe_text(destination.display_name)}",
        f"Kimlik: {safe_text(destination.id)}",
        f"Güvenli hedef görünümü: {safe_text(destination.endpoint)}",
        f"Durum: {'Etkin' if destination.active else 'Geri çekildi'}",
        f"Güncelleme: {safe_text(destination.updated_at)}",
        "Tam adres ve gizli anahtar çıktıda gösterilmez.",
    ]


def destination_mutation_lines(result: WebhookDestinationMutation) -> list[str]:
    labels = {
        "added": "Webhook hedefi kaydedildi.",
        "secret_rotated": "Webhook gizli anahtarı değiştirildi.",
        "revoked": "Webhook hedefi geri çekildi.",
    }
    return [labels[result.action], *destination_lines(result.destination)]


def destination_list_lines(destinations: tuple[WebhookDestination, ...]) -> list[str]:
    if not destinations:
        return ["Bu görünümde webhook hedefi yok."]
    lines = [f"Webhook hedefleri: {len(destinations)}"]
    for item in destinations:
        lines.append(
            f"- {safe_text(item.display_name)} | {safe_text(item.id)} | "
            f"{'etkin' if item.active else 'geri çekildi'} | {safe_text(item.endpoint)}"
        )
    lines.append("Ayrıntı: ./xti webhook target-show HEDEF_KIMLIGI")
    return lines


def delivery_lines(delivery: WebhookDelivery, *, created: bool | None = None) -> list[str]:
    lines = []
    if created is True:
        lines.append("Bildirim webhook teslim kuyruğuna eklendi.")
    elif created is False:
        lines.append("Aynı bildirim ve hedef zaten kuyrukta; yeni kopya oluşturulmadı.")
    lines.extend([
        f"Teslim kimliği: {safe_text(delivery.id)}",
        f"Hedef: {safe_text(delivery.destination_name)} — {safe_text(delivery.endpoint)}",
        f"Olay: {safe_text(delivery.event_type)}",
        f"Durum: {_STATUS[delivery.status]}",
        f"Deneme: {delivery.attempt_count}",
        f"Gövde SHA-256: {safe_text(delivery.payload_sha256)}",
    ])
    if delivery.last_http_status is not None:
        lines.append(f"Son HTTP durumu: {delivery.last_http_status}")
    if delivery.last_error is not None:
        lines.append(f"Son güvenli hata: {safe_text(delivery.last_error)}")
    return lines


def delivery_page_lines(page: WebhookDeliveryPage) -> list[str]:
    if not page.deliveries:
        return ["Bu görünümde webhook teslimi yok.", f"Eşleşen toplam: {page.total_count}"]
    lines = [f"Webhook teslimleri: {len(page.deliveries)} / {page.total_count}"]
    for item in page.deliveries:
        lines.append(
            f"- {_STATUS[item.status]} | {safe_text(item.event_type)} | "
            f"{safe_text(item.destination_name)} | {safe_text(item.id)} | deneme {item.attempt_count}"
        )
    lines.append("Ayrıntı: ./xti webhook delivery-show TESLIM_KIMLIGI")
    return lines


def delivery_detail_lines(details: WebhookDeliveryDetails) -> list[str]:
    lines = delivery_lines(details.delivery)
    lines.append("Teslim denemeleri:")
    if not details.attempts:
        lines.append("- Henüz gönderilmedi.")
    for item in details.attempts:
        status = f"HTTP {item.http_status}" if item.http_status is not None else "HTTP yanıtı yok"
        lines.append(
            f"- #{item.number} | {_STATUS[item.outcome]} | {status} | "
            f"{safe_text(item.attempted_at)}"
        )
    return lines


def delivery_result_lines(result: WebhookDeliveryResult) -> list[str]:
    heading = (
        "Webhook başarıyla teslim edildi."
        if result.delivery.status == "delivered"
        else "Webhook teslim denemesi kaydedildi; teslim tamamlanmadı."
    )
    return [heading, *delivery_lines(result.delivery)]
