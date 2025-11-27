"""
Centralized logging module for real-time-trans
Combines best practices from both codebases with robust error handling
"""
import time
import os
import sys
import traceback
from datetime import datetime

# Global flag to control debug logging
_debug_logging_enabled = True

def get_base_dir():
    """Lấy thư mục gốc - hỗ trợ cả script và exe"""
    try:
        if getattr(sys, 'frozen', False):
            # Chạy từ executable (PyInstaller)
            base_dir = os.path.dirname(sys.executable)
        else:
            # Chạy từ Python script - cần đi lên 1 level vì đang trong modules/
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.normpath(base_dir)
    except Exception:
        try:
            return os.path.normpath(os.getcwd())
        except Exception:
            # Ultimate fallback: thư mục temp
            try:
                import tempfile
                return tempfile.gettempdir()
            except Exception:
                return "."

def set_debug_logging_enabled(enabled):
    """Enable or disable debug logging."""
    global _debug_logging_enabled
    _debug_logging_enabled = enabled

def is_debug_logging_enabled():
    """Check if debug logging is currently enabled."""
    return _debug_logging_enabled

def log_debug(message):
    """Appends a timestamped message to the debug log file if logging is enabled."""
    if not _debug_logging_enabled:
        return
    
    try:
        base_dir = get_base_dir()
        debug_log_file = os.path.join(base_dir, 'translator_debug.log')
        
        # Đảm bảo thư mục tồn tại
        try:
            os.makedirs(base_dir, exist_ok=True)
        except (OSError, PermissionError):
            # Fallback về thư mục hiện tại
            try:
                base_dir = os.getcwd()
                debug_log_file = os.path.join(base_dir, 'translator_debug.log')
            except Exception:
                # Ultimate fallback: thư mục temp
                try:
                    import tempfile
                    base_dir = tempfile.gettempdir()
                    debug_log_file = os.path.join(base_dir, 'real-time-trans_debug.log')
                except Exception:
                    pass  # Complete failure
        
        try:
            with open(debug_log_file, 'a', encoding='utf-8', errors='replace') as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}: {message}\n")
                f.flush()  # Force write to disk
        except (IOError, PermissionError, OSError):
            # Fallback to stderr if available
            try:
                sys.stderr.write(f"[DEBUG LOG FAILED] {message}\n")
            except Exception:
                pass  # Last resort: ignore
    except Exception:
        # Ultimate fallback: try stderr
        try:
            sys.stderr.write(f"[CRITICAL] Debug logging failed: {message}\n")
        except Exception:
            pass  # Complete failure, ignore

def log_error(error_msg, exception=None):
    """Ghi lỗi ra file error_log.txt để debug - robust error handling cho EXE"""
    try:
        base_dir = get_base_dir()
        error_log_file = os.path.join(base_dir, "error_log.txt")
        
        # Đảm bảo thư mục tồn tại
        try:
            os.makedirs(base_dir, exist_ok=True)
        except (OSError, PermissionError) as dir_err:
            # Nếu không tạo được thư mục, fallback về thư mục hiện tại
            try:
                base_dir = os.getcwd()
                error_log_file = os.path.join(base_dir, "error_log.txt")
            except Exception:
                # Ultimate fallback: thư mục temp
                try:
                    import tempfile
                    base_dir = tempfile.gettempdir()
                    error_log_file = os.path.join(base_dir, "real-time-trans_error_log.txt")
                except Exception:
                    pass  # Complete failure
        
        # Ghi log với error handling
        try:
            with open(error_log_file, 'a', encoding='utf-8', errors='replace') as f:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"\n[{timestamp}] {error_msg}\n")
                if exception:
                    f.write(f"Exception: {str(exception)}\n")
                    try:
                        f.write(f"Traceback:\n{traceback.format_exc()}\n")
                    except Exception:
                        f.write("Traceback: (unable to format)\n")
                f.write("-" * 80 + "\n")
                f.flush()  # Force write to disk
        except (IOError, PermissionError, OSError) as file_err:
            # Nếu không ghi được file, thử ghi vào stderr (nếu có console)
            try:
                sys.stderr.write(f"[ERROR LOG FAILED] {error_msg}\n")
                if exception:
                    sys.stderr.write(f"Exception: {str(exception)}\n")
                sys.stderr.write(f"File write error: {file_err}\n")
            except Exception:
                pass  # Last resort: ignore
    except Exception as critical_err:
        # Ultimate fallback: try stderr
        try:
            sys.stderr.write(f"[CRITICAL] Error logging failed: {error_msg}\n")
            sys.stderr.write(f"Critical error: {critical_err}\n")
        except Exception:
            pass  # Complete failure, ignore

