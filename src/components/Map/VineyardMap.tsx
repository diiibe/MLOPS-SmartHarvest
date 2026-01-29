
import { useEffect } from 'react';
import { MapContainer, TileLayer, Polygon, useMap } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';

// Fix for default marker icons in Leaflet with Webpack/Vite
import L from 'leaflet';
import icon from 'leaflet/dist/images/marker-icon.png';
import iconShadow from 'leaflet/dist/images/marker-shadow.png';

const DefaultIcon = L.icon({
    iconUrl: icon,
    shadowUrl: iconShadow,
    iconAnchor: [12, 41]
});
L.Marker.prototype.options.icon = DefaultIcon;

const TUSCANY_COORDS: [number, number] = [43.4167, 11.1667]; // Chianti Region
const MOCK_VINEYARD_POLYGON: [number, number][] = [
    [43.4167, 11.1667],
    [43.4187, 11.1687],
    [43.4157, 11.1707],
    [43.4137, 11.1657],
];

export const VineyardMap = ({ selectedPolygons: _selectedPolygons }: { selectedPolygons: unknown[] }) => {
    return (
        <div className="h-full w-full rounded-2xl overflow-hidden border border-gray-800 shadow-2xl relative">
            <MapContainer
                center={TUSCANY_COORDS}
                zoom={14}
                style={{ height: '100%', width: '100%' }}
                className="z-0"
            >
                {/* Satellite-style tiles (Esri World Imagery) */}
                <TileLayer
                    attribution='&copy; <a href="https://www.esri.com/">Esri</a>'
                    url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
                />

                {/* Optional overlay for labels */}
                {/* <TileLayer
                    url="https://stamen-tiles-{s}.a.ssl.fastly.net/toner-labels/{z}/{x}/{y}{r}.png"
                /> */}

                {/* Draw Mock Polygon */}
                <Polygon
                    positions={MOCK_VINEYARD_POLYGON}
                    pathOptions={{ color: '#3b82f6', fillColor: '#3b82f6', fillOpacity: 0.2, weight: 2 }}
                />

                {/* Helper to resize map on container change */}
                <MapResizeHelper />
            </MapContainer>

            {/* Overlay Controls */}
            <div className="absolute top-4 right-4 z-[400] bg-black/50 backdrop-blur-md p-2 rounded-lg border border-white/10 text-xs text-white">
                <span className="font-bold text-blue-400">SAT</span> / MAP
            </div>
        </div>
    );
};

// Component to handle map invalidation/resize
const MapResizeHelper = () => {
    const map = useMap();
    useEffect(() => {
        const timeout = setTimeout(() => {
            map.invalidateSize();
        }, 100);
        return () => clearTimeout(timeout);
    }, [map]);
    return null;
};
