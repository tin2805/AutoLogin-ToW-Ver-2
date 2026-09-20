import sys
import io
import subprocess
import importlib

# Ensure UTF-8 output on Windows console without encoding errors
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        try:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
        except Exception:
            pass

# Map PyPI package names to python import names
REQUIRED_PACKAGES = {
    "numpy": "numpy",
    "opencv-python": "cv2",
    "Pillow": "PIL",
    "pyautogui": "pyautogui",
    "pyperclip": "pyperclip",
    "pywin32": "win32gui",
    "winocr": "winocr"
}

def check_package(import_name):
    try:
        importlib.import_module(import_name)
        return True
    except ImportError:
        return False

def install_packages():
    print("=" * 60)
    print("  TALES OF WIND AUTO LOGIN - CHƯƠNG TRÌNH CÀI ĐẶT THƯ VIỆN")
    print("=" * 60)
    print(f"[+] Sử dụng Python: {sys.executable}")
    print(f"[+] Phiên bản Python: {sys.version.split()[0]}")
    print("-" * 60)

    missing = []
    print("[*] Kiểm tra các thư viện hiện tại:")
    for pkg, import_name in REQUIRED_PACKAGES.items():
        if check_package(import_name):
            print(f"  [OK] {pkg} (Đã cài đặt)")
        else:
            print(f"  [MISSING] {pkg} (Chưa cài đặt)")
            missing.append(pkg)

    if not missing:
        print("\n[!] Tất cả thư viện cần thiết đã được cài đặt đầy đủ!")
        print("=" * 60)
        return True

    print(f"\n[*] Phát hiện {len(missing)} thư viện còn thiếu: {', '.join(missing)}")
    print("[*] Đang nâng cấp pip...")
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"], check=False)
    except Exception as e:
        print(f"[!] Cảnh báo khi nâng cấp pip: {e}")

    print("\n[*] Tiến hành cài đặt các thư viện thiếu...")
    install_cmd = [sys.executable, "-m", "pip", "install"] + missing

    try:
        result = subprocess.run(install_cmd, check=True)
        if result.returncode == 0:
            print("\n[OK] Đã chạy lệnh cài đặt pip hoàn tất!")
    except subprocess.CalledProcessError as e:
        print(f"\n[!] Có lỗi xảy ra khi cài đặt qua pip: {e}")
        print("[*] Đang thử lại với mirror PyPI dự phòng...")
        try:
            subprocess.run(install_cmd + ["-i", "https://pypi.org/simple"], check=True)
        except Exception as ex:
            print(f"[ERROR] Lỗi cài đặt thư viện: {ex}")
            return False

    # Check again after installation
    print("\n" + "-" * 60)
    print("[*] Kiểm tra lại sau khi cài đặt:")
    all_ok = True
    for pkg, import_name in REQUIRED_PACKAGES.items():
        if check_package(import_name):
            print(f"  [OK] {pkg} -> Hoạt động bình thường")
        else:
            if pkg == "winocr":
                print(f"  [INFO] {pkg} -> Không bắt buộc, tool vẫn hoạt động bình thường mà không có winocr")
            else:
                print(f"  [ERROR] {pkg} -> Vẫn chưa thể nạp!")
                all_ok = False

    print("=" * 60)
    if all_ok:
        print("[SUCCESS] CÀI ĐẶT THÀNH CÔNG! Tool đã sẵn sàng sử dụng.")
    else:
        print("[WARNING] Một số thư viện chính chưa cài đặt thành công. Vui lòng kiểm tra lại kết nối mạng hoặc quyền Admin.")
    print("=" * 60)
    return all_ok

if __name__ == "__main__":
    success = install_packages()
    sys.exit(0 if success else 1)
