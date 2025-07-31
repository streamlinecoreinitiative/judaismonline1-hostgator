"""
Deployment script for HostGator hosting.

This script freezes the Flask site using the existing update_site.py script
and uploads the generated static files to a HostGator server over FTP.

Set the following environment variables before running:

- HOSTGATOR_HOST: Hostname or IP address of your HostGator FTP server (e.g., 'ftp.example.com').
- HOSTGATOR_USERNAME: FTP username.
- HOSTGATOR_PASSWORD: FTP password.
- HOSTGATOR_REMOTE_PATH: Path on the FTP server where the static site should be uploaded (defaults to '/public_html').
- If your HostGator domain is under hostgator.mx, you may leave `HOSTGATOR_REMOTE_PATH` as '/public_html' to deploy to the root of your site.

You need to install the built-in ftplib library; no external dependencies are required.

Usage: python deploy_hostgator.py
"""

import os
import ftplib
import subprocess
import sys

# Generate static site by running update_site.py which calls daily_post, update_news and freeze
print("Running update_site.py to generate static site...")
subprocess.run([sys.executable, "update_site.py"], check=True)

# Read FTP credentials from environment variables
ftp_host = os.environ.get("HOSTGATOR_HOST")
ftp_user = os.environ.get("HOSTGATOR_USERNAME")
ftp_pass = os.environ.get("HOSTGATOR_PASSWORD")
remote_base = os.environ.get("HOSTGATOR_REMOTE_PATH", "/public_html")

if not all([ftp_host, ftp_user, ftp_pass]):
    raise RuntimeError(
        "Please set HOSTGATOR_HOST, HOSTGATOR_USERNAME and HOSTGATOR_PASSWORD environment variables."
    )

local_dir = "docs"

def upload_directory(ftp: ftplib.FTP, local_path: str, remote_path: str):
    """
    Recursively upload a local directory to the FTP server.
    """
    # Ensure the remote directory exists; create nested directories as needed
    def ensure_remote_dir(path_parts):
        current_path = ""
        for part in path_parts:
            if not part:
                continue
            current_path += "/" + part
            try:
                ftp.mkd(current_path)
            except ftplib.error_perm:
                # Directory probably exists
                pass

    ensure_remote_dir(remote_path.strip("/").split("/"))
    ftp.cwd(remote_path)

    for root, dirs, files in os.walk(local_path):
        rel_path = os.path.relpath(root, local_path)
        remote_sub = remote_path if rel_path == "." else f"{remote_path}/{rel_path.replace(os.sep, '/')}"
        # Ensure subdirectory exists on remote
        ensure_remote_dir(remote_sub.strip("/").split("/"))
        ftp.cwd(remote_sub)
        for filename in files:
            file_path = os.path.join(root, filename)
            with open(file_path, "rb") as f:
                print(f"Uploading {file_path} to {remote_sub}/{filename}")
                ftp.storbinary(f"STOR {filename}", f)
        # Reset to root remote path before descending to next directory
        ftp.cwd(remote_path)

print(f"Connecting to FTP server {ftp_host}...")
with ftplib.FTP(ftp_host) as ftp:
    ftp.login(user=ftp_user, passwd=ftp_pass)
    print("Connected. Uploading files...")
    upload_directory(ftp, local_dir, remote_base)
    print("Upload complete.")
