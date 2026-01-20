import os
import sys
import urllib.request
import subprocess

def download_and_extract():
    # URL verificada do GitHub
    url = "https://github.com/shinchiro/mpv-winbuild-cmake/releases/download/20260120/mpv-dev-x86_64-20260120-git-b7e8fe9.7z"
    dest_7z = "libmpv.7z"
    dll_name = "libmpv-2.dll" # Nome exato dentro do 7z
    
    print(f"Downloading {url}...")
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response, open(dest_7z, 'wb') as out_file:
            out_file.write(response.read())
            
        print(f"Extracting {dll_name}...")
        # Extrai recursivamente para encontrar o arquivo onde quer que ele esteja
        subprocess.run(["7z", "e", dest_7z, "-o.", dll_name, "-y", "-r"], check=True)
        
        if os.path.exists(dll_name):
            # Renomeia para mpv-2.dll para manter compatibilidade com o que o PyInstaller espera
            os.rename(dll_name, "mpv-2.dll")
            print("Success: mpv-2.dll extracted and renamed.")
            if os.path.exists(dest_7z): os.remove(dest_7z)
        else:
            print(f"Error: {dll_name} not found after extraction.")
            sys.exit(1)
            
    except Exception as e:
        print(f"Failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    download_and_extract()
