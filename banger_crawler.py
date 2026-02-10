#!/usr/bin/env python3
"""Crawl the 'post a banger' quote tree and save to DuckDB."""

import duckdb
import requests
import json
import re
import os
from urllib.parse import urlparse, parse_qs

API_BASE = "https://public.api.bsky.app/xrpc"
AUTH_API_BASE = "https://bsky.social/xrpc"

# Global session with auth
session = requests.Session()
access_token = None

def login():
    """Authenticate with Bluesky using app password."""
    global access_token
    
    handle = os.environ.get('BSKY_HANDLE')
    app_password = os.environ.get('BSKY_APP_PASSWORD')
    
    if not handle or not app_password:
        print("No auth credentials found. Set BSKY_HANDLE and BSKY_APP_PASSWORD env vars.")
        print("Continuing without authentication (may hit rate limits)...")
        return False
    
    resp = requests.post(f"{AUTH_API_BASE}/com.atproto.server.createSession", json={
        'identifier': handle,
        'password': app_password
    })
    
    if resp.status_code == 200:
        data = resp.json()
        access_token = data.get('accessJwt')
        session.headers['Authorization'] = f'Bearer {access_token}'
        print(f"Authenticated as {data.get('handle')}")
        return True
    else:
        print(f"Auth failed: {resp.status_code} - {resp.text}")
        return False

def api_get(endpoint, params=None):
    """Make an authenticated GET request."""
    url = f"{API_BASE}/{endpoint}"
    resp = session.get(url, params=params)
    resp.raise_for_status()
    return resp.json()

def init_db(db_path="bangers.duckdb"):
    """Initialize the database schema."""
    con = duckdb.connect(db_path)
    con.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            uri TEXT PRIMARY KEY,
            cid TEXT,
            author_did TEXT,
            author_handle TEXT,
            author_display_name TEXT,
            text TEXT,
            created_at TIMESTAMP,
            indexed_at TIMESTAMP,
            like_count INTEGER,
            quote_count INTEGER,
            repost_count INTEGER,
            reply_count INTEGER,
            -- The post this one quotes (parent in our tree)
            quotes_uri TEXT,
            -- Extracted media info
            embed_type TEXT,
            media_url TEXT,
            media_title TEXT,
            media_description TEXT,
            -- Crawl metadata
            crawled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            quotes_crawled BOOLEAN DEFAULT FALSE
        )
    """)
    con.commit()
    return con

def extract_youtube_id(url):
    """Extract YouTube video ID from various URL formats."""
    if not url:
        return None
    parsed = urlparse(url)
    if 'youtube.com' in parsed.netloc:
        return parse_qs(parsed.query).get('v', [None])[0]
    elif 'youtu.be' in parsed.netloc:
        return parsed.path.lstrip('/')
    return None

def extract_media_info(record, embed_view=None):
    """Extract media URL and info from post embed."""
    embed = record.get('embed', {})
    etype = embed.get('$type', '')
    
    media_url = None
    media_title = None
    media_desc = None
    
    # Handle different embed types
    if etype == 'app.bsky.embed.external':
        ext = embed.get('external', {})
        media_url = ext.get('uri')
        media_title = ext.get('title')
        media_desc = ext.get('description')
    elif etype == 'app.bsky.embed.recordWithMedia':
        media = embed.get('media', {})
        if media.get('$type') == 'app.bsky.embed.external':
            ext = media.get('external', {})
            media_url = ext.get('uri')
            media_title = ext.get('title')
            media_desc = ext.get('description')
    
    return etype, media_url, media_title, media_desc

def extract_quoted_uri(record):
    """Extract the URI of the post being quoted."""
    embed = record.get('embed', {})
    etype = embed.get('$type', '')
    
    if etype == 'app.bsky.embed.record':
        return embed.get('record', {}).get('uri')
    elif etype == 'app.bsky.embed.recordWithMedia':
        return embed.get('record', {}).get('record', {}).get('uri')
    return None

def resolve_uri_to_did(uri):
    """Convert a handle-based URI to a DID-based URI."""
    # at://handle/collection/rkey -> at://did/collection/rkey
    if uri.startswith('at://did:'):
        return uri  # Already DID-based
    
    parts = uri.replace('at://', '').split('/')
    handle = parts[0]
    rest = '/'.join(parts[1:])
    
    # Resolve handle to DID
    try:
        data = api_get('com.atproto.identity.resolveHandle', {'handle': handle})
        did = data.get('did')
        if did:
            return f"at://{did}/{rest}"
    except:
        pass
    return uri

def fetch_post(uri):
    """Fetch a single post by URI."""
    data = api_get('app.bsky.feed.getPostThread', {
        'uri': uri,
        'depth': 0,
        'parentHeight': 0
    })
    return data.get('thread', {}).get('post')

def save_post(con, post, force_update=False):
    """Save a post to the database.
    
    If post exists and quote_count increased, marks quotes_crawled=FALSE so we re-crawl.
    Returns True if this is a new post, False if it already existed.
    """
    if not post:
        return False
    
    uri = post.get('uri')
    record = post.get('record', {})
    author = post.get('author', {})
    
    embed_type, media_url, media_title, media_desc = extract_media_info(record)
    quotes_uri = extract_quoted_uri(record)
    new_quote_count = post.get('quoteCount', 0)
    
    # Check if post exists and if quote count changed
    existing = con.execute(
        "SELECT quote_count, quotes_crawled FROM posts WHERE uri = ?", [uri]
    ).fetchone()
    
    if existing:
        old_quote_count, was_crawled = existing
        # If quote count increased, we need to re-crawl
        needs_recrawl = new_quote_count > (old_quote_count or 0)
        
        if force_update or needs_recrawl:
            con.execute("""
                UPDATE posts SET
                    like_count = ?,
                    quote_count = ?,
                    repost_count = ?,
                    reply_count = ?,
                    quotes_crawled = ?
                WHERE uri = ?
            """, [
                post.get('likeCount', 0),
                new_quote_count,
                post.get('repostCount', 0),
                post.get('replyCount', 0),
                False if needs_recrawl else was_crawled,
                uri
            ])
            con.commit()
        return False  # Not a new post
    
    # New post - insert it
    try:
        con.execute("""
            INSERT INTO posts (
                uri, cid, author_did, author_handle, author_display_name,
                text, created_at, indexed_at,
                like_count, quote_count, repost_count, reply_count,
                quotes_uri, embed_type, media_url, media_title, media_description,
                crawled_at, quotes_crawled
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, FALSE)
        """, [
            uri,
            post.get('cid'),
            author.get('did'),
            author.get('handle'),
            author.get('displayName'),
            record.get('text'),
            record.get('createdAt'),
            post.get('indexedAt'),
            post.get('likeCount', 0),
            new_quote_count,
            post.get('repostCount', 0),
            post.get('replyCount', 0),
            quotes_uri,
            embed_type,
            media_url,
            media_title,
            media_desc
        ])
        con.commit()
        return True  # New post
    except Exception as e:
        print(f"Error saving post: {e}")
        return False

def fetch_quotes(uri, cursor=None):
    """Fetch posts that quote a given URI."""
    # Must use DID-based URI for getQuotes to work
    uri = resolve_uri_to_did(uri)
    params = {'uri': uri, 'limit': 100}
    if cursor:
        params['cursor'] = cursor
    
    return api_get('app.bsky.feed.getQuotes', params)

def crawl_to_root(con, start_uri):
    """Crawl from a post up to the root, saving all posts."""
    uri = start_uri
    chain = []
    
    while uri:
        # Check if we already have this post
        existing = con.execute("SELECT uri, quotes_uri FROM posts WHERE uri = ?", [uri]).fetchone()
        
        if existing:
            print(f"Already have: {uri}")
            chain.append(uri)
            uri = existing[1]  # quotes_uri
        else:
            print(f"Fetching: {uri}")
            post = fetch_post(uri)
            if post:
                save_post(con, post)
                record = post.get('record', {})
                quotes_uri = extract_quoted_uri(record)
                
                author = post.get('author', {}).get('handle', 'unknown')
                qcount = post.get('quoteCount', 0)
                lcount = post.get('likeCount', 0)
                print(f"  -> {author} | quotes:{qcount} likes:{lcount}")
                
                chain.append(uri)
                uri = quotes_uri
            else:
                break
    
    return chain

def crawl_quotes_bfs(con, root_uri, max_depth=None):
    """Crawl all quotes starting from root using BFS."""
    from collections import deque
    
    queue = deque([(root_uri, 0)])
    total_crawled = 0
    
    while queue:
        uri, depth = queue.popleft()
        
        if max_depth is not None and depth > max_depth:
            continue
        
        # Check if we've already crawled quotes for this post
        result = con.execute(
            "SELECT quotes_crawled, quote_count FROM posts WHERE uri = ?", [uri]
        ).fetchone()
        
        if not result:
            # We don't have this post yet, fetch it
            post = fetch_post(uri)
            if post:
                save_post(con, post)
                result = (False, post.get('quoteCount', 0))
        
        if result and not result[0]:  # Not yet crawled quotes
            quote_count = result[1] or 0
            if quote_count > 0:
                print(f"Fetching {quote_count} quotes for {uri[:50]}... (depth={depth})")
                
                cursor = None
                while True:
                    data = fetch_quotes(uri, cursor)
                    posts = data.get('posts', [])
                    
                    for post in posts:
                        save_post(con, post)
                        total_crawled += 1
                        post_uri = post.get('uri')
                        if post.get('quoteCount', 0) > 0:
                            queue.append((post_uri, depth + 1))
                    
                    cursor = data.get('cursor')
                    if not cursor or not posts:
                        break
            
            # Mark as crawled
            con.execute("UPDATE posts SET quotes_crawled = TRUE WHERE uri = ?", [uri])
            con.commit()
    
    return total_crawled


def print_stats(con):
    """Print database statistics."""
    total = con.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    with_media = con.execute("SELECT COUNT(*) FROM posts WHERE media_url IS NOT NULL").fetchone()[0]
    
    print(f"\n=== Database Stats ===")
    print(f"Total posts: {total}")
    print(f"Posts with media: {with_media}")
    
    print(f"\n=== Top 10 Most Quoted Posts ===")
    rows = con.execute("""
        SELECT author_handle, quote_count, like_count, substr(text, 1, 50) as text_preview
        FROM posts 
        ORDER BY quote_count DESC 
        LIMIT 10
    """).fetchall()
    for row in rows:
        print(f"  {row[0]}: {row[1]} quotes, {row[2]} likes - {row[3]}...")
    
    print(f"\n=== Top 10 Songs (by frequency) ===")
    rows = con.execute("""
        SELECT ANY_VALUE(media_title) as title, media_url, COUNT(*) as cnt
        FROM posts 
        WHERE media_url IS NOT NULL AND media_url LIKE '%youtu%'
        GROUP BY media_url
        ORDER BY cnt DESC
        LIMIT 10
    """).fetchall()
    for row in rows:
        print(f"  {row[2]}x: {row[0]} - {row[1]}")


if __name__ == "__main__":
    import sys
    
    # Try to authenticate
    login()
    
    con = init_db()
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python banger_crawler.py trace <post_url>  - Trace to root and save chain")
        print("  python banger_crawler.py crawl <post_uri>  - Crawl all quotes from a post")
        print("  python banger_crawler.py stats             - Print database stats")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "trace":
        # Convert bsky.app URL to AT URI
        url = sys.argv[2]
        # https://bsky.app/profile/handle/post/id -> at://handle/app.bsky.feed.post/id
        parts = url.replace("https://bsky.app/profile/", "").split("/post/")
        handle, post_id = parts[0], parts[1]
        uri = f"at://{handle}/app.bsky.feed.post/{post_id}"
        
        print(f"Tracing from: {uri}")
        chain = crawl_to_root(con, uri)
        print(f"\nChain length: {len(chain)}")
        print(f"Root: {chain[-1] if chain else 'none'}")
        print_stats(con)
        
    elif cmd == "crawl":
        uri = sys.argv[2]
        print(f"Crawling quotes from: {uri}")
        count = crawl_quotes_bfs(con, uri)
        print(f"\nCrawled {count} new posts")
        print_stats(con)
        
    elif cmd == "stats":
        print_stats(con)
    
    elif cmd == "crawl-all":
        # Crawl all posts that have uncrawled quotes
        while True:
            row = con.execute('''
                SELECT uri, quote_count FROM posts 
                WHERE quote_count > 0 AND quotes_crawled = FALSE
                ORDER BY quote_count DESC
                LIMIT 1
            ''').fetchone()
            
            if not row:
                print("All quotes crawled!")
                break
            
            uri, qcount = row
            print(f"\nCrawling {qcount} quotes from {uri[:60]}...")
            count = crawl_quotes_bfs(con, uri)
            print(f"Got {count} new posts")
        
        print_stats(con)
    
    elif cmd == "update":
        # Efficiently update the tree by checking for new quotes
        # 1. Re-fetch posts that had quotes to see if count increased
        # 2. Crawl any newly discovered quotes
        
        print("Checking for new quotes on existing posts...")
        
        # Get all posts that had quotes (most likely to have new ones)
        posts_with_quotes = con.execute('''
            SELECT uri FROM posts 
            WHERE quote_count > 0
            ORDER BY quote_count DESC
        ''').fetchall()
        
        updated = 0
        for (uri,) in posts_with_quotes:
            try:
                post = fetch_post(uri)
                if post:
                    old_count = con.execute(
                        "SELECT quote_count FROM posts WHERE uri = ?", [uri]
                    ).fetchone()[0] or 0
                    new_count = post.get('quoteCount', 0)
                    
                    if new_count > old_count:
                        print(f"  {uri[:50]}... {old_count} -> {new_count} quotes")
                        save_post(con, post, force_update=True)
                        updated += 1
            except Exception as e:
                print(f"  Error fetching {uri[:50]}: {e}")
        
        print(f"\nFound {updated} posts with new quotes")
        
        if updated > 0:
            print("\nCrawling new quotes...")
            # Now crawl-all to get the new quotes
            while True:
                row = con.execute('''
                    SELECT uri, quote_count FROM posts 
                    WHERE quote_count > 0 AND quotes_crawled = FALSE
                    ORDER BY quote_count DESC
                    LIMIT 1
                ''').fetchone()
                
                if not row:
                    break
                
                uri, qcount = row
                print(f"Crawling {qcount} quotes from {uri[:50]}...")
                crawl_quotes_bfs(con, uri)
        
        print_stats(con)
    
    con.close()
