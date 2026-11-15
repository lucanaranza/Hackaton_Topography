**Coordinate sito da verificare:** i risultati sotto si riferiscono ai centri dei DEM. Leggere [AVVERTENZA_COORDINATE.md](AVVERTENZA_COORDINATE.md) prima di usarli come punti di atterraggio.

# Risultati topografia

CSV corrente: [riepilogo.csv](riepilogo.csv)
Se sono presenti due CSV, usare questo collegamento: l'altro puo essere una versione precedente rimasta aperta.

Siti analizzati e verificati: 27. Errori: 0.

Parametri comuni: centro del DEM, osservatore 2 m, 360 azimut geografici, passo 5 m fino a 10 km e 100 m fino a 200 km,
celle 100 x 100 m e soglia di pendenza 10 gradi.

| Sito | Pendenza media (gradi) | Area <=10 gradi (%) | Incertezza media (m) | Esito |
| --- | --- | --- | --- | --- |
| [Sito_01](Sito_01/README.md) | 12.60 | 36.42 | 0.405 | PASS |
| [Sito_04](Sito_04/README.md) | 20.67 | 18.80 | 0.412 | PASS |
| [Sito_06](Sito_06/README.md) | 17.20 | 20.13 | 0.702 | PASS |
| [sito_07](sito_07/README.md) | 10.74 | 45.20 | 0.425 | PASS |
| [Sito_11](Sito_11/README.md) | 14.40 | 22.70 | 0.398 | PASS |
| [Sito_20](Sito_20/README.md) | 12.82 | 40.75 | 0.632 | PASS_WITH_NOTES |
| [Sito_20v2](Sito_20v2/README.md) | 13.11 | 35.42 | 0.642 | PASS |
| [Sito_23](Sito_23/README.md) | 17.40 | 16.79 | 0.501 | PASS_WITH_NOTES |
| [Sito_42](Sito_42/README.md) | 14.64 | 20.98 | 0.636 | PASS |
| [Sito_DM1](Sito_DM1/README.md) | 13.01 | 32.99 | 0.901 | PASS |
| [Sito_DM2](Sito_DM2/README.md) | 11.98 | 43.82 | 0.644 | PASS |
| [Sito_Haworth](Sito_Haworth/README.md) | 10.84 | 47.71 | 0.403 | PASS_WITH_NOTES |
| [Sito_LM1](Sito_LM1/README.md) | 12.87 | 46.84 | 0.378 | PASS |
| [Sito_LM2](Sito_LM2/README.md) | 12.60 | 40.71 | 0.377 | PASS |
| [Sito_LM3](Sito_LM3/README.md) | 11.53 | 44.93 | 0.412 | PASS |
| [Sito_LM4](Sito_LM4/README.md) | 11.20 | 46.83 | 0.371 | PASS |
| [Sito_LM5](Sito_LM5/README.md) | 10.87 | 52.39 | 0.395 | PASS |
| [Sito_LM6](Sito_LM6/README.md) | 12.24 | 34.85 | 0.423 | PASS |
| [Sito_LM7](Sito_LM7/README.md) | 10.70 | 50.27 | 0.492 | PASS |
| [Sito_LM8](Sito_LM8/README.md) | 10.94 | 50.07 | 0.389 | PASS |
| [Sito_NPA](Sito_NPA/README.md) | 6.47 | 80.05 | 0.524 | PASS |
| [Sito_NPB](Sito_NPB/README.md) | 5.25 | 84.70 | 1.088 | PASS |
| [Sito_NPC](Sito_NPC/README.md) | 5.50 | 86.27 | 0.569 | PASS |
| [Sito_NPD](Sito_NPD/README.md) | 6.18 | 81.55 | 0.502 | PASS |
| [Sito_Shoemaker](Sito_Shoemaker/README.md) | 8.97 | 65.73 | 0.366 | PASS |
| [Sito_SL2](Sito_SL2/README.md) | 12.72 | 33.81 | 0.389 | PASS |
| [Sito_SL3](Sito_SL3/README.md) | 14.70 | 22.94 | 0.454 | PASS |

## File e limiti

`riepilogo.json` e il CSV corrente consentono il confronto; `confronto.png` mostra pendenza e frazione <=10 gradi. `confronto_orizzonti.png` mostra il contributo del terreno lontano.
Se riepilogo.csv e aperto da un programma, il CSV corrente viene salvato come riepilogo_aggiornato.csv.
Ogni sito ha JSON dell'orizzonte, statistiche, celle CSV, mappa PNG e rapporto di verifica.
Le percentuali sono riferite ai pixel con pendenza calcolabile; le aree sono proiettate.
I raster hanno estensioni diverse: le sole aree assolute non sono un confronto omogeneo.
I profili orizzonte riguardano i centri dei DEM; le statistiche riguardano l'intera superficie.
**DEM lontano incluso:** il file LDSM 60S identifica il corrispondente LDEM 60S a 240 m/pixel. Le quote vengono dal LDEM.
La copertura dei campioni fino a 200 km e riportata per sito; non elimina i limiti della risoluzione o del campionamento. Il passo di 100 m non migliora la risoluzione regionale di 240 m.
La precisione non coincide con la risoluzione di 5 m; LDEC zero indica assenza di misure dirette, non necessariamente quota mancante.
Non sono stati calcolati luce, comunicazioni, temperatura, ghiaccio o uno score complessivo di atterraggio.
I GeoTIFF derivati sono omessi: il disco si e riempito durante la prima elaborazione. I dati originali sono preservati.
Site23 presenta un CRS nominalmente diverso nel file di errore, ma con parametri numerici e griglia identici.
Haworth presenta valori LDEC frazionari: nota nel rapporto; non sono interpretati come conteggi grezzi interi.

## Ripetere

Dalla radice del repository:

```powershell
.venv/Scripts/python.exe scripts/analyze_all.py
```

Gli output con gli stessi nomi vengono sovrascritti; i dati originali non sono modificati.
Gli script e i test sono in `scripts/`. I controlli verificano anche la corrispondenza LDSM/LDEM e il campionamento regionale.

