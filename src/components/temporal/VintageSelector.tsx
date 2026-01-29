
import React from 'react';
import { ChevronLeft, ChevronRight, Calendar } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface VintageSelectorProps {
    vintage: number;
    onVintageChange: (year: number) => void;
}

export const VintageSelector: React.FC<VintageSelectorProps> = ({ vintage, onVintageChange }) => {

    // Mock Quality Data (In real app, fetch from backend)
    const getVintageQuality = (year: number) => {
        if (year === 2024) return { stars: '⭐⭐⭐', label: 'Buona' };
        if (year === 2023) return { stars: '⭐⭐', label: 'Piovosa' };
        if (year === 2022) return { stars: '⭐⭐⭐⭐⭐', label: 'Eccellente' };
        return { stars: '...', label: 'N/A' };
    };

    const quality = getVintageQuality(vintage);

    return (
        <div className="flex items-center justify-between bg-[#1a1a1a] p-1 rounded-xl border border-gray-800">
            <Button
                variant="ghost"
                size="icon"
                onClick={() => onVintageChange(vintage - 1)}
                className="hover:bg-gray-800 text-gray-400 hover:text-white"
            >
                <ChevronLeft className="h-4 w-4" />
            </Button>

            <div className="flex flex-col items-center">
                <span className="text-[10px] uppercase tracking-widest text-blue-500 font-bold mb-0.5">Vendemmia</span>
                <div className="flex items-center gap-2">
                    <Calendar className="w-4 h-4 text-gray-500" />
                    <span className="text-xl font-bold text-white font-mono">{vintage}</span>
                </div>
                <span className="text-[9px] text-gray-500 font-medium mt-0.5" title="Qualità Annata">
                    {quality.stars} <span className="opacity-70">({quality.label})</span>
                </span>
            </div>

            <Button
                variant="ghost"
                size="icon"
                onClick={() => onVintageChange(vintage + 1)}
                className="hover:bg-gray-800 text-gray-400 hover:text-white"
            >
                <ChevronRight className="h-4 w-4" />
            </Button>
        </div>
    );
};
