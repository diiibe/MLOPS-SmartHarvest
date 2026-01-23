import { useState } from 'react';
import { Grape, Tag, MapPin, ChevronDown, Calendar, Info, Save, Zap } from 'lucide-react';
import { useAnalysisFilters } from '@/hooks/useAnalysisFilters';
import { MasterTimeline } from '@/components/MasterTimeline';
import { UnifiedDatePicker } from '@/components/UnifiedDatePicker';
import { TimeFrameToggle } from '@/components/TimeFrameToggle';
import { PolygonManager } from '@/components/PolygonManager';
import { FiltersSkeleton } from '@/components/FiltersSkeleton';
import { Button } from '@/components/ui/button';
import '@/index.css';

function App() {
  const [projectName, setProjectName] = useState('Nuovo Progetto');
  const filters = useAnalysisFilters();

  const handleDateRangeChange = (range: any) => {
    if (range) {
      filters.setDateRange(range);
    }
  };

  const handleStartAnalysis = () => {
    filters.setLoading(true);
    // Simulate loading
    setTimeout(() => {
      alert(`Analisi avviata!\nProgetto: ${projectName}\nAnno: ${filters.currentYear}\nPeriodo: ${filters.dateRange.from?.toLocaleDateString()} - ${filters.dateRange.to?.toLocaleDateString()}\nGranularità: ${filters.timeFrame}`);
      filters.setLoading(false);
    }, 2000);
  };

  return (
    <div className="bg-[#121212] text-gray-200 h-screen flex overflow-hidden">
      {/* Sidebar */}
      <div className="glass w-[400px] h-full flex flex-col z-[1000] shadow-2xl overflow-y-auto p-6 space-y-6">

        {/* Header */}
        <div className="flex items-center gap-3">
          <div className="p-2 bg-blue-600 rounded-lg shadow-lg shadow-blue-900/20">
            <Grape className="text-white w-6 h-6" />
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-white uppercase italic">SmartHarvest</h1>
        </div>

        {/* Project Info */}
        <div className="space-y-4">
          <div className="space-y-2">
            <label className="text-[10px] font-bold text-gray-500 uppercase tracking-widest ml-1">
              Project Metadata
            </label>
            <div className="relative">
              <Tag className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
              <input
                type="text"
                value={projectName}
                onChange={(e) => setProjectName(e.target.value)}
                placeholder="Nome vigneto..."
                className="w-full bg-[#252525] border border-gray-700/50 rounded-xl py-3 pl-10 pr-4 text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none transition-all"
              />
            </div>
          </div>

          <div className="space-y-2">
            <label className="text-[10px] font-bold text-gray-500 uppercase tracking-widest ml-1">
              Location Library
            </label>
            <div className="relative">
              <MapPin className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
              <select className="w-full bg-[#252525] border border-gray-700/50 rounded-xl py-3 pl-10 pr-4 text-sm focus:border-blue-500 outline-none appearance-none transition-all cursor-pointer">
                <option>Seleziona Vigneto Salvato</option>
              </select>
              <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500 pointer-events-none" />
            </div>
          </div>
        </div>

        <div className="border-t border-gray-800" />

        {/* Temporal Configuration */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <label className="text-[10px] font-bold text-blue-400 uppercase tracking-widest px-2 py-1 bg-blue-500/10 rounded-md">
              Configurazione Temporale
            </label>
            <Calendar className="w-4 h-4 text-blue-500/50" />
          </div>

          {filters.isLoading ? (
            <FiltersSkeleton />
          ) : (
            <div className="space-y-4">
              <MasterTimeline
                currentYear={filters.currentYear}
                onYearChange={filters.handleYearChange}
              />

              <TimeFrameToggle
                timeFrame={filters.timeFrame}
                onTimeFrameChange={(value) => filters.setTimeFrame(value as any)}
              />

              <UnifiedDatePicker
                dateRange={filters.dateRange}
                currentYear={filters.currentYear}
                onDateRangeChange={handleDateRangeChange}
              />
            </div>
          )}

          {/* Summary Card */}
          {filters.dateRange.from && filters.dateRange.to && !filters.isLoading && (
            <div className="bg-gradient-to-br from-blue-600/10 to-emerald-600/10 border border-blue-500/20 rounded-2xl p-4">
              <div className="flex items-start gap-3">
                <div className="p-2 bg-blue-500/20 rounded-lg">
                  <Info className="w-4 h-4 text-blue-400" />
                </div>
                <div className="text-[11px] text-blue-100 leading-relaxed font-light">
                  <strong className="text-blue-300">Periodo Selezionato:</strong><br />
                  📅 Anno: {filters.currentYear}<br />
                  📊 Granularità: {filters.timeFrame}<br />
                  📆 Range: {filters.dateRange.from.toLocaleDateString('it-IT')} → {filters.dateRange.to.toLocaleDateString('it-IT')}
                </div>
              </div>
            </div>
          )}

          {/* Polygon Manager */}
          <PolygonManager
            polygons={filters.selectedPolygons}
            onRemove={filters.removePolygon}
            onClearAll={filters.clearPolygons}
          />
        </div>

        {/* Action Buttons */}
        <div className="pt-4 space-y-3 mt-auto">
          <Button
            variant="outline"
            className="w-full py-6 flex items-center justify-center gap-2 hover:-translate-y-1 transition-transform"
          >
            <Save className="w-4 h-4" /> Salva Area
          </Button>
          <Button
            onClick={handleStartAnalysis}
            disabled={filters.isLoading || !filters.dateRange.from || !filters.dateRange.to}
            className="w-full bg-gradient-to-r from-blue-600 to-blue-500 hover:from-blue-500 hover:to-blue-400 py-6 text-md font-bold shadow-lg shadow-blue-600/20 flex items-center justify-center gap-2 hover:-translate-y-1 transition-transform"
          >
            <Zap className="w-5 h-5" /> Inizia Analisi
          </Button>
        </div>

        {filters.isLoading && (
          <div className="space-y-2">
            <div className="w-full bg-gray-800 rounded-full h-1.5 overflow-hidden">
              <div className="bg-blue-500 h-full w-2/3 animate-pulse" />
            </div>
            <p className="text-[10px] text-center text-gray-500 uppercase tracking-tighter">
              Caricamento...
            </p>
          </div>
        )}
      </div>

      {/* Map Placeholder */}
      <div className="flex-1 relative bg-gray-900">
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="text-center space-y-4">
            <div className="p-4 bg-black/50 backdrop-blur-md rounded-2xl border border-white/10">
              <MapPin className="w-12 h-12 text-blue-500 mx-auto mb-2" />
              <p className="text-sm text-white/70 uppercase tracking-widest font-bold">
                Leaflet Map Integration
              </p>
              <p className="text-xs text-white/50 mt-1">
                Coming next: Interactive vineyard selection
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
