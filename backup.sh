#!/bin/bash
# Enhanced Instacart backup pipeline with better error handling and features

set -euo pipefail  # Exit on error, undefined variables, pipe failures

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"

# Default configuration
CONFIG_FILE="${SCRIPT_DIR}/.backup_config"
LOG_DIR="${SCRIPT_DIR}/logs"
LOG_FILE="${LOG_DIR}/backup_$(date +%Y%m%d_%H%M%S).log"

# Function to display usage
usage() {
    cat << EOF
Usage: $0 [OPTIONS] SAVE_DIR [COPY_DIR] [POST_SCRIPT]

Enhanced Instacart backup pipeline

Arguments:
  SAVE_DIR      Directory to save scraped data (required)
  COPY_DIR      Optional directory to copy delivery photos
  POST_SCRIPT   Optional script to run on copied photos

Options:
  -h, --help          Show this help message
  -c, --config FILE   Use custom config file
  -d, --debug         Enable debug mode
  -s, --skip-scrape   Skip scraping, only analyze existing data
  -i, --skip-images   Skip image downloads
  -a, --after DATE    Only process orders after DATE (Y-m-d H:M)
  -f, --format FMT    Analysis output format (csv|json, default: csv)
  --insights          Show shopping insights after analysis
  --headless          Run scraper in headless mode
  --parallel N        Download images with N parallel connections (default: 5)

Examples:
  $0 ~/instacart_backup
  $0 ~/instacart_backup ~/photos --after "2024-01-01 00:00"
  $0 -s -i ~/instacart_backup --insights

EOF
}

# Function to log messages
log() {
    local level=$1
    shift
    local message="$@"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    # Log to file
    echo "[$timestamp] [$level] $message" >> "$LOG_FILE"
    
    # Log to console with colors
    case $level in
        ERROR)
            echo -e "${RED}[ERROR]${NC} $message" >&2
            ;;
        WARN)
            echo -e "${YELLOW}[WARN]${NC} $message" >&2
            ;;
        INFO)
            echo -e "${GREEN}[INFO]${NC} $message"
            ;;
        DEBUG)
            if [[ "${DEBUG:-0}" == "1" ]]; then
                echo -e "${BLUE}[DEBUG]${NC} $message"
            fi
            ;;
    esac
}

# Function to check dependencies
check_dependencies() {
    local missing=()
    
    # Check Python dependencies
    if ! command -v python3 &> /dev/null; then
        missing+=("python3")
    fi
    
    if ! command -v node &> /dev/null; then
        missing+=("nodejs")
    fi
    
    if ! command -v chromium-browser &> /dev/null && ! command -v google-chrome &> /dev/null; then
        missing+=("chromium-browser or google-chrome")
    fi
    
    # Check Python packages
    local python_packages=("selenium" "selenium_stealth" "rapidfuzz" "python-dotenv")
    for pkg in "${python_packages[@]}"; do
        if ! python3 -c "import $pkg" 2>/dev/null; then
            missing+=("Python package: $pkg")
        fi
    done
    
    if [ ${#missing[@]} -ne 0 ]; then
        log ERROR "Missing dependencies:"
        for dep in "${missing[@]}"; do
            log ERROR "  - $dep"
        done
        log INFO "Run ./installChromeDriver.sh to install system dependencies"
        log INFO "Run pip3 install -r requirements.txt to install Python dependencies"
        return 1
    fi
    
    return 0
}

# Function to create necessary directories
setup_directories() {
    local save_dir=$1
    
    mkdir -p "$save_dir"
    mkdir -p "$LOG_DIR"
    mkdir -p "$save_dir/delivery_photos"
    mkdir -p "$save_dir/product_thumbnails"
    
    log INFO "Created directory structure in $save_dir"
}

# Function to run scraper
run_scraper() {
    local save_dir=$1
    local orders_file="$save_dir/instacart_orders.json"
    local cmd="python3 '$SCRIPT_DIR/main.py' --file '$orders_file'"
    
    if [[ -n "${AFTER_DATE:-}" ]]; then
        cmd="$cmd --after '$AFTER_DATE'"
    fi
    
    if [[ "${HEADLESS:-0}" == "1" ]]; then
        cmd="$cmd --headless"
    fi
    
    if [[ "${DEBUG:-0}" == "1" ]]; then
        cmd="$cmd --debug"
    fi
    
    log INFO "Starting order scraping..."
    log DEBUG "Command: $cmd"
    
    if eval "$cmd" 2>&1 | tee -a "$LOG_FILE"; then
        log INFO "Scraping completed successfully"
        return 0
    else
        log ERROR "Scraping failed"
        return 1
    fi
}

# Function to run analyzer
run_analyzer() {
    local save_dir=$1
    local orders_file="$save_dir/instacart_orders.json"
    local cmd="python3 '$SCRIPT_DIR/analyze.py' '$orders_file'"
    
    if [[ -n "${AFTER_DATE:-}" ]]; then
        cmd="$cmd --after '$AFTER_DATE'"
    fi
    
    if [[ -n "${FORMAT:-}" ]]; then
        cmd="$cmd --format '$FORMAT'"
    fi
    
    if [[ "${INSIGHTS:-0}" == "1" ]]; then
        cmd="$cmd --insights"
    fi
    
    log INFO "Starting order analysis..."
    log DEBUG "Command: $cmd"
    
    if eval "$cmd" 2>&1 | tee -a "$LOG_FILE"; then
        log INFO "Analysis completed successfully"
        return 0
    else
        log ERROR "Analysis failed"
        return 1
    fi
}

# Function to download images
download_images() {
    local save_dir=$1
    local orders_file="$save_dir/instacart_orders.json"
    local node_script="$SCRIPT_DIR/downloadImages.js"
    
    # Use optimized downloader if available
    if [[ -f "$SCRIPT_DIR/downloadImages_optimized.js" ]]; then
        node_script="$SCRIPT_DIR/downloadImages_optimized.js"
    fi
    
    log INFO "Starting image downloads (parallel: ${PARALLEL:-5})..."
    
    if NODE_ENV="PARALLEL=${PARALLEL:-5}" node "$node_script" "$orders_file" 2>&1 | tee -a "$LOG_FILE"; then
        log INFO "Image downloads completed"
        return 0
    else
        log ERROR "Image downloads failed"
        return 1
    fi
}

# Function to copy photos and run post-processing
process_delivery_photos() {
    local save_dir=$1
    local copy_dir=$2
    local post_script=$3
    
    if [[ -z "$copy_dir" ]]; then
        return 0
    fi
    
    log INFO "Copying delivery photos to $copy_dir"
    
    local temp_dir=$(mktemp -d)
    trap "rm -rf '$temp_dir'" EXIT
    
    # Copy photos to temp directory
    if rsync -av "$save_dir/delivery_photos/" "$temp_dir/" >> "$LOG_FILE" 2>&1; then
        log INFO "Photos copied to temporary directory"
        
        # Run post-processing script if provided
        if [[ -n "$post_script" ]] && [[ -x "$post_script" ]]; then
            log INFO "Running post-processing script: $post_script"
            if "$post_script" "$temp_dir" 2>&1 | tee -a "$LOG_FILE"; then
                log INFO "Post-processing completed"
            else
                log WARN "Post-processing script failed"
            fi
        fi
        
        # Copy to final destination
        if rsync -av "$temp_dir/" "$copy_dir/" >> "$LOG_FILE" 2>&1; then
            log INFO "Photos copied to final destination"
        else
            log ERROR "Failed to copy photos to final destination"
            return 1
        fi
    else
        log ERROR "Failed to copy photos"
        return 1
    fi
    
    return 0
}

# Function to generate summary report
generate_summary() {
    local save_dir=$1
    local orders_file="$save_dir/instacart_orders.json"
    
    if [[ ! -f "$orders_file" ]]; then
        return
    fi
    
    local order_count=$(jq 'length' "$orders_file" 2>/dev/null || echo "0")
    local total_items=$(jq '[.[].items | length] | add' "$orders_file" 2>/dev/null || echo "0")
    local delivery_photos=$(find "$save_dir/delivery_photos" -type f 2>/dev/null | wc -l)
    local product_photos=$(find "$save_dir/product_thumbnails" -type f 2>/dev/null | wc -l)
    
    log INFO "=== Backup Summary ==="
    log INFO "Orders processed: $order_count"
    log INFO "Total items: $total_items"
    log INFO "Delivery photos: $delivery_photos"
    log INFO "Product thumbnails: $product_photos"
    log INFO "===================="
}

# Main function
main() {
    # Parse command line arguments
    local SAVE_DIR=""
    local COPY_DIR=""
    local POST_SCRIPT=""
    local SKIP_SCRAPE=0
    local SKIP_IMAGES=0
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                usage
                exit 0
                ;;
            -c|--config)
                CONFIG_FILE="$2"
                shift 2
                ;;
            -d|--debug)
                DEBUG=1
                shift
                ;;
            -s|--skip-scrape)
                SKIP_SCRAPE=1
                shift
                ;;
            -i|--skip-images)
                SKIP_IMAGES=1
                shift
                ;;
            -a|--after)
                AFTER_DATE="$2"
                shift 2
                ;;
            -f|--format)
                FORMAT="$2"
                shift 2
                ;;
            --insights)
                INSIGHTS=1
                shift
                ;;
            --headless)
                HEADLESS=1
                shift
                ;;
            --parallel)
                PARALLEL="$2"
                shift 2
                ;;
            -*)
                log ERROR "Unknown option: $1"
                usage
                exit 1
                ;;
            *)
                if [[ -z "$SAVE_DIR" ]]; then
                    SAVE_DIR="$1"
                elif [[ -z "$COPY_DIR" ]]; then
                    COPY_DIR="$1"
                elif [[ -z "$POST_SCRIPT" ]]; then
                    POST_SCRIPT="$1"
                fi
                shift
                ;;
        esac
    done
    
    # Validate arguments
    if [[ -z "$SAVE_DIR" ]]; then
        log ERROR "SAVE_DIR is required"
        usage
        exit 1
    fi
    
    # Load config file if exists
    if [[ -f "$CONFIG_FILE" ]]; then
        log DEBUG "Loading config from $CONFIG_FILE"
        source "$CONFIG_FILE"
    fi
    
    # Start backup process
    log INFO "Starting Instacart backup pipeline"
    log INFO "Save directory: $SAVE_DIR"
    log INFO "Log file: $LOG_FILE"
    
    # Check dependencies
    if ! check_dependencies; then
        exit 1
    fi
    
    # Setup directories
    setup_directories "$SAVE_DIR"
    
    # Run pipeline steps
    local exit_code=0
    
    if [[ $SKIP_SCRAPE -eq 0 ]]; then
        if ! run_scraper "$SAVE_DIR"; then
            exit_code=1
        fi
    else
        log INFO "Skipping scraper (--skip-scrape flag)"
    fi
    
    if [[ $exit_code -eq 0 ]]; then
        if ! run_analyzer "$SAVE_DIR"; then
            exit_code=1
        fi
    fi
    
    if [[ $exit_code -eq 0 ]] && [[ $SKIP_IMAGES -eq 0 ]]; then
        if ! download_images "$SAVE_DIR"; then
            log WARN "Image downloads failed, continuing..."
        fi
    elif [[ $SKIP_IMAGES -eq 1 ]]; then
        log INFO "Skipping image downloads (--skip-images flag)"
    fi
    
    if [[ $exit_code -eq 0 ]] && [[ -n "$COPY_DIR" ]]; then
        if ! process_delivery_photos "$SAVE_DIR" "$COPY_DIR" "$POST_SCRIPT"; then
            log WARN "Photo processing failed"
        fi
    fi
    
    # Update last backup timestamp
    if [[ $exit_code -eq 0 ]]; then
        echo "$(date)" > "$SAVE_DIR/lastBackedUp.txt"
        generate_summary "$SAVE_DIR"
        log INFO "Backup completed successfully"
    else
        log ERROR "Backup completed with errors"
    fi
    
    exit $exit_code
}

# Run main function
main "$@"
