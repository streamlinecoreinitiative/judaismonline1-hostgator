"""Delete the HostGator remote directory via FTP."""

import os
import ftplib

ftp_host = os.environ.get("HOSTGATOR_HOST")
ftp_user = os.environ.get("HOSTGATOR_USERNAME")
ftp_pass = os.environ.get("HOSTGATOR_PASSWORD")
remote_base = os.environ.get("HOSTGATOR_REMOTE_PATH", "/public_html")

if not all([ftp_host, ftp_user, ftp_pass]):
    raise RuntimeError(
        "Please set HOSTGATOR_HOST, HOSTGATOR_USERNAME and HOSTGATOR_PASSWORD environment variables."
    )


def delete_recursive(ftp: ftplib.FTP, path: str):
    try:
        items = ftp.nlst(path)
    except ftplib.error_perm as e:
        print(f"Cannot list {path}: {e}")
        return
    for item in items:
        try:
            ftp.delete(item)
            print(f"Deleted {item}")
        except ftplib.error_perm:
            delete_recursive(ftp, item)
            try:
                ftp.rmd(item)
                print(f"Removed directory {item}")
            except ftplib.error_perm as err:
                print(f"Failed to remove directory {item}: {err}")


print(f"Connecting to FTP server {ftp_host}...")
with ftplib.FTP(ftp_host) as ftp:
    ftp.login(user=ftp_user, passwd=ftp_pass)
    print(f"Connected. Removing {remote_base}...")
    delete_recursive(ftp, remote_base)
    try:
        ftp.rmd(remote_base)
    except ftplib.error_perm:
        pass
    print("Deletion complete.")

