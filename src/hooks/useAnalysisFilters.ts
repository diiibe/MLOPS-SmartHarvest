
import { useState } from 'react';

export interface DateRange {
    from: Date;
    to: Date;
}

export type TimeFrame = 'days' | 'weeks' | 'months';

export type PhenologicalStage = 'dormancy' | 'budbreak' | 'flowering' | 'veraison' | 'harvest' | 'custom';

export interface AnalysisFilters {
    vintage: number;
    setVintage: (year: number) => void;
    phenologicalStage: PhenologicalStage;
    setPhenologicalStage: (stage: PhenologicalStage) => void;
    dateRange: DateRange;
    setDateRange: (range: DateRange) => void;
    timeFrame: TimeFrame;
    setTimeFrame: (tf: TimeFrame) => void;
    selectedPolygons: any[];
    removePolygon: (id: string) => void;
    clearPolygons: () => void;
    isLoading: boolean;
    setLoading: (loading: boolean) => void;
}

export const useAnalysisFilters = (): AnalysisFilters => {
    const [vintage, setVintage] = useState<number>(new Date().getFullYear());
    const [phenologicalStage, setPhenologicalStage] = useState<PhenologicalStage>('custom');
    const [dateRange, setDateRange] = useState<DateRange>({ from: new Date(), to: new Date() });
    const [timeFrame, setTimeFrame] = useState<TimeFrame>('months');
    const [selectedPolygons] = useState<any[]>([]);
    const [isLoading, setLoading] = useState<boolean>(false);

    // Auto-update dates when switching phenological stages
    const handleStageChange = (stage: PhenologicalStage) => {
        setPhenologicalStage(stage);

        // Mock logic for auto-dates based on vintage
        // In real app, this would come from a configuration or agronomist data
        const v = vintage;
        switch (stage) {
            case 'budbreak': // Germogliamento (Northern Hemisphere: March/April)
                setDateRange({ from: new Date(v, 2, 20), to: new Date(v, 3, 30) });
                break;
            case 'flowering': // Fioritura (May/June)
                setDateRange({ from: new Date(v, 4, 15), to: new Date(v, 5, 20) });
                break;
            case 'veraison': // Invaiatura (July/August)
                setDateRange({ from: new Date(v, 6, 20), to: new Date(v, 7, 25) });
                break;
            case 'harvest': // Vendemmia (August/September/October)
                setDateRange({ from: new Date(v, 7, 25), to: new Date(v, 9, 15) });
                break;
            case 'dormancy': // Dormienza (Nov-Feb)
                setDateRange({ from: new Date(v, 10, 1), to: new Date(v + 1, 1, 28) });
                break;
        }
    };

    return {
        vintage,
        setVintage,
        phenologicalStage,
        setPhenologicalStage: handleStageChange,
        dateRange,
        setDateRange: (range) => {
            setDateRange(range);
            setPhenologicalStage('custom'); // Reset stage if manual override
        },
        timeFrame,
        setTimeFrame,
        selectedPolygons,
        removePolygon: () => { },
        clearPolygons: () => { },
        isLoading,
        setLoading
    };
};
