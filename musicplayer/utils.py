import unicodedata
import re

def slugify(text):
    """Convert text to letters-mus-br slug format"""
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('utf-8')
    text = text.lower()
    text = re.sub(r'[\s\-_]+', '-', text)
    text = re.sub(r'[^\w\-]', '', text)
    return text.strip('-')

def format_time(seconds):
    if seconds is None: return "00:00"
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins:02d}:{secs:02d}"

def parse_lrc(lrc_text):
    parsed = []
    pattern = re.compile(r'\[(\d+):(\d+(?:\.\d+)?)\](.*)')
    for line in lrc_text.splitlines():
        match = pattern.match(line)
        if match:
            minutes = float(match.group(1))
            seconds = float(match.group(2))
            text = match.group(3).strip()
            timestamp = minutes * 60 + seconds
            parsed.append({'time': timestamp, 'text': text})
    return parsed
