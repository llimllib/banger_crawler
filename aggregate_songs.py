#!/usr/bin/env python3
"""Aggregate songs by matching titles across different URLs/platforms."""

import duckdb
import re
from collections import defaultdict

# Manual mappings for songs that are hard to match automatically
# Maps a "canonical name" to patterns that identify it
SONG_PATTERNS = {
    "Adriano Celentano - Prisencolinensinainciusol": ["prisencolinensinainciusol"],
    "Plastic Bertrand - Ça Plane Pour Moi": ["plane pour moi", "ca plane"],
    "Nena - 99 Luftballons": ["99 luftballons", "99 red balloons"],
    "The HU - Wolf Totem": ["wolf totem"],
    "The HU - Yuve Yuve Yu": ["yuve yuve yu"],
    "O-Zone - Dragostea Din Tei": ["dragostea din tei", "numa numa"],
    "Rammstein - Du Hast": ["du hast"],
    "Rammstein - Sonne": ["rammstein sonne", "rammstein - sonne"],
    "Falco - Der Kommissar": ["der kommissar"],
    "Stromae - Papaoutai": ["papaoutai"],
    "Pizzicato Five - Twiggy Twiggy": ["twiggy twiggy"],
    "La Bamba": ["la bamba"],
    "Los Fabulosos Cadillacs - Matador": ["fabulosos cadillacs", "cadillacs matador"],
    "Sigur Rós - Hoppípolla": ["hoppipolla", "hoppípolla"],
    "Bomba Estéreo - Soy Yo": ["bomba estereo soy yo", "bomba estéreo soy yo"],
    "Daddy Yankee - Gasolina": ["gasolina"],
}


def normalize_title(title):
    """Normalize a title for matching."""
    if not title:
        return ''
    t = title.lower()
    # Normalize unicode
    t = t.replace('ç', 'c').replace('é', 'e').replace('ó', 'o').replace('í', 'i')
    # Remove everything in parens/brackets
    t = re.sub(r'\s*[\(\[].*?[\)\]]', '', t)
    # Remove punctuation
    t = re.sub(r'[^\w\s]', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def match_song(title):
    """Try to match a title to a canonical song name."""
    norm = normalize_title(title)
    for canonical, patterns in SONG_PATTERNS.items():
        for pattern in patterns:
            if pattern in norm:
                return canonical
    return None


def aggregate_songs(db_path="bangers.duckdb"):
    """Aggregate songs and return sorted list."""
    con = duckdb.connect(db_path)
    
    rows = con.execute('''
        SELECT media_url, media_title
        FROM posts 
        WHERE media_url IS NOT NULL AND media_title IS NOT NULL
    ''').fetchall()
    
    # Count by canonical song name
    song_counts = defaultdict(lambda: {"count": 0, "urls": [], "titles": set()})
    unmatched = defaultdict(lambda: {"count": 0, "urls": [], "titles": set()})
    
    for url, title in rows:
        canonical = match_song(title)
        if canonical:
            song_counts[canonical]["count"] += 1
            song_counts[canonical]["urls"].append(url)
            song_counts[canonical]["titles"].add(title)
        else:
            # Use normalized title as key for unmatched
            norm = normalize_title(title)
            unmatched[norm]["count"] += 1
            unmatched[norm]["urls"].append(url)
            unmatched[norm]["titles"].add(title)
    
    # Sort matched songs
    sorted_songs = sorted(song_counts.items(), key=lambda x: -x[1]["count"])
    
    # Add top unmatched songs
    sorted_unmatched = sorted(unmatched.items(), key=lambda x: -x[1]["count"])
    
    return sorted_songs, sorted_unmatched


def get_best_youtube_url(urls):
    """Pick the best YouTube URL from a list."""
    for url in urls:
        if 'youtube.com/watch' in url or 'youtu.be/' in url:
            # Prefer youtube.com over youtu.be
            if 'youtube.com' in url:
                return url
    # Fall back to first youtube URL
    for url in urls:
        if 'youtu' in url:
            return url
    return urls[0] if urls else None


if __name__ == "__main__":
    matched, unmatched = aggregate_songs()
    
    print("=" * 60)
    print("TOP SONGS (matched to canonical names)")
    print("=" * 60)
    for i, (name, data) in enumerate(matched[:20], 1):
        url = get_best_youtube_url(data["urls"])
        print(f"{i:2d}. [{data['count']:2d}] {name}")
        print(f"      {url}")
        print()
    
    print("\n" + "=" * 60)
    print("TOP UNMATCHED (may need manual mapping)")
    print("=" * 60)
    for i, (norm, data) in enumerate(unmatched[:15], 1):
        sample_title = list(data["titles"])[0][:50]
        print(f"{i:2d}. [{data['count']:2d}] {sample_title}...")
