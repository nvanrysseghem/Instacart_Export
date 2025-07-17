const http = require('http');
const https = require('https');
const fs = require('fs');
const path = require('path');
const { promisify } = require('util');
const { pipeline } = require('stream');
const pipelineAsync = promisify(pipeline);

// Configuration
const CONFIG = {
    maxConcurrent: 5,  // Limit concurrent downloads for Pi's limited resources
    retryAttempts: 3,
    retryDelay: 1000,
    timeout: 30000
};

class ImageDownloader {
    constructor(config = CONFIG) {
        this.config = config;
        this.downloadQueue = [];
        this.activeDownloads = 0;
        this.completed = 0;
        this.failed = [];
        this.total = 0;
    }

    async downloadWithRetry(url, destPath, attempts = this.config.retryAttempts) {
        for (let i = 0; i < attempts; i++) {
            try {
                await this.downloadImage(url, destPath);
                return true;
            } catch (error) {
                console.error(`Attempt ${i + 1} failed for ${url}: ${error.message}`);
                if (i < attempts - 1) {
                    await new Promise(resolve => setTimeout(resolve, this.config.retryDelay));
                } else {
                    this.failed.push({ url, destPath, error: error.message });
                    return false;
                }
            }
        }
    }

    downloadImage(url, destPath) {
        const protocol = url.startsWith('https') ? https : http;

        return new Promise((resolve, reject) => {
            const request = protocol.get(url, { timeout: this.config.timeout }, async (response) => {
                if (response.statusCode !== 200) {
                    reject(new Error(`HTTP ${response.statusCode}`));
                    return;
                }

                try {
                    await pipelineAsync(response, fs.createWriteStream(destPath));
                    resolve();
                } catch (error) {
                    fs.unlink(destPath, () => {});
                    reject(error);
                }
            });

            request.on('error', reject);
            request.on('timeout', () => {
                request.destroy();
                reject(new Error('Download timeout'));
            });
        });
    }

    async processQueue() {
        while (this.downloadQueue.length > 0 || this.activeDownloads > 0) {
            while (this.activeDownloads < this.config.maxConcurrent && this.downloadQueue.length > 0) {
                const task = this.downloadQueue.shift();
                this.activeDownloads++;
                
                this.downloadWithRetry(task.url, task.destPath)
                    .then(() => {
                        this.completed++;
                        this.printProgress();
                    })
                    .finally(() => {
                        this.activeDownloads--;
                    });
            }
            
            await new Promise(resolve => setTimeout(resolve, 100));
        }
    }

    printProgress() {
        const percentage = Math.round((this.completed / this.total) * 100);
        process.stdout.write(`\rProgress: ${this.completed}/${this.total} (${percentage}%) | Failed: ${this.failed.length}`);
    }

    addToQueue(url, destPath) {
        if (!fs.existsSync(destPath)) {
            this.downloadQueue.push({ url, destPath });
            this.total++;
        }
    }
}

const mkdirIfNotExists = (dir) => {
    if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
    }
};

const sanitizeFilename = (filename) => {
    return filename.replace(/[^a-z0-9.-]/gi, '_');
};

async function main() {
    const ordersFile = process.argv[2];
    if (!ordersFile || !fs.existsSync(ordersFile)) {
        console.error('Please provide a valid orders JSON file path');
        process.exit(1);
    }

    const orders = JSON.parse(fs.readFileSync(ordersFile, 'utf8'));
    const saveDir = path.dirname(ordersFile);
    
    const deliveriesDir = path.join(saveDir, 'delivery_photos');
    const productsDir = path.join(saveDir, 'product_thumbnails');
    
    mkdirIfNotExists(deliveriesDir);
    mkdirIfNotExists(productsDir);

    const downloader = new ImageDownloader();
    
    // Queue all downloads
    for (const order of orders) {
        if (order.deliveryPhotoUrl) {
            const filename = sanitizeFilename(
                `${order.dateTime.replace(/[: ]/g, '-')}${path.extname(order.deliveryPhotoUrl)}`
            );
            const destPath = path.join(deliveriesDir, filename);
            downloader.addToQueue(order.deliveryPhotoUrl, destPath);
        }
        
        for (const item of order.items || []) {
            if (item.thumbnailUrl) {
                const filename = sanitizeFilename(path.basename(item.thumbnailUrl));
                const destPath = path.join(productsDir, filename);
                downloader.addToQueue(item.thumbnailUrl, destPath);
            }
        }
    }

    console.log(`Starting download of ${downloader.total} images...`);
    
    await downloader.processQueue();
    
    console.log('\n\nDownload complete!');
    console.log(`Successfully downloaded: ${downloader.completed}`);
    
    if (downloader.failed.length > 0) {
        console.log(`Failed downloads: ${downloader.failed.length}`);
        const failedLog = path.join(saveDir, 'failed_downloads.json');
        fs.writeFileSync(failedLog, JSON.stringify(downloader.failed, null, 2));
        console.log(`Failed downloads logged to: ${failedLog}`);
    }
}

main().catch(error => {
    console.error('Fatal error:', error);
    process.exit(1);
});
