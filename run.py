"""
Run script for the music visualizer.
"""
import subprocess
import sys
import os

def main():
    # Change to app directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    # Install dependencies
    print("Checking dependencies...")
    try:
        # Try using uv first (faster and works without pip installed in venv)
        subprocess.check_call(["uv", "pip", "install", "-r", "requirements.txt", "-q"])
    except (subprocess.CalledProcessError, FileNotFoundError):
        try:
            # Fallback to standard pip
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "-q"])
        except subprocess.CalledProcessError:
            print("Warning: Failed to install dependencies. Application might not run correctly.")


    # Run the application
    print("Starting application...")
    from app.main import main
    main()

if __name__ == "__main__":
    main()
