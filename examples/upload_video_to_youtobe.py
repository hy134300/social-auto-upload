import asyncio
from pathlib import Path
from venv import logger

from playwright.async_api import async_playwright

from conf import BASE_DIR
from uploader.tk_uploader.main_chrome import tiktok_setup, TiktokVideo
from uploader.youtube_uploader.youtube_uploader import YouTubeVideoUploader
from utils.files_times import generate_schedule_time_next_day, get_title_and_hashtags

async def post_video_youtobe(
    file_list,
    title=None,
    tags=None,
    enableTimer=False,
    videos_per_day=1,
    daily_times=None,
    start_days=1,
    thumbnail_path=None
):
    base_dir = Path(BASE_DIR)
    video_dir = base_dir / "videoFile" / "tmp"

    normalized_files = []

    for f in file_list:
        f = f.strip()

        # 远程 URL → 只下载前几秒（测试用）
        if f.startswith("http://") or f.startswith("https://"):
            local_file = download_video_preview(
                url=f,
                output_dir=video_dir,
                seconds=5  # 👈 你想测几秒就改这里
            )
            normalized_files.append(local_file)
            continue

        # 已经是绝对路径
        if f.startswith("/"):
            p = Path(f)
        else:
            p = base_dir / "videoFile" / f

        if not p.exists():
            raise FileNotFoundError(f"视频文件不存在：{p}")

        normalized_files.append(p)
    files = normalized_files

    # 4️⃣ 逐个上传（可以后面改成并发）
    for index, file in enumerate(files):
        video_title = title
        video_tags = tags

        # 如果没传标题，走自动生成
        if not title or not tags:
            video_title, video_tags = get_title_and_hashtags(str(file))
        app = YouTubeVideoUploader(
            video_title,
            video_tags,
            file,
            '',
            True
        )
        try:
            async with async_playwright() as playwright:
                 await app.test_open_upload_only(playwright)
        except Exception as e:
            # 单视频失败不影响后续
            logger.exception(f"TikTok upload failed: {file} -> {e}")


def download_video_preview(url: str, output_dir: Path, seconds: int = 5) -> Path:
    import hashlib
    import subprocess

    output_dir.mkdir(parents=True, exist_ok=True)

    url_hash = hashlib.md5(url.encode()).hexdigest()
    output_file = output_dir / f"{url_hash}_test_{seconds}s.mp4"

    if output_file.exists():
        print(f"测试视频已存在，直接使用：{output_file}")
        return output_file

    print(f"下载远程视频前 {seconds} 秒：{url}")

    cmd = [
        "ffmpeg",
        "-y",
        "-nostdin",                 # 🔥 防止卡死
        "-loglevel", "error",       # 可选
        "-i", url,
        "-t", str(seconds),
        "-c", "copy",
        str(output_file)
    ]

    subprocess.run(
        cmd,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE
    )

    return output_file




if __name__ == '__main__':
    filepath = Path(BASE_DIR) / "videos"
    account_file = Path(BASE_DIR / "cookies" / "tk_uploader" / "account.json")
    folder_path = Path(filepath)
    # get video files from folder
    files = list(folder_path.glob("*.mp4"))
    file_num = len(files)
    publish_datetimes = generate_schedule_time_next_day(file_num, 1, daily_times=[16])
    cookie_setup = asyncio.run(tiktok_setup(account_file, handle=True))
    for index, file in enumerate(files):
        title, tags = get_title_and_hashtags(str(file))
        thumbnail_path = file.with_suffix('.png')
        print(f"video_file_name：{file}")
        print(f"video_title：{title}")
        print(f"video_hashtag：{tags}")
        if thumbnail_path.exists():
            print(f"thumbnail_file_name：{thumbnail_path}")
            app = TiktokVideo(title, file, tags, publish_datetimes[index], account_file, thumbnail_path)
        else:
            app = TiktokVideo(title, file, tags, publish_datetimes[index], account_file)
        asyncio.run(app.main(), debug=False)
