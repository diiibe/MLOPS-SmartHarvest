
import { MapContainer, TileLayer, Polygon } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import type { LatLngExpression } from 'leaflet';

interface MapComponentProps {
    isLoading: boolean;
    polygons: Array<{ id: string; coords: LatLngExpression[] }>;
}

// Effect to handle loading overlay
const LoadingOverlay = ({ visible }: { visible: boolean }) => {
    if (!visible) return null;
    return (
        <div className="absolute inset-0 z-[1000] bg-background/50 backdrop-blur-sm animate-pulse flex items-center justify-center">
            <div className="space-y-4 text-center">
                <div className="w-12 h-12 border-4 border-primary border-t-transparent rounded-full animate-spin mx-auto"></div>
                <p className="text-sm font-medium text-primary">Analisi in corso...</p>
            </div>
        </div>
    );
};

export const MapComponent = ({ isLoading, polygons }: MapComponentProps) => {
    // Center map on Italy or specific roi
    const center: LatLngExpression = [41.9028, 12.4964];

    return (
        <div className="relative w-full h-full rounded-xl overflow-hidden border border-border shadow-2xl">
            <LoadingOverlay visible={isLoading} />

            <MapContainer
                center={center}
                zoom={6}
                style={{ height: '100%', width: '100%', background: '#0a0a0a' }}
                zoomControl={false}
            >
                {/* High Impact Explorer / Satellite Style */}
                <TileLayer
                    url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
                    attribution='&copy; <a href="https://www.esri.com/">Esri</a>'
                />

                {/* Dark overlay to make neon pop if needed, or just let satellite shine. 
            User asked for "Mappa Satellitare ad alta risoluzione". */}

                {polygons.map((poly) => (
                    <Polygon
                        key={poly.id}
                        positions={poly.coords}
                        pathOptions={{
                            color: '#00ffcc',
                            weight: 2,
                            fillColor: '#00ffcc',
                            fillOpacity: 0.1,
                            className: 'neon-polygon'
                        }}
                    />
                ))}
            </MapContainer>

            {/* CSS injection for neon glow */}
            <style>{`
        .neon-polygon {
            filter: drop-shadow(0 0 8px #00ffcc);
            transition: all 0.3s ease;
        }
        .neon-polygon:hover {
            stroke-width: 4px;
            filter: drop-shadow(0 0 12px #00ffcc);
            fill-opacity: 0.2;
        }
      `}</style>
        </div>
    );
};
