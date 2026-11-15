# Hackaton_Topography
Topography repo

## Dati TIFF e Git LFS

Tutti i file `.tif` e `.tiff`, incluse le estensioni maiuscole o miste,
sono gestiti tramite Git LFS grazie a `.gitattributes`.
Installare Git LFS prima di clonare o aggiungere i raster.

Per scaricare i dati dopo un clone:

```powershell
git lfs install --local
git lfs pull
```

Per preparare e pubblicare i dati dalla radice del repository:

```powershell
git lfs install --local
git add .gitattributes
git add --renormalize -- ':(glob)**/*.[tT][iI][fF]' ':(glob)**/*.[tT][iI][fF][fF]'
git add -- ':(glob)**/*.[tT][iI][fF]' ':(glob)**/*.[tT][iI][fF][fF]'
git lfs status
git diff --cached --stat
git commit -m "Gestisci i dati TIFF con Git LFS"
git push origin main
```

La rinormalizzazione converte nell'indice anche i TIFF gia versionati;
i file locali restano raster completi e la cronologia pubblicata resta invariata.
Il push carica automaticamente gli oggetti LFS tramite il relativo hook.

I 112 TIFF attualmente presenti occupano circa 11,1 GB. Il file
`dati_regionali/87S/ldem_87s_5mpp.tif` pesa circa 3,47 GB:
supera il limite per file dei piani GitHub Free e Pro (2 GB).
Per caricarlo intero serve un piano con limite sufficiente, come Team (4 GB)
o Enterprise Cloud (5 GB), e spazio LFS disponibile sul proprietario del repository.
Riferimento: [limiti Git LFS di GitHub](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-git-large-file-storage).

## Analisi topografica

I risultati per ogni sito sono in [risultati topografia](<risultati topografia/README.md>).
La cartella contiene un riepilogo comparativo e una sottocartella per ciascun sito.

Per eseguire nuovamente tutte le analisi dalla radice di questo repository:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m unittest discover -s scripts -p "test_*.py"
.venv/Scripts/python.exe scripts/analyze_all.py
```

Parametri: centro del DEM, osservatore a 2 m, orizzonte a 360 azimut geografici
con passo vicino 5 m fino a 10 km, soglia di pendenza 10 gradi e celle da
100 x 100 m (piu piccole ai bordi quando necessario).
Gli output esistenti con lo stesso nome vengono sovrascritti; i dati originali
non vengono modificati. Gli output sono compatti: JSON, CSV e PNG, senza GeoTIFF derivati.

Il profilo orizzonte riguarda il centro del DEM, mentre le statistiche di
pendenza descrivono tutta la mappa. Il batch include ora il DEM lontano; il dettaglio resta limitato dalla risoluzione e l'orizzonte puo
non risolvere ogni rilievo. Non e una valutazione completa dell'illuminazione.


## Usare un LDSM per trovare il DEM

Il parametro `--far-dem` accetta anche la mappa di pendenza LDSM:

```powershell
.venv/Scripts/python.exe scripts/script.py --far-dem "dati_regionali/LDSM_60S_240MPP_ADJ.tiff" --no-rasters
```

Lo script usa il nome del prodotto per cercare il corrispondente
`LDEM_60S_240MPP_ADJ`, anche nelle sottocartelle della mappa. Sono accettate
le estensioni `.tif` e `.tiff`, senza distinzione tra maiuscole e minuscole.
Controlla che i due prodotti abbiano la stessa griglia e proiezione.
Nel caso attuale il file trovato e `dati_regionali/60S/LDEM_60S_240MPP_ADJ.TIF`.
Il collegamento richiesto/usato viene stampato e salvato nei metadati JSON.
La stessa ricerca funziona per `--input`, `--fallback-dem` e le chiamate Python.

Questa operazione trova un DEM esistente: non ricostruisce le quote dalla
pendenza. Se il LDEM manca, e ambiguo o ha una griglia incompatibile, il
programma si interrompe con un messaggio esplicativo. Nessun nuovo sito viene creato.


## Coordinate obbligatorie dei siti

Il centro del DEM non viene piu usato automaticamente come punto osservatore.
Compilare `config/site_coordinates.json` con `site_id`, `lat`, `lon` e `source`
per ogni sito. Il catalogo dichiara frame MOON_ME_DE421, angoli in gradi e
longitudine positiva verso est; sono accettate longitudini 0..360 oppure -180..180.
Le coordinate non disponibili restano `null`: non vengono dedotte dal centro.

Controllo senza ricalcolare o sovrascrivere gli output:

```powershell
.venv/Scripts/python.exe scripts/analyze_all.py --preflight-only
```

Aprire `controllo_coordinate/README.md` per confrontare le coordinate dei siti
con i centri dei DEM. Il JSON del controllo riporta anche X/Y lunari, riga,
colonna, quota interpolata e fonte delle coordinate quando sono disponibili.
Una coordinata esterna al DEM, priva di quota o senza fonte impedisce il batch.

Per una singola analisi, passare `--lat` e `--lon` esplicitamente. Per l'intero
batch usare `--sites-file config/site_coordinates.json`. Quando il catalogo e
completo, il batch trasmette questi punti a script.py; `--resume` non riusa
risultati costruiti dal centro DEM o da un catalogo differente.

`summary.center` rimane il centro della mappa, `summary.site` descrive invece
il punto del sito: pixel, quota, pendenza del pixel e cella che lo contiene.
Le statistiche globali restano riferite all'intero DEM.
