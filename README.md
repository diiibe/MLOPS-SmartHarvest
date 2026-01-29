# SmartHarvest Frontend (Export & Analytics)

## 🍷 Overview
SmartHarvest is a premium dashboard for Viticulture Analytics, featuring advanced temporal filtering, interactive maps, and MLOps integrations. This repository contains the Frontend application optimized for performance and "Enterprise-Grade" quality.

## ✨ Key Features
-   **Advanced Temporal Config**: Vintage (Vendemmia) selection & Phenological Stage quick-sets.
-   **Interactive Map**: Satellite view integration for vineyard monitoring.
-   **Data Export**: High-performance CSV export via Web Workers (non-blocking).
-   **MLOps Traceability**: Exports include model metadata (Version, Hash, Timestamp).
-   **Performance**: React 19, Vite, and optimized chunks.

## 🚀 Getting Started

### Prerequisites
-   Node.js 18+
-   npm 9+

### Installation
```bash
npm install
```

### Development
Start the dev server:
```bash
npm run dev
```
Visit `http://localhost:5173`.

### Build
Create a production build:
```bash
npm run build
```

## 🛠️ Tech Stack
-   **Framework**: React 19 + TypeScript + Vite
-   **Styling**: TailwindCSS 4 + Lucide Icons
-   **Maps**: React Leaflet
-   **Utils**: date-fns, clsx, tailwind-merge

## 🔒 Security
-   **CSV Sanitization**: Prevents CSV Injection attacks.
-   **Strict Typing**: Full TypeScript coverage.
