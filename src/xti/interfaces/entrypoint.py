"""Avoid loading terminal collectors for isolated platform control/read calls."""

import sys

from xti.interfaces.arguments import UsageError, root_parser


def _platform_selected(values):
    # Conservative dispatch only; the shared argparse grammar still validates
    # the WHOLE command. Ambiguous/invalid syntax goes through the full parser.
    # In particular, a data-directory value named 'platform' is not a command.
    index = 0
    while index < len(values):
        value = values[index]
        option, equals, _ = value.partition("=")
        if option.startswith("--") and len(option) > 2 and "--json".startswith(option) and not equals:
            index += 1
        elif option.startswith("--") and len(option) > 2 and "--data-dir".startswith(option):
            index += 1 if equals else 2
        else:
            return value == "platform"
    return False


def main(argv=None):
    values = list(sys.argv[1:] if argv is None else argv)
    if not _platform_selected(values):
        from xti.interfaces.cli import main as terminal_main
        return terminal_main(values)
    from xti.interfaces.platform_engine import register_platform_parser, report_platform_usage_error, run_platform
    parser = root_parser()
    register_platform_parser(parser.add_subparsers(dest="command", required=True))
    try:
        args = parser.parse_args(values)
    except UsageError:
        report_platform_usage_error()
        return 2
    return run_platform(args)
