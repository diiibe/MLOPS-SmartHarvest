
import { sanitizeData } from '@/utils/csvSanitizer';

self.onmessage = (e: MessageEvent) => {
    const { data, metadata, type } = e.data;

    if (type === 'GENERATE_CSV') {
        try {
            // Report start
            self.postMessage({ type: 'PROGRESS', progress: 10 });

            // Sanitize
            const sanitizedData = sanitizeData(data);
            self.postMessage({ type: 'PROGRESS', progress: 50 });

            if (sanitizedData.length === 0) {
                throw new Error('No data to export');
            }

            // Generate CSV
            const metaRows = metadata ? [
                `# ModelID: ${metadata.modelId}`,
                `# Version: ${metadata.versionHash}`,
                `# Date: ${metadata.timestamp}`,
                ''
            ] : [];

            const headers = Object.keys(sanitizedData[0]).join(',');
            const rows = sanitizedData.map(row => Object.values(row).join(','));
            const csvContent = [...metaRows, headers, ...rows].join('\n');

            self.postMessage({ type: 'PROGRESS', progress: 90 });

            // Create Blob
            const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });

            // Send back the blob
            self.postMessage({ type: 'SUCCESS', blob });

        } catch (error) {
            self.postMessage({ type: 'ERROR', error: (error as Error).message });
        }
    }
};
