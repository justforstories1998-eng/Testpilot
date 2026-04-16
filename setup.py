"""TestPilot Setup Script - Playwright Version"""

import os
import subprocess
import sys


def print_step(step):
    print(f"\n{'='*50}")
    print(f"  {step}")
    print(f"{'='*50}\n")


def check_node():
    try:
        subprocess.run(["node", "-v"], capture_output=True, check=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def main():
    print_step("Checking Prerequisites")

    if not check_node():
        print("ERROR: Node.js is not installed. Install from https://nodejs.org/")
        sys.exit(1)
    print(f"✓ Node.js found")
    print(f"✓ Python {sys.version.split()[0]} found")

    print_step("Setting up Backend")
    backend_dir = os.path.join(os.getcwd(), "backend")

    print("Installing Python dependencies...")
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
        cwd=backend_dir
    )

    print("Installing Playwright browsers (Chromium)...")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            cwd=backend_dir
        )
        print("✓ Playwright Chromium installed")
    except Exception as e:
        print(f"⚠ Playwright install failed: {e}")
        print("  Run manually: playwright install chromium")

    env_path = os.path.join(backend_dir, ".env")
    if not os.path.exists(env_path):
        print("Creating .env file from template...")
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(
                "# Database\n"
                "MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/?retryWrites=true&w=majority\n"
                "MONGODB_DB_NAME=testpilot\n\n"
                "# AI Configuration (Required)\n"
                "GROQ_API_KEY=\n"
                "GROQ_MODEL=llama-3.3-70b-versatile\n\n"
                "# Security\n"
                "SECRET_KEY=dev_secret_change_in_production\n"
            )
        print("✓ .env created. PLEASE EDIT with your MongoDB and Groq keys!")
    else:
        print("✓ .env file already exists")

    print_step("Setting up Frontend")
    frontend_dir = os.path.join(os.getcwd(), "frontend")
    if os.path.exists(frontend_dir):
        print("Installing Node modules...")
        subprocess.check_call(["npm", "install"], cwd=frontend_dir, shell=True)
    else:
        print("ERROR: /frontend directory not found")
        sys.exit(1)

    print_step("Setup Complete! 🚀")
    print("To start the app:")
    print("  python start.py")
    print("\nIMPORTANT: Edit backend/.env with your GROQ_API_KEY and MONGODB_URI")


if __name__ == "__main__":
    main()