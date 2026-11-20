#!/usr/bin/env python3
"""Run the existing fast-gate module list intact or in two disjoint CI shards."""
import argparse
import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def select_modules(modules, shard):
    if not modules or len(modules) != len(set(modules)):
        raise ValueError('The check module list must be nonempty and contain no duplicates.')
    if not shard:
        return modules
    if shard not in ('1/2', '2/2'):
        raise ValueError('XTI_CHECK_SHARD must be 1/2 or 2/2; omit it for the complete fast gate.')
    selected = modules[int(shard[0]) - 1::2]
    if not selected:
        raise ValueError('The selected check shard is empty.')
    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-v', action='store_true')
    parser.add_argument('modules', nargs='+')
    options = parser.parse_args()
    try:
        selected = select_modules(options.modules, os.environ.get('XTI_CHECK_SHARD'))
    except ValueError as error:
        parser.error(str(error))
    print(f"Fast gate: {len(selected)}/{len(options.modules)} modules; shard {os.environ.get('XTI_CHECK_SHARD') or 'all'}", flush=True)
    unittest.main(module=None, argv=[sys.argv[0], *(['-v'] if options.v else []), *selected])


if __name__ == '__main__': main()
