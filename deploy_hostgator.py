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


def list_remote_files(ftp, remote_path, base_path=""):
    """Recursively list all files on the remote FTP server."""
    remote_files = []
    try:
        ftp.cwd(remote_path)
        items = []
        ftp.retrlines('LIST', items.append)
        
        for item in items:
            # Parse FTP LIST output (simplified)
            parts = item.split()
            if len(parts) >= 9:
                permissions = parts[0]
                filename = ' '.join(parts[8:])
                
                # Skip . and .. directories
                if filename in ['.', '..']:
                    continue
                
                relative_path = f"{base_path}/{filename}" if base_path else filename
                full_remote_path = f"{remote_path}/{filename}"
                
                if permissions.startswith('d'):  # Directory
                    # Recursively list directory contents
                    sub_files = list_remote_files(ftp, full_remote_path, relative_path)
                    remote_files.extend(sub_files)
                else:  # File
                    remote_files.append(relative_path)
        
        return remote_files
    except Exception as e:
        print(f"⚠️ Warning: Could not list remote directory {remote_path}: {e}")
        return []


def delete_remote_file(ftp, remote_path):
    """Delete a file from the remote FTP server."""
    try:
        ftp.delete(remote_path)
        print(f"🗑️ Deleted remote file: {remote_path}")
        return True
    except Exception as e:
        print(f"❌ Failed to delete remote file {remote_path}: {e}")
        return False


def delete_empty_remote_directories(ftp, remote_base):
    """Delete empty directories from the remote server."""
    try:
        def try_delete_dir(dir_path):
            try:
                ftp.rmd(dir_path)
                print(f"🗑️ Deleted empty remote directory: {dir_path}")
                return True
            except Exception:
                return False
        
        # Get all directories and try to delete them (starting from deepest)
        ftp.cwd(remote_base)
        dirs_to_check = []
        
        def collect_dirs(path, base=""):
            try:
                ftp.cwd(path)
                items = []
                ftp.retrlines('LIST', items.append)
                
                for item in items:
                    parts = item.split()
                    if len(parts) >= 9:
                        permissions = parts[0]
                        filename = ' '.join(parts[8:])
                        
                        if filename in ['.', '..']:
                            continue
                        
                        if permissions.startswith('d'):
                            dir_path = f"{base}/{filename}" if base else filename
                            full_path = f"{path}/{filename}"
                            dirs_to_check.append(full_path)
                            collect_dirs(full_path, dir_path)
            except Exception:
                pass
        
        collect_dirs(remote_base)
        
        # Sort by depth (deepest first) and try to delete
        dirs_to_check.sort(key=lambda x: x.count('/'), reverse=True)
        for dir_path in dirs_to_check:
            try_delete_dir(dir_path)
            
    except Exception as e:
        print(f"⚠️ Warning during directory cleanup: {e}")


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
            
            # Get list of remote files for deletion comparison
            print("🔍 Scanning remote files for cleanup...")
            remote_files = list_remote_files(ftp, remote_base)
            
            # Determine which remote files should be deleted
            files_to_delete = []
            local_relative_files = set()
            
            # Build set of all local files (relative to docs/)
            for root, dirs, files in os.walk(local_dir):
                for filename in files:
                    local_path = os.path.join(root, filename)
                    relative_path = os.path.relpath(local_path, local_dir)
                    local_relative_files.add(relative_path.replace(os.sep, '/'))
            
            # Find remote files that don't exist locally
            for remote_file in remote_files:
                if remote_file not in local_relative_files:
                    remote_file_path = f"{remote_base}/{remote_file}"
                    files_to_delete.append(remote_file_path)
            
            # Delete obsolete remote files
            if files_to_delete:
                print(f"🗑️ Found {len(files_to_delete)} files to delete from server:")
                deleted_count = 0
                for remote_file_path in files_to_delete:
                    print(f"🗑️ Deleting: {remote_file_path}")
                    if delete_remote_file(ftp, remote_file_path):
                        deleted_count += 1
                
                print(f"🧹 Deleted {deleted_count}/{len(files_to_delete)} remote files")
                
                # Clean up empty directories
                print("🧹 Cleaning up empty directories...")
                delete_empty_remote_directories(ftp, remote_base)
            else:
                print("✨ No remote files need deletion")
            
            # Upload new/changed files
            uploaded_count = 0
            for local_path, remote_path in files_to_upload:
                if upload_file(ftp, local_path, remote_path):
                    uploaded_count += 1
            
            print(f"🎉 Deployment complete!")
            print(f"📤 Uploaded: {uploaded_count}/{len(files_to_upload)} files")
            if files_to_delete:
                print(f"🗑️ Deleted: {deleted_count}/{len(files_to_delete)} obsolete files")
            
            # Save updated hashes only if upload was successful
            save_file_hashes(new_hashes)
            print("💾 Updated file cache")
            
    except Exception as e:
        print(f"❌ FTP error: {e}")
        sys.exit(3)


if __name__ == "__main__":
    deploy_optimized()
