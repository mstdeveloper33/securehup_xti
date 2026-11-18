"""Count each HTTP opener attempt without retaining headers, credentials or bodies."""

from urllib.error import HTTPError

from xti.domain.assets import ValidationError
from xti.ports.discovery import SourceError


class MeteredSourceOpener:
    def __init__(self, opener, meter):
        self.opener, self.meter = opener, meter

    def open(self, *args, **kwargs):
        try:
            self.meter.begin()
        except ValidationError as error:
            raise SourceError(str(error)) from error
        try:
            response = self.opener.open(*args, **kwargs)
        except HTTPError as error:
            self.meter.received(error.code)
            raise
        except BaseException:
            self.meter.failed()
            raise
        self.meter.received(response.status)
        return response
