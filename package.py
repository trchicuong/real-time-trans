"""
Script to package the Real-Time Screen Translator into a zip file
Creates: RealTimeTrans-[version]-[timestampcode].zip
"""
import os
import sys
import zipfile
import datetime
import subprocess
import shutil

# Version number - updated with latest improvements
VERSION = "v1.2.0"  # MarianMT local translation added

def get_timestamp_code():
    """Get timestamp code in HHMMSS format"""
    now = datetime.datetime.now()
    return now.strftime("%H%M%S")

def build_executable():
    """Build the executable using PyInstaller"""
    print("Building executable...")
    try:
        # Check if build.spec exists (preferred)
        if os.path.exists("build.spec"):
            print("Using build.spec...")
            result = subprocess.run([
                "pyinstaller",
                "build.spec"
            ], capture_output=True, text=True)
            if result.returncode != 0:
                print(f"Build error: {result.stderr}")
                print(f"Build output: {result.stdout}")
                return False
        # Check if build.bat exists
        elif os.path.exists("build.bat"):
            print("Using build.bat...")
            result = subprocess.run(["build.bat"], shell=True, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"Build error: {result.stderr}")
                print(f"Build output: {result.stdout}")
                return False
        else:
            # Try using PyInstaller directly
            print("Using PyInstaller directly...")
            result = subprocess.run([
                "pyinstaller",
                "--onedir",
                "--windowed",
                "--name", "RealTimeScreenTranslator",
                "translator.py"
            ], capture_output=True, text=True)
            if result.returncode != 0:
                print(f"Build error: {result.stderr}")
                return False
        
        # Check if executable folder exists (onedir mode creates a folder)
        exe_folder = os.path.join("dist", "RealTimeScreenTranslator")
        exe_path = os.path.join(exe_folder, "RealTimeScreenTranslator.exe")
        if not os.path.exists(exe_path):
            print(f"Executable not found at {exe_path}")
            return False
        
        print("Build successful!")
        return True
    except Exception as e:
        print(f"Error building executable: {e}")
        return False

def create_package():
    """Create the zip package"""
    timestamp = get_timestamp_code()
    zip_name = f"RealTimeTrans-{VERSION}-{timestamp}.zip"
    
    print(f"\nCreating package: {zip_name}")
    
    # Check if executable folder exists (onedir mode)
    exe_folder = os.path.join("dist", "RealTimeScreenTranslator")
    exe_path = os.path.join(exe_folder, "RealTimeScreenTranslator.exe")
    
    if not os.path.exists(exe_path):
        print(f"Warning: Executable not found at {exe_path}")
        print("Please build the executable first using build.bat or pyinstaller")
        return False
    
    if not os.path.isdir(exe_folder):
        print(f"Warning: Executable folder not found at {exe_folder}")
        return False
    
    # Create zip file
    try:
        with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Add all files from the executable folder
            print(f"  Adding folder: RealTimeScreenTranslator/")
            for root, dirs, files in os.walk(exe_folder):
                for file in files:
                    file_path = os.path.join(root, file)
                    # Calculate relative path from exe_folder itself
                    arcname = os.path.relpath(file_path, exe_folder)
                    arcname = os.path.join("RealTimeScreenTranslator", arcname)
                    print(f"    Adding: {arcname}")
                    zipf.write(file_path, arcname)
            
            # Add HUONG_DAN.txt to root of zip
            if os.path.exists("HUONG_DAN.txt"):
                print(f"  Adding: HUONG_DAN.txt")
                zipf.write("HUONG_DAN.txt", "HUONG_DAN.txt")
            else:
                print("Warning: HUONG_DAN.txt not found")

            # Add LICENSE to root of zip
            if os.path.exists("LICENSE"):
                print(f"  Adding: LICENSE")
                zipf.write("LICENSE", "LICENSE")
            else:
                print("Warning: LICENSE not found")
        
        print(f"\n✓ Package created successfully: {zip_name}")
        print(f"  Size: {os.path.getsize(zip_name) / (1024*1024):.2f} MB")
        return True
    except Exception as e:
        print(f"Error creating package: {e}")
        return False

def main():
    """Main function"""
    print("=" * 60)
    print("Real-Time Screen Translator - Package Builder")
    print("=" * 60)
    
    # Check if we need to build
    exe_folder = os.path.join("dist", "RealTimeScreenTranslator")
    exe_path = os.path.join(exe_folder, "RealTimeScreenTranslator.exe")
    if not os.path.exists(exe_path):
        print("\nExecutable not found. Building...")
        if not build_executable():
            print("\nBuild failed. Please build manually and try again.")
            return 1
    else:
        print("\nExecutable found. Skipping build.")
        response = input("Rebuild executable? (y/n): ").strip().lower()
        if response == 'y':
            if not build_executable():
                print("\nBuild failed. Using existing executable.")
    
    # Create package
    if create_package():
        print("\n" + "=" * 60)
        print("Package creation completed!")
        print("=" * 60)
        return 0
    else:
        print("\n" + "=" * 60)
        print("Package creation failed!")
        print("=" * 60)
        return 1

if __name__ == "__main__":
    sys.exit(main())
