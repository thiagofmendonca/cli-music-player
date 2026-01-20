import os
import sys
import urllib.request
import py7zr

def download_and_extract():
    # URL direta para o build recente (SourceForge mirror automático)
    url = "https://sourceforge.net/projects/mpv-player-windows/files/libmpv/mpv-dev-x86_64-20250118-git-468d34c.7z/download"
    dest_7z = "libmpv.7z"
    
    print(f"Downloading {url}...")
    try:
        # User-Agent é crucial para o SourceForge não bloquear
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'}
        )
        with urllib.request.urlopen(req) as response, open(dest_7z, 'wb') as out_file:
            data = response.read()
            out_file.write(data)
            print(f"Downloaded {len(data)} bytes")
            
        print("Extracting mpv-2.dll...")
        # Usando py7zr se disponível, ou fallback para comando de sistema se necessário
        # Mas no actions instalamos py7zr via pip se quisermos, ou usamos o 7z do sistema
        # Para garantir, vamos usar o 7z do sistema que já tem no Windows runner
        import subprocess
        subprocess.run(["7z", "e", dest_7z, "-o.", "mpv-2.dll", "-y"], check=True)
        
        if os.path.exists("mpv-2.dll"):
            print("Success: mpv-2.dll extracted.")
        else:
            print("Error: mpv-2.dll not found after extraction.")
            sys.exit(1)
            
    except Exception as e:
        print(f"Failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    download_and_extract()
