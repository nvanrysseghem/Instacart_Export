# Instacart Export - Setup and Optimization Guide

## 🚀 Quick Start

1. **Install System Dependencies**
```bash
chmod +x installChromeDriver.sh
./installChromeDriver.sh
```

2. **Install Python Dependencies**
```bash
# For Raspberry Pi, use --no-cache-dir to save space
pip3 install --no-cache-dir -r requirements.txt
```

3. **Configure Environment**
```bash
# Create .env file
cat > .env << EOF
INSTACART_EMAIL=your_email@example.com
# Optional: Add other config here
EOF

# Create config file
cat > .backup_config << EOF
# Default configuration for backup.sh
DEBUG=0
HEADLESS=1
PARALLEL=3  # Reduced for Pi's limited resources
FORMAT=csv
EOF
```

4. **First Run**
```bash
./backup.sh ~/instacart_data --headless
```

## 🔧 Performance Optimizations

### For Raspberry Pi 3

1. **Memory Management**
   - Enable swap if not already enabled:
   ```bash
   sudo dphys-swapfile swapoff
   sudo sed -i 's/CONF_SWAPSIZE=100/CONF_SWAPSIZE=1024/' /etc/dphys-swapfile
   sudo dphys-swapfile setup
   sudo dphys-swapfile swapon
   ```

2. **Chrome Optimization**
   - The scripts already disable GPU, images, and unnecessary features
   - Consider using `chromium-browser` instead of `google-chrome` (lighter)

3. **Parallel Downloads**
   - Default is 5 concurrent downloads
   - For Pi 3, reduce to 2-3: `./backup.sh ~/data --parallel 3`

4. **Headless Mode**
   - Always use `--headless` flag to save resources
   - Saves ~200MB RAM vs GUI mode

### Storage Optimization

1. **Image Compression** (optional post-processing script)
```bash
#!/bin/bash
# save as compress_images.sh
find "$1" -name "*.jpg" -o -name "*.jpeg" | while read img; do
    jpegoptim --max=85 "$img"
done
find "$1" -name "*.png" | while read img; do
    optipng -o2 "$img"
done
```

2. **Regular Cleanup**
```bash
# Remove duplicate product thumbnails
fdupes -rdN ~/instacart_data/product_thumbnails/

# Archive old delivery photos
tar -czf delivery_photos_2023.tar.gz ~/instacart_data/delivery_photos/2023-*
rm ~/instacart_data/delivery_photos/2023-*
```

## 📊 Advanced Analysis

### Custom Analysis Queries

1. **Monthly Spending Trend**
```python
# add to analyze.py or run separately
import json
import pandas as pd
from datetime import datetime

with open('instacart_orders.json', 'r') as f:
    orders = json.load(f)

df = pd.DataFrame(orders)
df['date'] = pd.to_datetime(df['dateTime'])
df['month'] = df['date'].dt.to_period('M')
df['total_float'] = df['total'].str.replace('$', '').astype(float)

monthly = df.groupby('month')['total_float'].agg(['sum', 'count', 'mean'])
print(monthly)
```

2. **Product Price History**
```bash
# Extract price history for specific product
python3 analyze.py orders.json --format json | \
  jq '.items[] | select(.name | contains("Milk")) | {name, price_changes}'
```

## 🛡️ Security Best Practices

1. **Credential Management**
   - Never commit `.env` file to git
   - Use `chmod 600 .env` to restrict access
   - Consider using system keyring instead:
   ```python
   import keyring
   keyring.set_password("instacart", "email", "your_email@example.com")
   ```

2. **Session Management**
   - Chrome profile stores cookies - protect it:
   ```bash
   chmod -R 700 ~/.config/chromium/Default
   ```

3. **Network Security**
   - Use VPN if scraping frequently
   - Add random delays between requests (already implemented)

## 🐛 Troubleshooting

### Common Issues

1. **"Chrome not reachable"**
   ```bash
   # Check Chrome/Chromium installation
   chromium-browser --version
   # or
   google-chrome --version
   
   # Check chromedriver
   chromedriver --version
   ```

2. **Out of Memory**
   - Increase swap (see above)
   - Use `--skip-images` initially
   - Process in batches with `--after` flag

3. **Slow Performance**
   - Disable unnecessary services:
   ```bash
   sudo systemctl disable bluetooth
   sudo systemctl disable avahi-daemon
   ```
   - Use faster SD card (Class 10 or better)

4. **Login Issues**
   - Clear Chrome profile:
   ```bash
   rm -rf ~/.config/chromium/Default/Cookies
   ```
   - Try manual login first:
   ```bash
   chromium-browser https://www.instacart.ca
   ```

## 📈 Monitoring

### Performance Monitoring
```bash
# Create monitoring script
cat > monitor.sh << 'EOF'
#!/bin/bash
echo "=== System Stats ==="
echo "CPU Usage: $(top -bn1 | grep "Cpu(s)" | awk '{print $2 + $4"%"}')"
echo "Memory: $(free -h | awk '/^Mem:/ {print $3 "/" $2}')"
echo "Swap: $(free -h | awk '/^Swap:/ {print $3 "/" $2}')"
echo "Disk: $(df -h / | awk 'NR==2 {print $3 "/" $2 " (" $5 ")"}')"
echo "Temperature: $(vcgencmd measure_temp)"
EOF
chmod +x monitor.sh
```

### Log Analysis
```bash
# Most common errors
grep ERROR logs/*.log | cut -d' ' -f4- | sort | uniq -c | sort -nr

# Average scraping time
grep "Scraping completed" logs/*.log | awk '{print $1}' | \
  xargs -I{} date -d {} +%s | awk '{if(NR>1)print $1-prev; prev=$1}' | \
  awk '{sum+=$1} END {print "Average: " sum/NR/60 " minutes"}'
```

## 🔄 Automation

### Cron Setup
```bash
# Add to crontab for weekly backups
crontab -e

# Run every Sunday at 2 AM
0 2 * * 0 /home/pi/instacart_export/backup.sh /home/pi/instacart_data --headless >> /home/pi/instacart_export/logs/cron.log 2>&1

# With notification
0 2 * * 0 /home/pi/instacart_export/backup.sh /home/pi/instacart_data --headless && echo "Instacart backup completed" | mail -s "Backup Success" your@email.com
```

### Systemd Service (Alternative)
```bash
# Create service file
sudo cat > /etc/systemd/system/instacart-backup.service << EOF
[Unit]
Description=Instacart Order Backup
After=network.target

[Service]
Type=oneshot
User=pi
WorkingDirectory=/home/pi/instacart_export
ExecStart=/home/pi/instacart_export/backup.sh /home/pi/instacart_data --headless
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Create timer
sudo cat > /etc/systemd/system/instacart-backup.timer << EOF
[Unit]
Description=Run Instacart Backup Weekly
Requires=instacart-backup.service

[Timer]
Unit=instacart-backup.service
OnCalendar=weekly
Persistent=true

[Install]
WantedBy=timers.target
EOF

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable instacart-backup.timer
sudo systemctl start instacart-backup.timer
```

## 📊 Data Export Options

### Export to Google Sheets
```python
# Add to a new file: export_to_sheets.py
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
import json

# Setup credentials (follow Google Sheets API guide)
scope = ['https://spreadsheets.google.com/feeds',
         'https://www.googleapis.com/auth/drive']
creds = Credentials.from_service_account_file('credentials.json', scopes=scope)
client = gspread.authorize(creds)

# Load analysis
df = pd.read_csv('instacart_orders.json.analysis.csv')

# Create/update sheet
sheet = client.create('Instacart Orders Analysis')
worksheet = sheet.get_worksheet(0)
worksheet.update([df.columns.values.tolist()] + df.values.tolist())
```

### SQLite Database
```python
# Add to a new file: export_to_sqlite.py
import sqlite3
import json
import pandas as pd

# Load data
with open('instacart_orders.json', 'r') as f:
    orders = json.load(f)

# Create database
conn = sqlite3.connect('instacart.db')

# Orders table
orders_df = pd.DataFrame(orders)
orders_df.to_sql('orders', conn, if_exists='replace', index=False)

# Items table (normalized)
items = []
for order in orders:
    for item in order.get('items', []):
        item['order_date'] = order['dateTime']
        items.append(item)

items_df = pd.DataFrame(items)
items_df.to_sql('items', conn, if_exists='replace', index=False)

conn.close()
```

## 🎯 Next Steps

1. **Add Receipt OCR** - Extract prices from delivery photos
2. **Barcode Scanning** - Track physical inventory
3. **Price Prediction** - ML model for price trends
4. **Shopping List Generator** - Based on consumption patterns
5. **Integration with Meal Planning** - Connect to recipe databases

## 📚 Additional Resources

- [Selenium Documentation](https://selenium-python.readthedocs.io/)
- [Raspberry Pi Optimization Guide](https://www.raspberrypi.org/documentation/)
- [Chrome DevTools Protocol](https://chromedevtools.github.io/devtools-protocol/)
- [Web Scraping Best Practices](https://blog.apify.com/web-scraping-guide/)
