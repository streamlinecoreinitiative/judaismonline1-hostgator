
import os
from ftplib import FTP
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

FTP_HOST = os.getenv('HOSTGATOR_HOST')
FTP_USER = os.getenv('HOSTGATOR_USERNAME')
FTP_PASS = os.getenv('HOSTGATOR_PASSWORD')
FTP_PATH = os.getenv('HOSTGATOR_REMOTE_PATH', '/')

def test_ftp_connection():
    try:
        print(f"Conectando a {FTP_HOST}...")
        ftp = FTP(FTP_HOST)
        ftp.login(FTP_USER, FTP_PASS)
        print("Conexión exitosa.")
        ftp.cwd(FTP_PATH)
        print(f"Directorio actual: {ftp.pwd()}")
        print("Archivos en el directorio:")
        ftp.retrlines('LIST')
        ftp.quit()
        print("Conexión cerrada.")
    except Exception as e:
        print(f"Error en la conexión FTP: {e}")

if __name__ == "__main__":
    test_ftp_connection()
