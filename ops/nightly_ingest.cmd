@echo off
rem Nightly ingestion wrapper for Windows Task Scheduler (G0.3 soak).
rem FIXED filename: the previous %date%-substituted name produced invalid paths
rem with '/' under the dd/MM/yyyy locale, aborting the redirect before python ran
rem and silently killing 5 soak nights. Fixed, append-mode, locale-independent.
cd /d "C:\Users\Aksharajsinh\Claude\Projects\axrzce fund"
if not exist var\ingestion_logs mkdir var\ingestion_logs
".venv\Scripts\python.exe" ops\nightly_ingest.py >> var\ingestion_logs\console_soak.log 2>&1
