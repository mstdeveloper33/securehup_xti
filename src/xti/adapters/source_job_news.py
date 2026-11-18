"""Publisher service composition while the cooperative runner owns the writer lock."""

from contextlib import nullcontext
from urllib.request import build_opener, ProxyHandler
from xti.adapters.rss_atom_news import RssAtomNewsSource, _NoRedirects
from xti.adapters.metered_source_http import MeteredSourceOpener


class HeldSourceJobLock:
    """Only composed inside the source worker, which already owns this lock."""
    def acquire(self):
        return nullcontext()


def source(request_usage=None):
    opener = build_opener(ProxyHandler({}), _NoRedirects())
    if request_usage is not None:
        opener = MeteredSourceOpener(opener, request_usage)
    return RssAtomNewsSource(opener=opener.open)
