import os
import json
import threading
import time
import copy
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
import win32api
import win32con

import automation

CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'config.json')
ACCOUNTS_LOGIN_FILE = os.path.join(os.path.dirname(__file__), 'accounts_login.json')
ACCOUNTS_CLONE_FILE = os.path.join(os.path.dirname(__file__), 'accounts_clone.json')
ACCOUNTS_FILE = os.path.join(os.path.dirname(__file__), 'accounts.json')
OLD_CLONE_REF_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'account_clone.json')

class TowAutoApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Tales of Wind - Auto-Login & Multi-Clone Tool')
        self.geometry('1080x740')
        self.minsize(920, 600)
        self.configure(bg='#181825')
        
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.pause_event.set()
        self.skip_step_event = threading.Event()
        self.is_running = False
        self.is_paused = False
        self._hotkey_thread_running = True

        self.worker_thread = None
        self.accounts_login = []
        self.accounts_clone = []
        self.game_dir = r'C:\ToWRR'
        self.enable_logout_delay = True
        self.logout_delay = 5.0
        self.enable_open_delay = True
        self.open_delay = 5.0
        self.launch_mode = None
        
        self.load_data()
        self.setup_styles()
        self.create_widgets()
        self.refresh_table()
        self.bind_hotkeys()
        self._start_hotkey_listener()
        self.protocol('WM_DELETE_WINDOW', self._on_app_close)
        
    def setup_styles(self):
        self.style = ttk.Style(self)
        self.style.theme_use('clam')
        
        bg_dark = '#1e1e2e'
        fg_light = '#cdd6f4'
        accent_blue = '#89b4fa'
        accent_green = '#a6e3a1'
        accent_red = '#f38ba8'
        
        self.style.configure('.', background=bg_dark, foreground=fg_light, font=('Segoe UI', 10))
        self.style.configure('TFrame', background=bg_dark)
        self.style.configure('TLabelframe', background=bg_dark, foreground=accent_blue, font=('Segoe UI', 10, 'bold'))
        self.style.configure('TLabelframe.Label', background=bg_dark, foreground=accent_blue)
        
        self.style.configure('Treeview', background='#181825', foreground=fg_light, fieldbackground='#181825', rowheight=28)
        self.style.map('Treeview', background=[('selected', '#45475a')], foreground=[('selected', '#ffffff')])
        self.style.configure('Treeview.Heading', background='#313244', foreground='#cdd6f4', font=('Segoe UI', 10, 'bold'))
        
        self.style.configure('Accent.TButton', background=accent_blue, foreground='#11111b', font=('Segoe UI', 10, 'bold'), borderwidth=0)
        self.style.map('Accent.TButton', background=[('active', '#b4befe')])
        
        self.style.configure('Green.TButton', background=accent_green, foreground='#11111b', font=('Segoe UI', 11, 'bold'), borderwidth=0)
        self.style.map('Green.TButton', background=[('active', '#94e2d5')])
        
        self.style.configure('Red.TButton', background=accent_red, foreground='#11111b', font=('Segoe UI', 11, 'bold'), borderwidth=0)
        self.style.map('Red.TButton', background=[('active', '#eba0ac')])

        # Tab Notebook Styles
        self.style.configure('TNotebook', background='#181825', borderwidth=0)
        self.style.configure('TNotebook.Tab', background='#313244', foreground='#cdd6f4', padding=[24, 8], font=('Segoe UI', 10, 'bold'))
        self.style.map('TNotebook.Tab',
                       background=[('selected', '#1e1e2e'), ('active', '#45475a')],
                       foreground=[('selected', '#89b4fa'), ('active', '#ffffff')])

    def get_accounts(self, mode):
        return self.accounts_login if mode == 'login' else self.accounts_clone

    @staticmethod
    def normalize_clone(c):
        """Chuẩn hóa một clone entry: string cũ hoặc dict mới -> dict chuẩn."""
        if isinstance(c, dict):
            return {
                'name': c.get('name', 'Clone 1'),
                'server': c.get('server', ''),
                'selected': c.get('selected', True),
                'status': c.get('status', 'Sẵn sàng'),
            }
        elif isinstance(c, str):
            c_str = c.strip()
            if '(' in c_str and c_str.endswith(')'):
                idx = c_str.rfind('(')
                return {'name': c_str[:idx].strip(), 'server': c_str[idx+1:-1].strip(), 'selected': True, 'status': 'Sẵn sàng'}
            return {'name': c_str, 'server': '', 'selected': True, 'status': 'Sẵn sàng'}
        return {'name': 'Clone 1', 'server': '', 'selected': True, 'status': 'Sẵn sàng'}

    def create_widgets(self):
        # 1. Header Frame
        header = tk.Frame(self, bg='#11111b', height=60, padx=15, pady=10)
        header.pack(fill='x')
        
        title_lbl = tk.Label(header, text='⚔️ Tales of Wind Auto-Login & Multi-Clone', font=('Segoe UI', 15, 'bold'), fg='#89b4fa', bg='#11111b')
        title_lbl.pack(side='left')
        
        self.lbl_game_info = tk.Label(header, text=f'📁 Thư mục Game: {self.game_dir}', font=('Segoe UI', 10), fg='#a6adc8', bg='#11111b')
        self.lbl_game_info.pack(side='right', padx=10)
        
        btn_browse = tk.Button(header, text='📁 Chọn thư mục Game', command=self.choose_game_dir, bg='#313244', fg='#cdd6f4', relief='flat', font=('Segoe UI', 9))
        btn_browse.pack(side='right', padx=5)

        # 2. Main Split (Top: Notebook tabs, Bottom: Shared Log console)
        self.main_paned = tk.PanedWindow(self, orient='vertical', bg='#181825', sashwidth=4)
        self.main_paned.pack(fill='both', expand=True, padx=12, pady=8)
        
        # Notebook for 2 tabs
        self.notebook = ttk.Notebook(self.main_paned)
        self.main_paned.add(self.notebook, height=480)
        
        self.tab_login = tk.Frame(self.notebook, bg='#1e1e2e')
        self.tab_clone = tk.Frame(self.notebook, bg='#1e1e2e')
        
        self.notebook.add(self.tab_login, text='  🔑 Auto Login  ')
        self.notebook.add(self.tab_clone, text='  👥 Multi Clone  ')
        
        self.create_login_tab(self.tab_login)
        self.create_clone_tab(self.tab_clone)

        # 3. Bottom Log Console Frame
        bot_frame = tk.Frame(self.main_paned, bg='#11111b')
        self.main_paned.add(bot_frame, height=200)
        
        log_header = tk.Frame(bot_frame, bg='#11111b', padx=8, pady=3)
        log_header.pack(fill='x')
        tk.Label(log_header, text='📝 Nhật ký hoạt động (Logs):', font=('Segoe UI', 9, 'bold'), fg='#89b4fa', bg='#11111b').pack(side='left')
        tk.Label(
            log_header,
            text='⌨️ Phím tắt: Ctrl+X (Dừng) | Ctrl+P (Tạm dừng) | Ctrl+C (Tiếp tục) | Ctrl+S (Bỏ qua bước)',
            font=('Segoe UI', 8, 'italic'),
            fg='#fab387',
            bg='#11111b'
        ).pack(side='left', padx=15)
        tk.Button(log_header, text='Xóa log', bg='#313244', fg='#cdd6f4', relief='flat', font=('Segoe UI', 8), command=self.clear_logs).pack(side='right')
        
        self.log_text = scrolledtext.ScrolledText(bot_frame, bg='#11111b', fg='#a6adc8', font=('Consolas', 10), insertbackground='#ffffff')
        self.log_text.pack(fill='both', expand=True, padx=8, pady=(0, 6))

    def create_login_tab(self, parent):
        # Controls Bar for Auto Login
        ctrl_frame = ttk.LabelFrame(parent, text=' ⚙️ Điều khiển Đăng nhập Tự động (Auto Login) ')
        ctrl_frame.pack(fill='x', padx=8, pady=5)
        
        main_ctrl_frame = tk.Frame(ctrl_frame, bg='#1e1e2e', pady=6, padx=6)
        main_ctrl_frame.pack(fill='x')

        opts_frame = tk.Frame(main_ctrl_frame, bg='#1e1e2e')
        opts_frame.pack(side='left', fill='x', expand=True)

        btn_frame = tk.Frame(main_ctrl_frame, bg='#1e1e2e')
        btn_frame.pack(side='right')

        # Row 1: Chờ sau đăng xuất
        r1 = tk.Frame(opts_frame, bg='#1e1e2e')
        r1.pack(anchor='w', pady=2)
        self.var_delay_login = tk.BooleanVar(value=self.enable_logout_delay)
        chk_delay_login = tk.Checkbutton(
            r1, text='Chờ sau đăng xuất (chống giật CMD):',
            variable=self.var_delay_login, command=self._on_delay_toggle_login,
            bg='#1e1e2e', fg='#cdd6f4', selectcolor='#313244', activebackground='#1e1e2e'
        )
        chk_delay_login.pack(side='left', padx=3)
        
        spn_state = 'normal' if self.enable_logout_delay else 'disabled'
        self.spn_logout_delay_login = tk.Spinbox(r1, from_=1, to=30, width=3, bg='#313244', fg='#ffffff', state=spn_state)
        self.spn_logout_delay_login.delete(0, 'end')
        self.spn_logout_delay_login.insert(0, str(int(self.logout_delay)))
        self.spn_logout_delay_login.pack(side='left', padx=2)
        tk.Label(r1, text='s', bg='#1e1e2e', fg='#a6adc8').pack(side='left', padx=(0, 8))
        
        # Row 2 (ở phía dưới): Chờ sau khi mở game
        r2 = tk.Frame(opts_frame, bg='#1e1e2e')
        r2.pack(anchor='w', pady=2)
        self.var_open_delay_login = tk.BooleanVar(value=self.enable_open_delay)
        chk_open_delay_login = tk.Checkbutton(
            r2, text='Chờ sau khi mở game:',
            variable=self.var_open_delay_login, command=self._on_open_delay_toggle_login,
            bg='#1e1e2e', fg='#cdd6f4', selectcolor='#313244', activebackground='#1e1e2e'
        )
        chk_open_delay_login.pack(side='left', padx=3)

        spn_open_state = 'normal' if self.enable_open_delay else 'disabled'
        self.spn_open_delay_login = tk.Spinbox(r2, from_=1, to=30, width=3, bg='#313244', fg='#ffffff', state=spn_open_state)
        self.spn_open_delay_login.delete(0, 'end')
        self.spn_open_delay_login.insert(0, str(int(self.open_delay)))
        self.spn_open_delay_login.pack(side='left', padx=2)
        tk.Label(r2, text='s', bg='#1e1e2e', fg='#a6adc8').pack(side='left', padx=(0, 8))

        self.var_tile_login = tk.BooleanVar(value=True)
        chk_tile = tk.Checkbutton(r2, text='|  Tự xếp ngói', variable=self.var_tile_login, bg='#1e1e2e', fg='#cdd6f4', selectcolor='#313244', activebackground='#1e1e2e')
        chk_tile.pack(side='left', padx=6)
        
        self.btn_start_login = ttk.Button(btn_frame, text='▶ BẮT ĐẦU AUTO LOGIN', style='Green.TButton', command=lambda: self.start_automation(mode='login'))
        self.btn_start_login.pack(side='left', padx=5)
        
        self.btn_stop_login = ttk.Button(btn_frame, text='⏹ DỪNG LẠI', style='Red.TButton', command=self.stop_automation, state='disabled')
        self.btn_stop_login.pack(side='left', padx=5)

        # Quick Add Bar
        add_frame = tk.Frame(parent, bg='#1e1e2e', padx=8, pady=4)
        add_frame.pack(fill='x')
        
        tk.Label(add_frame, text='Email:', bg='#1e1e2e', fg='#cdd6f4').pack(side='left', padx=3)
        self.ent_email_login = tk.Entry(add_frame, width=24, bg='#313244', fg='#ffffff', insertbackground='#ffffff')
        self.ent_email_login.pack(side='left', padx=3)
        
        tk.Label(add_frame, text='Pass:', bg='#1e1e2e', fg='#cdd6f4').pack(side='left', padx=3)
        self.ent_pass_login = tk.Entry(add_frame, width=16, show='*', bg='#313244', fg='#ffffff', insertbackground='#ffffff')
        self.ent_pass_login.pack(side='left', padx=3)
        
        tk.Label(add_frame, text='Server:', bg='#1e1e2e', fg='#cdd6f4').pack(side='left', padx=3)
        self.ent_server_login = tk.Entry(add_frame, width=12, bg='#313244', fg='#ffffff', insertbackground='#ffffff')
        self.ent_server_login.pack(side='left', padx=3)

        action_frame = tk.Frame(parent, bg='#1e1e2e', padx=8, pady=2)
        action_frame.pack(fill='x')
        
        btn_add = tk.Button(action_frame, text='➕ Thêm', bg='#89b4fa', fg='#11111b', font=('Segoe UI', 9, 'bold'), relief='flat', command=lambda: self.add_single_account(mode='login'))
        btn_add.pack(side='left', padx=6)
        
        btn_batch = tk.Button(action_frame, text='📋 Nhập hàng loạt', bg='#45475a', fg='#cdd6f4', relief='flat', command=lambda: self.open_batch_dialog(mode='login'))
        btn_batch.pack(side='left', padx=4)
        
        btn_sel_all = tk.Button(action_frame, text='☑ Chọn hết', bg='#313244', fg='#a6e3a1', relief='flat', font=('Segoe UI', 8, 'bold'),
                                command=lambda: self.toggle_all(self.tree_login, 'login', force_state=True))
        btn_sel_all.pack(side='left', padx=3)
        
        btn_desel_all = tk.Button(action_frame, text='☐ Bỏ chọn', bg='#313244', fg='#cdd6f4', relief='flat', font=('Segoe UI', 8),
                                  command=lambda: self.toggle_all(self.tree_login, 'login', force_state=False))
        btn_desel_all.pack(side='left', padx=3)
        
        btn_del = tk.Button(action_frame, text='🗑️ Xóa acc đã tick [☑]', bg='#f38ba8', fg='#11111b', font=('Segoe UI', 9, 'bold'), relief='flat', padx=8, command=lambda: self.delete_checked_accounts(self.tree_login, 'login'))
        btn_del.pack(side='right', padx=4)
        
        btn_clear = tk.Button(action_frame, text='Xóa hết', bg='#45475a', fg='#cdd6f4', relief='flat', command=lambda: self.clear_all_accounts('login'))
        btn_clear.pack(side='right', padx=4)

        btn_reset_status = tk.Button(
            action_frame, text='↻ Reset trạng thái', bg='#f9e2af', fg='#11111b',
            relief='flat', command=lambda: self.reset_status('login')
        )
        btn_reset_status.pack(side='right', padx=4)

        # Accounts Treeview Table
        tbl_frame = tk.Frame(parent, bg='#1e1e2e')
        tbl_frame.pack(fill='both', expand=True, padx=8, pady=4)
        
        cols = ('check', 'id', 'email', 'password', 'server', 'status')
        self.tree_login = ttk.Treeview(tbl_frame, columns=cols, show='headings', selectmode='extended')
        self.tree_login.heading('check', text='☑ Chọn', command=lambda: self.toggle_all(self.tree_login, 'login'))
        self.tree_login.heading('id', text='#')
        self.tree_login.heading('email', text='Email / Tài khoản')
        self.tree_login.heading('password', text='Mật khẩu')
        self.tree_login.heading('server', text='Server')
        self.tree_login.heading('status', text='Trạng thái')
        
        self.tree_login.column('check', width=60, anchor='center')
        self.tree_login.column('id', width=45, anchor='center')
        self.tree_login.column('email', width=260)
        self.tree_login.column('password', width=140)
        self.tree_login.column('server', width=110, anchor='center')
        self.tree_login.column('status', width=260)
        
        self.tree_login.bind('<Button-1>', lambda e: self.on_tree_click(e, self.tree_login, 'login'))
        self.tree_login.bind('<Double-1>', lambda e: self.on_tree_double_click(e, self.tree_login, 'login'))
        self.tree_login.bind('<Button-3>', lambda e: self.on_tree_right_click(e, self.tree_login, 'login'))
        self.tree_login.bind('<space>', lambda e: self.on_tree_space(e, self.tree_login, 'login'))
        self.tree_login.bind('<Delete>', lambda e: self.on_tree_key_delete(e, self.tree_login, 'login'))
        
        sb_y = ttk.Scrollbar(tbl_frame, orient='vertical', command=self.tree_login.yview)
        self.tree_login.configure(yscrollcommand=sb_y.set)
        self.tree_login.pack(side='left', fill='both', expand=True)
        sb_y.pack(side='right', fill='y')

    def create_clone_tab(self, parent):
        # Controls Bar for Multi Clone
        ctrl_frame = ttk.LabelFrame(parent, text=' ⚙️ Điều khiển Mở Đa Tab Game (Multi Clone) ')
        ctrl_frame.pack(fill='x', padx=8, pady=5)
        
        main_ctrl_frame = tk.Frame(ctrl_frame, bg='#1e1e2e', pady=6, padx=6)
        main_ctrl_frame.pack(fill='x')

        opts_frame = tk.Frame(main_ctrl_frame, bg='#1e1e2e')
        opts_frame.pack(side='left', fill='x', expand=True)

        btn_frame = tk.Frame(main_ctrl_frame, bg='#1e1e2e')
        btn_frame.pack(side='right')

        # Row 1: Số tab & Chờ sau đăng xuất
        r1 = tk.Frame(opts_frame, bg='#1e1e2e')
        r1.pack(anchor='w', pady=2)
        tk.Label(r1, text='Số tab chạy cùng lúc:', bg='#1e1e2e', fg='#cdd6f4').pack(side='left', padx=3)
        self.spn_concurrent = tk.Spinbox(r1, from_=1, to=10, width=4, bg='#313244', fg='#ffffff')
        self.spn_concurrent.delete(0, 'end')
        self.spn_concurrent.insert(0, '1')
        self.spn_concurrent.pack(side='left', padx=3)
        
        self.var_delay_clone = tk.BooleanVar(value=self.enable_logout_delay)
        chk_delay_clone = tk.Checkbutton(
            r1, text=' |  Chờ sau đăng xuất (chống giật CMD):',
            variable=self.var_delay_clone, command=self._on_delay_toggle_clone,
            bg='#1e1e2e', fg='#cdd6f4', selectcolor='#313244', activebackground='#1e1e2e'
        )
        chk_delay_clone.pack(side='left', padx=(6, 1))
        
        spn_state_c = 'normal' if self.enable_logout_delay else 'disabled'
        self.spn_logout_delay_clone = tk.Spinbox(r1, from_=1, to=30, width=3, bg='#313244', fg='#ffffff', state=spn_state_c)
        self.spn_logout_delay_clone.delete(0, 'end')
        self.spn_logout_delay_clone.insert(0, str(int(self.logout_delay)))
        self.spn_logout_delay_clone.pack(side='left', padx=2)
        tk.Label(r1, text='s', bg='#1e1e2e', fg='#a6adc8').pack(side='left', padx=(0, 6))

        # Row 2 (ở phía dưới): Chờ sau khi mở game
        r2 = tk.Frame(opts_frame, bg='#1e1e2e')
        r2.pack(anchor='w', pady=2)
        self.var_open_delay_clone = tk.BooleanVar(value=self.enable_open_delay)
        chk_open_delay_clone = tk.Checkbutton(
            r2, text='Chờ sau khi mở game:',
            variable=self.var_open_delay_clone, command=self._on_open_delay_toggle_clone,
            bg='#1e1e2e', fg='#cdd6f4', selectcolor='#313244', activebackground='#1e1e2e'
        )
        chk_open_delay_clone.pack(side='left', padx=3)

        spn_open_state_c = 'normal' if self.enable_open_delay else 'disabled'
        self.spn_open_delay_clone = tk.Spinbox(r2, from_=1, to=30, width=3, bg='#313244', fg='#ffffff', state=spn_open_state_c)
        self.spn_open_delay_clone.delete(0, 'end')
        self.spn_open_delay_clone.insert(0, str(int(self.open_delay)))
        self.spn_open_delay_clone.pack(side='left', padx=2)
        tk.Label(r2, text='s', bg='#1e1e2e', fg='#a6adc8').pack(side='left', padx=(0, 6))

        self.var_tile_clone = tk.BooleanVar(value=True)
        chk_tile = tk.Checkbutton(r2, text='|  Tự xếp ngói', variable=self.var_tile_clone, bg='#1e1e2e', fg='#cdd6f4', selectcolor='#313244', activebackground='#1e1e2e')
        chk_tile.pack(side='left', padx=6)
        
        self.btn_start_clone = ttk.Button(btn_frame, text='▶ BẮT ĐẦU MULTI CLONE', style='Green.TButton', command=lambda: self.start_automation(mode='clone'))
        self.btn_start_clone.pack(side='left', padx=5)
        
        self.btn_stop_clone = ttk.Button(btn_frame, text='⏹ DỪNG LẠI', style='Red.TButton', command=self.stop_automation, state='disabled')
        self.btn_stop_clone.pack(side='left', padx=5)

        # Quick Add Bar
        add_frame = tk.Frame(parent, bg='#1e1e2e', padx=8, pady=4)
        add_frame.pack(fill='x')
        
        tk.Label(add_frame, text='Email:', bg='#1e1e2e', fg='#cdd6f4').pack(side='left', padx=3)
        self.ent_email_clone = tk.Entry(add_frame, width=22, bg='#313244', fg='#ffffff', insertbackground='#ffffff')
        self.ent_email_clone.pack(side='left', padx=3)
        
        tk.Label(add_frame, text='Pass:', bg='#1e1e2e', fg='#cdd6f4').pack(side='left', padx=3)
        self.ent_pass_clone = tk.Entry(add_frame, width=14, show='*', bg='#313244', fg='#ffffff', insertbackground='#ffffff')
        self.ent_pass_clone.pack(side='left', padx=3)
        
        tk.Label(add_frame, text='Clone:', bg='#1e1e2e', fg='#cdd6f4').pack(side='left', padx=3)
        self.ent_clone_clone = tk.Entry(add_frame, width=12, bg='#313244', fg='#ffffff', insertbackground='#ffffff')
        self.ent_clone_clone.pack(side='left', padx=3)
        
        tk.Label(add_frame, text='Server:', bg='#1e1e2e', fg='#cdd6f4').pack(side='left', padx=3)
        self.ent_server_clone = tk.Entry(add_frame, width=10, bg='#313244', fg='#ffffff', insertbackground='#ffffff')
        self.ent_server_clone.pack(side='left', padx=3)

        action_frame = tk.Frame(parent, bg='#1e1e2e', padx=8, pady=2)
        action_frame.pack(fill='x')
        
        btn_add = tk.Button(action_frame, text='➕ Thêm', bg='#89b4fa', fg='#11111b', font=('Segoe UI', 9, 'bold'), relief='flat', command=lambda: self.add_single_account(mode='clone'))
        btn_add.pack(side='left', padx=5)
        
        btn_batch = tk.Button(action_frame, text='📋 Nhập hàng loạt', bg='#45475a', fg='#cdd6f4', relief='flat', command=lambda: self.open_batch_dialog(mode='clone'))
        btn_batch.pack(side='left', padx=4)
        
        btn_sel_all = tk.Button(action_frame, text='☑ Chọn hết', bg='#313244', fg='#a6e3a1', relief='flat', font=('Segoe UI', 8, 'bold'),
                                command=lambda: self.toggle_all(self.tree_clone, 'clone', force_state=True))
        btn_sel_all.pack(side='left', padx=3)
        
        btn_desel_all = tk.Button(action_frame, text='☐ Bỏ chọn', bg='#313244', fg='#cdd6f4', relief='flat', font=('Segoe UI', 8),
                                  command=lambda: self.toggle_all(self.tree_clone, 'clone', force_state=False))
        btn_desel_all.pack(side='left', padx=3)
        
        btn_del = tk.Button(action_frame, text='🗑️ Xóa acc đã tick [☑]', bg='#f38ba8', fg='#11111b', font=('Segoe UI', 9, 'bold'), relief='flat', padx=8, command=lambda: self.delete_checked_accounts(self.tree_clone, 'clone'))
        btn_del.pack(side='right', padx=4)
        
        btn_clear = tk.Button(action_frame, text='Xóa hết', bg='#45475a', fg='#cdd6f4', relief='flat', command=lambda: self.clear_all_accounts('clone'))
        btn_clear.pack(side='right', padx=4)

        btn_reset_status = tk.Button(
            action_frame, text='↻ Reset trạng thái', bg='#f9e2af', fg='#11111b',
            relief='flat', command=lambda: self.reset_status('clone')
        )
        btn_reset_status.pack(side='right', padx=4)

        # Accounts Treeview Table with dedicated Clone column
        tbl_frame = tk.Frame(parent, bg='#1e1e2e')
        tbl_frame.pack(fill='both', expand=True, padx=8, pady=4)
        
        cols = ('check', 'id', 'email', 'password', 'clone', 'server', 'status')
        self.tree_clone = ttk.Treeview(tbl_frame, columns=cols, show='headings', selectmode='extended')
        self.tree_clone.heading('check', text='☑ Chọn', command=lambda: self.toggle_all(self.tree_clone, 'clone'))
        self.tree_clone.heading('id', text='#')
        self.tree_clone.heading('email', text='Email / Tài khoản')
        self.tree_clone.heading('password', text='Mật khẩu')
        self.tree_clone.heading('clone', text='Clone / Nhân vật ▼ (Nhấp để chọn)')
        self.tree_clone.heading('server', text='Server')
        self.tree_clone.heading('status', text='Trạng thái')
        
        self.tree_clone.column('check', width=55, anchor='center')
        self.tree_clone.column('id', width=40, anchor='center')
        self.tree_clone.column('email', width=220)
        self.tree_clone.column('password', width=120)
        self.tree_clone.column('clone', width=190, anchor='w')
        self.tree_clone.column('server', width=95, anchor='center')
        self.tree_clone.column('status', width=220)
        
        self.tree_clone.bind('<Button-1>', lambda e: self.on_tree_click(e, self.tree_clone, 'clone'))
        self.tree_clone.bind('<Double-1>', lambda e: self.on_tree_double_click(e, self.tree_clone, 'clone'))
        self.tree_clone.bind('<Button-3>', lambda e: self.on_tree_right_click(e, self.tree_clone, 'clone'))
        self.tree_clone.bind('<space>', lambda e: self.on_tree_space(e, self.tree_clone, 'clone'))
        self.tree_clone.bind('<Delete>', lambda e: self.on_tree_key_delete(e, self.tree_clone, 'clone'))
        
        sb_y = ttk.Scrollbar(tbl_frame, orient='vertical', command=self.tree_clone.yview)
        self.tree_clone.configure(yscrollcommand=sb_y.set)
        self.tree_clone.pack(side='left', fill='both', expand=True)
        sb_y.pack(side='right', fill='y')

    def log(self, msg):
        def _append():
            ts = time.strftime('%H:%M:%S')
            self.log_text.insert('end', f'[{ts}] {msg}\n')
            self.log_text.see('end')
        self.after(0, _append)

    def clear_logs(self):
        self.log_text.delete('1.0', 'end')

    def bind_hotkeys(self):
        """Bắt phím tắt khi cửa sổ tool đang được focus."""
        for key in ('<Control-x>', '<Control-X>'):
            self.bind_all(key, lambda e: self._on_hotkey_stop())
        for key in ('<Control-p>', '<Control-P>'):
            self.bind_all(key, lambda e: self._on_hotkey_pause())
        for key in ('<Control-c>', '<Control-C>'):
            self.bind_all(key, lambda e: self._on_hotkey_resume())
        for key in ('<Control-s>', '<Control-S>'):
            self.bind_all(key, lambda e: self._on_hotkey_skip_step())

    def _start_hotkey_listener(self):
        """Khởi động luồng nền lắng nghe phím tắt toàn hệ thống (Global Hotkeys)."""
        self._hotkey_thread = threading.Thread(target=self._hotkey_worker, daemon=True)
        self._hotkey_thread.start()

    def _hotkey_worker(self):
        keys_down = set()
        hotkey_map = {
            ord('X'): self._on_hotkey_stop,
            ord('P'): self._on_hotkey_pause,
            ord('C'): self._on_hotkey_resume,
            ord('S'): self._on_hotkey_skip_step,
        }
        while self._hotkey_thread_running:
            try:
                ctrl_down = bool(
                    (win32api.GetAsyncKeyState(win32con.VK_CONTROL) & 0x8000) or
                    (win32api.GetAsyncKeyState(win32con.VK_LCONTROL) & 0x8000) or
                    (win32api.GetAsyncKeyState(win32con.VK_RCONTROL) & 0x8000)
                )
                if ctrl_down:
                    for vk, callback in hotkey_map.items():
                        pressed = bool(win32api.GetAsyncKeyState(vk) & 0x8000)
                        if pressed:
                            if vk not in keys_down:
                                keys_down.add(vk)
                                self.after(0, callback)
                        else:
                            keys_down.discard(vk)
                else:
                    keys_down.clear()
            except Exception:
                pass
            time.sleep(0.04)

    def _on_hotkey_stop(self):
        if self.is_running:
            self.log('🛑 [Phím tắt Ctrl+X] Người dùng đã yêu cầu dừng chương trình!')
            self.stop_automation()

    def _on_hotkey_pause(self):
        if self.is_running and not self.is_paused:
            self.pause_event.clear()
            self.is_paused = True
            self.log('⏸️ [Phím tắt Ctrl+P] ĐÃ TẠM DỪNG TIẾN TRÌNH! (Nhấn Ctrl+C để tiếp tục, Ctrl+S để bỏ qua bước, Ctrl+X để dừng)')

    def _on_hotkey_resume(self):
        if self.is_running and self.is_paused:
            self.pause_event.set()
            self.is_paused = False
            self.log('▶️ [Phím tắt Ctrl+C] ĐÃ TIẾP TỤC TIẾN TRÌNH!')

    def _on_hotkey_skip_step(self):
        if self.is_running:
            self.skip_step_event.set()
            if self.is_paused:
                self.pause_event.set()
                self.is_paused = False
            self.log('⏩ [Phím tắt Ctrl+S] YÊU CẦU BỎ QUA BƯỚC HIỆN TẠI, CHUYỂN TIẾP...')

    def _on_app_close(self):
        self._hotkey_thread_running = False
        self.stop_event.set()
        self.pause_event.set()
        self.destroy()

    def _on_delay_toggle_login(self):
        enabled = self.var_delay_login.get()
        if hasattr(self, 'var_delay_clone'):
            self.var_delay_clone.set(enabled)
        state = 'normal' if enabled else 'disabled'
        if hasattr(self, 'spn_logout_delay_login'):
            self.spn_logout_delay_login.config(state=state)
        if hasattr(self, 'spn_logout_delay_clone'):
            self.spn_logout_delay_clone.config(state=state)
        self.save_data()

    def _on_delay_toggle_clone(self):
        enabled = self.var_delay_clone.get()
        if hasattr(self, 'var_delay_login'):
            self.var_delay_login.set(enabled)
        state = 'normal' if enabled else 'disabled'
        if hasattr(self, 'spn_logout_delay_login'):
            self.spn_logout_delay_login.config(state=state)
        if hasattr(self, 'spn_logout_delay_clone'):
            self.spn_logout_delay_clone.config(state=state)
        self.save_data()

    def _on_open_delay_toggle_login(self):
        enabled = self.var_open_delay_login.get()
        if hasattr(self, 'var_open_delay_clone'):
            self.var_open_delay_clone.set(enabled)
        state = 'normal' if enabled else 'disabled'
        if hasattr(self, 'spn_open_delay_login'):
            self.spn_open_delay_login.config(state=state)
        if hasattr(self, 'spn_open_delay_clone'):
            self.spn_open_delay_clone.config(state=state)
        self.save_data()

    def _on_open_delay_toggle_clone(self):
        enabled = self.var_open_delay_clone.get()
        if hasattr(self, 'var_open_delay_login'):
            self.var_open_delay_login.set(enabled)
        state = 'normal' if enabled else 'disabled'
        if hasattr(self, 'spn_open_delay_login'):
            self.spn_open_delay_login.config(state=state)
        if hasattr(self, 'spn_open_delay_clone'):
            self.spn_open_delay_clone.config(state=state)
        self.save_data()

    def load_data(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                    self.game_dir = cfg.get('game_dir', self.game_dir)
                    self.enable_logout_delay = cfg.get('enable_logout_delay', True)
                    self.logout_delay = cfg.get('logout_delay', 5.0)
                    self.enable_open_delay = cfg.get('enable_open_delay', True)
                    self.open_delay = cfg.get('open_delay', 5.0)
            except Exception:
                pass

        # Load reference clones map from account_clone.json if available
        ref_clone_map = {}
        if os.path.exists(OLD_CLONE_REF_FILE):
            try:
                with open(OLD_CLONE_REF_FILE, 'r', encoding='utf-8') as f:
                    ref_data = json.load(f)
                    for item in ref_data:
                        e = item.get('email', '').strip().lower()
                        srvs = item.get('servers', {})
                        c_list = []
                        for s_name, chars in srvs.items():
                            for ch in chars:
                                c_list.append(f"{ch} ({s_name})")
                        if e and c_list:
                            ref_clone_map[e] = c_list
            except Exception:
                pass

        # Load accounts_login
        if os.path.exists(ACCOUNTS_LOGIN_FILE):
            try:
                with open(ACCOUNTS_LOGIN_FILE, 'r', encoding='utf-8') as f:
                    self.accounts_login = json.load(f)
            except Exception:
                self.accounts_login = []
        elif os.path.exists(ACCOUNTS_FILE):
            try:
                with open(ACCOUNTS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self.accounts_login = data.get('login', [])
                    elif isinstance(data, list):
                        self.accounts_login = copy.deepcopy(data)
            except Exception:
                self.accounts_login = []
        else:
            self.accounts_login = []

        # Load accounts_clone
        if os.path.exists(ACCOUNTS_CLONE_FILE):
            try:
                with open(ACCOUNTS_CLONE_FILE, 'r', encoding='utf-8') as f:
                    self.accounts_clone = json.load(f)
            except Exception:
                self.accounts_clone = []
        elif os.path.exists(ACCOUNTS_FILE):
            try:
                with open(ACCOUNTS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self.accounts_clone = data.get('clone', [])
                    elif isinstance(data, list):
                        self.accounts_clone = copy.deepcopy(data)
            except Exception:
                self.accounts_clone = []
        else:
            self.accounts_clone = []

        # Normalize checked flag
        for a in self.accounts_login:
            if 'checked' not in a:
                a['checked'] = a.get('checked_login', True)
                
        # Normalize clone list for accounts_clone
        for a in self.accounts_clone:
            if 'checked' not in a:
                a['checked'] = a.get('checked_clone', True)
            e_lower = a.get('email', '').strip().lower()
            raw_clones = a.get('clones', [])
            # Migrate old string-list format to new dict-list format
            if raw_clones and isinstance(raw_clones[0], str):
                raw_clones = [self.normalize_clone(c) for c in raw_clones]
            elif not raw_clones:
                # Try to get from reference file
                if e_lower in ref_clone_map:
                    raw_clones = [self.normalize_clone(c) for c in ref_clone_map[e_lower]]
                else:
                    raw_clones = [
                        {'name': 'Clone 1', 'server': '', 'selected': True},
                        {'name': 'Clone 2', 'server': '', 'selected': False},
                        {'name': 'Clone 3', 'server': '', 'selected': False},
                        {'name': 'Clone 4', 'server': '', 'selected': False},
                    ]
            else:
                raw_clones = [self.normalize_clone(c) for c in raw_clones]
            a['clones'] = raw_clones
            # Remove legacy 'clone' field (single selection) — no longer needed
            a.pop('clone', None)

    def save_data(self):
        try:
            delay_val = 5.0
            enable_delay = True
            if hasattr(self, 'var_delay_login'):
                enable_delay = self.var_delay_login.get()
            elif hasattr(self, 'var_delay_clone'):
                enable_delay = self.var_delay_clone.get()

            if hasattr(self, 'spn_logout_delay_login'):
                try:
                    delay_val = float(self.spn_logout_delay_login.get())
                except Exception:
                    pass
            elif hasattr(self, 'spn_logout_delay_clone'):
                try:
                    delay_val = float(self.spn_logout_delay_clone.get())
                except Exception:
                    pass

            open_delay_val = 5.0
            enable_open_delay = True
            if hasattr(self, 'var_open_delay_login'):
                enable_open_delay = self.var_open_delay_login.get()
            elif hasattr(self, 'var_open_delay_clone'):
                enable_open_delay = self.var_open_delay_clone.get()

            if hasattr(self, 'spn_open_delay_login'):
                try:
                    open_delay_val = float(self.spn_open_delay_login.get())
                except Exception:
                    pass
            elif hasattr(self, 'spn_open_delay_clone'):
                try:
                    open_delay_val = float(self.spn_open_delay_clone.get())
                except Exception:
                    pass

            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump({
                    'game_dir': self.game_dir,
                    'enable_logout_delay': enable_delay,
                    'logout_delay': delay_val,
                    'enable_open_delay': enable_open_delay,
                    'open_delay': open_delay_val
                }, f, indent=2)
            with open(ACCOUNTS_LOGIN_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.accounts_login, f, indent=2)
            with open(ACCOUNTS_CLONE_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.accounts_clone, f, indent=2)
            with open(ACCOUNTS_FILE, 'w', encoding='utf-8') as f:
                json.dump({'login': self.accounts_login, 'clone': self.accounts_clone}, f, indent=2)
        except Exception as e:
            self.log(f'Lỗi lưu dữ liệu: {e}')

    def choose_game_dir(self):
        dir_path = filedialog.askdirectory(initialdir=self.game_dir, title='Chọn thư mục chứa Tales of Wind')
        if dir_path:
            self.game_dir = dir_path
            self.save_data()
            if hasattr(self, 'lbl_game_info'):
                self.lbl_game_info.config(text=f'📁 Thư mục Game: {self.game_dir}')
            self.log(f'Đã đặt thư mục game: {self.game_dir}')

    def refresh_table(self, mode=None):
        modes = ['login', 'clone'] if mode is None else [mode]
        for m in modes:
            tree = getattr(self, f'tree_{m}', None)
            if tree is None:
                continue
            accs = self.get_accounts(m)
            for item in tree.get_children():
                tree.delete(item)
                
            for idx, acc in enumerate(accs, 1):
                pwd_masked = '*' * len(acc.get('password', ''))
                status = acc.get('status', 'Sẵn sàng')
                check_symbol = '☑' if acc.get('checked', True) else '☐'
                
                if m == 'clone':
                    clones = acc.get('clones', [])
                    total_c = len(clones)
                    sel_clones = [c for c in clones if c.get('selected', True)]
                    sel_c = len(sel_clones)
                    if total_c == 0:
                        clone_display = '▼ (chưa có clone)'
                    elif sel_c == 0:
                        clone_display = f'▼ ☐ (không có clone nào được chọn / {total_c} clone)'
                    elif sel_c == 1:
                        c0 = sel_clones[0]
                        srv = f" ({c0['server']})" if c0.get('server') else ''
                        clone_display = f"▼ ☑ {c0['name']}{srv}"
                    elif sel_c <= 3:
                        names = ', '.join(c['name'] for c in sel_clones)
                        clone_display = f'▼ ☑ {names} ({sel_c}/{total_c})'
                    else:
                        # Nhiều hơn 3 — hiện 2 đầu + "..."
                        first2 = ', '.join(c['name'] for c in sel_clones[:2])
                        clone_display = f'▼ ☑ {first2}... +{sel_c - 2} ({sel_c}/{total_c})'
                    tree.insert('', 'end', values=(check_symbol, idx, acc.get('email', ''), pwd_masked, clone_display, acc.get('server', ''), status))
                else:
                    tree.insert('', 'end', values=(check_symbol, idx, acc.get('email', ''), pwd_masked, acc.get('server', ''), status))
        self.save_data()

    def on_tree_click(self, event, tree, mode):
        region = tree.identify_region(event.x, event.y)
        if region == 'heading':
            col = tree.identify_column(event.x)
            if col == '#1':  # 'check' column
                self.toggle_all(tree, mode)
                return
        elif region in ('cell', 'tree'):
            col = tree.identify_column(event.x)
            item = tree.identify_row(event.y)
            if not item:
                return
            if col == '#1':  # Clicked directly on checkbox cell
                self.toggle_single_check(item, tree, mode)
            elif mode == 'clone' and col == '#5':  # Clicked on Clone dropdown cell
                self.show_clone_dropdown(item, tree, event)

    def on_tree_double_click(self, event, tree, mode):
        region = tree.identify_region(event.x, event.y)
        if region in ('cell', 'tree'):
            col = tree.identify_column(event.x)
            item = tree.identify_row(event.y)
            if not item:
                return
            if col == '#1':
                self.toggle_single_check(item, tree, mode)
            elif mode == 'clone' and col == '#5':
                self.show_clone_dropdown(item, tree, event)
            else:
                self.open_edit_account_dialog(tree, item, mode)

    def on_tree_space(self, event, tree, mode):
        for item in tree.selection():
            self.toggle_single_check(item, tree, mode)

    def on_tree_right_click(self, event, tree, mode):
        item = tree.identify_row(event.y)
        if item:
            curr_sel = tree.selection()
            if item not in curr_sel:
                tree.selection_set(item)
        else:
            return

        selected_items = tree.selection()
        if not selected_items:
            return

        tab_label = 'Auto Login' if mode == 'login' else 'Multi Clone'
        acc_list = self.get_accounts(mode)
        checked_count = sum(1 for a in acc_list if a.get('checked', False))

        menu = tk.Menu(self, tearoff=0, bg='#1e1e2e', fg='#cdd6f4', activebackground='#45475a', activeforeground='#ffffff')
        menu.add_command(label=f"✏️ Chỉnh sửa tài khoản [{tab_label}]...", command=lambda: self.open_edit_account_dialog(tree, selected_items[0], mode))
        
        if mode == 'clone':
            children = tree.get_children()
            if selected_items[0] in children:
                row_idx = children.index(selected_items[0])
                if row_idx < len(self.accounts_clone):
                    cur_c = self.accounts_clone[row_idx].get('clone', 'Clone 1')
                    menu.add_command(label=f"👥 Chọn Clone cụ thể (hiện tại: {cur_c}) ▼", command=lambda: self.show_clone_dropdown(selected_items[0], tree, event))
                    
        menu.add_separator()
        menu.add_command(label=f"🗑️ Xóa tất cả acc đã tick [☑] ({checked_count} tài khoản)", command=lambda: self.delete_checked_accounts(tree, mode))
        menu.add_command(label=f"🗑️ Xóa dòng đang chọn ({len(selected_items)} tài khoản)", command=lambda: self.delete_highlighted_accounts(tree, mode))

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def show_clone_dropdown(self, item, tree, event):
        """Mở Clone Manager Dialog để quản lý danh sách clone cho tài khoản được click."""
        children = tree.get_children()
        if item not in children:
            return
        idx = children.index(item)
        if idx >= len(self.accounts_clone):
            return
        acc = self.accounts_clone[idx]
        self._open_clone_manager(idx, acc)

    def _open_clone_manager(self, acc_idx, acc):
        """Dialog quản lý clone: checkbox multi-select, chỉnh sửa tên/server inline."""
        email = acc.get('email', f'#{acc_idx+1}')
        # Ensure clones is list of dicts
        clones = [self.normalize_clone(c) for c in acc.get('clones', [])]
        if not clones:
            clones = [{'name': 'Clone 1', 'server': '', 'selected': True, 'status': 'Sẵn sàng'}]
        acc['clones'] = clones

        dlg = tk.Toplevel(self)
        dlg.title(f"👥 Quản lý Clone — {email}")
        dlg.geometry('860x460')
        dlg.minsize(720, 340)
        dlg.configure(bg='#1e1e2e')
        dlg.transient(self)
        dlg.grab_set()

        # --- Header ---
        hdr = tk.Frame(dlg, bg='#11111b', padx=12, pady=8)
        hdr.pack(fill='x')
        tk.Label(hdr, text=f'👥 Nhân vật / Clone của: {email}', font=('Segoe UI', 11, 'bold'),
                 fg='#89b4fa', bg='#11111b').pack(side='left')
        tk.Label(hdr, text='☑ = sẽ được mở khi chạy', font=('Segoe UI', 9),
                 fg='#a6adc8', bg='#11111b').pack(side='right')

        # --- Table header ---
        col_hdr = tk.Frame(dlg, bg='#313244', padx=6, pady=4)
        col_hdr.pack(fill='x', padx=10, pady=(8, 0))
        tk.Label(col_hdr, text='☑', width=3, bg='#313244', fg='#cdd6f4',
                 font=('Segoe UI', 10, 'bold')).grid(row=0, column=0, padx=(0, 4))
        tk.Label(col_hdr, text='Tên nhân vật / Clone', width=22, bg='#313244', fg='#cdd6f4',
                 font=('Segoe UI', 10, 'bold'), anchor='w').grid(row=0, column=1, padx=4)
        tk.Label(col_hdr, text='Server', width=12, bg='#313244', fg='#cdd6f4',
                 font=('Segoe UI', 10, 'bold'), anchor='w').grid(row=0, column=2, padx=4)
        tk.Label(col_hdr, text='Trạng thái', width=22, bg='#313244', fg='#fab387',
                 font=('Segoe UI', 10, 'bold'), anchor='w').grid(row=0, column=3, padx=4)
        tk.Label(col_hdr, text='📋', width=4, bg='#313244', fg='#89b4fa',
                 font=('Segoe UI', 10, 'bold'), anchor='center').grid(row=0, column=4, padx=4)
        tk.Label(col_hdr, text='🗑️', width=4, bg='#313244', fg='#f38ba8',
                 font=('Segoe UI', 10, 'bold'), anchor='center').grid(row=0, column=5, padx=4)

        # --- Scrollable list frame ---
        list_outer = tk.Frame(dlg, bg='#1e1e2e')
        list_outer.pack(fill='both', expand=True, padx=10, pady=2)

        canvas = tk.Canvas(list_outer, bg='#1e1e2e', highlightthickness=0)
        sb = ttk.Scrollbar(list_outer, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)

        list_frame = tk.Frame(canvas, bg='#1e1e2e')
        canvas_window = canvas.create_window((0, 0), window=list_frame, anchor='nw')

        def _on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox('all'))
        def _on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=event.width)
        list_frame.bind('<Configure>', _on_frame_configure)
        canvas.bind('<Configure>', _on_canvas_configure)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')
        canvas.bind('<MouseWheel>', _on_mousewheel)
        list_frame.bind('<MouseWheel>', _on_mousewheel)

        # Row widget references: (var_sel, ent_name, ent_server, lbl_status)
        row_widgets = []

        # Status color mapping
        STATUS_COLORS = {
            'Sẵn sàng':        '#a6adc8',
            'Đang đăng nhập':  '#fab387',
            '✅ Đã vào game':  '#a6e3a1',
            '❌ Lỗi đăng nhập':'#f38ba8',
            '⏹ Đã dừng':      '#cdd6f4',
        }

        def _status_color(status):
            for key, col in STATUS_COLORS.items():
                if status.startswith(key[:6]):
                    return col
            return '#a6adc8'

        def _build_rows():
            for w in list_frame.winfo_children():
                w.destroy()
            row_widgets.clear()
            for r_idx, clone in enumerate(clones):
                row_bg = '#181825' if r_idx % 2 == 0 else '#1e1e2e'
                row = tk.Frame(list_frame, bg=row_bg, pady=3, padx=4)
                row.pack(fill='x')

                # Col 0: Checkbox
                var_sel = tk.BooleanVar(value=clone.get('selected', True))
                chk = tk.Checkbutton(row, variable=var_sel, bg=row_bg,
                                     activebackground=row_bg, selectcolor='#313244',
                                     fg='#a6e3a1', font=('Segoe UI', 11))
                chk.grid(row=0, column=0, padx=(2, 4))

                # Col 1: Name entry
                ent_name = tk.Entry(row, width=22, bg='#313244', fg='#ffffff',
                                    insertbackground='#ffffff', font=('Segoe UI', 10),
                                    relief='flat', bd=3)
                ent_name.insert(0, clone.get('name', ''))
                ent_name.grid(row=0, column=1, padx=4)

                # Col 2: Server entry
                ent_srv = tk.Entry(row, width=12, bg='#313244', fg='#cce0ff',
                                   insertbackground='#ffffff', font=('Segoe UI', 10),
                                   relief='flat', bd=3)
                ent_srv.insert(0, clone.get('server', ''))
                ent_srv.grid(row=0, column=2, padx=4)

                # Col 3: Status label (read-only, colored)
                st_text = clone.get('status', 'Sẵn sàng')
                lbl_status = tk.Label(row, text=st_text, width=22, anchor='w',
                                      bg=row_bg, fg=_status_color(st_text),
                                      font=('Segoe UI', 9))
                lbl_status.grid(row=0, column=3, padx=4, sticky='w')

                # Col 4: Duplicate button
                btn_dup = tk.Button(row, text='📋', bg='#45475a', fg='#89b4fa',
                                    relief='flat', font=('Segoe UI', 9), padx=4,
                                    command=lambda ri=r_idx: _duplicate_row(ri))
                btn_dup.grid(row=0, column=4, padx=(4, 2))

                # Col 5: Delete button
                btn_del = tk.Button(row, text='🗑️', bg='#45475a', fg='#f38ba8',
                                    relief='flat', font=('Segoe UI', 9), padx=4,
                                    command=lambda ri=r_idx: _delete_row(ri))
                btn_del.grid(row=0, column=5, padx=(2, 2))

                row.bind('<MouseWheel>', _on_mousewheel)
                for w in row.winfo_children():
                    w.bind('<MouseWheel>', _on_mousewheel)

                row_widgets.append((var_sel, ent_name, ent_srv, lbl_status))

        def _delete_row(ri):
            if len(clones) <= 1:
                messagebox.showwarning('Không thể xóa', 'Tài khoản cần có ít nhất 1 clone!', parent=dlg)
                return
            del clones[ri]
            _build_rows()

        def _duplicate_row(ri):
            """Nhân đôi clone tại vị trí ri — chèn bản sao ngay sau dòng đó."""
            if ri < len(clones):
                src = clones[ri]
                new_clone = {
                    'name': src.get('name', 'Clone') + ' (copy)',
                    'server': src.get('server', ''),
                    'selected': src.get('selected', True),
                    'status': 'Sẵn sàng',
                }
                clones.insert(ri + 1, new_clone)
                _build_rows()
                canvas.update_idletasks()
                # Scroll để thấy dòng vừa nhân đôi
                canvas.yview_moveto((ri + 1) / max(len(clones), 1))

        def _add_row():
            clones.append({'name': f'Clone {len(clones)+1}', 'server': '', 'selected': True, 'status': 'Sẵn sàng'})
            _build_rows()
            canvas.update_idletasks()
            canvas.yview_moveto(1.0)

        def _select_all():
            for var, *_ in row_widgets:
                var.set(True)

        def _deselect_all():
            for var, *_ in row_widgets:
                var.set(False)

        def _read_back_and_save():
            """Read widget values back into clones list and save."""
            for r_i, (var_sel, ent_name, ent_srv, lbl_st) in enumerate(row_widgets):
                if r_i < len(clones):
                    name_val = ent_name.get().strip() or f'Clone {r_i+1}'
                    clones[r_i]['name'] = name_val
                    clones[r_i]['server'] = ent_srv.get().strip()
                    clones[r_i]['selected'] = var_sel.get()
                    # preserve existing status
            acc['clones'] = list(clones)
            acc.pop('clone', None)
            self.refresh_table('clone')
            self.save_data()
            sel_names = [c['name'] for c in clones if c.get('selected')]
            self.log(f"👥 [{email}] Đã lưu {len(clones)} clone — Đã chọn: {', '.join(sel_names) if sel_names else '(không có)'}")
            dlg.destroy()

        _build_rows()

        # --- Bottom toolbar ---
        tool_bar = tk.Frame(dlg, bg='#313244', padx=8, pady=6)
        tool_bar.pack(fill='x', side='bottom')

        tk.Button(tool_bar, text='➕ Thêm clone mới', bg='#89b4fa', fg='#11111b',
                  font=('Segoe UI', 9, 'bold'), relief='flat', padx=8,
                  command=_add_row).pack(side='left', padx=4)
        tk.Button(tool_bar, text='☑ Chọn tất cả', bg='#313244', fg='#a6e3a1',
                  relief='flat', font=('Segoe UI', 9),
                  command=_select_all).pack(side='left', padx=4)
        tk.Button(tool_bar, text='☐ Bỏ chọn hết', bg='#313244', fg='#cdd6f4',
                  relief='flat', font=('Segoe UI', 9),
                  command=_deselect_all).pack(side='left', padx=4)

        tk.Button(tool_bar, text='💾 Lưu & Đóng', bg='#a6e3a1', fg='#11111b',
                  font=('Segoe UI', 10, 'bold'), relief='flat', padx=14,
                  command=_read_back_and_save).pack(side='right', padx=4)
        tk.Button(tool_bar, text='Hủy', bg='#45475a', fg='#cdd6f4',
                  relief='flat', padx=10,
                  command=dlg.destroy).pack(side='right', padx=4)

    def open_edit_account_dialog(self, tree, item, mode='login'):
        children = tree.get_children()
        if item not in children:
            return
        idx = children.index(item)
        acc_list = self.get_accounts(mode)
        if idx >= len(acc_list):
            return
        acc = acc_list[idx]

        tab_label = 'Auto Login' if mode == 'login' else 'Multi Clone'
        dlg = tk.Toplevel(self)
        dlg.title(f"[{tab_label}] Chỉnh sửa tài khoản #{idx+1}")
        dlg_height = 320 if mode == 'clone' else 240
        dlg.geometry(f'440x{dlg_height}')
        dlg.resizable(False, False)
        dlg.configure(bg='#1e1e2e')
        dlg.transient(self)
        dlg.grab_set()

        form = tk.Frame(dlg, bg='#1e1e2e', padx=20, pady=15)
        form.pack(fill='both', expand=True)

        tk.Label(form, text='Email / Tài khoản:', bg='#1e1e2e', fg='#cdd6f4', anchor='w').grid(row=0, column=0, sticky='w', pady=6)
        ent_email = tk.Entry(form, width=28, bg='#313244', fg='#ffffff', insertbackground='#ffffff')
        ent_email.insert(0, acc.get('email', ''))
        ent_email.grid(row=0, column=1, pady=6, padx=5)

        tk.Label(form, text='Mật khẩu:', bg='#1e1e2e', fg='#cdd6f4', anchor='w').grid(row=1, column=0, sticky='w', pady=6)
        ent_pwd = tk.Entry(form, width=28, show='*', bg='#313244', fg='#ffffff', insertbackground='#ffffff')
        ent_pwd.insert(0, acc.get('password', ''))
        ent_pwd.grid(row=1, column=1, pady=6, padx=5)

        tk.Label(form, text='Server:', bg='#1e1e2e', fg='#cdd6f4', anchor='w').grid(row=2, column=0, sticky='w', pady=6)
        ent_server = tk.Entry(form, width=28, bg='#313244', fg='#ffffff', insertbackground='#ffffff')
        ent_server.insert(0, acc.get('server', ''))
        ent_server.grid(row=2, column=1, pady=6, padx=5)

        # Clone specific fields in edit dialog
        if mode == 'clone':
            clones = acc.get('clones', [])
            sel_count = sum(1 for c in clones if c.get('selected', True))
            total_count = len(clones)
            clone_summary = f'{sel_count}/{total_count} nhân vật được chọn' if total_count else '(chưa có clone)'

            tk.Label(form, text='Nhân vật / Clone:', bg='#1e1e2e', fg='#89b4fa',
                     font=('Segoe UI', 9, 'bold'), anchor='w').grid(row=3, column=0, sticky='w', pady=6)
            lbl_clone_info = tk.Label(form, text=clone_summary, bg='#313244', fg='#a6e3a1',
                                      font=('Segoe UI', 9), relief='flat', padx=8, pady=4, anchor='w', width=26)
            lbl_clone_info.grid(row=3, column=1, pady=6, padx=5, sticky='ew')

            btn_manage = tk.Button(form, text='⚙️ Mở Clone Manager...', bg='#45475a', fg='#89b4fa',
                                   relief='flat', font=('Segoe UI', 9),
                                   command=lambda: [dlg.destroy(), self._open_clone_manager(idx, acc)])
            btn_manage.grid(row=4, column=0, columnspan=2, pady=4, padx=5, sticky='ew')

        btn_box = tk.Frame(dlg, bg='#1e1e2e', pady=10)
        btn_box.pack(fill='x')

        def on_save():
            new_email = ent_email.get().strip()
            new_pwd = ent_pwd.get().strip()
            if not new_email or not new_pwd:
                messagebox.showwarning('Cảnh báo', 'Email và mật khẩu không được để trống!', parent=dlg)
                return
            acc['email'] = new_email
            acc['password'] = new_pwd
            acc['server'] = ent_server.get().strip()
            # clones are managed separately via Clone Manager — no change here

            self.refresh_table(mode)
            self.log(f"[{tab_label}] Đã cập nhật thông tin tài khoản: {new_email}")
            dlg.destroy()

        btn_save = tk.Button(btn_box, text='💾 Lưu thay đổi', bg='#a6e3a1', fg='#11111b', font=('Segoe UI', 9, 'bold'), relief='flat', padx=12, pady=4, command=on_save)
        btn_save.pack(side='right', padx=(5, 20))

        btn_cancel = tk.Button(btn_box, text='Hủy', bg='#45475a', fg='#cdd6f4', relief='flat', padx=10, pady=4, command=dlg.destroy)
        btn_cancel.pack(side='right', padx=5)

    def toggle_single_check(self, item, tree, mode):
        acc_list = self.get_accounts(mode)
        children = tree.get_children()
        if item in children:
            idx = children.index(item)
            if idx < len(acc_list):
                current = acc_list[idx].get('checked', True)
                acc_list[idx]['checked'] = not current
                vals = list(tree.item(item)['values'])
                vals[0] = '☑' if acc_list[idx]['checked'] else '☐'
                tree.item(item, values=vals)
                self.save_data()

    def toggle_all(self, tree, mode, force_state=None):
        acc_list = self.get_accounts(mode)
        if force_state is None:
            all_checked = all(acc.get('checked', True) for acc in acc_list) if acc_list else False
            new_state = not all_checked
        else:
            new_state = force_state
            
        for acc in acc_list:
            acc['checked'] = new_state
            
        children = tree.get_children()
        for item in children:
            vals = list(tree.item(item)['values'])
            vals[0] = '☑' if new_state else '☐'
            tree.item(item, values=vals)
        self.save_data()

    def add_single_account(self, mode='login'):
        tab_label = 'Auto Login' if mode == 'login' else 'Multi Clone'
        clone_val = 'Clone 1'
        if mode == 'clone':
            email = self.ent_email_clone.get().strip() if hasattr(self, 'ent_email_clone') else ''
            pwd = self.ent_pass_clone.get().strip() if hasattr(self, 'ent_pass_clone') else ''
            server = self.ent_server_clone.get().strip() if hasattr(self, 'ent_server_clone') else ''
            custom_clone = self.ent_clone_clone.get().strip() if hasattr(self, 'ent_clone_clone') else ''
            if custom_clone:
                clone_val = custom_clone
        else:
            email = self.ent_email_login.get().strip() if hasattr(self, 'ent_email_login') else ''
            pwd = self.ent_pass_login.get().strip() if hasattr(self, 'ent_pass_login') else ''
            server = self.ent_server_login.get().strip() if hasattr(self, 'ent_server_login') else ''

        if not email or not pwd:
            messagebox.showwarning('Thiếu thông tin', 'Vui lòng nhập đầy đủ Email và Mật khẩu!')
            return
            
        new_acc = {
            'email': email,
            'password': pwd,
            'server': server,
            'checked': True,
            'status': 'Sẵn sàng'
        }
        if mode == 'clone':
            # Build initial clones list from the quick-add Clone field
            clone_name = self.ent_clone_clone.get().strip() if hasattr(self, 'ent_clone_clone') else ''
            initial_server = server  # use server field as clone server too
            if clone_name:
                new_acc['clones'] = [{'name': clone_name, 'server': initial_server, 'selected': True}]
            else:
                new_acc['clones'] = [
                    {'name': 'Clone 1', 'server': '', 'selected': True},
                    {'name': 'Clone 2', 'server': '', 'selected': False},
                    {'name': 'Clone 3', 'server': '', 'selected': False},
                ]
            
        acc_list = self.get_accounts(mode)
        acc_list.append(new_acc)
        
        if mode == 'clone' and hasattr(self, 'ent_email_clone'):
            self.ent_email_clone.delete(0, 'end')
            self.ent_pass_clone.delete(0, 'end')
            if hasattr(self, 'ent_clone_clone'): self.ent_clone_clone.delete(0, 'end')
            self.ent_server_clone.delete(0, 'end')
        elif mode == 'login' and hasattr(self, 'ent_email_login'):
            self.ent_email_login.delete(0, 'end')
            self.ent_pass_login.delete(0, 'end')
            self.ent_server_login.delete(0, 'end')

        self.refresh_table(mode)
        self.log(f'[{tab_label}] Đã thêm tài khoản: {email}')

    def on_tree_key_delete(self, event, tree, mode):
        acc_list = self.get_accounts(mode)
        checked_indices = [i for i, a in enumerate(acc_list) if a.get('checked', False)]
        selected_items = list(tree.selection())

        if checked_indices and (len(checked_indices) < len(acc_list) or not selected_items):
            self.delete_checked_accounts(tree, mode)
        elif selected_items:
            self.delete_highlighted_accounts(tree, mode)
        else:
            self.delete_checked_accounts(tree, mode)

    def delete_checked_accounts(self, tree=None, mode=None):
        if mode is None:
            mode = 'clone' if tree == getattr(self, 'tree_clone', None) else 'login'
        if tree is None:
            tree = getattr(self, f'tree_{mode}')

        acc_list = self.get_accounts(mode)
        tab_label = 'Auto Login' if mode == 'login' else 'Multi Clone'

        checked_indices = [i for i, acc in enumerate(acc_list) if acc.get('checked', False)]

        if not checked_indices:
            messagebox.showinfo(
                'Chưa có tài khoản nào được tick',
                f'[{tab_label}] Hiện chưa có tài khoản nào được tick chọn [☑]!\n\n'
                f'Hướng dẫn xóa theo checkbox:\n'
                f'1. Bấm nút "☐ Bỏ chọn" để bỏ tick toàn bộ.\n'
                f'2. Tick [☑] vào các tài khoản bạn muốn xóa.\n'
                f'3. Bấm nút "🗑️ Xóa acc đã tick [☑]".'
            )
            return

        count = len(checked_indices)
        emails = [acc_list[i].get('email', '') for i in checked_indices]
        sample_list = '\n'.join([f"  • {e}" for e in emails[:6]])
        if count > 6:
            sample_list += f"\n  ... và {count - 6} tài khoản khác"

        confirm_msg = (
            f"Bạn có chắc chắn muốn XÓA {count} tài khoản ĐÃ TICK CHỌN [☑] khỏi danh sách [{tab_label}]?\n\n"
            f"Danh sách tài khoản sẽ bị xóa ({count} tài khoản):\n"
            f"{sample_list}\n\n"
            f"Lưu ý: Hành động này không thể hoàn tác!"
        )

        if not messagebox.askyesno(f'Xác nhận xóa {count} tài khoản [☑]', confirm_msg, icon='warning'):
            return

        for idx in sorted(checked_indices, reverse=True):
            del acc_list[idx]

        self.refresh_table(mode)
        self.save_data()
        log_sample = ', '.join(emails[:3]) + ('...' if count > 3 else '')
        self.log(f'🗑️ [{tab_label}] Đã xóa thành công {count} tài khoản được tick chọn [☑]: {log_sample}')

    def delete_highlighted_accounts(self, tree=None, mode=None):
        if mode is None:
            mode = 'clone' if tree == getattr(self, 'tree_clone', None) else 'login'
        if tree is None:
            tree = getattr(self, f'tree_{mode}')

        selected = list(tree.selection())
        if not selected:
            messagebox.showinfo('Chưa chọn dòng', 'Vui lòng bấm chọn dòng tài khoản bạn muốn xóa!')
            return

        acc_list = self.get_accounts(mode)
        tab_label = 'Auto Login' if mode == 'login' else 'Multi Clone'
        count = len(selected)

        indices = [tree.index(item) for item in selected if item in tree.get_children()]
        indices.sort(reverse=True)
        deleted_emails = [acc_list[i].get('email', '') for i in indices if i < len(acc_list)]

        if not messagebox.askyesno('Xác nhận xóa dòng', f'Bạn có chắc chắn muốn xóa {count} tài khoản đang bôi đen khỏi danh sách [{tab_label}]?'):
            return

        for idx in indices:
            if idx < len(acc_list):
                del acc_list[idx]

        self.refresh_table(mode)
        self.save_data()
        log_str = ', '.join(deleted_emails[:3]) + ('...' if len(deleted_emails) > 3 else '')
        self.log(f'🗑️ [{tab_label}] Đã xóa thành công {count} tài khoản bôi đen: {log_str}')

    def delete_selected_accounts(self, tree=None, mode=None):
        if mode is None:
            mode = 'clone' if tree == getattr(self, 'tree_clone', None) else 'login'
        if tree is None:
            tree = getattr(self, f'tree_{mode}')

        acc_list = self.get_accounts(mode)
        checked_indices = [i for i, acc in enumerate(acc_list) if acc.get('checked', False)]
        if checked_indices:
            self.delete_checked_accounts(tree, mode)
        else:
            self.delete_highlighted_accounts(tree, mode)

    def clear_all_accounts(self, mode='login'):
        acc_list = self.get_accounts(mode)
        if not acc_list:
            return
        tab_label = 'Auto Login' if mode == 'login' else 'Multi Clone'
        if messagebox.askyesno('Xác nhận', f'Bạn có chắc chắn muốn xóa tất cả tài khoản trong danh sách [{tab_label}]?'):
            acc_list.clear()
            self.refresh_table(mode)
            self.log(f'Đã xóa toàn bộ tài khoản trong danh sách [{tab_label}].')

    def open_batch_dialog(self, mode='login'):
        tab_label = 'Auto Login' if mode == 'login' else 'Multi Clone'
        dlg = tk.Toplevel(self)
        dlg.title(f'Nhập danh sách tài khoản hàng loạt - Tab {tab_label}')
        dlg.geometry('600x480')
        dlg.minsize(500, 360)
        dlg.configure(bg='#1e1e2e')
        dlg.transient(self)
        dlg.grab_set()
        
        header_frame = tk.Frame(dlg, bg='#1e1e2e', padx=12, pady=6)
        header_frame.pack(side='top', fill='x')
        tk.Label(header_frame, text=f'📋 Dán danh sách tài khoản cho [{tab_label}] (mỗi dòng một tài khoản):', font=('Segoe UI', 10, 'bold'), fg='#89b4fa', bg='#1e1e2e').pack(anchor='w')
        if mode == 'clone':
            tk.Label(header_frame, text='Định dạng: email|pass  hoặc  email|pass|Clone1,Clone2,Clone3  hoặc  email|pass|Clone1,Clone2|Server', font=('Segoe UI', 9), fg='#a6adc8', bg='#1e1e2e').pack(anchor='w', pady=(2, 0))
        else:
            tk.Label(header_frame, text='Định dạng: email|pass hoặc email|pass|server', font=('Segoe UI', 9), fg='#a6adc8', bg='#1e1e2e').pack(anchor='w', pady=(2, 0))
        
        btn_frame = tk.Frame(dlg, bg='#1e1e2e', pady=10, padx=12)
        btn_frame.pack(side='bottom', fill='x')
        
        opt_frame = tk.Frame(dlg, bg='#1e1e2e', padx=12, pady=4)
        opt_frame.pack(side='bottom', fill='x')
        
        mode_var = tk.StringVar(value='append')
        rb_append = tk.Radiobutton(opt_frame, text='Thêm tiếp vào danh sách hiện tại', variable=mode_var, value='append',
                                   bg='#1e1e2e', fg='#cdd6f4', selectcolor='#313244', activebackground='#1e1e2e', font=('Segoe UI', 9))
        rb_append.pack(side='left', padx=(0, 15))
        rb_replace = tk.Radiobutton(opt_frame, text='Ghi đè (thay thế toàn bộ danh sách cũ)', variable=mode_var, value='replace',
                                    bg='#1e1e2e', fg='#cdd6f4', selectcolor='#313244', activebackground='#1e1e2e', font=('Segoe UI', 9))
        rb_replace.pack(side='left')
        
        txt = scrolledtext.ScrolledText(dlg, bg='#11111b', fg='#ffffff', font=('Consolas', 10), insertbackground='#ffffff')
        txt.pack(side='top', fill='both', expand=True, padx=12, pady=6)
        
        acc_list = self.get_accounts(mode)
        def load_current():
            txt.delete('1.0', 'end')
            lines = []
            for acc in acc_list:
                srv = acc.get('server', '')
                if mode == 'clone':
                    # Đọc từ clones[] dict (format mới), ghép tên clone đã chọn bằng dấu phẩy
                    clones_list = acc.get('clones', [])
                    sel_clones = [c for c in clones_list if c.get('selected', True)]
                    if not sel_clones:
                        sel_clones = clones_list  # fallback: tất cả
                    clone_names = ','.join(c.get('name', 'Clone 1') for c in sel_clones)
                    if not clone_names:
                        clone_names = 'Clone 1'
                    # Server: ưu tiên server của clone đầu, fallback sang server account
                    clone_srv = sel_clones[0].get('server', '') if sel_clones else ''
                    use_srv = clone_srv or srv
                    if use_srv:
                        lines.append(f"{acc.get('email', '')}|{acc.get('password', '')}|{clone_names}|{use_srv}")
                    else:
                        lines.append(f"{acc.get('email', '')}|{acc.get('password', '')}|{clone_names}")
                else:
                    if srv:
                        lines.append(f"{acc.get('email', '')}|{acc.get('password', '')}|{srv}")
                    else:
                        lines.append(f"{acc.get('email', '')}|{acc.get('password', '')}")
            txt.insert('end', '\n'.join(lines))
            
        btn_load = tk.Button(btn_frame, text='📄 Nạp danh sách hiện có', bg='#313244', fg='#cdd6f4',
                             relief='flat', font=('Segoe UI', 9), padx=8, pady=4, command=load_current)
        btn_load.pack(side='left')
        
        def do_import():
            lines = txt.get('1.0', 'end').splitlines()
            new_list = []
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                parts = None
                for delim in ['|', '\t']:
                    if delim in line:
                        parts = line.split(delim)
                        break
                if not parts:
                    continue
                email = parts[0].strip()
                pwd = parts[1].strip() if len(parts) > 1 else ''

                if mode == 'clone':
                    # Format: email|pass hoặc email|pass|Clone1,Clone2 hoặc email|pass|Clone1,Clone2|Server
                    if len(parts) >= 4:
                        raw_clones_str = parts[2].strip()
                        server = parts[3].strip()
                    elif len(parts) == 3:
                        raw_clones_str = parts[2].strip()
                        server = ''
                    else:
                        raw_clones_str = ''
                        server = ''

                    # Parse danh sách clone từ chuỗi (phân cách bởi dấu phẩy)
                    if raw_clones_str:
                        clone_names = [n.strip() for n in raw_clones_str.split(',') if n.strip()]
                    else:
                        clone_names = ['Clone 1', 'Clone 2', 'Clone 3']

                    # Tạo clones list dạng dict chuẩn
                    clones_dicts = [
                        {'name': cname, 'server': server, 'selected': True, 'status': 'Sẵn sàng'}
                        for cname in clone_names
                    ]

                    if email and pwd:
                        new_list.append({
                            'email': email,
                            'password': pwd,
                            'server': server,
                            'clones': clones_dicts,
                            'checked': True,
                            'status': 'Sẵn sàng'
                        })
                else:
                    server = parts[2].strip() if len(parts) > 2 else ''
                    if email and pwd:
                        new_list.append({
                            'email': email,
                            'password': pwd,
                            'server': server,
                            'checked': True,
                            'status': 'Sẵn sàng'
                        })

            if not new_list:
                messagebox.showwarning('Trống', 'Không có tài khoản hợp lệ nào để lưu!\nĐịnh dạng chuẩn: email|pass hoặc email|pass|server', parent=dlg)
                return
                
            if mode_var.get() == 'replace':
                if mode == 'clone':
                    self.accounts_clone = new_list
                else:
                    self.accounts_login = new_list
            else:
                if mode == 'clone':
                    self.accounts_clone.extend(new_list)
                else:
                    self.accounts_login.extend(new_list)
                
            self.refresh_table(mode)
            self.log(f'✅ [{tab_label}] Đã lưu thành công {len(new_list)} tài khoản vào danh sách!')
            dlg.destroy()
            messagebox.showinfo('Thành công', f'[{tab_label}] Đã xác nhận và lưu thành công {len(new_list)} tài khoản!')
            
        btn_save = tk.Button(btn_frame, text='💾 Xác nhận & Lưu danh sách', bg='#a6e3a1', fg='#11111b',
                             font=('Segoe UI', 10, 'bold'), relief='flat', padx=14, pady=5, command=do_import)
        btn_save.pack(side='right', padx=4)
        
        btn_cancel = tk.Button(btn_frame, text='Hủy bỏ', bg='#45475a', fg='#cdd6f4',
                               relief='flat', font=('Segoe UI', 9), padx=10, pady=5, command=dlg.destroy)
        btn_cancel.pack(side='right', padx=4)

    def update_account_status(self, index, status_text, mode='login'):
        acc_list = self.get_accounts(mode)
        if index < len(acc_list):
            acc_list[index]['status'] = status_text
            self.save_data()
        def _upd():
            tree = getattr(self, f'tree_{mode}', None)
            if tree:
                children = tree.get_children()
                if index < len(children):
                    vals = list(tree.item(children[index])['values'])
                    status_col_idx = 6 if mode == 'clone' else 5
                    if len(vals) > status_col_idx:
                        vals[status_col_idx] = status_text
                        tree.item(children[index], values=vals)
        self.after(0, _upd)

    def reset_status(self, mode='login'):
        """Đặt lại status độc lập cho toàn bộ danh sách của một tab."""
        acc_list = self.get_accounts(mode)
        if not acc_list:
            return
        tab_label = 'Auto Login' if mode == 'login' else 'Multi Clone'
        if not messagebox.askyesno(
            'Reset trạng thái',
            f'Đặt lại trạng thái của toàn bộ account trong tab {tab_label}?'
        ):
            return

        for account in acc_list:
            account['status'] = 'Sẵn sàng'
            if mode == 'clone':
                for clone in account.get('clones', []):
                    clone['status'] = 'Sẵn sàng'

        self.save_data()
        self.refresh_table(mode)
        self.log(f'↻ [{tab_label}] Đã reset trạng thái account' + (' và clone.' if mode == 'clone' else '.'))

    def choose_launch_mode(self, tab_mode):
        """Hiển thị popup chọn chế độ khởi chạy trước khi bắt đầu automation."""
        dlg = tk.Toplevel(self)
        dlg.title('Xác nhận chế độ khởi chạy')
        dlg.geometry('430x235')
        dlg.resizable(False, False)
        dlg.configure(bg='#1e1e2e')
        dlg.transient(self)

        self.update_idletasks()
        app_x = self.winfo_rootx()
        app_y = self.winfo_rooty()
        app_w = self.winfo_width()
        app_h = self.winfo_height()
        popup_w = 430
        popup_h = 235
        popup_x = app_x + max((app_w - popup_w) // 2, 0)
        popup_y = app_y + max((app_h - popup_h) // 2, 0)
        dlg.geometry(f'{popup_w}x{popup_h}+{popup_x}+{popup_y}')
        dlg.grab_set()

        selected_mode = tk.StringVar(value='safe')
        tab_label = 'Auto Login' if tab_mode == 'login' else 'Multi Clone'

        tk.Label(
            dlg,
            text=f'Chọn chế độ khởi chạy cho [{tab_label}]',
            bg='#1e1e2e',
            fg='#89b4fa',
            font=('Segoe UI', 12, 'bold'),
        ).pack(anchor='w', padx=20, pady=(18, 10))

        options = tk.Frame(dlg, bg='#1e1e2e')
        options.pack(fill='x', padx=20)
        tk.Radiobutton(
            options,
            text='Safe Mode',
            variable=selected_mode,
            value='safe',
            bg='#1e1e2e',
            fg='#a6e3a1',
            selectcolor='#313244',
            activebackground='#1e1e2e',
            activeforeground='#a6e3a1',
            font=('Segoe UI', 10, 'bold'),
        ).pack(anchor='w', pady=4)
        tk.Radiobutton(
            options,
            text='Fast Mode',
            variable=selected_mode,
            value='fast',
            bg='#1e1e2e',
            fg='#fab387',
            selectcolor='#313244',
            activebackground='#1e1e2e',
            activeforeground='#fab387',
            font=('Segoe UI', 10, 'bold'),
        ).pack(anchor='w', pady=4)

        result = {'confirmed': False, 'mode': None}

        def confirm():
            result['confirmed'] = True
            result['mode'] = selected_mode.get()
            dlg.destroy()

        def cancel():
            dlg.destroy()

        buttons = tk.Frame(dlg, bg='#1e1e2e')
        buttons.pack(side='bottom', fill='x', padx=20, pady=16)
        tk.Button(
            buttons,
            text='Hủy',
            command=cancel,
            bg='#45475a',
            fg='#cdd6f4',
            relief='flat',
            padx=12,
        ).pack(side='right', padx=(6, 0))
        tk.Button(
            buttons,
            text='Xác nhận khởi chạy',
            command=confirm,
            bg='#a6e3a1',
            fg='#11111b',
            font=('Segoe UI', 9, 'bold'),
            relief='flat',
            padx=12,
        ).pack(side='right')

        dlg.protocol('WM_DELETE_WINDOW', cancel)
        self.wait_window(dlg)
        if result['confirmed']:
            self.launch_mode = result['mode']
            mode_label = 'Safe Mode' if result['mode'] == 'safe' else 'Fast Mode'
            self.log(f'[{tab_label}] Đã chọn chế độ khởi chạy: {mode_label}')
        return result['confirmed']

    def start_automation(self, mode='login'):
        acc_list = self.get_accounts(mode)
        if not acc_list:
            tab_label = 'Auto Login' if mode == 'login' else 'Multi Clone'
            messagebox.showwarning('Chưa có tài khoản', f'Danh sách tài khoản [{tab_label}] đang trống!\nVui lòng thêm ít nhất một tài khoản trước khi bắt đầu!')
            return
            
        game_exe = os.path.join(self.game_dir, 'ToW.exe')
        if not os.path.exists(game_exe):
            messagebox.showerror('Không tìm thấy Game', f'Không tìm thấy file ToW.exe trong thư mục:\n{self.game_dir}\n\nVui lòng bấm nút "📁 Chọn thư mục Game" để chỉ đúng nơi cài game!')
            return

        if not self.choose_launch_mode(mode):
            return

        if mode == 'clone':
            if hasattr(self, 'btn_start_clone'): self.btn_start_clone.config(state='disabled')
            if hasattr(self, 'btn_stop_clone'): self.btn_stop_clone.config(state='normal')
        else:
            if hasattr(self, 'btn_start_login'): self.btn_start_login.config(state='disabled')
            if hasattr(self, 'btn_stop_login'): self.btn_stop_login.config(state='normal')
            
        self.stop_event.clear()
        self.pause_event.set()
        self.skip_step_event.clear()
        self.is_running = True
        self.is_paused = False
        
        self.worker_thread = threading.Thread(target=self._run_automation_worker, args=(mode,), daemon=True)
        self.worker_thread.start()

    def stop_automation(self):
        self.log('🛑 Đang yêu cầu dừng toàn bộ tiến trình...')
        self.stop_event.set()
        self.pause_event.set()
        self.skip_step_event.set()
        self.is_paused = False
        if hasattr(self, 'btn_stop_login'): self.btn_stop_login.config(state='disabled')
        if hasattr(self, 'btn_stop_clone'): self.btn_stop_clone.config(state='disabled')

    def _run_automation_worker(self, mode='login'):
        tab_name = 'AUTO LOGIN' if mode == 'login' else 'MULTI CLONE'
        fast_mode = self.launch_mode == 'fast'
        automation.set_fast_mode(fast_mode)
        mode_label = 'Fast Mode' if fast_mode else 'Safe Mode'
        self.log(f'⚙️ [{tab_name}] Chế độ khởi chạy: {mode_label}')
        self.log(f'🚀 BẮT ĐẦU TIẾN TRÌNH [{tab_name}]...')
        game_exe = os.path.join(self.game_dir, 'ToW.exe')
        if not os.path.exists(game_exe):
            self.log(f'❌ Không tìm thấy file ToW.exe trong {self.game_dir}!')
            self.is_running = False
            self.is_paused = False
            self.pause_event.set()
            def _reset():
                if hasattr(self, 'btn_start_login'): self.btn_start_login.config(state='normal')
                if hasattr(self, 'btn_start_clone'): self.btn_start_clone.config(state='normal')
                if hasattr(self, 'btn_stop_login'): self.btn_stop_login.config(state='disabled')
                if hasattr(self, 'btn_stop_clone'): self.btn_stop_clone.config(state='disabled')
            self.after(0, _reset)
            return

        if mode == 'clone':
            try:
                concurrency = int(self.spn_concurrent.get())
            except Exception:
                concurrency = 1
            if hasattr(self, 'var_delay_clone') and not self.var_delay_clone.get():
                logout_delay = 0.0
            else:
                try:
                    logout_delay = float(self.spn_logout_delay_clone.get())
                except Exception:
                    logout_delay = 5.0

            if hasattr(self, 'var_open_delay_clone') and not self.var_open_delay_clone.get():
                open_game_delay = 0.0
            else:
                try:
                    open_game_delay = float(self.spn_open_delay_clone.get())
                except Exception:
                    open_game_delay = 5.0
            auto_tile = self.var_tile_clone.get() if hasattr(self, 'var_tile_clone') else True
        else:
            concurrency = 1
            if hasattr(self, 'var_delay_login') and not self.var_delay_login.get():
                logout_delay = 0.0
            else:
                try:
                    logout_delay = float(self.spn_logout_delay_login.get())
                except Exception:
                    logout_delay = 5.0

            if hasattr(self, 'var_open_delay_login') and not self.var_open_delay_login.get():
                open_game_delay = 0.0
            else:
                try:
                    open_game_delay = float(self.spn_open_delay_login.get())
                except Exception:
                    open_game_delay = 5.0
            auto_tile = self.var_tile_login.get() if hasattr(self, 'var_tile_login') else True

        acc_list = self.get_accounts(mode)
        checked_indices = [i for i, acc in enumerate(acc_list) if acc.get('checked', False)]

        if checked_indices:
            base_items = [(i, acc_list[i]) for i in checked_indices]
            self.log(f'🎯 [{tab_name}] Đã tick chọn {len(base_items)} tài khoản.')
        else:
            base_items = list(enumerate(acc_list))
            self.log(f'📋 [{tab_name}] Không tick chọn -> Mở toàn bộ {len(base_items)} tài khoản.')

        # For clone mode: grouped per-account logic
        # Thứ tự: đăng xuất → login gmail1 → clone1 → clone2 → ... → đăng xuất → login gmail2 → ...
        if mode == 'clone':
            # Build per-account groups with selected clones
            acc_groups = []  # [(orig_idx, acc, [selected_clones])]
            total_tasks = 0
            for orig_idx, acc in base_items:
                normalized = [self.normalize_clone(c) for c in acc.get('clones', [])]
                acc['clones'] = normalized
                selected = [c for c in normalized if c.get('selected', True)]
                if not selected:
                    selected = normalized  # fallback: all clones
                acc_groups.append((orig_idx, acc, selected))
                total_tasks += len(selected)

            self.log(f'👥 [{tab_name}] {len(acc_groups)} tài khoản — tổng {total_tasks} clone sẽ được mở.')
            self.log(f'📋 Thứ tự: đăng xuất → gmail1 → clone1 → clone2 → ... → đăng xuất → gmail2 → ...')

            base_run_idx = 0
            for grp_idx, (orig_idx, acc, selected_clones) in enumerate(acc_groups):
                if self.stop_event.is_set():
                    break

                email_label = acc.get('email', f'#{orig_idx+1}')
                clone_names = ', '.join(c.get('name', '?') for c in selected_clones)
                self.log(f'━━━ [{tab_name}] Tài khoản #{grp_idx+1}/{len(acc_groups)}: {email_label} | Clones: [{clone_names}] ━━━')

                # Mark all clones as "running"
                for c in selected_clones:
                    c['status'] = 'Đang đăng nhập...'
                self.update_account_status(orig_idx, f'Đang đăng nhập... ({len(selected_clones)} clone)', mode)

                # Call grouped flow: 1 login → N clones
                results = automation.auto_login_flow_grouped(
                    account=acc,
                    clones=selected_clones,
                    clone_exe=game_exe,
                    stop_event=self.stop_event,
                    logger=self.log,
                    base_index=base_run_idx,
                    total_tasks=total_tasks,
                    logout_delay=logout_delay,
                    open_game_delay=open_game_delay,
                    step_timeout=30.0,
                    max_retries=2,
                    pause_event=self.pause_event,
                    skip_step_event=self.skip_step_event,
                    auto_tile=auto_tile,
                    concurrency=concurrency,
                )

                # Write status back to each clone dict
                for c, ok in zip(selected_clones, results):
                    if ok:
                        c['status'] = '✅ Đã vào game'
                    elif c.get('status') == 'không tìm thấy clone':
                        c['status'] = 'không tìm thấy clone'
                    elif self.stop_event.is_set():
                        c['status'] = '⏹ Đã dừng'
                    else:
                        c['status'] = '❌ Lỗi đăng nhập'

                # Lưu trạng thái từng clone ngay sau khi nhóm clone kết thúc.
                self.save_data()

                # Update account row status summary
                ok_count = sum(1 for ok in results if ok)
                total_c = len(selected_clones)
                if ok_count == total_c:
                    row_status = f'✅ {ok_count}/{total_c} clone đã vào game'
                elif ok_count == 0:
                    row_status = f'❌ 0/{total_c} clone đã vào game'
                else:
                    row_status = f'⚠️ {ok_count}/{total_c} clone đã vào game'
                self.update_account_status(orig_idx, row_status, mode)

                base_run_idx += len(selected_clones)

                # Nghỉ giữa các tài khoản
                if grp_idx < len(acc_groups) - 1 and not self.stop_event.is_set():
                    self.log(f'⏳ Nghỉ 5s trước tài khoản tiếp theo...')
                    delay_start = time.time()
                    while time.time() - delay_start < 5.0:
                        if self.stop_event.is_set():
                            break
                        if not self.pause_event.is_set():
                            while not self.pause_event.is_set():
                                if self.stop_event.is_set() or self.skip_step_event.is_set():
                                    break
                                time.sleep(0.05)
                        if self.skip_step_event.is_set():
                            self.skip_step_event.clear()
                            self.log('⏩ [Phím tắt Ctrl+S] Đã bỏ qua thời gian nghỉ giữa các tài khoản!')
                            break
                        time.sleep(0.2)

        else:
            # Auto Login mode — simple sequential run
            total_run = len(base_items)
            for run_idx, (orig_idx, acc) in enumerate(base_items):
                if self.stop_event.is_set():
                    break

                self.update_account_status(orig_idx, 'Đang đăng nhập...', mode)
                self.log(f'--- [{tab_name} | Acc #{run_idx+1}/{total_run}: {acc.get("email")}] Khởi chạy ToW.exe ---')

                success = automation.auto_login_flow(
                    account=acc,
                    clone_exe=game_exe,
                    stop_event=self.stop_event,
                    logger=self.log,
                    index=run_idx,
                    total=total_run,
                    logout_delay=logout_delay,
                    open_game_delay=open_game_delay,
                    mode=mode,
                    step_timeout=30.0,
                    max_retries=2,
                    pause_event=self.pause_event,
                    skip_step_event=self.skip_step_event,
                    auto_tile=auto_tile,
                )

                if success:
                    self.update_account_status(orig_idx, '✅ Đã vào game', mode)
                else:
                    if self.stop_event.is_set():
                        self.update_account_status(orig_idx, '⏹ Đã dừng', mode)
                    else:
                        self.update_account_status(orig_idx, '❌ Lỗi đăng nhập', mode)

                if run_idx < total_run - 1 and not self.stop_event.is_set():
                    rest_time = 5.0 if run_idx >= 1 else 2.0
                    self.log(f'Nghỉ {rest_time:.0f} giây trước tài khoản tiếp theo...')
                    delay_start = time.time()
                    while time.time() - delay_start < rest_time:
                        if self.stop_event.is_set():
                            break
                        if not self.pause_event.is_set():
                            while not self.pause_event.is_set():
                                if self.stop_event.is_set() or self.skip_step_event.is_set():
                                    break
                                time.sleep(0.05)
                        if self.skip_step_event.is_set():
                            self.skip_step_event.clear()
                            self.log('⏩ [Phím tắt Ctrl+S] Đã bỏ qua thời gian nghỉ giữa các tài khoản!')
                            break
                        time.sleep(0.2)

        self.log(f'🏁 TIẾN TRÌNH [{tab_name}] ĐÃ KẾT THÚC.')
        self.is_running = False
        self.is_paused = False
        self.pause_event.set()
        def _finish():
            if hasattr(self, 'btn_start_login'): self.btn_start_login.config(state='normal')
            if hasattr(self, 'btn_start_clone'): self.btn_start_clone.config(state='normal')
            if hasattr(self, 'btn_stop_login'): self.btn_stop_login.config(state='disabled')
            if hasattr(self, 'btn_stop_clone'): self.btn_stop_clone.config(state='disabled')
        self.after(0, _finish)

if __name__ == '__main__':
    app = TowAutoApp()
    app.mainloop()
