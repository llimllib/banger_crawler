# Banger Crawler 🎵

A tool to crawl and visualize the Bluesky meme **"Post a banger that isn't in English"** - a viral chain of quote-posts

## The Meme

Started on March 24, 2024 by [@bridgemusicbunker.bsky.social](https://bsky.app/profile/bridgemusicbunker.bsky.social) with... Scatman John's "Scatman".

The meme spread through quote-posts, creating a massive tree structure that's now **25 levels deep** with **2,300+ posts**.

## Live Visualization

👉 **[View the interactive tree](https://llimllib.github.io/banger_crawler/)**

- **Scroll** to zoom in/out
- **Drag** to pan
- **Hover** on nodes to see post details
- **Click** a node to play the song (YouTube, Spotify, Apple Music embeds)

Node colors:

- 🔴 Red = YouTube video
- 🔵 Teal = Other media (Spotify, Apple Music, etc.)
- ⚫ Gray = No media attached

Node size = number of quote-posts

## Top Songs

| #   | Song                                          | Posts |
| --- | --------------------------------------------- | ----- |
| 1   | Adriano Celentano - Prisencolinensinainciusol | ~39   |
| 2   | Nena - 99 Luftballons                         | 14    |
| 3   | The HU - Wolf Totem                           | 9     |
| 4   | O-Zone - Dragostea Din Tei                    | 9     |
| 5   | Plastic Bertrand - Ça Plane Pour Moi          | ~17   |
| 6   | Rammstein - Sonne / Du Hast                   | ~11   |
| 7   | The HU - Yuve Yuve Yu                         | 7     |
| 8   | Pizzicato Five - Twiggy Twiggy                | 6     |
| 9   | Falco - Der Kommissar                         | 6     |
| 10  | Stromae - Papaoutai                           | 6     |

## Usage

### Crawling

Set up authentication:

```bash
export BSKY_HANDLE="your-handle.bsky.social"
export BSKY_APP_PASSWORD="xxxx-xxxx-xxxx-xxxx"
```

Trace from a post back to the root:

```bash
python banger_crawler.py trace "https://bsky.app/profile/someone/post/abc123"
```

Crawl all quotes from a post:

```bash
python banger_crawler.py crawl "at://did:plc:xxx/app.bsky.feed.post/abc123"
```

Crawl all uncrawled quotes in the database:

```bash
python banger_crawler.py crawl-all
```

Update the tree (efficiently check for new quotes on existing posts):

```bash
python banger_crawler.py update
```

View stats:

```bash
python banger_crawler.py stats
```

### Exporting

Generate the tree JSON and song stats:

```bash
python export_tree.py
```

### Viewing locally

```bash
python -m http.server 8765
# Open http://localhost:8765/tree_viz.html
```

## Files

- `banger_crawler.py` - Main crawler script
- `export_tree.py` - Export tree structure and song stats to JSON
- `tree_viz.html` - Interactive D3.js visualization
- `bangers.duckdb` - DuckDB database with all posts
- `banger_tree.json` - Tree structure for visualization
- `song_stats.json` - Top 100 songs with stats

## Requirements

- Python 3.8+
- `duckdb`
- `requests`

```bash
pip install duckdb requests
```

## License

MIT
