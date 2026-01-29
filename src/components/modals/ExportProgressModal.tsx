
import React from 'react';
import { Loader2 } from 'lucide-react';

interface ExportProgressModalProps {
    isOpen: boolean;
    progress: number;
}

export const ExportProgressModal: React.FC<ExportProgressModalProps> = ({ isOpen, progress }) => {
    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/80 backdrop-blur-sm">
            <div className="bg-[#1a1a1a] border border-gray-700 rounded-2xl p-8 w-[400px] shadow-2xl space-y-6">
                <div className="text-center space-y-2">
                    <div className="mx-auto w-12 h-12 bg-blue-500/10 rounded-full flex items-center justify-center">
                        <Loader2 className="w-6 h-6 text-blue-500 animate-spin" />
                    </div>
                    <h3 className="text-lg font-bold text-white">Esportazione in corso...</h3>
                    <p className="text-sm text-gray-400">Stiamo generando il tuo file CSV ottimizzato.</p>
                </div>

                <div className="space-y-2">
                    <div className="flex justify-between text-xs font-medium text-gray-500">
                        <span>Progress</span>
                        <span>{Math.round(progress)}%</span>
                    </div>
                    <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
                        <div
                            className="h-full bg-gradient-to-r from-blue-500 to-emerald-500 transition-all duration-300 ease-out"
                            style={{ width: `${progress}%` }}
                        />
                    </div>
                </div>

                <div className="pt-2 text-center">
                    <p className="text-[10px] text-gray-600 uppercase tracking-widest animate-pulse">
                        Sanitizing • Formatting • Packaging
                    </p>
                </div>
            </div>
        </div>
    );
};
