# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python video processing system that performs automated content analysis and editing. The pipeline: extracts audio → uploads to OSS → ASR transcription → AI analysis (DeepSeek) → intelligent clip cutting → video merging → optional subtitles.

## Installation

### System Requirements
- Python 3.9+
- ffmpeg (required for video processing)

### Install ffmpeg
**macOS:** `brew install ffmpeg`
**Ubuntu/Debian:** `sudo apt-get install ffmpeg`
**Windows:** Download from https://ffmpeg.org/download.html

### Install the Package

#### Method 1: Development Install (Recommended for development)
```bash
pip install -e .
# Or with dev dependencies: pip install -e ".[dev]"
```

#### Method 2: Using Install Scripts
```bash
# macOS/Linux
chmod +x install.sh && ./install.sh

# Windows
install.bat
```

#### Method 3: From Wheel Package
```bash
pip install dist/video_processor-1.0.0-py3-none-any.whl
```

### Configuration
1. Copy `.env.example` to `.env`
2. Fill in API keys:
   - `ALIYUN_ACCESS_KEY_ID` / `ALIYUN_ACCESS_KEY_SECRET`: OSS credentials
   - `ALIYUN_APP_KEY`: ASR app key
   - `DEEPSEEK_API_KEY`: DeepSeek API key

### Installed Commands
After installation, the following CLI commands are available:
- `video-processor` or `vp`: Main video processing command
- `video-server`: Start HTTP API server (port 8001)
- `video-ws-server`: Start WebSocket server (port 8000)

## Common Commands

### Development Dependencies (legacy method)
```bash
pip install -r app/requirements.txt
```

### Run Tests
```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_video_processor.py

# Run single test
pytest tests/test_video_processor.py::test_init_creates_dirs -v
```

### Start Servers
```bash
# Using installed commands (recommended)
video-ws-server    # WebSocket server (port 8000)
video-server       # HTTP API server (port 8001)

# Or using Python directly (development)
python app/services/websocket_server.py
python run.py --server
```

### Process Videos (CLI)
```bash
# Using installed command (recommended)
video-processor video1.mp4 video2.mp4
vp video1.mp4 video2.mp4  # alias

# Process all videos in data/input/mediasource
video-processor

# Custom output directory
video-processor -o custom_output video.mp4

# Analyze existing transcripts
video-processor --analyze

# Merge existing clips
video-processor --merge

# Add subtitles to latest video
video-processor --add-subtitles

# Or using Python directly (development)
python run.py video1.mp4 video2.mp4
python run.py -o custom_output video.mp4
```

## Architecture

### Entry Points
- `run.py`: CLI entry that sets up Python path and delegates to `main.py`
- `app/main.py`: Argument parsing and dispatch to VideoProcessor or servers
- `app/services/websocket_server.py`: WebSocket server (port 8000) for real-time task processing
- `app/services/http_server.py`: FastAPI HTTP server (port 8001) with REST endpoints

### Core Components (`app/core/`)

**VideoProcessor** (`video_processor.py`): The main orchestrator class that coordinates the entire pipeline:
- `process_directory()`: Main workflow - transcribe all videos → merge → analyze → cut → merge
- `process_single_video()`: Extract audio → OSS upload → ASR → save transcript JSON
- Delegates to specialized modules for each step

**TaskManager** (`task_manager.py`): Async task queue for WebSocket server with concurrent task limiting (default max 3). Manages VideoProcessor instances per task and handles WebSocket communication.

**ASRClient** (`asr_client.py`): Wraps Alibaba Cloud ASR (filetrans) API for speech recognition. Uploads audio to OSS, submits transcription tasks, polls for results.

**AI Analyzer** (`ai_analyzer.py`): Uses DeepSeek API to analyze merged transcripts and generate `important_dialogues.txt` and `clip_order.txt`.

**Clip Cutter** (`clip_cutter.py`): Reads `clip_order.txt` and cuts video segments using MoviePy.

**Transcript Merger** (`transcript_merger.py`): Merges individual JSON transcript files into `merged_transcripts.txt` with proper ordering.

### Two-Server Architecture
The system uses a dual-server design:
1. **WebSocket Server** (port 8000): Handles long-running video processing tasks via `TaskManager`
2. **HTTP Server** (port 8001): FastAPI REST API that forwards requests to WebSocket server internally

The HTTP server's `/api/process` endpoint connects to `ws://localhost:8000` to delegate actual processing.

### Configuration (`app/config/config.py`)
Environment variables (loaded from `.env`):
- `ALIYUN_ACCESS_KEY_ID` / `ALIYUN_ACCESS_KEY_SECRET`: OSS and ASR credentials
- `ALIYUN_APP_KEY`: ASR app key
- `DEEPSEEK_API_KEY`: AI analysis API key
- `ALIYUN_BUCKET_NAME`, `ALIYUN_ENDPOINT`: OSS configuration

### Directory Structure
```
data/
  input/mediasource/   # Default input videos
  output/              # Task outputs with merged_highlights.mp4
  temp/                # Temporary audio files
tests/                 # pytest tests with conftest.py for path setup
```

Each task creates its own output directory: `app/output/task_{timestamp}_{uuid}/` containing:
- `temp/`: Transcript JSONs and temporary audio
- `cuts/`: Individual clip segments
- `merged_transcripts.txt`: Combined transcript
- `important_dialogues.txt`: AI analysis results
- `clip_order.txt`: Cut instructions for clip_cutter
- `merged_highlights.mp4`: Final merged video

### Key Dependencies
- `moviepy`: Video editing and cutting
- `fastapi` + `uvicorn`: HTTP API server
- `websockets`: WebSocket server
- `oss2`: Alibaba Cloud OSS SDK
- `aliyun-python-sdk-*`: Alibaba Cloud ASR SDK
- `openai`: DeepSeek API client
- `yt-dlp`: YouTube video download support
