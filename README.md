# Hackaton_Topography

1) Local Data is taken from dati_siti_topografia folder (5m elevation tiff)
2) analyze_all.py first runs subroutine -> script.py takes only elevation DEM
3) script.py calcola 
4) CHE TERRENO VEDO + ANALISI TERRENO
	 * horizon() calcola orizzonte a 360°
	 * terrain_derivatives -> gradiente per slope 
	 * angolo inclinazione in gradi da atan(gradiente)
	 * direzione gradiente da atan2(compY,compX) 
5) Celle divise in quadrati 100x100m (dem locali perdono res, dem globali no o poco, semplice griglia a ampiezza costante)
6)  calcolo slope coverage ; elevation ; relief m ; slope mean ; slope max ; slope filter % landable ; lon, lat
7) salvataggio in site_cells.csv
	 
	 
	 COMMAND TO RUN 
	 Get-ChildItem dati_siti_topografia -Directory | ForEach-Object { $dem = Get-ChildItem $_.FullName -Filter *_surf.tif | Select-Object -First 1; Write-Host "== $($_.Name)"; .\.venv\Scripts\python.exe scripts\script.py --mode metrics --no-rasters --no-plot --input $dem.FullName --output "risultati_v2\$($_.Name)" }