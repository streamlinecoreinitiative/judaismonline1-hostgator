"""
Optimized deployment script for HostGator hosting.

This script freezes the Flask site using the existing update_site.py script
and uploads only changed files to a HostGator server over FTP.

Uses file hashing to detect changes and avoid unnecessary uploads.
"""

import os
import fnmatch
import hashlib
import json
import subprocess
import sys
from ftplib import FTP
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()


def file_hash(filepath):
    """Calculate MD5 hash of a file."""
    hash_md5 = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def load_file_hashes():
    """Load file hashes from cache file."""
    cache_file = '.deploy_cache.json'
    if os.path.exists(cache_file):
        with open(cache_file, 'r') as f:
            return json.load(f)
    return {}


def save_file_hashes(hashes):
    """Save file hashes to cache file."""
    cache_file = '.deploy_cache.json'
    with open(cache_file, 'w') as f:
        json.dump(hashes, f, indent=2)


def should_upload_file(local_path, cached_hashes):
    """Check if file should be uploaded based on hash comparison."""
    current_hash = file_hash(local_path)
    relative_path = os.path.relpath(local_path)
    
    if relative_path not in cached_hashes:
        return True, current_hash
    
    if cached_hashes[relative_path] != current_hash:
        return True, current_hash
    
    return False, current_hash


def create_remote_directory(ftp, remote_path):
    """Create remote directory structure."""
    if remote_path == '.' or remote_path == '':
        return
    
    path_parts = remote_path.strip("/").split("/")
    current_path = ""
    
    for part in path_parts:
        if not part:
            continue
        current_path = f"{current_path}/{part}" if current_path else f"/{part}"
        try:
            ftp.mkd(current_path)
            print(f"📁 Created directory: {current_path}")
        except Exception:
            # Directory probably exists
            pass


def upload_file(ftp, local_path, remote_path):
    """Upload a single file to FTP server."""
    print(f"📤 Uploading: {local_path} -> {remote_path}")
    
    # Ensure remote directory exists
    remote_dir = os.path.dirname(remote_path)
    if remote_dir and remote_dir != '.':
        create_remote_directory(ftp, remote_dir)
    
    try:
        with open(local_path, 'rb') as file:
            ftp.storbinary(f'STOR {remote_path}', file)
        print(f"✅ Uploaded successfully: {remote_path}")
        return True
    except Exception as e:
        print(f"❌ Failed to upload {local_path}: {e}")
        return False


def deploy_optimized():
    """Main deployment function with optimization."""
    # Generate static site by running update_site.py
    print("🔧 Running update_site.py to generate static site...")
    try:
        result = subprocess.run([sys.executable, "update_site.py"], capture_output=True, text=True, check=True)
        print("✅ update_site.py completed successfully")
        if result.stdout:
            print(f"📝 STDOUT:\n{result.stdout}")
        if result.stderr:
            print(f"⚠️ STDERR:\n{result.stderr}")
    except subprocess.CalledProcessError as e:
        print("❌ update_site.py failed!")
        print(f"📝 STDOUT:\n{e.stdout or ''}")
        print(f"📝 STDERR:\n{e.stderr or ''}")
        sys.exit(1)

    # Read FTP credentials from environment variables
    ftp_host = os.environ.get("HOSTGATOR_HOST")
    ftp_user = os.environ.get("HOSTGATOR_USERNAME")
    ftp_pass = os.environ.get("HOSTGATOR_PASSWORD")
    remote_base = os.environ.get("HOSTGATOR_REMOTE_PATH", "/public_html")

    print(f"🌐 FTP_HOST: {ftp_host}")
    print(f"👤 FTP_USER: {ftp_user}")
    print(f"🔒 FTP_PASS: {'*' * len(ftp_pass) if ftp_pass else None}")
    print(f"📁 REMOTE_PATH: {remote_base}")

    if not all([ftp_host, ftp_user, ftp_pass]):
        print("❌ Please set HOSTGATOR_HOST, HOSTGATOR_USERNAME and HOSTGATOR_PASSWORD environment variables.")
        sys.exit(2)

    local_dir = "docs"
    
    # Load cached file hashes
    cached_hashes = load_file_hashes()
    new_hashes = {}
    files_to_upload = []
    
    print(f"🔍 Scanning for changed files in {local_dir}...")
    
    # Scan for files that need uploading
    for root, dirs, files in os.walk(local_dir):
        for filename in files:
            local_path = os.path.join(root, filename)
            relative_path = os.path.relpath(local_path, local_dir)
            remote_path = f"{remote_base}/{relative_path.replace(os.sep, '/')}"
            
            should_upload, file_hash_value = should_upload_file(local_path, cached_hashes)
            new_hashes[os.path.relpath(local_path)] = file_hash_value
            
            if should_upload:
                files_to_upload.append((local_path, remote_path))
                print(f"📋 Queued for upload: {local_path}")
    
    if not files_to_upload:
        print("✨ No files need uploading. Everything is up to date!")
        return
    
    print(f"📊 Found {len(files_to_upload)} files to upload")
    
    # Upload files
    try:
        print(f"🔗 Connecting to FTP server {ftp_host}...")
        with FTP(ftp_host) as ftp:
            ftp.login(user=ftp_user, passwd=ftp_pass)
            print("✅ Connected successfully")
            
            uploaded_count = 0
            for local_path, remote_path in files_to_upload:
                if upload_file(ftp, local_path, remote_path):
                    uploaded_count += 1
            
            print(f"🎉 Upload complete! {uploaded_count}/{len(files_to_upload)} files uploaded successfully")
            
            # Save updated hashes only if upload was successful
            save_file_hashes(new_hashes)
            print("💾 Updated file cache")
            
    except Exception as e:
        print(f"❌ FTP error: {e}")
        sys.exit(3)


if __name__ == "__main__":
    deploy_optimized()
