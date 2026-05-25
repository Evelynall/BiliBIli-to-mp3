#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
B站视频下载转MP3工具
功能：批量下载B站视频，转换为MP3音频，下载封面并嵌入MP3元数据
"""

import os
import sys
import json
import threading
import queue
import subprocess
import shutil
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

# ─── 依赖检查 ───────────────────────────────────────────────
REQUIRED_MODULES = {
    "yt_dlp": "yt-dlp",
    "mutagen": "mutagen",
}

missing = []
for module, package in REQUIRED_MODULES.items():
    try:
        __import__(module)
    except ImportError:
        missing.append(package)

if missing:
    print(f"[!] 缺少依赖: {', '.join(missing)}")
    print(f"[*] 正在自动安装...")
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "--user", *missing, "-i", "https://pypi.tuna.tsinghua.edu.cn/simple"]
    )
    print("[✓] 依赖安装完成，正在启动程序...\n")
    # 重新启动以加载新安装的模块
    os.execv(sys.executable, [sys.executable] + sys.argv)

import yt_dlp
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, TIT2, TPE1, ID3NoHeaderError


# ─── ffmpeg 检查 ────────────────────────────────────────────
def check_ffmpeg():
    """检查 ffmpeg 是否可用"""
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            check=True,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


# ─── BBDown 检查 ────────────────────────────────────────────
def check_bbdown():
    """检查 BBDown 是否可用"""
    return get_bbdown_path() is not None

def get_bbdown_path():
    """获取可用的 BBDown 路径，优先使用 BBDown-go.exe，其次是 BBDown.exe"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 优先检查 BBDown-go.exe
    bbdown_go_path = os.path.join(script_dir, "BBDown-go.exe")
    if os.path.exists(bbdown_go_path):
        try:
            result = subprocess.run(
                [bbdown_go_path, "--help"],
                capture_output=True,
                text=True,
                encoding='utf-8',
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            if result.returncode == 0:
                return bbdown_go_path, "go"
        except Exception as e:
            print(f"[DEBUG] BBDown-go.exe 检测失败: {type(e).__name__}: {e}")
    
    # 检查 BBDown.exe
    bbdown_path = os.path.join(script_dir, "BBDown.exe")
    if os.path.exists(bbdown_path):
        try:
            result = subprocess.run(
                [bbdown_path, "--help"],
                capture_output=True,
                text=True,
                encoding='utf-8',
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            if result.returncode == 0:
                return bbdown_path, "original"
        except Exception as e:
            print(f"[DEBUG] BBDown.exe 检测失败: {type(e).__name__}: {e}")
    
    # 检查系统 PATH 中的 BBDown
    try:
        result = subprocess.run(
            ["BBDown", "--help"],
            capture_output=True,
            text=True,
            encoding='utf-8',
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        if result.returncode == 0:
            return "BBDown", "original"
    except Exception as e:
        pass
    
    return None, None


# ─── 下载与转换核心逻辑 ────────────────────────────────────
class BiliDownloader:
    def __init__(self):
        self.temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_temp_download")
        os.makedirs(self.temp_dir, exist_ok=True)
        self.stop_requested = False
        self.bbdown_path, self.bbdown_type = get_bbdown_path()
        self.bbdown_available = self.bbdown_path is not None

    def get_video_info(self, url, stop_callback=None):
        """获取视频信息（标题、封面URL等）"""
        if stop_callback is None:
            stop_callback = lambda: False
            
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "socket_timeout": 30,
            "retries": 3,
            "fragment_retries": 3,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if stop_callback():
                raise RuntimeError("用户停止")
            return {
                "title": info.get("title", "未知标题"),
                "thumbnail": info.get("thumbnail", ""),
                "uploader": info.get("uploader", ""),
                "duration": info.get("duration", 0),
            }

    def download_and_convert_with_bbdown(self, url, output_dir, filename=None, artist="", title="",
                                         select_page="", progress_callback=None, log_callback=None, stop_callback=None):
        """使用 BBDown 下载音频、封面，并转换为 MP3"""
        if log_callback is None:
            log_callback = lambda x: None
        if progress_callback is None:
            progress_callback = lambda x: None
        if stop_callback is None:
            stop_callback = lambda: False

        log_callback("正在使用 BBDown 下载...")
        progress_callback("使用 BBDown 下载中...")

        # 创建临时目录并清理旧文件
        temp_work_dir = os.path.join(self.temp_dir, "bbdown_temp")
        if os.path.exists(temp_work_dir):
            shutil.rmtree(temp_work_dir)
        os.makedirs(temp_work_dir, exist_ok=True)

        # 确定 BBDown 路径和类型
        if not self.bbdown_available:
            raise RuntimeError("BBDown 不可用")
        bbdown_cmd = self.bbdown_path
        
        log_callback(f"使用 BBDown: {bbdown_cmd} (类型: {self.bbdown_type})")

        # 查找 ffmpeg 路径
        ffmpeg_path = "ffmpeg"
        try:
            result = subprocess.run(
                ["where", "ffmpeg"],
                capture_output=True,
                text=True,
                encoding='utf-8',
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            if result.returncode == 0 and result.stdout.strip():
                ffmpeg_path = result.stdout.strip().split("\n")[0].strip()
        except:
            pass
        
        log_callback(f"使用 ffmpeg: {ffmpeg_path}")

        # 获取视频信息（BBDown-go 使用 --only-show-info，原版使用 --show-all）
        log_callback("获取视频信息...")
        log_callback(f"[DEBUG] BBDown类型: {self.bbdown_type}")
        video_title = ""
        try:
            info_args = [
                bbdown_cmd,
                url,
                "--only-show-info" if self.bbdown_type == "go" else "--show-all",
                "--work-dir", temp_work_dir,
            ]
            
            log_callback(f"[DEBUG] 执行命令: {' '.join(info_args)}")
            
            info_process = subprocess.run(
                info_args,
                capture_output=True,
                text=True,
                encoding='utf-8',
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                cwd=temp_work_dir,
                timeout=30,
            )
            
            log_callback(f"[DEBUG] 命令返回码: {info_process.returncode}")
            log_callback(f"[DEBUG] stdout 长度: {len(info_process.stdout)} 字符")
            log_callback(f"[DEBUG] stderr 长度: {len(info_process.stderr)} 字符")
            
            # BBDown-go 可能将日志输出到 stderr，合并两者
            combined_output = info_process.stdout + info_process.stderr
            
            # 输出前5行用于调试
            output_lines = combined_output.splitlines()[:5]
            if output_lines:
                log_callback(f"[DEBUG] 合并输出前5行:")
                for i, line in enumerate(output_lines):
                    log_callback(f"[DEBUG]  Line {i+1}: {repr(line)}")
            
            # 从输出中提取视频标题
            found_video_title_line = False
            for line in combined_output.splitlines():
                if "视频标题" in line:
                    found_video_title_line = True
                    log_callback(f"[DEBUG] 找到包含'视频标题'的行: {repr(line)}")
                    import re
                    # BBDown-go 格式: msg="视频标题: xxx"
                    # 原版 BBDown 格式: 视频标题: xxx
                    if self.bbdown_type == "go":
                        # 匹配 msg="视频标题: xxx" 中的 xxx，去除首尾引号
                        pattern = r'msg="[^"]*视频标题[：:]\s*([^"]+)"'
                        match = re.search(pattern, line)
                        log_callback(f"[DEBUG] 使用正则: {pattern}")
                    else:
                        pattern = r'视频标题[：:]\s*(.*)'
                        match = re.search(pattern, line)
                        log_callback(f"[DEBUG] 使用正则: {pattern}")
                    
                    if match:
                        video_title = match.group(1).replace('\n', '').replace('\r', '').strip()
                        log_callback(f"[DEBUG] 正则匹配成功，提取标题: {repr(video_title)}")
                        log_callback(f"视频标题: {video_title}")
                        break
                    else:
                        log_callback(f"[DEBUG] 正则匹配失败，该行无法解析")
            
            if not found_video_title_line:
                log_callback(f"[DEBUG] 未找到包含'视频标题'的行")
                log_callback(f"[DEBUG] 搜索所有行中是否有相关内容...")
                for line in combined_output.splitlines()[:20]:
                    if any(keyword in line for keyword in ["title", "Title", "标题", "TITLE"]):
                        log_callback(f"[DEBUG] 可能相关的行: {repr(line)}")
                        
        except Exception as e:
            log_callback(f"获取视频信息失败: {e}")
            import traceback
            log_callback(f"[DEBUG] 异常详情: {traceback.format_exc()}")

        # 确定文件名
        if not filename and video_title:
            filename = self._sanitize_filename(video_title)
        elif not filename:
            # 从URL提取视频ID作为临时文件名
            import re
            match = re.search(r'(BV[\w]+)|(av\d+)', url)
            if match:
                filename = match.group(1) or match.group(2)
            else:
                filename = "video"
        log_callback(f"使用文件名: {filename}")

        try:
            # 1. 使用 BBDown 下载音频
            args = [
                bbdown_cmd,
                url,
                "--audio-only",
                "--work-dir", temp_work_dir,
                "--ffmpeg-path", ffmpeg_path,
            ]
            
            # 添加分P参数
            if select_page:
                args.append("-p")
                args.append(select_page)
                log_callback(f"指定分P: {select_page}")

            log_callback(f"启动 BBDown 进程下载音频...")
            process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                bufsize=1,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                cwd=temp_work_dir,
            )
            
            log_callback(f"BBDown PID: {process.pid}")

            # 使用线程读取输出，避免阻塞
            output_lines = []
            stop_reading = threading.Event()
            
            def read_output():
                """在后台线程中读取输出"""
                while not stop_reading.is_set():
                    try:
                        line = process.stdout.readline()
                        if line:
                            output_lines.append(line)
                            log_callback(line.strip())
                        elif process.poll() is not None:
                            break
                    except:
                        break
            
            # 启动读取线程
            reader_thread = threading.Thread(target=read_output, daemon=True)
            reader_thread.start()
            
            # 主循环等待进程结束
            while True:
                if stop_callback():
                    stop_reading.set()
                    process.terminate()
                    reader_thread.join(timeout=2)
                    raise RuntimeError("用户停止")
                
                # 检查进程是否结束
                returncode = process.poll()
                if returncode is not None:
                    # 进程已结束，等待读取线程完成
                    stop_reading.set()
                    reader_thread.join(timeout=5)
                    break
                
                # 短暂休眠，避免CPU占用过高
                threading.Event().wait(0.1)

            log_callback(f"BBDown 音频下载结束，返回码: {returncode}")

            if returncode is not None and returncode != 0:
                raise RuntimeError(f"BBDown 音频下载失败，返回码: {returncode}")

            # 2. 使用 BBDown 下载封面
            log_callback(f"启动 BBDown 进程下载封面...")
            cover_args = [
                bbdown_cmd,
                url,
                "--cover-only",
                "--work-dir", temp_work_dir,
            ]
            
            cover_process = subprocess.run(
                cover_args,
                capture_output=True,
                text=True,
                encoding='utf-8',
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                cwd=temp_work_dir,
                timeout=30,
            )
            
            if cover_process.returncode == 0:
                log_callback(f"封面下载成功")
            else:
                log_callback(f"封面下载失败，返回码: {cover_process.returncode}")

            # 查找下载的音频文件（BBDown 可能在子目录中创建文件，可能是mp4容器）
            audio_file = None
            
            # 递归查找 temp_work_dir 下所有子目录中的音频文件
            log_callback(f"在 {temp_work_dir} 及其子目录中查找音频文件...")
            all_files = list(Path(temp_work_dir).rglob("*"))
            
            # 按文件大小排序，最大的通常是主要音频
            audio_files = sorted(
                [f for f in all_files if f.is_file() and f.suffix in [".m4a", ".mp3", ".aac", ".flac", ".wav", ".mp4"]],
                key=lambda x: x.stat().st_size,
                reverse=True
            )
            
            if audio_files:
                audio_file = audio_files[0]
                log_callback(f"找到 {len(audio_files)} 个文件，选择最大的: {audio_file}")
            else:
                log_callback(f"未在 {temp_work_dir} 找到音频文件")
                raise RuntimeError("未找到 BBDown 下载的音频文件")

            # 查找封面文件
            cover_file = None
            cover_files = sorted(
                [f for f in all_files if f.is_file() and f.suffix in [".jpg", ".jpeg", ".png"]],
                key=lambda x: x.stat().st_size,
                reverse=True
            )
            
            if cover_files:
                cover_file = cover_files[0]
                log_callback(f"找到封面文件: {cover_file}")

            # 如果下载的不是 MP3，转换为 MP3
            mp3_path = os.path.join(output_dir, f"{filename}.mp3")
            if audio_file.suffix != ".mp3":
                log_callback("正在转换为 MP3...")
                progress_callback("转换中...")
                ffmpeg_args = [
                    "ffmpeg",
                    "-i", str(audio_file),
                    "-codec:a", "libmp3lame",
                    "-b:a", "192k",
                    "-y",
                    mp3_path,
                ]
                subprocess.run(
                    ffmpeg_args,
                    capture_output=True,
                    check=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                )
            else:
                # 直接移动文件
                shutil.move(str(audio_file), mp3_path)

            # 移动封面文件
            cover_path = None
            if cover_file:
                cover_path = os.path.join(output_dir, f"{filename}{cover_file.suffix}")
                shutil.move(str(cover_file), cover_path)
                log_callback(f"封面已保存: {os.path.basename(cover_path)}")

            # 确定元数据
            if not title and video_title:
                title = video_title
            if not artist:
                # 尝试从输出中提取UP主信息
                for line in output_lines:
                    if "UP主" in line or "uploader" in line.lower():
                        import re
                        match = re.search(r'UP主[：:]\s*(.*)', line)
                        if match:
                            artist = match.group(1).strip()
                            break

            # 写入 MP3 元数据
            log_callback("正在写入元数据...")
            self._write_mp3_metadata(mp3_path, title, artist, cover_path)

            log_callback("✓ 完成!")
            progress_callback("完成")

            return mp3_path, cover_path

        finally:
            # 清理临时目录
            self._cleanup_temp()

    def download_and_convert(self, url, output_dir, filename=None, artist="", title="",
                              select_page="", progress_callback=None, log_callback=None, stop_callback=None):
        """
        下载视频并转换为MP3（优先使用 BBDown）
        返回: (mp3_path, cover_path) 或抛出异常
        """
        if log_callback is None:
            log_callback = lambda x: None
        if progress_callback is None:
            progress_callback = lambda x: None
        if stop_callback is None:
            stop_callback = lambda: False

        # 优先尝试使用 BBDown
        if self.bbdown_available:
            try:
                return self.download_and_convert_with_bbdown(
                    url, output_dir, filename=filename, artist=artist, title=title,
                    select_page=select_page,
                    progress_callback=progress_callback, log_callback=log_callback,
                    stop_callback=stop_callback
                )
            except Exception as e:
                log_callback(f"BBDown 下载失败: {e}，将尝试使用 yt-dlp")

        # 回退到 yt-dlp
        return self.download_and_convert_with_yt_dlp(
            url, output_dir, filename=filename, artist=artist, title=title,
            progress_callback=progress_callback, log_callback=log_callback,
            stop_callback=stop_callback
        )

    def download_and_convert_with_yt_dlp(self, url, output_dir, filename=None, artist="", title="",
                                         progress_callback=None, log_callback=None, stop_callback=None):
        """使用 yt-dlp 下载视频并转换为MP3"""
        if log_callback is None:
            log_callback = lambda x: None
        if progress_callback is None:
            progress_callback = lambda x: None
        if stop_callback is None:
            stop_callback = lambda: False

        # 获取视频信息
        log_callback("正在使用 yt-dlp 获取视频信息...")
        info = self.get_video_info(url, stop_callback=stop_callback)
        video_title = info["title"]
        cover_url = info["thumbnail"]

        # 确定文件名
        if not filename:
            filename = self._sanitize_filename(video_title)

        # 确定元数据
        meta_title = title if title else video_title
        meta_artist = artist if artist else info.get("uploader", "")

        mp3_filename = f"{filename}.mp3"
        cover_filename = f"{filename}.jpg"
        mp3_path = os.path.join(output_dir, mp3_filename)
        cover_path = os.path.join(output_dir, cover_filename)

        # yt-dlp 下载选项
        temp_output = os.path.join(self.temp_dir, "%(id)s.%(ext)s")

        def progress_hook(d):
            if stop_callback():
                raise RuntimeError("用户停止")
            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
                downloaded = d.get("downloaded_bytes", 0)
                if total > 0:
                    pct = int(downloaded / total * 100)
                    progress_callback(f"下载中... {pct}%")
            elif d["status"] == "finished":
                progress_callback("下载完成，正在转换...")
            elif d["status"] == "processing":
                progress_callback("正在处理音频...")

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": temp_output,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
            "progress_hooks": [progress_hook],
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "socket_timeout": 30,
            "retries": 3,
            "fragment_retries": 3,
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://www.bilibili.com",
            },
        }

        log_callback(f"开始下载: {video_title}")

        # 下载并转换
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        # 找到下载的文件（yt-dlp 会生成 .mp3）
        downloaded_files = list(Path(self.temp_dir).glob("*"))
        mp3_temp = None
        for f in downloaded_files:
            if f.suffix == ".mp3":
                mp3_temp = str(f)
                break

        if not mp3_temp:
            # 可能还是其他格式，找最大的音频文件
            audio_files = [f for f in downloaded_files if f.suffix in (".mp3", ".m4a", ".webm", ".opus")]
            if audio_files:
                mp3_temp = str(max(audio_files, key=lambda f: f.stat().st_size))
            else:
                raise RuntimeError("未找到下载的音频文件")

        # 移动 MP3 到目标目录
        shutil.move(mp3_temp, mp3_path)
        log_callback(f"MP3 已保存: {mp3_filename}")

        # 下载封面
        if cover_url:
            log_callback("正在下载封面...")
            try:
                import urllib.request
                req = urllib.request.Request(
                    cover_url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                        "Referer": "https://www.bilibili.com",
                    },
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    with open(cover_path, "wb") as f:
                        f.write(resp.read())
                log_callback(f"封面已保存: {cover_filename}")
            except Exception as e:
                log_callback(f"封面下载失败: {e}")
                cover_path = None

        # 写入 MP3 元数据
        log_callback("正在写入元数据...")
        self._write_mp3_metadata(mp3_path, meta_title, meta_artist, cover_path)

        # 清理临时目录
        self._cleanup_temp()

        log_callback("✓ 完成!")
        progress_callback("完成")

        return mp3_path, cover_path

    def _write_mp3_metadata(self, mp3_path, title, artist, cover_path=None):
        """写入 MP3 元数据（标题、艺术家、封面），并清除所有其他元数据"""
        try:
            # 尝试加载已有的 ID3 标签
            try:
                tags = ID3(mp3_path)
            except ID3NoHeaderError:
                tags = ID3()

            # 清除所有原有标签（只保留我们要设置的）
            # 获取所有现有的标签键
            existing_keys = list(tags.keys())
            for key in existing_keys:
                tags.delall(key)

            # 添加标题
            tags.add(TIT2(encoding=3, text=title))
            # 添加艺术家
            tags.add(TPE1(encoding=3, text=artist))

            # 添加封面
            if cover_path and os.path.exists(cover_path):
                with open(cover_path, "rb") as f:
                    cover_data = f.read()
                tags.add(
                    APIC(
                        encoding=3,
                        mime="image/jpeg",
                        type=3,  # Cover (front)
                        desc="Cover",
                        data=cover_data,
                    )
                )

            tags.save(mp3_path, v2_version=3)
        except Exception as e:
            print(f"[!] 元数据写入失败: {e}")

    def _sanitize_filename(self, name):
        """清理文件名中的非法字符"""
        if not name:
            return "video"
        name = name.replace('\n', '').replace('\r', '')
        invalid_chars = r'<>:"/\|?*'
        for ch in invalid_chars:
            name = name.replace(ch, "_")
        name = name.strip()
        return name if name else "video"

    def _cleanup_temp(self):
        """清理临时下载目录"""
        try:
            for f in Path(self.temp_dir).glob("*"):
                f.unlink()
        except Exception:
            pass


# ─── GUI 界面 ───────────────────────────────────────────────
class Application(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("B站视频下载转MP3工具")
        self.geometry("960x700")
        self.minsize(800, 600)

        # 配置样式
        self.style = ttk.Style(self)
        self.style.theme_use("clam")

        # 配色
        self.bg_color = "#f0f0f0"
        self.accent_color = "#fb7299"  # B站粉色
        self.configure(bg=self.bg_color)

        self.style.configure("Title.TLabel", font=("Microsoft YaHei UI", 16, "bold"),
                             foreground=self.accent_color, background=self.bg_color)
        self.style.configure("Header.TLabel", font=("Microsoft YaHei UI", 10, "bold"),
                             background=self.bg_color)
        self.style.configure("TButton", font=("Microsoft YaHei UI", 9))
        self.style.configure("Accent.TButton", font=("Microsoft YaHei UI", 10, "bold"),
                             foreground="white", background=self.accent_color)
        self.style.map("Accent.TButton",
                       background=[("active", "#e85d85"), ("pressed", "#d94d75")])
        self.style.configure("Status.TLabel", font=("Microsoft YaHei UI", 9),
                             foreground="#666666", background=self.bg_color)
        self.style.configure("Treeview", font=("Microsoft YaHei UI", 9), rowheight=28)
        self.style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 9, "bold"))

        self.downloader = BiliDownloader()
        self.task_queue = queue.Queue()
        self.is_processing = False

        # 配置文件路径（程序同目录下）
        self.config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
        # 默认下载路径：程序同目录下的 download 文件夹
        self.default_output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "download")
        # 关键词匹配配置
        self.keyword_matches = []  # [{"keyword": "", "artist": ""}, ...]
        self.auto_extract_booktitle = True  # 是否自动提取书名号内容作为标题
        self.video_info_cache = {}  # 缓存视频信息

        self._build_ui()
        self._load_config()
        self._check_environment()

    def _open_metadata_editor(self):
        """打开 MP3 元数据编辑器"""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        editor_path = os.path.join(script_dir, "mp3_metadata_editor.py")

        if not os.path.exists(editor_path):
            messagebox.showerror("错误", f"未找到 MP3 元数据编辑器: {editor_path}")
            return

        try:
            subprocess.Popen(
                [sys.executable, editor_path],
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )
        except Exception as e:
            messagebox.showerror("错误", f"启动失败: {e}")

    def _check_environment(self):
        # 检查 BBDown
        script_dir = os.path.dirname(os.path.abspath(__file__))
        bbdown_go_path = os.path.join(script_dir, "BBDown-go.exe")
        bbdown_path = os.path.join(script_dir, "BBDown.exe")
        
        self.log_text.configure(state=tk.NORMAL)
        
        if os.path.exists(bbdown_go_path):
            self.log_text.insert(tk.END, f"[✓] 找到 BBDown-go.exe: {bbdown_go_path}\n")
        if os.path.exists(bbdown_path):
            self.log_text.insert(tk.END, f"[✓] 找到 BBDown.exe: {bbdown_path}\n")
        
        if self.downloader.bbdown_available:
            bbdown_type = "BBDown-go" if self.downloader.bbdown_type == "go" else "BBDown"
            self.log_text.insert(tk.END, f"[✓] {bbdown_type} 检测成功，将优先使用 {bbdown_type} 下载。\n")
        else:
            self.log_text.insert(tk.END, "[!] 未检测到可用的 BBDown，将使用 yt-dlp 下载。\n")
            self.log_text.insert(tk.END, "[!] 如需使用 BBDown，请下载 BBDown-go.exe 或 BBDown.exe 并放置在程序目录中。\n")
            self.log_text.insert(tk.END, "[!] BBDown-go: https://github.com/nilaoda/BBDown-go\n")
            self.log_text.insert(tk.END, "[!] BBDown: https://github.com/nilaoda/BBDown\n")
        
        if not check_ffmpeg():
            self.log_text.insert(tk.END, "[!] 警告: 未检测到 ffmpeg，音频转换将无法进行。\n")
            self.log_text.insert(tk.END, "[!] 请安装 ffmpeg 并确保其在系统 PATH 中。\n")
            self.log_text.insert(tk.END, "[!] 下载地址: https://ffmpeg.org/download.html\n\n")

            messagebox.showwarning(
                "缺少 ffmpeg",
                "未检测到 ffmpeg！\n\n"
                "音频转换需要 ffmpeg。\n"
                "请安装 ffmpeg 并确保其在系统 PATH 中。\n\n"
                "下载地址: https://ffmpeg.org/download.html",
            )
        
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _build_ui(self):
        """构建界面"""
        # ── 顶部标题栏 ──
        title_frame = ttk.Frame(self)
        title_frame.pack(fill=tk.X, padx=15, pady=(10, 5))
        ttk.Label(title_frame, text="🎵 B站视频下载转MP3工具", style="Title.TLabel").pack(side=tk.LEFT)
        ttk.Button(title_frame, text="🎵 MP3编辑器", command=self._open_metadata_editor).pack(side=tk.RIGHT, padx=(5, 0))

        # ── 输出目录选择 ──
        dir_frame = ttk.Frame(self)
        dir_frame.pack(fill=tk.X, padx=15, pady=5)

        ttk.Label(dir_frame, text="保存目录:", style="Header.TLabel").pack(side=tk.LEFT)
        self.dir_var = tk.StringVar(value=self.default_output_dir)
        self.dir_entry = ttk.Entry(dir_frame, textvariable=self.dir_var, width=70)
        self.dir_entry.pack(side=tk.LEFT, padx=(5, 5), fill=tk.X, expand=True)
        ttk.Button(dir_frame, text="浏览...", command=self._select_dir).pack(side=tk.LEFT)

        # ── 任务列表区域 ──
        list_frame = ttk.LabelFrame(self, text=" 下载任务列表 ", padding=10)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)

        # 按钮栏
        btn_frame = ttk.Frame(list_frame)
        btn_frame.pack(fill=tk.X, pady=(0, 5))

        ttk.Button(btn_frame, text="➕ 添加链接", command=self._add_task).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="➖ 删除选中", command=self._remove_task).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="🗑 清空列表", command=self._clear_tasks).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="📋 粘贴链接", command=self._paste_links).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="⚙ 设置", command=self._open_settings).pack(side=tk.LEFT, padx=2)

        # Treeview 容器（用独立 Frame 避免与外层 pack 冲突）
        tree_container = ttk.Frame(list_frame)
        tree_container.pack(fill=tk.BOTH, expand=True)

        # Treeview
        columns = ("status", "url", "select_page", "artist", "title", "filename")
        self.tree = ttk.Treeview(tree_container, columns=columns, show="headings", selectmode="extended")

        self.tree.heading("status", text="状态")
        self.tree.heading("url", text="B站链接")
        self.tree.heading("select_page", text="分P (如: 1,3-5)")
        self.tree.heading("artist", text="艺术家 (元数据)")
        self.tree.heading("title", text="标题 (元数据)")
        self.tree.heading("filename", text="文件名")

        self.tree.column("status", width=70, minwidth=60, anchor=tk.CENTER)
        self.tree.column("url", width=280, minwidth=150)
        self.tree.column("select_page", width=100, minwidth=60, anchor=tk.CENTER)
        self.tree.column("artist", width=130, minwidth=80)
        self.tree.column("title", width=180, minwidth=100)
        self.tree.column("filename", width=180, minwidth=100)

        # 滚动条
        scrollbar_y = ttk.Scrollbar(tree_container, orient=tk.VERTICAL, command=self.tree.yview)
        scrollbar_x = ttk.Scrollbar(tree_container, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar_y.grid(row=0, column=1, sticky="ns")
        scrollbar_x.grid(row=1, column=0, sticky="ew")

        tree_container.grid_rowconfigure(0, weight=1)
        tree_container.grid_columnconfigure(0, weight=1)

        # 双击编辑
        self.tree.bind("<Double-1>", self._on_double_click)

        # ── 操作按钮 ──
        action_frame = ttk.Frame(self)
        action_frame.pack(fill=tk.X, padx=15, pady=5)

        self.start_btn = ttk.Button(action_frame, text="▶ 开始下载", style="Accent.TButton",
                                    command=self._start_download)
        self.start_btn.pack(side=tk.LEFT, padx=5)

        self.stop_btn = ttk.Button(action_frame, text="⏹ 停止", command=self._stop_download,
                                   state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)

        self.progress_var = tk.StringVar(value="就绪")
        ttk.Label(action_frame, textvariable=self.progress_var, style="Status.TLabel").pack(
            side=tk.RIGHT, padx=10)

        # 进度条
        self.progress_bar = ttk.Progressbar(action_frame, mode="determinate", length=200)
        self.progress_bar.pack(side=tk.RIGHT, padx=5)

        # ── 日志区域 ──
        log_frame = ttk.LabelFrame(self, text=" 运行日志 ", padding=5)
        log_frame.pack(fill=tk.X, padx=15, pady=(5, 10))

        self.log_text = tk.Text(log_frame, height=6, font=("Consolas", 9),
                                bg="#1e1e1e", fg="#d4d4d4", insertbackground="white",
                                wrap=tk.WORD, state=tk.DISABLED)
        log_scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scrollbar.set)

        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    # ── 目录选择 ──
    def _select_dir(self):
        dir_path = filedialog.askdirectory(initialdir=self.dir_var.get())
        if dir_path:
            self.dir_var.set(dir_path)
            self._save_config()

    # ── 配置管理 ──
    def _load_config(self):
        """从配置文件加载保存目录和关键词匹配"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                saved_dir = config.get("output_dir", "")
                if saved_dir and os.path.isdir(saved_dir):
                    self.dir_var.set(saved_dir)
                self.keyword_matches = config.get("keyword_matches", [])
                self.auto_extract_booktitle = config.get("auto_extract_booktitle", True)
                return
        except Exception:
            pass
        # 无配置或无效时使用默认路径
        self.dir_var.set(self.default_output_dir)
        self.keyword_matches = []
        self.auto_extract_booktitle = True

    def _save_config(self):
        """保存当前目录和关键词匹配到配置文件"""
        try:
            config = {
                "output_dir": self.dir_var.get(),
                "keyword_matches": self.keyword_matches,
                "auto_extract_booktitle": self.auto_extract_booktitle
            }
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"保存配置失败: {e}")
            return False

    # ── 任务管理 ──
    def _remove_task(self):
        """删除选中的任务"""
        selected = self.tree.selection()
        if not selected:
            return
        for item in selected:
            self.tree.delete(item)

    def _clear_tasks(self):
        """清空所有任务"""
        if self.tree.get_children():
            if messagebox.askyesno("确认", "确定要清空所有任务吗？"):
                self.tree.delete(*self.tree.get_children())

    def _on_double_click(self, event):
        """双击编辑单元格"""
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return

        column = self.tree.identify_column(event.x)
        item = self.tree.identify_row(event.y)
        if not item:
            return

        # 获取列索引
        col_idx = int(column.replace("#", "")) - 1
        col_names = ["status", "url", "select_page", "artist", "title", "filename"]

        # 状态列不可编辑
        if col_idx == 0:
            return

        col_name = col_names[col_idx]
        current_value = self.tree.set(item, col_name)

        # 弹出编辑对话框
        labels = {
            "url": "B站链接",
            "select_page": "分P（如: 1,3-5，留空则下载全部）",
            "artist": "艺术家（写入MP3元数据）",
            "title": "标题（写入MP3元数据）",
            "filename": "文件名（不含扩展名，留空则使用视频标题）",
        }

        new_value = self._simple_input_dialog(
            f"编辑 - {labels[col_name]}",
            labels[col_name] + ":",
            default=current_value,
        )

        if new_value is not None:
            self.tree.set(item, col_name, new_value)

    def _simple_input_dialog(self, title, prompt, default=""):
        """简单的输入对话框"""
        dialog = tk.Toplevel(self)
        dialog.title(title)
        dialog.geometry("500x150")
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)

        # 居中
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 500) // 2
        y = self.winfo_y() + (self.winfo_height() - 150) // 2
        dialog.geometry(f"+{x}+{y}")

        result = {"value": None}

        ttk.Label(dialog, text=prompt, wraplength=460).pack(padx=15, pady=(15, 5), anchor=tk.W)

        entry = ttk.Entry(dialog, width=60)
        entry.pack(padx=15, pady=5, fill=tk.X)
        entry.insert(0, default)
        entry.select_range(0, tk.END)
        entry.focus_set()

        def confirm(event=None):
            result["value"] = entry.get().strip()
            dialog.destroy()

        def cancel():
            dialog.destroy()

        entry.bind("<Return>", confirm)
        entry.bind("<Escape>", cancel)

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="确定", command=confirm).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="取消", command=cancel).pack(side=tk.LEFT, padx=5)

        dialog.wait_window()
        return result["value"]

    # ── 日志 ──
    def _log(self, message):
        """添加日志"""
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    # ── 下载控制 ──
    def _start_download(self):
        """开始下载所有任务"""
        tasks = self.tree.get_children()
        if not tasks:
            messagebox.showinfo("提示", "请先添加下载任务")
            return

        output_dir = self.dir_var.get()
        if not output_dir:
            messagebox.showwarning("警告", "请选择保存目录")
            return

        os.makedirs(output_dir, exist_ok=True)

        self.is_processing = True
        self.start_btn.configure(state=tk.DISABLED)
        self.stop_btn.configure(state=tk.NORMAL)

        # 在后台线程中处理
        thread = threading.Thread(target=self._process_tasks, daemon=True)
        thread.start()

    def _stop_download(self):
        """停止下载"""
        self.is_processing = False
        self._log("⏹ 用户请求停止...")

    def _process_tasks(self):
        """处理所有下载任务（在后台线程中运行）"""
        output_dir = self.dir_var.get()
        tasks = self.tree.get_children()
        total = len(tasks)
        success_count = 0
        fail_count = 0

        self.after(0, self._log, f"开始处理 {total} 个任务...")
        self.after(0, self.progress_bar.configure, {"maximum": total, "value": 0})

        for i, task_id in enumerate(tasks):
            if not self.is_processing:
                self.after(0, self._log, "⏹ 已停止")
                break

            values = self.tree.item(task_id, "values")
            url = values[1]
            select_page = values[2] if len(values) > 2 else ""
            artist = values[3] if len(values) > 3 else ""
            title = values[4] if len(values) > 4 else ""
            filename = values[5] if len(values) > 5 else ""

            self.after(0, self._update_tree_status, task_id, "⬇ 下载中...")
            self.after(0, self.progress_var.set, f"正在处理 ({i + 1}/{total}): {url[:40]}...")
            self.after(0, self.progress_bar.configure, {"value": i})

            try:
                mp3_path, cover_path = self.downloader.download_and_convert(
                    url=url,
                    output_dir=output_dir,
                    filename=filename if filename else None,
                    artist=artist,
                    title=title,
                    select_page=select_page if select_page else "",
                    progress_callback=lambda msg, tid=task_id: self.after(
                        0, self._update_tree_status, tid, msg
                    ),
                    log_callback=lambda msg: self.after(0, self._log, msg),
                    stop_callback=lambda: not self.is_processing,
                )
                self.after(0, self._update_tree_status, task_id, "✅ 完成")
                self.after(0, self._log, f"  → {os.path.basename(mp3_path)}")
                success_count += 1
            except Exception as e:
                error_msg = str(e)[:80]
                if "用户停止" in error_msg or not self.is_processing:
                    self.after(0, self._update_tree_status, task_id, "⏹ 已停止")
                    self.after(0, self._log, f"  ⏹ 已停止")
                    # 停止时直接跳出循环，不再处理后续任务
                    break
                else:
                    self.after(0, self._update_tree_status, task_id, f"❌ 失败")
                    self.after(0, self._log, f"  ✗ 失败: {error_msg}")
                    fail_count += 1

        # 完成
        self.after(0, self.progress_bar.configure, {"value": total})
        self.after(0, self.progress_var.set,
                   f"完成! 成功: {success_count}, 失败: {fail_count}, 共: {total}")
        self.after(0, self._log,
                   f"\n{'='*40}\n全部完成! 成功: {success_count}, 失败: {fail_count}\n{'='*40}")

        self.after(0, self.start_btn.configure, {"state": tk.NORMAL})
        self.after(0, self.stop_btn.configure, {"state": tk.DISABLED})
        self.is_processing = False

    def _update_tree_status(self, item_id, status):
        """更新任务状态"""
        values = list(self.tree.item(item_id, "values"))
        values[0] = status
        self.tree.item(item_id, values=values)

    # ── 设置对话框 ──
    def _open_settings(self):
        """打开设置对话框"""
        dialog = tk.Toplevel(self)
        dialog.title("设置")
        dialog.geometry("600x600")  # 高度增加到 600
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(True, True)

        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 600) // 2
        y = self.winfo_y() + (self.winfo_height() - 600) // 2
        dialog.geometry(f"+{x}+{y}")

        # 创建变量副本，避免直接修改
        temp_keywords = [dict(k) for k in self.keyword_matches]
        temp_auto_extract = tk.BooleanVar(value=self.auto_extract_booktitle)

        # 主容器
        main_frame = ttk.Frame(dialog, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 书名号提取选项
        extract_frame = ttk.LabelFrame(main_frame, text=" 标题提取设置 ", padding=10)
        extract_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Checkbutton(
            extract_frame,
            text="自动提取书名号《》『』【】「」中的内容作为标题和文件名",
            variable=temp_auto_extract
        ).pack(anchor=tk.W)

        # 关键词匹配区域
        keyword_frame = ttk.LabelFrame(main_frame, text=" 关键词匹配（自动填写艺术家） ", padding=10)
        keyword_frame.pack(fill=tk.BOTH, expand=True)

        # 关键词列表
        tree_columns = ("keyword", "artist")
        keyword_tree = ttk.Treeview(keyword_frame, columns=tree_columns, show="headings")
        keyword_tree.heading("keyword", text="关键词")
        keyword_tree.heading("artist", text="对应的艺术家")
        keyword_tree.column("keyword", width=200)
        keyword_tree.column("artist", width=250)

        keyword_scroll = ttk.Scrollbar(keyword_frame, orient=tk.VERTICAL, command=keyword_tree.yview)
        keyword_tree.configure(yscrollcommand=keyword_scroll.set)

        keyword_tree.grid(row=0, column=0, sticky="nsew")
        keyword_scroll.grid(row=0, column=1, sticky="ns")
        keyword_frame.grid_rowconfigure(0, weight=1)
        keyword_frame.grid_columnconfigure(0, weight=1)

        # 加载现有关键词
        for match in temp_keywords:
            keyword_tree.insert("", tk.END, values=(match["keyword"], match["artist"]))

        # 关键词操作按钮
        keyword_btn_frame = ttk.Frame(keyword_frame)
        keyword_btn_frame.grid(row=1, column=0, columnspan=2, pady=5)

        def add_keyword():
            """添加关键词"""
            add_dialog = tk.Toplevel(dialog)
            add_dialog.title("添加关键词匹配")
            add_dialog.geometry("400x180")
            add_dialog.transient(dialog)
            add_dialog.grab_set()

            add_dialog.update_idletasks()
            ax = dialog.winfo_x() + (dialog.winfo_width() - 400) // 2
            ay = dialog.winfo_y() + (dialog.winfo_height() - 180) // 2
            add_dialog.geometry(f"+{ax}+{ay}")

            add_frame = ttk.Frame(add_dialog, padding=15)
            add_frame.pack(fill=tk.BOTH, expand=True)

            ttk.Label(add_frame, text="关键词（视频标题中包含此关键词）:").pack(anchor=tk.W, pady=(0, 5))
            keyword_entry = ttk.Entry(add_frame, width=50)
            keyword_entry.pack(fill=tk.X, pady=(0, 10))

            ttk.Label(add_frame, text="对应的艺术家名称:").pack(anchor=tk.W, pady=(0, 5))
            artist_entry = ttk.Entry(add_frame, width=50)
            artist_entry.pack(fill=tk.X, pady=(0, 10))

            def confirm_add():
                kw = keyword_entry.get().strip()
                art = artist_entry.get().strip()
                if kw and art:
                    temp_keywords.append({"keyword": kw, "artist": art})
                    keyword_tree.insert("", tk.END, values=(kw, art))
                    add_dialog.destroy()

            def cancel_add():
                add_dialog.destroy()

            btn_frame = ttk.Frame(add_frame)
            btn_frame.pack(pady=10)
            ttk.Button(btn_frame, text="确定", command=confirm_add).pack(side=tk.LEFT, padx=5)
            ttk.Button(btn_frame, text="取消", command=cancel_add).pack(side=tk.LEFT, padx=5)

        def remove_keyword():
            """删除选中关键词"""
            selected = keyword_tree.selection()
            if not selected:
                return
            for item in selected:
                values = keyword_tree.item(item, "values")
                # 从temp_keywords中删除匹配的项
                for i, m in enumerate(temp_keywords):
                    if m["keyword"] == values[0] and m["artist"] == values[1]:
                        del temp_keywords[i]
                        break
                keyword_tree.delete(item)

        ttk.Button(keyword_btn_frame, text="➕ 添加", command=add_keyword).pack(side=tk.LEFT, padx=2)
        ttk.Button(keyword_btn_frame, text="➖ 删除选中", command=remove_keyword).pack(side=tk.LEFT, padx=2)

        # 底部按钮
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.pack(fill=tk.X, pady=(10, 0))

        def save_settings():
            """保存设置"""
            # 直接从 Treeview 中获取关键词数据
            new_keywords = []
            for item in keyword_tree.get_children():
                values = keyword_tree.item(item, "values")
                if values[0] and values[1]:
                    new_keywords.append({"keyword": values[0], "artist": values[1]})
            
            self.keyword_matches = new_keywords
            self.auto_extract_booktitle = temp_auto_extract.get()
            
            success = self._save_config()
            if success:
                dialog.destroy()
            else:
                messagebox.showerror("错误", "保存配置失败，请检查是否有写入权限")

        ttk.Button(bottom_frame, text="保存", command=save_settings, style="Accent.TButton").pack(side=tk.RIGHT, padx=5)
        ttk.Button(bottom_frame, text="取消", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)

    # ── 视频信息处理 ──
    def _extract_video_info(self, url):
        """使用 BBDown 提取视频信息（标题等）"""
        try:
            # 使用 downloader 中的 bbdown_path 和 bbdown_type
            bbdown_cmd = self.downloader.bbdown_path
            bbdown_type = self.downloader.bbdown_type

            if not bbdown_cmd:
                return None

            temp_dir = os.path.join(self.default_output_dir, "temp_info")
            os.makedirs(temp_dir, exist_ok=True)

            # BBDown-go 使用 --only-show-info，原版使用 --show-all
            info_param = "--only-show-info" if bbdown_type == "go" else "--show-all"
            args = [bbdown_cmd, url, info_param, "--work-dir", temp_dir]
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                encoding='utf-8',
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                cwd=temp_dir,
                timeout=30
            )

            # 清理临时目录
            try:
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
            except:
                pass

            print(f"[DEBUG _extract_video_info] BBDown类型: {bbdown_type}")
            print(f"[DEBUG _extract_video_info] 命令返回码: {result.returncode}")
            print(f"[DEBUG _extract_video_info] stdout 长度: {len(result.stdout)} 字符")
            print(f"[DEBUG _extract_video_info] stderr 长度: {len(result.stderr)} 字符")
            
            # BBDown-go 可能将日志输出到 stderr，合并两者
            combined_output = result.stdout + result.stderr
            
            # 输出前10行用于调试
            output_lines = combined_output.splitlines()[:10]
            if output_lines:
                print(f"[DEBUG _extract_video_info] 合并输出前10行:")
                for i, line in enumerate(output_lines):
                    print(f"[DEBUG _extract_video_info]  Line {i+1}: {repr(line)}")

            video_title = ""
            if result.returncode == 0:
                import re
                found_video_title_line = False
                for line in combined_output.splitlines():
                    if "视频标题" in line:
                        found_video_title_line = True
                        print(f"[DEBUG _extract_video_info] 找到包含'视频标题'的行: {repr(line)}")
                        # BBDown-go 格式: msg="视频标题: xxx"
                        # 原版 BBDown 格式: 视频标题: xxx
                        if bbdown_type == "go":
                            pattern = r'msg="[^"]*视频标题[：:]\s*([^"]+)"'
                            match = re.search(pattern, line)
                            print(f"[DEBUG _extract_video_info] 使用正则: {pattern}")
                        else:
                            pattern = r'视频标题[：:]\s*(.*)'
                            match = re.search(pattern, line)
                            print(f"[DEBUG _extract_video_info] 使用正则: {pattern}")
                        
                        if match:
                            video_title = match.group(1).strip()
                            print(f"[DEBUG _extract_video_info] 正则匹配成功，提取标题: {repr(video_title)}")
                            break
                        else:
                            print(f"[DEBUG _extract_video_info] 正则匹配失败，该行无法解析")
                
                if not found_video_title_line:
                    print(f"[DEBUG _extract_video_info] 未找到包含'视频标题'的行")
                    print(f"[DEBUG _extract_video_info] 搜索所有行中是否有相关内容...")
                    for line in combined_output.splitlines()[:20]:
                        if any(keyword in line for keyword in ["title", "Title", "标题", "TITLE"]):
                            print(f"[DEBUG _extract_video_info] 可能相关的行: {repr(line)}")

            print(f"[DEBUG _extract_video_info] 最终提取的标题: {repr(video_title)}")
            return {"title": video_title} if video_title else None
        except Exception as e:
            print(f"[DEBUG _extract_video_info] 异常: {e}")
            import traceback
            print(f"[DEBUG _extract_video_info] 异常详情: {traceback.format_exc()}")
            return None

    def _process_title(self, raw_title):
        """处理标题：提取书名号、匹配关键词"""
        if not raw_title:
            raw_title = ""
        raw_title = raw_title.replace('\n', '').replace('\r', '').strip()
        processed_title = raw_title
        filename = ""
        artist = ""

        # 1. 提取书名号内容（支持《》、『』、【】、「」）
        if self.auto_extract_booktitle:
            import re
            # 匹配各种中文引号内的内容
            pattern = r'[《『【「](.*?)[》』】」]'
            matches = re.findall(pattern, raw_title)
            if matches:
                processed_title = matches[-1]  # 使用最后一个引号内容
                filename = processed_title

        # 2. 关键词匹配
        for match in self.keyword_matches:
            if match["keyword"] in raw_title:
                artist = match["artist"]
                break

        return {
            "title": processed_title,
            "filename": filename if filename else processed_title,
            "artist": artist
        }

    # 修改添加任务方法，添加自动获取视频信息
    def _add_task(self, url="", select_page="1", artist="", title="", filename="", auto_fetch=True):
        """添加一个下载任务"""
        if not url:
            url = self._simple_input_dialog("添加B站链接", "请输入B站视频链接:")
            if not url:
                return

        # 验证链接格式
        url = url.strip()
        if not url:
            return

        # 支持 bilibili.com 和 b23.tv 短链接
        if not any(domain in url for domain in ["bilibili.com", "b23.tv", "bilibili.cn"]):
            messagebox.showwarning("链接无效", "请输入有效的B站视频链接")
            return

        item_id = None
        if auto_fetch and self.downloader.bbdown_available:
            # 先添加等待状态的任务
            item_id = self.tree.insert("", tk.END, values=("🔍 获取信息中...", url, select_page, artist, title, filename))
            self.tree.see(item_id)

            # 在后台线程中获取视频信息
            def fetch_info():
                info = self._extract_video_info(url)
                if info:
                    processed = self._process_title(info["title"])
                    final_artist = artist if artist else processed["artist"]
                    final_title = title if title else processed["title"]
                    final_filename = filename if filename else processed["filename"]
                    final_filename = self.downloader._sanitize_filename(final_filename)
                    
                    self.after(0, lambda: self.tree.item(item_id, values=(
                        "⏳ 等待",
                        url,
                        select_page,
                        final_artist,
                        final_title,
                        final_filename
                    )))
                else:
                    self.after(0, lambda: self._update_tree_status(item_id, "⏳ 等待"))

            thread = threading.Thread(target=fetch_info, daemon=True)
            thread.start()
        else:
            item_id = self.tree.insert("", tk.END, values=("⏳ 等待", url, select_page, artist, title, filename))
            self.tree.see(item_id)

        return item_id

    # 修改粘贴链接方法
    def _paste_links(self):
        """从剪贴板粘贴链接"""
        try:
            clipboard = self.clipboard_get()
            if not clipboard:
                messagebox.showinfo("提示", "剪贴板为空")
                return

            # 按行分割，过滤出有效链接
            lines = clipboard.strip().split("\n")
            count = 0
            for line in lines:
                line = line.strip()
                if any(domain in line for domain in ["bilibili.com", "b23.tv", "bilibili.cn"]):
                    self._add_task(url=line)
                    count += 1

            if count == 0:
                messagebox.showinfo("提示", "剪贴板中未找到有效的B站链接")
            else:
                self._log(f"从剪贴板添加了 {count} 个链接")
        except Exception as e:
            messagebox.showerror("错误", f"读取剪贴板失败: {e}")


# ─── 启动 ───────────────────────────────────────────────────
if __name__ == "__main__":
    app = Application()
    app.mainloop()
