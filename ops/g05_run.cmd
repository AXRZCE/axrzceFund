@echo off
rem One-shot G0.5 broker round-trip (market hours). FIXED safe log filename
rem (see nightly_ingest.cmd — locale %date% bug killed the 06-11 scheduled run).
cd /d "C:\Users\Aksharajsinh\Claude\Projects\axrzce fund"
if not exist var\g05 mkdir var\g05
".venv\Scripts\python.exe" ops\broker_roundtrip.py >> var\g05\console_soak.log 2>&1
