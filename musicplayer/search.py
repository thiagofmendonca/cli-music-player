import yt_dlp

class OnlineSearcher:
    def __init__(self):
        self.ydl_opts = {
            'quiet': True,
            'noplaylist': True,
            'extract_flat': 'in_playlist',
            'skip_download': True,
            'no_warnings': True,
        }

    def search(self, query, source='youtube'):
        """
        Search for tracks on YouTube or SoundCloud.
        source: 'youtube' or 'soundcloud'
        Returns: List of dicts {'title', 'artist', 'duration', 'id', 'source'}
        """
        prefix = "ytsearch5:" if source == 'youtube' else "scsearch5:"
        
        try:
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                info = ydl.extract_info(f"{prefix}{query}", download=False)
                
                results = []
                if 'entries' in info:
                    for entry in info['entries']:
                        results.append({
                            'title': entry.get('title', 'Unknown'),
                            'artist': entry.get('uploader', 'Unknown'),
                            'duration': entry.get('duration', 0),
                            'id': entry.get('id'),
                            'url': entry.get('url'), # Capture the full URL
                            'source': source,
                            'type': 'stream' # To distinguish from 'file'
                        })
                return results
        except Exception as e:
            # print(f"Search error: {e}")
            return []
