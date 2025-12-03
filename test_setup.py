#!/usr/bin/env python3
"""
Test script to verify camera server setup and configuration.
Run this before starting the camera server to ensure everything is configured correctly.
"""

import json
import os
import sys
import importlib
import onvif
def check_dependencies():
    """Check if all required Python packages are installed"""

    required_modules = {
        "requests": "requests",
        "opencv-python": "cv2",
        "gstreamer-python": "gi",
        "onvif-zeep": "onvif",     # <-- FIXED HERE
        "asyncio": "asyncio",
        "aiohttp": "aiohttp",
        "pydantic": "pydantic",
        "loguru": "loguru",
    }

    missing = []

    print(" Checking dependencies...")

    for pip_name, module_name in required_modules.items():
        try:
            importlib.import_module(module_name)
            print(module_name)
        except ImportError:
            print(f"Missing: {pip_name}")
            missing.append(pip_name)

    if missing:
        print("\n Missing packages:", ", ".join(missing))
        print("Run: pip install -r requirements.txt\n")
        return False

    return True


def check_config():
    """Check if config.json is valid and complete"""
    config_path = 'config.json'

    if not os.path.exists(config_path):
        print(f" Config file not found: {config_path}")
        return False

    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        #print(f" Invalid JSON in config file: {e}")
        return False

    # Check required sections
    required_sections = ['shinobi', 'cameras', 'recording', 'server']
    for section in required_sections:
        if section not in config:
           # print(f" Missing section in config: {section}")
            return False

    # Check Shinobi config
    shinobi = config['shinobi']
    required_shinobi_keys = ['base_url', 'api_key', 'group_key']
    for key in required_shinobi_keys:
        if key not in shinobi or not shinobi[key]:
            print(f" Missing or empty Shinobi config: {key}")
            return False

    # Check cameras
    cameras = config['cameras']
    if not isinstance(cameras, list) or len(cameras) == 0:
        print(" No cameras configured")
        return False

    for i, camera in enumerate(cameras):
        required_camera_keys = ['id', 'name', 'rtsp_url', 'onvif_url', 'username', 'password']
        for key in required_camera_keys:
            if key not in camera or not camera[key]:
                print(f" Camera {i+1}: Missing or empty field: {key}")
                return False

    # Check recording config
    recording = config['recording']
    required_recording_keys = ['base_dir', 'segment_duration', 'pre_event_buffer', 'post_event_duration']
    for key in required_recording_keys:
        if key not in recording:
            print(f" Missing recording config: {key}")
            return False

   # print(" Configuration is valid!")
    return True

def check_directories():
    """Check if required directories exist and are writable"""
    config_path = 'config.json'

    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
    except:
        return False

    recording_dir = config['recording']['base_dir']

    try:
        os.makedirs(recording_dir, exist_ok=True)
        # Test write permission
        test_file = os.path.join(recording_dir, 'test_write.tmp')
        with open(test_file, 'w') as f:
            f.write('test')
        os.remove(test_file)

        print(f" Recording directory is writable: {recording_dir}")
        return True
    except Exception as e:
        print(f" Cannot create/write to recording directory: {e}")
        return False

def main():
    """Run all setup checks"""
   # print(" Checking Camera Server Setup...\n")

    all_good = True

    print(" Checking dependencies...")
    if not check_dependencies():
        all_good = False

    print("\n  Checking configuration...")
    if not check_config():
        all_good = False

    print("\n Checking directories...")
    if not check_directories():
        all_good = False

    print("\n" + "="*50)

    if all_good:
        print("Setup check passed! You can now run the camera server:")
        print("   python camera_server.py")
    else:
        print(" Setup check failed. Please fix the issues above.")
        sys.exit(1)

if __name__ == "__main__":
    main()
