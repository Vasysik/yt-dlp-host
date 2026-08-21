# Development Roadmap

```text
yt-dlp-host
│
├── Search
│   └── yt-dlp-powered search (ytsearch)
│
├── Metadata
│   ├── embed metadata
│   ├── embed thumbnail
│   └── optional ID3 handling via mutagen
│
├── Synchronous Requests
│   └── wait mode with async fallback
│
├── Playlists
│   ├── audio/video playlist downloads
│   ├── item/range selection
│   ├── per-item progress
│   ├── partial failure handling
│   └── optional archive output
│
├── Streaming
│   ├── audio streaming
│   ├── video streaming
│   ├── FFmpeg pipe/mux
│   ├── client disconnect cancellation
│   └── quota/concurrency handling
│
└── Object Storage
    ├── Local storage
    ├── S3-compatible storage
    │   ├── Amazon S3
    │   ├── Cloudflare R2
    │   └── MinIO
    └── Google Cloud Storage
```
