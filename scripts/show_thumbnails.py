#!/usr/bin/env python3
"""Backward-compatible wrapper around search_media.py."""

import sys

from search_media import main as search_main


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    translated: list = []
    list_only = False
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == '--file-id':
            translated.append('--id')
            if i + 1 < len(argv) and not argv[i + 1].startswith('-'):
                translated.append(argv[i + 1])
                i += 1
        elif arg in ('--file',) and i + 1 < len(argv):
            translated.extend(['--path', argv[i + 1]])
            i += 1
        elif arg == '--list-only':
            list_only = True
        elif arg == '--open':
            translated.append('--show')
            translated.append('full')
        else:
            translated.append(arg)
        i += 1

    show = 'basic,thumbnail'
    if list_only:
        translated.extend(['--show', show, '--no-save', '--no-grid'])
    else:
        translated.extend(['--show', show])
    return search_main(translated)


if __name__ == '__main__':
    sys.exit(main())
