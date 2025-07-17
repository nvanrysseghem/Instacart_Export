# Instacart_Extract (Raspberry Pi 3 Optimized Version)

This project has been modified to run efficiently on a Raspberry Pi 3 running Raspbian OS.

## 🔧 Requirements

### System Dependencies (install via apt)
```bash
sudo apt update
sudo apt install -y python3-pip chromium-browser chromium-chromedriver python3-levenshtein nodejs rsync
```

### Python Dependencies
```bash
pip3 install -r requirements.txt
```

## 🚀 Setup Instructions

1. Extract the ZIP package.
2. Make the install script executable and run it:
```bash
chmod +x installChromeDriver.sh
./installChromeDriver.sh
```

3. Make the backup script executable:
```bash
chmod +x backup.sh
```

4. Run the pipeline using:
```bash
./backup.sh path/to/save_dir [optional_copy_dir] [optional_script_to_run]
```

Or run individual steps:
```bash
python3 main.py --file path/to/instacart_orders.json
python3 analyze.py path/to/instacart_orders.json
node downloadImages.js path/to/instacart_orders.json
```

## 📁 Contents

- `main.py` – Selenium scraper (headless, Pi-ready)
- `analyze.py` – Analysis tool (optimized with `rapidfuzz`)
- `downloadImages.js` – Downloads product images
- `installChromeDriver.sh` – Installs Chromium + chromedriver
- `backup.sh` – Optional full pipeline runner
- `requirements.txt` – Python and system dependencies

## 🧠 Notes

- `tkinter` removed to support headless use.
- Replaced `fuzzywuzzy` with faster `rapidfuzz`.
- Scripts are tested for minimal CPU/RAM impact on Raspberry Pi 3.
