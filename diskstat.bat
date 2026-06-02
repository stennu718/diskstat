@echo off
echo =============================================
echo  DiskStat — kettakasutus analuus
echo =============================================
echo.
echo [1/3] Docker image ehitamine...
docker build -t diskstat:latest .

echo.
echo [2/3] Skaneerimine - C: ketas...
docker run --rm -v C:\Users\LocalAdmin\Downloads\diskstat-output:/out diskstat:latest /mnt/c/ -o /out

echo.
echo [3/3] Raporti avamine...
for %%F in (C:\Users\LocalAdmin\Downloads\diskstat-output\*\report.html) do (
    start "" "%%F"
    goto :done
)
echo Raporti ei leitud. Kontrolli /out kausta.
:done
echo.
echo Valmis!
pause
