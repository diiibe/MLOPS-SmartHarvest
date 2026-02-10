# Google Earth Engine Cloud Project Setup

## Problema
GEE richiede un Google Cloud Project per funzionare. L'autenticazione è completata ma manca il progetto.

## Soluzione: Registra un Cloud Project per GEE

### Opzione 1: Usa un progetto Cloud esistente
Se hai già un progetto Google Cloud:
1. Vai su https://console.cloud.google.com/
2. Seleziona o crea un progetto
3. Abilita Earth Engine API per quel progetto
4. Esegui: `earthengine set_project YOUR_PROJECT_ID`

### Opzione 2: Registra un nuovo progetto GEE (Consigliato)
1. Vai su: https://code.earthengine.google.com/
2. Accedi con il tuo account Google
3. Segui le istruzioni per registrare un nuovo progetto
4. Una volta registrato, ottieni il PROJECT_ID
5. Esegui: `earthengine set_project YOUR_PROJECT_ID`

## Comandi da eseguire dopo la registrazione

```bash
# Sostituisci YOUR_PROJECT_ID con il tuo project ID
earthengine set_project YOUR_PROJECT_ID

# Verifica che sia impostato
earthengine --project YOUR_PROJECT_ID ls projects/YOUR_PROJECT_ID/assets
```

## Test finale

Dopo aver impostato il progetto, testa con:
```bash
export PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH"
docker-compose exec api-server python src/test_gee.py
```
