# -*- coding: utf-8 -*-
"""
Hotkey Manager - Global keyboard shortcuts
Supports customizable hotkeys with validation
"""

import threading
from pynput import keyboard
from modules import log_error, log_debug

class HotkeyManager:
    """Quản lý hotkeys toàn cục với khả năng tùy chỉnh"""
    
    # Default hotkeys
    DEFAULT_HOTKEYS = {
        'start_stop': '<ctrl>+<alt>+s',
        'pause_resume': '<ctrl>+<alt>+p',
        'clear_history': '<ctrl>+<alt>+c',
        'toggle_overlay': '<ctrl>+<alt>+o',
        'select_region': '<ctrl>+<alt>+r',
        'toggle_lock': '<ctrl>+<alt>+l'
    }
    
    def __init__(self, callback_map=None, root=None):
        """
        Initialize hotkey manager
        
        Args:
            callback_map: Dict mapping action names to callback functions
                         {'start_stop': func, 'pause_resume': func, ...}
            root: Tkinter root window for thread-safe callbacks
        """
        self.callback_map = callback_map or {}
        self.hotkeys = self.DEFAULT_HOTKEYS.copy()
        self.listener = None
        self.active_keys = set()
        self.running = False
        self._lock = threading.Lock()
        self.root = root
        self.triggered_hotkeys = set()  # Track recently triggered hotkeys to prevent spam
        # Define modifier keys set (both left/right variants)
        self.modifier_keys = {
            keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r,
            keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt_gr,
            keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r,
            keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r
        }

    def _is_modifier(self, key):
        """Check if a key is a modifier"""
        try:
            return key in self.modifier_keys
        except Exception as e:
            log_error("Error checking if key is modifier", e)
            return False
    
    def set_hotkeys(self, hotkey_config):
        """
        Cập nhật hotkeys từ config
        
        Args:
            hotkey_config: Dict {'action': 'hotkey_string', ...}
        """
        with self._lock:
            for action, hotkey_str in hotkey_config.items():
                if action in self.DEFAULT_HOTKEYS:
                    self.hotkeys[action] = hotkey_str
    
    def get_hotkeys(self):
        """Lấy danh sách hotkeys hiện tại"""
        with self._lock:
            return self.hotkeys.copy()
    
    def register_callback(self, action, callback):
        """
        Đăng ký callback cho action
        
        Args:
            action: Tên action ('start_stop', 'pause_resume', ...)
            callback: Function được gọi khi hotkey nhấn
        """
        self.callback_map[action] = callback
    
    def parse_hotkey(self, hotkey_str):
        """
        Parse hotkey string thành set of keys
        
        Args:
            hotkey_str: String như '<ctrl>+<alt>+s' hoặc '<shift>+f1'
        
        Returns:
            Set of keyboard.Key or keyboard.KeyCode objects
        """
        keys = set()
        parts = hotkey_str.lower().replace(' ', '').split('+')
        
        # Map to both left and right variants for modifiers
        key_mapping = {
            '<ctrl>': [keyboard.Key.ctrl_l, keyboard.Key.ctrl_r, keyboard.Key.ctrl],
            '<control>': [keyboard.Key.ctrl_l, keyboard.Key.ctrl_r, keyboard.Key.ctrl],
            '<alt>': [keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt, keyboard.Key.alt_gr],
            '<shift>': [keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r],
            '<cmd>': [keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r],
            '<win>': [keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r],
        }
        
        for part in parts:
            if part in key_mapping:
                # For modifiers, we'll check if ANY variant is pressed
                # Store as tuple to mark it as "any of these"
                keys.add(('modifier', tuple(key_mapping[part])))
            else:
                # Regular key
                part_clean = part.strip('<>')
                if len(part_clean) == 1:
                    # Create KeyCode for the character
                    keys.add(keyboard.KeyCode.from_char(part_clean))
                else:
                    # Function keys, etc
                    try:
                        keys.add(getattr(keyboard.Key, part_clean))
                    except AttributeError:
                        log_error(f"Unknown key: {part_clean}", None)
        
        return keys
    
    def check_hotkey_match(self, expected_keys, active_keys):
        """
        Check if expected hotkey matches active keys
        Handles modifier key variants (left/right) and KeyCode comparison
        """
        for expected in expected_keys:
            if isinstance(expected, tuple) and expected[0] == 'modifier':
                # Check if ANY of the modifier variants is pressed
                modifier_variants = expected[1]
                if not any(mod in active_keys for mod in modifier_variants):
                    return False
            else:
                # Regular key - need to compare by char/vk
                found = False
                for active_key in active_keys:
                    if self._keys_match(expected, active_key):
                        found = True
                        break
                if not found:
                    return False
        return True
    
    def _keys_match(self, key1, key2):
        """Compare two keys, handling KeyCode char comparison"""
        # Direct equality
        if key1 == key2:
            return True
        
        # Both are KeyCodes - compare by char
        if isinstance(key1, keyboard.KeyCode) and isinstance(key2, keyboard.KeyCode):
            if key1.char and key2.char:
                return key1.char.lower() == key2.char.lower()
            # Compare by vk if no char
            if key1.vk and key2.vk:
                return key1.vk == key2.vk
        
        return False
    
    def on_press(self, key):
        """Callback khi nhấn phím"""
        if not self.running:
            return
        
        with self._lock:
            # Normalize key
            try:
                if hasattr(key, 'char') and key.char:
                    normalized_key = keyboard.KeyCode.from_char(key.char.lower())
                else:
                    # If it's a KeyCode without char but with vk (Windows), normalize to char
                    if isinstance(key, keyboard.KeyCode) and hasattr(key, 'vk') and key.vk is not None:
                        vk = key.vk
                        try:
                            if 65 <= vk <= 90:  # A-Z
                                normalized_key = keyboard.KeyCode.from_char(chr(vk).lower())
                            elif 48 <= vk <= 57:  # 0-9
                                normalized_key = keyboard.KeyCode.from_char(chr(vk))
                            else:
                                normalized_key = key
                        except Exception as e:
                            log_error("Error normalizing VK code in on_press", e)
                            normalized_key = key
                    else:
                        normalized_key = key
            except Exception as e:
                log_error("Error normalizing key in on_press", e)
                normalized_key = key
            
            self.active_keys.add(normalized_key)
            
            # Only attempt matching when a NON-modifier key was pressed (edge trigger on main key)
            if not self._is_modifier(normalized_key):
                for action, hotkey_str in self.hotkeys.items():
                    expected_keys = self.parse_hotkey(hotkey_str)
                    
                    # Check if all expected keys are pressed and not already triggered
                    if self.check_hotkey_match(expected_keys, self.active_keys) and action not in self.triggered_hotkeys:
                        # Mark as triggered to prevent spam
                        self.triggered_hotkeys.add(action)
                        
                        # Minimal log for trigger
                        log_debug(f"[Hotkeys] Triggered: {action}")
                        
                        # Execute callback
                        callback = self.callback_map.get(action)
                        if callback:
                            try:
                                # Use Tkinter's thread-safe method if root is available
                                if self.root:
                                    self.root.after(0, callback)
                                else:
                                    callback()
                            except Exception as e:
                                log_error(f"Error executing hotkey callback for {action}", e)
    
    def on_release(self, key):
        """Callback khi thả phím"""
        if not self.running:
            return
        
        with self._lock:
            # Normalize key
            try:
                if hasattr(key, 'char') and key.char:
                    normalized_key = keyboard.KeyCode.from_char(key.char.lower())
                else:
                    # If it's a KeyCode without char but with vk (Windows), normalize to char
                    if isinstance(key, keyboard.KeyCode) and hasattr(key, 'vk') and key.vk is not None:
                        vk = key.vk
                        try:
                            if 65 <= vk <= 90:  # A-Z
                                normalized_key = keyboard.KeyCode.from_char(chr(vk).lower())
                            elif 48 <= vk <= 57:  # 0-9
                                normalized_key = keyboard.KeyCode.from_char(chr(vk))
                            else:
                                normalized_key = key
                        except Exception as e:
                            log_error("Error normalizing VK code in on_release", e)
                            normalized_key = key
                    else:
                        normalized_key = key
            except Exception as e:
                log_error("Error normalizing key in on_release", e)
                normalized_key = key
            
            # Remove from active keys
            self.active_keys.discard(normalized_key)
            
            # Reset triggered hotkeys when any key is released
            self.triggered_hotkeys.clear()
    
    def start(self):
        """Bắt đầu lắng nghe hotkeys"""
        if self.running:
            return
        
        self.running = True
        self.listener = keyboard.Listener(
            on_press=self.on_press,
            on_release=self.on_release
        )
        self.listener.start()
        log_debug("[Hotkeys] Started listening")
    
    def stop(self):
        """Dừng lắng nghe hotkeys"""
        if not self.running:
            return
        
        self.running = False
        if self.listener:
            self.listener.stop()
            self.listener = None
        
        with self._lock:
            self.active_keys.clear()
        
        log_debug("[Hotkeys] Stopped listening")
    
    def validate_hotkey(self, hotkey_str):
        """
        Kiểm tra hotkey string có hợp lệ không
        
        Args:
            hotkey_str: String hotkey cần validate
        
        Returns:
            (bool, str): (valid, error_message)
        """
        try:
            parts = hotkey_str.lower().replace(' ', '').split('+')
            
            if len(parts) < 2:
                return False, "Hotkey phải có ít nhất 2 phím (ví dụ: Ctrl+S)"
            
            valid_modifiers = ['<ctrl>', '<control>', '<alt>', '<shift>', '<cmd>', '<win>']
            has_modifier = any(part in valid_modifiers for part in parts)
            
            if not has_modifier:
                return False, "Hotkey phải có ít nhất 1 phím modifier (Ctrl, Alt, Shift)"
            
            # Parse to check for errors
            self.parse_hotkey(hotkey_str)
            
            return True, ""
        
        except Exception as e:
            return False, f"Lỗi parse hotkey: {str(e)}"
    
    @staticmethod
    def format_hotkey_display(hotkey_str):
        """
        Format hotkey string để hiển thị cho người dùng
        
        Args:
            hotkey_str: '<ctrl>+<alt>+s'
        
        Returns:
            'Ctrl+Alt+S'
        """
        display_map = {
            '<ctrl>': 'Ctrl',
            '<control>': 'Ctrl',
            '<alt>': 'Alt',
            '<shift>': 'Shift',
            '<cmd>': 'Win',
            '<win>': 'Win',
        }
        
        parts = hotkey_str.replace(' ', '').split('+')
        formatted_parts = []
        
        for part in parts:
            if part in display_map:
                formatted_parts.append(display_map[part])
            else:
                # Regular key - capitalize
                clean = part.strip('<>').upper()
                formatted_parts.append(clean)
        
        return '+'.join(formatted_parts)
