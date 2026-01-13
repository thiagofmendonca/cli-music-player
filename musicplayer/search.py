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
        is_url = query.startswith('http') or query.startswith('www')
        if is_url:
            search_query = query
        else:
            prefix = "ytsearch20:" if source == 'youtube' else "scsearch20:"
            search_query = f"{prefix}{query}"
        
        try:
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                info = ydl.extract_info(search_query, download=False)
                
                results = []
                # If it's a direct video URL, info might be the dict itself
                if 'entries' not in info and 'title' in info:
                    results.append({
                        'title': info.get('title', 'Unknown'),
                        'artist': info.get('uploader', 'Unknown'),
                        'duration': info.get('duration', 0),
                        'id': info.get('id'),
                        'url': info.get('url') or info.get('webpage_url'),
                        'source': source,
                        'type': 'stream'
                    })
                elif 'entries' in info:
                    for entry in info['entries']:
                        # Filter out None entries (happens sometimes with deleted videos in playlists)
                        if not entry: continue
                        results.append({
                            'title': entry.get('title', 'Unknown'),
                            'artist': entry.get('uploader', 'Unknown'),
                            'duration': entry.get('duration', 0),
                            'id': entry.get('id'),
                            'url': entry.get('url'), 
                            'source': source,
                            'type': 'stream' 
                        })
                return results
        except Exception as e:
            # print(f"Search error: {e}")
            return []
