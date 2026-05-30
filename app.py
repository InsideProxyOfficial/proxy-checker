import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import concurrent.futures
import requests
import time
import json

TEST_URLS = {
    "httpbin.org/ip": "http://httpbin.org/ip",
    "google.com":     "http://www.google.com",
    "api.ipify.org":  "http://api.ipify.org?format=json",
}

SAMPLE_PROXIES = """185.220.101.45:9050
194.165.16.3:1080
51.158.172.165:8811
109.201.133.100:4145
72.10.160.174:23567
198.59.191.234:8080
176.9.75.42:3128
167.71.5.83:3128
82.64.183.22:8080
205.185.126.246:3128
134.209.29.120:3128
45.155.68.129:8133
103.83.232.122:80
159.65.69.186:9300
91.108.4.79:1080"""


def check_proxy(proxy_str, protocol, test_url, timeout_ms):
    timeout_s = timeout_ms / 1000

    # parse
    line = proxy_str.strip()
    if not line or line.startswith("#"):
        return None

    detected_proto = None
    for p in ["http://", "https://", "socks4://", "socks5://"]:
        if line.lower().startswith(p):
            detected_proto = p[:-3]
            line = line[len(p):]
            break

    parts = line.split(":")
    if len(parts) < 2:
        return None
    ip   = parts[0]
    port = parts[1]
    user = parts[2] if len(parts) > 2 else None
    pwd  = parts[3] if len(parts) > 3 else None

    # pick protocol
    if protocol == "Auto-detect":
        proto = detected_proto or "http"
    else:
        proto = protocol.lower()

    if user and pwd:
        proxy_url = f"{proto}://{user}:{pwd}@{ip}:{port}"
    else:
        proxy_url = f"{proto}://{ip}:{port}"

    proxies = {"http": proxy_url, "https": proxy_url}

    url = TEST_URLS.get(test_url, "http://httpbin.org/ip")

    start = time.time()
    try:
        resp = requests.get(url, proxies=proxies, timeout=timeout_s,
                            headers={"User-Agent": "Mozilla/5.0"})
        elapsed = int((time.time() - start) * 1000)
        if resp.status_code == 200:
            # try to get real IP from response
            country = "—"
            try:
                data = resp.json()
                origin = data.get("origin") or data.get("ip") or ""
                if origin:
                    # geo lookup
                    geo = requests.get(f"http://ip-api.com/json/{origin.split(',')[0].strip()}",
                                       timeout=3)
                    if geo.status_code == 200:
                        gdata = geo.json()
                        cc      = gdata.get("countryCode", "")
                        cname   = gdata.get("country", "")
                        country = f"{cc} · {cname}" if cc else "—"
            except Exception:
                pass
            return {
                "status":  "live",
                "speed":   elapsed,
                "country": country,
                "type":    proto.upper(),
            }
        else:
            return {"status": "dead", "speed": None, "country": None, "type": None}
    except requests.exceptions.Timeout:
        return {"status": "timeout", "speed": None, "country": None, "type": None}
    except Exception:
        return {"status": "dead", "speed": None, "country": None, "type": None}


class ProxyChecker:
    def __init__(self, root):
        self.root = root
        self.root.title("Proxy Checker")
        self.root.geometry("900x660")
        self.root.configure(bg="#0f0f0f")
        self.root.resizable(True, True)

        self.checking  = False
        self.results   = []
        self.filter_mode = "all"
        self._executor = None

        self.setup_styles()
        self.build_ui()

    def setup_styles(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure("TFrame",      background="#0f0f0f")
        s.configure("TLabel",      background="#0f0f0f", foreground="#e0e0e0", font=("Courier New", 10))
        s.configure("Title.TLabel",background="#0f0f0f", foreground="#ffffff",  font=("Courier New", 16, "bold"))
        s.configure("Sub.TLabel",  background="#0f0f0f", foreground="#666666",  font=("Courier New", 9))
        s.configure("Card.TLabel", background="#1a1a1a", foreground="#e0e0e0",  font=("Courier New", 10))
        s.configure("Stat.TLabel", background="#1a1a1a", foreground="#ffffff",  font=("Courier New", 22, "bold"))
        s.configure("StatSub.TLabel", background="#1a1a1a", foreground="#555555", font=("Courier New", 9))
        s.configure("Green.Stat.TLabel",  background="#1a1a1a", foreground="#00ff88", font=("Courier New", 22, "bold"))
        s.configure("Red.Stat.TLabel",    background="#1a1a1a", foreground="#ff4444", font=("Courier New", 22, "bold"))
        s.configure("Yellow.Stat.TLabel", background="#1a1a1a", foreground="#ffaa00", font=("Courier New", 22, "bold"))
        s.configure("Primary.TButton", background="#ffffff", foreground="#000000",
                    font=("Courier New", 10, "bold"), relief="flat", padding=(16, 8))
        s.map("Primary.TButton", background=[("active", "#cccccc")])
        s.configure("TButton", background="#1a1a1a", foreground="#e0e0e0",
                    font=("Courier New", 10), relief="flat", padding=(12, 8))
        s.map("TButton", background=[("active", "#2a2a2a")])
        s.configure("TCombobox", background="#1a1a1a", foreground="#e0e0e0",
                    fieldbackground="#1a1a1a", font=("Courier New", 10))
        s.configure("Horizontal.TProgressbar", background="#00ff88",
                    troughcolor="#1a1a1a", thickness=4)
        s.configure("Treeview", background="#111111", foreground="#e0e0e0",
                    fieldbackground="#111111", rowheight=28, font=("Courier New", 10))
        s.configure("Treeview.Heading", background="#1a1a1a", foreground="#444444",
                    font=("Courier New", 9), relief="flat")
        s.map("Treeview", background=[("selected", "#2a2a2a")], foreground=[("selected", "#ffffff")])

    def build_ui(self):
        main = ttk.Frame(self.root, padding="20 20 20 20")
        main.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main, text="Proxy Checker", style="Title.TLabel").pack(anchor="w")
        ttk.Label(main, text="HTTP · HTTPS · SOCKS4 · SOCKS5  —  real requests, real results",
                  style="Sub.TLabel").pack(anchor="w", pady=(2, 16))

        # Input card
        in_card = tk.Frame(main, bg="#1a1a1a", pady=16, padx=16)
        in_card.pack(fill=tk.X, pady=(0, 10))

        tk.Label(in_card, text="PROXY LIST", bg="#1a1a1a", fg="#444444",
                 font=("Courier New", 9)).pack(anchor="w")

        self.proxy_input = tk.Text(in_card, height=7,
            bg="#111111", fg="#e0e0e0", insertbackground="#ffffff",
            font=("Courier New", 11), relief="flat", padx=10, pady=8,
            wrap=tk.NONE, selectbackground="#333333")
        self.proxy_input.pack(fill=tk.X, pady=(6, 12))
        self.proxy_input.insert("1.0", "ip:port\nip:port:user:pass\nhttp://ip:port\nsocks5://ip:port")
        self.proxy_input.bind("<FocusIn>", self.clear_placeholder)

        # Options
        opts = tk.Frame(in_card, bg="#1a1a1a")
        opts.pack(fill=tk.X, pady=(0, 12))
        for c in range(4):
            opts.columnconfigure(c, weight=1, pad=8)

        self._make_opt(opts, "PROTOCOL", 0,
            ["Auto-detect","HTTP","HTTPS","SOCKS4","SOCKS5"], "protocol_var")
        self._make_entry(opts, "TIMEOUT (MS)", 1, "8000", "timeout_var")
        self._make_entry(opts, "THREADS",      2, "10",   "threads_var")
        self._make_opt(opts, "TEST URL", 3,
            list(TEST_URLS.keys()), "testurl_var")

        # Buttons
        btn_row = tk.Frame(in_card, bg="#1a1a1a")
        btn_row.pack(anchor="w")
        self.check_btn = ttk.Button(btn_row, text="Check proxies",
            style="Primary.TButton", command=self.toggle_check)
        self.check_btn.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_row, text="Load sample", command=self.load_sample).pack(side=tk.LEFT, padx=(0,8))
        ttk.Button(btn_row, text="Clear",        command=self.clear_all).pack(side=tk.LEFT, padx=(0,8))
        ttk.Button(btn_row, text="Export live",  command=self.export_live).pack(side=tk.LEFT)

        # Stats
        stats_frame = tk.Frame(main, bg="#0f0f0f")
        stats_frame.pack(fill=tk.X, pady=(0, 8))
        self.stat_labels = {}
        for key, lbl, style in [
            ("total",  "TOTAL",    "Stat.TLabel"),
            ("live",   "LIVE",     "Green.Stat.TLabel"),
            ("dead",   "DEAD",     "Red.Stat.TLabel"),
            ("pending","PENDING",  "Yellow.Stat.TLabel"),
            ("speed",  "AVG SPEED","Stat.TLabel"),
        ]:
            sf = tk.Frame(stats_frame, bg="#1a1a1a", padx=16, pady=10)
            sf.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
            v = ttk.Label(sf, text="0", style=style)
            v.pack(anchor="w")
            ttk.Label(sf, text=lbl, style="StatSub.TLabel").pack(anchor="w")
            self.stat_labels[key] = v

        # Progress
        self.progress = ttk.Progressbar(main, style="Horizontal.TProgressbar",
                                         mode="determinate", maximum=100)
        self.progress.pack(fill=tk.X, pady=(0, 8))

        # Results
        res_card = tk.Frame(main, bg="#1a1a1a")
        res_card.pack(fill=tk.BOTH, expand=True)

        filter_row = tk.Frame(res_card, bg="#1a1a1a", pady=8, padx=12)
        filter_row.pack(fill=tk.X)
        self.filter_btns = {}
        for f in ["all", "live", "dead", "timeout"]:
            b = tk.Button(filter_row, text=f.upper(),
                bg="#2a2a2a", fg="#888888",
                font=("Courier New", 9), relief="flat",
                padx=12, pady=4, cursor="hand2",
                command=lambda x=f: self.set_filter(x))
            b.pack(side=tk.LEFT, padx=(0, 4))
            self.filter_btns[f] = b
        self.filter_btns["all"].configure(bg="#ffffff", fg="#000000")

        cols = ("proxy","status","type","speed","country")
        self.tree = ttk.Treeview(res_card, columns=cols, show="headings", selectmode="extended")
        self.tree.heading("proxy",   text="PROXY")
        self.tree.heading("status",  text="STATUS")
        self.tree.heading("type",    text="TYPE")
        self.tree.heading("speed",   text="SPEED")
        self.tree.heading("country", text="COUNTRY")
        self.tree.column("proxy",   width=260, minwidth=180)
        self.tree.column("status",  width=90,  minwidth=80,  anchor="center")
        self.tree.column("type",    width=90,  minwidth=70,  anchor="center")
        self.tree.column("speed",   width=90,  minwidth=70,  anchor="center")
        self.tree.column("country", width=200, minwidth=120)
        self.tree.tag_configure("live",    foreground="#00ff88")
        self.tree.tag_configure("dead",    foreground="#ff4444")
        self.tree.tag_configure("timeout", foreground="#ffaa00")
        self.tree.tag_configure("pending", foreground="#555555")

        sb = ttk.Scrollbar(res_card, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

    def _make_opt(self, parent, label, col, values, attr):
        f = tk.Frame(parent, bg="#1a1a1a")
        f.grid(row=0, column=col, sticky="ew", padx=(0, 12))
        tk.Label(f, text=label, bg="#1a1a1a", fg="#444444", font=("Courier New", 9)).pack(anchor="w")
        var = tk.StringVar(value=values[0])
        setattr(self, attr, var)
        ttk.Combobox(f, textvariable=var, values=values, state="readonly", width=16).pack(fill=tk.X, pady=(4,0))

    def _make_entry(self, parent, label, col, default, attr):
        f = tk.Frame(parent, bg="#1a1a1a")
        f.grid(row=0, column=col, sticky="ew", padx=(0, 12))
        tk.Label(f, text=label, bg="#1a1a1a", fg="#444444", font=("Courier New", 9)).pack(anchor="w")
        var = tk.StringVar(value=default)
        setattr(self, attr, var)
        tk.Entry(f, textvariable=var, width=10,
                 bg="#111111", fg="#e0e0e0", insertbackground="#ffffff",
                 font=("Courier New", 10), relief="flat",
                 highlightthickness=1, highlightbackground="#333333").pack(fill=tk.X, pady=(4,0))

    def clear_placeholder(self, event):
        content = self.proxy_input.get("1.0", tk.END).strip()
        if content in ["ip:port\nip:port:user:pass\nhttp://ip:port\nsocks5://ip:port"]:
            self.proxy_input.delete("1.0", tk.END)

    def parse_proxies(self):
        raw = self.proxy_input.get("1.0", tk.END).strip()
        proxies = []
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            proxies.append({
                "raw": line, "status": "pending",
                "speed": None, "country": None, "type": None
            })
        return proxies

    def toggle_check(self):
        if self.checking:
            self.checking = False
            if self._executor:
                self._executor.shutdown(wait=False, cancel_futures=True)
            self.check_btn.configure(text="Check proxies")
        else:
            self.start_check()

    def start_check(self):
        proxies = self.parse_proxies()
        if not proxies:
            messagebox.showwarning("No proxies", "Paste at least one proxy first.")
            return
        self.results  = proxies
        self.checking = True
        self.check_btn.configure(text="Stop")
        self.progress["value"] = 0
        self.render_results()
        self.update_stats()

        timeout  = int(self.timeout_var.get() or 8000)
        n_threads = int(self.threads_var.get() or 10)
        protocol  = self.protocol_var.get()
        test_url  = self.testurl_var.get()

        threading.Thread(
            target=self._check_worker,
            args=(proxies, protocol, test_url, timeout, n_threads),
            daemon=True).start()

    def _check_worker(self, proxies, protocol, test_url, timeout, n_threads):
        total = len(proxies)
        done  = [0]
        lock  = threading.Lock()

        def do_one(i):
            if not self.checking:
                return
            result = check_proxy(proxies[i]["raw"], protocol, test_url, timeout)
            if result:
                proxies[i].update(result)
            else:
                proxies[i]["status"] = "dead"
            with lock:
                done[0] += 1
                pct = int(done[0] / total * 100)
            self.root.after(0, lambda p=pct: self._on_result(p))

        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=n_threads)
        with self._executor as ex:
            ex.map(do_one, range(total))

        self.root.after(0, self._finish)

    def _on_result(self, pct):
        self.progress["value"] = pct
        self.update_stats()
        self.render_results()

    def _finish(self):
        self.checking = False
        self.check_btn.configure(text="Check proxies")
        self.progress["value"] = 100

    def update_stats(self):
        live    = [r for r in self.results if r["status"] == "live"]
        dead    = [r for r in self.results if r["status"] in ("dead","timeout")]
        pending = [r for r in self.results if r["status"] == "pending"]
        self.stat_labels["total"].configure(text=str(len(self.results)))
        self.stat_labels["live"].configure(text=str(len(live)))
        self.stat_labels["dead"].configure(text=str(len(dead)))
        self.stat_labels["pending"].configure(text=str(len(pending)))
        if live:
            avg = int(sum(r["speed"] for r in live) / len(live))
            self.stat_labels["speed"].configure(text=f"{avg}ms")
        else:
            self.stat_labels["speed"].configure(text="—")

    def render_results(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        filtered = self.results if self.filter_mode == "all" \
                   else [r for r in self.results if r["status"] == self.filter_mode]
        for r in filtered:
            parts = r["raw"].split(":")
            proxy = f"{parts[0]}:{parts[1]}" if len(parts) >= 2 else r["raw"]
            speed   = f"{r['speed']}ms" if r["speed"] else "—"
            country = r["country"] or "—"
            ptype   = r["type"]    or "—"
            self.tree.insert("", tk.END,
                values=(proxy, r["status"].upper(), ptype, speed, country),
                tags=(r["status"],))

    def set_filter(self, mode):
        self.filter_mode = mode
        for k, b in self.filter_btns.items():
            b.configure(bg="#ffffff" if k == mode else "#2a2a2a",
                        fg="#000000" if k == mode else "#888888")
        self.render_results()

    def load_sample(self):
        self.proxy_input.delete("1.0", tk.END)
        self.proxy_input.insert("1.0", SAMPLE_PROXIES)

    def clear_all(self):
        self.checking = False
        self.check_btn.configure(text="Check proxies")
        self.proxy_input.delete("1.0", tk.END)
        self.results = []
        self.progress["value"] = 0
        for k in self.stat_labels:
            self.stat_labels[k].configure(text="0" if k != "speed" else "—")
        for item in self.tree.get_children():
            self.tree.delete(item)

    def export_live(self):
        live = [r["raw"].split(":")[0] + ":" + r["raw"].split(":")[1]
                for r in self.results if r["status"] == "live"]
        if not live:
            messagebox.showinfo("Export", "No live proxies to export.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files","*.txt")],
            initialfile="live_proxies.txt")
        if path:
            with open(path, "w") as f:
                f.write("\n".join(live))
            messagebox.showinfo("Exported", f"Saved {len(live)} live proxies to file.")


if __name__ == "__main__":
    root = tk.Tk()
    ProxyChecker(root)
    root.mainloop()
