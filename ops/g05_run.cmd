@echo off
rem One-shot G0.5 broker round-trip (market hours). Artifact: var\g05\<run_id>.json
cd /d "C:\Users\Aksharajsinh\Claude\Projects\axrzce fund"
if not exist var\g05 mkdir var\g05
".venv\Scripts\python.exe" ops\broker_roundtrip.py >> var\g05\console_%date:~-4%%date:~4,2%%date:~7,2%.log 2>&1
