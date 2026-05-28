@echo off
echo Igniting Career Brain...

:: Location of your vector database folder
cd /d "C:\vector_database" 

:: Launch Streamlit quietly in the background without opening Firefox
start /b "" "C:\Users\schli\AppData\Local\Python\pythoncore-3.14-64\python.exe" -m streamlit run 11.0_career_brain_ui.py --server.headless true

:: Give the local server 3 seconds to spin up
timeout /t 3 /nobreak > NUL

:: Force Windows to open Google Chrome directly to the app
start chrome "http://localhost:8501"
