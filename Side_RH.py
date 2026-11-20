# -*- coding: utf-8 -*-
# YOLOv8/YOLOv12/YOLO26 + Tkinter + SQL Server (Right panel fixed & stable - width=300)
# Stable/Low-DB-Load edition (YOLO26 weights: Camera_SIDE_RH_WeightYolo26)
# - DB client with persistent connection, executemany batching, background writer & name lookup queue
# - No UI-thread DB calls; bulk preload expected Name_AI; async extra Name_AI lookup
# - No-CAR close=1 frame; percent (xx%); first-seen save; NG_VINSTART on close if NG remains (with NG buffer override)
# - If no DB spec to compare → DO NOT save (skip persist).
# - (2025-10-03) VINSTART snapshot (RAW; no YOLO labels) [ปิดการใช้งาน auto save แล้วตาม req ใหม่]
# - UPDATED: Reset รอบก็ต่อเมื่อ “เจอ NO_CAR/No_Car เท่านั้น”; ภาพว่างไม่รีเซ็ต
# - UPDATED: ลดขนาดข้อความบนภาพจากกล้องลง 3 เท่า (labels ของโมเดล)
# - UPDATED: Inference ใช้ภาพเต็มสเกลจากกล้อง (ไม่ครอป/ไม่ย่อก่อนส่งเข้าโมเดล)
# - UPDATED (กติกา 4 ข้อ): Red%→Green, W/O rule, ซ่อนดำ id9 ซ้ำเขียว, ROOF_COLOR ไม่โชว์/ไม่บันทึก,
#   และ Extra ที่จะบันทึกต้องไม่ใช่ ROOF_COLOR และไม่ซ้ำ id9 กับรายการเขียว (Result=NG)
# - UPDATED (ALL_OK RULE with W/O): ALL_OK = เจอครบทุก expected item ที่ไม่ใช่ "W/O"
# - (2025-10-22): ไฟล์รูปทุกใบ ~100KB
# - (2025-10-23): NG BUFFER — รอ No Car ค่อยเซฟ ถ้ายังไม่ ALL_OK
# - (2025-10-29 SEQ RULE) [ปรับใหม่]:
#   * การเริ่มรอบใหม่อ้างอิงจาก VinNo ใน InlineDetails(IdProcess=199) + SeqCar จาก Cars(GatewayQC)
# - (2025-10-29 BEST-FRAME RULE):
#   * ภาพที่ใช้เป็นรูป ALL_OK (สีเขียวหมด) ต้องมาจาก "ช่วง Carryover collecting"
#     ระหว่างรอ VIN/SEQ ใหม่ (waiting_for_new_vin == True)
#   * เก็บเฟรมที่เห็น item (ไม่ใช่ NO_CAR) เยอะที่สุดในช่วงนั้น
#   * พอตัดสินว่ารอบเก่า ALL_OK ตอน SEQ เปลี่ยน -> เซฟรูปนี้ครั้งเดียว แล้วล็อก
#   * หลังบันทึกรูป ALL_OK แล้ว รอบนั้นไม่ต้องเซฟรูปอื่นอีก
#   * ถ้าไม่ ALL_OK -> จะใช้ flow เดิม: บัฟเฟอร์ NG แล้ว persist ตอนเจอ No Car
# - (This file) ปรับ logic finalize รอบเก่า (T-3sec snapshot) ให้ผูกกับ carryover_best_frame
# - (2025-10-31) NEW: Extra item min confidence (config on UI). Extras with conf < threshold → NOT counted, NOT compared, NOT saved.
# - (2025-11-05) NEW: Post-NoCar+3s snapshot → ใช้รูปหลังจาก "No Car หายไปครบ 3 วินาที" เป็นภาพบันทึกให้รอบที่กำลังจะปิด
#                    ถ้า OK → OK_..., ถ้าไม่ → NG_...  (ใช้รูปเดียวกัน)
# - (2025-11-13) NEW: แหล่งข้อมูลหลักของ Vin/LotCode/Seq/IdModel มาจาก
#                     - VinNo: InlineDetails(TMT-GW-DIAS) WHERE IdProcess=199 ORDER BY StartDate DESC
#                     - BodyNoCar, LotCodeCar, IdModel, SeqCar: Cars(GatewayQC) จากฟังก์ชัน fetch_car_info_by_vin_from_gateway
# - (2025-11-14) NEW: Preview ใช้ภาพดิบจากกล้อง (ไม่ตีกรอบ/ไม่เขียน text YOLO) เพื่อลดอาการกระตุก
#                     → Logic YOLO / DB / กติกาไม่เปลี่ยน
# - (2025-11-19) NEW: วาดกรอบ + text เอง:
#                     * กรอบ + text ของ item เดียวกันสีเดียวกัน
#                     * ต่าง item คนละสี
#                     * text เล็กลง
#                     * ยังลดโหลดด้วยการให้ YOLO อ่านจากภาพย่อ แต่กรอบสเกลกลับไปวาดบนภาพเต็ม
#                     * ขยายภาพแสดงผลให้ใหญ่ขึ้น ลดพื้นที่พื้นหลังสีดำ
#
# - (2025-11-20) NEW (12MP FULL VIEW):
#   * PREF_RES_LIST ปรับให้ลองเปิดที่ความละเอียดสูงสุดของกล้องก่อน (เช่น 4000x3000)
#   * VIEW_ZOOM = 1.0 เพื่อให้ภาพขยายเต็มพื้นที่แสดงผล
#   * configure_display_from_window ปรับให้ใช้พื้นที่ทางซ้ายเต็มหน้าต่าง (ลบ margin ออก)
#   → ภาพจากกล้องจะ "เต็มจอฝั่งซ้าย" มากที่สุดเท่าที่อัตราส่วนภาพอนุญาต (ไม่ครอป)
#
# - (2025-11-24) NEW: Carryover match
#   * ขณะ waiting_for_new_vin = True จะจำ item ที่ YOLO อ่านได้ (ยกเว้น NO_CAR)
#   * เมื่อได้ SEQ ใหม่ (โหลด spec จาก DB) จะนำ item ที่จำไว้มาเทียบกับ expected ของ SEQ ใหม่ทันที
#   * ถ้าตรง spec → matched_set (เขียว) / ถ้าไม่ตรง → extras (ดำ, ตาม extra_min_conf)
#
# - (2025-11-24) NEW (THIS CHANGE):
#   * ระหว่าง "กำลังรอ SEQ ใหม่" (waiting_for_new_vin = True)
#     แสดง item ที่ YOLO อ่านได้ (carryover) ในกรอบข้อความด้านขวาเป็น "ตัวอักษรสีฟ้า"
#     แยกจากแดง/ดำ/เขียวของรอบปัจจุบัน

import os
import cv2
import numpy as np
import time
import threading
import queue
import torch
import pyodbc
import tkinter as tk
from tkinter import font as tkfont, ttk, messagebox
from collections import deque
from datetime import datetime
from PIL import Image, ImageTk
from ultralytics import YOLO
import ultralytics as _ultra
import re
import sys
import traceback
import ctypes
import random
import logging
from logging.handlers import RotatingFileHandler
import shutil
import hashlib

# ขยายภาพให้เต็มพื้นที่แสดงผล (ไม่ครอป) ด้วย letterbox → ใช้ 1.0 ได้เลย
VIEW_ZOOM = 1.0   # 0.5–1.0: 1.0 = เต็มพื้นที่แสดงผล

def letterbox(img, new_w, new_h, color=(0, 0, 0)):
    """
    Resize แบบรักษาอัตราส่วนภาพ แล้วใส่ขอบ (padding) ให้ได้ขนาดปลายทาง new_w x new_h
    """
    if img is None:
        return None
    h, w = img.shape[:2]
    if w <= 0 or h <= 0 or new_w is None or new_h is None or new_w <= 0 or new_h <= 0:
        return img  # เผื่อค่าผิดปกติ: ส่งภาพเดิมกลับ

    # scale ตามด้านที่จำกัดกว่า
    scale = min(new_w / float(w), new_h / float(h))
    rw, rh = int(round(w * scale)), int(round(h * scale))

    # resize
    interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
    resized = cv2.resize(img, (rw, rh), interpolation=interp)

    # คำนวณ padding
    pad_w = max(0, new_w - rw)
    pad_h = max(0, new_h - rh)
    left   = pad_w // 2
    right  = pad_w - left
    top    = pad_h // 2
    bottom = pad_h - top

    # เติมขอบให้ตรงขนาด
    out = cv2.copyMakeBorder(resized, top, bottom, left, right,
                             borderType=cv2.BORDER_CONSTANT, value=color)
    return out


# ========= Logging =========
LOG_DIR = os.path.abspath("./logs")
os.makedirs(LOG_DIR, exist_ok=True)
logger = logging.getLogger("camera_SIDE_RH")
logger.setLevel(logging.INFO)
_handler = RotatingFileHandler(os.path.join(LOG_DIR, "app.log"), maxBytes=2_000_000, backupCount=3, encoding="utf-8")
_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
_handler.setFormatter(_formatter)
logger.addHandler(_handler)

# ========= SQL Log (C:\LogAI\Log_SIDE_RH_YYYYMMDD.txt) =========
LOG_AI_DIR = r"C:\LogAI"
try:
    os.makedirs(LOG_AI_DIR, exist_ok=True)
except Exception:
    pass

def _write_sql_log(sql_text, params=None, result=None, error=None):
    """เก็บเวลาทำสั่ง SQL และผลลัพธ์ลงไฟล์ .txt แยกวัน ชื่อ Log_SIDE_RH_YYYYMMDD.txt"""
    try:
        today = datetime.now().strftime("%Y%m%d")
        path = os.path.join(LOG_AI_DIR, f"Log_SIDE_RH_{today}.txt")
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"[{ts}]\n")
            f.write(f"SQL:\n{sql_text.strip()}\n")
            if params is not None:
                f.write(f"Params: {params}\n")
            if error is not None:
                f.write(f"Result: ERROR - {error}\n")
            elif result is not None:
                f.write(f"Result: {result}\n")
            else:
                f.write("Result: (none)\n")
            f.write("-" * 60 + "\n")
    except Exception:
        pass

# ========= Device / CUDA =========
use_cuda = torch.cuda.is_available()
DEVICE_IDX = 0 if use_cuda else "cpu"
USE_HALF = bool(use_cuda)
torch.backends.cudnn.benchmark = True
cv2.setNumThreads(1)

def _print_device_info():
    print(">>> Using CUDA:", use_cuda)
    try:
        print(">>> torch.version:", torch.__version__)
        print(">>> torch.version.cuda:", torch.version.cuda)
    except Exception:
        pass
    try:
        print(">>> ultralytics version:", getattr(_ultra, "__version__", "unknown"))
    except Exception:
        pass
    if use_cuda:
        try:
            print(">>> GPU:", torch.cuda.get_device_name(0))
            print(">>> CUDA Capabilities:", torch.cuda.get_device_capability(0))
        except Exception as e:
            print(">>> GPU check error:", e)

_print_device_info()

def _set_windows_appusermodel():
    try:
        myappid = u'camera_SIDE_RH.App.1'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except Exception:
        pass

_set_windows_appusermodel()

# ========= UI Layout =========
RIGHT_PANEL_W = 300
DISPLAY_W, DISPLAY_H = None, None

# ========= Autostart camera =========
AUTO_START_ON_LAUNCH = True
AUTO_START_CAMERA_INDEX = 1  # กล้องตัวที่ 3 (0-based index)
_auto_started_once = False
# บังคับ backend กล้องได้: "MSMF", "DSHOW", หรือ "ANY"
CAMERA_PREFER_BACKEND = "DSHOW"

# ========= Database =========
DB_DRIVER = 'ODBC Driver 17 for SQL Server'

# DB สำหรับฝั่งกล้อง / AI / InlineDetails / AI_Result_Spec ฯลฯ
DIAS_DB = {
    'server': '192.168.0.125',
    'database': 'TMT-GW-DIAS',
    'username': 'sa',
    'password': '@QK10260'
}

# DB สำหรับ Cars (ข้อมูลตัวรถจาก GatewayQC)
GATEWAY_DB = {
    'server': '192.168.0.125',
    'database': 'GatewayQC',
    'username': 'sa',
    'password': '@QK10260'
}

def _conn_str_dias():
    return (
        f"DRIVER={{{DB_DRIVER}}};"
        f"SERVER={DIAS_DB['server']};"
        f"DATABASE={DIAS_DB['database']};"
        f"UID={DIAS_DB['username']};"
        f"PWD={DIAS_DB['password']};"
        f"MARS_Connection=Yes"
    )

def _conn_str_gw():
    return (
        f"DRIVER={{{DB_DRIVER}}};"
        f"SERVER={GATEWAY_DB['server']};"
        f"DATABASE={GATEWAY_DB['database']};"
        f"UID={GATEWAY_DB['username']};"
        f"PWD={GATEWAY_DB['password']};"
        f"MARS_Connection=Yes"
    )
def _conn_str():
    return (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={DIAS_DB['server']};DATABASE={DIAS_DB['database']};"
        f"UID={DIAS_DB['username']};PWD={DIAS_DB['password']};"
        f"MARS_Connection=Yes"
    )

def _conn_str_gw():
    return (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={GATEWAY_DB['server']};DATABASE={GATEWAY_DB['database']};"
        f"UID={GATEWAY_DB['username']};PWD={GATEWAY_DB['password']};"
        f"MARS_Connection=Yes"
    )

# ========= Inference control =========
TARGET_FPS_INFER = 10
CONF_THRES = 0.7

# ----- กล้อง & YOLO ขนาดที่ใช้ infer เพื่อลดโหลด -----
# (0,0) ก่อน = native เร็วสุด; ถ้าไดรเวอร์ไม่ให้เฟรมค่อยลอง 720p
PREF_RES_LIST = [
    (4000, 3000),
    (1280, 720),
]

INFER_DOWNSCALE = 0.5   # ใช้ภาพย่อสำหรับ YOLO เมื่อรับภาพใหญ่ระดับ 48MP
DET_LABEL_FONT_SCALE = 1.5625  # ลดลง 3 เท่า ตามที่ขอ
DET_LABEL_THICKNESS = 1
DET_BOX_THICKNESS = 2

# ========= UI Optimization =========
UI_UPDATE_INTERVAL_MS = 33  # ~30 FPS สำหรับ UI update
DB_QUERY_CACHE_MS = 500     # Cache DB queries เพื่อลดโหลด
RESULT_QUEUE_SIZE = 1       # Keep maxsize=1 เพื่อไม่ให้ queue เก่า
UI_TEXT_REBUILD_SKIP_COUNT = 1  # realtime: update text ทุก frame

def open_camera_best(index, prefer_backend=cv2.CAP_MSMF, strict_backend=True):
    """
    strict_backend=True: ลองแค่ backend เดียวกับที่เลือกใน combo (ตรงกับ RESCAN)
    บน Windows ดัชนีเดียวกันระหว่าง MSMF กับ DirectShow มักชี้คนละอุปกรณ์ — fallback DSHOW มักภาพดำ
    """
    if strict_backend:
        backends_to_try = [prefer_backend]
    else:
        seen = []
        backends_to_try = []
        for b in (prefer_backend, cv2.CAP_MSMF, cv2.CAP_DSHOW, cv2.CAP_ANY):
            if b not in seen:
                seen.append(b)
                backends_to_try.append(b)
    for backend in backends_to_try:
        for (w, h) in PREF_RES_LIST:
            cap = cv2.VideoCapture(index, backend)
            if not cap.isOpened():
                cap.release(); continue
            try:
                if w > 0 and h > 0:
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
                try:
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                except Exception:
                    pass
            except Exception:
                pass
            try:
                ok, frame = cap.read()
            except cv2.error as e:
                logger.warning(f"[CAM] read failed idx={index} backend={backend} {w}x{h}: {e}")
                cap.release()
                continue
            if ok and frame is not None and frame.size > 0:
                tag = "native" if (w <= 0 or h <= 0) else f"{w}x{h}"
                logger.info(f"[CAM] Opened idx={index} backend={backend} {tag}")
                return cap, backend, (w or frame.shape[1], h or frame.shape[0])
            cap.release()
    return None, None, (0,0)

# ========= Rule / Save =========
CAM_NO_FILTER = 'camera_SIDE_RH'
REFRESH_MS = 2000
NO_CAR_CONSEC_REQUIRED = 1
PERSIST_ON_IDLE_SEC = None

SAVE_DIR = r"C:\Images\camera_SIDE_RH"

# ---- เป้าหมายไฟล์ ~100KB ----
JPEG_TARGET_KB = 100
JPEG_TOLERANCE_KB = 8
JPEG_START_QUALITY = 90
JPEG_MIN_QUALITY = 5
DOWNSCALE_FACTOR = 0.75
MIN_WIDTH_FLOOR = 240
MIN_HEIGHT_FLOOR = 135
os.makedirs(SAVE_DIR, exist_ok=True)

SHOW_NAME_ON_EXPECTED = True
SHOW_NAME_ON_EXTRAS = True
MAX_NAME_CHARS = 44

def _shorten(s: str, n: int) -> str:
    s = (s or "").strip().replace("\n", " ")
    return s if len(s) <= n else (s[:max(1, n-1)] + "…")

def _norm_sel1(sel) -> str:
    s = (str(sel) or "").strip()
    return s[:1] if len(s) >= 1 else ""

def _build_key(id9: str, sel_any) -> str:
    id9 = (str(id9) or "")[:9]
    sel1 = _norm_sel1(sel_any)
    return (id9 + sel1) if len(id9) == 9 and len(sel1) == 1 else ""

_AI_KEY_LEN = 10
def _parse_ai_label(lbl: str):
    s = (lbl or "").strip()
    core = re.sub(r'[^0-9A-Za-z]', '', s)
    id9 = core[:9]
    sel1 = core[9] if len(core) >= 10 else ""
    key = _build_key(id9, sel1)
    return id9, sel1, key

# ========= Ignore readable-text labels (OCR-like) =========
# ข้าม label/คำที่อ่านได้ซึ่งไม่ต้องนำไปเทียบ spec/ไม่ต้องแสดงผล
IGNORE_READABLE_LABEL_TOKENS = {
    "AI938W042",
    "AID46H091",
    "AID46H092",
    "AID46H060",
    "AID46H061",
}

def _should_ignore_readable_label(label: str) -> bool:
    core = re.sub(r"[^0-9A-Za-z]", "", str(label or "")).upper()
    if not core:
        return False
    for tok in IGNORE_READABLE_LABEL_TOKENS:
        if tok in core:
            return True
    return False

def _contains_blacktape_text(s: str) -> bool:
    try:
        return "BLACKTAPE" in str(s or "").upper()
    except Exception:
        return False

def _should_ignore_expected_item(id9: str, key10: str) -> bool:
    # ใช้ชุดกติกาเดียวกับ ignore label เพื่อกันรายการจาก DB หลุดมาเป็น expected
    return _should_ignore_readable_label(id9) or _should_ignore_readable_label(key10)

# ===== Save rate-limit / session vars =====
SAVE_COOLDOWN_SEC = 5
PER_VIN_SAVE_LIMIT = 50
last_save_time_by_key = {}
per_vin_save_count = {}
last_snapshot_picture_path = ""
vinstart_picture_path = ""
ok_all_image_saved_by_vin = {}   # vin -> bool
last_saved_frame_sig = ""
last_saved_frame_ts = 0.0

# ===== NG BUFFER =====
ng_buffer = {
    "frame": None,
    "seq": "",
    "vin": "",
    "lot": "",
    "keys": [],
    "ts": 0.0
}

# ===== SEQ CHANGE DELAY TIMER =====
seq_change_ts = None  # เวลาที่ SEQ เปลี่ยน
seq_change_delay_sec = 0  # รอ 2 วิ ค่อย save
seq_change_pending = False  # รอการบันทึกอยู่
last_seq_change_saved_key = ""  # กัน save ซ้ำใน SEQ เดิม

def _clear_ng_buffer():
    ng_buffer["frame"] = None
    ng_buffer["seq"]  = ""
    ng_buffer["vin"]  = ""
    ng_buffer["lot"]  = ""
    ng_buffer["keys"] = []
    ng_buffer["ts"]   = 0.0

def _remember_ng_frame(annotated_frame, seq_text, vin, lot, ng_keys):
    if annotated_frame is None:
        return
    ng_buffer["frame"] = annotated_frame.copy()
    ng_buffer["seq"]   = str(seq_text or "")
    ng_buffer["vin"]   = str(vin or "")
    ng_buffer["lot"]   = str(lot or "")
    ng_buffer["keys"]  = list(ng_keys or [])
    ng_buffer["ts"]    = time.time()

def _has_saved_image_for_cycle() -> bool:
    return bool(last_snapshot_picture_path)

def _frame_signature(frame_bgr) -> str:
    try:
        small = cv2.resize(frame_bgr, (64, 64), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        return hashlib.md5(gray.tobytes()).hexdigest()
    except Exception:
        return ""

def _is_duplicate_frame(frame_bgr, window_sec=5.0) -> bool:
    sig = _frame_signature(frame_bgr)
    if not sig:
        return False
    now = time.time()
    return (sig == last_saved_frame_sig) and ((now - last_saved_frame_ts) <= window_sec)

def _mark_saved_frame_sig(frame_bgr):
    global last_saved_frame_sig, last_saved_frame_ts
    sig = _frame_signature(frame_bgr)
    if sig:
        last_saved_frame_sig = sig
        last_saved_frame_ts = time.time()

def _reuse_last_snapshot_if_duplicate(frame_bgr, window_sec=5.0) -> str:
    if last_snapshot_picture_path and _is_duplicate_frame(frame_bgr, window_sec=window_sec):
        logger.info("Duplicate frame detected; reuse last snapshot path.")
        return last_snapshot_picture_path
    return ""

def _save_image_and_mark(frame_bgr, out_path) -> bool:
    if save_image_target_jpg(frame_bgr, out_path):
        _mark_saved_frame_sig(frame_bgr)
        return True
    return False

def _save_buffered_ng_if_any(snapshot=None, include_extras=True):
    global last_snapshot_picture_path
    if snapshot is not None and not _snapshot_has_ng(snapshot, include_extras):
        return ""
    if _has_saved_image_for_cycle():
        return ""
    if ng_buffer["frame"] is not None:
        reused = _reuse_last_snapshot_if_duplicate(ng_buffer["frame"])
        if reused:
            return reused
        t = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        vin = _sanitize_for_filename(ng_buffer["vin"] or "")
        lot = _sanitize_for_filename(ng_buffer["lot"] or "")
        seq = _sanitize_for_filename(ng_buffer["seq"] or "")
        key_join = "_".join([k[:_AI_KEY_LEN] for k in (ng_buffer["keys"] or [])])[:60]
        fname = f"{vin}_{lot}_{seq}_{t}.jpg"
        path = os.path.join(SAVE_DIR, fname)
        if _save_image_and_mark(ng_buffer["frame"], path):
            last_snapshot_picture_path = path
            logger.info(f"Saved NG from buffer: {path}")
            flash_info("NG SNAP", 900, bg="#FFAB91")
            return path
    return save_ng_copy_of_vinstart()

def _reset_per_vin_counters():
    global per_vin_save_count, last_snapshot_picture_path, vinstart_picture_path
    global last_saved_frame_sig, last_saved_frame_ts
    per_vin_save_count.clear()
    last_snapshot_picture_path = ""
    vinstart_picture_path = ""
    last_saved_frame_sig = ""
    last_saved_frame_ts = 0.0

def _can_save_for(key10, vin):
    now = time.time()
    if key10 in last_save_time_by_key and now - last_save_time_by_key[key10] < SAVE_COOLDOWN_SEC:
        return False
    cnt = per_vin_save_count.get(vin, 0)
    return cnt < PER_VIN_SAVE_LIMIT

def _mark_saved(key10, vin):
    last_save_time_by_key[key10] = time.time()
    per_vin_save_count[vin] = per_vin_save_count.get(vin, 0) + 1

def ensure_save_dir_writable():
    try:
        os.makedirs(SAVE_DIR, exist_ok=True)
        p = os.path.join(SAVE_DIR, "_write_test.tmp")
        with open(p, "wb") as f:
            f.write(b"ok")
        os.remove(p)
        return True
    except Exception as e:
        print("SAVE_DIR not writable:", e)
        try:
            status_label.config(text=f"SAVE_DIR not writable: {e}", fg="#E53935")
        except Exception:
            pass
        set_corner_state("error", "SAVE DIR\nERROR")
        return False

def _sanitize_for_filename(s: str) -> str:
    if s is None:
        return "-"
    s = str(s)
    return re.sub(r'[^0-9A-Za-z._-]+', '', s) or "-"

def save_image_target_jpg(
    img_bgr,
    out_path,
    target_kb=100,
    start_q=90,
    min_q=5,
    down_factor=0.75,
    tol_kb=8
):
    try:
        if img_bgr is None or img_bgr.size == 0:
            return False
        cur = img_bgr
        if cur.dtype != np.uint8:
            cur = np.clip(cur, 0, 255).astype(np.uint8)
        target = int((target_kb + tol_kb) * 1024)
        attempt = 0
        while True:
            attempt += 1
            q = int(start_q)
            while q >= min_q:
                ok, enc = cv2.imencode(".jpg", cur, [cv2.IMWRITE_JPEG_QUALITY, q])
                if not ok:
                    break
                sz = len(enc)
                if sz <= target:
                    with open(out_path, "wb") as f:
                        f.write(enc.tobytes())
                    return True
                if sz > target * 2.2:
                    q -= 18
                elif sz > target * 1.6:
                    q -= 12
                elif sz > target * 1.25:
                    q -= 8
                else:
                    q -= 5
            h, w = cur.shape[:2]
            nw = max(MIN_WIDTH_FLOOR, int(w * down_factor))
            nh = max(MIN_HEIGHT_FLOOR, int(h * down_factor))
            if (nw == w and nh == h) or (nw <= MIN_WIDTH_FLOOR and nh <= MIN_HEIGHT_FLOOR):
                ok, enc = cv2.imencode(".jpg", cur, [cv2.IMWRITE_JPEG_QUALITY, min_q])
                if ok:
                    with open(out_path, "wb") as f:
                        f.write(enc.tobytes())
                    return True
                cv2.imwrite(out_path, cur)
                return True
            cur = cv2.resize(cur, (nw, nh), interpolation=cv2.INTER_AREA)
            if attempt > 20:
                ok, enc = cv2.imencode(".jpg", cur, [cv2.IMWRITE_JPEG_QUALITY, min_q])
                if ok:
                    with open(out_path, "wb") as f:
                        f.write(enc.tobytes())
                    return True
                cv2.imwrite(out_path, cur)
                return True
    except Exception as e:
        logger.exception(f"save_image_target_jpg error: {e}")
        try:
            cv2.imwrite(out_path, img_bgr)
            return True
        except Exception:
            return False

def save_ng_copy_of_vinstart():
    try:
        if vinstart_picture_path and os.path.isfile(vinstart_picture_path):
            src = vinstart_picture_path
            dir_ = os.path.dirname(src)
            base = os.path.basename(src)
            dst = os.path.join(dir_, base)
            shutil.copyfile(src, dst)
            logger.info(f"Saved NG copy from VINSTART: {dst}")
            return dst
    except Exception as e:
        logger.warning(f"Copy NG VINSTART failed, fallback to snapshot. err={e}")
    with latest_frame_lock:
        frame = None if latest_frame is None else latest_frame.copy()
    if frame is None:
        return ""
    car = inline_data or {}
    vin = _sanitize_for_filename(car.get("VinNo", ""))
    lot = _sanitize_for_filename(car.get("LotCodeCar", ""))
    seq = _sanitize_for_filename(car.get("SeqCar", ""))
    t = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    fname = f"{vin}_{lot}_{seq}_{t}.jpg"
    path = os.path.join(SAVE_DIR, fname)
    if _save_image_and_mark(frame, path):
        logger.info(f"Saved NG VINSTART snapshot (fallback): {path}")
        return path
    return ""

# ========= BEST FRAME PER SEQ =========
best_frame_this_seq = None
best_frame_itemcount = 0
best_frame_meta = {"vin":"", "lot":"", "seq":""}
best_frame_locked_saved = False  # สำหรับกันเซฟซ้ำตอน ALL_OK เดิม

def _reset_best_frame_for_new_seq(vin_val, lot_val, seq_val):
    global best_frame_this_seq, best_frame_itemcount, best_frame_meta, best_frame_locked_saved
    best_frame_this_seq = None
    best_frame_itemcount = 0
    best_frame_meta = {
        "vin": _sanitize_for_filename(vin_val or ""),
        "lot": _sanitize_for_filename(lot_val or ""),
        "seq": _sanitize_for_filename(seq_val or "")
    }
    best_frame_locked_saved = False

def _update_best_frame_candidate(annotated_frame, count_items, vin_val, lot_val, seq_val):
    global best_frame_this_seq, best_frame_itemcount, best_frame_meta
    if annotated_frame is None:
        return
    if count_items > best_frame_itemcount:
        best_frame_itemcount = count_items
        best_frame_meta = {
            "vin": _sanitize_for_filename(vin_val or ""),
            "lot": _sanitize_for_filename(lot_val or ""),
            "seq": _sanitize_for_filename(seq_val or "")
        }
        best_frame_this_seq = annotated_frame.copy()

def _save_best_frame_all_ok_once(prefix=""):
    global best_frame_locked_saved, last_snapshot_picture_path
    if _has_saved_image_for_cycle():
        return ""
    if best_frame_locked_saved:
        return ""
    if best_frame_this_seq is None:
        return ""
    reused = _reuse_last_snapshot_if_duplicate(best_frame_this_seq)
    if reused:
        best_frame_locked_saved = True
        return reused
    t = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    vin = best_frame_meta["vin"]
    lot = best_frame_meta["lot"]
    seq = best_frame_meta["seq"]
    fname = f"{vin}_{lot}_{seq}_{t}.jpg"
    path = os.path.join(SAVE_DIR, fname)
    if _save_image_and_mark(best_frame_this_seq, path):
        last_snapshot_picture_path = path
        best_frame_locked_saved = True
        ok_all_image_saved_by_vin[vin] = True
        logger.info(f"Saved BEST-FRAME snapshot (current seq): {path}")
        flash_info("SNAP", 900, bg="#81C784")
        return path
    return ""

# ========= CARRYOVER BEST FRAME =========
carryover_best_frame = None
carryover_best_count = 0
carryover_best_meta = {"vin":"", "lot":"", "seq":""}
carryover_locked_saved = False  # กันเซฟซ้ำภาพ ALL_OK ของรอบเก่า

def _reset_carryover_best():
    global carryover_best_frame, carryover_best_count, carryover_best_meta, carryover_locked_saved
    carryover_best_frame = None
    carryover_best_count = 0
    carryover_best_meta = {"vin":"", "lot":"", "seq":""}
    carryover_locked_saved = False

def _update_carryover_candidate(frame_bgr, detected_items, vin_val, lot_val, seq_val):
    global carryover_best_frame, carryover_best_count, carryover_best_meta
    if frame_bgr is None:
        return
    count_items = len(detected_items)
    if count_items > carryover_best_count:
        carryover_best_count = count_items
        carryover_best_meta = {
            "vin": _sanitize_for_filename(vin_val or ""),
            "lot": _sanitize_for_filename(lot_val or ""),
            "seq": _sanitize_for_filename(seq_val or "")
        }
        carryover_best_frame = frame_bgr.copy()

def _save_carryover_all_ok_once(prefix=""):
    global carryover_locked_saved, last_snapshot_picture_path
    if _has_saved_image_for_cycle():
        return ""
    if carryover_locked_saved:
        return ""
    if carryover_best_frame is None:
        return ""
    reused = _reuse_last_snapshot_if_duplicate(carryover_best_frame)
    if reused:
        carryover_locked_saved = True
        return reused
    t = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    vin = carryover_best_meta["vin"]
    lot = carryover_best_meta["lot"]
    seq = carryover_best_meta["seq"]
    fname = f"{vin}_{lot}_{seq}_{t}.jpg"
    path = os.path.join(SAVE_DIR, fname)
    if _save_image_and_mark(carryover_best_frame, path):
        last_snapshot_picture_path = path
        carryover_locked_saved = True
        ok_all_image_saved_by_vin[vin] = True
        logger.info(f"Saved CARRYOVER snapshot (prev seq): {path}")
        flash_info("SNAP", 900, bg="#81C784")
        return path
    return ""

def _save_seq_change_snapshot(vin_val, lot_val, seq_val):
    """เมื่อ SEQ เปลี่ยน: พยายามบันทึกทันที และตั้ง timer สำรองถ้ายังไม่มีภาพ"""
    global seq_change_ts, seq_change_pending, persisted_this_cycle, last_snapshot_picture_path
    global last_seq_change_saved_key
    global latest_annotated_frame, latest_annotated_lock, latest_frame, latest_frame_lock

    persisted_this_cycle = False
    vin = _sanitize_for_filename(vin_val or "")
    seq = _sanitize_for_filename(seq_val or "")
    seq_key = f"{vin}|{seq}"
    if seq_key == last_seq_change_saved_key:
        logger.info(f"Skip duplicate SEQ_CHANGE save for {seq_key}")
        return

    # --- Try immediate save pair (real-time) ---
    frame_with_label = None
    frame_without_label = None
    with latest_annotated_lock:
        if latest_annotated_frame is not None:
            frame_with_label = latest_annotated_frame.copy()
    with latest_frame_lock:
        if latest_frame is not None:
            frame_without_label = latest_frame.copy()

    if frame_with_label is not None and frame_without_label is not None:
        try:
            is_ok = _decide_overall_ok_by_db_logic()
            t = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            lot = _sanitize_for_filename(lot_val or "")
            snap = {
                "expected_pairs": list(expected_pairs),
                "expected_set": set(expected_set),
                "matched_set": set(matched_set),
                "extras_black": set(extras_black),
                "ai_conf_by_key": dict(ai_conf_by_key),
                "ai_by_key": dict(ai_by_key),
                "ai_by_id9": dict(ai_by_id9),
                "inline_data": {"VinNo": vin_val, "LotCodeCar": lot_val, "SeqCar": seq_val, "IdModel": (inline_data or {}).get("IdModel")}
            }
            include_extras = (not is_ok)
            fname_label = f"{vin}_{lot}_{seq}_{t}_yolo.jpg"
            fname_raw = f"{vin}_{lot}_{seq}_{t}_raw.jpg"
            path_label = os.path.join(SAVE_DIR, fname_label)
            path_raw = os.path.join(SAVE_DIR, fname_raw)

            ok_label = _save_image_and_mark(frame_with_label, path_label)
            ok_raw = _save_image_and_mark(frame_without_label, path_raw)
            if ok_label and ok_raw:
                last_snapshot_picture_path = path_label
                last_seq_change_saved_key = seq_key
                logger.info(f"Saved SEQ_CHANGE pair IMMEDIATE: {path_label} | {path_raw}")
                flash_info("SEQ CHANGE", 1000, bg="#64B5F6")

                # DB summary: ทำเฉพาะตอนจบรอบด้วย No_Car

                # immediate saved -> no need pending timer
                seq_change_pending = False
                seq_change_ts = None
                return
            logger.warning(f"SEQ_CHANGE pair save incomplete (immediate): label={ok_label} raw={ok_raw}")
        except Exception as e:
            logger.exception(f"Immediate SEQ change snapshot save failed: {e}")

    # --- Fallback to delayed save when no frame yet ---
    seq_change_ts = time.time()
    seq_change_pending = True
    logger.info(f"SEQ changed: VIN={vin_val} SEQ={seq_val} - waiting 2 sec...")
    flash_info("SEQ CHANGE - WAIT 2sec", 1000, bg="#FFC107")

def _process_seq_change_after_delay():
    """หลัง 2 วิ บันทึกภาพพร้อม label จาก YOLO"""
    global seq_change_ts, seq_change_pending, last_snapshot_picture_path, persisted_this_cycle
    global last_seq_change_saved_key
    global expected_set, expected_pairs, matched_set, extras_black, ai_conf_by_key, ai_by_key, ai_by_id9
    global latest_annotated_frame, latest_annotated_lock, latest_frame, latest_frame_lock
    
    if not seq_change_pending or seq_change_ts is None:
        return
    
    elapsed = time.time() - seq_change_ts
    if elapsed < seq_change_delay_sec:
        return  # ยังไม่ครบ 2 วิ
    
    seq_change_pending = False
    
    # เก็บภาพ 2 แบบ: มี label YOLO และไม่มี label
    frame_with_label = None
    frame_without_label = None
    with latest_annotated_lock:
        if latest_annotated_frame is not None:
            frame_with_label = latest_annotated_frame.copy()
    with latest_frame_lock:
        if latest_frame is not None:
            frame_without_label = latest_frame.copy()

    if frame_with_label is None or frame_without_label is None:
        logger.warning("SEQ change: pair frame not available")
        return
    
    try:
        lv = globals().get("latest_vin")
        ll = globals().get("latest_lot")
        ls = globals().get("latest_seq")
        lm = globals().get("latest_model")
        vin = _sanitize_for_filename(lv or "")
        seq = _sanitize_for_filename(ls or "")
        seq_key = f"{vin}|{seq}"
        if seq_key == last_seq_change_saved_key:
            return
        # ตัดสินใจ OK/NG ตามตรรกะเดียวกับ DB
        is_ok = _decide_overall_ok_by_db_logic()
        
        t = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        lot = _sanitize_for_filename(ll or "")
        snap = {
            "expected_pairs": list(expected_pairs),
            "expected_set": set(expected_set),
            "matched_set": set(matched_set),
            "extras_black": set(extras_black),
            "ai_conf_by_key": dict(ai_conf_by_key),
            "ai_by_key": dict(ai_by_key),
            "ai_by_id9": dict(ai_by_id9),
            "inline_data": {"VinNo": lv, "LotCodeCar": ll, "SeqCar": ls, "IdModel": lm}
        }
        include_extras = (not is_ok)
        fname_label = f"{vin}_{lot}_{seq}_{t}_yolo.jpg"
        fname_raw = f"{vin}_{lot}_{seq}_{t}_raw.jpg"
        path_label = os.path.join(SAVE_DIR, fname_label)
        path_raw = os.path.join(SAVE_DIR, fname_raw)

        ok_label = _save_image_and_mark(frame_with_label, path_label)
        ok_raw = _save_image_and_mark(frame_without_label, path_raw)
        if ok_label and ok_raw:
            last_snapshot_picture_path = path_label
            last_seq_change_saved_key = seq_key
            logger.info(f"Saved SEQ_CHANGE pair: {path_label} | {path_raw}")
            flash_info("SEQ CHANGE", 1000, bg="#64B5F6")
            
            # DB summary: ทำเฉพาะตอนจบรอบด้วย No_Car
        else:
            logger.warning(f"SEQ_CHANGE pair save incomplete: label={ok_label} raw={ok_raw}")
    except Exception as e:
        logger.exception(f"SEQ change snapshot save failed: {e}")

def _decide_result_ok_or_ng():
    """ตัดสินใจ OK/NG ตามการ match กับ expected spec"""
    try:
        if not expected_set:
            return "NG"  # ไม่มี spec = NG
        
        if matched_set == expected_set and len(filter_nojudge_extras()) == 0:
            return "OK"
        
        return "NG"
    except Exception:
        return "NG"

def _decide_result_ok_or_ng_no_spec():
    """ตัดสินใจ OK/NG (ไม่มี NOSPEC) ตามการ match กับ expected spec"""
    try:
        if not expected_set:
            return "NG"  # ไม่มี spec = NG (ไม่ใช่ NOSPEC)
        
        if matched_set == expected_set and len(filter_nojudge_extras()) == 0:
            return "OK"
        
        return "NG"
    except Exception:
        return "NG"

def _decide_overall_ok_by_db_logic() -> bool:
    """ตัดสินใจ OK ตามตรรกะเดียวกับ DB (ใช้ seen + W/O + extras)"""
    try:
        if not expected_pairs:
            return False
        req = set()
        for (_id9, _sel1, key10) in expected_pairs:
            nm = (expected_name_ai.get(key10, "") or "")
            if "W/O" in nm.upper():
                continue
            req.add(key10)
        seen = set(matched_set) | set(ai_conf_by_key.keys())
        if not (req.issubset(seen) and (len(expected_set) >= 1)):
            return False
        if len(filter_nojudge_extras()) > 0:
            return False
        return True
    except Exception:
        return False

def filter_nojudge_extras():
    """ได้ extras ที่ต้อง judge (เช่น ไม่ใช่ zone, ไม่ต่ำกว่า threshold)"""
    try:
        result = set()
        ok_id9 = {b[:9] for b in matched_set}
        for b in extras_black:
            if b[:9] in ok_id9:
                continue
            if _is_roof_color_key(b):
                continue
            if not _is_extra_conf_pass(b):
                continue
            if _is_zone_label(b):
                continue
            result.add(b)
        return result
    except Exception:
        return set()

# ========= Backoff/retry helper =========
def _retry(op, tries=3, base_delay=0.25):
    last_exc = None
    for i in range(to := tries):
        try:
            return op()
        except Exception as e:
            last_exc = e
            time.sleep(base_delay * (2**i) + random.random() * 0.15)
    raise last_exc

# ========= Stable detection gate =========
DETECT_STABLE_SEC = 0.0
_detect_since = {}

# ========= Global state =========
latest_frame_lock = threading.Lock()
latest_frame = None

latest_annotated_lock = threading.Lock()
latest_annotated_frame = None

result_queue = queue.Queue(maxsize=1)
program_started = True  # Flag สำหรับการเก็บภาพเมื่อเปิดโปรแกรมครั้งแรก
ui_frame_counter = 0    # Counter สำหรับการ optimize text rebuild
inline_data = None
infer_fps = 0.0
first_dims_ready = threading.Event()
_cam_w = 0
_cam_h = 0
cam_thread = None
infer_thread = None
cam_stop_flag = threading.Event()
_infer_session_id = 0
_yolo_predict_lock = threading.Lock()
current_cam_index = None
current_cam_backend = None

# ========= Cycle state =========
expected_pairs = []
expected_set = set()
matched_set = set()
extras_black = set()
ai_reads_full = []
ai_by_key = {}
ai_by_id9 = {}
ai_conf_by_key = {}
ai_conf_by_id9 = {}
# สะสมแบบจำนวนครั้ง: ต่อ key10 ต่อรอบ update ใช้ conf สูงสุดของรอบนั้น
# All_Percent = sum(conf*100), Frame = จำนวนครั้งที่นำค่าไปบวก (ขั้นต่ำ 1 เมื่อเคยเห็น)
allpercent_by_key = {}
frame_count_by_key = {}
# สะสม Frame ต่อ key: ค่า 0–221 ไม่แสดงใน text area และไม่บันทึก DB; เริ่มทำงานตามปกติเมื่อ Frame >= 222
MIN_ACCUM_FRAME_FOR_UI_AND_DB = 155
# Threshold สำหรับตัดสิน OK/NG: ค่านี้จะถูกผูกกับค่า "Extra min %" (ตาม _get_extra_min_conf())
OK_PERCENT_THRESHOLD = 0.0  # kept for compatibility (actual decision uses _get_extra_min_conf()*100)
recent_seen_keys = set()
last_loaded_key = None
expected_name_ai = {}
extra_name_ai_cache = {}
first_seen_index = {}
_seen_counter = 0
ok_key10_persisted_this_cycle = set()  # key10 (id9+sel1) ที่เคย insert Result=OK แล้วใน cycle นี้
previous_vin = None
previous_body = None
previous_seq = None   # SeqCar จาก Cars(GatewayQC)
waiting_for_new_vin = True
_no_car_streak = 0
latest_no_car_confs = []      # รายการความมั่นใจ No_Car ในเฟรมล่าสุด (0..1 หรือ 0..100)
latest_no_car_ts = 0.0
_round_start_time = time.time()
_last_seen_non_no_car_ts = None
last_frame_ts = time.time()
VIN_SNAPSHOT_DELAY_MS = 2000
vin_change_snapshot_job = None

# ========= Snapshot history =========
SNAPSHOT_HISTORY_SEC = 12.0
snapshot_history = deque(maxlen=240)

# ========= NEW FLAGS (Autosave & lock) =========
ALL_OK_AUTOSAVE = True
early_saved_all_green = False
persisted_this_cycle = False
# บันทึก No_Car ครั้งเดียวต่อช่วง "มีแต่ No_Car" (ไม่ผูกกับ persisted_this_cycle — กันกรณี ALL_OK บันทึกแล้ว No_Car ไม่ยิง SQL)
no_car_persist_done_this_streak = False
lock_hide_extras = False

# ========= Behavior flags =========
SAVE_EXTRAS_WHEN_NO_DB = True

def _percent_str(conf: float):
    try:
        p = int(round(float(conf) * 100.0))
        return f" ({p:02d}%) "
    except Exception:
        return ""

# ========= DB Client =========
class DbClient:
    # ========= CONSTRUCTOR =========
    def __init__(self, dias_conn_str, gw_conn_str):
        # DIAS (TMT-GW-DIAS) – inline / AI_Result_Spec / InlineDetails ฯลฯ
        self.conn_str = dias_conn_str
        # GatewayQC – Cars
        self.conn_str_gw = gw_conn_str

        self._lock = threading.RLock()

        # main connection (DIAS)
        self._conn = None
        # gateway connection (Cars)
        self._conn_gw = None

        self._ensure_conn()
        self._ensure_conn_gw()

        # writer queue (ไปตาราง AI_Result_Spec – ใช้ DIAS DB)
        self.write_queue = queue.Queue(maxsize=50)
        self.writer_thread = threading.Thread(
            target=self._writer_worker, daemon=True
        )
        self.writer_thread.start()

        # queue สำหรับโหลด Name_AI เพิ่ม (ใช้ DIAS DB)
        self.name_q = queue.Queue(maxsize=200)
        self._name_pending = set()
        self.name_thread = threading.Thread(
            target=self._name_worker, daemon=True
        )
        self.name_thread.start()

    # ========= CONNECTION (DIAS) =========
    def _ensure_conn(self):
        with self._lock:
            try:
                if self._conn is None or not self._conn_connected():
                    self._conn = pyodbc.connect(self.conn_str, timeout=5, autocommit=False)
            except Exception:
                logger.exception("DB (DIAS) connect failed")
                raise

    def _conn_connected(self):
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
            return True
        except Exception:
            return False

    def _reconnect(self):
        with self._lock:
            try:
                if self._conn:
                    try:
                        self._conn.close()
                    except Exception:
                        pass
                self._conn = pyodbc.connect(self.conn_str, timeout=5, autocommit=False)
            except Exception:
                logger.exception("DB (DIAS) reconnect failed")
                raise

    # ========= CONNECTION (GatewayQC / Cars) =========
    def _ensure_conn_gw(self):
        with self._lock:
            try:
                if self._conn_gw is None or not self._conn_gw_connected():
                    self._conn_gw = pyodbc.connect(self.conn_str_gw, timeout=5, autocommit=False)
            except Exception:
                logger.exception("DB (GatewayQC) connect failed")
                raise

    def _conn_gw_connected(self):
        try:
            cur = self._conn_gw.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
            return True
        except Exception:
            return False

    def _reconnect_gw(self):
        with self._lock:
            try:
                if self._conn_gw:
                    try:
                        self._conn_gw.close()
                    except Exception:
                        pass
                self._conn_gw = pyodbc.connect(self.conn_str_gw, timeout=5, autocommit=False)
            except Exception:
                logger.exception("DB (GatewayQC) reconnect failed")
                raise

    # ========= INLINE DETAILS (อ่าน VIN ปัจจุบันจาก TMT-GW-DIAS) =========
    def fetch_latest_vin_from_inline_details(self):
        """
        อ่าน VIN ล่าสุดจาก TMT-GW-DIAS.dbo.Inline_Tester_Line1
        ใช้ VinNo ล่าสุดตาม DateIn ล่าสุด
        """
        sql = """
        SELECT TOP (1) VinNo
        FROM Inline_Tester_Line1 WITH (NOLOCK)
        ORDER BY DateIn DESC
        """
        def _do():
            self._ensure_conn()
            cur = self._conn.cursor()
            cur.execute(sql)
            row = cur.fetchone()
            self._conn.commit()
            if not row:
                return None
            return {"VinNo": row[0]}
        try:
            return _retry(_do, tries=3, base_delay=0.3)
        except Exception as e:
            try:
                self._reconnect()
            except Exception:
                pass
            return None

    # ========= CARS (GatewayQC – ใช้ข้อมูลตัวรถทุกอย่างจากฟังก์ชันนี้) =========
    
    def fetch_car_info_by_vin_from_gateway(self, vin):
        """
        ดึงข้อมูลรถจาก GatewayQC.dbo.Cars โดยใช้ VinNoCar
        คืน dict: {VinNoCar, BodyNoCar, LotCodeCar, IdModel, SeqCar}
        """
        # กัน null / empty
        if not vin:
            return {}

        # ถ้ามาเป็น dict เช่น {'VinNo': 'XXX'} หรือ {'VinNoCar': 'XXX'}
        if isinstance(vin, dict):
            vin = vin.get("VinNo") or vin.get("VinNoCar") or ""
        if not isinstance(vin, str):
            vin = str(vin)

        vin = vin.strip()
        if not vin:
            return {}

        logger.info("[Cars] Query GatewayQC.dbo.Cars VIN='%s'", vin)

        sql = """
        SELECT TOP 1
            VinNoCar,
            BodyNoCar,
            LotCodeCar,
            IdModel,
            SeqCar
        FROM GatewayQC.dbo.Cars WITH (NOLOCK)
        WHERE VinNoCar = ?
        ORDER BY No DESC
        """
        cols = ["VinNoCar", "BodyNoCar", "LotCodeCar", "IdModel", "SeqCar"]

        def _do():
            # ใช้ connection ของ GatewayQC
            self._ensure_conn_gw()
            cur = self._conn_gw.cursor()
            cur.execute(sql, (vin,))
            row = cur.fetchone()
            self._conn_gw.commit()
            out = dict(zip(cols, row)) if row else {}
            return out

        try:
            result = _retry(_do, tries=3, base_delay=0.3)
            if not result:
                logger.info("Vin=%s not found in Cars(GatewayQC)", vin)
            else:
                logger.info(
                    "Vin=%s found: BodyNo=%s LotCode=%s IdModel=%s SeqCar=%s",
                    result["VinNoCar"],
                    result["BodyNoCar"],
                    result["LotCodeCar"],
                    result["IdModel"],
                    result["SeqCar"],
                )
            return result
        except Exception as e:
            logger.error("[Cars] ERROR: %s", e, exc_info=True)
            try:
                self._reconnect_gw()
            except Exception:
                pass
            return {}


    # ========= SPEC / NAME_AI (ใช้ DIAS DB) =========
    def load_expected_from_master_lotcode(self, lotcode, camno):
        if not lotcode:
            return []
        sql = """
        SELECT IdItem, Select_Code
        FROM dbo.AI_Master_Select_Lotcode WITH (NOLOCK)
        WHERE LotCode = ? AND CamNo = ?
        """
        def _do():
            self._ensure_conn()
            cur = self._conn.cursor()
            cur.execute(sql, (lotcode, camno))
            fetch = cur.fetchall()
            self._conn.commit()
            out = []
            if fetch:
                for rid, rsel in fetch:
                    iditem = (str(rid) or "")[:9]
                    sel1 = _norm_sel1(rsel)
                    key10 = _build_key(iditem, sel1)
                    if key10:
                        out.append((iditem, sel1, key10))
            return out
        try:
            return _retry(_do, tries=3, base_delay=0.3)
        except Exception as e:
            try:
                self._reconnect()
            except Exception:
                pass
            return []

    def fetch_itemcheck_nameai(self, iditem9, select_code1):
        if not iditem9 or not select_code1:
            return ("", "")
        sel1 = _norm_sel1(select_code1)
        sql = """
        SELECT TOP 1 Item_Check, Name_AI
        FROM dbo.AI_Master_Select WITH (NOLOCK)
        WHERE ID_AI = ? AND Select_Code = ?
        """
        def _do():
            self._ensure_conn()
            cur = self._conn.cursor()
            cur.execute(sql, (iditem9, sel1))
            row = cur.fetchone()
            self._conn.commit()
            res = (row[0] or "", row[1] or "") if row else ("", "")
            return res
        try:
            return _retry(_do, tries=3, base_delay=0.3)
        except Exception as e:
            try:
                self._reconnect()
            except Exception:
                pass
            return ("", "")

    def fetch_nameai_bulk(self, pairs):
        if not pairs:
            return {}
        params = [(id9, _norm_sel1(sel1)) for (id9, sel1, _k) in pairs]
        uniq = list({(a, b) for (a, b) in params})
        chunk = 80
        result = {}
        for i in range(0, len(uniq), chunk):
            sub = uniq[i:i+chunk]
            where = " OR ".join(["(ID_AI=? AND Select_Code=?)"] * len(sub))
            sql = (
                "SELECT ID_AI, Select_Code, Name_AI "
                "FROM dbo.AI_Master_Select WITH (NOLOCK) "
                f"WHERE {where}"
            )
            flat = []
            for (a, b) in sub:
                flat.extend([a, b])
            def _do():
                self._ensure_conn()
                cur = self._conn.cursor()
                cur.execute(sql, flat)
                rows = cur.fetchall()
                self._conn.commit()
                return rows
            try:
                rows = _retry(_do, tries=2, base_delay=0.25)
            except Exception as e:
                try:
                    self._reconnect()
                except Exception:
                    pass
                rows = []
            d = {(str(r[0])[:9], _norm_sel1(r[1])): (r[2] or "") for r in rows}
            for (id9, sel1, key10) in pairs:
                nm = d.get((id9, _norm_sel1(sel1)))
                if nm is not None:
                    result[key10] = nm
        return result

    def queue_extra_name(self, key10):
        if not key10 or len(key10) < 10:
            return
        with self._lock:
            if key10 in self._name_pending:
                return
            self._name_pending.add(key10)
        try:
            self.name_q.put_nowait(key10)
        except queue.Full:
            with self._lock:
                self._name_pending.discard(key10)

    def _name_worker(self):
        while True:
            try:
                key10 = self.name_q.get()
                id9 = key10[:9]; sel1 = key10[9:10]
                _ic, nm = self.fetch_itemcheck_nameai(id9, sel1)
                extra_name_ai_cache[key10] = nm or ""
                with self._lock:
                    self._name_pending.discard(key10)
                try:
                    root.after(0, rebuild_right_text)
                except Exception:
                    pass
            except Exception as e:
                logger.exception(f"name_worker error: {e}")
            finally:
                try:
                    self.name_q.task_done()
                except Exception:
                    pass

    # ========= WRITER (AI_Result_Spec – DIAS DB) =========
    def enqueue_results(self, rows):
        if not rows:
            print("[SQL][enqueue] skip: empty rows (nothing to INSERT)", flush=True)
            return
        try:
            self.write_queue.put_nowait(rows)
            try:
                qs = self.write_queue.qsize()
            except Exception:
                qs = -1
            print(
                f"[SQL][enqueue] queued {len(rows)} row(s) for AI_Result_Spec (write_queue qsize≈{qs})",
                flush=True,
            )
        except queue.Full:
            print(
                "[SQL][enqueue] FAIL: write_queue FULL — batch DROPPED (no INSERT)",
                flush=True,
            )
            logger.warning("write_queue full; dropping a batch to keep UI responsive")

    def _writer_worker(self):
        sql = """
        INSERT INTO [dbo].[AI_Result_Spec]
        (VinNo, Date, Time, Picture, SEQ, IdModel, LotCode, CamNo, IdItem, SelectCode, Spec, Result_SQL,
         AI_Read, Percent_AI, Result, AI_SelectCode, AI_Spec, PC, Frame, All_Percent)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        # กัน insert ล้มทั้ง batch เมื่อค่ายาวเกินคอลัมน์ fixed length
        fixed_max_len = {
            "VinNo": 20,
            "Date": 30,
            "Time": 10,
            "Picture": 200,
            "SEQ": 10,
            "IdModel": 10,
            "LotCode": 10,
            "CamNo": 50,
            "IdItem": 50,
            "Result": 10,
            "AI_SelectCode": 10,
            "PC": 50,
        }

        def _clip_field(field_name, val, row_idx):
            if val is None:
                return ""
            s = str(val)
            max_len = fixed_max_len.get(field_name)
            if max_len and len(s) > max_len:
                clipped = s[:max_len]
                print(
                    f"[SQL][clip] row={row_idx} field={field_name} len={len(s)}>{max_len} "
                    f"truncated value={s!r} -> {clipped!r}",
                    flush=True,
                )
                return clipped
            return s

        while True:
            try:
                rows = self.write_queue.get()
                if not rows:
                    self.write_queue.task_done()
                    continue
                args = []
                for i, r in enumerate(rows):
                    args.append((
                        _clip_field("VinNo", r.get("VinNo", ""), i),
                        _clip_field("Date", r.get("Date", ""), i),
                        _clip_field("Time", r.get("Time", ""), i),
                        _clip_field("Picture", r.get("Picture", ""), i),
                        _clip_field("SEQ", r.get("SEQ", ""), i),
                        _clip_field("IdModel", r.get("IdModel", ""), i),
                        _clip_field("LotCode", r.get("LotCode", ""), i),
                        _clip_field("CamNo", r.get("CamNo", ""), i),
                        _clip_field("IdItem", r.get("IdItem", ""), i),
                        str(r.get("SelectCode", "") or ""),
                        str(r.get("Spec", "") or ""),
                        str(r.get("Result_SQL", "") or ""),
                        str(r.get("AI_Read", "") or ""),
                        int(round(float(r.get("Percent_AI", 0) or 0))),
                        _clip_field("Result", r.get("Result", ""), i),
                        _clip_field("AI_SelectCode", r.get("AI_SelectCode", ""), i),
                        str(r.get("AI_Spec", "") or ""),
                        _clip_field("PC", r.get("PC", "PCmain"), i),
                        int(round(float(r.get("Frame", 0) or 0))),
                        int(round(float(r.get("All_Percent", 0) or 0))),
                    ))
                sql_one_line = " ".join(sql.split())
                logger.info(f"[SQL][AI_Result_Spec] CMD: {sql_one_line}")
                logger.info(f"[SQL][AI_Result_Spec] PARAMS: executemany rows={len(args)}")
                print(f"[SQL][AI_Result_Spec] executemany rows={len(args)}", flush=True)
                print(f"[SQL][AI_Result_Spec] CMD: {sql_one_line[:200]}...", flush=True)
                if rows:
                    r0 = rows[0]
                    logger.info(
                        f"[SQL][AI_Result_Spec] SAMPLE: VinNo={r0.get('VinNo','')} "
                        f"SEQ={r0.get('SEQ','')} LotCode={r0.get('LotCode','')} "
                        f"IdItem={r0.get('IdItem','')} Result={r0.get('Result','')} "
                        f"Percent_AI={r0.get('Percent_AI',0)} Frame={r0.get('Frame',0)} "
                        f"All_Percent={r0.get('All_Percent',0)}"
                    )
                    print(
                        f"[SQL][AI_Result_Spec] SAMPLE row0: VinNo={r0.get('VinNo','')} "
                        f"SEQ={r0.get('SEQ','')} LotCode={r0.get('LotCode','')} "
                        f"IdItem={r0.get('IdItem','')} Result={r0.get('Result','')}",
                        flush=True,
                    )

                def _do():
                    self._ensure_conn()
                    cur = self._conn.cursor()
                    try:
                        cur.fast_executemany = True
                    except Exception:
                        pass
                    cur.executemany(sql, args)
                    self._conn.commit()

                _retry(_do, tries=3, base_delay=0.5)
                vin_seq_lot = ""
                if rows:
                    r0 = rows[0]
                    vin_seq_lot = (
                        f" VinNo={r0.get('VinNo', '')}"
                        f" SEQ={r0.get('SEQ', '')}"
                        f" LotCode={r0.get('LotCode', '')}"
                    )
                _write_sql_log(
                    sql,
                    params=f"executemany {len(rows)} rows{vin_seq_lot}",
                    result=f"OK inserted {len(rows)} rows{vin_seq_lot}",
                )
                logger.info(
                    f"DBWriter: inserted {len(rows)} rows "
                    f"(VinNo={rows[0].get('VinNo','')} SEQ={rows[0].get('SEQ','')} LotCode={rows[0].get('LotCode','')})"
                )
                logger.info(f"[SQL][AI_Result_Spec] SUCCESS: committed rows={len(rows)}")
                print(
                    f"[SQL][AI_Result_Spec] SUCCESS COMMIT rows={len(rows)}{vin_seq_lot}",
                    flush=True,
                )
            except Exception as e:
                vin_seq_lot = ""
                if rows:
                    r0 = rows[0]
                    vin_seq_lot = (
                        f" VinNo={r0.get('VinNo', '')}"
                        f" SEQ={r0.get('SEQ', '')}"
                        f" LotCode={r0.get('LotCode', '')}"
                    )
                _write_sql_log(
                    sql,
                    params=f"executemany {len(rows)} rows{vin_seq_lot}",
                    error=str(e),
                )
                logger.error(f"[SQL][AI_Result_Spec] ERROR: {e}")
                logger.exception(f"DBWriter error: {e}")
                print(f"[SQL][AI_Result_Spec] ERROR (no COMMIT): {e}{vin_seq_lot}", flush=True)
                try:
                    self._reconnect()
                except Exception:
                    pass
            finally:
                try:
                    self.write_queue.task_done()
                except Exception:
                    pass


db_client = DbClient(_conn_str_dias(), _conn_str_gw())


# ========= Tkinter widgets =========
root = tk.Tk()
root.title("camera_SIDE_RH")
try:
    root.state('zoomed')  # เปิดมาเต็มจอเลย
except Exception:
    root.attributes('-zoomed', True)

# ========= UI theme (modern dark) =========
BG_APP = "#0F172A"
BG_PANEL = "#111827"
BG_PANEL_SOFT = "#1F2937"
BG_VIDEO = "#020617"
FG_MAIN = "#E5E7EB"
FG_MUTED = "#9CA3AF"
ACCENT = "#2563EB"
ACCENT_ALT = "#0EA5E9"
GOOD = "#10B981"
WARN = "#F59E0B"
BAD = "#EF4444"

root.configure(bg=BG_APP)
style = ttk.Style(root)
try:
    style.theme_use("clam")
except Exception:
    pass

style.configure("Panel.TLabelframe", background=BG_PANEL, foreground=FG_MAIN, borderwidth=1)
style.configure("Panel.TLabelframe.Label", background=BG_PANEL, foreground=FG_MAIN, font=("Segoe UI", 9, "bold"))
style.configure("Panel.TLabel", background=BG_PANEL, foreground=FG_MAIN)
style.configure("Main.TCombobox", fieldbackground=BG_PANEL_SOFT, background=BG_PANEL_SOFT, foreground=FG_MAIN)
style.map("Main.TCombobox", fieldbackground=[("readonly", BG_PANEL_SOFT)], foreground=[("readonly", FG_MAIN)])
style.configure("Primary.TButton", font=("Segoe UI", 9, "bold"), padding=(8, 6), anchor="w")
style.map("Primary.TButton", background=[("active", ACCENT_ALT), ("!disabled", ACCENT)], foreground=[("!disabled", "#FFFFFF")])
style.configure("Secondary.TButton", font=("Segoe UI", 9), padding=(8, 6))

root.grid_columnconfigure(0, weight=1)
root.grid_columnconfigure(1, weight=0, minsize=RIGHT_PANEL_W)
root.grid_rowconfigure(0, weight=1)

left_frame = tk.Frame(root, bg=BG_VIDEO)
left_frame.grid(row=0, column=0, sticky="nsew")
video_label = tk.Label(left_frame, bd=0, highlightthickness=0, bg=BG_VIDEO)
video_label.pack(fill="both", expand=True)

right_frame = tk.Frame(root, width=RIGHT_PANEL_W, bg=BG_PANEL)
right_frame.grid(row=0, column=1, sticky="ns")
right_frame.grid_propagate(False)
right_frame.grid_rowconfigure(6, weight=1)

header = tk.Frame(right_frame, bg=BG_PANEL)
header.grid(row=0, column=0, sticky="new", padx=4, pady=(4, 0))
tk.Label(header, text="Detected / Expected", font=("Segoe UI", 11, "bold"), bg=BG_PANEL, fg=FG_MAIN).pack(anchor="w")

cam_block = ttk.LabelFrame(right_frame, text="Camera", style="Panel.TLabelframe", padding=6)
cam_block.grid(row=1, column=0, sticky="ew", padx=6, pady=(6, 4))
cam_block.grid_columnconfigure(1, weight=1)
ttk.Label(cam_block, text="Select:", style="Panel.TLabel").grid(row=0, column=0, sticky="e", padx=(0,6))
camera_combo = ttk.Combobox(cam_block, state="readonly", values=[], style="Main.TCombobox")
camera_combo.grid(row=0, column=1, sticky="ew")
rescan_btn = ttk.Button(cam_block, text="RESCAN", style="Secondary.TButton")
rescan_btn.grid(row=0, column=2, padx=(6,0))
start_btn = ttk.Button(cam_block, text="START", style="Primary.TButton")
start_btn.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(8,0))

_seq_font_size = 18
_seq_font = tkfont.Font(family="Arial", size=_seq_font_size, weight="bold")
seq_label = tk.Label(right_frame, text="SeqCar: -", fg="green", font=_seq_font, anchor="w", justify="left")
seq_label.grid(row=2, column=0, sticky="nw", padx=4, pady=(2, 0))
seq_label.configure(bg=BG_PANEL, fg=GOOD)

lot_model_label = tk.Label(right_frame, text="Lot: - Model: -", font=("Arial", 10), anchor="w", justify="left")
lot_model_label.grid(row=3, column=0, sticky="nw", padx=4, pady=(0, 2))
lot_model_label.configure(bg=BG_PANEL, fg=FG_MUTED, font=("Segoe UI", 9))

def _fit_seq_font(text):
    max_w = RIGHT_PANEL_W - 6
    size = _seq_font_size
    while size > 8:
        f = tkfont.Font(family="Arial", size=size, weight="bold")
        if f.measure(text) <= max_w:
            seq_label.config(font=f)
            return
        size -= 1
    seq_label.config(font=tkfont.Font(family="Arial", size=8, weight="bold"))

stat_block = tk.Frame(right_frame, bg=BG_PANEL)
stat_block.grid(row=4, column=0, sticky="ew", padx=4, pady=(0, 2))
stat_block.grid_columnconfigure(0, weight=1)
matched_label = tk.Label(stat_block, text="Matched 0/0 | Extra 0", font=("Segoe UI", 10, "bold"), anchor="w", bg=BG_PANEL, fg=FG_MAIN)
matched_label.grid(row=0, column=0, sticky="w")
seen_label = tk.Label(stat_block, text="AI Seen: 0", font=("Segoe UI", 9), anchor="w", bg=BG_PANEL, fg=FG_MUTED)
seen_label.grid(row=1, column=0, sticky="w")
status_label = tk.Label(stat_block, text="Waiting for new VIN...", font=("Segoe UI", 9),
                        anchor="w", justify="left", fg=WARN, bg=BG_PANEL)
status_label.grid(row=2, column=0, sticky="w", pady=(0,2))

# ======== NEW: Config block (Extra min %) ========
config_block = ttk.LabelFrame(right_frame, text="Config", style="Panel.TLabelframe", padding=6)
config_block.grid(row=5, column=0, sticky="ew", padx=6, pady=(0, 4))
config_block.grid_columnconfigure(1, weight=1)

ttk.Label(config_block, text="Extra min %:", style="Panel.TLabel").grid(row=0, column=0, sticky="e", padx=(0,6))
extra_min_conf_var = tk.StringVar(value="70")  # default 70%
extra_min_entry = ttk.Entry(config_block, textvariable=extra_min_conf_var, width=6, justify="center")
extra_min_entry.grid(row=0, column=1, sticky="w")

# ========= Class list (right side) =========
class_text = tk.Text(
    right_frame,
    font=("Consolas", 10),
    wrap="word",
    bg=BG_PANEL_SOFT,
    fg=FG_MAIN,
    insertbackground=FG_MAIN,
    bd=0,
    highlightthickness=1,
    highlightbackground="#334155",
    relief="flat"
)
class_text.tag_config("red", foreground=BAD)
class_text.tag_config("green", foreground=GOOD)
class_text.tag_config("black", foreground=FG_MAIN)
# NEW: สีขาวสำหรับ expected จาก DB ที่ยังไม่เคยเห็นจาก YOLO
class_text.tag_config("white", foreground="#FFFFFF")
# NEW: แท็กสำหรับแสดง No_Car realtime
class_text.tag_config("noc", foreground="#FFFFFF")
# NEW: แท็กสีฟ้าสำหรับ item ช่วงกำลังรอ SEQ ใหม่
class_text.tag_config("blue", foreground=ACCENT_ALT)
class_text.config(state="disabled")
class_text.grid(row=6, column=0, sticky="nsew", padx=4, pady=4)

tk_img_ref = None

# Corner badge
BADGE_DIAMETER = 96
BADGE_PAD_X = 12
BADGE_PAD_Y = 12
BADGE_FONT = ("Arial", 10, "bold")
COLOR_WAIT_BG   = "#FFD54F"
COLOR_ACTIVE_BG = "#66BB6A"
COLOR_SAVING_BG = "#FB8C00"
COLOR_ERROR_BG  = "#EF5350"
COLOR_TEXT_DARK = "#000000"
COLOR_TEXT_LIGHT= "#FFFFFF"

badge_canvas = tk.Canvas(
    left_frame, width=BADGE_DIAMETER, height=BADGE_DIAMETER,
    highlightthickness=0, bd=0, bg=left_frame.cget("bg")
)
badge_canvas.place(relx=1.0, rely=0.0, anchor="ne", x=-BADGE_PAD_X, y=BADGE_PAD_Y)
_badge_circle_id = badge_canvas.create_oval(
    0, 0, BADGE_DIAMETER, BADGE_DIAMETER,
    fill=COLOR_WAIT_BG, outline="", width=0
)
_badge_text_id = badge_canvas.create_text(
    BADGE_DIAMETER//2, BADGE_DIAMETER//2,
    text="WAITING\nVIN", font=BADGE_FONT,
    fill=COLOR_TEXT_DARK, justify="center"
)
_blink_job = None
_blink_on = True
_saving_job = None

def _cancel_after(job_id):
    if job_id is not None:
        try:
            root.after_cancel(job_id)
        except Exception:
            pass

def _blink_start(period_ms=450):
    global _blink_job, _blink_on
    _blink_on = True
    _cancel_after(_blink_job)
    def _tick():
        global _blink_job, _blink_on
        _blink_on = not _blink_on
        badge_canvas.itemconfigure(
            _badge_text_id,
            fill=COLOR_TEXT_DARK if _blink_on else "#333333"
        )
        _blink_job = root.after(period_ms, _tick)
    _blink_job = root.after(period_ms, _tick)

def _blink_stop():
    global _blink_job
    _cancel_after(_blink_job)
    _blink_job = None
    badge_canvas.itemconfigure(_badge_text_id, fill=COLOR_TEXT_DARK)

def _badge_set(bg: str, text: str, text_color: str):
    badge_canvas.configure(bg=left_frame.cget("bg"))
    badge_canvas.itemconfigure(_badge_circle_id, fill=bg)
    badge_canvas.itemconfigure(_badge_text_id, text=text, fill=text_color)

def set_corner_state(state: str, text: str = None):
    global _saving_job
    _cancel_after(_saving_job)
    if state == "waiting":
        _badge_set(COLOR_WAIT_BG, (text or "WAITING\nVIN"), COLOR_TEXT_DARK)
        _blink_start(420)
    elif state == "active":
        _blink_stop()
        _badge_set(COLOR_ACTIVE_BG, (text or "ACTIVE"), COLOR_TEXT_DARK)
    elif state == "saving":
        _badge_set(COLOR_SAVING_BG, (text or "SAVING..."), COLOR_TEXT_DARK)
        _blink_start(650)
        def _back_wait():
            set_corner_state("waiting")
        _saving_job = root.after(2000, _back_wait)
    elif state == "error":
        _blink_stop()
        _badge_set(COLOR_ERROR_BG, (text or "ERROR"), COLOR_TEXT_LIGHT)
    else:
        _blink_stop()
        _badge_set("#90CAF9", (text or "STATE"), COLOR_TEXT_DARK)

def flash_info(text, ms=1200, bg="#90CAF9", fg=COLOR_TEXT_DARK):
    _blink_stop()
    _badge_set(bg, text, fg)
    root.after(ms, lambda: set_corner_state("active" if not waiting_for_new_vin else "waiting"))

def set_status(text: str, fg: str = None):
    status_label.config(text=text, fg=(fg if fg else status_label.cget("fg")))
    logger.info(text)

# ========= Model (lazy-load to speed startup) =========
MODEL_PATHS = [
    r"C:\YOLO26\SIDE_RH_WeightYolo26\weight_pack\best.pt",
    r"C:/Users/ADMIN/Downloads/SIDE_RH_WeightYolo12/weight_pack/best.pt",
]
def _select_existing_path(paths):
    for p in paths:
        if p and os.path.isfile(p):
            return p
    return paths[0]

MODEL_PATH = _select_existing_path(MODEL_PATHS)


def _fix_conv2d_bool_groups(root_module):
    """YOLO26 .pt บางไฟล์ deserialize nn.Conv2d.groups เป็น bool; PyTorch 2.5+ ใช้ไม่ได้"""
    if root_module is None:
        return 0
    n = 0
    for m in root_module.modules():
        if isinstance(m, torch.nn.Conv2d) and type(m.groups) is bool:
            m.groups = 1
            n += 1
    return n


def _fix_yolo26_conv2d_groups(yolo_model):
    return _fix_conv2d_bool_groups(getattr(yolo_model, "model", None))

model = None
names = {}
_model_ready = threading.Event()
_model_loading = False


def _load_model_worker():
    global model, names, _model_loading
    try:
        if not MODEL_PATH or not os.path.isfile(MODEL_PATH):
            raise FileNotFoundError(f"YOLO weight not found: {MODEL_PATH!r}")
        t0 = time.time()
        m = YOLO(MODEL_PATH)
        _fixed_g = _fix_yolo26_conv2d_groups(m)
        if _fixed_g:
            print(f">>> Patched Conv2d.groups (bool→1): {_fixed_g} layer(s)")
            logger.info(f"Patched Conv2d.groups bool: {_fixed_g} layer(s)")
        model = m
        try:
            names = m.names
        except Exception:
            names = {}
        dt = time.time() - t0
        print(">>> Model loaded:", MODEL_PATH, f"({dt:.1f}s)")
        logger.info(f"Model loaded: {MODEL_PATH} ({dt:.1f}s)")
        set_status(f"Model ready ({dt:.1f}s)", "#2E7D32")
    except Exception as e:
        print("Failed to load YOLO model:", e)
        logger.exception("Failed to load YOLO model")
        try:
            set_corner_state("error", "MODEL\nERROR")
            set_status("Model load failed (see terminal)", "#E53935")
        except Exception:
            pass
    finally:
        _model_ready.set()
        _model_loading = False


def ensure_model_async():
    global _model_loading
    if _model_ready.is_set() or _model_loading:
        return
    _model_loading = True
    try:
        set_status("Loading YOLO model...", "#FB8C00")
    except Exception:
        pass
    threading.Thread(target=_load_model_worker, daemon=True).start()

# ========= DB helper wrappers (บางตัวอาจไม่ใช้ตรงๆ แต่เก็บไว้) =========
def fetch_latest_from_inline_testers():
    return db_client.fetch_latest_from_inline_testers()

def fetch_latest_from_InlineTesters():
    return db_client.fetch_latest_from_InlineTesters()

# ========= DB helpers =========
def fetch_latest_vin_from_inline_details():
    return db_client.fetch_latest_vin_from_inline_details()

def fetch_car_info_by_vin_from_gateway(vin):
    return db_client.fetch_car_info_by_vin_from_gateway(vin)

def load_expected_from_master_lotcode(lotcode: str):
    return db_client.load_expected_from_master_lotcode(lotcode, CAM_NO_FILTER)

def fetch_itemcheck_nameai(iditem9: str, select_code1: str):
    return db_client.fetch_itemcheck_nameai(iditem9, select_code1)


# ---------- Business rules ----------
def _is_roof_color_key(key10: str) -> bool:
    txt = (ai_by_key.get(key10, "") or "") + " " + (extra_name_ai_cache.get(key10, "") or "")
    return "ROOF_COLOR" in txt.upper()

def _green_id9_set() -> set:
    return {k[:9] for k in matched_set}

def _digits_7_9(s: str) -> str:
    """ตัวอักษรตำแหน่ง 7-9 (0-based index 6:9) ของ IdItem/key10 สำหรับจัดกลุ่ม candidates"""
    return s[6:9] if (s and len(s) >= 9) else ""

def _enforce_business_rules():
    changed = False
    # 1) ถ้ามีแดงพร้อม % ให้เขียว
    for (id9, sel1, key10) in expected_pairs:
        if key10 in matched_set:
            continue
        if (key10 in ai_conf_by_key) or (id9 in ai_conf_by_id9):
            matched_set.add(key10)
            changed = True
    # 2) ถ้าในชื่อมี "W/O" และไม่มีดำ id9 ซ้ำ ให้เขียว
    for (id9, sel1, key10) in expected_pairs:
        if key10 in matched_set:
            continue
        name_ai = (expected_name_ai.get(key10, "") or "")
        if "W/O" in name_ai.upper():
            if not any(b[:9] == id9 for b in extras_black):
                matched_set.add(key10)
                changed = True
    # 3) ลบดำที่เป็น ROOF_COLOR
    to_remove = {k for k in extras_black if _is_roof_color_key(k)}
    for k in to_remove:
        extras_black.discard(k)
        changed = True
    # 4) ลบดำที่ id9 ซ้ำกับรายการเขียว
    g9 = _green_id9_set()
    if g9:
        to_remove2 = {k for k in extras_black if k[:9] in g9}
        for k in to_remove2:
            extras_black.discard(k)
            changed = True
    if changed:
        rebuild_right_text()

# ========= Extra confidence threshold (NEW) =========
EXTRA_MIN_CONF = 0.70  # default 70%

def _get_extra_min_conf():
    global EXTRA_MIN_CONF
    try:
        v = float(extra_min_conf_var.get().strip())
        if v < 0: v = 0
        if v > 100: v = 100
        EXTRA_MIN_CONF = v / 100.0
    except Exception:
        EXTRA_MIN_CONF = 0.85  # fallback
        extra_min_conf_var.set("85")
    return EXTRA_MIN_CONF

def _is_extra_conf_pass(key10: str) -> bool:
    conf = ai_conf_by_key.get(key10)
    if conf is None:
        # ถ้าไม่ทราบค่า conf ให้ถือว่าไม่ผ่านเกณฑ์ (กันเผลอนับ/บันทึก)
        return False
    return conf >= _get_extra_min_conf()

def apply_extra_threshold_filter():
    """ลบ Extra ที่ความมั่นใจต่ำกว่าเกณฑ์ออกจาก extras_black และ UI"""
    _get_extra_min_conf()
    to_remove = {k for k in list(extras_black) if not _is_extra_conf_pass(k)}
    for k in to_remove:
        try:
            extras_black.discard(k)
        except Exception:
            pass
    rebuild_right_text()
    set_status(f"Applied Extra min % = {int(EXTRA_MIN_CONF*100)}", "#5E35B1")

def _on_extra_min_change(_evt=None):
    apply_extra_threshold_filter()

extra_min_entry.bind("<Return>", _on_extra_min_change)
extra_min_entry.bind("<FocusOut>", _on_extra_min_change)

# ========= Right-panel helpers =========
def update_item_counter_label():
    extra_count = 0 if lock_hide_extras else len(extras_black)
    matched_label.config(
        text=f"Matched {len(matched_set)}/{len(expected_set)} | Extra {extra_count}"
    )
    seen_label.config(text=f"AI Seen: 0" if waiting_for_new_vin else f"AI Seen: {len(matched_set) + extra_count}")

def _ui_prefix_percent(key10: str) -> str:
    conf = ai_conf_by_key.get(key10)
    if conf is None:
        id9 = (key10 or "")[:9]
        conf = ai_conf_by_id9.get(id9)
    if conf is None:
        return ""
    try:
        p = int(round(float(conf) * 100.0))
        return f"({p:02d}%) "
    except Exception:
        return ""

def _first11_keys_set():
    items = sorted(first_seen_index.items(), key=lambda t: t[1])
    first11 = {k for k, idx in items if idx is not None and idx <= 11}
    return first11

# ========= Carryover cache (detection sets for cross-cycle assist) =========
carryover_black_keys = set()
carryover_ai_conf_by_key = {}
carryover_ai_by_key = {}

def _carryover_remember_from_detections(det_list):
    if not det_list:
        return
    for (name, conf) in det_list:
        if name.upper() == "NO_CAR":
            continue
        id9, sel1, key10 = _parse_ai_label(name)
        if not key10:
            continue

        prev = carryover_ai_conf_by_key.get(key10, -1.0)
        if conf is not None and conf > prev:
            carryover_ai_conf_by_key[key10] = float(conf)
            # เก็บข้อความที่จะแสดงตรงๆ (class + %)
            carryover_ai_by_key[key10] = f"{name} {int(conf*100):02d}%" if conf is not None else name

        carryover_black_keys.add(key10)

def adopt_carryover_into_new_cycle():
    """
    นำ item ที่จำไว้ระหว่าง waiting_for_new_vin มาใช้กับ SEQ ใหม่ทันที:
    - ถ้า key อยู่ใน expected_set → matched_set (เขียว)
    - ถ้าไม่อยู่ → extras_black (ดำ) ตาม extra_min_conf
    """
    if not carryover_black_keys:
        return
    for k in list(carryover_black_keys):
        conf = carryover_ai_conf_by_key.get(k)
        txt  = carryover_ai_by_key.get(k)
        if conf is not None:
            ai_conf_by_key[k] = conf
        if txt:
            ai_by_key[k] = txt

        # ถือว่า item นี้ “เคยเห็นแล้วในรอบปัจจุบัน” เพื่อให้ logic อื่นใช้ได้เหมือนกัน
        recent_seen_keys.add(k)

        if not lock_hide_extras and not _is_roof_color_key(k):
            if _is_extra_conf_pass(k):
                extras_black.add(k)
        if k in expected_set:
            matched_set.add(k)
            if k in extras_black:
                try:
                    extras_black.discard(k)
                except Exception:
                    pass

    _enforce_business_rules()
    rebuild_right_text()
    set_status(
        f"Carryover: นำ {len(carryover_black_keys)} รายการมาจับคู่กับ SEQ ใหม่ → "
        f"Match {len(matched_set)}/{len(expected_set)} | Extra {len(extras_black)}",
        "#00897B"
    )
    carryover_black_keys.clear()
    carryover_ai_conf_by_key.clear()
    carryover_ai_by_key.clear()

def rebuild_right_text(force=False):
    """
    อัปเดตกรอบข้อความด้านขวา:
    - ถ้า waiting_for_new_vin == True → แสดง item ที่ YOLO อ่านได้ช่วงรอ SEQ ใหม่เป็น "สีฟ้า"
      (ใช้ข้อมูลจาก carryover_black_keys / carryover_ai_by_key)
    - ถ้าอยู่ในรอบตรวจสอบปัจจุบัน → แสดง expected (แดง/เขียว) + extras (ดำ) ตามเดิม
    
    force=True: บังคับอัปเดตเสมอ (default=False เพื่อ optimize)
    """
    global ui_frame_counter
    
    # Optimization: skip rebuild ทุก UI_TEXT_REBUILD_SKIP_COUNT frames
    if not force and (ui_frame_counter % UI_TEXT_REBUILD_SKIP_COUNT) != 0:
        ui_frame_counter += 1
        return
    ui_frame_counter += 1
    
    class_text.config(state="normal")
    class_text.delete("1.0", tk.END)

    # --- No_Car realtime line (if recently seen) ---
    try:
        if latest_no_car_confs and (time.time() - float(latest_no_car_ts or 0.0)) <= 2.0:
            for c in list(latest_no_car_confs):
                try:
                    cf = float(c)
                except Exception:
                    continue
                p = int(round((cf * 100.0) if cf <= 1.0 else cf))
                class_text.insert(tk.END, f"No_Car ({p}%)\n", "noc")
    except Exception:
        pass

    # --- 1) ช่วงกำลังรอ SEQ ใหม่: แสดง carryover เป็นสีฟ้า ---
    if waiting_for_new_vin:
        if carryover_black_keys:
            class_text.insert(tk.END, "Waiting SEQ: YOLO items\n", "blue")
            class_text.insert(tk.END, "-------------------------\n", "blue")
        for key10 in sorted(carryover_black_keys):
            txt = carryover_ai_by_key.get(key10)
            if not txt:
                txt = key10
            class_text.insert(tk.END, txt + "\n", "blue")

        class_text.config(state="disabled")
        update_item_counter_label()
        return

    # --- 2) อยู่ในรอบตรวจสอบปัจจุบัน: ใช้ logic เดิม (แดง/เขียว/ดำ) ---
    if not lock_hide_extras:
        green9 = _green_id9_set()
        extras_effective = []
        for k in sorted(extras_black):
            if k[:9] in green9:
                continue
            if _is_roof_color_key(k):
                continue
            if not _is_extra_conf_pass(k):
                continue
            extras_effective.append(k)
    else:
        extras_effective = []

    # แสดงแบบรวมทั้งหมดในลิสต์เดียว (ไม่แยก section)
    # สีคงเดิม: expected=แดง/เขียว, extras=ดำ, seen-only=ฟ้า
    entries = {}

    for (_iditem9, _sel1, key10) in expected_pairs:
        if not key10:
            continue
        # ถ้ายังไม่เคยเห็น key10 นี้จาก YOLO เลย ให้แสดงเป็นสีขาว (DB-only)
        if key10 in matched_set:
            tag = "green"
        elif key10 in ai_conf_by_key:
            tag = "red"
        else:
            tag = "white"
        name_ai = expected_name_ai.get(key10, "") if SHOW_NAME_ON_EXPECTED else ""
        base = key10 if not name_ai else f"{key10}_{_shorten(name_ai, MAX_NAME_CHARS)}"
        entries[key10] = (tag, base)

    if not lock_hide_extras:
        for key10 in extras_effective:
            if not key10:
                continue
            nm = extra_name_ai_cache.get(key10, "") if SHOW_NAME_ON_EXTRAS else ""
            base = f"{key10}_{_shorten(nm, MAX_NAME_CHARS)}" if nm else key10
            entries[key10] = ("black", base)

    for key10 in recent_seen_keys:
        if not key10 or key10 in entries:
            continue
        txt = ai_by_key.get(key10) or key10
        entries[key10] = ("blue", txt)

    def _sort_by_id9_alpha(k):
        return ((k[:9] if len(k) >= 9 else k), k)

    for key10 in sorted(entries.keys(), key=_sort_by_id9_alpha):
        tag, base = entries[key10]
        # รายการ DB-only (สีขาว) แสดงได้ทันที ไม่ต้องรอ Frame gate
        if tag != "white" and (not _accum_frame_meets_ui_db_gate(key10)):
            continue
        all_percent_raw = float(allpercent_by_key.get(key10, 0.0))
        # ถ้าเพิ่งเริ่มเห็น label และยังไม่ทันสะสมเวลา ให้แสดงค่าพื้นฐานจาก conf ล่าสุดก่อน
        if all_percent_raw <= 0.0:
            c0 = ai_conf_by_key.get(key10)
            if c0 is not None:
                try:
                    all_percent_raw = float(c0) * 100.0
                except Exception:
                    all_percent_raw = 0.0
        all_percent_val = int(round(all_percent_raw))
        line = f"[{all_percent_val}] {base}"
        class_text.insert(tk.END, line + "\n", tag)

    class_text.config(state="disabled")
    update_item_counter_label()

def reset_cycle_state(keep_recent_seen=True, clear_right_text=True):
    expected_pairs.clear()
    expected_set.clear()
    matched_set.clear()
    extras_black.clear()
    ai_reads_full.clear()
    ai_by_key.clear()
    ai_by_id9.clear()
    ai_conf_by_key.clear()
    ai_conf_by_id9.clear()
    allpercent_by_key.clear()
    frame_count_by_key.clear()
    expected_name_ai.clear()
    extra_name_ai_cache.clear()
    ok_key10_persisted_this_cycle.clear()
    if not keep_recent_seen:
        recent_seen_keys.clear()
    _detect_since.clear()
    first_seen_index.clear()
    global _seen_counter
    _seen_counter = 0
    if clear_right_text:
        rebuild_right_text()
    update_item_counter_label()
    _clear_ng_buffer()

SHIFT_RESET_TIMES = [
    # Day shift
    (7, 30),
    (9, 40),
    (12, 30),
    (14, 40),
    (16, 40),
    (17, 00),
    # Night shift
    (19, 30),
    (21, 40),
    (0, 30),
    (2, 40),
    (4, 40),
    (5, 00),
]
SHIFT_RESET_GRACE_SEC = 59
_shift_reset_done_keys = set()

def _shift_reset_key(dt: datetime, hh: int, mm: int) -> str:
    return f"{dt.date().isoformat()}_{hh:02d}:{mm:02d}"

def reset_labels_for_shift_time():
    """
    ล้าง label ที่มาจาก YOLO ใหม่หมด (เริ่มจับใหม่)
    แต่ไม่ล้างข้อมูลจาก DB (expected_pairs/expected_set/expected_name_ai ฯลฯ)
    """
    global persisted_this_cycle, early_saved_all_green, lock_hide_extras
    global best_frame_locked_saved, carryover_locked_saved
    global _no_car_streak, _last_seen_non_no_car_ts, _seen_counter

    # YOLO-derived state
    matched_set.clear()
    extras_black.clear()
    ai_reads_full.clear()
    ai_by_key.clear()
    ai_by_id9.clear()
    ai_conf_by_key.clear()
    ai_conf_by_id9.clear()
    allpercent_by_key.clear()
    frame_count_by_key.clear()
    recent_seen_keys.clear()
    _detect_since.clear()
    first_seen_index.clear()
    _seen_counter = 0

    # Buffers/state tied to YOLO detection history
    _clear_ng_buffer()
    _clear_post_nocar3()
    _reset_carryover_best()
    try:
        car = inline_data or {}
        _reset_best_frame_for_new_seq(car.get("VinNo", ""), car.get("LotCodeCar", ""), car.get("SeqCar", ""))
    except Exception:
        pass

    # Allow fresh save decisions after shift reset
    persisted_this_cycle = False
    early_saved_all_green = False
    lock_hide_extras = False
    best_frame_locked_saved = False
    carryover_locked_saved = False
    _no_car_streak = 0
    _last_seen_non_no_car_ts = None

    rebuild_right_text(force=True)
    update_item_counter_label()
    set_corner_state("active", "SHIFT\nRESET")
    set_status("Shift reset: cleared YOLO labels (start fresh)", "#F57C00")

def _maybe_shift_time_reset(now_dt: datetime | None = None):
    if now_dt is None:
        now_dt = datetime.now()
    for (hh, mm) in SHIFT_RESET_TIMES:
        if now_dt.hour == hh and now_dt.minute == mm and now_dt.second <= SHIFT_RESET_GRACE_SEC:
            k = _shift_reset_key(now_dt, hh, mm)
            if k not in _shift_reset_done_keys:
                _shift_reset_done_keys.add(k)
                logger.info(f"[SHIFT_RESET] Trigger at {hh:02d}:{mm:02d} -> reset YOLO labels/Frame/All_Percent")
                reset_labels_for_shift_time()
            return

def build_current_snapshot():
    first11 = _first11_keys_set()
    extras_effective = {
        k for k in extras_black
        if not (k in matched_set and k in first11)
        if _is_extra_conf_pass(k)
        if not _is_roof_color_key(k)
        if k[:9] not in _green_id9_set()
    }
    return {
        "inline_data": (inline_data.copy() if inline_data else {}),
        "expected_pairs": expected_pairs.copy(),
        "expected_set": expected_set.copy(),
        "matched_set": matched_set.copy(),
        "extras_black": extras_effective,
        "ai_conf_by_key": ai_conf_by_key.copy(),
        "allpercent_by_key": allpercent_by_key.copy(),
        "frame_count_by_key": frame_count_by_key.copy(),
        "ai_reads_full": ai_reads_full.copy(),
        "ai_by_key": ai_by_key.copy(),
        "ai_by_id9": ai_by_id9.copy(),
    }

def _snapshot_has_ng(snapshot, include_extras=True) -> bool:
    if not snapshot:
        return True
    exp_pairs = snapshot.get("expected_pairs", [])
    if not exp_pairs:
        return True
    matched = snapshot.get("matched_set", set())
    ai_conf = snapshot.get("ai_conf_by_key", ai_conf_by_key)

    for (_id9_exp, _sel1_exp, key10_exp) in exp_pairs:
        seen_this_key = (key10_exp in ai_conf)
        is_green = (key10_exp in matched) or seen_this_key
        if not is_green:
            return True

    if include_extras and SAVE_EXTRAS_WHEN_NO_DB:
        green9 = _green_id9_set()
        extras = snapshot.get("extras_black", set())
        for key10 in sorted(extras):
            if _is_roof_color_key(key10):
                continue
            if key10[:9] in green9:
                continue
            return True

    return False

def _result_prefix_from_snapshot(snapshot, include_extras=True) -> str:
    return ""

def _is_no_car_label(name: str) -> bool:
    """รองรับรูปแบบสะกด No Car หลายแบบ: No_Car / No Car / NOCAR / NO CAR"""
    try:
        s = (name or "").upper().replace("_", "").replace(" ", "")
        return s == "NOCAR"
    except Exception:
        return False

def _count_to_frame_units(count_val):
    """แปลงจำนวนครั้งสะสมเป็นค่า Frame โดยถ้าเคยเห็นแล้วต้องไม่เป็น 0."""
    try:
        c = float(count_val)
    except Exception:
        return 0
    if c <= 0:
        return 0
    i = int(round(c))
    return i if i >= 1 else 1

def _accum_frame_count_int(key10: str) -> int:
    try:
        return int(round(float(frame_count_by_key.get(key10, 0.0) or 0.0)))
    except Exception:
        return 0

def _accum_frame_meets_ui_db_gate(key10: str) -> bool:
    return _accum_frame_count_int(key10) >= MIN_ACCUM_FRAME_FOR_UI_AND_DB

def persist_cycle_results(snapshot, include_extras=True):
    """
    บันทึกผลลง AI_Result_Spec ตามหลัก ub1:
    - สำหรับแต่ละ spec (id9) หา label ที่ตรวจจับได้ทั้งหมดที่ digit 7-9 ตรงกัน
    - เปรียบ All_Percent (ผลรวมเปอร์เซ็นที่บวกสะสมแต่ละครั้ง) → label ที่สูงสุด = winner
    - เปรียบ digit ที่ 10 ของ winner กับ SelectCode ของ spec + Percent_AI >= OK_PERCENT_THRESHOLD
      → ตรงและเกินเกณฑ์ = OK, ไม่ตรงหรือต่ำกว่า = NG
    - label ที่แพ้ = No_Judge; extra = No_Judge
    - Percent_AI = All_Percent / FrameCount
    - แถวที่ Frame < MIN_ACCUM_FRAME_FOR_UI_AND_DB จะไม่ถูกส่งเข้า DB
    """
    if not snapshot:
        logger.warning("persist_cycle_results: empty snapshot; skip")
        print("[SQL][persist] ABORT: empty snapshot (no INSERT)", flush=True)
        return 0
    car = snapshot.get("inline_data") or {}
    lotcode = car.get("LotCodeCar", "")
    vin = car.get("VinNo", "")
    seq = car.get("SeqCar", "")
    idmodel = (str(car.get("IdModel", "")) or "")[:4]
    exp_pairs = snapshot.get("expected_pairs", [])
    extras = snapshot.get("extras_black", set()) if include_extras else set()
    by_key = snapshot.get("ai_by_key", {})
    by_id9 = snapshot.get("ai_by_id9", {})
    # ใช้ค่าสะสม "สูงสุด" ระหว่าง snapshot กับสถานะปัจจุบัน
    # เพื่อกันกรณีจังหวะ save ได้ค่าไม่ทันล่าสุดแล้ว All_Percent ตกเหลือค่ารอบเดียว
    snap_allpercent = snapshot.get("allpercent_by_key", {}) or {}
    snap_frame = snapshot.get("frame_count_by_key", {}) or {}
    allpercent_map = dict(snap_allpercent)
    frame_map = dict(snap_frame)
    for k, v in (allpercent_by_key or {}).items():
        if float(v) > float(allpercent_map.get(k, 0.0)):
            allpercent_map[k] = float(v)
    for k, v in (frame_count_by_key or {}).items():
        if float(v) > float(frame_map.get(k, 0.0)):
            frame_map[k] = float(v)
    no_db_spec = (len(exp_pairs) == 0)
    if no_db_spec:
        logger.info(f"No DB spec; will persist extras only if available (vin={vin}, lot={lotcode}, seq={seq})")
        set_status("No DB spec: จะบันทึกเฉพาะรายการที่ตรวจจับได้ (extras)", "#6D4C41")

    def _frame_ok_from_map(key10: str) -> bool:
        try:
            return int(round(float(frame_map.get(key10, 0.0) or 0.0))) >= MIN_ACCUM_FRAME_FOR_UI_AND_DB
        except Exception:
            return False

    print(
        f"[SQL][persist] build rows: vin={vin!r} seq={seq!r} lot={lotcode!r} "
        f"exp_pairs={len(exp_pairs)} extras_in_snap={len(extras)} "
        f"allpercent_keys={len(allpercent_map)} frame_keys={len(frame_map)} "
        f"no_db_spec={no_db_spec} include_extras={include_extras}",
        flush=True,
    )

    rows = []
    now_date = datetime.now().date().isoformat()
    now_time = datetime.now().strftime("%H:%M:%S")
    picture = (last_snapshot_picture_path or "")

    ok_key10_local = set()
    missing_expected = []

    for (iditem9_exp, sel1_exp, key10_exp) in exp_pairs:
        spec, result_sql = fetch_itemcheck_nameai(iditem9_exp, sel1_exp)
        if _contains_blacktape_text(spec) or _contains_blacktape_text(result_sql):
            continue

        key_exp = _digits_7_9(iditem9_exp)
        candidates = {
            b10: ap
            for b10, ap in allpercent_map.items()
            if _digits_7_9(b10) == key_exp and _frame_ok_from_map(b10)
        }

        if not candidates:
            missing_expected.append((iditem9_exp, sel1_exp, key10_exp, spec, result_sql))
            continue

        winner_b10 = max(candidates, key=lambda b: candidates[b])
        winner_allpercent = int(round(candidates[winner_b10]))
        winner_count = float(frame_map.get(winner_b10, 0.0))
        winner_frame = _count_to_frame_units(winner_count)
        winner_percent_ai = round(winner_allpercent / winner_count, 2) if winner_count > 0 else 0.0
        winner_sel = (winner_b10[9:10] if len(winner_b10) >= 10 else "")

        ok_threshold_percent = _get_extra_min_conf() * 100.0
        if (winner_sel == sel1_exp) and (winner_percent_ai >= ok_threshold_percent):
            result = "OK"
        else:
            result = "NG"
        if result == "OK":
            ok_key10_persisted_this_cycle.add(key10_exp)
            ok_key10_local.add(key10_exp)

        winner_ai_read = by_key.get(winner_b10) or by_id9.get(winner_b10[:9], "") or winner_b10
        if winner_ai_read and _should_ignore_readable_label(winner_ai_read):
            winner_ai_read = winner_b10
        winner_ai_spec = ""
        if winner_sel:
            _, name_ai2 = fetch_itemcheck_nameai(winner_b10[:9], winner_sel)
            winner_ai_spec = name_ai2 or ""
        if _contains_blacktape_text(winner_ai_spec):
            winner_ai_spec = ""

        rows.append({
            "VinNo": vin, "Date": now_date, "Time": now_time, "Picture": picture,
            "SEQ": seq, "IdModel": idmodel, "LotCode": lotcode, "CamNo": CAM_NO_FILTER,
            "IdItem": iditem9_exp, "SelectCode": sel1_exp, "Spec": spec, "Result_SQL": result_sql,
            "AI_Read": winner_ai_read, "Percent_AI": winner_percent_ai, "Result": result,
            "AI_SelectCode": winner_sel, "AI_Spec": winner_ai_spec, "PC": "PCmain",
            "Frame": winner_frame, "All_Percent": winner_allpercent,
        })

        for b10, ap in candidates.items():
            if b10 == winner_b10:
                continue
            loser_count = float(frame_map.get(b10, 0.0))
            loser_frame = _count_to_frame_units(loser_count)
            loser_ap = int(round(ap))
            loser_percent_ai = round(loser_ap / loser_count, 2) if loser_count > 0 else 0.0
            loser_sel = (b10[9:10] if len(b10) >= 10 else "")
            loser_ai_read = by_key.get(b10) or by_id9.get(b10[:9], "") or b10
            if loser_ai_read and _should_ignore_readable_label(loser_ai_read):
                loser_ai_read = b10
            loser_ai_spec = ""
            if loser_sel:
                _, name_ai4 = fetch_itemcheck_nameai(b10[:9], loser_sel)
                loser_ai_spec = name_ai4 or ""
            if _contains_blacktape_text(loser_ai_spec):
                loser_ai_spec = ""
            rows.append({
                "VinNo": vin, "Date": now_date, "Time": now_time, "Picture": picture,
                "SEQ": seq, "IdModel": idmodel, "LotCode": lotcode, "CamNo": CAM_NO_FILTER,
                "IdItem": iditem9_exp, "SelectCode": sel1_exp, "Spec": spec, "Result_SQL": result_sql,
                "AI_Read": loser_ai_read, "Percent_AI": loser_percent_ai, "Result": "No_Judge",
                "AI_SelectCode": loser_sel, "AI_Spec": loser_ai_spec, "PC": "PCmain",
                "Frame": loser_frame, "All_Percent": loser_ap,
            })

    # Pass 2: insert NG เฉพาะ expected ที่ไม่มี candidate และยังไม่เคย OK
    for (iditem9_exp, sel1_exp, key10_exp, spec, result_sql) in missing_expected:
        if key10_exp in ok_key10_persisted_this_cycle or key10_exp in ok_key10_local:
            continue
        rows.append({
            "VinNo": vin, "Date": now_date, "Time": now_time, "Picture": picture,
            "SEQ": seq, "IdModel": idmodel, "LotCode": lotcode, "CamNo": CAM_NO_FILTER,
            "IdItem": iditem9_exp, "SelectCode": sel1_exp, "Spec": spec, "Result_SQL": result_sql,
            "AI_Read": "", "Percent_AI": 0.0, "Result": "NG",
            "AI_SelectCode": "", "AI_Spec": "", "PC": "PCmain",
            "Frame": MIN_ACCUM_FRAME_FOR_UI_AND_DB, "All_Percent": 0,
        })

    if include_extras and SAVE_EXTRAS_WHEN_NO_DB:
        green9 = _green_id9_set()
        for key10 in sorted(extras):
            if not _frame_ok_from_map(key10):
                continue
            if _is_roof_color_key(key10):
                continue
            if key10[:9] in green9:
                continue
            ai_read_str = by_key.get(key10) or key10
            if ai_read_str and _should_ignore_readable_label(ai_read_str):
                ai_read_str = key10
            ai_id9 = (key10 or "")[:9]
            ai_sel1 = (key10 or "")[9:10]
            nm = extra_name_ai_cache.get(key10, "")
            ai_spec = nm
            if not ai_spec and ai_id9 and ai_sel1:
                _ic3, name_ai3 = fetch_itemcheck_nameai(ai_id9, ai_sel1)
                ai_spec = name_ai3
            if _contains_blacktape_text(ai_read_str) or _contains_blacktape_text(ai_spec):
                continue
            ap = int(round(allpercent_map.get(key10, 0.0)))
            seen_count = float(frame_map.get(key10, 0.0))
            fc = _count_to_frame_units(seen_count)
            percent_ai = round(ap / seen_count, 2) if seen_count > 0 else 0.0
            rows.append({
                "VinNo": vin, "Date": now_date, "Time": now_time, "Picture": picture,
                "SEQ": seq, "IdModel": idmodel, "LotCode": lotcode, "CamNo": CAM_NO_FILTER,
                "IdItem": ai_id9, "SelectCode": "", "Spec": "", "Result_SQL": "",
                "AI_Read": ai_read_str or "", "Percent_AI": percent_ai, "Result": "No_Judge",
                "AI_SelectCode": ai_sel1, "AI_Spec": ai_spec, "PC": "PCmain",
                "Frame": fc, "All_Percent": ap,
            })

    rows = [
        r for r in rows
        if int(r.get("Frame", 0) or 0) >= MIN_ACCUM_FRAME_FOR_UI_AND_DB
    ]
    if rows:
        try:
            max_ap = max([r.get("All_Percent", 0) for r in rows]) if rows else 0
            max_fc = max([r.get("Frame", 0) for r in rows]) if rows else 0
            print(f"[PERSIST][AI_Result_Spec] summary rows={len(rows)} maxAllPercent={max_ap} maxFrame={max_fc}")
        except Exception:
            pass
        db_client.enqueue_results(rows)
        logger.info(f"Persist queued: {len(rows)} rows (vin={vin}, lot={lotcode}, seq={seq})")
        print(f"[PERSIST][AI_Result_Spec] queued rows={len(rows)} vin={vin} seq={seq} lot={lotcode} no_db_spec={no_db_spec}")
        return len(rows)
    logger.info(f"Nothing to persist (rows=0) (vin={vin}, lot={lotcode}, seq={seq})")
    print(
        f"[SQL][persist] NO INSERT: rows=0 vin={vin} seq={seq} lot={lotcode} "
        f"no_db_spec={no_db_spec} (blacktape / ไม่มี candidates+extras / หรือ Frame ทุกแถว < {MIN_ACCUM_FRAME_FOR_UI_AND_DB})",
        flush=True,
    )
    return 0

# ========= Expected preload & instant-compare =========
def apply_seen_to_expected():
    changed = False
    for k in list(recent_seen_keys):
        if k in expected_set and k not in matched_set:
            matched_set.add(k)
            changed = True
        elif k not in expected_set and k not in extras_black and k:
            if not lock_hide_extras:
                if not _is_roof_color_key(k):
                    if _is_extra_conf_pass(k):
                        extras_black.add(k)
                        changed = True
                        db_client.queue_extra_name(k)
    if changed:
        rebuild_right_text()
        set_status(
            f"Instant compare: Match {len(matched_set)}/{len(expected_set)} | Extra {len(extras_black)}",
            "#1E88E5"
        )

def _add_expected_rows(rows):
    try:
        name_map = db_client.fetch_nameai_bulk(rows)
    except Exception as e:
        logger.warning(f"bulk name preload failed: {e}")
        name_map = {}

    for id9, sel1, key10 in rows:
        nm = name_map.get(key10, "") or ""
        if _should_ignore_expected_item(id9, key10):
            continue
        if _contains_blacktape_text(nm):
            continue
        expected_pairs.append((id9, sel1, key10))
        expected_set.add(key10)
        expected_name_ai[key10] = nm

def preload_expected_for_current_inline(do_instant_compare=True):
    """
    โหลดสเปคจาก AI_Master_Select_Lotcode โดยใช้ LotCodeCar ที่มาจาก
    GatewayQC.dbo.Cars (ผ่าน fetch_car_info_by_vin_from_gateway แล้วเก็บใน inline_data)
    """
    car = inline_data or {}
    vin = (car.get("VinNo") or "").strip()
    lotcode = (car.get("LotCodeCar") or "").strip()

    if not lotcode:
        set_status("No LotCode (from Cars/GatewayQC) → cannot preload specs", "#E53935")
        return reset_cycle_state(keep_recent_seen=True)

    rows = load_expected_from_master_lotcode(lotcode)
    _add_expected_rows(rows)
    rebuild_right_text()
    set_status(
        (f"Preloaded {len(rows)} specs from LotCode={lotcode} (Cars/GatewayQC)" if rows else
         f"No spec rows for LotCode={lotcode} (Cars/GatewayQC)"), "#2E7D32"
    )
    if do_instant_compare:
        apply_seen_to_expected()

# ========= Camera scan/select =========
def try_open_one(index, backend_flag, test_w=640, test_h=480):
    cap = cv2.VideoCapture(index, backend_flag)
    if not cap.isOpened():
        cap.release()
        return None
    try:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, test_w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, test_h)
        if backend_flag == cv2.CAP_DSHOW:
            try:
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            except Exception:
                pass
    except Exception:
        pass
    ok, frame = cap.read()
    cap.release()
    return (index, backend_flag) if (ok and frame is not None and frame.size > 0) else None

def scan_cameras(max_index=8):
    items = []
    for idx in range(max_index + 1):
        t = try_open_one(idx, cv2.CAP_MSMF)
        if t is not None:
            items.append((idx, "MSMF"))
            continue
        t = try_open_one(idx, cv2.CAP_DSHOW)
        if t is not None:
            items.append((idx, "DSHOW"))
            continue
    return items

def do_rescan():
    # Keep sync wrapper for button/hotkey
    return do_rescan_async()


def _apply_scan_results(items):
    if not items:
        camera_combo["values"] = ["<no camera found>"]
        camera_combo.current(0)
        set_status("No camera found (RESCAN)", "#E53935")
        return
    display = [f"Camera {i} [{b}]" for (i, b) in items]
    camera_combo["values"] = display
    camera_combo._map = {f"Camera {i} [{b}]": (i, b) for (i, b) in items}
    try:
        target = AUTO_START_CAMERA_INDEX
        j = next((k for k, (cam_idx, _b) in enumerate(items) if cam_idx == target), None)
        camera_combo.current(j if j is not None else 0)
    except Exception:
        camera_combo.current(0)
    set_status("Camera list updated", "#2E7D32")

    global _auto_started_once
    if AUTO_START_ON_LAUNCH and not _auto_started_once:
        sel = camera_combo.get()
        if sel and "<no camera" not in sel:
            _auto_started_once = True
            on_start_clicked()


def do_rescan_async():
    set_status("Scanning cameras...", "#FB8C00")

    def _worker():
        try:
            items = scan_cameras()
        except Exception as e:
            items = []
            print("Scan error:", e)
            logger.exception("Scan error")
        root.after(0, lambda: _apply_scan_results(items))

    threading.Thread(target=_worker, daemon=True).start()

# ========= Helper: required expected (exclude W/O) =========
def _required_expected_keys_for_frame():
    req = set()
    for (_id9, _sel1, key10) in expected_pairs:
        nm = (expected_name_ai.get(key10, "") or "")
        if "W/O" in nm.upper():
            continue
        req.add(key10)
    return req

def _all_ok_required_in_frame(keys_in_frame: set) -> bool:
    req = _required_expected_keys_for_frame()
    return req.issubset(keys_in_frame) and (len(expected_set) >= 1)

# ==== NEW: post-NoCar+3s snapshot state ====
post_nocar_transition_ts = None    # เวลาเกิดทรานซิชัน "Only No_Car → พบรถ"
post_nocar3_frame = None           # รูปที่คาบหลังครบ 3 วินาที
post_nocar3_meta = {"vin":"", "lot":"", "seq":""}
post_nocar3_captured = False
_prev_only_no_car = True           # สถานะเฟรมก่อนหน้า: มีแต่ No_Car เท่านั้น

def _capture_post_nocar3_if_due(now_ts, annotated_frame):
    """ครบ 3 วินาทีหลัง No Car หาย → คาบภาพพร้อมเมตา"""
    global post_nocar_transition_ts, post_nocar3_frame, post_nocar3_meta, post_nocar3_captured
    if post_nocar_transition_ts is None:
        return
    if post_nocar3_captured:
        return
    if (now_ts - post_nocar_transition_ts) >= 3.0 and annotated_frame is not None:
        car = inline_data or {}
        post_nocar3_frame = annotated_frame.copy()
        post_nocar3_meta = {
            "vin": _sanitize_for_filename(car.get("VinNo","")),
            "lot": _sanitize_for_filename(car.get("LotCodeCar","")),
            "seq": _sanitize_for_filename(car.get("SeqCar","")),
        }
        post_nocar3_captured = True
        logger.info(f"[Post-NoCar+3s] Captured frame for VIN={post_nocar3_meta['vin']} SEQ={post_nocar3_meta['seq']}")

def _clear_post_nocar3():
    global post_nocar_transition_ts, post_nocar3_frame, post_nocar3_meta, post_nocar3_captured
    post_nocar_transition_ts = None
    post_nocar3_frame = None
    post_nocar3_meta = {"vin":"", "lot":"", "seq":""}
    post_nocar3_captured = False

def _save_specific_frame_with_prefix(frame_bgr, prefix, meta):
    """เซฟรูปที่ส่งเข้ามา (ไม่ใส่ prefix)"""
    global last_snapshot_picture_path
    if _has_saved_image_for_cycle():
        return ""
    if frame_bgr is None:
        return ""
    reused = _reuse_last_snapshot_if_duplicate(frame_bgr)
    if reused:
        return reused
    t = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    vin = meta.get("vin","")
    lot = meta.get("lot","")
    seq = meta.get("seq","")
    fname = f"{vin}_{lot}_{seq}_{t}.jpg"
    path = os.path.join(SAVE_DIR, fname)
    if _save_image_and_mark(frame_bgr, path):
        last_snapshot_picture_path = path
        logger.info(f"Saved snapshot by post-NoCar+3s: {path}")
        flash_info("SNAP SAVED", 900, bg="#90CAF9")
        return path
    return ""

# ========= UI loop & Save logic =========
def _push_snapshot_history():
    try:
        snap = build_current_snapshot()
        ts = time.time()
        snapshot_history.append((ts, snap))
        cutoff = ts - SNAPSHOT_HISTORY_SEC
        while len(snapshot_history) and snapshot_history[0][0] < cutoff:
            snapshot_history.popleft()
    except Exception as e:
        logger.warning(f"push snapshot history failed: {e}")

def _find_snapshot_before(ts_target, fallback_last=True):
    if not snapshot_history:
        return None
    best = None
    best_dt = 1e9
    cur_vin = (inline_data or {}).get("VinNo", None)
    for (ts, snap) in snapshot_history:
        vin = (snap.get("inline_data") or {}).get("VinNo", None)
        if cur_vin and vin != cur_vin:
            continue
        if ts <= ts_target:
            dt = ts_target - ts
            if dt < best_dt:
                best_dt = dt
                best = snap
    if best is None and fallback_last:
        for ts, snap in reversed(snapshot_history):
            vin = (snap.get("inline_data") or {}).get("VinNo", None)
            if cur_vin and vin == cur_vin:
                return snap
        return None
    return best

def ui_update():
    global tk_img_ref, _no_car_streak, last_snapshot_picture_path, _last_seen_non_no_car_ts, _seen_counter
    global early_saved_all_green, persisted_this_cycle, lock_hide_extras, no_car_persist_done_this_streak
    global latest_annotated_frame
    global carryover_best_frame, carryover_best_count, carryover_best_meta
    global _prev_only_no_car, post_nocar_transition_ts
    global latest_no_car_confs, latest_no_car_ts

    # ตรวจ timer SEQ change (รอ 2 วิ ค่อยบันทึก)
    _process_seq_change_after_delay()

    if DISPLAY_W is None and first_dims_ready.is_set():
        configure_display_from_window()

    try:
        annotated_frame, det_list = result_queue.get_nowait()
    except queue.Empty:
        annotated_frame, det_list = None, None

    # ถ้ายังไม่มีผลจาก YOLO (ยังโหลดโมเดล/ยังไม่เริ่ม infer) ให้แสดงภาพดิบจากกล้องทันที
    if annotated_frame is None:
        with latest_frame_lock:
            if latest_frame is not None:
                annotated_frame = latest_frame.copy()
                det_list = det_list or []

    # --- Capture No_Car confidence realtime for text area ---
    if det_list:
        try:
            confs = []
            for (n, c) in det_list:
                if _is_no_car_label(n):
                    try:
                        cv = float(c)
                    except Exception:
                        continue
                    confs.append(cv)
            if confs:
                confs.sort(reverse=True)
                latest_no_car_confs = confs
                latest_no_car_ts = time.time()
        except Exception:
            pass

    # --- แสดงภาพ + เก็บ annotated ล่าสุดสำหรับ UI ---
    if annotated_frame is not None and DISPLAY_W is not None and DISPLAY_H is not None:
        with latest_annotated_lock:
            latest_annotated_frame = annotated_frame.copy()

        # ใช้ letterbox + VIEW_ZOOM=1.0 ให้กินพื้นที่ซ้ายเต็ม (ย่อเฉพาะรักษาอัตราส่วน)
        shown = letterbox(
            annotated_frame,
            int(DISPLAY_W * VIEW_ZOOM),
            int(DISPLAY_H * VIEW_ZOOM),
            color=(0, 0, 0)
        )

        # FPS text เล็กลง (สีเขียว)
        cv2.putText(
            shown,
            f"INF: {infer_fps:.1f} FPS ({'GPU' if use_cuda else 'CPU'})",
            (20,35),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0,255,0) if use_cuda else (0,200,255),
            1,
            cv2.LINE_AA
        )
        if current_cam_index is not None and current_cam_backend is not None:
            cv2.putText(
                shown,
                f"CAM {current_cam_index} [{current_cam_backend}]",
                (20,55),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (200,200,200),
                1,
                cv2.LINE_AA
            )
        rgb = cv2.cvtColor(shown, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)
        tk_img_ref = ImageTk.PhotoImage(image=img)
        video_label.config(image=tk_img_ref)
        video_label.image = tk_img_ref

    # -------- โหมด waiting_for_new_vin ----------
    if waiting_for_new_vin:
        if det_list:
            detected_items_wo_nocar = [(name, conf) for (name, conf) in det_list if not _is_no_car_label(name)]
            if detected_items_wo_nocar:
                prev_car = inline_data or {}
                _update_carryover_candidate(
                    annotated_frame,
                    detected_items_wo_nocar,
                    prev_car.get("VinNo",""),
                    prev_car.get("LotCodeCar",""),
                    prev_car.get("SeqCar","")
                )
                _carryover_remember_from_detections(detected_items_wo_nocar)
                # NEW: อัปเดตกรอบข้อความทันทีให้เห็น item สีฟ้า
                rebuild_right_text()

        set_corner_state("waiting", "WAITING\nVIN")
        _push_snapshot_history()
        root.after(12, ui_update)
        return

    # ----------- มี VIN/SEQ แล้ว (active รอบ) ----------------
    now_ts = time.time()

    keys_in_frame = []
    non_no_car_items = []
    if det_list is not None:
        detected_items = [(name, conf) for (name, conf) in det_list if not _is_no_car_label(name)]
        non_no_car_items = detected_items
        only_no_car = (len(detected_items) == 0) and any(_is_no_car_label(n) for (n, _) in det_list)

        # ==== NEW: ตรวจจับทรานซิชัน Only No_Car → พบรถ แล้วเริ่มจับเวลา 3 วิ ====
        if _prev_only_no_car and not only_no_car:
            post_nocar_transition_ts = now_ts
            logger.info("[Post-NoCar+3s] transition start (car just appeared)")
        _prev_only_no_car = only_no_car
        _capture_post_nocar3_if_due(now_ts, annotated_frame)

        if len(detected_items) > 0:
            _last_seen_non_no_car_ts = now_ts

        # ub1: ต่อ 1 เฟรม ต่อ key10 ใช้ conf สูงสุดในเฟรม (ไม่บวกซ้ำถ้า AI ส่ง label ซ้ำหลายบรรทัด)
        frame_conf_by_key = {}
        for (item_str, conf) in detected_items:
            id9, sel1, key10 = _parse_ai_label(item_str)
            if not key10:
                continue
            keys_in_frame.append(key10)

            prev = ai_conf_by_key.get(key10, -1.0)
            if conf is not None and (conf > prev):
                ai_conf_by_key[key10] = float(conf)
                ai_by_key[key10] = f"{item_str}{_percent_str(conf)}"
            if conf is not None:
                try:
                    c = float(conf)
                except (TypeError, ValueError):
                    c = 0.0
                if c > frame_conf_by_key.get(key10, -1.0):
                    frame_conf_by_key[key10] = c

            if id9:
                prev9 = ai_conf_by_id9.get(id9, -1.0)
                if conf is not None and (conf > prev9):
                    ai_conf_by_id9[id9] = float(conf)
                    ai_by_id9[id9] = f"{item_str}{_percent_str(conf)}"

        # สะสมแบบจำนวนครั้ง: ต่อ key10 ต่อรอบ update บวกเปอร์เซ็น 1 ครั้ง (ใช้ค่าสูงสุดของ key ในรอบนั้น)
        if not only_no_car:
            for key10, new_c in frame_conf_by_key.items():
                allpercent_by_key[key10] = allpercent_by_key.get(key10, 0.0) + (new_c * 100.0)
                frame_count_by_key[key10] = frame_count_by_key.get(key10, 0.0) + 1.0

        # stable tracking
        for k in keys_in_frame:
            if k not in _detect_since:
                _detect_since[k] = now_ts
        for k in list(_detect_since.keys()):
            if k not in keys_in_frame:
                _detect_since.pop(k, None)

        stable_keys = [k for k, ts0 in _detect_since.items() if (now_ts - ts0) >= DETECT_STABLE_SEC]

        changed = False
        new_keys_stable = []
        new_keys_first_seen = []
        for key10 in stable_keys:
            if (key10 not in matched_set) and (key10 not in extras_black):
                _seen_counter += 1
                first_seen_index.setdefault(key10, _seen_counter)
                if key10 in expected_set:
                    matched_set.add(key10)
                else:
                    if not lock_hide_extras and not _is_roof_color_key(key10):
                        if _is_extra_conf_pass(key10):
                            extras_black.add(key10)
                            db_client.queue_extra_name(key10)
                new_keys_stable.append(key10)
                changed = True
        for k in keys_in_frame:
            if k not in recent_seen_keys:
                recent_seen_keys.add(k)
                new_keys_first_seen.append(k)

        _enforce_business_rules()
        if changed:
            rebuild_right_text()
            set_status(
                f"Match {len(matched_set)}/{len(expected_set)} | Extra {len(extras_black)}",
                "#2E7D32"
            )

        # best_frame_this_seq update
        car_now = inline_data or {}
        _update_best_frame_candidate(
            annotated_frame,
            count_items=len(non_no_car_items),
            vin_val=car_now.get("VinNo",""),
            lot_val=car_now.get("LotCodeCar",""),
            seq_val=car_now.get("SeqCar","")
        )

        # --- เช็ค ALL_OK ณ เฟรมปัจจุบัน (ไม่สน W/O)
        all_ok_in_this_frame = _all_ok_required_in_frame(set(keys_in_frame))

        if ALL_OK_AUTOSAVE and all_ok_in_this_frame and not persisted_this_cycle:
            snapshot = build_current_snapshot()
            _save_best_frame_all_ok_once(prefix="")
            # DB summary: ทำเฉพาะตอนจบรอบด้วย No_Car
            early_saved_all_green = True
            lock_hide_extras = True
            _clear_ng_buffer()

        # ---- บัฟเฟอร์ NG (ยังไม่ ALL_OK) ----
        if annotated_frame is not None:
            seq_txt = (inline_data or {}).get("SeqCar", "")
            vin_cur = (inline_data or {}).get("VinNo", "")
            lot_cur = (inline_data or {}).get("LotCodeCar", "")
            if not best_frame_locked_saved:
                if new_keys_stable or new_keys_first_seen:
                    new_keys_all = new_keys_stable if new_keys_stable else new_keys_first_seen
                    ng_keys = [k for k in new_keys_all if (k not in expected_set)]
                    ng_keys = [k for k in ng_keys if _is_extra_conf_pass(k)]
                    if ng_keys:
                        _remember_ng_frame(annotated_frame, seq_txt, vin_cur, lot_cur, ng_keys)
                        logger.info(f"NG buffered ({len(ng_keys)} keys) for VIN={vin_cur}")
                        flash_info("NG BUFFERED", 600, bg="#FFCC80")

        # realtime: อัปเดตค่าทางขวาทุกรอบที่มีผลตรวจ เพื่อให้ All_Percent ขึ้นทันที
        rebuild_right_text(force=True)

    # ===== Detect No_Car only =====
    has_no_car = any(_is_no_car_label(n) for (n, c) in (det_list or []))
    has_any_item = any((not _is_no_car_label(n)) for (n, c) in (det_list or []))
    if has_no_car and not has_any_item:
        _no_car_streak += 1
    else:
        _no_car_streak = 0

    # ===== ตอนเจอ No_Car แล้ว =====
    no_car_only_now = has_no_car and (not has_any_item)
    if not no_car_only_now:
        no_car_persist_done_this_streak = False
    if no_car_only_now:
        print(f"[NO_CAR] detected -> trigger persist vin={(inline_data or {}).get('VinNo','')} seq={(inline_data or {}).get('SeqCar','')}")
        if not no_car_persist_done_this_streak:
            # บันทึกครั้งแรกของช่วง "มีแต่ No_Car" เสมอ (ไม่ skip เพราะ persisted_this_cycle จาก ALL_OK/SEQ แล้ว)
            logger.info(
                f"Trigger persist on No_Car (vin={(inline_data or {}).get('VinNo','')}, seq={(inline_data or {}).get('SeqCar','')})"
            )
            snapshot = build_current_snapshot()
            sp = snapshot or {}
            print(
                f"[NO_CAR][SQL] snapshot keys={list(sp.keys())} "
                f"exp_pairs={len(sp.get('expected_pairs') or [])} "
                f"extras={len(sp.get('extras_black') or set())} "
                f"allpercent={len(sp.get('allpercent_by_key') or {})} "
                f"persisted_this_cycle(before)={persisted_this_cycle}",
                flush=True,
            )
            n_ins = 0
            try:
                n_ins = persist_cycle_results(snapshot, include_extras=True)
                if n_ins > 0:
                    set_corner_state("saving", "SAVING...")
                    set_status("Saved snapshot (No Car) → Waiting for new VIN", "#FB8C00")
            except Exception as e:
                logger.exception(f"Error persisting DB on No_Car: {e}")
                print(f"[NO_CAR][SQL] persist_cycle_results EXCEPTION: {e}", flush=True)
            no_car_persist_done_this_streak = True
            if n_ins > 0:
                persisted_this_cycle = True
        else:
            print(
                f"[NO_CAR][SQL] skip duplicate persist (already saved this no-car streak) "
                f"persisted_this_cycle={persisted_this_cycle}",
                flush=True,
            )

        # ปิดรอบปัจจุบัน แล้วกลับไปรอ VIN/SEQ ใหม่
        reset_cycle_state(keep_recent_seen=False, clear_right_text=True)
        set_waiting_for_new_vin(True)
        _no_car_streak = 0
        _reset_per_vin_counters()
        _clear_ng_buffer()
        _last_seen_non_no_car_ts = None
        lock_hide_extras = False
        _clear_post_nocar3()  # เคลียร์สถานะ post-NoCar สำหรับรอบใหม่

    _push_snapshot_history()
    root.after(12, ui_update)

# ========= VINSTART snapshot =========
def schedule_vin_change_snapshot():
    try:
        _save_seq_change_snapshot(
            globals().get("latest_vin"),
            globals().get("latest_lot"),
            globals().get("latest_seq"),
        )
    except Exception as e:
        logger.exception(f"schedule_vin_change_snapshot error: {e}")

# ========= Pre-change finalize (T-3s) + Post-NoCar+3s preferred =========
def set_waiting_for_new_vin(flag: bool):
    global waiting_for_new_vin
    waiting_for_new_vin = flag
    if flag:
        _detect_since.clear()
        set_corner_state("waiting", "WAITING\nVIN")
        set_status("Waiting for new VIN...", "#F9A825")
    else:
        set_corner_state("active", "ACTIVE")
        set_status("Ready", "#2E7D32")

def _all_ok_by_snapshot_wo_aware(snap) -> bool:
    if not snap:
        return False
    exp_pairs_snap = snap.get("expected_pairs", [])
    matched_snap   = snap.get("matched_set", set())
    if not exp_pairs_snap:
        return False
    req = set()
    for (_id9, _sel1, key10) in exp_pairs_snap:
        nm = (expected_name_ai.get(key10, "") or "")
        if "W/O" in nm.upper():
            continue
        req.add(key10)
    return req.issubset(matched_snap) and (len(snap.get("expected_set", set())) >= 1)

def _finalize_previous_cycle_by_preferred_snapshot(ts_change: float):
    """
    เมื่อ SEQ เปลี่ยน: ตรวจว่าเก็บ DB แล้วหรือยัง
    ถ้าเก็บแล้วจาก _save_seq_change_snapshot() ไม่ต้องทำซ้ำ
    """
    global persisted_this_cycle
    
    # ถ้าเก็บ DB แล้วจาก _save_seq_change_snapshot() ให้ข้ามไป
    if persisted_this_cycle:
        logger.info("DB already persisted from SEQ_CHANGE snapshot; skip finalize")
        return True
    
    snap = _find_snapshot_before(ts_change, fallback_last=True)
    if not snap or not snap.get("expected_pairs"):
        logger.info("No suitable snapshot for finalize-by-preferred; skip.")
        return False

    use_all_ok = _all_ok_by_snapshot_wo_aware(snap)
    
    # เก็บ DB (สำรอง กรณีที่ _save_seq_change_snapshot ลงคนละจุด)
    # DB summary: ทำเฉพาะตอนจบรอบด้วย No_Car
    return True

def _finalize_previous_cycle_all_ok_with_carryover_frame(prev_snap, ts_change):
    # เดิมคงไว้ (สำรอง)
    global carryover_locked_saved, last_snapshot_picture_path
    if not prev_snap:
        return False
    if not _all_ok_by_snapshot_wo_aware(prev_snap):
        return False
    saved_path = _save_carryover_all_ok_once(prefix="")
    if saved_path:
        last_snapshot_picture_path = saved_path
    # DB summary: ทำเฉพาะตอนจบรอบด้วย No_Car
    carryover_locked_saved = True
    return True

def _finalize_previous_cycle_by_prechange_snapshot(ts_change: float):
    # เดิมคงไว้ (สำรอง)
    snap = _find_snapshot_before(ts_change - 3.0, fallback_last=True)
    if not snap:
        logger.info("No pre-change snapshot found; skip finalize-by-prechange.")
        return False
    prev_car = snap.get("inline_data") or {}
    vin_prev = prev_car.get("VinNo", "")
    seq_prev = prev_car.get("SeqCar", "")
    if not snap.get("expected_pairs", []):
        logger.info(f"[PreChange] Skip: no spec rows (VIN={vin_prev}, SEQ={seq_prev})")
        return False
    ok_done = _finalize_previous_cycle_all_ok_with_carryover_frame(snap, ts_change)
    if not ok_done:
        logger.info(
            f"[PreChange] Not ALL_OK for VIN={vin_prev}, SEQ={seq_prev} -> will rely on No Car logic later."
        )
    return ok_done

def poll_inline_testers():
    """
    *** ปรับใหม่ ***
    - อ่าน VinNo ล่าสุดจาก TMT-GW-DIAS.dbo.InlineDetails (IdProcess=199, ORDER BY StartDate DESC)
    - แล้วใช้ VinNo ไปดึงข้อมูลรถจาก GatewayQC.dbo.Cars ผ่านฟังก์ชัน fetch_car_info_by_vin_from_gateway
    - inline_data จะอิงจากข้อมูลของ Cars เป็นหลัก:
        VinNo, BodyNoCar, LotCodeCar, IdModel, SeqCar
    - การขึ้นรอบใหม่: ถ้า Vin หรือ Seq เปลี่ยนจากค่าก่อนหน้า
    """
    global inline_data, previous_vin, previous_body, previous_seq
    global _round_start_time, _last_seen_non_no_car_ts, waiting_for_new_vin
    global early_saved_all_green, persisted_this_cycle, lock_hide_extras
    global best_frame_this_seq, best_frame_itemcount, best_frame_meta, best_frame_locked_saved
    global carryover_best_frame, carryover_best_count, carryover_best_meta, carryover_locked_saved
    global _prev_only_no_car, program_started

    try:
        # 1) อ่าน Vin ล่าสุดจาก InlineDetails (DIAS)
        latest_vin_from_inline = fetch_latest_vin_from_inline_details()

        if not latest_vin_from_inline:
            # ไม่มี Vin ใน InlineDetails
            if waiting_for_new_vin:
                set_status("Waiting for new VIN (InlineDetails empty)...", "#F9A825")
            else:
                seq_text = "SeqCar: -"
                _fit_seq_font(seq_text)
                seq_label.config(text=seq_text)
                lot_model_label.config(text="Lot: - Model: -")
                set_status("Waiting for new VIN (InlineDetails empty)...", "#F9A825")
        else:
            # 2) ใช้ Vin นี้ไปดึงข้อมูลจาก Cars(GatewayQC)
            car_info = fetch_car_info_by_vin_from_gateway(latest_vin_from_inline)
            if not car_info:
                # หา Vin นี้ใน Cars ไม่เจอ
                if waiting_for_new_vin:
                    set_status(f"Vin={latest_vin_from_inline} not found in Cars(GatewayQC)", "#E53935")
                else:
                    set_status(f"Vin={latest_vin_from_inline} not found in Cars(GatewayQC)", "#E53935")
            else:
                # map ค่าจาก Cars -> inline_data
                merged = {
                    "VinNo":     car_info.get("VinNoCar"),
                    "BodyNoCar": car_info.get("BodyNoCar"),
                    "LotCodeCar":car_info.get("LotCodeCar"),
                    "IdModel":   car_info.get("IdModel"),
                    "SeqCar":    car_info.get("SeqCar"),
                }
                inline_data = merged

                latest_vin   = merged.get("VinNo")
                latest_body  = merged.get("BodyNoCar")
                latest_seq   = merged.get("SeqCar")
                latest_lot   = merged.get("LotCodeCar")
                latest_model = merged.get("IdModel")

                seq_text = f"SeqCar: {latest_seq if latest_seq is not None else '-'}"
                _fit_seq_font(seq_text)
                seq_label.config(text=seq_text)
                lot_txt   = f"{latest_lot if latest_lot is not None else '-'}"
                model_txt = f"{latest_model if latest_model is not None else '-'}"
                lot_model_label.config(text=f"Lot: {lot_txt} Model: {model_txt}")

                # ตรวจ Vin/Seq เปลี่ยน → ขึ้นรอบใหม่
                if latest_vin and latest_seq and (
                    latest_vin != previous_vin or latest_seq != previous_seq
                ):
                    seq_changed_really = (previous_seq is None or latest_seq != previous_seq)
                    ts_change = time.time()
                    is_bootstrap_first_cycle = (previous_vin is None and previous_seq is None)
                    print(f"✅ New cycle: VIN={latest_vin} SEQ={latest_seq}")
                    logger.info(f"New cycle from InlineDetails+Cars: VIN={latest_vin} Seq {latest_seq}")

                    # กรณีเปิดโปรแกรมครั้งแรก: ให้เริ่มนับเป็นรอบแรกทันที
                    # และรอ insert ตอนเจอ No_Car (ไม่บันทึกก่อนเวลา)
                    if not is_bootstrap_first_cycle:
                        # finalize รอบเก่าด้วย snapshot ที่เหมาะสม
                        try:
                            _finalize_previous_cycle_by_preferred_snapshot(ts_change)
                        except Exception as e:
                            logger.exception(f"Finalize-by-preferred error: {e}")
                            try:
                                _finalize_previous_cycle_by_prechange_snapshot(ts_change)
                            except Exception as e2:
                                logger.exception(f"Fallback finalize-by-prechange error: {e2}")
                    else:
                        logger.info("Bootstrap first cycle: start tracking immediately and wait No_Car to persist")

                    # Force rebuild text เมื่อ SEQ เปลี่ยน
                    rebuild_right_text(force=True)

                    # ย้ายไปรอบใหม่แล้ว
                    previous_vin  = latest_vin
                    previous_body = latest_body
                    previous_seq  = latest_seq
                    program_started = False  # ปิด flag เพราะเก็บภาพแล้ว

                    early_saved_all_green = False
                    # ถ้ามีการ persist แล้วจาก _save_seq_change_snapshot() ให้คงค่าไว้
                    if not persisted_this_cycle:
                        persisted_this_cycle = False
                    lock_hide_extras      = False

                    vin_new_safe = _sanitize_for_filename(latest_vin or "")
                    if vin_new_safe:
                        ok_all_image_saved_by_vin[vin_new_safe] = False

                    _reset_best_frame_for_new_seq(latest_vin, latest_lot, latest_seq)
                    _reset_carryover_best()
                    _clear_post_nocar3()          # เคลียร์ snapshot post-NoCar ของรอบใหม่
                    _prev_only_no_car = True      # เริ่มรอบใหม่ให้ถือว่าเริ่มจาก only no_car

                    set_waiting_for_new_vin(False)
                    reset_cycle_state(keep_recent_seen=False, clear_right_text=True)
                    snapshot_history.clear()
                    _clear_ng_buffer()
                    preload_expected_for_current_inline(do_instant_compare=True)
                    adopt_carryover_into_new_cycle()
                    apply_extra_threshold_filter()
                    set_status(f"VIN={latest_vin} SEQ={latest_seq} loaded from Cars(GatewayQC). Ready.", "#2E7D32")

                    _reset_per_vin_counters()
                    _round_start_time         = time.time()
                    _last_seen_non_no_car_ts  = None
                    if seq_changed_really:
                        schedule_vin_change_snapshot()
                else:
                    if waiting_for_new_vin:
                        set_status("Waiting for new VIN...", "#F9A825")

    except Exception as e:
        logger.exception(f"poll_inline_testers error: {e}")
    finally:
        root.after(REFRESH_MS, poll_inline_testers)

# ========= Start/Stop camera logic =========
def stop_camera_threads():
    global cam_thread, infer_thread, _infer_session_id
    cam_stop_flag.set()
    _infer_session_id += 1
    for th in (cam_thread, infer_thread):
        try:
            if th is not None:
                th.join(timeout=1.5)
        except Exception:
            pass
    cam_thread = None
    infer_thread = None
    first_dims_ready.clear()

def start_camera_threads(cam_index: int, backend_name: str):
    global cam_thread, infer_thread, current_cam_index, current_cam_backend, _infer_session_id
    stop_camera_threads()
    cam_stop_flag.clear()
    session = _infer_session_id
    current_cam_index, current_cam_backend = cam_index, backend_name
    prefer = (CAMERA_PREFER_BACKEND or "").upper().strip()
    backend_flag = (
        cv2.CAP_DSHOW if prefer == "DSHOW" else
        cv2.CAP_MSMF if prefer == "MSMF" else
        cv2.CAP_MSMF if backend_name == "MSMF" else
        cv2.CAP_DSHOW if backend_name == "DSHOW" else
        cv2.CAP_ANY
    )
    cam_thread = threading.Thread(
        target=camera_worker,
        kwargs={"cam_index": cam_index, "backend_flag": backend_flag, "infer_session": session},
        daemon=True
    )
    cam_thread.start()
    # เริ่ม inference เมื่อโมเดลพร้อม (ไม่บล็อก startup/UI)
    if model is None:
        ensure_model_async()
        infer_thread = None
        set_status("Camera started (model loading...)", "#1E88E5")
    else:
        infer_thread = threading.Thread(
            target=inference_worker,
            args=(model, names, session),
            daemon=True
        )
        infer_thread.start()
    set_status(f"Camera started @ index {cam_index} [prefer {prefer or backend_name}]", "#1E88E5")
    flash_info("CAM START", 800, bg="#90CAF9")

def on_start_clicked():
    sel = camera_combo.get()
    if not sel or "<no camera" in sel:
        messagebox.showwarning("Camera", "กรุณากด RESCAN และเลือกกล้องก่อนเริ่ม")
        return
    try:
        idx = int(sel.split()[1])  # "Camera {i} [X]"
        backend_name = sel.split('[')[1].split(']')[0]
    except Exception:
        messagebox.showerror("Camera", f"ไม่สามารถอ่านค่าเลือกจาก '{sel}'")
        return
    start_camera_threads(idx, backend_name)

# ========= Hotkeys =========
root.bind("<Key-r>", lambda e: do_rescan())
root.bind("<Key-s>", lambda e: on_start_clicked())

def _force_save(_=None):
    global _no_car_streak, _last_seen_non_no_car_ts
    global persisted_this_cycle, lock_hide_extras, early_saved_all_green
    global carryover_locked_saved

    if waiting_for_new_vin:
        flash_info("NO VIN", 1000, bg="#FFCDD2")
        return
    if persisted_this_cycle:
        flash_info("ALREADY SAVED", 800, bg="#C5E1A5")
        return

    logger.info("Trigger persist (FORCE F9)")

    snapshot = build_current_snapshot()

    keys_now = set(recent_seen_keys)
    if _all_ok_required_in_frame(keys_now):
        _save_best_frame_all_ok_once(prefix="")
        n_ins = persist_cycle_results(snapshot, include_extras=False)
    else:
        if not best_frame_locked_saved and not carryover_locked_saved:
            _ = _save_buffered_ng_if_any(snapshot, include_extras=True)
        n_ins = persist_cycle_results(snapshot, include_extras=True)

    if n_ins > 0:
        set_corner_state("saving", "SAVING...")
        set_status("Saved snapshot (FORCE) → Waiting for new VIN", "#FB8C00")
        persisted_this_cycle = True

    reset_cycle_state(keep_recent_seen=False, clear_right_text=True)
    set_waiting_for_new_vin(True)
    _no_car_streak = 0
    _reset_per_vin_counters()
    _clear_ng_buffer()
    _last_seen_non_no_car_ts = None
    early_saved_all_green = False
    lock_hide_extras = False
    _clear_post_nocar3()

root.bind("<F9>", _force_save)

def on_close():
    stop_camera_threads()
    root.destroy()

# ========= Window / Resize helpers =========
_resize_after_id = None

def configure_display_from_window():
    """
    ปรับให้ภาพจากกล้องกินพื้นที่ฝั่งซ้าย 'เต็มจอ' ให้มากที่สุด:
    - ใช้ขนาดหน้าต่างจริง - RIGHT_PANEL_W โดยไม่เผื่อ margin เพิ่ม
    - letterbox จะรักษาอัตราส่วนภาพของกล้องไว้ (ไม่ครอป)
    """
    global DISPLAY_W, DISPLAY_H
    window_w = max(400, root.winfo_width())
    window_h = max(300, root.winfo_height())

    # พื้นที่ฝั่งซ้าย = ทั้งหน้าต่าง - ความกว้าง panel ขวา
    avail_w = max(200, window_w - RIGHT_PANEL_W)
    avail_h = max(200, window_h)

    DISPLAY_W = int(avail_w)
    DISPLAY_H = int(avail_h)

    left_frame.config(width=DISPLAY_W, height=DISPLAY_H)
    left_frame.grid_propagate(False)
    if DISPLAY_W and DISPLAY_H:
        video_label.config(width=DISPLAY_W, height=DISPLAY_H)

    right_frame.config(width=RIGHT_PANEL_W)
    right_frame.grid_propagate(False)
    root.grid_columnconfigure(1, minsize=RIGHT_PANEL_W)

def _debounced_resize(_evt):
    global _resize_after_id
    if _resize_after_id is not None:
        root.after_cancel(_resize_after_id)
    _resize_after_id = root.after(120, configure_display_from_window)

root.bind("<Configure>", _debounced_resize)
root.after_idle(configure_display_from_window)

# ========= Inference worker =========

# จานสีสำหรับกรอบ + ตัวหนังสือ (BGR)
CLASS_COLOR_PALETTE = [
    (0, 255, 0),
    (0, 255, 255),
    (255, 0, 255),
    (255, 255, 0),
    (0, 128, 255),
    (255, 128, 0),
    (128, 255, 0),
    (255, 0, 128),
    (0, 200, 200),
    (200, 200, 0),
]

def _get_color_for_class(cls_id: int) -> tuple:
    if cls_id is None:
        return (0, 255, 0)
    return CLASS_COLOR_PALETTE[int(cls_id) % len(CLASS_COLOR_PALETTE)]

def camera_worker(cam_index=0, backend_flag=cv2.CAP_MSMF, infer_session=0):
    global latest_frame, _cam_w, _cam_h, last_frame_ts, current_cam_backend, _infer_session_id
    cap = None
    first_dims_ready.clear()
    while not cam_stop_flag.is_set() and infer_session == _infer_session_id:
        if cap is None:
            cap, used_backend, (w, h) = open_camera_best(cam_index, backend_flag)
            if cap is None:
                time.sleep(0.4)
                continue
            current_cam_backend = (
                "MSMF" if used_backend == cv2.CAP_MSMF else
                "DSHOW" if used_backend == cv2.CAP_DSHOW else
                "ANY"
            )
        try:
            ok, frame = cap.read()
        except cv2.error as e:
            logger.warning(f"[CAM] read crash in worker idx={cam_index}: {e}")
            ok, frame = False, None
        if not ok or frame is None:
            try:
                cap.release()
            except Exception:
                pass
            cap = None
            time.sleep(0.1)
            continue
        with latest_frame_lock:
            latest_frame = frame
            last_frame_ts = time.time()
        if _cam_w == 0 or _cam_h == 0:
            h0, w0 = frame.shape[:2]
            _cam_w, _cam_h = w0, h0
            first_dims_ready.set()
    try:
        if cap is not None:
            cap.release()
    except Exception:
        pass

def inference_worker(model, names, infer_session=0):
    global infer_fps, USE_HALF, _infer_session_id
    times = deque(maxlen=30)
    dummy = np.zeros((480, 640, 3), dtype=np.uint8)
    _fix_yolo26_conv2d_groups(model)
    try:
        with torch.no_grad():
            with _yolo_predict_lock:
                _ = model(dummy, conf=CONF_THRES, device=DEVICE_IDX, half=USE_HALF, verbose=False)
        _fix_yolo26_conv2d_groups(model)
    except Exception as e:
        logger.warning(f"Warmup failed with half={USE_HALF}, retrying with half=False; err={e}")
        USE_HALF = False
        with torch.no_grad():
            with _yolo_predict_lock:
                _ = model(dummy, conf=CONF_THRES, device=DEVICE_IDX, half=False, verbose=False)
        _fix_yolo26_conv2d_groups(model)
    print(f">>> Inference running on: {'GPU' if use_cuda else 'CPU'} (half={USE_HALF})")
    logger.info(f"Inference on {'GPU' if use_cuda else 'CPU'} (half={USE_HALF})")

    while not cam_stop_flag.is_set() and infer_session == _infer_session_id:
        start = time.time()
        with latest_frame_lock:
            frame_full = None if latest_frame is None else latest_frame.copy()
        if frame_full is None:
            time.sleep(0.005)
            continue

        h0, w0 = frame_full.shape[:2]

        # เวลาเปลี่ยน (กะ/รอบ) -> เคลียร์ค่าการสะสม label ทั้งหมด
        try:
            _maybe_shift_time_reset()
        except Exception as e:
            logger.warning(f"[SHIFT_RESET] check failed: {e}")

        # ภาพย่อสำหรับ YOLO เพื่อลดโหลด
        if INFER_DOWNSCALE != 1.0:
            infer_frame = cv2.resize(
                frame_full,
                (int(w0 * INFER_DOWNSCALE), int(h0 * INFER_DOWNSCALE),
                ),
                interpolation=cv2.INTER_AREA
            )
            scale_back = 1.0 / INFER_DOWNSCALE
        else:
            infer_frame = frame_full
            scale_back = 1.0

        try:
            with torch.no_grad():
                with _yolo_predict_lock:
                    results = model(
                        infer_frame,
                        conf=CONF_THRES,
                        device=DEVICE_IDX,
                        half=USE_HALF,
                        imgsz=960,
                        verbose=False
                    )

        except Exception as e:
            logger.exception(f"YOLO infer error: {e}")
            time.sleep(0.02)
            continue

        res0 = results[0]

        # ใช้ภาพเต็มจากกล้องสำหรับวาดกรอบ + แสดงผล
        annotated = frame_full.copy()

        det_list = []
        try:
            if getattr(res0, "boxes", None) is not None and \
               getattr(res0.boxes, "cls", None) is not None and \
               len(res0.boxes.cls) > 0:

                cls_ids = res0.boxes.cls.detach().float().cpu().numpy().astype(int)
                confs   = res0.boxes.conf.detach().float().cpu().numpy().astype(float)
                xyxy    = res0.boxes.xyxy.detach().cpu().numpy().astype(float)

                for i, c in enumerate(cls_ids):
                    raw = names[c] if (c in names) else (names.get(c, "") if hasattr(names,"get") else "")
                    name = str(raw or "")
                    if _is_no_car_label(name):
                        display_name = "No_Car"
                    else:
                        display_name = name

                    if display_name != "No_Car" and _contains_blacktape_text(display_name):
                        continue
                    if display_name != "No_Car" and _should_ignore_readable_label(display_name):
                        continue

                    conf = float(confs[i]) if i < len(confs) else None
                    det_list.append((display_name, conf))

                    # วาดกรอบ + text (สีเดียวกันต่อ item)
                    x1, y1, x2, y2 = xyxy[i] * scale_back
                    x1 = int(max(0, min(w0 - 1, x1)))
                    y1 = int(max(0, min(h0 - 1, y1)))
                    x2 = int(max(0, min(w0 - 1, x2)))
                    y2 = int(max(0, min(h0 - 1, y2)))

                    # สีตามผล match: matched=เขียว, ไม่ matched=แดง
                    _id9, _sel1, key10 = _parse_ai_label(display_name)
                    color = (0, 255, 0) if (key10 and key10 in matched_set) else (0, 0, 255)
                    # วาดกรอบทุก item (รวม No_Car) และแสดง label ทุกกรณี
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), color, DET_BOX_THICKNESS)

                    label = display_name
                    if conf is not None:
                        label = f"{display_name} {int(conf*100):02d}%"

                    # พื้นหลัง label เล็ก ๆ (ใช้สีเดียวกับกรอบแต่จางลงหน่อย)
                    (tw, th), _ = cv2.getTextSize(
                        label,
                        cv2.FONT_HERSHEY_SIMPLEX,
                        DET_LABEL_FONT_SCALE,
                        DET_LABEL_THICKNESS
                    )
                    y_text = max(0, y1 - 2)
                    cv2.rectangle(
                        annotated,
                        (x1, y_text - th - 4),
                        (x1 + tw + 4, y_text),
                        (color[0]//3, color[1]//3, color[2]//3),
                        -1
                    )
                    cv2.putText(
                        annotated,
                        label,
                        (x1 + 2, y_text - 2),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        DET_LABEL_FONT_SCALE,
                        color,
                        DET_LABEL_THICKNESS,
                        cv2.LINE_AA
                    )
        except Exception as e:
            logger.warning(f"parse boxes / draw failed: {e}")

        try:
            if result_queue.full():
                _ = result_queue.get_nowait()
            result_queue.put_nowait((annotated, det_list))
        except queue.Full:
            pass

        dt = time.time() - start
        times.append(dt)
        if times:
            infer_fps = 1.0 / (sum(times) / len(times))

        remain = (1.0 / TARGET_FPS_INFER) - dt
        if remain > 0:
            time.sleep(remain)

# ========= Watchdog =========
def _watchdog():
    if time.time() - last_frame_ts > 3.0 and not cam_stop_flag.is_set() and current_cam_index is not None:
        try:
            start_camera_threads(current_cam_index, current_cam_backend or "MSMF")
            set_status("Camera watchdog: auto-restart", "#D84315")
            flash_info("CAM RESTART", 1200, bg="#FFCC80")
        except Exception:
            set_corner_state("error", "CAM\nERROR")
            logger.exception("Watchdog restart failed")
    root.after(1000, _watchdog)

# ========= Hooks & timers =========
start_btn.config(command=on_start_clicked)
rescan_btn.config(command=do_rescan)
root.protocol("WM_DELETE_WINDOW", on_close)
root.after(0, ui_update)
root.after(200, poll_inline_testers)
root.after(2000, _watchdog)
# Kick camera scan after Tkinter event loop starts to avoid blocking window render.
root.after(100, do_rescan_async)
# โหลดโมเดลแบบไม่บล็อกหน้าต่าง
root.after(150, ensure_model_async)
ensure_save_dir_writable()

# ========= Main Loop =========
if __name__ == "__main__":
    try:
        root.mainloop()
    except Exception as e:
        print("Fatal error:", e)
        logger.exception("Fatal error")
        traceback.print_exc()
