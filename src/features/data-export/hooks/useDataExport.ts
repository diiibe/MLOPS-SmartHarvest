
import { useState, useCallback, useRef } from 'react';
import { getExportMetadata } from '@/features/data-export/utils/exportMetadata';


interface ExportOptions {
    fileName?: string;
    onSuccess?: () => void;
    onError?: (error: Error) => void;
}

export const useDataExport = (data: Record<string, unknown>[], filters: unknown) => {
    const [isExporting, setIsExporting] = useState(false);
    const [progress, setProgress] = useState(0);

    // Fix Stale Closures: Keep track of latest data/filters with refs
    const dataRef = useRef(data);
    const filtersRef = useRef(filters);

    // Update refs when dependencies change
    dataRef.current = data;
    filtersRef.current = filters;

    const exportCSV = useCallback(async (options: ExportOptions = {}) => {
        setIsExporting(true);
        setProgress(0);

        try {
            // Use ref to get latest data
            const currentData = dataRef.current;

            if (!currentData || currentData.length === 0) {
                throw new Error('No data to export');
            }

            // Initialize Worker
            const worker = new Worker(new URL('../workers/export.worker.ts', import.meta.url), { type: 'module' });

            worker.onmessage = (e) => {
                const { type, blob, progress: workerProgress, error } = e.data;

                if (type === 'PROGRESS') {
                    setProgress(workerProgress);
                } else if (type === 'SUCCESS') {
                    const url = URL.createObjectURL(blob);

                    const link = document.createElement('a');
                    link.href = url;
                    link.setAttribute('download', options.fileName || 'export.csv');
                    document.body.appendChild(link);
                    link.click();
                    document.body.removeChild(link);

                    // Clean up: Revoke URL and terminate worker
                    requestAnimationFrame(() => {
                        URL.revokeObjectURL(url);
                        worker.terminate();
                    });

                    options.onSuccess?.();
                    setIsExporting(false);
                    setProgress(100);
                } else if (type === 'ERROR') {
                    console.error('Worker Error:', error);
                    options.onError?.(new Error(error));
                    worker.terminate();
                    setIsExporting(false);
                }
            };

            worker.onerror = (err) => {
                console.error('Worker Script Error:', err);
                options.onError?.(new Error('Worker script failed'));
                worker.terminate();
                setIsExporting(false);
            };

            // Phase 4: Fetch Metadata
            const metadata = await getExportMetadata();

            // Send data to worker
            worker.postMessage({
                type: 'GENERATE_CSV',
                data: currentData,
                metadata
            });

        } catch (error) {
            console.error('Export failed:', error);
            options.onError?.(error as Error);
            setIsExporting(false);
        }
    }, []); // Empty dependency array relying on Refs

    return {
        exportCSV,
        isExporting,
        progress
    };
};
