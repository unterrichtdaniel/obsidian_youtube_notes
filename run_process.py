#!/usr/bin/env python3
import os
import sys
import subprocess

# Set environment variables explicitly
os.environ["YOUTUBE_API_KEY"] = "AIzaSyCM6nxM5hsfV2PLKaJYc0MkkQP1XVrRhXU"
os.environ["OBSIDIAN_VAULT_PATH"] = "./vault"
os.environ["API_ENDPOINT"] = "http://127.0.0.1:11434/v1"
os.environ["MODEL"] = "gemma3:1b"
os.environ["MAX_RETRIES"] = "5"
os.environ["INITIAL_RETRY_DELAY"] = "2.0"
os.environ["MAX_RETRY_DELAY"] = "120.0"
os.environ["RETRY_EXPONENTIAL_BASE"] = "2.0"

# Get command line arguments
args = sys.argv[1:]
if not args:
    print("Usage: python run_process.py <youtube_id_or_url> [--verbose]")
    sys.exit(1)

# Construct the command
cmd = ["python", "-m", "yt_obsidian.main", "process"] + args

print(f"Running command: {' '.join(cmd)}")
print(f"With environment variables:")
print(f"  YOUTUBE_API_KEY: {os.environ['YOUTUBE_API_KEY'][:5]}...")
print(f"  OBSIDIAN_VAULT_PATH: {os.environ['OBSIDIAN_VAULT_PATH']}")
print(f"  API_ENDPOINT: {os.environ['API_ENDPOINT']}")
print(f"  MODEL: {os.environ['MODEL']}")

# Run the command
result = subprocess.run(cmd)
sys.exit(result.returncode)