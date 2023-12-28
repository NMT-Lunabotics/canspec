#!/usr/bin/env python3

"""CAN schema generator."""

import argparse
import yaml

import _convert


def _main() -> None:
    parser = argparse.ArgumentParser(
        prog='canspec',
        description="""
        CAN schema generator. Takes input files as concise YAML
        specifications, and can convert them to either KCD or directly
        to much more usable C++ header files.
        """
    )
    infile = parser.add_argument('infile').dest
    kcd = parser.add_argument(
        '--kcd',
        metavar='outfile',
        help='generate a KCD file',
    ).dest
    hpp = parser.add_argument(
        '--hpp',
        metavar='outfile',
        help='generate a C++ header file',
    ).dest

    parsed = parser.parse_args().__dict__

    if not (parsed[kcd] or parsed[hpp]):
        print('need either --kcd or --hpp')
        exit(-1)

    with open(parsed[infile]) as file:
        input = yaml.load(file.read(), Loader=yaml.UnsafeLoader)

    if parsed[kcd]:
        with open(parsed[kcd], 'w') as file:
            file.write(str(_convert.database_to_kcd(input).human_readable(2)))

    if parsed[hpp]:
        with open(parsed[hpp], 'w') as file:
            file.write(_convert.database_to_cpp(input))


if __name__ == '__main__':
    _main()
