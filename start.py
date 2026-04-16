"""
TestPilot Launcher
==================
Starts both Backend (Uvicorn) and Frontend (Vite) concurrently.
"""

import subprocess
import time
import os
import sys
import threading
import signal

# Global process handles
backend_process = None
frontend_process = None

def stream_output(process, prefix):
    """Reads output from a subprocess and prints it with a prefix."""
    for line in iter(process.stdout.readline, ""):
        print(f"[{prefix}] {line.strip()}")

def start_backend():
    global backend_process
    print("??? Starting Backend (Port 8000)...")
    backend_dir = os.path.join(os.getcwd(), "backend")
    
    # Run uvicorn directly
    cmd = [sys.executable, "-m", "uvicorn", "app.main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"]
    
    backend_process = subprocess.Popen(
        cmd,
        cwd=backend_dir,
        stdout=sys.stdout,
        stderr=sys.stderr,
        env=os.environ.copy()
    )

def start_frontend():
    global frontend_process
    print("??? Starting Frontend (Port 5173)...")
    frontend_dir = os.path.join(os.getcwd(), "frontend")
    
    # Use npm run dev
    cmd = ["npm", "run", "dev"]
    
    frontend_process = subprocess.Popen(
        cmd,
        cwd=frontend_dir,
        stdout=sys.stdout,
        stderr=sys.stderr,
        shell=True # Required for npm on Windows
    )

def stop_services(signum=None, frame=None):
    print("\n??? Stopping services...")
    
    if backend_process:
        if sys.platform == "win32":
            subprocess.call(["taskkill", "/F", "/T", "/PID", str(backend_process.pid)])
        else:
            backend_process.terminate()
            
    if frontend_process:
        if sys.platform == "win32":
            subprocess.call(["taskkill", "/F", "/T", "/PID", str(frontend_process.pid)])
        else:
            frontend_process.terminate()
            
    sys.exit(0)

if __name__ == "__main__":
    # Handle Ctrl+C
    signal.signal(signal.SIGINT, stop_services)
    signal.signal(signal.SIGTERM, stop_services)

    print("==================================================")
    print("  TestPilot v2.0 - AI Automation Platform")
    print("==================================================\n")

    try:
        t1 = threading.Thread(target=start_backend)
        t2 = threading.Thread(target=start_frontend)
        
        t1.start()
        time.sleep(2) # Give backend a head start
        t2.start()

        print("\n??? App running at: http://localhost:5173")
        print("??? API running at: http://localhost:8000/docs")
        print("??? Press Ctrl+C to stop\n")
        
        # Keep main thread alive
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        stop_services()