@echo off
rem Nightly ingestion wrapper for Windows Task Scheduler (G0.3 soak).
cd /d "C:\Users\Aksharajsinh\Claude\Projects\axrzce fund"
if not exist var\ingestion_logs mkdir var\ingestion_logs
".venv\Scripts\python.exe" ops\nightly_ingest.py >> var\ingestion_logs\console_%date:~-4%%date:~4,2%%date:~7,2%.log 2>&1
