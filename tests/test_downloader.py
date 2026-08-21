from pathlib import Path

from yt_dlp_host.downloader import DownloadEngine


def test_time_parser():
    assert DownloadEngine._time_to_seconds("01:02:03") == 3723
    assert DownloadEngine._time_to_seconds("02:03") == 123
    assert DownloadEngine._time_to_seconds(15) == 15


def test_final_file_selection_ignores_part(tmp_path: Path):
    final = tmp_path / "video.mp4"
    final.write_bytes(b"1234")
    (tmp_path / "video.part").write_bytes(b"123456")
    assert DownloadEngine._find_final_file(tmp_path, []) == final
