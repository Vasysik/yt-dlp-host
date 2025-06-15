import yt_dlp
import os
import json
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
import asyncio

from app.core.config import settings

executor = None

def init_executor():
    global executor
    if executor is None:
        executor = asyncio.ThreadPoolExecutor(max_workers=settings.MAX_WORKERS)

def ensure_download_dir_exists():
    settings.DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

def _get_estimated_size_sync(url_str: str, video_format: Optional[str] = None, audio_format: Optional[str] = None) -> int:
    try:
        ydl_opts_info = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'skip_download': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
            info = ydl.extract_info(url_str, download=False)
        
        estimated_size = 0
        formats = info.get('formats', [])
        
        def get_format_actual_size(f_info_dict: Dict[str, Any]) -> int:
            return f_info_dict.get('filesize') or f_info_dict.get('filesize_approx') or 0
        
        if video_format:
            if video_format.startswith("bestvideo"):
                video_streams = [f for f in formats if f.get('vcodec') != 'none' and f.get('acodec') == 'none']
                if video_streams:
                    best_video_stream = max(video_streams, key=lambda x: (x.get('height', 0), x.get('tbr', 0)))
                    estimated_size += get_format_actual_size(best_video_stream)
            else:
                selected_format = next((f for f in formats if f.get('format_id') == video_format), None)
                if selected_format:
                    estimated_size += get_format_actual_size(selected_format)
        
        if audio_format:
            if audio_format.startswith("bestaudio"):
                audio_streams = [f for f in formats if f.get('acodec') != 'none' and f.get('vcodec') == 'none']
                if audio_streams:
                    best_audio_stream = max(audio_streams, key=lambda x: (x.get('abr', 0), x.get('tbr', 0)))
                    estimated_size += get_format_actual_size(best_audio_stream)
            else:
                selected_format = next((f for f in formats if f.get('format_id') == audio_format), None)
                if selected_format:
                    estimated_size += get_format_actual_size(selected_format)
        
        if estimated_size == 0 and info.get('duration') and info.get('filesize_approx'):
            estimated_size = info['filesize_approx']
        elif estimated_size == 0 and info.get('duration') and info.get('tbr'):
            estimated_size = int(info['duration'] * info['tbr'] * 1024 / 8)

        return int(estimated_size * settings.SIZE_ESTIMATION_BUFFER_FACTOR) if estimated_size > 0 else -1
    except Exception as e:
        print(f"Error in _get_estimated_size_sync for {url_str}: {e}")
        return -1


def _run_yt_dlp_download_sync(
    task_id: str, 
    url_str: str, 
    task_specific_params: Dict[str, Any],
    is_live_task: bool = False
) -> Tuple[Path, int]:
    
    task_download_dir = settings.DOWNLOAD_DIR / task_id
    task_download_dir.mkdir(parents=True, exist_ok=True)

    is_video_download = bool(task_specific_params.get('video_format')) and not task_specific_params.get('audio_only_explicit', False)


    output_template_filename = 'video.%(ext)s' if is_video_download else 'audio.%(ext)s'
    output_template = task_download_dir / output_template_filename

    ydl_opts = {
        'outtmpl': str(output_template),
        'quiet': True,
        'no_warnings': True,
        'noprogress': True,
        # 'verbose': True,
    }

    if is_video_download:
        video_f = task_specific_params.get('video_format', 'bestvideo')
        audio_f = task_specific_params.get('audio_format', 'bestaudio')
        ydl_opts['format'] = f"{video_f}+{audio_f}/bestvideo+bestaudio/best"
        ydl_opts['merge_output_format'] = 'mp4' 
    else:
        ydl_opts['format'] = task_specific_params.get('audio_format', 'bestaudio')
        ydl_opts['extract_audio'] = True
        ydl_opts['audio_format'] = task_specific_params.get('output_audio_container_format', 'best') # 'mp3', 'm4a', 'opus', etc.
        ydl_opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': ydl_opts['audio_format']}]
    
    if not is_live_task and (task_specific_params.get('start_time') or task_specific_params.get('end_time')):
        section_parts = []
        if task_specific_params.get('start_time'):
            section_parts.append(task_specific_params['start_time'])
        
        start_s = task_specific_params.get('start_time')
        end_s = task_specific_params.get('end_time')
        
        if start_s and end_s:
            ydl_opts['download_sections'] = f"*{start_s}-{end_s}"
        elif start_s:
            ydl_opts['download_sections'] = f"*{start_s}-"
        elif end_s:
            ydl_opts['download_sections'] = f"*-{end_s}" 
            if end_s and not start_s: ydl_opts['download_sections'] = f"*0:0:0-{end_s}"
        
        if task_specific_params.get('force_keyframes', False) and ydl_opts.get('download_sections'):
            ydl_opts['force_keyframes_at_cuts'] = True
        
    if is_live_task:
        ydl_opts['live_from_start'] = True
        # ydl_opts['wait_for_video'] = (5, 30) # (min_tries, max_tries) for waiting
        # ydl_opts['no_resume'] = True
        print(f"Warning: Live recording for task {task_id} will attempt to capture current live stream. Precise start/duration control is limited.")

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url_str])
        
        downloaded_file_path = None
        highest_mtime = 0
        
        for f_path_obj in task_download_dir.iterdir():
            if f_path_obj.is_file():
                current_mtime = f_path_obj.stat().st_mtime
                is_correct_type = False
                if is_video_download and f_path_obj.suffix.lower() in ['.mp4', '.mkv', '.webm', '.ts']:
                    is_correct_type = True
                elif not is_video_download and f_path_obj.suffix.lower() in ['.mp3', '.m4a', '.ogg', '.opus', '.wav', '.aac']:
                    is_correct_type = True
                
                if is_correct_type and (downloaded_file_path is None or current_mtime > highest_mtime):
                    downloaded_file_path = f_path_obj
                    highest_mtime = current_mtime
        
        if not downloaded_file_path:
            raise FileNotFoundError(f"yt-dlp finished for task {task_id} but no suitable output file was found in {task_download_dir}.")
            
        file_size = downloaded_file_path.stat().st_size
        return downloaded_file_path, file_size

    except yt_dlp.utils.DownloadError as e:
        raise RuntimeError(f"yt-dlp download error for task {task_id}: {str(e)}") from e
    except Exception as e:
        raise RuntimeError(f"Generic error during yt-dlp download for task {task_id}: {e}") from e


def _run_yt_dlp_get_info_sync(task_id: str, url_str: str) -> Tuple[Path, Dict[str, Any]]:
    task_download_dir = settings.DOWNLOAD_DIR / task_id
    task_download_dir.mkdir(parents=True, exist_ok=True)
    info_file_path_obj = task_download_dir / "info.json"

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'writeinfojson': False,
        'extract_flat': False,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url_str, download=False)
        
        with open(info_file_path_obj, 'w', encoding='utf-8') as f:
            json.dump(info_dict, f, indent=2)
            
        return info_file_path_obj, info_dict
    
    except yt_dlp.utils.DownloadError as e:
        raise RuntimeError(f"yt-dlp info extraction error for task {task_id}: {str(e)}") from e
    except Exception as e:
        raise RuntimeError(f"Generic error during yt-dlp info extraction for task {task_id}: {e}") from e

def _cleanup_task_files_sync(task_id: str):
    task_dir = settings.DOWNLOAD_DIR / task_id
    if task_dir.exists() and task_dir.is_dir():
        try:
            shutil.rmtree(task_dir)
            print(f"Cleaned up files for task {task_id} in directory {task_dir}")
        except Exception as e:
            print(f"Error cleaning up files for task {task_id} in {task_dir}: {e}")
    # else:
    #     print(f"Directory for task {task_id} not found for cleanup: {task_dir}")

async def run_download_task(task_id: str, url_str: str, task_specific_params: Dict[str, Any], is_live: bool) -> Tuple[Path, int]:
    if executor is None: init_executor()
    return await asyncio.to_thread(
        _run_yt_dlp_download_sync, task_id, url_str, task_specific_params, is_live
    )

async def run_getinfo_task(task_id: str, url_str: str) -> Tuple[Path, Dict[str, Any]]:
    if executor is None: init_executor()
    return await asyncio.to_thread(_run_yt_dlp_get_info_sync, task_id, url_str)

async def get_estimated_size(url_str: str, video_format: Optional[str] = None, audio_format: Optional[str] = None) -> int:
    if executor is None: init_executor()
    return await asyncio.to_thread(_get_estimated_size_sync, url_str, video_format, audio_format)

async def cleanup_task_files(task_id: str):
    if executor is None: init_executor()
    await asyncio.to_thread(_cleanup_task_files_sync, task_id)
