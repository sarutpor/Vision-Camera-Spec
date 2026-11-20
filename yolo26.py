# filename: yolo26_train_gui_full_fixed_gpu_push_PATCHED_NO_MEMERROR.py
# -*- coding: utf-8 -*-

import os
import sys
import shutil
import time
import random
from datetime import datetime, timedelta
from threading import Thread
import urllib.request
import ssl
import atexit
import tempfile
import multiprocessing as mp

from sklearn.model_selection import train_test_split
import tkinter as tk
from tkinter import filedialog, ttk, messagebox
from tkinter.scrolledtext import ScrolledText

from ultralytics import YOLO
import torch
import torch.nn as nn
import torch.nn.functional as F


# =================================================================================
# ✅ กันโปรแกรมรันซ้อน (กันเด้ง askdirectory ซ้ำ)
# =================================================================================
_LOCK_FILE = os.path.join(tempfile.gettempdir(), "yolo26_train_gui.lock")

def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            SYNCHRONIZE = 0x00100000
            STILL_ACTIVE = 259

            handle = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE,
                False,
                pid
            )
            if not handle:
                return False

            exit_code = ctypes.c_ulong()
            ok = ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            ctypes.windll.kernel32.CloseHandle(handle)
            return bool(ok and exit_code.value == STILL_ACTIVE)
        except Exception:
            return False

    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False

def _acquire_single_instance_lock():
    try:
        if os.path.exists(_LOCK_FILE):
            old_pid = None
            try:
                with open(_LOCK_FILE, "r", encoding="utf-8") as f:
                    old_pid = int((f.read() or "").strip())
            except Exception:
                old_pid = None

            if old_pid and _pid_is_running(old_pid):
                print(f"❌ โปรแกรมกำลังรันอยู่แล้ว (single-instance lock, PID={old_pid}).")
                sys.exit(0)

            try:
                os.remove(_LOCK_FILE)
                print("ℹ️ พบ lock ค้างจากรอบก่อนหน้า -> ลบอัตโนมัติแล้ว")
            except Exception:
                print("❌ พบ lock ค้าง แต่ลบไม่ได้ กรุณาปิดโปรแกรมเดิมหรือสิทธิ์ไม่พอ")
                sys.exit(1)

        with open(_LOCK_FILE, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))

        def _cleanup():
            try:
                if os.path.exists(_LOCK_FILE):
                    owner_pid = None
                    try:
                        with open(_LOCK_FILE, "r", encoding="utf-8") as rf:
                            owner_pid = int((rf.read() or "").strip())
                    except Exception:
                        owner_pid = None
                    if owner_pid in (None, os.getpid()):
                        os.remove(_LOCK_FILE)
            except Exception:
                pass

        atexit.register(_cleanup)
    except Exception:
        pass


# =================================================================================
# 🛡️ SYSTEM PATCHES: ส่วนแก้ไขเร่งด่วน (SPPF & Conv2d Compatibility)
# =================================================================================
def apply_ultralytics_patches():
    try:
        from ultralytics.nn.modules import block

        def patched_sppf_init(self, c1, c2, k=5, *args, **kwargs):
            nn.Module.__init__(self)
            c_ = c1 // 2
            self.cv1 = block.Conv(c1, c_, 1, 1)
            self.cv2 = block.Conv(c_ * 4, c2, 1, 1)
            self.m = nn.MaxPool2d(kernel_size=k, stride=1, padding=k // 2)

        block.SPPF.__init__ = patched_sppf_init
        print("✅ System Patch 1: Applied SPPF compatibility fix.")

        original_conv2d = F.conv2d

        def patched_conv2d(input, weight, bias=None, stride=1, padding=0, dilation=1, groups=1):
            if isinstance(groups, bool):
                in_channels = input.shape[1]
                weight_in_channels = weight.shape[1]
                groups = in_channels // weight_in_channels
            return original_conv2d(input, weight, bias, stride, padding, dilation, groups)

        F.conv2d = patched_conv2d
        print("✅ System Patch 2: Applied Conv2d argument fix.")

    except Exception as e:
        print(f"⚠️ Warning: Patch application failed: {e}")


# =================================================================================
# CUDA / Memory / ปิด AutoBatch
# =================================================================================
def setup_cuda_env():
    torch.cuda.empty_cache()
    os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
    os.environ["YOLO_AUTOBATCH"] = "0"
    os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

    try:
        torch.backends.cudnn.benchmark = False
        torch.set_float32_matmul_precision("high")
        if torch.cuda.is_available():
            torch.backends.cuda.matmul.allow_tf32 = True
            torch.backends.cudnn.allow_tf32 = True
    except Exception:
        pass


# =================================================================================
# Helpers: Progress Popup (Bytes-based)
# =================================================================================
def create_progress_popup(parent, title="กำลังเตรียมโฟลเดอร์/ชุดข้อมูล..."):
    win = tk.Toplevel(parent)
    win.title(title)
    win.geometry("520x160")
    win.resizable(False, False)
    win.attributes("-topmost", True)
    try:
        win.iconify()
        win.deiconify()
    except Exception:
        pass

    frm = tk.Frame(win, padx=14, pady=12)
    frm.pack(fill="both", expand=True)

    label_msg_var = tk.StringVar(value="เริ่มนับจำนวนไบต์ทั้งหมด...")
    tk.Label(frm, textvariable=label_msg_var, font=("Tahoma", 11)).pack(anchor="w", pady=(0, 8))

    pb = ttk.Progressbar(frm, orient="horizontal", length=480, mode="determinate", maximum=100)
    pb.pack(pady=(0, 6))

    label_percent_var = tk.StringVar(value="0%")
    tk.Label(frm, textvariable=label_percent_var, font=("Tahoma", 11, "bold")).pack()

    cancel_state = {"cancel": False}

    def _cancel():
        cancel_state["cancel"] = True

    btn = tk.Button(frm, text="ยกเลิก", command=_cancel, bg="#cc0000", fg="white")
    btn.pack(pady=(10, 0))
    win.protocol("WM_DELETE_WINDOW", _cancel)
    return win, pb, label_msg_var, label_percent_var, cancel_state


def update_progress_bytes(win, pb, label_msg_var, label_percent_var, done_bytes, total_bytes, msg=None):
    if msg:
        label_msg_var.set(msg)
    percent = int(done_bytes * 100 / max(1, total_bytes))
    pb["value"] = percent
    label_percent_var.set(f"{percent}%")
    win.update_idletasks()
    win.update()


def safe_makedirs(p):
    os.makedirs(p, exist_ok=True)


# =================================================================================
# Weight Auto Download (YOLO26) + SSL FIX
# =================================================================================
def get_ultralytics_asset_url(weight_name: str) -> str:
    return f"https://github.com/ultralytics/assets/releases/download/v8.4.0/{weight_name}"


def _build_ssl_context(mode: str, log_fn):
    if mode == "insecure":
        log_fn("⚠️ ใช้โหมด insecure: ไม่ตรวจสอบ SSL certificate (ใช้เฉพาะกรณีจำเป็น!)")
        return ssl._create_unverified_context()

    if mode == "certifi":
        try:
            import certifi
            cafile = certifi.where()
            log_fn(f"ใช้ certifi CA bundle: {cafile}")
            return ssl.create_default_context(cafile=cafile)
        except Exception as e:
            log_fn(f"ไม่สามารถใช้ certifi ได้: {e} -> fallback เป็น default")
            return ssl.create_default_context()

    return ssl.create_default_context()


def _download_file_stream(url: str, dst: str, log_fn, context: ssl.SSLContext, timeout=60):
    safe_makedirs(os.path.dirname(dst))
    tmp = dst + ".part"

    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, context=context, timeout=timeout) as resp:
        total = resp.headers.get("Content-Length")
        total = int(total) if total and total.isdigit() else None

        done = 0
        chunk = 1024 * 256
        with open(tmp, "wb") as f:
            while True:
                buf = resp.read(chunk)
                if not buf:
                    break
                f.write(buf)
                done += len(buf)
                if total:
                    pct = done * 100 // max(1, total)
                    if pct % 10 == 0:
                        log_fn(f"ดาวน์โหลด... {pct}%")
    os.replace(tmp, dst)


def ensure_pretrained_weight(weight_name: str, save_dir: str, log_fn):
    weight_name = (weight_name or "").strip()
    if not weight_name:
        return weight_name

    if os.path.isabs(weight_name) and os.path.exists(weight_name):
        return weight_name

    if os.path.exists(weight_name):
        return os.path.abspath(weight_name)

    wn = weight_name.lower()
    if wn.startswith("yolo") and wn.endswith(".pt"):
        safe_makedirs(save_dir)
        dst = os.path.join(save_dir, weight_name)
        if os.path.exists(dst):
            log_fn(f"พบไฟล์พรีเทรนแล้ว: {dst}")
            return dst

        url = get_ultralytics_asset_url(weight_name)
        log_fn(f"ไม่พบ {weight_name} -> เตรียมดาวน์โหลดจาก: {url}")
        log_fn(f"ปลายทาง: {dst}")

        allow_insecure = os.environ.get("YOLO26_ALLOW_INSECURE_DOWNLOAD", "0").strip() == "1"
        modes = ["default", "certifi"] + (["insecure"] if allow_insecure else [])
        last_err = None

        for mode in modes:
            try:
                ctx = _build_ssl_context(mode, log_fn)
                _download_file_stream(url, dst, log_fn, ctx)
                log_fn(f"✅ ดาวน์โหลดสำเร็จ: {dst}")
                return dst
            except Exception as e:
                last_err = e
                log_fn(f"❌ ดาวน์โหลดล้มเหลว (mode={mode}): {e}")

        hint = (
            "แนวทางแก้:\n"
            "1) ติดตั้ง certifi แล้วลองใหม่:  python -m pip install certifi\n"
            "2) ถ้าเป็นเน็ตโรงงาน/Proxy บล็อก GitHub: ดาวน์โหลดไฟล์ด้วย browser แล้ววางเองตาม path ด้านล่าง\n"
            "3) (ทางเลือกสุดท้าย) ถ้าจำเป็นจริง ๆ ให้ตั้งค่า env เพื่ออนุญาต insecure download:\n"
            "   setx YOLO26_ALLOW_INSECURE_DOWNLOAD 1\n"
            "   แล้วเปิดเทอร์มินอลใหม่/รันใหม่\n"
        )

        raise FileNotFoundError(
            f"ดาวน์โหลด weight ไม่สำเร็จ ({weight_name}).\n\n"
            f"ปลายทางที่ต้องวางไฟล์:\n{dst}\n\n"
            f"URL:\n{url}\n\n"
            f"Error:\n{last_err}\n\n"
            f"{hint}"
        )

    return weight_name


# =================================================================================
# 🖼️ Offline Data Augmentation — เพิ่มรูปจากรูปน้อย (ใช้แค่ Pillow + random)
# =================================================================================
def augment_images_in_folder(train_img_dir: str, train_lbl_dir: str, multiplier: int, log_fn) -> int:
    """
    สร้างรูปเพิ่มใน train folder ด้วย offline augmentation
    - multiplier=5 หมายถึงรูปต้นฉบับ 1 รูป -> รวม 5 รูป (เพิ่ม 4 รูปใหม่)
    - ไม่มี flip ใดๆ — วัตถุอยู่ตำแหน่งเดิมทุกรูป (bbox ไม่เปลี่ยน)
    - เปลี่ยนแค่สี/แสง/เบลอ เท่านั้น
    """
    try:
        from PIL import Image, ImageEnhance, ImageFilter
    except ImportError:
        log_fn("⚠️ ไม่พบ Pillow: pip install Pillow  -> ข้าม augmentation")
        return 0

    existing = [f for f in os.listdir(train_img_dir) if f.lower().endswith((".jpg", ".jpeg", ".png"))]
    if not existing:
        log_fn("⚠️ ไม่พบรูปใน train folder สำหรับ augment")
        return 0

    # ✅ ไม่มี flip ทุกรูปแบบ — วัตถุและ bbox อยู่ตำแหน่งเดิม 100%
    aug_ops_pool = [
        "bright_up",        # สว่างมาก (+35%)
        "bright_down",      # มืดมาก (-35%)
        "bright_mid_up",    # สว่างนิดหน่อย (+15%)
        "bright_mid_down",  # มืดนิดหน่อย (-15%)
        "contrast_up",      # contrast สูง (+40%)
        "contrast_down",    # contrast ต่ำ (-25%)
        "sat_up",           # สีสด (+50%)
        "sat_down",         # สีซีด (-50%)
        "blur",             # เบลอปานกลาง
        "blur_soft",        # เบลอเบา
        "sharp",            # คมชัดขึ้น
        "bright_contrast",  # สว่าง + contrast สูง (รวมกัน)
        "dark_sat",         # มืด + สีซีด (รวมกัน)
    ]

    aug_count = 0
    n_per_img = max(1, multiplier - 1)

    for img_file in existing:
        name = os.path.splitext(img_file)[0]
        img_path = os.path.join(train_img_dir, img_file)
        lbl_path = os.path.join(train_lbl_dir, f"{name}.txt")

        labels_lines: list[str] = []
        if os.path.exists(lbl_path):
            with open(lbl_path, "r", encoding="utf-8") as f:
                raw = [l.strip() for l in f.readlines() if l.strip()]
            # ลบ duplicate labels (เหมือนกันทุกคอลัมน์) ก่อนใช้งาน
            seen: set = set()
            for line in raw:
                if line not in seen:
                    seen.add(line)
                    labels_lines.append(line)

        try:
            img = Image.open(img_path).convert("RGB")
        except Exception as e:
            log_fn(f"⚠️ เปิดรูปไม่ได้ {img_file}: {e}")
            continue

        chosen_ops = random.sample(aug_ops_pool, min(n_per_img, len(aug_ops_pool)))

        for op in chosen_ops:
            aug_img = img.copy()
            # ✅ aug_lbls ไม่มีการเปลี่ยนแปลง bbox เลย — ทุก op ด้านล่างแตะแค่ภาพ

            if op == "bright_up":
                aug_img = ImageEnhance.Brightness(aug_img).enhance(1.35)
            elif op == "bright_down":
                aug_img = ImageEnhance.Brightness(aug_img).enhance(0.65)
            elif op == "bright_mid_up":
                aug_img = ImageEnhance.Brightness(aug_img).enhance(1.15)
            elif op == "bright_mid_down":
                aug_img = ImageEnhance.Brightness(aug_img).enhance(0.85)
            elif op == "contrast_up":
                aug_img = ImageEnhance.Contrast(aug_img).enhance(1.4)
            elif op == "contrast_down":
                aug_img = ImageEnhance.Contrast(aug_img).enhance(0.75)
            elif op == "sat_up":
                aug_img = ImageEnhance.Color(aug_img).enhance(1.5)
            elif op == "sat_down":
                aug_img = ImageEnhance.Color(aug_img).enhance(0.5)
            elif op == "blur":
                aug_img = aug_img.filter(ImageFilter.GaussianBlur(radius=1.5))
            elif op == "blur_soft":
                aug_img = aug_img.filter(ImageFilter.GaussianBlur(radius=0.8))
            elif op == "sharp":
                aug_img = ImageEnhance.Sharpness(aug_img).enhance(2.0)
            elif op == "bright_contrast":
                aug_img = ImageEnhance.Brightness(aug_img).enhance(1.2)
                aug_img = ImageEnhance.Contrast(aug_img).enhance(1.3)
            elif op == "dark_sat":
                aug_img = ImageEnhance.Brightness(aug_img).enhance(0.75)
                aug_img = ImageEnhance.Color(aug_img).enhance(0.6)

            suffix = f"_aug{aug_count:06d}_{op}"
            out_img = os.path.join(train_img_dir, f"{name}{suffix}.jpg")
            aug_img.save(out_img, "JPEG", quality=93)

            # bbox ไม่เปลี่ยนเลย — คัดลอก label ต้นฉบับทุกครั้ง
            if labels_lines:
                out_lbl = os.path.join(train_lbl_dir, f"{name}{suffix}.txt")
                with open(out_lbl, "w", encoding="utf-8") as f:
                    f.write("\n".join(labels_lines))

            aug_count += 1

    log_fn(f"✅ Augmentation เสร็จ: เพิ่ม {aug_count} รูป (รวมทั้งหมด {len(existing) + aug_count} รูป ใน train)")
    return aug_count


# =================================================================================
# main() — defaults tuned for RTX 5090 (~32GB) + 128GB RAM (cache=ram, workers↑, batch caps↑)
# =================================================================================
def main():
    apply_ultralytics_patches()
    setup_cuda_env()

    # Force GPU-only training (show error if CUDA not available)
    FORCE_GPU = True
    # Force RAM cache for dataset loading (no disk/false fallback)
    FORCE_RAM_CACHE = True
    device = 0 if torch.cuda.is_available() else "cpu"

    # =============================
    # เลือกโฟลเดอร์ต้นทาง
    # =============================
    root = tk.Tk()
    root.withdraw()

    source_folder = filedialog.askdirectory(
        title="เลือกโฟลเดอร์ที่มีไฟล์ .jpg / .jpeg / .png และ .txt"
    )
    if not source_folder:
        print("❌ ไม่ได้เลือกโฟลเดอร์ ยกเลิกการทำงาน")
        root.destroy()
        raise SystemExit

    # =============================
    # Progress เตรียม dataset
    # =============================
    progress_win, progress_bar, progress_msg, progress_percent, progress_flag = create_progress_popup(
        root, "กำลังสร้างชุดข้อมูล (dataset) สำหรับเทรน..."
    )
    progress_msg.set("กำลังสแกนไฟล์ภาพ/เลเบล...")
    progress_win.update()

    images = [f for f in os.listdir(source_folder) if f.lower().endswith((".jpg", ".jpeg", ".png"))]
    labels = [f for f in os.listdir(source_folder) if f.lower().endswith(".txt") and f != "classes.txt"]
    if not images or not labels:
        progress_win.destroy()
        messagebox.showerror("ไฟล์ไม่ครบ", "❌ ไม่พบไฟล์ภาพ (.jpg/.jpeg/.png) หรือไฟล์เลเบล (.txt)")
        root.destroy()
        raise SystemExit

    classes_path = os.path.join(source_folder, "classes.txt")
    if not os.path.exists(classes_path):
        progress_win.destroy()
        messagebox.showerror("ไฟล์ไม่ครบ", "❌ ไม่พบไฟล์ classes.txt")
        root.destroy()
        raise SystemExit

    with open(classes_path, "r", encoding="utf-8") as f:
        classes = [line.strip() for line in f.readlines() if line.strip()]

    if not classes:
        progress_win.destroy()
        messagebox.showerror("classes.txt ว่าง", "❌ classes.txt ไม่มีชื่อคลาส")
        root.destroy()
        raise SystemExit

    parent_dir = os.path.dirname(source_folder)
    folder_name = os.path.basename(source_folder)

    custom_run_dir = os.path.join(parent_dir, folder_name + "_WeightYolo26")
    dataset_dir = os.path.join(custom_run_dir, "dataset")

    progress_msg.set("กำลังเตรียมโฟลเดอร์ dataset..."); progress_win.update()

    # ตรวจว่ามี dataset เดิม (พร้อม augmentation) อยู่แล้วหรือไม่
    use_existing_dataset = False
    _train_img_dir_check = os.path.join(dataset_dir, "images", "train")
    _data_yaml_check     = os.path.join(dataset_dir, "data.yaml")
    if os.path.exists(_train_img_dir_check) and os.path.exists(_data_yaml_check):
        _existing_count = len([
            f for f in os.listdir(_train_img_dir_check)
            if f.lower().endswith((".jpg", ".jpeg", ".png"))
        ])
        if _existing_count > 0:
            progress_win.iconify()   # ซ่อน progress ชั่วคราว
            _ans = messagebox.askyesno(
                "พบ Dataset เดิม",
                f"พบ dataset ที่เตรียมไว้แล้ว:\n{dataset_dir}\n\n"
                f"ภาพ train ที่มีอยู่: {_existing_count} ใบ\n"
                f"(รวม Augmentation ที่เคยสร้างไว้)\n\n"
                f"✅ YES = ใช้ dataset เดิมเลย (ข้าม copy + augmentation)\n"
                f"❌ NO  = ลบแล้วสร้าง dataset ใหม่จากต้นฉบับ\n",
                icon="question"
            )
            progress_win.deiconify()
            if _ans:
                use_existing_dataset = True

    if not use_existing_dataset:
        if os.path.exists(dataset_dir):
            shutil.rmtree(dataset_dir, ignore_errors=True)
        for sub in ["images/train", "images/val", "labels/train", "labels/val"]:
            os.makedirs(os.path.join(dataset_dir, sub), exist_ok=True)

    val_ratio = 0.2
    val_count = max(1, int(len(images) * val_ratio))
    train_imgs, val_imgs = train_test_split(images, test_size=val_count, random_state=42)

    def sum_bytes(file_list):
        total = 0
        for img in file_list:
            img_path = os.path.join(source_folder, img)
            if os.path.exists(img_path):
                total += os.path.getsize(img_path)
            lbl = f"{os.path.splitext(img)[0]}.txt"
            lbl_path = os.path.join(source_folder, lbl)
            if lbl in labels and os.path.exists(lbl_path):
                total += os.path.getsize(lbl_path)
        return total

    total_bytes = sum_bytes(train_imgs) + sum_bytes(val_imgs)
    extra_bytes = 512 * 1024
    total_bytes += extra_bytes
    done_bytes = 0

    def copy_with_progress_bytes(src, dst, msg, chunk_size=1024 * 1024):
        nonlocal done_bytes
        if progress_flag["cancel"]:
            raise KeyboardInterrupt("ผู้ใช้ยกเลิกระหว่างเตรียมไฟล์")
        if not os.path.exists(src):
            return

        size = os.path.getsize(src)
        copied = 0
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(src, "rb") as fsrc, open(dst, "wb") as fdst:
            while True:
                if progress_flag["cancel"]:
                    raise KeyboardInterrupt("ผู้ใช้ยกเลิกระหว่างเตรียมไฟล์")
                buf = fsrc.read(chunk_size)
                if not buf:
                    break
                fdst.write(buf)
                copied += len(buf)
                done_bytes += len(buf)
                update_progress_bytes(
                    progress_win, progress_bar, progress_msg, progress_percent,
                    done_bytes, total_bytes,
                    f"{msg} ({copied*100//max(1,size)}% ของไฟล์นี้)"
                )
        try:
            shutil.copystat(src, dst)
        except Exception:
            pass

    def move_files(file_list, split):
        base_msg = f"กำลังคัดลอก {split}..."
        for img_file in file_list:
            name = os.path.splitext(img_file)[0]
            label_file = f"{name}.txt"

            copy_with_progress_bytes(
                os.path.join(source_folder, img_file),
                os.path.join(dataset_dir, f"images/{split}", img_file),
                f"{base_msg} ภาพ: {img_file}"
            )

            if label_file in labels:
                copy_with_progress_bytes(
                    os.path.join(source_folder, label_file),
                    os.path.join(dataset_dir, f"labels/{split}", label_file),
                    f"{base_msg} เลเบล: {label_file}"
                )

    try:
        if use_existing_dataset:
            # ข้าม copy ทั้งหมด — ใช้ dataset เดิมที่มี aug อยู่แล้ว
            progress_msg.set("✅ ใช้ dataset เดิม (ข้าม copy + augmentation)")
            progress_win.update()
            data_yaml_path = os.path.join(dataset_dir, "data.yaml")
            time.sleep(0.3)
        else:
            move_files(train_imgs, "train")
            move_files(val_imgs, "val")

            data_yaml_path = os.path.join(dataset_dir, "data.yaml")
            progress_msg.set("กำลังเขียน data.yaml ..."); progress_win.update()
            with open(data_yaml_path, "w", encoding="utf-8") as f:
                f.write(f"path: {dataset_dir}\n")
                f.write("train: images/train\n")
                f.write("val: images/val\n")
                f.write(f"nc: {len(classes)}\n")
                f.write(f"names: {classes}\n")

            done_bytes += extra_bytes
            update_progress_bytes(
                progress_win, progress_bar, progress_msg, progress_percent,
                done_bytes, total_bytes,
                "บันทึก data.yaml สำเร็จ"
            )
            time.sleep(0.15)

    except KeyboardInterrupt:
        progress_win.destroy()
        messagebox.showwarning("ยกเลิก", "ยกเลิกการเตรียมไฟล์แล้ว")
        root.destroy()
        raise SystemExit
    except Exception as e:
        progress_win.destroy()
        messagebox.showerror("ข้อผิดพลาดระหว่างเตรียมไฟล์", str(e))
        root.destroy()
        raise SystemExit
    finally:
        if progress_win.winfo_exists():
            progress_win.destroy()

    # =============================
    # GUI หลัก
    # =============================
    root.deiconify()
    root.title(
        "YOLO26 Training Monitor (RTX 5090 32GB + 128GB RAM) [GPU-only]"
        + (" — ✅ ใช้ Dataset เดิม (มี Augmentation แล้ว)" if use_existing_dataset else "")
    )
    root.geometry("900x850")

    start_dt = datetime.now()
    start_label = tk.Label(root, text=f"🕒 เริ่มเทรน: {start_dt.strftime('%H:%M:%S')}", font=("Tahoma", 12))
    start_label.pack(pady=5)

    gpu_ready = torch.cuda.is_available()
    gpu_status_var = tk.StringVar(
        value=(
            "🟢 GPU-only mode: พร้อม (จะเทรนบน CUDA เท่านั้น)"
            if gpu_ready
            else "🔴 GPU-only mode: ไม่พร้อม (ไม่พบ CUDA GPU)"
        )
    )
    gpu_status_label = tk.Label(root, textvariable=gpu_status_var, font=("Tahoma", 11, "bold"), fg=("#0a7f2e" if gpu_ready else "red"))
    gpu_status_label.pack(pady=(0, 6))

    default_model   = "yolo26x.pt"
    # Defaults tuned for RTX 5090 (~32GB VRAM) + 128GB system RAM + YOLO26x-class models
    default_imgsz   = 640
    default_epochs  = 200
    _vram_gb = 0.0
    if torch.cuda.is_available():
        try:
            _vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
        except Exception:
            _vram_gb = 0.0
    # Starting batch before Auto Ramp caps; aligns with _pick_stable_batch caps
    if _vram_gb >= 30:
        default_batch = 32
    elif _vram_gb >= 24:
        default_batch = 24
    elif _vram_gb >= 16:
        default_batch = 16
    elif _vram_gb >= 12:
        default_batch = 12
    elif torch.cuda.is_available():
        default_batch = 8
    else:
        default_batch = 4

    amp_var = tk.BooleanVar(value=True)
    auto_ramp_var = tk.BooleanVar(value=True)

    # 128GB RAM: feed GPU — use more dataloader workers (capped in start_training on Windows)
    _cpu_count = os.cpu_count() or 16
    workers_var = tk.IntVar(value=min(16, max(10, (_cpu_count * 3) // 4)))

    # Use RAM cache by default (fastest) on a high-RAM machine.
    cache_mode_var = tk.StringVar(value="ram")  # disk | false | ram

    # Offline Augmentation
    # ถ้าใช้ dataset เดิม (มี aug แล้ว) → ปิด aug อัตโนมัติ
    aug_var = tk.BooleanVar(value=False if use_existing_dataset else False)
    aug_multiplier_var = tk.IntVar(value=2)  # ถ้าเปิด: แค่ 2x ก็พอ (เพิ่ม 1 ชุด)

    # Resume Training
    resume_var = tk.BooleanVar(value=False)

    # ----- Task (BBOX / SEG) + Model dropdown
    model_frame = tk.Frame(root); model_frame.pack(pady=4)
    tk.Label(model_frame, text="🎯 Task:", font=("Tahoma", 12)).pack(side="left")
    task_var = tk.StringVar(value="detect")
    task_cb = ttk.Combobox(
        model_frame,
        textvariable=task_var,
        values=["detect", "segment"],
        state="readonly",
        width=10
    )
    task_cb.pack(side="left", padx=6)

    tk.Label(model_frame, text="🧠 Model:", font=("Tahoma", 12)).pack(side="left")
    model_var = tk.StringVar(value=default_model)
    model_cb = ttk.Combobox(
        model_frame,
        textvariable=model_var,
        values=["yolo26n.pt", "yolo26s.pt", "yolo26m.pt", "yolo26l.pt", "yolo26x.pt"],
        state="readonly",
        width=18
    )
    model_cb.pack(side="left", padx=6)

    detect_models = ["yolo26n.pt", "yolo26s.pt", "yolo26m.pt", "yolo26l.pt", "yolo26x.pt"]
    seg_models = ["yolov8n-seg.pt", "yolov8s-seg.pt", "yolov8m-seg.pt", "yolov8l-seg.pt", "yolov8x-seg.pt"]

    def _on_task_change(_evt=None):
        t = (task_var.get() or "detect").strip().lower()
        vals = seg_models if t == "segment" else detect_models
        model_cb.configure(values=vals)
        if model_var.get() not in vals:
            # Default to largest (X) when switching task — matches yolo26x / yolov8x-seg
            model_var.set(vals[-1] if vals else default_model)

    task_cb.bind("<<ComboboxSelected>>", _on_task_change)
    _on_task_change()

    # ----- Epoch
    epoch_frame = tk.Frame(root); epoch_frame.pack(pady=2)
    tk.Label(epoch_frame, text="🔢 Epochs:", font=("Tahoma", 12)).pack(side="left")
    epoch_entry = tk.Entry(epoch_frame, width=8)
    epoch_entry.insert(0, str(default_epochs))
    epoch_entry.pack(side="left", padx=5)

    # ----- imgsz
    imgsz_frame = tk.Frame(root); imgsz_frame.pack(pady=2)
    tk.Label(imgsz_frame, text="📏 Image Size:", font=("Tahoma", 12)).pack(side="left")
    imgsz_spinbox = tk.Spinbox(imgsz_frame, from_=320, to=1536, increment=32, width=10)
    imgsz_spinbox.delete(0, "end"); imgsz_spinbox.insert(0, str(default_imgsz))
    imgsz_spinbox.pack(side="left", padx=6)

    cancel_training = False
    training_done = False
    start_time = 0

    # ===== Labels =====
    final_params_var = tk.StringVar(value="พารามิเตอร์สุดท้าย: —")
    final_params_label = tk.Label(root, textvariable=final_params_var, font=("Tahoma", 11, "bold"), fg="#006699")
    final_params_label.pack(pady=(4, 6))

    finish_label = tk.Label(root, text="🕗 คาดว่าจะเสร็จ: --:--:--", font=("Tahoma", 12)); finish_label.pack(pady=5)
    progress_label = tk.Label(root, text="🔋 ความคืบหน้า: 0%", font=("Tahoma", 12)); progress_label.pack()
    countdown_label = tk.Label(root, text="⏳ เทรนไปแล้ว: 0 นาที 0 วินาที", font=("Tahoma", 12), fg="blue"); countdown_label.pack(pady=3)
    status_label = tk.Label(root, text="🔄 รอเริ่มการเทรน...", font=("Tahoma", 12)); status_label.pack(pady=6)

    # ===== Options frame =====
    push_frame = tk.LabelFrame(root, text="⚡ GPU Push Options", padx=10, pady=8, font=("Tahoma", 11, "bold"))
    push_frame.pack(fill="x", padx=10, pady=(4, 4))

    tk.Checkbutton(push_frame, text="Auto Ramp Batch (หา batch สูงสุดที่ไม่ OOM)", variable=auto_ramp_var)\
        .grid(row=0, column=0, sticky="w", padx=4, pady=2)
    tk.Checkbutton(push_frame, text="Enable AMP (เร็วขึ้น/ใช้ GPU สูงขึ้น)", variable=amp_var)\
        .grid(row=1, column=0, sticky="w", padx=4, pady=2)

    tk.Label(push_frame, text="Dataloader workers:", font=("Tahoma", 10))\
        .grid(row=0, column=1, sticky="e", padx=(20, 6))
    tk.Spinbox(push_frame, from_=0, to=max(32, (os.cpu_count() or 16) + 16),
               increment=1, textvariable=workers_var, width=6)\
        .grid(row=0, column=2, sticky="w")

    tk.Label(push_frame, text="Cache mode:", font=("Tahoma", 10))\
        .grid(row=1, column=1, sticky="e", padx=(20, 6))
    ttk.Combobox(push_frame, textvariable=cache_mode_var,
                 values=["disk", "false", "ram"], state="readonly", width=8)\
        .grid(row=1, column=2, sticky="w")

    # ===== Augmentation Frame =====
    aug_frame = tk.LabelFrame(root, text="🖼️ Offline Augmentation — เพิ่มรูปอัตโนมัติก่อนเทรน",
                               padx=10, pady=8, font=("Tahoma", 11, "bold"))
    aug_frame.pack(fill="x", padx=10, pady=(0, 4))

    tk.Checkbutton(
        aug_frame,
        text="เปิดใช้ Augmentation (สร้างรูปเพิ่มจากรูปต้นฉบับ)",
        variable=aug_var,
        font=("Tahoma", 10)
    ).grid(row=0, column=0, columnspan=2, sticky="w", padx=4, pady=2)

    tk.Label(aug_frame, text="จำนวนรูปสุดท้ายต่อ 1 รูปต้นฉบับ (Multiplier):", font=("Tahoma", 10))\
        .grid(row=1, column=0, sticky="e", padx=(4, 6))
    aug_spin = tk.Spinbox(aug_frame, from_=2, to=12, increment=1,
                          textvariable=aug_multiplier_var, width=6)
    aug_spin.grid(row=1, column=1, sticky="w")
    tk.Label(aug_frame,
             text="  ตัวอย่าง: 50 รูป × multiplier=5 = 250 รูป train  |  แนะนำ 3-8",
             font=("Tahoma", 9), fg="#555555")\
        .grid(row=2, column=0, columnspan=3, sticky="w", padx=4)

    # ===== Resume Frame =====
    resume_frame = tk.LabelFrame(root, text="🔁 Resume Training — เทรนต่อจากของเดิม",
                                  padx=10, pady=8, font=("Tahoma", 11, "bold"), fg="#7b1fa2")
    resume_frame.pack(fill="x", padx=10, pady=(0, 4))

    def _on_resume_toggle():
        if resume_var.get():
            last_pt = os.path.join(
                os.path.dirname(source_folder),
                os.path.basename(source_folder) + "_WeightYolo26",
                "train", "weights", "last.pt"
            )
            if not os.path.exists(last_pt):
                messagebox.showwarning(
                    "ไม่พบ last.pt",
                    f"ไม่พบไฟล์:\n{last_pt}\n\n"
                    "ต้องเคยเทรนด้วย dataset เดิมนี้ก่อน\n"
                    "จึงจะ Resume ได้"
                )
                resume_var.set(False)
                return
            resume_path_var.set(f"✅ last.pt: {last_pt}")
        else:
            resume_path_var.set("")

    tk.Checkbutton(
        resume_frame,
        text="เทรนต่อจาก last.pt (ไม่เริ่มใหม่ ไม่ลบผลเดิม)",
        variable=resume_var,
        command=_on_resume_toggle,
        font=("Tahoma", 10)
    ).grid(row=0, column=0, columnspan=2, sticky="w", padx=4, pady=2)

    resume_path_var = tk.StringVar(value="")
    tk.Label(resume_frame, textvariable=resume_path_var,
             font=("Tahoma", 8), fg="#4a148c", wraplength=780, anchor="w")\
        .grid(row=1, column=0, columnspan=2, sticky="w", padx=4)

    tk.Label(resume_frame,
             text="  ⚠️ เมื่อ Resume: epoch/imgsz/batch ถูกอ่านจาก checkpoint เดิมอัตโนมัติ  "
                  "|  ปรับ Epochs ใน box บนเพื่อกำหนดยอดรวมทั้งหมด",
             font=("Tahoma", 9), fg="#555")\
        .grid(row=2, column=0, columnspan=2, sticky="w", padx=4)

    # ===== Log UI =====
    log_frame = tk.LabelFrame(root, text="Logs (Realtime)", padx=6, pady=6, font=("Tahoma", 11, "bold"))
    log_frame.pack(fill="both", expand=True, padx=10, pady=8)
    log_text = ScrolledText(log_frame, height=16, wrap="word", font=("Consolas", 10))
    log_text.pack(fill="both", expand=True)
    log_text.configure(state="disabled")

    def gui_log(message: str):
        ts = datetime.now().strftime("%H:%M:%S")
        def _append():
            log_text.configure(state="normal")
            log_text.insert("end", f"[{ts}] {message}\n")
            log_text.see("end")
            log_text.configure(state="disabled")
        root.after(0, _append)

    class _StdRedirector:
        def __init__(self, write_fn): self._write_fn = write_fn
        def write(self, s):
            s = s.rstrip()
            if s: self._write_fn(s)
        def flush(self): pass

    def sec_to_str(sec: float) -> str:
        sec = int(max(0, sec)); m, s = divmod(sec, 60); h, m = divmod(m, 60)
        return f"{h} ชม {m} นาที {s} วินาที" if h else f"{m} นาที {s} วินาที"

    def _resolve_cache_value():
        if FORCE_RAM_CACHE:
            return "ram"
        v = (cache_mode_var.get() or "disk").strip().lower()
        if v == "false":
            return False
        if v == "ram":
            return "ram"
        return "disk"  # default

    def countdown():
        nonlocal training_done, cancel_training, start_time
        while not training_done and not cancel_training:
            elapsed = int(time.time() - start_time)
            mins, secs = divmod(elapsed, 60)
            root.after(0, lambda m=mins, s=secs: countdown_label.config(text=f"⏳ เทรนไปแล้ว: {m} นาที {s} วินาที"))
            time.sleep(1)

    def make_minimal_weight_pack(train_dir: str, weight_pack_dir: str, classes_list, src_classes_path: str):
        os.makedirs(weight_pack_dir, exist_ok=True)
        weights_src = os.path.join(train_dir, "weights")
        best_pt = os.path.join(weights_src, "best.pt")
        if not os.path.exists(best_pt):
            raise FileNotFoundError("ไม่พบไฟล์ best.pt หลังการเทรน")
        shutil.copy2(best_pt, os.path.join(weight_pack_dir, "best.pt"))

        if os.path.exists(src_classes_path):
            shutil.copy2(src_classes_path, os.path.join(weight_pack_dir, "classes.txt"))
        else:
            with open(os.path.join(weight_pack_dir, "classes.txt"), "w", encoding="utf-8") as f:
                f.write("\n".join(classes_list))

        with open(os.path.join(weight_pack_dir, "data.yaml"), "w", encoding="utf-8") as f:
            f.write(f"nc: {len(classes_list)}\n")
            f.write(f"names: {classes_list}\n")

    def train_model(model_name, imgsz_start, epochs, workers, use_amp, auto_ramp, use_aug, aug_multiplier, do_resume):
        nonlocal training_done, device, cancel_training, start_time

        orig_stdout, orig_stderr = sys.stdout, sys.stderr
        sys.stdout = _StdRedirector(gui_log)
        sys.stderr = _StdRedirector(gui_log)

        # GPU-only: do not allow CPU training.
        if not torch.cuda.is_available():
            raise RuntimeError("GPU-only mode: ไม่พบ CUDA GPU (กรุณาติดตั้ง PyTorch แบบ CUDA และไดรเวอร์ NVIDIA ให้พร้อม)")
        device = 0  # forced cuda:0

        # ===== Resume: โหลด last.pt แล้วเทรนต่อทันที =====
        if do_resume:
            last_pt = os.path.join(custom_run_dir, "train", "weights", "last.pt")
            if not os.path.exists(last_pt):
                sys.stdout, sys.stderr = orig_stdout, orig_stderr
                root.after(0, lambda: messagebox.showerror(
                    "Resume Error",
                    f"ไม่พบ last.pt:\n{last_pt}\n\nกรุณาปิด Resume แล้วเริ่มเทรนใหม่"
                ))
                training_done = True
                return
            try:
                gui_log(f"[RESUME] โหลด last.pt: {last_pt}")
                model_r = YOLO(last_pt)
                torch.cuda.empty_cache()
                gui_log(f"[RESUME] เริ่ม resume training (epochs รวม = {epochs})")
                model_r.train(resume=True)
                gui_log("[RESUME] ✅ Resume เสร็จสมบูรณ์")
            except Exception as e:
                gui_log(f"[RESUME] ❌ Error: {e}")
                sys.stdout, sys.stderr = orig_stdout, orig_stderr
                root.after(0, lambda: messagebox.showerror("Resume Error", str(e)))
                training_done = True
                return

            # copy best.pt ออก weight_pack
            try:
                train_dir_r = os.path.join(custom_run_dir, "train")
                weight_pack_dir = os.path.join(custom_run_dir, "weight_pack")
                if os.path.isdir(weight_pack_dir):
                    shutil.rmtree(weight_pack_dir, ignore_errors=True)
                make_minimal_weight_pack(train_dir_r, weight_pack_dir, classes, classes_path)
                gui_log(f"[RESUME] weight_pack อัปเดตแล้ว: {weight_pack_dir}")
            except Exception as e:
                gui_log(f"[RESUME] ⚠️ weight_pack: {e}")

            training_done = True
            elapsed = int(time.time() - start_time)
            m, s = divmod(elapsed, 60)
            root.after(0, lambda: status_label.config(
                text=f"✅ Resume เสร็จ | ใช้เวลา {m} นาที {s} วินาที", fg="green"))
            sys.stdout, sys.stderr = orig_stdout, orig_stderr
            return

        # ===== Offline Augmentation (ก่อนเทรน — เฉพาะ Normal mode) =====
        if use_existing_dataset:
            gui_log("[AUG] ข้าม augmentation — ใช้ dataset เดิมที่มี augmentation แล้ว ✅")
        elif use_aug:
            train_img_dir = os.path.join(dataset_dir, "images", "train")
            train_lbl_dir = os.path.join(dataset_dir, "labels", "train")
            gui_log(f"[AUG] กำลังสร้างรูปเพิ่ม (x{aug_multiplier}) ใน train folder...")
            try:
                aug_added = augment_images_in_folder(train_img_dir, train_lbl_dir, aug_multiplier, gui_log)
                gui_log(f"[AUG] เพิ่ม {aug_added} รูปเรียบร้อย ✅")
            except Exception as e:
                gui_log(f"[AUG] ⚠️ augmentation มีปัญหา (ข้ามแล้วเทรนปกติ): {e}")

        pretrained_dir = os.path.join(custom_run_dir, "pretrained")
        try:
            model_path = ensure_pretrained_weight(model_name, pretrained_dir, gui_log)
        except Exception as e:
            sys.stdout, sys.stderr = orig_stdout, orig_stderr
            root.after(0, lambda: messagebox.showerror("Load Model Error", str(e)))
            training_done = True
            return

        try:
            model = YOLO(model_path)
            gui_log(f"โหลดโมเดลสำเร็จ: {model_path}")
        except Exception as e:
            sys.stdout, sys.stderr = orig_stdout, orig_stderr
            root.after(0, lambda: messagebox.showerror("Load Model Error", f"โหลดโมเดลไม่สำเร็จ: {e}\n\npath: {model_path}"))
            training_done = True
            return

        EMA_ALPHA = 0.35
        state = {"epoch_t0": None, "ema_epoch_sec": None}

        def on_start(trainer):
            state["epoch_t0"] = time.time()

        def on_end(trainer):
            if state["epoch_t0"] is None:
                return
            sec = time.time() - state["epoch_t0"]
            state["ema_epoch_sec"] = sec if state["ema_epoch_sec"] is None else \
                (EMA_ALPHA * sec + (1 - EMA_ALPHA) * state["ema_epoch_sec"])
            done = trainer.epoch + 1
            remain = max(0, epochs - done)
            avg = state["ema_epoch_sec"] * 1.06
            est = datetime.now() + timedelta(seconds=remain * avg)

            root.after(0, lambda:
                progress_label.config(text=f"🔋 ความคืบหน้า: {done/epochs*100:.1f}%")
            )
            root.after(0, lambda:
                finish_label.config(text=f"🕗 คาดว่าจะเสร็จ: {est.strftime('%H:%M:%S')} (เหลือ {sec_to_str(remain * avg)})")
            )

            if cancel_training:
                trainer.stop = True
            gui_log(f"Epoch {done}/{epochs} | ETA {sec_to_str(remain * avg)}")

        model.add_callback("on_train_epoch_start", on_start)
        model.add_callback("on_train_epoch_end", on_end)

        selected = {"imgsz": None, "batch": None}
        data_yaml_path = os.path.join(dataset_dir, "data.yaml")

        def _is_recoverable_runtime_error(msg: str) -> bool:
            m = (msg or "").lower()
            keys = [
                "cuda out of memory",
                "cudnn",
                "dataloader worker",
                "worker exited unexpectedly",
                "illegal memory access",
                "device-side assert",
                "cublas",
            ]
            return any(k in m for k in keys)

        def _train_once_with_overrides(imgsz, batch, cache_val, workers_override, amp_override):
            root.after(0, lambda:
                final_params_var.set(
                    f"กำลังลอง: imgsz={imgsz}, batch={batch}, workers={workers_override}, amp={'ON' if amp_override else 'OFF'}, cache={cache_val}"
                )
            )
            gui_log(
                f"ลองเทรนด้วย imgsz={imgsz}, batch={batch}, workers={workers_override}, cache={cache_val}, amp={amp_override}"
            )
            extra_task = {}
            try:
                if (task_var.get() or 'detect').strip().lower() == 'segment':
                    extra_task['task'] = 'segment'
            except Exception:
                pass
            return model.train(
                **extra_task,
                data=data_yaml_path,
                epochs=epochs,
                imgsz=imgsz,
                batch=batch,
                device=device,
                workers=workers_override,
                cache=cache_val,
                amp=amp_override,
                optimizer="AdamW",
                cos_lr=True,
                lr0=0.01,
                lrf=0.005,          # ลด LR สุดท้ายให้ fine-tune ได้ดีขึ้น
                warmup_epochs=3,    # warm-up ก่อนเทรนจริง ลด spike ช่วงแรก
                weight_decay=0.0005,
                patience=30,        # เพิ่ม patience เพราะ dataset เล็ก
                # --- Online augmentation ที่ YOLO ทำระหว่าง train ---
                hsv_h=0.015,        # สุ่ม hue ±1.5%
                hsv_s=0.7,          # สุ่ม saturation ±70%
                hsv_v=0.4,          # สุ่ม brightness ±40%
                mosaic=0.8,         # ลดจาก 1.0 — dataset หลากหลายอยู่แล้ว ไม่ต้อง mosaic เต็ม
                mixup=0.05,         # ลดกลับ — dataset ใหญ่ mixup มากเกินทำให้สับสน
                copy_paste=0.05,
                close_mosaic=20,    # ปิด mosaic ช่วง 20 epoch สุดท้าย ให้โมเดล fine-tune ตรงๆ
                degrees=10.0,       # หมุน ±10° (เพิ่มจาก 5°)
                translate=0.1,
                scale=0.5,
                shear=2.0,          # เพิ่ม shear เล็กน้อย
                perspective=0.0005,
                fliplr=0.0,         # ปิด flip ซ้าย-ขวา — วัตถุต้องอยู่ตำแหน่งเดิม
                flipud=0.0,         # ปิด flip บน-ล่าง
                label_smoothing=0.05,  # ลด overfit บน dataset เล็ก
                project=custom_run_dir,
                name="train",
                exist_ok=True,
                verbose=True,
            )

        def _run_train_resilient(imgsz, batch, cache_val):
            if FORCE_RAM_CACHE:
                cache_val = "ram"
                gui_log("[RESILIENT] 🔒 Force cache=ram (ไม่ fallback ไป disk/false)")

            attempt_plan = [
                (workers, use_amp, cache_val, "ค่าที่ผู้ใช้เลือก"),
                (0, use_amp, cache_val, "ลด workers=0"),
                (0, False, cache_val, "ปิด AMP"),
            ]
            last_err = None

            for idx, (w, a, c, tag) in enumerate(attempt_plan, start=1):
                if cancel_training:
                    raise RuntimeError("ผู้ใช้ยกเลิกการเทรน")
                try:
                    torch.cuda.empty_cache()
                    gui_log(f"[RESILIENT] Attempt {idx}/{len(attempt_plan)}: {tag}")
                    return _train_once_with_overrides(imgsz, batch, c, w, a), w, a, c
                except MemoryError as e:
                    last_err = e
                    gui_log(f"[RESILIENT] ❌ MemoryError (RAM/cache เต็ม) [cache=ram]: {e}")
                    time.sleep(0.5)
                    continue
                except RuntimeError as e:
                    last_err = e
                    msg = str(e)
                    gui_log(f"[RESILIENT] ล้มเหลว: {msg}")
                    if not _is_recoverable_runtime_error(msg):
                        raise
                    time.sleep(0.35)
                    continue
                except Exception as e:
                    last_err = e
                    gui_log(f"[RESILIENT] ล้มเหลวแบบไม่คาดคิด: {e}")
                    continue

            raise RuntimeError(f"train ล้มเหลวทุกโหมด fallback: {last_err}")

        def _pick_stable_batch(imgsz, start_batch):
            b = max(1, int(start_batch))
            if not torch.cuda.is_available():
                return 1
            try:
                total_gb = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
            except Exception:
                total_gb = 8.0

            ig = int(imgsz)
            v = float(total_gb)
            # Caps for YOLO26x / YOLOv8x-sized models (AMP on). RTX 5090 ~32GB tier uses high caps.
            if v >= 30:
                if ig >= 1280:
                    cap = 8
                elif ig >= 1024:
                    cap = 12
                elif ig >= 896:
                    cap = 20
                elif ig >= 768:
                    cap = 28
                elif ig >= 640:
                    cap = 40
                else:
                    cap = 48
            elif v >= 24:
                if ig >= 1280:
                    cap = 6
                elif ig >= 1024:
                    cap = 10
                elif ig >= 896:
                    cap = 14
                elif ig >= 768:
                    cap = 20
                elif ig >= 640:
                    cap = 28
                else:
                    cap = 36
            elif v >= 16:
                if ig >= 1280:
                    cap = 4
                elif ig >= 1024:
                    cap = 8
                elif ig >= 896:
                    cap = 10
                elif ig >= 768:
                    cap = 14
                elif ig >= 640:
                    cap = 20
                else:
                    cap = 24
            elif v >= 12:
                if ig >= 1024:
                    cap = 4
                elif ig >= 896:
                    cap = 6
                elif ig >= 768:
                    cap = 8
                elif ig >= 640:
                    cap = 12
                else:
                    cap = 16
            elif v >= 9:
                if ig >= 896:
                    cap = 4
                elif ig >= 640:
                    cap = 8
                else:
                    cap = 12
            else:
                if ig >= 1280 or v < 5:
                    cap = 1
                elif ig >= 1024 or v < 7:
                    cap = 2
                elif ig >= 896 or v < 9:
                    cap = 4
                elif ig >= 640:
                    cap = 8
                else:
                    cap = 12

            chosen = max(1, min(b, cap))
            gui_log(
                f"[AUTO] ประเมิน batch: {chosen} (imgsz={imgsz}, VRAM≈{total_gb:.1f}GB, cap={cap})"
            )
            return chosen

        cache_val = _resolve_cache_value()  # ✅ disk/false/ram

        # เคลียร์โฟลเดอร์ผลลัพธ์รอบก่อนหน้า เพื่อไม่ให้กระโดดเป็น train2/train3
        # (ข้ามถ้า do_resume — ต้องคงไว้สำหรับ resume)
        train_dir = os.path.join(custom_run_dir, "train")
        if os.path.isdir(train_dir) and not do_resume:
            try:
                shutil.rmtree(train_dir, ignore_errors=True)
                gui_log(f"[INIT] ล้างผลลัพธ์เก่า: {train_dir}")
            except Exception as e:
                gui_log(f"[INIT] ล้างโฟลเดอร์ train เดิมไม่สำเร็จ (ข้าม): {e}")

        ok = False
        try:
            for s in [imgsz_start, 896, 832, 768]:
                try:
                    if auto_ramp:
                        b_final = _pick_stable_batch(s, default_batch)
                        _, used_workers, used_amp, used_cache = _run_train_resilient(s, b_final, cache_val=cache_val)
                        selected["imgsz"], selected["batch"] = s, b_final
                        root.after(0, lambda s_=s, b_=b_final:
                            final_params_var.set(
                                f"พารามิเตอร์สุดท้าย: imgsz={s_}, batch={b_}, workers={used_workers}, amp={'ON' if used_amp else 'OFF'}, cache={used_cache} (สำเร็จ)"
                            )
                        )
                        ok = True
                        break
                    else:
                        for b in [default_batch, 2, 1]:
                            selected["imgsz"], selected["batch"] = s, b
                            gui_log(f"เริ่มเทรนจริงด้วย imgsz={s}, batch={b}, cache={cache_val}")
                            _, used_workers, used_amp, used_cache = _run_train_resilient(s, b, cache_val=cache_val)
                            root.after(0, lambda s_=s, b_=b, uw=used_workers, ua=used_amp, uc=used_cache:
                                final_params_var.set(
                                    f"พารามิเตอร์สุดท้าย: imgsz={s_}, batch={b_}, workers={uw}, amp={'ON' if ua else 'OFF'}, cache={uc} (สำเร็จ)"
                                )
                            )
                            ok = True
                            break
                        if ok:
                            break

                except RuntimeError as e:
                    msg = str(e)
                    if "CUDA out of memory" in msg:
                        torch.cuda.empty_cache()
                        gui_log("⚠️ OOM: ลด imgsz ลงแล้วลองใหม่...")
                        time.sleep(0.4)
                        continue
                    else:
                        gui_log(f"❌ RuntimeError: {msg}")
                        continue

        except Exception as e:
            gui_log(f"❌ Exception: {e}")
            sys.stdout, sys.stderr = orig_stdout, orig_stderr
            root.after(0, lambda: messagebox.showerror("Train Error", str(e)))
            training_done = True
            return

        if not ok:
            sys.stdout, sys.stderr = orig_stdout, orig_stderr
            root.after(0, lambda: messagebox.showerror("Train Error", "หน่วยความจำ/ดาต้าโหลดไม่พร้อม แม้จะลดค่าลงแล้ว"))
            training_done = True
            return

        try:
            weight_pack_dir = os.path.join(custom_run_dir, "weight_pack")
            if os.path.isdir(weight_pack_dir):
                shutil.rmtree(weight_pack_dir, ignore_errors=True)
            make_minimal_weight_pack(
                train_dir=train_dir,
                weight_pack_dir=weight_pack_dir,
                classes_list=classes,
                src_classes_path=classes_path
            )
            gui_log(f"[INFO] เสร็จแล้ว: {weight_pack_dir} -> best.pt, classes.txt, data.yaml")
        except Exception as e:
            gui_log(f"⚠️ Weight Pack: สร้างไม่สำเร็จ: {e}")
            sys.stdout, sys.stderr = orig_stdout, orig_stderr
            root.after(0, lambda: messagebox.showwarning("Weight Pack", f"สร้าง weight_pack ไม่สำเร็จ: {e}"))

        training_done = True
        elapsed = int(time.time() - start_time)
        m, s = divmod(elapsed, 60)

        root.after(0, lambda:
            status_label.config(
                text=f"{'✅ เทรนเสร็จ' if not cancel_training else '⛔ ยกเลิกแล้ว'} | ใช้เวลา {m} นาที {s} วินาที",
                fg="green" if not cancel_training else "red"
            )
        )
        gui_log("🎉 เทรนเสร็จสมบูรณ์")

        sys.stdout, sys.stderr = orig_stdout, orig_stderr

    def start_training():
        nonlocal cancel_training, training_done, start_time

        if FORCE_GPU and not torch.cuda.is_available():
            gpu_status_var.set("🔴 GPU-only mode: ไม่พร้อม (ไม่พบ CUDA GPU)")
            gpu_status_label.config(fg="red")
            messagebox.showerror("GPU Required", "ไม่พบ CUDA GPU (ต้องมี NVIDIA + ติดตั้ง CUDA/PyTorch แบบ GPU)")
            return

        cancel_training = False
        training_done = False

        try:
            epochs = int(epoch_entry.get())
            imgsz  = int(imgsz_spinbox.get())
            workers = int(workers_var.get())
        except Exception:
            messagebox.showerror("ค่าผิดพลาด", "กรุณากรอก Epochs / Image Size / workers เป็นตัวเลข")
            return

        if epochs <= 0:
            messagebox.showerror("ค่าผิดพลาด", "Epochs ต้องมากกว่า 0")
            return
        if imgsz < 320:
            messagebox.showerror("ค่าผิดพลาด", "Image Size ต้องไม่น้อยกว่า 320")
            return
        if workers < 0:
            messagebox.showerror("ค่าผิดพลาด", "workers ต้องไม่ติดลบ")
            return

        # Windows + 128GB RAM: allow more workers; still cap to avoid spawn storms
        if os.name == "nt" and workers > 24:
            messagebox.showwarning(
                "Workers ถูกจำกัด",
                f"บน Windows ค่า workers สูงมากอาจทำให้ค้าง/หลุดง่าย\nปรับจาก {workers} -> 24 เพื่อความเสถียร"
            )
            workers = 24
            workers_var.set(24)

        model_name = model_var.get().strip()
        use_amp = bool(amp_var.get())
        auto_ramp = bool(auto_ramp_var.get())
        if FORCE_RAM_CACHE:
            cache_mode_var.set("ram")
        cache_val = _resolve_cache_value()
        use_aug = bool(aug_var.get())
        try:
            aug_multiplier = int(aug_multiplier_var.get())
            aug_multiplier = max(2, min(12, aug_multiplier))
        except Exception:
            aug_multiplier = 5

        do_resume = bool(resume_var.get())

        if do_resume:
            last_pt = os.path.join(custom_run_dir, "train", "weights", "last.pt")
            confirm_msg = (
                f"📁 Dataset: {dataset_dir}\n\n"
                f"🔁 RESUME MODE — เทรนต่อจาก:\n{last_pt}\n\n"
                f"Epochs รวมทั้งหมด: {epochs}\n"
                f"GPU: CUDA:0 (forced)\n\n"
                "⚠️ ค่า imgsz/batch/workers ถูกอ่านจาก checkpoint เดิม\n\n"
                "เริ่ม Resume หรือไม่?"
            )
        else:
            confirm_msg = (
                f"📁 Dataset: {dataset_dir}\n\n"
                f"Task: {('SEGMENT' if task_var.get()=='segment' else 'DETECT')}\nModel: {model_name}\nImage Size: {imgsz}\nEpochs: {epochs}\n"
                f"GPU: CUDA:0 (forced)\n"
                f"Workers: {workers}\n"
                f"AMP: {'ON' if use_amp else 'OFF'}\n"
                f"Auto Ramp Batch: {'ON' if auto_ramp else 'OFF'}\n"
                f"Cache: {cache_val}\n"
                f"Batch start: {default_batch}\n"
                f"Offline Augmentation: {'ON x' + str(aug_multiplier) if use_aug else 'OFF'}\n\n"
                "เริ่มการเทรนหรือไม่?"
            )

        confirm = messagebox.askyesno("Confirm Training", confirm_msg, icon="question")
        if not confirm:
            return

        # ล้าง log
        log_text.configure(state="normal")
        log_text.delete("1.0", "end")
        log_text.configure(state="disabled")

        start_time = time.time()
        start_label.config(text=f"🕒 เริ่มเทรน: {datetime.now().strftime('%H:%M:%S')}")
        gpu_status_var.set("🟢 GPU-only mode: กำลังเทรนบน CUDA:0")
        gpu_status_label.config(fg="#0a7f2e")
        Thread(target=train_model, args=(model_name, imgsz, epochs, workers, use_amp, auto_ramp, use_aug, aug_multiplier, do_resume), daemon=True).start()
        Thread(target=countdown, daemon=True).start()
        mode_txt = "🔁 RESUME" if do_resume else "🚀 เทรนใหม่"
        status_label.config(text=f"{mode_txt} YOLO26 (GPU-only mode | CUDA:0)...", fg="black")

    def cancel_training_func():
        nonlocal cancel_training
        cancel_training = True
        status_label.config(text="⛔ ยกเลิกการฝึก รอหยุด...", fg="red")
        gui_log("ผู้ใช้กดยกเลิกการเทรน (จะหยุดหลังจบ epoch ที่กำลังรัน)")

    # ===== ปุ่มด้านบน
    btn_row = tk.Frame(root)
    btn_row.pack(pady=(8, 4))
    tk.Button(btn_row, text="▶️ Start Train", bg="green", fg="white",
              command=start_training, width=14, height=2).pack(side="left", padx=6)
    tk.Button(btn_row, text="🚫 Cancel", bg="red", fg="white",
              command=cancel_training_func, width=14, height=2).pack(side="left", padx=6)

    root.mainloop()


# =================================================================================
# ✅ จุดสำคัญ: guard กัน spawn แล้วรันซ้ำ + freeze_support
# =================================================================================
if __name__ == "__main__":
    _acquire_single_instance_lock()
    mp.freeze_support()
    main()
