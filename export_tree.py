#!/usr/bin/env python3
"""Export the banger tree to various formats."""

import duckdb
import json
from urllib.parse import urlparse, parse_qs

def extract_video_id(url):
    if not url:
        return None
    parsed = urlparse(url)
    if 'youtube.com' in parsed.netloc or 'www.youtube.com' in parsed.netloc:
        return parse_qs(parsed.query).get('v', [None])[0]
    elif 'youtu.be' in parsed.netloc:
        return parsed.path.lstrip('/').split('?')[0]
    return None

def export_to_json(con, output_file='banger_tree.json'):
    """Export tree structure to JSON."""
    
    # Get all posts with their relationships
    posts = con.execute('''
        SELECT uri, author_handle, author_display_name, text, 
               quotes_uri, media_url, media_title, like_count, quote_count,
               created_at
        FROM posts
    ''').fetchall()
    
    # Build lookup
    post_map = {}
    for p in posts:
        uri, handle, display, text, parent, media_url, media_title, likes, quotes, created = p
        post_map[uri] = {
            'uri': uri,
            'author': display or handle,
            'handle': handle,
            'text': text[:100] if text else '',
            'parent': parent,
            'media_url': media_url,
            'media_title': media_title,
            'youtube_id': extract_video_id(media_url),
            'likes': likes,
            'quotes': quotes,
            'created': str(created) if created else None,
            'children': []
        }
    
    # Build tree structure
    roots = []
    for uri, node in post_map.items():
        parent_uri = node['parent']
        if parent_uri and parent_uri in post_map:
            post_map[parent_uri]['children'].append(node)
        elif not parent_uri:
            roots.append(node)
    
    # Remove parent references for cleaner JSON
    def clean_node(node):
        del node['parent']
        for child in node['children']:
            clean_node(child)
        return node
    
    for root in roots:
        clean_node(root)
    
    with open(output_file, 'w') as f:
        json.dump(roots, f, indent=2)
    
    print(f"Exported tree to {output_file}")
    return roots


def export_song_stats(con, output_file='song_stats.json'):
    """Export song statistics."""
    
    rows = con.execute('''
        SELECT media_url, media_title, author_handle, like_count
        FROM posts 
        WHERE media_url IS NOT NULL 
        AND (media_url LIKE '%youtu%' OR media_url LIKE '%youtube%')
    ''').fetchall()
    
    # Aggregate by video ID
    videos = {}
    for url, title, author, likes in rows:
        vid = extract_video_id(url)
        if vid:
            if vid not in videos:
                videos[vid] = {
                    'id': vid,
                    'title': title,
                    'url': f'https://youtube.com/watch?v={vid}',
                    'count': 0,
                    'total_likes': 0,
                    'posters': []
                }
            videos[vid]['count'] += 1
            videos[vid]['total_likes'] += likes or 0
            videos[vid]['posters'].append(author)
    
    # Sort by count
    sorted_videos = sorted(videos.values(), key=lambda x: -x['count'])
    
    with open(output_file, 'w') as f:
        json.dump(sorted_videos[:100], f, indent=2)  # Top 100
    
    print(f"Exported song stats to {output_file}")
    return sorted_videos


def print_top_songs(videos, n=50):
    """Print top songs in a nice format."""
    print(f"\n{'='*60}")
    print(f"TOP {n} SONGS - 'Post a banger that isn't in English'")
    print(f"{'='*60}\n")
    
    for i, v in enumerate(videos[:n], 1):
        print(f"{i:2d}. [{v['count']:2d} posts] {v['title'][:55]}")
        print(f"    {v['url']}")
        print()


if __name__ == '__main__':
    con = duckdb.connect('bangers.duckdb')
    
    # Export tree
    export_to_json(con)
    
    # Export and print song stats  
    videos = export_song_stats(con)
    print_top_songs(videos, 50)
    
    con.close()
