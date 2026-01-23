

import { useState } from 'react';
import type { DateRange } from "react-day-picker";
import { Trash2, Satellite, Layers } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DateRangePicker } from './DateRangePicker';
import { MapComponent } from './MapComponent';

// Mock Data
const INITIAL_POLYGONS = [
    { id: '1', name: 'Vigneto Nord', area: '12.5 ha', coords: [[45.5, 10.5], [45.52, 10.5], [45.52, 10.53], [45.5, 10.53]] },
    { id: '2', name: 'Uliveto Sud', area: '8.2 ha', coords: [[45.4, 10.4], [45.42, 10.4], [45.42, 10.43], [45.4, 10.43]] },
];

export default function TerritorialAnalysis() {
    const [dateRange, setDateRange] = useState<DateRange | undefined>({
        from: new Date(2023, 0, 1),
        to: new Date(2023, 11, 31),
    });

    const [polygons, setPolygons] = useState(INITIAL_POLYGONS);
    const [isLoading, setIsLoading] = useState(false);

    const handleDateApply = () => {
        setIsLoading(true);
        // Simulate API call / recalculation
        setTimeout(() => {
            setIsLoading(false);
        }, 1500);
    };

    const removePolygon = (id: string) => {
        setPolygons(prev => prev.filter(p => p.id !== id));
    };

    return (
        <div className="min-h-screen bg-background text-foreground flex flex-col">
            {/* Header */}
            <header className="border-b bg-card/50 backdrop-blur sticky top-0 z-50">
                <div className="container mx-auto px-4 h-16 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <div className="bg-primary/10 p-2 rounded-lg">
                            <Satellite className="w-6 h-6 text-primary" />
                        </div>
                        <h1 className="text-xl font-bold tracking-tight">Zero-Friction Analysis</h1>
                    </div>
                    <div className="flex items-center gap-4">
                        {/* Date Picker */}
                        <DateRangePicker
                            date={dateRange}
                            setDate={setDateRange}
                            onApply={handleDateApply}
                            loading={isLoading}
                        />
                    </div>
                </div>
            </header>

            <main className="flex-1 container mx-auto p-4 flex gap-4 h-[calc(100vh-4rem)]">
                {/* Sidebar - Polygon Management */}
                <Card className="w-80 h-full flex flex-col border-border/50 bg-card/30 backdrop-blur shadow-xl">
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2 text-lg">
                            <Layers className="w-5 h-5 text-muted-foreground" />
                            Aree Monitorate
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="flex-1 overflow-hidden p-0">
                        <div className="h-full overflow-y-auto p-4 space-y-2">
                            <AnimatePresence mode="popLayout">
                                {polygons.length === 0 ? (
                                    <motion.div
                                        initial={{ opacity: 0 }}
                                        animate={{ opacity: 1 }}
                                        className="text-center text-muted-foreground py-8"
                                    >
                                        Nessun poligono selezionato
                                    </motion.div>
                                ) : (
                                    polygons.map((poly) => (
                                        <motion.div
                                            key={poly.id}
                                            layout
                                            initial={{ opacity: 0, x: -20 }}
                                            animate={{ opacity: 1, x: 0 }}
                                            exit={{ opacity: 0, x: -20, transition: { duration: 0.2 } }}
                                            className="group flex items-center justify-between p-3 rounded-lg bg-card border hover:border-primary/50 transition-colors"
                                        >
                                            <div>
                                                <div className="font-medium">{poly.name}</div>
                                                <div className="text-xs text-muted-foreground">{poly.area}</div>
                                            </div>
                                            <Button
                                                variant="ghost"
                                                size="icon"
                                                onClick={() => removePolygon(poly.id)}
                                                className="opacity-0 group-hover:opacity-100 transition-opacity text-destructive hover:text-destructive hover:bg-destructive/10"
                                            >
                                                <Trash2 className="w-4 h-4" />
                                            </Button>
                                        </motion.div>
                                    ))
                                )}
                            </AnimatePresence>
                        </div>
                    </CardContent>
                </Card>

                {/* Main Map Area */}
                <div className="flex-1 h-full rounded-xl overflow-hidden relative border border-border/50 shadow-2xl">
                    <MapComponent
                        isLoading={isLoading}
                        polygons={polygons.map(p => ({
                            id: p.id,
                            coords: p.coords as any // Quick type fix, normally would type strictly
                        }))}
                    />
                </div>
            </main>
        </div>
    );
}
