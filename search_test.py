import yt_dlp
import json
import sys

def test_search(query, source='youtube'):
    print(f"--- Testing Source: {source} (Query: '{query}') ---")
    
    # yt-dlp search prefixes
    prefix = "ytsearch5:" if source == 'youtube' else "scsearch5:"
    
    ydl_opts = {
        'quiet': True,
        'noplaylist': True,
        'extract_flat': 'in_playlist', # Just extract metadata, don't download, don't resolve deep URLs yet
        'skip_download': True,
        'no_warnings': True,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # The search query is formatted as "prefix:query"
            info = ydl.extract_info(f"{prefix}{query}", download=False)
            
            if 'entries' in info:
                results = list(info['entries'])
                print(f"Found {len(results)} results:")
                for i, entry in enumerate(results):
                    title = entry.get('title', 'Unknown')
                    uploader = entry.get('uploader', 'Unknown')
                    duration = entry.get('duration', 0)
                    url = entry.get('url', 'No URL')
                    video_id = entry.get('id', 'No ID')
                    
                    print(f"[{i+1}] {title}")
                    print(f"    Artist: {uploader}")
                    print(f"    Duration: {duration}s")
                    print(f"    ID: {video_id}")
                    # print(f"    URL: {url}") # URL in extract_flat is usually just the ID or webpage_url
            else:
                print("No 'entries' found in result.")
                
    except Exception as e:
        print(f"Error searching {source}: {e}")
    print("\n")

if __name__ == "__main__":
    test_search("Coldplay Yellow", "youtube")
    test_search("Synthwave", "soundcloud")
