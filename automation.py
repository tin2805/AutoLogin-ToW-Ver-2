import os
import time
import subprocess
import ctypes
import asyncio
import re
import difflib
import threading
import concurrent.futures
import numpy as np
import cv2
from PIL import ImageGrab, Image
import pyautogui
import pyperclip
import win32gui
import win32process
import win32con
import win32api

ACTION_LOCK = threading.Lock()

FAST_MODE = False
_time_module = time
_native_sleep = time.sleep

_CURRENT_STOP_EVENT = None
_CURRENT_PAUSE_EVENT = None
_CURRENT_SKIP_STEP_EVENT = None
_CURRENT_LOGGER = print

def set_automation_events(stop_event=None, pause_event=None, skip_step_event=None, logger=None):
    global _CURRENT_STOP_EVENT, _CURRENT_PAUSE_EVENT, _CURRENT_SKIP_STEP_EVENT, _CURRENT_LOGGER
    _CURRENT_STOP_EVENT = stop_event
    _CURRENT_PAUSE_EVENT = pause_event
    _CURRENT_SKIP_STEP_EVENT = skip_step_event
    if logger is not None:
        _CURRENT_LOGGER = logger

def check_flow_control(email="", step_desc=""):
    """
    Kiểm tra tín hiệu phím tắt & điều khiển:
    - stop_event (Ctrl+X): trả về 'stop'
    - pause_event (Ctrl+P): nếu bị tạm dừng, đứng chờ cho đến khi Ctrl+C (resume) hoặc Ctrl+X (stop) hoặc Ctrl+S (skip)
    - skip_step_event (Ctrl+S): xóa cờ và trả về 'skip' để bỏ qua bước hiện tại
    - bình thường: trả về 'ok'
    """
    if _CURRENT_STOP_EVENT and _CURRENT_STOP_EVENT.is_set():
        return 'stop'
    if _CURRENT_PAUSE_EVENT and not _CURRENT_PAUSE_EVENT.is_set():
        while not _CURRENT_PAUSE_EVENT.is_set():
            if _CURRENT_STOP_EVENT and _CURRENT_STOP_EVENT.is_set():
                return 'stop'
            if _CURRENT_SKIP_STEP_EVENT and _CURRENT_SKIP_STEP_EVENT.is_set():
                _CURRENT_SKIP_STEP_EVENT.clear()
                if email and _CURRENT_LOGGER:
                    _CURRENT_LOGGER(f'[{email}] ⏩ [HOTKEY Ctrl+S] Đã bỏ qua bước: {step_desc}!')
                return 'skip'
            _native_sleep(0.05)
    if _CURRENT_SKIP_STEP_EVENT and _CURRENT_SKIP_STEP_EVENT.is_set():
        _CURRENT_SKIP_STEP_EVENT.clear()
        if email and _CURRENT_LOGGER:
            _CURRENT_LOGGER(f'[{email}] ⏩ [HOTKEY Ctrl+S] Đã bỏ qua bước: {step_desc}!')
        return 'skip'
    return 'ok'

def interruptible_sleep(seconds, allow_fast_mode_skip=False):
    if seconds <= 0:
        return
    if allow_fast_mode_skip and FAST_MODE:
        return
    end_time = _time_module.time() + seconds
    while _time_module.time() < end_time:
        if _CURRENT_STOP_EVENT and _CURRENT_STOP_EVENT.is_set():
            break
        if _CURRENT_SKIP_STEP_EVENT and _CURRENT_SKIP_STEP_EVENT.is_set():
            break
        if _CURRENT_PAUSE_EVENT and not _CURRENT_PAUSE_EVENT.is_set():
            while not _CURRENT_PAUSE_EVENT.is_set():
                if _CURRENT_STOP_EVENT and _CURRENT_STOP_EVENT.is_set():
                    return
                if _CURRENT_SKIP_STEP_EVENT and _CURRENT_SKIP_STEP_EVENT.is_set():
                    return
                _native_sleep(0.05)
        rem = end_time - _time_module.time()
        _native_sleep(min(0.05, max(0.005, rem)))

_real_sleep = interruptible_sleep

class _TimeFacade:
    def __getattr__(self, name):
        return getattr(_time_module, name)

    @staticmethod
    def sleep(seconds):
        interruptible_sleep(seconds, allow_fast_mode_skip=True)

time = _TimeFacade()


def set_fast_mode(enabled):
    global FAST_MODE
    FAST_MODE = bool(enabled)

try:
    import winocr
except Exception:
    winocr = None

# Ensure DPI awareness for pixel-perfect coordinates
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), 'templates')

def load_template(name):
    path = os.path.join(TEMPLATE_DIR, name)
    if not os.path.exists(path):
        raise FileNotFoundError(f'Template not found: {path}')
    return cv2.imread(path)

# Pre-load templates
TEMPLATES = {
    'notice_close': load_template('btn_notice_close.png'),
    'account': load_template('btn_account.png'),
    'icon_email': load_template('icon_email.png'),
    'icon_password': load_template('icon_password.png'),
    'btn_login': load_template('btn_login.png'),
    'login_form': load_template('test_login_modal.png'),
    'start_adv_title': load_template('btn_start_adv_title.png'),
    'start_adv_char': load_template('btn_start_adv_char.png'),
    'loading_dear_adv': load_template('loading_dear_adv.png'),
    'loading_entering': load_template('loading_entering.png'),
    'crop_title_bottom': load_template('crop_title_bottom.png'),
    'server_header': load_template('server_header.png'),
    'server_tab_role': load_template('server_tab_role.png'),
    'crop_real_start_adv': load_template('crop_real_start_adv.png'),
    'final_start_adv': load_template('image-2.png'),
}

def find_window_by_pid(target_pid):
    result = []
    def enum_cb(hwnd, extra):
        if win32gui.IsWindowVisible(hwnd):
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid == target_pid:
                title = win32gui.GetWindowText(hwnd)
                if title and 'ToW' in title:
                    result.append(hwnd)
        return True
    win32gui.EnumWindows(enum_cb, None)
    return result[0] if result else None

def find_tow_windows():
    result = []
    def enum_cb(hwnd, extra):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title and ('ToW' in title or 'Tales of Wind' in title):
                result.append(hwnd)
        return True
    win32gui.EnumWindows(enum_cb, None)
    return result

def activate_window(hwnd):
    if not hwnd or not win32gui.IsWindow(hwnd):
        return
    try:
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        else:
            win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
            
        win32gui.BringWindowToTop(hwnd)
        win32gui.SetWindowPos(
            hwnd, win32con.HWND_TOP, 0, 0, 0, 0,
            win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW
        )
        
        fore_hwnd = win32gui.GetForegroundWindow()
        if fore_hwnd != hwnd:
            cur_thread = win32api.GetCurrentThreadId()
            fore_thread, _ = win32process.GetWindowThreadProcessId(fore_hwnd)
            if cur_thread != fore_thread:
                try:
                    win32process.AttachThreadInput(cur_thread, fore_thread, True)
                    win32gui.SetForegroundWindow(hwnd)
                    win32gui.BringWindowToTop(hwnd)
                    win32process.AttachThreadInput(cur_thread, fore_thread, False)
                except Exception:
                    win32gui.SetForegroundWindow(hwnd)
            else:
                win32gui.SetForegroundWindow(hwnd)
                win32gui.BringWindowToTop(hwnd)
        # Foreground activation is an OS synchronization point, even in Fast Mode.
        _real_sleep(0.2)
    except Exception:
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass

def capture_window(hwnd):
    rect = win32gui.GetWindowRect(hwnd)
    x1, y1, x2, y2 = rect
    w = x2 - x1
    h = y2 - y1
    if w <= 0 or h <= 0:
        return None, (0, 0, 0, 0)
    img = ImageGrab.grab(bbox=(x1, y1, x2, y2))
    img_np = np.array(img)
    img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
    return img_bgr, (x1, y1, w, h)

def locate_template_in_window(hwnd, template_key, threshold=0.72):
    if not hwnd or not win32gui.IsWindow(hwnd):
        return None
    with ACTION_LOCK:
        activate_window(hwnd)
        img_bgr, (wx, wy, ww, wh) = capture_window(hwnd)
    if img_bgr is None:
        return None
    tpl = TEMPLATES[template_key]
    res = cv2.matchTemplate(img_bgr, tpl, cv2.TM_CCOEFF_NORMED)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
    if max_val >= threshold:
        th, tw = tpl.shape[:2]
        cx = wx + max_loc[0] + tw // 2
        cy = wy + max_loc[1] + th // 2
        return (cx, cy, max_val)
    return None

def capture_final_start_button(hwnd, threshold=0.65):
    """Chụp một frame ổn định và tìm nút Start Adventure cuối trên frame đó."""
    if not hwnd or not win32gui.IsWindow(hwnd):
        return None
    with ACTION_LOCK:
        activate_window(hwnd)
        img_bgr, (wx, wy, ww, wh) = capture_window(hwnd)
    if img_bgr is None:
        return None

    # Mẫu chuẩn cho bước cuối: image-2.png (313x90).
    tpl = TEMPLATES['final_start_adv']
    if tpl.shape[0] > img_bgr.shape[0] or tpl.shape[1] > img_bgr.shape[1]:
        return None
    result = cv2.matchTemplate(img_bgr, tpl, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    if max_val >= threshold:
        th, tw = tpl.shape[:2]
        return (wx + max_loc[0] + tw // 2, wy + max_loc[1] + th // 2, max_val)
    return None

def click_coords(x, y, delay=0.2, hwnd=None, extra_delay=0.0, force_real_delay=False):
    with ACTION_LOCK:
        if hwnd and win32gui.IsWindow(hwnd):
            activate_window(hwnd)
        target = (int(round(x)), int(round(y)))
        # Dùng tọa độ màn hình Windows trực tiếp để khớp với ImageGrab/GetWindowRect.
        win32api.SetCursorPos(target)
        cursor_pos = win32api.GetCursorPos()
        if cursor_pos != target:
            _real_sleep(0.05)
            win32api.SetCursorPos(target)
            cursor_pos = win32api.GetCursorPos()
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    total_delay = delay + (0.5 if extra_delay > 0 else 0.0)
    if force_real_delay:
        _real_sleep(total_delay)
    else:
        time.sleep(total_delay)

def type_via_clipboard(text, delay=0.2, hwnd=None, extra_delay=0.0):
    with ACTION_LOCK:
        if hwnd and win32gui.IsWindow(hwnd):
            activate_window(hwnd)
        pyperclip.copy(text)
        _real_sleep(0.05)
        pyautogui.hotkey('ctrl', 'a')
        _real_sleep(0.05)
        pyautogui.press('backspace')
        _real_sleep(0.05)
        pyautogui.hotkey('ctrl', 'v')
    time.sleep(delay + (0.3 if extra_delay > 0 else 0.0))

def tile_window(hwnd, index, total=4):
    screen_w, screen_h = pyautogui.size()
    avail_h = screen_h - 40
    cols = 2 if total <= 4 else 3
    rows = (total + cols - 1) // cols
    w = screen_w // cols
    h = avail_h // rows
    c = index % cols
    r = index // cols
    x = c * w
    y = r * h
    try:
        with ACTION_LOCK:
            win32gui.MoveWindow(hwnd, x, y, w, h, True)
    except Exception:
        pass

class StepTimeoutException(Exception):
    """Ném ra khi không tìm thấy bước tiếp theo trong vòng 30s do game bị treo hoặc mất phản hồi."""
    pass

class CloneNotFoundException(Exception):
    """Ném ra khi không tìm thấy đúng tên clone trên màn hình chọn nhân vật."""
    def __init__(self, message, proc=None, pid=None, hwnd=None):
        super().__init__(message)
        self.proc = proc
        self.pid = pid
        self.hwnd = hwnd

def kill_game_process(proc=None, pid=None, hwnd=None):
    """Đóng sạch tiến trình game ToW khi bị treo hoặc cần khởi động lại."""
    owner_pid = None
    if hwnd and win32gui.IsWindow(hwnd):
        try:
            _, owner_pid = win32process.GetWindowThreadProcessId(hwnd)
        except Exception:
            pass

    try:
        if hwnd and win32gui.IsWindow(hwnd):
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            _real_sleep(0.3)
    except Exception:
        pass
        
    try:
        if proc:
            proc.kill()
    except Exception:
        pass
        
    process_ids = []
    for process_id in (owner_pid, pid):
        if process_id and process_id not in process_ids:
            process_ids.append(process_id)

    for process_id in process_ids:
        try:
            subprocess.run(
                ['taskkill', '/F', '/T', '/PID', str(process_id)],
                capture_output=True,
                check=False,
            )
        except Exception:
            pass

    deadline = time.time() + 3.0
    while hwnd and win32gui.IsWindow(hwnd) and time.time() < deadline:
        _real_sleep(0.2)

    # Một số phiên bản game không xử lý WM_CLOSE kịp thời; xác nhận lần cuối
    # và cưỡng chế theo PID đã lấy từ chính HWND nếu cửa sổ vẫn còn.
    if hwnd and win32gui.IsWindow(hwnd) and owner_pid:
        try:
            subprocess.run(
                ['taskkill', '/F', '/T', '/PID', str(owner_pid)],
                capture_output=True,
                check=False,
            )
        except Exception:
            pass
        deadline = time.time() + 2.0
        while win32gui.IsWindow(hwnd) and time.time() < deadline:
            _real_sleep(0.2)

def wait_for_next_step(hwnd, email, logger, stop_event, step_name, check_func, timeout=30.0):
    """
    Tìm đối tượng của bước tiếp theo trong vòng timeout (30s).
    Nếu sau 30s tìm kiếm mà KHÔNG TÌM THẤY BƯỚC TIẾP THEO -> Ném StepTimeoutException để khởi động lại game.
    Hỗ trợ phím tắt Ctrl+S (bỏ qua bước) và Ctrl+P/Ctrl+C (tạm dừng/tiếp tục).
    """
    logger(f'[{email}] 🔍 Đang tìm bước tiếp theo: [{step_name}] (tối đa {timeout:.0f}s)...')
    start_time = time.time()
    while time.time() - start_time < timeout:
        state = check_flow_control(email, step_name)
        if state == 'stop':
            return None
        if state == 'skip':
            return ('skipped', None)
        res = check_func()
        if res:
            elapsed = time.time() - start_time
            logger(f'[{email}] 🎯 Đã thấy bước tiếp theo [{step_name}] sau {elapsed:.1f}s!')
            return res
        time.sleep(0.8)
        
    raise StepTimeoutException(f"Không tìm thấy bước tiếp theo [{step_name}] sau {timeout:.0f}s")

def wait_for_loading_done(hwnd, email, logger, stop_event=None, timeout=180.0, extra_delay=0.0, require_loading=False):
    """
    Theo dõi màn hình load sau khi bấm Start Adventure:
    - Khi game đang ở màn hình loading: ĐÂY LÀ BƯỚC HIỆN TẠI ĐANG DIỄN RA (nạp tài nguyên bản đồ).
      Tool giữ nguyên trạng thái chờ nạp tài nguyên cho đến khi nạp xong (KHÔNG ngắt ở 30s).
    - Đợi cho đến khi màn hình loading hoàn toàn biến mất (vào hẳn thế giới game).
    """
    logger(f'[{email}] ⏳ Đang đợi màn hình load nạp tài nguyên vào game...')
    start_time = time.time()
    saw_loading = False
    consecutive_done = 0

    time.sleep(2.0 + extra_delay)

    while time.time() - start_time < timeout:
        state = check_flow_control(email, "chờ nạp bản đồ")
        if state == 'stop':
            return False
        if state == 'skip':
            return True

        is_loading = (
            locate_template_in_window(hwnd, 'loading_entering', threshold=0.65) or
            locate_template_in_window(hwnd, 'loading_dear_adv', threshold=0.65)
        )

        if is_loading:
            if not saw_loading:
                saw_loading = True
                logger(f'[{email}] 🔄 Màn hình Loading đang tải dữ liệu bản đồ... Vui lòng chờ...')
            consecutive_done = 0
        else:
            if saw_loading:
                consecutive_done += 1
                if consecutive_done >= 2:
                    elapsed = int(time.time() - start_time)
                    logger(f'[{email}] 🌟 Màn hình load đã hoàn tất sau {elapsed}s! Đã vào thế giới game.')
                    time.sleep(1.0 + extra_delay)
                    return True
            elif not require_loading:
                match_start = (
                    locate_template_in_window(hwnd, 'start_adv_title', threshold=0.68) or
                    locate_template_in_window(hwnd, 'start_adv_char', threshold=0.68)
                )
                if match_start and (time.time() - start_time > (4.0 + extra_delay)):
                    logger(f'[{email}] ⚠️ Nút Start Adventure vẫn còn, click lại...')
                    click_coords(match_start[0], match_start[1], delay=1.5, hwnd=hwnd, extra_delay=extra_delay)
                elif not match_start and (time.time() - start_time >= (5.0 + extra_delay)):
                    consecutive_done += 1
                    if consecutive_done >= 2:
                        elapsed = int(time.time() - start_time)
                        logger(f'[{email}] 🌟 Tải dữ liệu hoàn tất sau {elapsed}s!')
                        time.sleep(1.0 + extra_delay)
                        return True

        time.sleep(1.0)

    logger(f'[{email}] ❌ Không xác nhận được màn hình loading sau {timeout}s.')
    return False

async def _async_ocr_card(card_bgr):
    if winocr is None:
        return ""
    try:
        pil_img = Image.fromarray(cv2.cvtColor(card_bgr, cv2.COLOR_BGR2RGB))
        res = await winocr.recognize_pil(pil_img, 'en')
        return res.text.strip().replace('\n', ' ')
    except Exception:
        return ""

def ocr_card_sync(card_bgr):
    """Nhận diện chữ trên thẻ nhân vật/server bằng OCR không đồng bộ qua asyncio."""
    if winocr is None:
        return ""
    try:
        return asyncio.run(_async_ocr_card(card_bgr))
    except Exception:
        return ""


def match_server_score(card_text, target_server):
    """
    Tính điểm khớp giữa nội dung text trên card và target_server.
    Tại bảng Select Server chỉ cần chọn đúng tên Server, không cần tìm theo tên nhân vật.
    """
    if not card_text:
        return -1
    t_srv = (target_server or '').strip().lower()
    if not t_srv:
        return 50  # Không chỉ định server cụ thể -> thẻ nào cũng được
        
    c_txt = card_text.lower()
    
    # 1. Khớp chuỗi trực tiếp (ví dụ 'est-218' trong 'est-218 loyal21')
    if t_srv in c_txt:
        return 100
        
    # 2. Chuẩn hóa dấu chấm/gạch nối và khoảng trắng (ví dụ 'est.217' -> 'est-217')
    c_norm = c_txt.replace('.', '-').replace(' ', '')
    t_norm = t_srv.replace('.', '-').replace(' ', '')
    if t_norm in c_norm:
        return 95
        
    # 3. Chuẩn hóa các ký tự OCR dễ nhầm lẫn trong số: 'i'/'l' -> '1', 'z' -> '2', 'o' -> '0'
    c_norm2 = c_norm.replace('i', '1').replace('l', '1').replace('z', '2').replace('o', '0')
    t_norm2 = t_norm.replace('i', '1').replace('l', '1').replace('z', '2').replace('o', '0')
    if t_norm2 in c_norm2:
        return 90
        
    # 4. So khớp số hiệu của server (ví dụ '218' trong 'est-218')
    t_digits = re.findall(r'\d+', t_srv)
    if t_digits:
        main_num = t_digits[-1]
        if main_num in c_txt or main_num in c_norm2:
            return 85
            
    return 0

def select_server_and_character(hwnd, email, target_char, target_server, logger=print, stop_event=None, extra_delay=0.0, step_timeout=15.0):
    """
    Sau khi điền thông tin đăng nhập và đăng nhập thành công:
    1. Bấm vào crop_title_bottom (khung server ở màn hình Title) để mở popup 'Select Server'.
    2. Đợi popup 'Select Server' mở ra (nhận diện server_header hoặc server_tab_role).
    3. Đảm bảo tab 'Role' đang được chọn.
    4. Quét các thẻ trong bảng Select Server để CHỌN ĐÚNG SERVER (không cần tìm theo tên nhân vật ở bảng này).
    5. Bấm vào thẻ có đúng Server để chọn -> popup đóng lại, game quay về Title screen với đúng Server!
    """
    logger(f'[{email}] 🔍 Mở bảng Select Server để chọn Server=[{target_server or "(tự động)"}]...')
    
    activate_window(hwnd)
    
    # Đóng notice nếu có trước
    match_notice = locate_template_in_window(hwnd, 'notice_close', threshold=0.70)
    if match_notice:
        logger(f'[{email}] 📌 Phát hiện bảng thông báo. Đang bấm tắt [X]...')
        click_coords(match_notice[0], match_notice[1], delay=0.8, hwnd=hwnd, extra_delay=extra_delay)
        time.sleep(0.5)
        
    # 1. Bấm vào crop_title_bottom
    logger(f'[{email}] 🖱️ Bấm vào khung Server (crop_title_bottom) để mở bảng chọn Server...')
    match_bottom = locate_template_in_window(hwnd, 'crop_title_bottom', threshold=0.68)
    if match_bottom:
        click_coords(match_bottom[0], match_bottom[1], delay=1.0, hwnd=hwnd, extra_delay=extra_delay)
    else:
        # Fallback tọa độ khung server trên cửa sổ
        rect = win32gui.GetWindowRect(hwnd)
        wx, wy, ww, wh = rect[0], rect[1], rect[2]-rect[0], rect[3]-rect[1]
        click_coords(wx + int(ww * 0.453), wy + int(wh * 0.778), delay=1.0, hwnd=hwnd, extra_delay=extra_delay)
        
    time.sleep(1.0 + extra_delay)
    if stop_event and stop_event.is_set():
        return False
        
    # 2. Đợi popup 'Select Server' xuất hiện
    logger(f'[{email}] ⏳ Đang chờ mở bảng Select Server...')
    server_opened = False
    open_wait_start = time.time()
    
    while time.time() - open_wait_start < step_timeout:
        if stop_event and stop_event.is_set():
            return False
            
        header_loc = locate_template_in_window(hwnd, 'server_header', threshold=0.68)
        if header_loc:
            server_opened = True
            break
            
        tab_loc = locate_template_in_window(hwnd, 'server_tab_role', threshold=0.68)
        if tab_loc:
            server_opened = True
            break
            
        # Thử click lại crop_title_bottom nếu sau 3s chưa mở
        if time.time() - open_wait_start >= 3.0:
            match_b2 = locate_template_in_window(hwnd, 'crop_title_bottom', threshold=0.68)
            if match_b2:
                click_coords(match_b2[0], match_b2[1], delay=1.0, hwnd=hwnd, extra_delay=extra_delay)
            time.sleep(1.0)
            
        time.sleep(0.5)
        
    if not server_opened:
        logger(f'[{email}] ⚠️ Không thấy bảng Select Server mở ra sau {step_timeout:.0f}s -> Bỏ qua bước chọn Server, tiếp tục trực tiếp...')
        return False
        
    logger(f'[{email}] ✅ Đã mở bảng Select Server!')
    activate_window(hwnd)
    time.sleep(0.5 + extra_delay)
    
    # 3. Đảm bảo tab 'Role' đang được chọn
    match_role = locate_template_in_window(hwnd, 'server_tab_role', threshold=0.70)
    if match_role:
        click_coords(match_role[0], match_role[1], delay=0.5, hwnd=hwnd, extra_delay=extra_delay)
        time.sleep(0.5)
        
    # 4. Quét các thẻ trên bảng Select Server để tìm đúng Server (dùng tỉ lệ tương đối theo kích thước cửa sổ)
    activate_window(hwnd)
    img_bgr, (wx, wy, ww, wh) = capture_window(hwnd)
    if img_bgr is None:
        logger(f'[{email}] ⚠️ Không thể chụp ảnh cửa sổ để quét Server.')
        return False
        
    col_ratios = [0.246, 0.496, 0.746]
    row_ratios = [0.341, 0.483, 0.625, 0.767]
    hw = int(ww * 0.12)
    hh = int(wh * 0.065)
    
    best_slot = None
    best_score = -1
    best_coords = None
    best_text = ""
    
    first_valid_coords = None
    first_valid_text = ""
    
    logger(f'[{email}] 🤖 Đang quét tìm thẻ có Server [{target_server or "Mặc định"}]...')
    slot_idx = 0
    for r_idx, ry in enumerate(row_ratios):
        for c_idx, rx in enumerate(col_ratios):
            slot_idx += 1
            cx = int(ww * rx)
            cy = int(wh * ry)
            
            y1, y2 = cy - hh, cy + hh
            x1, x2 = cx - hw, cx + hw
            if y1 < 0 or y2 > wh or x1 < 0 or x2 > ww:
                continue
                
            card_crop = img_bgr[y1:y2, x1:x2]
            # Bỏ qua ô trống (ô trống không có card nền màu be, mean > 225 hoặc std nhỏ)
            if card_crop.size == 0 or (card_crop.mean() > 222 and card_crop.std() < 6):
                continue
                
            card_text = ocr_card_sync(card_crop)
            if card_text:
                if first_valid_coords is None:
                    first_valid_coords = (wx + cx, wy + cy)
                    first_valid_text = card_text
                    
                score = match_server_score(card_text, target_server)
                logger(f'[{email}]   • Thẻ #{slot_idx}: "{card_text}" -> Khớp Server [{target_server}]: {score}')
                if score > best_score:
                    best_score = score
                    best_slot = slot_idx
                    best_coords = (wx + cx, wy + cy)
                    best_text = card_text
                    # Nếu đã khớp 100% tên Server thì dừng quét sớm để tiết kiệm thời gian
                    if score >= 95:
                        break
        if best_score >= 95:
            break
                
    # 5. Bấm chọn thẻ có đúng tên Server
    if best_coords and best_score > 0:
        logger(f'[{email}] 🎯 Tìm thấy thẻ đúng Server [{target_server}] (Thẻ #{best_slot}: "{best_text}")! Đang nhấp chọn...')
        click_coords(best_coords[0], best_coords[1], delay=1.5, hwnd=hwnd, extra_delay=extra_delay)
    elif first_valid_coords:
        logger(f'[{email}] ℹ️ Không quét thấy thẻ mang tên Server [{target_server}], chọn thẻ đầu tiên: "{first_valid_text}"...')
        click_coords(first_valid_coords[0], first_valid_coords[1], delay=1.5, hwnd=hwnd, extra_delay=extra_delay)
    else:
        # Fallback bấm thẻ đầu tiên theo tọa độ mặc định
        fallback_cx = wx + int(ww * col_ratios[0])
        fallback_cy = wy + int(wh * row_ratios[0])
        logger(f'[{email}] ⚠️ Không quét được chữ trên thẻ, nhấp thẻ đầu tiên tại ({fallback_cx}, {fallback_cy})...')
        click_coords(fallback_cx, fallback_cy, delay=1.5, hwnd=hwnd, extra_delay=extra_delay)
        
    time.sleep(1.5 + extra_delay)
    logger(f'[{email}] ✨ Đã chọn Server [{target_server}] thành công! Sẵn sàng bấm Start Adventure.')
    return True

async def _async_ocr_left_panel(left_bgr):
    if winocr is None:
        return []
    try:
        pil_img = Image.fromarray(cv2.cvtColor(left_bgr, cv2.COLOR_BGR2RGB))
        res = await winocr.recognize_pil(pil_img, 'en')
        words_info = []
        for line in res.lines:
            for word in line.words:
                words_info.append((word.text, word.bounding_rect.x, word.bounding_rect.y, word.bounding_rect.width, word.bounding_rect.height))
        return words_info
    except Exception:
        return []

def ocr_left_panel_sync(left_bgr):
    """Quét OCR danh sách nhân vật ở cạnh trái màn hình chọn nhân vật."""
    if winocr is None:
        return []
    try:
        return asyncio.run(_async_ocr_left_panel(left_bgr))
    except RuntimeError:
        # Nếu đang ở trong event loop, tạo một event loop mới trong thread riêng
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(lambda: asyncio.run(_async_ocr_left_panel(left_bgr)))
            return future.result(timeout=10)
    except Exception:
        return []

def ocr_character_panel_variants(left_bgr):
    """OCR nhiều biến thể ảnh để tăng độ ổn định khi nền game làm mờ tên."""
    height, width = left_bgr.shape[:2]
    variants = [left_bgr]
    enlarged = cv2.resize(left_bgr, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    variants.append(enlarged)

    gray = cv2.cvtColor(left_bgr, cv2.COLOR_BGR2GRAY)
    contrast = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    thresholded = cv2.adaptiveThreshold(
        contrast, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 31, 9,
    )
    variants.append(cv2.cvtColor(thresholded, cv2.COLOR_GRAY2BGR))

    words = []
    for variant in variants:
        scale_x = width / variant.shape[1]
        scale_y = height / variant.shape[0]
        for text, bx, by, bw, bh in ocr_left_panel_sync(variant):
            words.append((
                text,
                int(bx * scale_x), int(by * scale_y),
                int(bw * scale_x), int(bh * scale_y),
            ))
    return words

def select_character_avatar_in_list(hwnd, email, target_char, clone_idx=0, logger=print, stop_event=None, extra_delay=0.0, force_real_delay=False):
    """
    Ở màn hình chọn nhân vật (Character Selection Screen):
    1. Quét danh sách nhân vật ở bên trái cửa sổ.
    2. Tìm đúng tên nhân vật (ví dụ loyal21, loyal29, loyal25...).
    3. Nhấp vào AVATAR kế bên tên nhân vật đó để chọn nhân vật.
    4. Chờ nhân vật được kích hoạt trước khi ấn Start Adventure.
    """
    logger(f'[{email}] 👤 Đang tìm và nhấp chọn nhân vật [{target_char or f"Clone #{clone_idx+1}"}] (nhấp vào Avatar kế bên tên)...')
    activate_window(hwnd)

    # Chờ danh sách tên render đầy đủ rồi mới OCR; các email sau thường tải chậm hơn.
    if force_real_delay:
        _real_sleep(2.0)

    words = []
    wx = wy = ww = wh = 0
    for ocr_attempt in range(3):
        activate_window(hwnd)
        img_bgr, (wx, wy, ww, wh) = capture_window(hwnd)
        if img_bgr is None:
            logger(f'[{email}] ⚠️ Không thể chụp ảnh để tìm avatar nhân vật.')
            return False

        # Tên nhân vật nằm bên phải avatar; lấy rộng hơn để không cắt mất "loyal4".
        left_w = int(ww * 0.45)
        left_bgr = img_bgr[0:wh, 0:left_w]
        words = ocr_character_panel_variants(left_bgr)
        if words and not force_real_delay:
            break
        if force_real_delay and ocr_attempt < 2:
            logger(f'[{email}] ⏳ Danh sách tên chưa render đủ, chờ thêm 1s rồi quét lại (lần {ocr_attempt + 2}/3)...')
            _real_sleep(1.0)
    
    best_word = None
    best_score = 0
    best_y = None

    t_name = (target_char or '').strip().lower().replace(' ', '')
    t_clean = re.sub(r'[^a-z0-9]', '', t_name)

    # OCR đôi khi tách tên thành hai token cùng một dòng, ví dụ "loyal" + "4".
    # Ghép các token gần nhau để so khớp đúng tên hiển thị trong game.
    ocr_candidates = list(words)
    sorted_words = sorted(words, key=lambda item: (item[2], item[1]))
    for first, second in zip(sorted_words, sorted_words[1:]):
        first_text, first_x, first_y, first_w, first_h = first
        second_text, second_x, second_y, second_w, second_h = second
        first_center_y = first_y + first_h / 2
        second_center_y = second_y + second_h / 2
        horizontal_gap = second_x - (first_x + first_w)
        if (
            abs(first_center_y - second_center_y) <= max(first_h, second_h) * 0.8 and
            -5 <= horizontal_gap <= max(first_h, second_h) * 2.0
        ):
            ocr_candidates.append((
                f'{first_text}{second_text}',
                first_x,
                min(first_y, second_y),
                second_x + second_w - first_x,
                max(first_h, second_h),
            ))

    for text, bx, by, bw, bh in ocr_candidates:
        # Bỏ qua nút Back hoặc chữ điều khiển
        if any(b in text.lower() for b in ['back', 'ack', 'exit']):
            continue
        
        # Tính điểm khớp tên nhân vật
        s = 0
        o_clean = re.sub(r'[^a-z0-9]', '', text.lower())
        if t_name and not t_name.startswith('clone'):
            o_tokens = re.findall(r'[a-z]+\d+', text.lower())
            if t_clean == o_clean or t_clean in [re.sub(r'[^a-z0-9]', '', token) for token in o_tokens]:
                s = 100
            else:
                t_norm = t_clean.replace('l', '1').replace('i', '1').replace('o', '0').replace('z', '2')
                o_norm = o_clean.replace('l', '1').replace('i', '1').replace('o', '0').replace('z', '2')
                if t_norm == o_norm:
                    s = 90
                elif (
                    re.search(r'\d+', t_clean).group() in o_clean and
                    difflib.SequenceMatcher(None, t_norm, o_norm).ratio() >= 0.78
                ):
                    s = 80
        
        if s > best_score:
            best_score = s
            best_word = text
            best_y = int(by + bh / 2)

    # 5 vị trí avatar mặc định theo tỉ lệ chiều cao cửa sổ nếu OCR không khớp
    # Avatar 1: ~9.8%, Avatar 2: ~23.7%, Avatar 3: ~37.8%, Avatar 4: ~51.8%, Avatar 5: ~65.8%
    fallback_y_ratios = [0.098, 0.237, 0.378, 0.518, 0.658]
    avatar_x = wx + int(ww * 0.073)

    if best_y is not None and best_score > 0:
        click_y = wy + best_y
        logger(f'[{email}] 🎯 Tìm thấy tên [{target_char}] (khớp với "{best_word}"). Đang nhấp vào Avatar kế bên tại ({avatar_x}, {click_y})...')
        click_coords(
            avatar_x, click_y, delay=1.2, hwnd=hwnd, extra_delay=extra_delay,
            force_real_delay=force_real_delay,
        )
    elif not t_name or t_name.startswith('clone'):
        # Sử dụng vị trí theo số thứ tự clone
        slot_idx = clone_idx % len(fallback_y_ratios)
        click_y = wy + int(wh * fallback_y_ratios[slot_idx])
        logger(f'[{email}] ℹ️ Không nhận diện được tên cụ thể, nhấp Avatar #{slot_idx+1} theo thứ tự tại ({avatar_x}, {click_y})...')
        click_coords(
            avatar_x, click_y, delay=1.2, hwnd=hwnd, extra_delay=extra_delay,
            force_real_delay=force_real_delay,
        )
    else:
        if words:
            ocr_words = ', '.join(text for text, _, _, _, _ in words)
            logger(f'[{email}] 🔎 OCR danh sách nhân vật: [{ocr_words}]')
        logger(f'[{email}] ❌ Không tìm thấy clone [{target_char}] trên danh sách nhân vật.')
        return False

    if force_real_delay:
        _real_sleep(1.0 + extra_delay)
    else:
        time.sleep(1.0 + extra_delay)
    logger(f'[{email}] ✅ Đã nhấp chọn Avatar nhân vật xong!')
    return True

def _run_flow_steps(account, clone_exe, stop_event=None, logger=print, index=0, total=1, logout_delay=4.0, open_game_delay=0.0, mode='login', step_timeout=30.0, skip_login=False, auto_tile=True):
    email = account.get('email', '')
    password = account.get('password', '')
    server = account.get('server', '')
    
    game_dir = os.path.dirname(clone_exe)
    exe_name = os.path.basename(clone_exe)
    
    # GHI NHẬN TẤT CẢ CÁC CỬA SỔ TOW HIỆN CÓ TRƯỚC KHI MỞ CỬA SỔ MỚI
    # (Tuyệt đối không bao giờ nhận nhầm cửa sổ của các account đã mở trước đó)
    existing_hwnds = set(find_tow_windows())
    num_existing = len(existing_hwnds)
    
    extra_delay = 0.0
    logger(f'[{email}] 🚀 Đang khởi động {exe_name} (Đang có {num_existing} tab chạy)...')
        
    def step_pause(step_desc=""):
        pass

    proc = subprocess.Popen([clone_exe], cwd=game_dir)
    pid = proc.pid
    
    # 1. Tìm bước tiếp theo: Cửa sổ game ToW MỚI xuất hiện (tối đa 30s)
    def find_new_game_win():
        h = find_window_by_pid(pid)
        if h and h not in existing_hwnds:
            return h
        current_wins = find_tow_windows()
        new_wins = [w for w in current_wins if w not in existing_hwnds]
        if new_wins:
            return new_wins[-1]
        return None
        
    hwnd = wait_for_next_step(None, email, logger, stop_event, "Cửa sổ game ToW mới", find_new_game_win, timeout=step_timeout)
    if stop_event and stop_event.is_set():
        return False, proc, pid, hwnd
        
    logger(f'[{email}] ✅ Đã xác định đúng cửa sổ game của account này (HWND: {hwnd})! Kích hoạt...')
    activate_window(hwnd)

    if not skip_login:
        # 2. Tìm bước tiếp theo: Màn hình bắt đầu game (Popup Notice hoặc icon Account, tối đa 30s)
        def check_initial_screen():
            activate_window(hwnd)
            match_notice = locate_template_in_window(hwnd, 'notice_close', threshold=0.72)
            if match_notice:
                return ('notice', match_notice)
            match_acc = locate_template_in_window(hwnd, 'account', threshold=0.72)
            if match_acc:
                return ('account', match_acc)
            match_start = locate_template_in_window(hwnd, 'start_adv_title', threshold=0.68)
            if match_start:
                return ('title', match_start)
            return None

        init_res = wait_for_next_step(hwnd, email, logger, stop_event, "Màn hình bắt đầu (Notice / Account)", check_initial_screen, timeout=step_timeout)
        if stop_event and stop_event.is_set():
            return False, proc, pid, hwnd

        # Độ trễ sau khi mở game hoàn toàn do người dùng tùy chỉnh (trước khi tắt thông báo của phần đăng xuất)
        if open_game_delay and float(open_game_delay) > 0:
            actual_open_delay = float(open_game_delay)
            logger(f'[{email}] ⏳ Đang chờ {actual_open_delay:.0f}s sau khi mở game (theo tùy chỉnh của người dùng)...')
            delay_start = time.time()
            while time.time() - delay_start < actual_open_delay:
                state = check_flow_control(email, "chờ sau khi mở game")
                if state == 'stop':
                    return False, proc, pid, hwnd
                if state == 'skip':
                    break
                time.sleep(0.5)
            activate_window(hwnd)
            time.sleep(0.5)

        if init_res and init_res[0] == 'notice':
            logger(f'[{email}] 📌 Phát hiện bảng thông báo (Notice). Đang tắt...')
            match_n_fresh = locate_template_in_window(hwnd, 'notice_close', threshold=0.70)
            target_close = match_n_fresh if match_n_fresh else init_res[1]
            click_coords(target_close[0], target_close[1], delay=1.0, hwnd=hwnd, extra_delay=extra_delay)
            time.sleep(1.0)

        activate_window(hwnd)

        # 3. Click nút Account (Đăng xuất)
        match_notice_before_logout = locate_template_in_window(hwnd, 'notice_close', threshold=0.72)
        if match_notice_before_logout:
            logger(f'[{email}] 📌 Đóng Notice trước khi bấm Account (Đăng xuất)...')
            click_coords(
                match_notice_before_logout[0],
                match_notice_before_logout[1],
                delay=0.8,
                hwnd=hwnd,
                extra_delay=extra_delay,
            )
            _real_sleep(0.5)

        logger(f'[{email}] 🔑 Đang tìm nút Account (Đăng xuất)...')
        match_acc = locate_template_in_window(hwnd, 'account', threshold=0.70)
        if match_acc:
            click_coords(match_acc[0], match_acc[1], delay=0.8, hwnd=hwnd, extra_delay=extra_delay)
        else:
            rect = win32gui.GetWindowRect(hwnd)
            wx, wy, ww, wh = rect[0], rect[1], rect[2]-rect[0], rect[3]-rect[1]
            logger(f'[{email}] ⚠️ Nhận diện ảnh chưa thấy, bấm tọa độ nút Account lần 1...')
            click_coords(wx + int(ww * 0.08), wy + int(wh * 0.18), delay=0.8, hwnd=hwnd, extra_delay=extra_delay)

        time.sleep(2.0 + extra_delay)
        if stop_event and stop_event.is_set():
            return False, proc, pid, hwnd
        activate_window(hwnd)

        match_notice2 = locate_template_in_window(hwnd, 'notice_close', threshold=0.72)
        if match_notice2:
            logger(f'[{email}] 📌 Bảng thông báo xuất hiện đè. Đang bấm đóng...')
            click_coords(match_notice2[0], match_notice2[1], delay=0.8, hwnd=hwnd, extra_delay=extra_delay)
            _real_sleep(0.5)

        logger(f'[{email}] 🔁 Bấm nút Account (Đăng xuất) lần 2 để đảm bảo...')
        match_acc2 = locate_template_in_window(hwnd, 'account', threshold=0.70)
        if match_acc2:
            click_coords(match_acc2[0], match_acc2[1], delay=0.8, hwnd=hwnd, extra_delay=extra_delay)
        else:
            rect = win32gui.GetWindowRect(hwnd)
            wx, wy, ww, wh = rect[0], rect[1], rect[2]-rect[0], rect[3]-rect[1]
            click_coords(wx + int(ww * 0.08), wy + int(wh * 0.18), delay=0.8, hwnd=hwnd, extra_delay=extra_delay)

        step_pause("chờ sau khi bấm Đăng xuất")

        if logout_delay and float(logout_delay) > 0:
            actual_delay = float(logout_delay)
            logger(f'[{email}] ⏳ Đang trễ {actual_delay:.0f}s chờ game ổn định sau đăng xuất (chống giật do cửa sổ CMD)...')
            delay_start = time.time()
            while time.time() - delay_start < actual_delay:
                state = check_flow_control(email, "chờ sau đăng xuất")
                if state == 'stop':
                    return False, proc, pid, hwnd
                if state == 'skip':
                    break
                time.sleep(0.5)
            activate_window(hwnd)
            time.sleep(0.5)
        else:
            activate_window(hwnd)

        # 4. Tìm bước tiếp theo: Form đăng nhập xuất hiện (tối đa 30s)
        def check_login_form():
            activate_window(hwnd)
            match_n = locate_template_in_window(hwnd, 'notice_close', threshold=0.70)
            if match_n:
                logger(f'[{email}] 📌 Phát hiện bảng thông báo. Đang tắt [X]...')
                click_coords(match_n[0], match_n[1], delay=0.8, hwnd=hwnd, extra_delay=extra_delay, force_real_delay=True)
                time.sleep(0.5)
            match_form = locate_template_in_window(hwnd, 'login_form', threshold=0.55)
            if match_form:
                return ('form', match_form)
            match_e = locate_template_in_window(hwnd, 'icon_email', threshold=0.68)
            if match_e:
                return ('email', match_e)
            match_l = locate_template_in_window(hwnd, 'btn_login', threshold=0.70)
            if match_l:
                return ('login', match_l)
            return None

        form_res = None
        form_check_start = time.time()
        while time.time() - form_check_start < 3.0:
            if stop_event and stop_event.is_set():
                return False, proc, pid, hwnd
            form_res = check_login_form()
            if form_res:
                logger(f'[{email}] ✅ Đã xác nhận popup form đăng nhập.')
                break
            _real_sleep(0.1)

        if not form_res:
            logger(f'[{email}] ⚠️ Chưa thấy popup form đăng nhập. Đóng Notice và thực hiện lại bước đăng xuất...')
            match_notice_retry = locate_template_in_window(hwnd, 'notice_close', threshold=0.70)
            if match_notice_retry:
                logger(f'[{email}] 📌 Đang tắt Notice trước khi đăng xuất lại...')
                click_coords(match_notice_retry[0], match_notice_retry[1], delay=0.8, hwnd=hwnd, extra_delay=extra_delay)
                _real_sleep(0.5)

            match_acc_retry = locate_template_in_window(hwnd, 'account', threshold=0.70)
            if match_acc_retry:
                click_coords(match_acc_retry[0], match_acc_retry[1], delay=0.8, hwnd=hwnd, extra_delay=extra_delay)
            else:
                rect = win32gui.GetWindowRect(hwnd)
                wx, wy, ww, wh = rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1]
                click_coords(wx + int(ww * 0.08), wy + int(wh * 0.18), delay=0.8, hwnd=hwnd, extra_delay=extra_delay)

            time.sleep(2.0 + extra_delay)
            match_notice_retry = locate_template_in_window(hwnd, 'notice_close', threshold=0.70)
            if match_notice_retry:
                logger(f'[{email}] 📌 Đang tắt Notice sau khi đăng xuất lại...')
                click_coords(match_notice_retry[0], match_notice_retry[1], delay=0.8, hwnd=hwnd, extra_delay=extra_delay)

        form_res = wait_for_next_step(hwnd, email, logger, stop_event, "Form đăng nhập", check_login_form, timeout=step_timeout)
        if stop_event and stop_event.is_set():
            return False, proc, pid, hwnd

        step_pause("chờ form đăng nhập sẵn sàng")

        # Điền Email & Password
        for input_attempt in range(1, 3):
            if stop_event and stop_event.is_set():
                return False, proc, pid, hwnd
            activate_window(hwnd)

            match_email = locate_template_in_window(hwnd, 'icon_email', threshold=0.68)
            rect = win32gui.GetWindowRect(hwnd)
            wx, wy, ww, wh = rect[0], rect[1], rect[2]-rect[0], rect[3]-rect[1]

            if match_email:
                click_coords(match_email[0] + 60, match_email[1], delay=0.3, hwnd=hwnd, extra_delay=extra_delay)
            else:
                click_coords(wx + int(ww * 0.48), wy + int(wh * 0.40), delay=0.3, hwnd=hwnd, extra_delay=extra_delay)

            logger(f'[{email}] ✍️ Đang nhập Email (Lần {input_attempt})...')
            type_via_clipboard(email, delay=0.3, hwnd=hwnd, extra_delay=extra_delay)

            email_ok = False
            try:
                pyperclip.copy('')
                pyautogui.hotkey('ctrl', 'a')
                time.sleep(0.05)
                pyautogui.hotkey('ctrl', 'c')
                time.sleep(0.05)
                copied = pyperclip.paste().strip()
                if copied == email.strip():
                    email_ok = True
            except Exception:
                pass

            if not email_ok:
                logger(f'[{email}] ⚠️ Kiểm tra thấy ô Email chưa đủ dữ liệu -> Đang xóa và nhập lại...')
                if match_email:
                    click_coords(match_email[0] + 60, match_email[1], delay=0.2, hwnd=hwnd, extra_delay=extra_delay)
                else:
                    click_coords(wx + int(ww * 0.48), wy + int(wh * 0.40), delay=0.2, hwnd=hwnd, extra_delay=extra_delay)
                type_via_clipboard(email, delay=0.4, hwnd=hwnd, extra_delay=extra_delay)

            match_pwd = locate_template_in_window(hwnd, 'icon_password', threshold=0.70)
            if match_pwd:
                click_coords(match_pwd[0] + 60, match_pwd[1], delay=0.3, hwnd=hwnd, extra_delay=extra_delay)
            else:
                click_coords(wx + int(ww * 0.48), wy + int(wh * 0.47), delay=0.3, hwnd=hwnd, extra_delay=extra_delay)

            logger(f'[{email}] 🔒 Đang nhập Mật khẩu (Lần {input_attempt})...')
            type_via_clipboard(password, delay=0.4, hwnd=hwnd, extra_delay=extra_delay)

            step_pause("chuẩn bị gửi thông tin đăng nhập")

            match_login = locate_template_in_window(hwnd, 'btn_login', threshold=0.70)
            if match_login:
                logger(f'[{email}] 🔵 Bấm nút Log In...')
                click_coords(match_login[0], match_login[1], delay=1.5, hwnd=hwnd, extra_delay=extra_delay)
            else:
                click_coords(wx + int(ww * 0.48), wy + int(wh * 0.60), delay=1.5, hwnd=hwnd, extra_delay=extra_delay)

            time.sleep(2.5 + extra_delay)
            activate_window(hwnd)
            still_form = locate_template_in_window(hwnd, 'btn_login', threshold=0.70) or locate_template_in_window(hwnd, 'icon_email', threshold=0.68)
            if still_form and input_attempt < 2:
                logger(f'[{email}] ⚠️ Form đăng nhập vẫn còn hiện diện (chưa đủ thông tin hoặc bị nuốt phím). Đang kiểm tra và nhập lại...')
                time.sleep(1.0 + extra_delay)
                continue
            else:
                break

        step_pause("chờ chuyển cảnh sau Log In")

    else:
        # skip_login=True: clone tiếp theo cùng account — bỏ qua logout+login
        # Chờ màn hình char select / StartAdventure xuất hiện (game đã giữ session)
        logger(f'[{email}] ⏭️ Bỏ qua bước Đăng xuất/Đăng nhập — cùng tài khoản, tiếp tục chọn nhân vật tiếp theo...')
        activate_window(hwnd)
        step_pause("chờ cửa sổ game clone tiếp theo ổn định")
        # Clone mới luôn có thể hiện Notice sau khi cửa sổ đã ổn định; chờ ngắn để bắt popup xuất hiện.
        notice_wait_start = time.time()
        while time.time() - notice_wait_start < 10.0:
            if stop_event and stop_event.is_set():
                return False, proc, pid, hwnd
            match_n = locate_template_in_window(hwnd, 'notice_close', threshold=0.70)
            if match_n:
                logger(f'[{email}] 📌 Clone mới xuất hiện bảng thông báo. Đang bấm tắt [X]...')
                click_coords(match_n[0], match_n[1], delay=0.8, hwnd=hwnd, extra_delay=extra_delay)
                time.sleep(0.5)
                break
            time.sleep(0.5)
        else:
            logger(f'[{email}] ✅ Không thấy Notice trong thời gian chờ, tiếp tục kiểm tra màn hình nhân vật...')

        # [FIX 2c] Chờ màn hình chọn nhân vật / Start Adventure xuất hiện trước khi tiếp tục
        # Tránh miss-click do game chưa kịp render character select screen
        logger(f'[{email}] 🔍 Chờ màn hình chọn nhân vật (Start Adventure) xuất hiện...')
        def _check_char_or_start():
            activate_window(hwnd)
            # Đóng notice nếu có trước
            match_notice = locate_template_in_window(hwnd, 'notice_close', threshold=0.70)
            if match_notice:
                click_coords(match_notice[0], match_notice[1], delay=0.5, hwnd=hwnd, extra_delay=extra_delay)
                time.sleep(0.3)
            if locate_template_in_window(hwnd, 'start_adv_title', threshold=0.68):
                return True
            if locate_template_in_window(hwnd, 'start_adv_char', threshold=0.68):
                return True
            return None

        char_wait_start = time.time()
        char_screen_found = False
        while time.time() - char_wait_start < step_timeout:
            if stop_event and stop_event.is_set():
                return False, proc, pid, hwnd
            res = _check_char_or_start()
            if res:
                logger(f'[{email}] ✅ Màn hình chọn nhân vật đã sẵn sàng!')
                char_screen_found = True
                break
            time.sleep(0.8)
        if not char_screen_found:
            logger(f'[{email}] ⚠️ Không thấy màn hình chọn nhân vật sau {step_timeout:.0f}s — tiếp tục bằng fallback...')

    # BƯỚC CHỌN ĐÚNG CLONE (Bấm crop_title_bottom để mở Select Server và chọn đúng nhân vật/server)
    target_char = account.get('_clone_name', '').strip()
    target_server = account.get('server', '').strip() or account.get('_clone_server', '').strip()

    if mode == 'clone' or target_char or target_server:
        select_server_and_character(
            hwnd=hwnd,
            email=email,
            target_char=target_char,
            target_server=target_server,
            logger=logger,
            stop_event=stop_event,
            extra_delay=extra_delay,
            step_timeout=step_timeout,
        )
        if stop_event and stop_event.is_set():
            return False, proc, pid, hwnd
        step_pause("chờ sau khi chọn nhân vật và quay về Title")
        time.sleep(1.0 + extra_delay)

    logger(f'[{email}] 🚀 Đã trỏ đúng Server & Nhân vật -> Tìm nút Start Adventure để vào game...')
    def check_start_btn():
        activate_window(hwnd)
        match_notice = locate_template_in_window(hwnd, 'notice_close', threshold=0.70)
        if match_notice:
            logger(f'[{email}] 📌 Phát hiện bảng thông báo. Đang bấm tắt [X]...')
            click_coords(match_notice[0], match_notice[1], delay=0.8, hwnd=hwnd, extra_delay=extra_delay)
            time.sleep(0.5)
        match_start = (
            locate_template_in_window(hwnd, 'start_adv_title', threshold=0.68) or
            locate_template_in_window(hwnd, 'crop_real_start_adv', threshold=0.68)
        )
        if match_start:
            return ('title', match_start)
        match_start_char = locate_template_in_window(hwnd, 'start_adv_char', threshold=0.68)
        if match_start_char:
            return ('char', match_start_char)
        return None

    start_res = None
    start_wait_t = time.time()
    while time.time() - start_wait_t < step_timeout:
        if stop_event and stop_event.is_set():
            return False, proc, pid, hwnd
        start_res = check_start_btn()
        if start_res:
            break
        if time.time() - start_wait_t >= (4.0 + extra_delay):
            rect = win32gui.GetWindowRect(hwnd)
            wx, wy, ww, wh = rect[0], rect[1], rect[2]-rect[0], rect[3]-rect[1]
            logger(f'[{email}] 👉 Bấm tọa độ nút Start Adventure giữa phía dưới...')
            fallback_start = (wx + int(ww * 0.50), wy + int(wh * 0.90))
            start_res = ('fallback', fallback_start)
            break
        _real_sleep(0.8)

    if not start_res:
        raise StepTimeoutException(f"Không tìm thấy bước tiếp theo [Nút Start Adventure] sau {step_timeout:.0f}s")

    # 1. Nếu đang ở màn hình Title (hoặc fallback): Bấm Start Adventure trên Title để mở màn hình chọn nhân vật
    if start_res[0] in ('title', 'fallback'):
        logger(f'[{email}] ⚔️ Bấm nút Start Adventure trên màn hình Title...')
        click_coords(
            start_res[1][0], start_res[1][1], delay=2.0, hwnd=hwnd,
            extra_delay=extra_delay, force_real_delay=True,
        )
        _real_sleep(1.5 + extra_delay)
        activate_window(hwnd)

    # 2. Đợi màn hình chọn nhân vật xuất hiện (tối đa 15s)
    logger(f'[{email}] 🔍 Đang kiểm tra màn hình chọn nhân vật (Character Selection)...')
    is_char_screen = False
    loading_detected = False
    char_wait_start = time.time()
    while time.time() - char_wait_start < 15.0:
        if stop_event and stop_event.is_set():
            return False, proc, pid, hwnd
        match_char_adv = (
            locate_template_in_window(hwnd, 'start_adv_char', threshold=0.65) or
            locate_template_in_window(hwnd, 'final_start_adv', threshold=0.65)
        )
        if match_char_adv or start_res[0] == 'char':
            is_char_screen = True
            break
        # Kiểm tra nếu game vào thẳng màn hình loading map
        if locate_template_in_window(hwnd, 'loading_entering', threshold=0.65) or locate_template_in_window(hwnd, 'loading_dear_adv', threshold=0.65):
            loading_detected = True
            break
        _real_sleep(0.5)

    # 3. Ở MÀN HÌNH NÀY: NHẤP VÀO AVATAR KẾ BÊN TÊN NHÂN VẬT TRƯỚC, SAU ĐÓ MỚI BẤM START ADVENTURE!
    final_start_clicked = False
    if is_char_screen:
        if mode == 'login':
            logger(f'[{email}] ⏭️ Auto Login: bỏ qua bước nhấp Avatar, đi thẳng tới Start Adventure cuối.')
        else:
            character_selected = select_character_avatar_in_list(
                hwnd=hwnd,
                email=email,
                target_char=target_char,
                clone_idx=index,
                logger=logger,
                stop_event=stop_event,
                extra_delay=extra_delay,
                force_real_delay=(mode == 'clone'),
            )
            if not character_selected and target_char and not target_char.lower().startswith('clone'):
                raise CloneNotFoundException(
                    f'Không tìm thấy clone [{target_char}]',
                    proc=proc,
                    pid=pid,
                    hwnd=hwnd,
                )
        if stop_event and stop_event.is_set():
            return False, proc, pid, hwnd

        if mode == 'login':
            # Auto Login vẫn giữ nhịp render như Safe Mode trước khi tìm nút cuối.
            _real_sleep(1.0)
        activate_window(hwnd)
        # Đồng bộ như Safe Mode: chờ game hoàn tất chọn avatar và render nút cuối trước khi chụp.
        _real_sleep(5.0)
        match_start_char2 = None
        start_char_wait = time.time()
        while time.time() - start_char_wait < 8.0:
            if stop_event and stop_event.is_set():
                return False, proc, pid, hwnd
            # FastMode vẫn phải có một frame chụp thực tế trước khi click cuối.
            match_start_char2 = capture_final_start_button(hwnd, threshold=0.65)
            if match_start_char2:
                break
            _real_sleep(0.1)

        # Bấm nút Start Adventure màu xanh góc dưới bên phải
        if match_start_char2:
            logger(f'[{email}] 📸 Đã chụp và so sánh với image-2.png (độ khớp {match_start_char2[2]:.2f}).')
            logger(f'[{email}] 🎯 Tọa độ nút từ ảnh: ({match_start_char2[0]}, {match_start_char2[1]}). Đang đưa con trỏ tới đúng vị trí...')
            logger(f'[{email}] 🎮 Bấm nút Start Adventure màu xanh góc dưới để vào game...')
            click_coords(
                match_start_char2[0], match_start_char2[1], delay=2.0, hwnd=hwnd,
                extra_delay=extra_delay, force_real_delay=True,
            )
            final_start_clicked = True
        else:
            rect = win32gui.GetWindowRect(hwnd)
            wx, wy, ww, wh = rect[0], rect[1], rect[2]-rect[0], rect[3]-rect[1]
            logger(f'[{email}] 🎮 Bấm tọa độ nút Start Adventure màu xanh góc phải bên dưới (83.6%, 90.8%)...')
            click_coords(
                wx + int(ww * 0.836), wy + int(wh * 0.908), delay=2.0, hwnd=hwnd,
                extra_delay=extra_delay, force_real_delay=True,
            )
            final_start_clicked = True

    elif mode == 'clone':
        # Cho game thêm một nhịp render trước khi kết luận Character Selection bị treo.
        logger(f'[{email}] ⏳ Chờ thêm 3s để màn hình chọn nhân vật Multi Clone render hoàn tất...')
        _real_sleep(3.0)
        activate_window(hwnd)
        late_char_match = (
            locate_template_in_window(hwnd, 'start_adv_char', threshold=0.65) or
            locate_template_in_window(hwnd, 'final_start_adv', threshold=0.65)
        )
        if late_char_match:
            is_char_screen = True
        else:
            raise StepTimeoutException(
                'Chưa xác nhận màn hình chọn nhân vật Multi Clone; không được click fallback hoặc thu nhỏ tab'
            )

    if is_char_screen and not final_start_clicked:
        if mode != 'login' and 'character_selected' not in locals():
            character_selected = select_character_avatar_in_list(
                hwnd=hwnd,
                email=email,
                target_char=target_char,
                clone_idx=index,
                logger=logger,
                stop_event=stop_event,
                extra_delay=extra_delay,
                force_real_delay=(mode == 'clone'),
            )
            if not character_selected and target_char and not target_char.lower().startswith('clone'):
                raise CloneNotFoundException(
                    f'Không tìm thấy clone [{target_char}]',
                    proc=proc,
                    pid=pid,
                    hwnd=hwnd,
                )
        activate_window(hwnd)
        _real_sleep(5.0)
        match_start_char2 = capture_final_start_button(hwnd, threshold=0.65)
        if match_start_char2:
            logger(f'[{email}] 📸 Đã chụp và so sánh với image-2.png sau thời gian chờ bổ sung.')
            click_coords(
                match_start_char2[0], match_start_char2[1], delay=2.0, hwnd=hwnd,
                extra_delay=extra_delay, force_real_delay=True,
            )
            final_start_clicked = True

    elif mode != 'clone' and not loading_detected and start_res[0] in ('title', 'fallback'):
        rect = win32gui.GetWindowRect(hwnd)
        wx, wy, ww, wh = rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1]
        logger(f'[{email}] ⚠️ Không nhận diện được màn hình nhân vật, bấm fallback Start Adventure cuối tại góc phải (83.6%, 90.8%)...')
        click_coords(
            wx + int(ww * 0.836), wy + int(wh * 0.908), delay=2.0, hwnd=hwnd,
            extra_delay=extra_delay, force_real_delay=True,
        )
        final_start_clicked = True

    if not final_start_clicked and not loading_detected:
        raise StepTimeoutException('Chưa click được nút Start Adventure cuối')

    if mode == 'login':
        # Cho Auto Login thêm thời gian xử lý click cuối như Safe Mode.
        _real_sleep(2.0)

    # Xác nhận game đã nhận click cuối trước khi cho phép xếp cửa sổ.
    logger(f'[{email}] 🔍 Đang xác nhận chuyển cảnh sau khi click Start Adventure cuối...')
    transition_confirmed = False
    transition_wait_start = time.time()
    button_gone_count = 0
    while time.time() - transition_wait_start < 8.0:
        if stop_event and stop_event.is_set():
            return False, proc, pid, hwnd

        loading_seen = (
            locate_template_in_window(hwnd, 'loading_entering', threshold=0.65) or
            locate_template_in_window(hwnd, 'loading_dear_adv', threshold=0.65)
        )
        if loading_seen:
            logger(f'[{email}] ✅ Đã xác nhận game chuyển sang màn hình loading.')
            transition_confirmed = True
            break

        final_button_still_visible = locate_template_in_window(hwnd, 'final_start_adv', threshold=0.65)
        if not final_button_still_visible:
            button_gone_count += 1
            if button_gone_count >= 2:
                logger(f'[{email}] ✅ Đã xác nhận nút Start Adventure cuối biến mất sau click.')
                transition_confirmed = True
                break
        else:
            button_gone_count = 0

        _real_sleep(0.2)

    if not transition_confirmed:
        raise StepTimeoutException('Game chưa xác nhận chuyển cảnh sau khi click Start Adventure cuối')
        
    # Xử lý thông báo in-game nếu có xuất hiện
    match_notice_final = locate_template_in_window(hwnd, 'notice_close', threshold=0.70)
    if match_notice_final:
        logger(f'[{email}] 📌 Bấm tắt bảng thông báo trong game [X]...')
        click_coords(match_notice_final[0], match_notice_final[1], delay=0.8, hwnd=hwnd, extra_delay=extra_delay)
        time.sleep(0.5)

    step_pause("chờ ổn định trước khi xếp ngói cửa sổ")

    # 8. Xếp cửa sổ (nếu người dùng bật tùy chọn Tự xếp ngói)
    if auto_tile:
        tile_window(hwnd, index, total)
    logger(f'[{email}] ✨ Hoàn tất đăng nhập thành công!')
    return True, proc, pid, hwnd

def auto_login_flow(account, clone_exe, stop_event=None, logger=print, index=0, total=1,
                    logout_delay=4.0, open_game_delay=0.0, mode='login', step_timeout=30.0,
                    max_retries=2, skip_login=False, pause_event=None, skip_step_event=None, auto_tile=True):
    set_automation_events(stop_event=stop_event, pause_event=pause_event, skip_step_event=skip_step_event, logger=logger)
    email = account.get('email', '')

    for attempt in range(1, max_retries + 2):
        if stop_event and stop_event.is_set():
            logger(f'[{email}] 🛑 Người dùng đã bấm dừng.')
            return False

        if attempt > 1:
            logger(f'[{email}] 🔁 Bắt đầu chạy lại sau khi khởi động lại game (Lần thử {attempt}/{max_retries + 1})...')

        proc = None
        pid = None
        hwnd = None

        try:
            success, proc, pid, hwnd = _run_flow_steps(
                account=account,
                clone_exe=clone_exe,
                stop_event=stop_event,
                logger=logger,
                index=index,
                total=total,
                logout_delay=logout_delay,
                open_game_delay=open_game_delay,
                mode=mode,
                step_timeout=step_timeout,
                skip_login=skip_login,
                auto_tile=auto_tile,
            )
            if success:
                return True
            else:
                if stop_event and stop_event.is_set():
                    return False
        except StepTimeoutException as e:
            logger(f'[{email}] ⚠️ Phát hiện game bị treo: {e}!')
            if attempt <= max_retries:
                logger(f'[{email}] 💥 Đang đóng tiến trình game bị treo và khởi động lại sau 3s (Lần {attempt}/{max_retries})...')
                kill_game_process(proc, pid, hwnd)
                time.sleep(3.0)
                continue
            else:
                logger(f'[{email}] ❌ Đã thử khởi động lại {max_retries} lần nhưng không qua được bước tiếp theo. Bỏ qua tài khoản này.')
                kill_game_process(proc, pid, hwnd)
                return False
        except CloneNotFoundException as e:
            logger(f'[{email}] ❌ {e}. Đánh dấu clone là "không tìm thấy clone" và bỏ qua clone này.')
            clone_ref = account.get('_clone_ref')
            if clone_ref is not None:
                clone_ref['status'] = 'không tìm thấy clone'
            logger(f'[{email}] 🛑 Đang đóng tab game của clone lỗi (HWND: {e.hwnd}, PID: {e.pid})...')
            kill_game_process(e.proc, e.pid, e.hwnd)
            logger(f'[{email}] ✅ Đã đóng tab game của clone lỗi.')
            return False
        except Exception as e:
            logger(f'[{email}] ❌ Lỗi phát sinh trong quá trình đăng nhập: {e}')
            kill_game_process(proc, pid, hwnd)
            return False

    return False


def auto_login_flow_grouped(account, clones, clone_exe, stop_event=None, logger=print,
                             base_index=0, total_tasks=1,
                             logout_delay=4.0, open_game_delay=0.0, step_timeout=30.0, max_retries=2,
                             pause_event=None, skip_step_event=None, auto_tile=True, concurrency=1):
    """
    Luồng Multi-Clone theo nhóm tài khoản (Cách 2 - Song song theo batch):
      đăng xuất -> đăng nhập gmail1 -> clone1 (tuần tự) -> [clone2, clone3, ...] (song song với concurrency) -> đăng xuất -> gmail2 -> ...

        - Clone đầu tiên: thực hiện full flow (logout + login + StartAdventure) TUẦN TỰ để khởi tạo session.
        - Các clone tiếp theo của CÙNG TÀI KHOẢN: mở thêm window mới, bỏ qua bước logout/login,
            nếu concurrency > 1 sẽ chạy song song theo luồng đa tiến trình (ThreadPoolExecutor).
        - Nếu clone đầu tiên THẤT BẠI: bỏ qua toàn bộ account (không mở clone tiếp vì không có session).

    Trả về: list[bool] — kết quả từng clone theo thứ tự.
    """
    set_automation_events(stop_event=stop_event, pause_event=pause_event, skip_step_event=skip_step_event, logger=logger)
    email = account.get('email', '')
    if not clones:
        return []

    results = [False] * len(clones)

    # 1. Clone đầu tiên (Clone #1): Thực hiện full flow (Logout + Login + StartAdventure) TUẦN TỰ
    clone0 = clones[0]
    task_acc0 = dict(account)
    task_acc0['server'] = clone0.get('server') or account.get('server', '')
    task_acc0['_clone_name'] = clone0.get('name', '')
    task_acc0['_clone_server'] = clone0.get('server', '')
    task_acc0['_clone_ref'] = clone0

    cname0 = clone0.get('name', 'Clone 1')
    csrv0 = clone0.get('server', '')
    clone_label0 = f"{cname0}" + (f" ({csrv0})" if csrv0 else '')
    logger(f'[{email}] ━━━ Clone #1: {clone_label0} — Thực hiện full Đăng xuất → Đăng nhập ━━━')

    ok0 = auto_login_flow(
        account=task_acc0,
        clone_exe=clone_exe,
        stop_event=stop_event,
        logger=logger,
        index=base_index,
        total=total_tasks,
        logout_delay=logout_delay,
        open_game_delay=open_game_delay,
        mode='clone',
        step_timeout=step_timeout,
        max_retries=max_retries,
        skip_login=False,
        pause_event=pause_event,
        skip_step_event=skip_step_event,
        auto_tile=auto_tile,
    )
    results[0] = ok0

    # Nếu clone đầu tiên thất bại → bỏ qua toàn bộ account (không có session)
    if not ok0:
        if not (stop_event and stop_event.is_set()):
            logger(f'[{email}] ❌ Clone đầu tiên ({clone_label0}) thất bại → Bỏ qua {len(clones) - 1} clone còn lại của tài khoản này.')
        return results

    if len(clones) == 1 or (stop_event and stop_event.is_set()):
        return results

    # 2. Các clone tiếp theo của CÙNG TÀI KHOẢN (bỏ qua Đăng xuất / Đăng nhập)
    remaining_items = list(enumerate(clones))[1:]  # [(1, clone1), (2, clone2), ...]

    if concurrency > 1 and len(remaining_items) > 1:
        logger(f'[{email}] 🚀 Chạy song song {len(remaining_items)} clone tiếp theo (Số tab chạy cùng lúc: {concurrency})...')

        def _run_single_clone(item):
            clone_offset, clone = item
            if stop_event and stop_event.is_set():
                return clone_offset, False

            task_acc = dict(account)
            task_acc['server'] = clone.get('server') or account.get('server', '')
            task_acc['_clone_name'] = clone.get('name', '')
            task_acc['_clone_server'] = clone.get('server', '')
            task_acc['_clone_ref'] = clone

            run_index = base_index + clone_offset
            cname = clone.get('name', f'Clone {clone_offset+1}')
            csrv = clone.get('server', '')
            clone_label = f"{cname}" + (f" ({csrv})" if csrv else '')

            logger(f'[{email}] ━━━ Clone #{clone_offset+1}: {clone_label} — [Song song] Mở cửa sổ mới, bỏ qua Đăng xuất/Đăng nhập ━━━')

            ok = auto_login_flow(
                account=task_acc,
                clone_exe=clone_exe,
                stop_event=stop_event,
                logger=logger,
                index=run_index,
                total=total_tasks,
                logout_delay=0.0,
                open_game_delay=open_game_delay,
                mode='clone',
                step_timeout=step_timeout,
                max_retries=max_retries,
                skip_login=True,
                pause_event=pause_event,
                skip_step_event=skip_step_event,
                auto_tile=auto_tile,
            )
            return clone_offset, ok

        max_workers = min(concurrency, len(remaining_items))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_offset = {executor.submit(_run_single_clone, item): item[0] for item in remaining_items}
            for future in concurrent.futures.as_completed(future_to_offset):
                try:
                    c_off, ok = future.result()
                    results[c_off] = ok
                except Exception as e:
                    c_off = future_to_offset[future]
                    logger(f'[{email}] ❌ Lỗi luồng clone #{c_off+1}: {e}')
                    results[c_off] = False
    else:
        # Chạy tuần tự từng clone nếu concurrency == 1 hoặc chỉ có 1 clone còn lại
        for clone_offset, clone in remaining_items:
            if stop_event and stop_event.is_set():
                break

            task_acc = dict(account)
            task_acc['server'] = clone.get('server') or account.get('server', '')
            task_acc['_clone_name'] = clone.get('name', '')
            task_acc['_clone_server'] = clone.get('server', '')
            task_acc['_clone_ref'] = clone

            run_index = base_index + clone_offset
            cname = clone.get('name', f'Clone {clone_offset+1}')
            csrv = clone.get('server', '')
            clone_label = f"{cname}" + (f" ({csrv})" if csrv else '')

            logger(f'[{email}] ━━━ Clone #{clone_offset+1}: {clone_label} — Mở cửa sổ mới, bỏ qua Đăng xuất/Đăng nhập ━━━')

            ok = auto_login_flow(
                account=task_acc,
                clone_exe=clone_exe,
                stop_event=stop_event,
                logger=logger,
                index=run_index,
                total=total_tasks,
                logout_delay=0.0,
                open_game_delay=open_game_delay,
                mode='clone',
                step_timeout=step_timeout,
                max_retries=max_retries,
                skip_login=True,
                pause_event=pause_event,
                skip_step_event=skip_step_event,
                auto_tile=auto_tile,
            )
            results[clone_offset] = ok

            if not ok and stop_event and stop_event.is_set():
                break

            if clone_offset < len(clones) - 1 and not (stop_event and stop_event.is_set()):
                num_open = len(find_tow_windows())
                inter_delay = 3.0 + (3.0 if num_open >= 2 else 0.0)
                logger(f'[{email}] ⏳ Nghỉ {inter_delay:.0f}s trước clone tiếp theo (đang có {num_open} tab game mở)...')
                delay_start = time.time()
                while time.time() - delay_start < inter_delay:
                    state = check_flow_control(email, "nghỉ trước clone tiếp theo")
                    if state in ('stop', 'skip'):
                        break
                    _native_sleep(0.2)

    return results
