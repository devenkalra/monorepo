#!/bin/bash
# convert_non_photos.sh
# Bash port of convert_non_photos.py
# Traverses a directory, converts .avi/.vob to .mp4, and moves originals to archive.

set -u

# Defaults
CRF=16
PRESET="slow"
AUDIO_BITRATE="320k"

DEINTERLACE_ALL=false
OVERWRITE_MP4=false
DRY_RUN=false
TEST_MODE=false
SRC_ROOT=""
ARCHIVE_ROOT=""
VERBOSE=false
LOG_FILE="/tmp/convert.log"
LIMIT=0
LIMIT=0
PATTERN="*"
MAX_RETRIES=5
COOL_DOWN=5

# Global array to hold the generated command
FFMPEG_CMD=()
DETECTED_OPTS=""

# Arrays for reporting
SUCCESS_LIST=()
FAILURE_LIST=()

# Capture invocation args before parsing
INVOCATION_ARGS="$0 $@"

usage() {
    echo "Usage: $0 --src <dir> --archive <dir> [options]"
    echo "Options:"
    echo "  --crf <int>            x264 CRF (default: 16)"
    echo "  --preset <str>         x264 preset (default: slow)"
    echo "  --audio-bitrate <rate> AAC bitrate (default: 320k)"
    echo "  --deinterlace          Force deinterlacing (bwdif) for all files"
    echo "  --pattern <glob>       Process only files matching pattern (default: *)"
    echo "  --test                 Test mode: 30s limit, keep tmp, no archive"
    echo "  --overwrite-mp4        Overwrite existing MP4s"
    echo "  --dry-run              Print commands, don't execute"
    echo "  --log <file>           Log file path (default: /tmp/convert.log)"
    echo "  --limit <int>          Process at most N files (0=unlimited)"
    echo "  --verbose              Enable verbose output"
    echo "  -h, --help             Show this help"
    exit 1
}

# Argument Parsing
while [[ $# -gt 0 ]]; do
    case "$1" in
        --src)
            SRC_ROOT="$2"
            shift 2
            ;;
        --archive)
            ARCHIVE_ROOT="$2"
            shift 2
            ;;
        --crf)
            CRF="$2"
            shift 2
            ;;
        --preset)
            PRESET="$2"
            shift 2
            ;;
        --audio-bitrate)
            AUDIO_BITRATE="$2"
            shift 2
            ;;
        --deinterlace)
            DEINTERLACE_ALL=true
            shift 1
            ;;
        --pattern)
            PATTERN="$2"
            shift 2
            ;;
        --test)
            TEST_MODE=true
            shift 1
            ;;
        --overwrite-mp4)
            OVERWRITE_MP4=true
            shift 1
            ;;
        --dry-run)
            DRY_RUN=true
            shift 1
            ;;
        --log)
            LOG_FILE="$2"
            shift 2
            ;;
        --limit)
            LIMIT="$2"
            shift 2
            ;;
        --verbose)
            VERBOSE=true
            shift 1
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo "Unknown argument: $1"
            usage
            ;;
    esac
done

if [[ -z "$SRC_ROOT" || -z "$ARCHIVE_ROOT" ]]; then
    echo "Error: --src and --archive are required."
    usage
fi

# Resolve absolute paths
SRC_ROOT=$(realpath "$SRC_ROOT")
ARCHIVE_ROOT=$(realpath "$ARCHIVE_ROOT")

# Setup Temp Work Directory
WORK_ROOT="/tmp/convert_work_$$"
mkdir -p "$WORK_ROOT"
# Trap to clean up on exit
trap 'rm -rf "$WORK_ROOT"' EXIT

# Setup logging

# Setup logging
mkdir -p "$(dirname "$LOG_FILE")"

log() {
    local MSG="$(date '+%Y-%m-%d %H:%M:%S') | $1"
    if [[ "$VERBOSE" == "true" ]]; then
        echo "$MSG" | tee -a "$LOG_FILE"
    else
        echo "$MSG" >> "$LOG_FILE"
    fi
}

robust_copy() {
    local source="$1"
    local dest="$2"
    local count=0
    
    # Retry loop for copying
    while [ $count -lt $MAX_RETRIES ]; do
        # Use rsync with timeout and inplace for better NAS handling
        rsync -a --timeout=30 --inplace "$source" "$dest"
        if [ $? -eq 0 ]; then
            # Flush buffers
            sync
            return 0
        else
            count=$((count + 1))
            log "  ⚠ Copy failed (rsync). Attempt $count of $MAX_RETRIES. Retrying in $COOL_DOWN seconds..."
            sleep $COOL_DOWN
        fi
    done
    return 1
}

# Check requirements
if ! command -v ffmpeg &> /dev/null; then
    echo "Error: ffmpeg not found." | tee -a "$LOG_FILE"
    exit 1
fi
if ! command -v ffprobe &> /dev/null; then
    echo "Error: ffprobe not found." | tee -a "$LOG_FILE"
    exit 1
fi
if ! command -v rsync &> /dev/null; then
    echo "Error: rsync not found." | tee -a "$LOG_FILE"
    exit 1
fi

detect_interlacing() {
    local IN_FILE="$1"
    DETECTED_OPTS="" # Reset
    
    # If forced globally
    if [[ "$DEINTERLACE_ALL" == "true" ]]; then
        log "  Force deinterlace enabled."
        DETECTED_OPTS="-vf bwdif=mode=1:parity=-1:deint=0"
        return
    fi
    
    log "  Running interlace detection (300 frames)..."
    local RESULT
    RESULT=$(ffmpeg -i "$IN_FILE" -filter:v idet -frames:v 300 -an -f null - 2>&1 | grep "Multi frame detection" | tail -n 1)
    
    if [[ -z "$RESULT" ]]; then
        log "  ⚠ Detection failed or no video stream. Assuming progressive."
        return
    fi
     
    # Extract values
    local PROG=$(echo "$RESULT" | awk -F'Progressive: *' '{print $2}' | awk '{print $1}')
    local TFF=$(echo "$RESULT" | awk -F'TFF: *' '{print $2}' | awk '{print $1}')
    local BFF=$(echo "$RESULT" | awk -F'BFF: *' '{print $2}' | awk '{print $1}')
    
    PROG=${PROG:-0}
    TFF=${TFF:-0}
    BFF=${BFF:-0}
    
    local INT=$((TFF + BFF))
    local TOTAL=$((PROG + INT))
    local CONFIDENCE=0
    
    if [[ "$TOTAL" -gt 0 ]]; then
        CONFIDENCE=$(( 100 * INT / TOTAL ))
    fi
    
    log "  Stats - Progressive: $PROG | Interlaced: $INT | Confidence: $CONFIDENCE%"
    
    if [[ "$CONFIDENCE" -gt 50 ]]; then
        log "  => Detected Interlaced (>50%). Applying bwdif."
        DETECTED_OPTS="-vf bwdif=mode=1:parity=-1:deint=0"
    else
        log "  => Detected Progressive. No deinterlacing."
    fi
}

build_ffmpeg_command() {
    local IN_FILE="$1"
    local OUT_FILE="$2"
    local VF_OPTS="${3:-}"
    
    local CMD=(ffmpeg -hide_banner -y -nostdin)
    
    if [[ "$TEST_MODE" == "true" ]]; then
        CMD+=(-t 30)
    fi
    
    CMD+=(-i "$IN_FILE" -map "0:v:0" -map "0:a?")
    
    if [[ -n "$VF_OPTS" ]]; then 
        # We need to be careful with splitting if VF_OPTS has spaces but is one arg.
        # But here VF_OPTS is usually "-vf filter_str", so we want word splitting if it contains the flag and the value.
        # However, our detect_interlacing returns "-vf bwdif=...".
        # So we can just append it as is if we trust it doesn't have internal spaces that break logic.
        # Ideally, we should potentially split it.
        # For safety, let's treat VF_OPTS as space separated args in this specific simplistic case.
        CMD+=($VF_OPTS)
    fi
    
    CMD+=(-c:v libx264 -preset "$PRESET" -crf "$CRF" -profile:v high -pix_fmt yuv420p)
    CMD+=(-c:a aac -b:a "$AUDIO_BITRATE" -movflags +faststart)
    CMD+=("$OUT_FILE")
    
    FFMPEG_CMD=("${CMD[@]}")
}

print_report() {
    log "=========================================="
    log "             FINAL REPORT                 "
    log "=========================================="
    
    local SUCCESS_COUNT=${#SUCCESS_LIST[@]}
    local FAILURE_COUNT=${#FAILURE_LIST[@]}
    
    log "Total processed: $((SUCCESS_COUNT + FAILURE_COUNT))"
    log "Successful:      $SUCCESS_COUNT"
    log "Failed:          $FAILURE_COUNT"
    log "------------------------------------------"
    
    if [[ "$SUCCESS_COUNT" -gt 0 ]]; then
        log "Successful Conversions:"
        for ITEM in "${SUCCESS_LIST[@]}"; do
            log "  [OK] $ITEM"
        done
        log "------------------------------------------"
    fi
    
    if [[ "$FAILURE_COUNT" -gt 0 ]]; then
        log "Failed Conversions:"
        for ITEM in "${FAILURE_LIST[@]}"; do
             # Use a generic approach to log each line of the item
             # so that 'log' adds the timestamp to every line.
             # We prefix the first line with [FAIL].
             
             local FULL_ITEM="  [FAIL] $ITEM"
             while IFS= read -r LINE; do
                 log "$LINE"
             done <<< "$FULL_ITEM"
        done
        log "------------------------------------------"
    fi
}


log "=== Conversion run started ==="
log "Invocation: $INVOCATION_ARGS"
log "Source: $SRC_ROOT"
log "Archive: $ARCHIVE_ROOT"
log "Params: CRF=$CRF, Preset=$PRESET, Audio=$AUDIO_BITRATE"

if [[ "$DRY_RUN" == "true" ]]; then
    log "DRY RUN enabled"
fi
if [[ "$TEST_MODE" == "true" ]]; then
    log "TEST MODE enabled (30s limit, no move)"
fi

# Find files: .avi and .vob (case insensitive) AND matching pattern
FILES_LIST=$(find "$SRC_ROOT" -type f \( -iname "*.avi" -o -iname "*.vob" \) -iname "$PATTERN" | sort)

if [[ -z "$FILES_LIST" ]]; then
    TOTAL=0
else
    TOTAL=$(echo "$FILES_LIST" | wc -l)
fi

log "Found $TOTAL file(s) under $SRC_ROOT"

COUNT=0

# We process line by line.
while IFS= read -u 9 -r FILE; do
    # Skip empty lines (if any)
    [[ -z "$FILE" ]] && continue
    
    # Check limit
    if [[ "$LIMIT" -gt 0 && "$COUNT" -ge "$LIMIT" ]]; then
        log "Limit of $LIMIT reached. Stopping."
        break
    fi
    ((COUNT++))

    REL_PATH="${FILE#$SRC_ROOT/}"
    DIR_NAME=$(dirname "$FILE")
    BASE_NAME=$(basename "$FILE")
    EXT="${BASE_NAME##*.}"
    NAME_NO_EXT="${BASE_NAME%.*}"
    
    # Sanitize output name
    SAFE_NAME=$(echo "$NAME_NO_EXT.mp4" | sed "s/['\":*?<>|]/_/g")
    OUT_MP4="$DIR_NAME/$SAFE_NAME"
    # TMP_MP4 is no longer used for processing, we use LOCAL_DST
    
    # Define local temp paths
    LOCAL_SRC="$WORK_ROOT/$BASE_NAME"
    LOCAL_DST="$WORK_ROOT/$SAFE_NAME.tmp.mp4"

    log "[$COUNT/$TOTAL] Processing: $REL_PATH"

    if [[ -f "$OUT_MP4" && "$OVERWRITE_MP4" == "false" && "$TEST_MODE" == "false" ]]; then
        log "  ↷ mp4 exists (skip): $(basename "$OUT_MP4")"
        continue
    fi
    
    # Copy to local temp
    log "  Copying to local temp..."
    if ! robust_copy "$FILE" "$LOCAL_SRC"; then
        log "  ✗ Failed to copy to local temp after $MAX_RETRIES attempts"
        FAILURE_LIST+=("$REL_PATH (copy failed)")
        continue
    fi

    # Detect Interlacing (sets DETECTED_OPTS)
    detect_interlacing "$LOCAL_SRC"
    
    # Build Command
    build_ffmpeg_command "$LOCAL_SRC" "$LOCAL_DST" "$DETECTED_OPTS"

    # Construct safe command string for logging
    CMD_STR=""
    for arg in "${FFMPEG_CMD[@]}"; do
        CMD_STR="$CMD_STR $(printf %q "$arg")"
    done

    if [[ "$DRY_RUN" == "true" ]]; then
        log "  [DRY] $CMD_STR"
        continue
    fi

    log "  [CMD] $CMD_STR"

    # Run conversion
    OUTPUT=$("${FFMPEG_CMD[@]}" 2>&1 < /dev/null)
    RET=$?

    if [[ $RET -ne 0 ]]; then
        log "  ✗ ffmpeg failed (exit code $RET)"
        if [[ "$VERBOSE" == "true" ]]; then
            echo "$OUTPUT" | tee -a "$LOG_FILE"
        else
             echo "$OUTPUT" >> "$LOG_FILE"
        fi
        rm -f "$LOCAL_DST"
        log "Error: $FILE"
        
        # Indent output for report
        INDENTED_OUTPUT=$(echo "$OUTPUT" | sed 's/^/            /')
        FAILURE_LIST+=("$REL_PATH (ffmpeg exit $RET)
$INDENTED_OUTPUT")
        # Cleanup source
        rm -f "$LOCAL_SRC"
        continue
    fi

    # Verify output with ffprobe
    if ! ffprobe -v error -select_streams v:0 -show_entries stream=codec_type -of json "$LOCAL_DST" | grep -q '"codec_type": "video"'; then
        log "  ✗ output invalid or no video stream"
        rm -f "$LOCAL_DST"
        log "Error: $FILE"
        FAILURE_LIST+=("$REL_PATH (no video stream)")
        # Cleanup source
        rm -f "$LOCAL_SRC"
        continue
    fi

    if [[ "$TEST_MODE" == "true" ]]; then
        log "  ✓ converted (test mode: tmp file kept in $LOCAL_DST, source not moved)"
        log "Success: $FILE"
        SUCCESS_LIST+=("$REL_PATH")
        # We might NOT want to clean up in test mode if user wants to inspect?
        # User request says "process it there and then copy back".
        # For test mode, maybe just leave it in work dir or move to original dir as .tmp?
        # The original code left it as .tmp.mp4 in the original dir.
        # Let's move it to original dir as .tmp.mp4 for inspection to preserve behavior.
        mv "$LOCAL_DST" "$DIR_NAME/$SAFE_NAME.tmp.mp4"
        rm -f "$LOCAL_SRC"
        continue
    fi

    # Move temp to final
    mv "$LOCAL_DST" "$OUT_MP4"
    log "  ✓ converted $FILE"
    
    # Cleanup local source
    rm -f "$LOCAL_SRC"

    # Archive original
    REL_DIR=$(dirname "$REL_PATH")
    ARCHIVE_DIR="$ARCHIVE_ROOT/$REL_DIR"
    mkdir -p "$ARCHIVE_DIR"
    
    mv "$FILE" "$ARCHIVE_DIR/"
    sync

    # Handle sidecars
    for SC_SUFFIX in "xmp" "${EXT}.xmp"; do
        CAND1="${DIR_NAME}/${NAME_NO_EXT}.xmp"
        if [[ -f "$CAND1" ]]; then mv "$CAND1" "$ARCHIVE_DIR/"; fi
        CAND2="${FILE}.xmp"
        if [[ -f "$CAND2" ]]; then mv "$CAND2" "$ARCHIVE_DIR/"; fi
    done
    sync

    ls -l "$ARCHIVE_DIR/" > /dev/null

    log "  ✓ archived source file -- $FILE --  to -- $ARCHIVE_DIR/ --"
    log "Success: $FILE"
    SUCCESS_LIST+=("$REL_PATH")
done 9< <(echo "$FILES_LIST")

print_report

log "Done."
