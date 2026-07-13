#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 [-r] [directory]"
  echo "  -r    recurse into subdirectories"
  exit 1
}

RECURSE=false

while getopts ":r" opt; do
  case "$opt" in
    r) RECURSE=true ;;
    *) usage ;;
  esac
done
shift $((OPTIND - 1))

DIR="${1:-.}"

if [[ ! -d "$DIR" ]]; then
  echo "Error: '$DIR' is not a directory" >&2
  exit 1
fi

if $RECURSE; then
  find "$DIR" -type f
else
  find "$DIR" -maxdepth 1 -type f
fi \
| sed -n 's/.*\.//p' \
| sort -u
