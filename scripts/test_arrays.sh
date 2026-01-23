#!/bin/bash
SUCCESS_LIST=()
FAILURE_LIST=()

FILES_LIST="file1.txt
file2.txt
file3.txt"

log() {
  echo "$1"
}

log "Starting loop"
while IFS= read -r FILE; do
    log "Processing $FILE"
    SUCCESS_LIST+=("$FILE")
    FAILURE_LIST+=("$FILE (failed)")
done <<< "$FILES_LIST"

echo "Success count: ${#SUCCESS_LIST[@]}"
echo "Failure count: ${#FAILURE_LIST[@]}"

for item in "${SUCCESS_LIST[@]}"; do
    echo "Success: $item"
done
