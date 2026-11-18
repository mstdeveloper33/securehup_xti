"""Shared root grammar for full terminal and lightweight platform dispatch."""

import argparse
import os

from xti import __version__


class UsageError(ValueError):
    """Invalid terminal syntax, rendered in the selected output format."""


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise UsageError(message)


class DataDirectoryAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, values)
        namespace.explicit_data_dir = True


def root_parser():
    parser = Parser(prog="xti", description="Marka taklidini ve yetkili DNS/TLS dış yüzeyini terminalden izle.")
    parser.add_argument("--version", action="version", version=f"XTI {__version__}")
    parser.add_argument("--data-dir", default=os.environ.get("XTI_DATA_DIR", ".xti-data"),
                        action=DataDirectoryAction,
                        help="Kayıt klasörü (varsayılan: .xti-data veya XTI_DATA_DIR).")
    parser.add_argument("--json", action="store_true", help="Otomasyon için JSON çıktı üret.")
    return parser
