
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import TerritorialAnalysis from './features/territory/TerritorialAnalysis'

// Simple ThemeProvider
function ThemeProviderWrapper({ children }: { children: React.ReactNode }) {
  return (
    <div className="dark">
      {children}
    </div>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProviderWrapper>
      <TerritorialAnalysis />
    </ThemeProviderWrapper>
  </StrictMode>,
)
