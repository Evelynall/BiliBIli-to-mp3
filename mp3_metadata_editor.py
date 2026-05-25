#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MP3元数据编辑器
功能：编辑MP3音频的封面、歌词等元数据
支持自动匹配同名文件和歌词转移功能
"""

import os
import sys
import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import requests
import threading
from queue import Queue

REQUIRED_MODULES = {
    "mutagen": "mutagen",
    "requests": "requests",
}

missing = []
for module, package in REQUIRED_MODULES.items():
    try:
        __import__(module)
    except ImportError:
        missing.append(package)

if missing:
    import subprocess
    print(f"[!] 缺少依赖: {', '.join(missing)}")
    print(f"[*] 正在自动安装...")
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "--user", *missing, "-i", "https://pypi.tuna.tsinghua.edu.cn/simple"]
    )
    print("[✓] 依赖安装完成，正在启动程序...\n")

from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, USLT, SYLT, ID3NoHeaderError


class MP3MetadataEditor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MP3元数据编辑器")
        self.geometry("900x850")
        self.minsize(800, 750)

        self.style = ttk.Style(self)
        self.style.theme_use("clam")

        self.bg_color = "#f0f0f0"
        self.accent_color = "#4CAF50"
        self.configure(bg=self.bg_color)

        self.style.configure("Title.TLabel", font=("Microsoft YaHei UI", 16, "bold"),
                             foreground=self.accent_color, background=self.bg_color)
        self.style.configure("Header.TLabel", font=("Microsoft YaHei UI", 10, "bold"),
                             background=self.bg_color)
        self.style.configure("TButton", font=("Microsoft YaHei UI", 9))
        self.style.configure("Accent.TButton", font=("Microsoft YaHei UI", 10, "bold"),
                            foreground="white", background=self.accent_color)
        self.style.map("Accent.TButton",
                       background=[("active", "#45a049"), ("pressed", "#3d8b40")])
        self.style.configure("Status.TLabel", font=("Microsoft YaHei UI", 9),
                             foreground="#666666", background=self.bg_color)
        self.style.configure("Treeview", font=("Microsoft YaHei UI", 9), rowheight=28)
        self.style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 9, "bold"))

        self.mp3_files = []
        self.current_cover_path = None
        self.current_lrc_path = None
        self.output_dir = None
        self.artist_mapping = {}
        self.config_file = os.path.join(os.path.dirname(__file__), 'config.json')
        
        self._load_config()
        self._build_ui()

    def _load_config(self):
        """加载配置文件"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    if 'artist_mapping' in config:
                        self.artist_mapping = config['artist_mapping']
                    else:
                        self.artist_mapping = {}
            else:
                self.artist_mapping = {}
        except Exception as e:
            self.artist_mapping = {}
            print(f"加载配置失败: {e}")

    def _save_config(self):
        """保存配置文件"""
        try:
            config = {}
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            
            config['artist_mapping'] = self.artist_mapping
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            
            self._log("配置已保存")
        except Exception as e:
            self._log(f"保存配置失败: {e}")

    def _build_ui(self):
        title_frame = ttk.Frame(self)
        title_frame.pack(fill=tk.X, padx=15, pady=(10, 5))
        ttk.Label(title_frame, text="🎵 MP3元数据编辑器", style="Title.TLabel").pack(side=tk.LEFT)

        import_frame = ttk.LabelFrame(self, text=" 文件导入 ", padding=10)
        import_frame.pack(fill=tk.X, padx=15, pady=5)

        import_btn_frame = ttk.Frame(import_frame)
        import_btn_frame.pack(fill=tk.X)

        ttk.Button(import_btn_frame, text="📂 导入音乐文件夹",
                   command=self._import_music_folder).pack(side=tk.LEFT, padx=2)
        ttk.Button(import_btn_frame, text="🎵 导入音乐文件",
                   command=self._import_music_files).pack(side=tk.LEFT, padx=2)
        ttk.Button(import_btn_frame, text="🖼 导入封面文件夹",
                   command=self._import_cover_folder).pack(side=tk.LEFT, padx=2)
        ttk.Button(import_btn_frame, text="📝 导入歌词文件夹",
                   command=self._import_lrc_folder).pack(side=tk.LEFT, padx=2)
        ttk.Button(import_btn_frame, text="🔍 自动匹配歌词",
                   command=self._auto_match_lyrics,
                   style="Accent.TButton").pack(side=tk.LEFT, padx=2)

        self.path_label = ttk.Label(import_frame, text="请先导入音乐文件夹",
                                    style="Status.TLabel")
        self.path_label.pack(anchor=tk.W, pady=(5, 0))

        file_list_frame = ttk.LabelFrame(self, text=" 音乐文件列表 ", padding=10)
        file_list_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)

        tree_container = ttk.Frame(file_list_frame)
        tree_container.pack(fill=tk.BOTH, expand=True)

        columns = ("filename", "artist", "has_cover", "has_lyrics", "matched_cover", "matched_lrc")
        self.tree = ttk.Treeview(tree_container, columns=columns, show="headings", selectmode="extended")

        self.tree.heading("filename", text="文件名")
        self.tree.heading("artist", text="艺术家")
        self.tree.heading("has_cover", text="已有封面")
        self.tree.heading("has_lyrics", text="已有歌词")
        self.tree.heading("matched_cover", text="匹配的封面")
        self.tree.heading("matched_lrc", text="匹配的歌词")

        self.tree.column("filename", width=250, minwidth=150)
        self.tree.column("artist", width=120, minwidth=80)
        self.tree.column("has_cover", width=80, minwidth=60, anchor=tk.CENTER)
        self.tree.column("has_lyrics", width=80, minwidth=60, anchor=tk.CENTER)
        self.tree.column("matched_cover", width=120, minwidth=80)
        self.tree.column("matched_lrc", width=120, minwidth=80)

        scrollbar_y = ttk.Scrollbar(tree_container, orient=tk.VERTICAL, command=self.tree.yview)
        scrollbar_x = ttk.Scrollbar(tree_container, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar_y.grid(row=0, column=1, sticky="ns")
        scrollbar_x.grid(row=1, column=0, sticky="ew")

        tree_container.grid_rowconfigure(0, weight=1)
        tree_container.grid_columnconfigure(0, weight=1)

        list_btn_frame = ttk.Frame(file_list_frame)
        list_btn_frame.pack(fill=tk.X, pady=(5, 0))
        ttk.Button(list_btn_frame, text="🔄 刷新匹配",
                   command=self._refresh_matches).pack(side=tk.LEFT, padx=2)
        ttk.Button(list_btn_frame, text="🗑 清空列表",
                   command=self._clear_list).pack(side=tk.LEFT, padx=2)

        self.status_label = ttk.Label(list_btn_frame, text="共 0 个文件",
                                       style="Status.TLabel")
        self.status_label.pack(side=tk.RIGHT, padx=10)

        # 文件名处理区域
        filename_frame = ttk.LabelFrame(self, text=" 文件名处理 ", padding=10)
        filename_frame.pack(fill=tk.X, padx=15, pady=5)

        filename_btn_frame = ttk.Frame(filename_frame)
        filename_btn_frame.pack(fill=tk.X)
        ttk.Button(filename_btn_frame, text="⚙️ 管理艺术家映射",
                   command=self._open_mapping_manager).pack(side=tk.LEFT, padx=2)
        self.rename_btn = ttk.Button(filename_btn_frame, text="📝 重命名文件（添加艺术家）",
                                      style="Accent.TButton",
                                      command=self._rename_files_with_artist)
        self.rename_btn.pack(side=tk.LEFT, padx=2)

        # 原有的操作区域
        action_frame = ttk.LabelFrame(self, text=" 元数据操作 ", padding=10)
        action_frame.pack(fill=tk.X, padx=15, pady=5)

        action_btn_frame = ttk.Frame(action_frame)
        action_btn_frame.pack(fill=tk.X)

        self.write_btn = ttk.Button(action_btn_frame, text="✏ 写入元数据",
                                     style="Accent.TButton",
                                     command=self._write_metadata)
        self.write_btn.pack(side=tk.LEFT, padx=2)

        ttk.Button(action_btn_frame, text="🔀 LYRICS转USLT",
                   command=self._transfer_lyrics).pack(side=tk.LEFT, padx=2)
        ttk.Button(action_btn_frame, text="📄 格式化歌词",
                   command=self._format_lyrics).pack(side=tk.LEFT, padx=2)

        self.progress_var = tk.StringVar(value="就绪")
        ttk.Label(action_btn_frame, textvariable=self.progress_var,
                  style="Status.TLabel").pack(side=tk.RIGHT, padx=10)

        log_frame = ttk.LabelFrame(self, text=" 日志 ", padding=5)
        log_frame.pack(fill=tk.X, padx=15, pady=(5, 10))

        self.log_text = tk.Text(log_frame, height=6, font=("Consolas", 9),
                                 bg="#1e1e1e", fg="#d4d4d4", insertbackground="white",
                                 wrap=tk.WORD, state=tk.DISABLED)
        log_scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scrollbar.set)

        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def _log(self, message):
        """添加日志"""
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _import_music_folder(self):
        folder = filedialog.askdirectory(title="选择音乐文件夹")
        if not folder:
            return

        self.output_dir = folder
        self.mp3_files = []
        self.tree.delete(*self.tree.get_children())

        for file in Path(folder).iterdir():
            if file.suffix.lower() in ['.mp3']:
                self.mp3_files.append(str(file))
                artist = self._get_artist_from_metadata(str(file)) or "未知"
                self.tree.insert("", tk.END, values=(file.name, artist, "未知", "未知", "", ""))

        self.path_label.config(text=f"音乐目录: {folder}")
        self.status_label.config(text=f"共 {len(self.mp3_files)} 个文件")
        self._log(f"导入了 {len(self.mp3_files)} 个音乐文件")
        self._refresh_matches()

    def _import_music_files(self):
        files = filedialog.askopenfilenames(
            title="选择音乐文件",
            filetypes=[("MP3文件", "*.mp3"), ("所有文件", "*.*")]
        )
        if not files:
            return

        for file in files:
            if file not in self.mp3_files:
                self.mp3_files.append(file)
                file_path = Path(file)
                artist = self._get_artist_from_metadata(file) or "未知"
                self.tree.insert("", tk.END, values=(file_path.name, artist, "未知", "未知", "", ""))

        self.status_label.config(text=f"共 {len(self.mp3_files)} 个文件")
        self._log(f"添加了 {len(files)} 个音乐文件")
        self._refresh_matches()

    def _import_cover_folder(self):
        folder = filedialog.askdirectory(title="选择封面文件夹")
        if not folder:
            return

        self.cover_dir = folder
        self._log(f"封面目录: {folder}")
        self._refresh_matches()

    def _import_lrc_folder(self):
        folder = filedialog.askdirectory(title="选择歌词文件夹")
        if not folder:
            return

        self.lrc_dir = folder
        self._log(f"歌词目录: {folder}")
        self._refresh_matches()

    def _get_base_name(self, filename):
        """获取不含扩展名的文件名"""
        return Path(filename).stem

    def _find_matching_file(self, base_name, directory, extensions):
        """在目录中查找匹配的文件"""
        if not directory or not os.path.isdir(directory):
            return None

        for ext in extensions:
            potential_file = os.path.join(directory, base_name + ext)
            if os.path.exists(potential_file):
                return os.path.basename(potential_file)
        return None

    def _check_mp3_metadata(self, mp3_path):
        """检查MP3文件已有的元数据"""
        has_cover = False
        has_lyrics = False
        lyrics_type = None

        try:
            tags = ID3(mp3_path)
            for key in tags.keys():
                if key.startswith("APIC"):
                    has_cover = True
                    break
            for key in tags.keys():
                if key.startswith("USLT"):
                    has_lyrics = True
                    lyrics_type = "USLT"
                    break
                elif key.startswith("SYLT"):
                    has_lyrics = True
                    lyrics_type = "SYLT"
                    break
        except ID3NoHeaderError:
            pass
        except Exception as e:
            self._log(f"检查元数据失败 {mp3_path}: {e}")

        return has_cover, has_lyrics, lyrics_type

    def _refresh_matches(self):
        """刷新文件匹配状态"""
        cover_extensions = ['.jpg', '.jpeg', '.png', '.JPG', '.JPEG', '.PNG']
        lrc_extensions = ['.lrc', '.LRC']

        cover_dir = getattr(self, 'cover_dir', None)
        lrc_dir = getattr(self, 'lrc_dir', None)

        for i, item in enumerate(self.tree.get_children()):
            values = list(self.tree.item(item, "values"))
            mp3_file = self.mp3_files[i] if i < len(self.mp3_files) else None

            if mp3_file:
                base_name = self._get_base_name(mp3_file)

                has_cover, has_lyrics, lyrics_type = self._check_mp3_metadata(mp3_file)

                values[2] = "✓" if has_cover else "✗"
                values[3] = lyrics_type if has_lyrics else "✗"

                matched_cover = self._find_matching_file(base_name, cover_dir, cover_extensions)
                matched_lrc = self._find_matching_file(base_name, lrc_dir, lrc_extensions)

                values[4] = matched_cover if matched_cover else ""
                values[5] = matched_lrc if matched_lrc else ""

                self.tree.item(item, values=values)

        self._log("已刷新文件匹配状态")

    def _clear_list(self):
        """清空列表"""
        if self.tree.get_children():
            if messagebox.askyesno("确认", "确定要清空列表吗？"):
                self.tree.delete(*self.tree.get_children())
                self.mp3_files = []
                self.status_label.config(text="共 0 个文件")
                self._log("已清空文件列表")

    def _write_metadata(self):
        """写入元数据"""
        items = self.tree.selection()
        if not items:
            if messagebox.askyesno("提示", "未选择文件，是否处理所有文件？"):
                items = self.tree.get_children()
            else:
                return

        if not items:
            messagebox.showinfo("提示", "没有可处理的文件")
            return

        cover_dir = getattr(self, 'cover_dir', None)
        lrc_dir = getattr(self, 'lrc_dir', None)
        cover_extensions = ['.jpg', '.jpeg', '.png', '.JPG', '.JPEG', '.PNG']
        lrc_extensions = ['.lrc', '.LRC']

        success_count = 0
        fail_count = 0

        for item in items:
            idx = self.tree.index(item)
            if idx >= len(self.mp3_files):
                continue

            mp3_path = self.mp3_files[idx]
            base_name = self._get_base_name(mp3_path)
            values = list(self.tree.item(item, "values"))

            try:
                matched_cover = values[4]
                matched_lrc = values[5]

                if not matched_cover and not matched_lrc:
                    self._log(f"跳过（无匹配文件）: {base_name}")
                    continue

                self._log(f"处理中: {base_name}")

                try:
                    audio = MP3(mp3_path)
                    try:
                        tags = audio.tags
                    except:
                        audio.add_tags()
                        tags = audio.tags

                    cover_added = False
                    lrc_added = False

                    if matched_cover and cover_dir:
                        cover_path = os.path.join(cover_dir, matched_cover)
                        if os.path.exists(cover_path):
                            mime_type = "image/jpeg"
                            if matched_cover.lower().endswith('.png'):
                                mime_type = "image/png"

                            with open(cover_path, 'rb') as f:
                                cover_data = f.read()

                            tags.delall("APIC")
                            tags.add(APIC(
                                encoding=3,
                                mime=mime_type,
                                type=3,
                                desc="Cover",
                                data=cover_data
                            ))
                            cover_added = True
                            self._log(f"  + 封面已添加: {matched_cover}")

                    if matched_lrc and lrc_dir:
                        lrc_path = os.path.join(lrc_dir, matched_lrc)
                        if os.path.exists(lrc_path):
                            with open(lrc_path, 'r', encoding='utf-8') as f:
                                lyrics_content = f.read()

                            tags.delall("USLT")
                            tags.add(USLT(
                                encoding=3,
                                lang='eng',
                                desc='',
                                text=lyrics_content
                            ))
                            lrc_added = True
                            self._log(f"  + 歌词已添加: {matched_lrc}")

                    audio.save()
                    self._log(f"  ✓ 完成")
                    success_count += 1

                except Exception as e:
                    self._log(f"  ✗ 失败: {e}")
                    fail_count += 1

            except Exception as e:
                self._log(f"处理失败 {base_name}: {e}")
                fail_count += 1

        self.progress_var.set(f"完成! 成功: {success_count}, 失败: {fail_count}")
        self._log(f"\n写入完成: 成功 {success_count}, 失败 {fail_count}")

    def _transfer_lyrics(self):
        """将LYRICS标签内容转移到UNSYNCED LYRICS标签"""
        items = self.tree.selection()
        if not items:
            if messagebox.askyesno("提示", "未选择文件，是否处理所有文件？"):
                items = self.tree.get_children()
            else:
                return

        if not items:
            messagebox.showinfo("提示", "没有可处理的文件")
            return

        success_count = 0
        fail_count = 0

        for item in items:
            idx = self.tree.index(item)
            if idx >= len(self.mp3_files):
                continue

            mp3_path = self.mp3_files[idx]
            base_name = self._get_base_name(mp3_path)

            try:
                audio = MP3(mp3_path)
                try:
                    tags = audio.tags
                except:
                    audio.add_tags()
                    tags = audio.tags

                lyrics_text = None
                found_source = None

                for key in tags.keys():
                    if key.startswith("SYLT"):
                        frame = tags[key]
                        lyrics_text = self._extract_lyrics_from_frame(frame)
                        found_source = "SYLT"
                        break
                    elif key.startswith("USLT"):
                        frame = tags[key]
                        lyrics_text = self._extract_lyrics_from_frame(frame)
                        found_source = "USLT"
                        break
                    elif key.startswith("LYRICS"):
                        frame = tags[key]
                        lyrics_text = self._extract_lyrics_from_frame(frame)
                        found_source = "LYRICS"
                        break
                    elif key.startswith("TXXX") and "LYRIC" in key.upper():
                        frame = tags[key]
                        lyrics_text = self._extract_lyrics_from_frame(frame)
                        found_source = "TXXX:" + key
                        break

                if not lyrics_text:
                    self._log(f"跳过（未找到歌词）: {base_name}")
                    continue

                lyrics_text = lyrics_text.replace('\x00', '')

                tags.delall("USLT")
                tags.add(USLT(
                    encoding=3,
                    lang='eng',
                    desc='',
                    text=lyrics_text
                ))

                audio.save()
                self._log(f"✓ 已从 {found_source} 转移到 USLT: {base_name}")
                success_count += 1

            except Exception as e:
                self._log(f"✗ 处理失败 {base_name}: {str(e)[:50]}")
                fail_count += 1

        self.progress_var.set(f"完成! 成功: {success_count}, 失败: {fail_count}")
        self._log(f"\n歌词转移完成: 成功 {success_count}, 失败 {fail_count}")

    def _extract_lyrics_from_frame(self, frame):
        """从帧中提取歌词内容"""
        if not hasattr(frame, 'text'):
            return None
        
        text = frame.text
        
        if isinstance(text, str):
            return self._clean_lyrics_text(text)
        elif isinstance(text, list):
            parts = []
            for item in text:
                if isinstance(item, str):
                    parts.append(self._clean_lyrics_text(item))
                elif hasattr(item, '__iter__') and len(item) >= 2:
                    parts.append(self._clean_lyrics_text(str(item[1])))
                else:
                    parts.append(self._clean_lyrics_text(str(item)))
            return '\n'.join(parts)
        else:
            return self._clean_lyrics_text(str(text))

    def _clean_lyrics_text(self, text):
        """清理歌词文本，去除BOM、列表符号和转义字符"""
        text = str(text)
        
        text = text.replace('\ufeff', '').replace('\uFEFF', '')
        
        if text.startswith("['") and text.endswith("']"):
            text = text[2:-2]
        elif text.startswith('["') and text.endswith('"]'):
            text = text[2:-2]
        elif text.startswith('[') and text.endswith(']'):
            text = text[1:-1]
        
        text = text.replace('\\n', '\n').replace('\\r', '\r').replace('\\t', '\t')
        text = text.replace('\\"', '"').replace("\\'", "'").replace('\\\\', '\\')
        text = text.replace('\x00', '')
        
        text = text.replace("', '", '\n').replace('", "', '\n')
        
        return text.strip()

    def _open_mapping_manager(self):
        """打开艺术家映射管理对话框"""
        MappingManagerDialog(self)

    def _rename_files_with_artist(self):
        """重命名文件，将艺术家添加到文件名末尾"""
        items = self.tree.selection()
        if not items:
            if messagebox.askyesno("提示", "未选择文件，是否处理所有文件？"):
                items = self.tree.get_children()
            else:
                return
        
        if not items:
            messagebox.showinfo("提示", "没有可处理的文件")
            return
        
        success_count = 0
        fail_count = 0
        skip_count = 0
        
        for item in items:
            idx = self.tree.index(item)
            if idx >= len(self.mp3_files):
                continue
            
            mp3_path = self.mp3_files[idx]
            path = Path(mp3_path)
            
            try:
                artist = self._get_artist_from_metadata(mp3_path)
                if not artist:
                    self._log(f"跳过（未找到艺术家）: {path.name}")
                    skip_count += 1
                    continue
                
                artist = self._apply_artist_mapping(artist)
                
                new_path = self._generate_new_filename(mp3_path, artist)
                if not new_path:
                    skip_count += 1
                    continue
                
                if new_path.exists():
                    self._log(f"跳过（文件已存在）: {new_path.name}")
                    skip_count += 1
                    continue
                
                path.rename(new_path)
                self.mp3_files[idx] = str(new_path)
                
                values = list(self.tree.item(item, "values"))
                values[0] = new_path.name
                self.tree.item(item, values=values)
                
                self._log(f"✓ 重命名: {path.name} → {new_path.name}")
                success_count += 1
                
            except Exception as e:
                self._log(f"✗ 重命名失败 {path.name}: {e}")
                fail_count += 1
        
        self.progress_var.set(f"完成! 成功: {success_count}, 跳过: {skip_count}, 失败: {fail_count}")
        self._log(f"\n重命名完成: 成功 {success_count}, 跳过 {skip_count}, 失败 {fail_count}")

    def _get_artist_from_metadata(self, mp3_path):
        """从MP3文件读取艺术家信息"""
        try:
            tags = ID3(mp3_path)
            # 尝试多种艺术家标签
            if 'TPE1' in tags:  # 主要艺术家
                return str(tags['TPE1'])
            elif 'TPE2' in tags:  # 专辑艺术家
                return str(tags['TPE2'])
            elif 'TCOM' in tags:  # 作曲家
                return str(tags['TCOM'])
        except ID3NoHeaderError:
            pass
        except Exception as e:
            self._log(f"读取艺术家失败 {mp3_path}: {e}")
        return None

    def _apply_artist_mapping(self, artist_name):
        """应用艺术家名字映射"""
        if not artist_name:
            return artist_name
        return self.artist_mapping.get(artist_name, artist_name)

    def _extract_song_name(self, filename):
        """从文件名中提取歌曲名（取最后一个"-"前面的部分）"""
        stem = Path(filename).stem
        if "-" in stem:
            return stem.rsplit("-", 1)[0].strip()
        return stem.strip()
    
    def _search_lyrics_from_netease(self, song_name):
        """通过网易云音乐 API 搜索歌词"""
        try:
            # 第一步：搜索歌曲
            search_url = "https://music.163.com/api/search/get/web"
            params = {
                "s": song_name,
                "type": 1,
                "offset": 0,
                "limit": 5
            }
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            response = requests.get(search_url, params=params, headers=headers, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            if data.get("code") == 200 and data.get("result", {}).get("songs"):
                song_id = data["result"]["songs"][0]["id"]
                
                # 第二步：获取歌词
                lyric_url = f"https://music.163.com/api/song/media?id={song_id}"
                response = requests.get(lyric_url, headers=headers, timeout=15)
                response.raise_for_status()
                lyric_data = response.json()
                
                if lyric_data.get("code") == 200 and lyric_data.get("lyric"):
                    return lyric_data["lyric"]
            return None
        except Exception as e:
            self._log(f"网易云音乐歌词获取失败 {song_name}: {e}")
            return None
    
    def _search_lyrics_from_gecimi(self, song_name):
        """通过 gecimi API 搜索歌词"""
        try:
            # 尝试使用 HTTPS 协议
            url = f"https://gecimi.com/api/lyric/{requests.utils.quote(song_name)}"
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            if data.get("code") == 0 and data.get("count", 0) > 0:
                # 返回第一个匹配结果的歌词 URL
                lrc_url = data["result"][0]["lrc"]
                # 确保歌词 URL 也使用 HTTPS
                if lrc_url.startswith("http://"):
                    lrc_url = "https://" + lrc_url[7:]
                return lrc_url
            return None
        except requests.exceptions.RequestException as e:
            self._log(f"gecimi API 搜索歌词失败 {song_name}: {e}")
            return None
        except Exception as e:
            self._log(f"gecimi API 搜索歌词出错 {song_name}: {e}")
            return None
    
    def _download_lyrics(self, lrc_url_or_content, save_path, is_content=False):
        """下载歌词文件或直接保存内容"""
        try:
            if is_content:
                with open(save_path, 'w', encoding='utf-8') as f:
                    f.write(lrc_url_or_content)
                return True
            else:
                response = requests.get(lrc_url_or_content, timeout=15)
                response.raise_for_status()
                with open(save_path, 'w', encoding='utf-8') as f:
                    f.write(response.text)
                return True
        except requests.exceptions.RequestException as e:
            self._log(f"下载歌词失败: {e}")
            return False
        except Exception as e:
            self._log(f"保存歌词失败: {e}")
            return False
    
    def _auto_match_lyrics(self):
        """自动匹配并下载歌词"""
        if not self.mp3_files:
            messagebox.showwarning("警告", "请先导入音乐文件")
            return
        
        lrc_dir = getattr(self, 'lrc_dir', None)
        if not lrc_dir:
            lrc_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '歌词')
            if not os.path.exists(lrc_dir):
                os.makedirs(lrc_dir)
            self.lrc_dir = lrc_dir
            self._log(f"歌词目录已设置为: {lrc_dir}")
        
        items = self.tree.selection()
        if not items:
            if messagebox.askyesno("提示", "未选择文件，是否处理所有文件？"):
                items = self.tree.get_children()
            else:
                return
        
        if not items:
            messagebox.showinfo("提示", "没有可处理的文件")
            return
        
        self._log("=" * 40)
        self._log("开始自动匹配歌词...")
        self.progress_var.set("正在下载歌词...")
        self.update_idletasks()
        
        tasks_to_process = []
        for item in items:
            idx = self.tree.index(item)
            if idx >= len(self.mp3_files):
                continue
            mp3_path = self.mp3_files[idx]
            base_name = self._get_base_name(mp3_path)
            song_name = self._extract_song_name(mp3_path)
            lrc_path = os.path.join(lrc_dir, base_name + ".lrc")
            
            if os.path.exists(lrc_path):
                self._log(f"跳过（歌词已存在）: {base_name}")
                continue
            
            tasks_to_process.append({
                'item': item,
                'idx': idx,
                'base_name': base_name,
                'song_name': song_name,
                'lrc_path': lrc_path
            })
        
        if not tasks_to_process:
            self._log("没有需要处理的歌曲")
            self.progress_var.set("完成！")
            return
        
        self._log(f"共 {len(tasks_to_process)} 个任务需要处理")
        
        self.lyrics_queue = Queue()
        self.lyrics_results = {}
        
        def download_worker(task):
            base_name = task['base_name']
            song_name = task['song_name']
            lrc_path = task['lrc_path']
            item = task['item']
            idx = task['idx']
            
            self.lyrics_queue.put({
                'type': 'log',
                'item': item,
                'idx': idx,
                'base_name': base_name,
                'message': f"搜索歌词: {song_name}",
                'final': False
            })
            
            lrc_url = self._search_lyrics_from_gecimi(song_name)
            if lrc_url:
                if self._download_lyrics(lrc_url, lrc_path):
                    self.lyrics_queue.put({
                        'type': 'log',
                        'item': item,
                        'idx': idx,
                        'base_name': base_name,
                        'message': f"  ✓ 歌词已保存(gecimi): {base_name}.lrc",
                        'success': True,
                        'final': True
                    })
                    return
            
            self.lyrics_queue.put({
                'type': 'log',
                'item': item,
                'idx': idx,
                'base_name': base_name,
                'message': f"  gecimi 失败，尝试网易云音乐...",
                'final': False
            })
            
            lyric_content = self._search_lyrics_from_netease(song_name)
            if lyric_content:
                if self._download_lyrics(lyric_content, lrc_path, is_content=True):
                    self.lyrics_queue.put({
                        'type': 'log',
                        'item': item,
                        'idx': idx,
                        'base_name': base_name,
                        'message': f"  ✓ 歌词已保存(网易云): {base_name}.lrc",
                        'success': True,
                        'final': True
                    })
                    return
            
            self.lyrics_queue.put({
                'type': 'log',
                'item': item,
                'idx': idx,
                'base_name': base_name,
                'message': f"  ✗ 未找到歌词",
                'success': False,
                'final': True
            })
        
        def process_queue():
            processed = 0
            total = len(tasks_to_process)
            
            while processed < total:
                try:
                    result = self.lyrics_queue.get_nowait()
                    
                    if result['type'] == 'log':
                        self._log(result['message'])
                        
                        if result.get('final', False):
                            if result.get('success', False):
                                values = list(self.tree.item(result['item'], "values"))
                                values[5] = f"{result['base_name']}.lrc"
                                self.tree.item(result['item'], values=values)
                            
                            self.lyrics_results[result['idx']] = result
                            processed += 1
                        
                        self.progress_var.set(f"正在下载歌词... ({processed}/{total})")
                    
                except:
                    pass
                
                self.after(100, process_queue)
                return
            
            self._finish_lyrics_download()
        
        for task in tasks_to_process:
            t = threading.Thread(target=download_worker, args=(task,))
            t.daemon = True
            t.start()
        
        self.after(100, process_queue)
    
    def _finish_lyrics_download(self):
        """完成歌词下载后更新状态"""
        success_count = sum(1 for r in self.lyrics_results.values() if r['success'])
        fail_count = sum(1 for r in self.lyrics_results.values() if not r['success'] and not r['skip'])
        
        self.progress_var.set(f"完成! 成功: {success_count}, 跳过: 0, 失败: {fail_count}")
        self._log(f"\n歌词匹配完成: 成功 {success_count}, 跳过 0, 失败 {fail_count}")
        self._log("=" * 40)
    
    def _generate_new_filename(self, original_path, artist_name):
        """生成新的文件名"""
        path = Path(original_path)
        stem = path.stem
        ext = path.suffix
        
        # 检查文件名是否已经包含括号中的艺术家
        import re
        if re.search(r'\([^)]+\)$', stem):
            self._log(f"文件名已包含括号标记，跳过: {stem}")
            return None
        
        # 生成新文件名
        new_stem = f"{stem}({artist_name})"
        return path.with_name(new_stem + ext)

    def _parse_filename_info(self, filename):
        """从文件名中提取歌曲名和原唱，格式：{歌曲名}-{原唱}(其他内容)"""
        stem = Path(filename).stem
        song_name = ""
        original_singer = ""
        
        if "-" in stem:
            parts = stem.rsplit("-", 1)
            song_name = parts[0].strip()
            
            second_part = parts[1].strip()
            if "(" in second_part:
                end_idx = second_part.find("(")
                original_singer = second_part[:end_idx].strip()
            else:
                original_singer = second_part
        
        return song_name, original_singer

    def _extract_first_lyric_time(self, lyrics_content):
        """提取第一句歌词的时间戳"""
        import re
        lines = lyrics_content.split('\n')
        
        for line in lines:
            line = line.strip()
            if line.startswith('[') and ']' in line:
                time_match = re.match(r'\[(\d{2}):(\d{2})\.(\d{2,3})\]', line)
                if time_match:
                    minutes = int(time_match.group(1))
                    seconds = int(time_match.group(2))
                    milliseconds = int(time_match.group(3))
                    return minutes * 60 + seconds + milliseconds / 1000.0
        
        return None

    def _subtract_seconds_from_time(self, total_seconds, subtract_seconds=3):
        """从时间戳中减去指定秒数，返回格式化的时间字符串"""
        new_seconds = max(0, total_seconds - subtract_seconds)
        
        minutes = int(new_seconds // 60)
        seconds = int(new_seconds % 60)
        milliseconds = int((new_seconds - int(new_seconds)) * 100)
        
        return f"{minutes:02d}:{seconds:02d}.{milliseconds:02d}"

    def _get_lyrics_from_metadata(self, mp3_path):
        """从MP3元数据中读取歌词"""
        try:
            audio = MP3(mp3_path)
            tags = audio.tags
            
            for key in tags.keys():
                if key.startswith("USLT"):
                    return str(tags[key].text)
                elif key.startswith("SYLT"):
                    return self._extract_lyrics_from_frame(tags[key])
            return None
        except Exception as e:
            self._log(f"从元数据读取歌词失败 {mp3_path}: {e}")
            return None

    def _write_lyrics_to_metadata(self, mp3_path, lyrics_content):
        """将歌词写入MP3元数据"""
        try:
            audio = MP3(mp3_path)
            try:
                tags = audio.tags
            except:
                audio.add_tags()
                tags = audio.tags
            
            tags.delall("USLT")
            tags.add(USLT(
                encoding=3,
                lang='eng',
                desc='',
                text=lyrics_content
            ))
            audio.save()
            return True
        except Exception as e:
            self._log(f"写入歌词到元数据失败 {mp3_path}: {e}")
            return False

    def _format_lyrics(self):
        """格式化歌词文件，添加基础信息，支持歌词文件和元数据"""
        lrc_dir = getattr(self, 'lrc_dir', None)
        
        items = self.tree.selection()
        if not items:
            if messagebox.askyesno("提示", "未选择文件，是否处理所有文件？"):
                items = self.tree.get_children()
            else:
                return
        
        if not items:
            messagebox.showinfo("提示", "没有可处理的文件")
            return
        
        success_count = 0
        fail_count = 0
        skip_count = 0
        
        for item in items:
            idx = self.tree.index(item)
            if idx >= len(self.mp3_files):
                continue
            
            mp3_path = self.mp3_files[idx]
            base_name = self._get_base_name(mp3_path)
            lrc_path = os.path.join(lrc_dir, base_name + ".lrc") if lrc_dir else None
            
            content = None
            
            if lrc_path and os.path.exists(lrc_path):
                with open(lrc_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            else:
                content = self._get_lyrics_from_metadata(mp3_path)
            
            if not content:
                self._log(f"跳过（无歌词内容）: {base_name}")
                skip_count += 1
                continue
            
            try:
                song_name, original_singer = self._parse_filename_info(mp3_path)
                artist = self._get_artist_from_metadata(mp3_path) or "未知"
                
                lines = content.split('\n')
                first_line = lines[0] if lines else ""
                remaining_lines = lines[1:] if len(lines) > 1 else []
                
                first_lyric_time = self._extract_first_lyric_time(content)
                
                formatted_lines = []
                
                if first_line.startswith('[by:') and ']' in first_line:
                    formatted_lines.append(first_line)
                    formatted_lines.append("[offset:500]")
                else:
                    formatted_lines.append("[offset:500]")
                    if first_line:
                        remaining_lines.insert(0, first_line)
                
                formatted_lines.append("")
                formatted_lines.append(f"[00:00.00] {song_name} - {original_singer}" if song_name else "")
                
                if first_lyric_time is not None and first_lyric_time < 2.0:
                    formatted_lines.append(f"[00:00.00] 翻唱：{artist}")
                else:
                    formatted_lines.append(f"[00:02.00] 翻唱：{artist}")
                
                formatted_lines.append("[00:04.00]")
                formatted_lines.append("")
                
                if first_lyric_time is not None:
                    dotted_time = self._subtract_seconds_from_time(first_lyric_time)
                    formatted_lines.append(f"[{dotted_time}]...")
                    formatted_lines.append("")
                
                formatted_lines.extend(remaining_lines)
                
                new_content = '\n'.join(formatted_lines)
                
                if lrc_path and os.path.exists(lrc_path):
                    with open(lrc_path, 'w', encoding='utf-8') as f:
                        f.write(new_content)
                    self._log(f"✓ 歌词文件格式化完成: {base_name}.lrc")
                else:
                    if self._write_lyrics_to_metadata(mp3_path, new_content):
                        self._log(f"✓ 元数据歌词格式化完成: {base_name}")
                    else:
                        self._log(f"✗ 写入元数据失败: {base_name}")
                        fail_count += 1
                        continue
                
                success_count += 1
                
            except Exception as e:
                self._log(f"✗ 歌词格式化失败 {base_name}: {e}")
                fail_count += 1
        
        self.progress_var.set(f"完成! 成功: {success_count}, 跳过: {skip_count}, 失败: {fail_count}")
        self._log(f"\n歌词格式化完成: 成功 {success_count}, 跳过 {skip_count}, 失败 {fail_count}")


class MappingManagerDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title("艺术家映射管理")
        self.geometry("500x550")
        self.resizable(True, True)
        
        self.style = ttk.Style(self)
        self.style.theme_use("clam")
        
        self._build_ui()
        self._load_mapping_to_tree()
        
        self.transient(parent)
        self.grab_set()
    
    def _build_ui(self):
        # 列表区域
        list_frame = ttk.LabelFrame(self, text=" 映射列表 ", padding=10)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.tree = ttk.Treeview(list_frame, columns=("original", "mapped"), show="headings")
        self.tree.heading("original", text="原名")
        self.tree.heading("mapped", text="映射名")
        self.tree.column("original", width=180, minwidth=100)
        self.tree.column("mapped", width=180, minwidth=100)
        
        scrollbar_y = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        scrollbar_x = ttk.Scrollbar(list_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)
        scrollbar_x.pack(side=tk.BOTTOM, fill=tk.X)
        
        # 输入区域
        input_frame = ttk.LabelFrame(self, text=" 添加/编辑映射 ", padding=10)
        input_frame.pack(fill=tk.X, padx=10, pady=5)
        
        row1 = ttk.Frame(input_frame)
        row1.pack(fill=tk.X, pady=5)
        ttk.Label(row1, text="原名:").pack(side=tk.LEFT, padx=5)
        self.original_entry = ttk.Entry(row1, width=25)
        self.original_entry.pack(side=tk.LEFT, padx=5)
        ttk.Label(row1, text="映射名:").pack(side=tk.LEFT, padx=5)
        self.mapped_entry = ttk.Entry(row1, width=25)
        self.mapped_entry.pack(side=tk.LEFT, padx=5)
        
        # 按钮区域
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Button(btn_frame, text="➕ 添加", command=self._add_mapping).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="✏ 编辑", command=self._edit_mapping).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="🗑 删除", command=self._delete_mapping).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="🔄 清空", command=self._clear_all).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="💾 保存", command=self._save_and_close, style="Accent.TButton").pack(side=tk.RIGHT, padx=2)
    
    def _load_mapping_to_tree(self):
        """加载映射到列表"""
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        for original, mapped in self.parent.artist_mapping.items():
            self.tree.insert("", tk.END, values=(original, mapped))
    
    def _add_mapping(self):
        """添加映射"""
        original = self.original_entry.get().strip()
        mapped = self.mapped_entry.get().strip()
        
        if not original or not mapped:
            messagebox.showwarning("警告", "请填写完整的原名和映射名")
            return
        
        if original in self.parent.artist_mapping:
            if messagebox.askyesno("确认", f"原名 '{original}' 已存在，是否覆盖？"):
                self.parent.artist_mapping[original] = mapped
                self._load_mapping_to_tree()
        else:
            self.parent.artist_mapping[original] = mapped
            self._load_mapping_to_tree()
        
        self.original_entry.delete(0, tk.END)
        self.mapped_entry.delete(0, tk.END)
    
    def _edit_mapping(self):
        """编辑映射"""
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("警告", "请选择要编辑的映射")
            return
        
        item = selected[0]
        values = self.tree.item(item, "values")
        original = values[0]
        mapped = values[1]
        
        self.original_entry.delete(0, tk.END)
        self.original_entry.insert(0, original)
        self.mapped_entry.delete(0, tk.END)
        self.mapped_entry.insert(0, mapped)
        
        self.tree.delete(item)
        del self.parent.artist_mapping[original]
    
    def _delete_mapping(self):
        """删除映射"""
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("警告", "请选择要删除的映射")
            return
        
        if messagebox.askyesno("确认", "确定要删除选中的映射吗？"):
            item = selected[0]
            values = self.tree.item(item, "values")
            original = values[0]
            
            self.tree.delete(item)
            if original in self.parent.artist_mapping:
                del self.parent.artist_mapping[original]
    
    def _clear_all(self):
        """清空所有映射"""
        if not self.tree.get_children():
            return
        
        if messagebox.askyesno("确认", "确定要清空所有映射吗？"):
            for item in self.tree.get_children():
                self.tree.delete(item)
            self.parent.artist_mapping.clear()
    
    def _save_and_close(self):
        """保存并关闭"""
        self.parent._save_config()
        self.destroy()


if __name__ == "__main__":
    app = MP3MetadataEditor()
    app.mainloop()
