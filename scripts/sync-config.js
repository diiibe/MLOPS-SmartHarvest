
const fs = require('fs');
const path = require('path');

// Paths
const BACKEND_DIR = path.resolve(__dirname, '../../MLOPS-SmartHarvest');
const FRONTEND_PUBLIC_DIR = path.resolve(__dirname, '../public');

// Files to sync
const ROI_FILE = 'roi.json';

const syncConfig = () => {
    const sourcePath = path.join(BACKEND_DIR, ROI_FILE);
    const destPath = path.join(FRONTEND_PUBLIC_DIR, 'backend_config.json'); // Rename to be clear it's from backend

    console.log(`Syncing config from ${BACKEND_DIR} to ${FRONTEND_PUBLIC_DIR}...`);

    if (fs.existsSync(sourcePath)) {
        try {
            const data = fs.readFileSync(sourcePath);
            // We might want to wrap it or parse it, but for now direct copy is fine
            // Or we can create a composite config file.

            // Let's read config.py if possible? No, sticking to JSON is safer for this script.
            // Assumption: roi.json contains the geometry.

            fs.writeFileSync(destPath, data);
            console.log(`Successfully synced ${ROI_FILE} to backend_config.json`);
        } catch (e) {
            console.error('Error syncing config:', e);
            process.exit(1);
        }
    } else {
        console.warn(`Warning: ${ROI_FILE} not found in backend. Using default/empty config.`);
        // Create an empty config to prevent frontend crash
        fs.writeFileSync(destPath, JSON.stringify({ coordinates: [] }));
    }
};

syncConfig();
