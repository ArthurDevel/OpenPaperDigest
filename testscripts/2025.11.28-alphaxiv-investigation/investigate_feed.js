const puppeteer = require('puppeteer');
const fs = require('fs');

(async () => {
    console.log('Launching browser...');
    const browser = await puppeteer.launch({
        headless: "new",
        args: ['--no-sandbox', '--disable-setuid-sandbox']
    });
    const page = await browser.newPage();

    const jsonResponses = [];

    await page.setRequestInterception(true);

    page.on('request', request => {
        request.continue();
    });

    page.on('response', async response => {
        const url = response.url();
        const contentType = response.headers()['content-type'];

        if (contentType && (contentType.includes('application/json') || url.includes('json'))) {
            try {
                // Clone the response because .json() consumes it? No, puppeteer response.json() gets the body.
                // But sometimes it fails if the response is empty or 304.
                if (response.request().resourceType() === 'xhr' || response.request().resourceType() === 'fetch') {
                    const data = await response.json();
                    console.log(`Captured JSON from: ${url}`);
                    jsonResponses.push({
                        url: url,
                        data: data
                    });
                }
            } catch (e) {
                // console.log(`Failed to parse JSON from ${url}: ${e.message}`);
            }
        }
    });

    console.log('Navigating to https://www.alphaxiv.org/state-of-the-art...');
    try {
        await page.goto('https://www.alphaxiv.org/state-of-the-art', { waitUntil: 'networkidle0', timeout: 60000 });
    } catch (e) {
        console.log('Navigation timeout or error:', e.message);
    }

    console.log('Waiting for additional requests...');
    await new Promise(r => setTimeout(r, 5000));

    // Capture page content after navigation and waiting
    const content = await page.content();

    console.log(`Captured ${jsonResponses.length} JSON responses.`);
    fs.writeFileSync('testscripts/2025.11.28-alphaxiv-investigation/output/json_responses.json', JSON.stringify(jsonResponses, null, 2));
    fs.writeFileSync('testscripts/2025.11.28-alphaxiv-investigation/output/page_content.html', content);
    fs.writeFileSync('testscripts/2025.11.28-alphaxiv-investigation/output/all_requests.log', requestLog.join('\n'));

    console.log('Closing browser...');
    await browser.close();
})();
