
import React from 'react';
import { Sprout, Flower2, Grape, Scan, SunSnow } from 'lucide-react';
import { PhenologicalStage } from '@/hooks/useAnalysisFilters';
import { RichTooltip } from '@/components/ui/tooltip/RichTooltip';

interface PhenologySelectorProps {
    currentStage: PhenologicalStage;
    onStageChange: (stage: PhenologicalStage) => void;
}

export const PhenologySelector: React.FC<PhenologySelectorProps> = ({ currentStage, onStageChange }) => {

    const stages: { id: PhenologicalStage; label: string; icon: React.ReactNode; desc: string }[] = [
        { id: 'budbreak', label: 'Germogliamento', icon: <Sprout className="w-3 h-3" />, desc: "Inizio ciclo. Monitorare rischio gelate." },
        { id: 'flowering', label: 'Fioritura', icon: <Flower2 className="w-3 h-3" />, desc: "Fase critica per allegagione. Evitare stress." },
        { id: 'veraison', label: 'Invaiatura', icon: <Grape className="w-3 h-3" />, desc: "Cambio colore. Inizio accumulo zuccheri." },
        { id: 'harvest', label: 'Vendemmia', icon: <Scan className="w-3 h-3" />, desc: "Maturazione finale. Decisione raccolta." },
        { id: 'dormancy', label: 'Dormienza', icon: <SunSnow className="w-3 h-3" />, desc: "Riposo vegetativo. Potatura." },
    ];

    return (
        <div className="space-y-2">
            <label className="text-[10px] font-bold text-gray-500 uppercase tracking-widest ml-1">
                Fasi Fenologiche (Quick-Set)
            </label>
            <div className="grid grid-cols-5 gap-1">
                {stages.map((stage) => {
                    const isActive = currentStage === stage.id;
                    return (
                        <RichTooltip key={stage.id} content={stage.desc}>
                            <button
                                onClick={() => onStageChange(stage.id)}
                                className={`
                                    flex flex-col items-center justify-center p-2 rounded-lg transition-all duration-200 gap-1 border w-full
                                    ${isActive
                                        ? 'bg-blue-500/20 border-blue-500/50 text-blue-200 shadow-[0_0_15px_rgba(59,130,246,0.2)]'
                                        : 'bg-[#1a1a1a] border-transparent text-gray-500 hover:bg-[#252525] hover:text-gray-300'}
                                `}
                            >
                                {stage.icon}
                                <span className="text-[8px] font-medium truncate w-full text-center">{stage.label}</span>
                            </button>
                        </RichTooltip>
                    );
                })}
            </div>
        </div>
    );
};
