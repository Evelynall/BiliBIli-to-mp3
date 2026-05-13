#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MP3元数据编辑器
功能：编辑MP3音频的封面、歌词等元数据
支持自动匹配同名文件和歌词转移功能
"""

import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

REQUIRED_MODULES = {
    "mutagen": "mutagen",
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
        self.geometry("900x700")
        self.minsize(800, 600)

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

        self._build_ui()

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

        self.path_label = ttk.Label(import_frame, text="请先导入音乐文件夹",
                                    style="Status.TLabel")
        self.path_label.pack(anchor=tk.W, pady=(5, 0))

        file_list_frame = ttk.LabelFrame(self, text=" 音乐文件列表 ", padding=10)
        file_list_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)

        tree_container = ttk.Frame(file_list_frame)
        tree_container.pack(fill=tk.BOTH, expand=True)

        columns = ("filename", "has_cover", "has_lyrics", "matched_cover", "matched_lrc")
        self.tree = ttk.Treeview(tree_container, columns=columns, show="headings", selectmode="extended")

        self.tree.heading("filename", text="文件名")
        self.tree.heading("has_cover", text="已有封面")
        self.tree.heading("has_lyrics", text="已有歌词")
        self.tree.heading("matched_cover", text="匹配的封面")
        self.tree.heading("matched_lrc", text="匹配的歌词")

        self.tree.column("filename", width=300, minwidth=150)
        self.tree.column("has_cover", width=80, minwidth=60, anchor=tk.CENTER)
        self.tree.column("has_lyrics", width=80, minwidth=60, anchor=tk.CENTER)
        self.tree.column("matched_cover", width=150, minwidth=80)
        self.tree.column("matched_lrc", width=150, minwidth=80)

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

        action_frame = ttk.LabelFrame(self, text=" 操作 ", padding=10)
        action_frame.pack(fill=tk.X, padx=15, pady=5)

        action_btn_frame = ttk.Frame(action_frame)
        action_btn_frame.pack(fill=tk.X)

        self.write_btn = ttk.Button(action_btn_frame, text="✏ 写入元数据",
                                     style="Accent.TButton",
                                     command=self._write_metadata)
        self.write_btn.pack(side=tk.LEFT, padx=2)

        ttk.Button(action_btn_frame, text="🔀 LYRICS转USLT",
                   command=self._transfer_lyrics).pack(side=tk.LEFT, padx=2)

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
                self.tree.insert("", tk.END, values=(file.name, "未知", "未知", "", ""))

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
                self.tree.insert("", tk.END, values=(file_path.name, "未知", "未知", "", ""))

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

                values[1] = "✓" if has_cover else "✗"
                values[2] = lyrics_type if has_lyrics else "✗"

                matched_cover = self._find_matching_file(base_name, cover_dir, cover_extensions)
                matched_lrc = self._find_matching_file(base_name, lrc_dir, lrc_extensions)

                values[3] = matched_cover if matched_cover else ""
                values[4] = matched_lrc if matched_lrc else ""

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
                matched_cover = values[3]
                matched_lrc = values[4]

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


if __name__ == "__main__":
    app = MP3MetadataEditor()
    app.mainloop()
