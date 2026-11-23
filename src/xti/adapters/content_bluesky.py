"""Bounded, unauthenticated Bluesky public AppView search windows."""
from datetime import datetime, timedelta, timezone
import json
import re
import time
import unicodedata
from urllib.parse import quote, urlencode

from xti.domain.assets import ValidationError
from xti.domain.content_monitoring import ContentDocument, ContentError, digest


PUBLIC_ENDPOINT = "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts"
APPVIEW_ENDPOINT = "https://api.bsky.app/xrpc/app.bsky.feed.searchPosts"
_ENDPOINTS = {"public": PUBLIC_ENDPOINT, "api": APPVIEW_ENDPOINT}
_AT_POST = re.compile(
    r"at://(did:[a-z0-9]+:[A-Za-z0-9._:%-]{1,500})/"
    r"app\.bsky\.feed\.post/([A-Za-z0-9._~:-]{1,512})"
)


def _search_term(value):
    value = unicodedata.normalize("NFKC", value).strip()
    if not value or len(value) > 253 or any(unicodedata.category(char) in ("Cc", "Cs") for char in value):
        raise ValidationError("Bluesky arama terimi geçersiz.")
    if any(char.isspace() for char in value):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return value


def search_queries(targets):
    """Interleave primary names, domains and aliases so small budgets stay fair."""
    if not isinstance(targets, (tuple, list)) or not targets:
        raise ValidationError("Bluesky araması için en az bir firma veya tedarikçi hedefi gerekli.")
    ordered = []
    for target in targets:
        ordered.append(target["name"])
    for key in ("domains", "aliases"):
        width = max((len(target.get(key, ())) for target in targets), default=0)
        for index in range(width):
            for target in targets:
                values = target.get(key, ())
                if index < len(values):
                    ordered.append(values[index])
    seen, result = set(), []
    for value in ordered:
        normalized = unicodedata.normalize("NFKC", value).casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(_search_term(value))
    return tuple(result)


def _post_url(uri):
    matched = _AT_POST.fullmatch(uri) if isinstance(uri, str) else None
    if matched is None:
        raise ValidationError("Bluesky gönderi kimliği geçersiz.")
    did, record_key = matched.groups()
    return "https://bsky.app/profile/" + quote(did, safe=":._-") + "/post/" + quote(record_key, safe="._~:-")


def _timestamp(value):
    if not isinstance(value, str):
        raise ValidationError("Bluesky gönderi zamanı geçersiz.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValidationError("Bluesky gönderi zamanı geçersiz.") from None
    if parsed.tzinfo is None:
        raise ValidationError("Bluesky gönderi zamanı UTC saat dilimi içermeli.")
    return parsed.astimezone(timezone.utc).isoformat()


def parse_search_response(body, *, historical):
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ContentError("invalid_response", "Bluesky yanıtı geçerli JSON değil.") from None
    if not isinstance(payload, dict) or not isinstance(payload.get("posts"), list) or len(payload["posts"]) > 100:
        raise ContentError("invalid_response", "Bluesky yanıt yapısı geçersiz.")
    if "cursor" in payload and not isinstance(payload["cursor"], str):
        raise ContentError("invalid_response", "Bluesky sayfalama bilgisi geçersiz.")
    documents, skipped, malformed, unsupported = [], 0, 0, 0
    for post in payload["posts"]:
        try:
            if not isinstance(post, dict):
                raise ValueError()
            uri, record = post["uri"], post["record"]
            if not isinstance(record, dict) or record.get("$type", "app.bsky.feed.post") != "app.bsky.feed.post":
                raise ValueError()
            content = record["text"]
            if not isinstance(content, str):
                raise ValueError()
            published_at = _timestamp(record["createdAt"])
            indexed_at = _timestamp(post["indexedAt"])
            url = _post_url(uri)
            if not content:
                # Empty/media-only posts are valid provider records but outside
                # this text-only source. They make the window partial, not broken.
                skipped += 1
                unsupported += 1
                continue
            document = ContentDocument(
                uri,
                url,
                "Bluesky gönderisi",
                content,
                published_at,
                indexed_at,
                "message",
                historical,
            ).validate()
            documents.append(document)
        except (KeyError, TypeError, ValueError, ValidationError):
            skipped += 1
            malformed += 1
    if payload["posts"] and not documents and malformed and not unsupported:
        raise ContentError("invalid_response", "Bluesky yanıtındaki gönderiler doğrulanamadı.")
    hits = payload.get("hitsTotal")
    if hits is not None and (type(hits) is not int or hits < 0):
        raise ContentError("invalid_response", "Bluesky sonuç sayısı geçersiz.")
    return documents, skipped, {
        "cursor_present": bool(payload.get("cursor")),
        "reported_hits": hits,
        "unsupported_items": unsupported,
    }


def collect_bluesky(definition, checkpoint, budget, consume, *, targets, http, clock=time.monotonic):
    queries = search_queries(targets)
    # Target identities are part of the scope: replacing a company with another
    # record that happens to have the same name must start a new silent baseline.
    fingerprint = digest([definition.get("language", "und"), list(targets), list(queries)])
    same_scope = checkpoint.get("query_sha256") == fingerprint
    index = checkpoint.get("query_index", 0) if same_scope else 0
    baseline_complete = bool(checkpoint.get("baseline_complete", False)) if same_scope else False
    preferred_endpoint = checkpoint.get("endpoint", "public") if same_scope else "public"
    if type(index) is not int or not 0 <= index < len(queries):
        raise ContentError("invalid_checkpoint", "Bluesky ilerleme kaydı geçersiz.")
    if preferred_endpoint not in _ENDPOINTS:
        raise ContentError("invalid_checkpoint", "Bluesky uç nokta ilerleme kaydı geçersiz.")

    started = clock()
    operations = items = skipped = unsupported = completed = reported_hits = 0
    cursor_present = False
    endpoint_hosts_used = []
    fallback_used = False
    seen = set()
    status = "complete"
    failure = None
    while index < len(queries):
        remaining_seconds = budget["seconds"] - (clock() - started)
        operations_left = budget["max_operations"] - operations
        items_left = budget["max_items"] - items
        if remaining_seconds <= 0 or operations_left <= 0 or items_left <= 0:
            status = "partial"
            break
        remaining_queries = len(queries) - index
        limit = min(25, max(1, items_left // remaining_queries))
        parameters = {"q": queries[index], "sort": "latest", "limit": limit}
        language = definition.get("language", "und")
        if language not in ("und", "mul"):
            parameters["lang"] = language
        order = (preferred_endpoint, "api" if preferred_endpoint == "public" else "public")
        response = None
        for endpoint_index, endpoint_name in enumerate(order):
            remaining_seconds = budget["seconds"] - (clock() - started)
            operations_left = budget["max_operations"] - operations
            if remaining_seconds <= 0 or operations_left <= 0:
                break
            response = http.get(
                _ENDPOINTS[endpoint_name] + "?" + urlencode(parameters),
                seconds=remaining_seconds,
                max_operations=operations_left,
            )
            used = len(response.get("attempts", []))
            operations += used
            if used:
                endpoint_hosts_used.append(endpoint_name)
            if response.get("status") == "complete":
                preferred_endpoint = endpoint_name
                fallback_used = fallback_used or endpoint_index > 0
                break
            if response.get("status") not in (
                "authentication_required", "access_denied", "not_found", "unavailable"
            ):
                break
            fallback_used = True
        if response is None:
            status = "partial"
            break
        used = len(response.get("attempts", []))
        if response.get("status") != "complete":
            failure = response.get("status", "unavailable")
            status = failure if completed == 0 else "partial"
            break
        if used == 0:
            failure, status = "invalid_usage", "invalid_usage"
            break
        try:
            documents, page_skipped, metadata = parse_search_response(
                response.get("body", b""), historical=not baseline_complete
            )
        except ContentError as error:
            failure = error.code
            status = error.code if completed == 0 else "partial"
            break
        for document in documents:
            if document.native_id in seen:
                continue
            seen.add(document.native_id)
            consume(document)
            items += 1
        skipped += page_skipped
        unsupported += metadata["unsupported_items"]
        cursor_present = cursor_present or metadata["cursor_present"]
        if metadata["reported_hits"] is not None:
            reported_hits += metadata["reported_hits"]
        completed += 1
        index += 1

    cycle_complete = index >= len(queries)
    if cycle_complete:
        index = 0
        baseline_complete = True
        if skipped:
            status = "partial"
    checkpoint_out = {
        "query_sha256": fingerprint,
        "query_index": index,
        "baseline_complete": baseline_complete,
        "endpoint": preferred_endpoint,
    }
    result = {
        "status": status,
        "operations": operations,
        "operation_unit": "bluesky_public_search_request",
        "network_requests": operations,
        "items": items,
        "skipped_items": skipped,
        "unsupported_items": unsupported,
        "checkpoint": checkpoint_out,
        "coverage": "latest_public_search_pages",
        "history_complete": False,
        "query_count": len(queries),
        "queries_completed": completed,
        "cycle_complete": cycle_complete,
        "cursor_present": cursor_present,
        "provider_reported_hits_sum": reported_hits,
        "scope_reset": bool(checkpoint and not same_scope),
        "endpoint_hosts_used": sorted(set(endpoint_hosts_used)),
        "endpoint_fallback_used": fallback_used,
        "usage_complete": bool(operations or status == "complete"),
    }
    if failure:
        result["last_error"] = failure
    if failure == "rate_limited":
        result["checkpoint"] = {
            **checkpoint_out,
            "retry_at": (
                datetime.now(timezone.utc)
                + timedelta(seconds=response.get("retry_after_seconds", 300))
            ).isoformat(),
        }
    return result
