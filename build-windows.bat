@echo off
REM Build HomeSight for Windows (run this on Windows with Go installed)

echo Building HomeSight for Windows...

go build -o bin\homesightd.exe .\cmd\homesightd
go build -o bin\homesight-dashboard.exe .\cmd\dashboard

echo.
echo Done! Executables in bin\
echo.
echo To run:
echo   set HOMESIGHT_CONFIG=config.yaml
echo   set HOMESIGHT_DB=data\homesight.db
echo   bin\homesightd.exe
