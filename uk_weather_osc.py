#!/usr/bin/env python3
# UK City Weather (Open-Meteo) => OSC (with Pure Data example) 

import tkinter as tk
from tkinter import ttk, messagebox
import requests
from pythonosc import udp_client
import time
import math

CITIES = [
    {"name": "London",    "slug": "london",    "lat": 51.5085,  "lon": -0.12574},
    {"name": "Manchester","slug": "manchester","lat": 53.48095, "lon": -2.23743},
    {"name": "Birmingham","slug": "birmingham","lat": 52.48142, "lon": -1.89983},
    {"name": "Glasgow",   "slug": "glasgow",   "lat": 55.8652,  "lon": -4.25763},
    {"name": "Liverpool", "slug": "liverpool", "lat": 53.4106,  "lon": -2.97794},
    {"name": "Leeds",     "slug": "leeds",     "lat": 53.7965,  "lon": -1.54785},
    {"name": "Sheffield", "slug": "sheffield", "lat": 53.38297, "lon": -1.4659},
    {"name": "Edinburgh", "slug": "edinburgh", "lat": 55.95206, "lon": -3.19648},
    {"name": "Bristol",   "slug": "bristol",   "lat": 51.45451, "lon": -2.58791},
    {"name": "Leicester", "slug": "leicester", "lat": 52.6386,  "lon": -1.13169},
]

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_PARAMS_BASE = {
    "current": "temperature_2m,wind_speed_10m,wind_direction_10m",
    "timezone": "Europe/London",
}

DEFAULT_OSC_HOST = "127.0.0.1"
DEFAULT_OSC_PORT = 9000
DEFAULT_REFRESH_SECONDS = 60

def deg_to_compass(deg: float) -> str:
    if deg is None:
        return "?"
    dirs = [
        "N","NNE","NE","ENE",
        "E","ESE","SE","SSE",
        "S","SSW","SW","WSW",
        "W","WNW","NW","NNW",
    ]
    idx = int((deg % 360) / 22.5 + 0.5)
    return dirs[idx % 16]

def fetch_city_weather(city):
    params = {
        **OPEN_METEO_PARAMS_BASE,
        "latitude": city["lat"],
        "longitude": city["lon"],
    }
    try:
        resp = requests.get(OPEN_METEO_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None

    current = data.get("current", {})
    return {
        "temperature": current.get("temperature_2m"),
        "wind_speed": current.get("wind_speed_10m"),
        "wind_dir": current.get("wind_direction_10m"),
        "time": current.get("time"),
    }

class WeatherOSCApp:
    def __init__(self, master):
        self.master = master
        self.master.title("UK City Weather → OSC (Open-Meteo)")
        self.master.geometry("950x450")

        self.running = False
        self.refresh_seconds = DEFAULT_REFRESH_SECONDS

        self.osc_host = tk.StringVar(value=DEFAULT_OSC_HOST)
        self.osc_port = tk.IntVar(value=DEFAULT_OSC_PORT)

        self._build_style()
        self._build_widgets()

    def _build_style(self):
        style = ttk.Style()
        try: style.theme_use("clam")
        except: pass
        style.configure("Treeview", font=("Segoe UI", 11), rowheight=26)
        style.configure("Treeview.Heading", font=("Segoe UI", 11, "bold"))
        style.configure("Big.TButton", font=("Segoe UI", 11, "bold"), padding=6)
        style.configure("Status.TLabel", font=("Segoe UI", 10))

    def _build_widgets(self):
        frame_table = ttk.Frame(self.master, padding=10)
        frame_table.pack(fill=tk.BOTH, expand=True)

        columns = ("city","temp","wind","dir","updated")
        self.tree = ttk.Treeview(frame_table, columns=columns, show="headings")
        for col in columns:
            self.tree.heading(col, text=col.capitalize())
        self.tree.column("city", width=150, anchor=tk.W)
        self.tree.column("temp", width=120, anchor=tk.CENTER)
        self.tree.column("wind", width=120, anchor=tk.CENTER)
        self.tree.column("dir",  width=150, anchor=tk.CENTER)
        self.tree.column("updated", width=240, anchor=tk.W)

        self.tree_items = {}
        for city in CITIES:
            iid = self.tree.insert("", tk.END, values=(city["name"],"-","-","-","-"))
            self.tree_items[city["slug"]] = iid

        self.tree.pack(fill=tk.BOTH, expand=True)

        frame_bottom = ttk.Frame(self.master, padding=(10,5))
        frame_bottom.pack(fill=tk.X)

        osc_frame = ttk.LabelFrame(frame_bottom, text="OSC Settings", padding=8)
        osc_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0,5))

        ttk.Label(osc_frame, text="Host:").grid(row=0, column=0)
        ttk.Entry(osc_frame, textvariable=self.osc_host, width=16).grid(row=0, column=1)

        ttk.Label(osc_frame, text="Port:").grid(row=0, column=2)
        ttk.Entry(osc_frame, textvariable=self.osc_port, width=8).grid(row=0, column=3)

        ttk.Label(osc_frame, text="Refresh (s):").grid(row=1, column=0, pady=(5,0))
        self.refresh_scale = ttk.Scale(osc_frame, from_=10, to=300,
                                       orient=tk.HORIZONTAL,
                                       command=self._on_refresh_scale_move)
        self.refresh_scale.set(self.refresh_seconds)
        self.refresh_scale.grid(row=1, column=1, columnspan=3, sticky="ew")

        osc_frame.columnconfigure(1, weight=1)

        button_frame = ttk.Frame(frame_bottom)
        button_frame.pack(side=tk.RIGHT)

        self.start_button = ttk.Button(button_frame, text="Start",
                                       style="Big.TButton",
                                       command=self.start_updates)
        self.start_button.grid(row=0, column=0, padx=5)

        self.stop_button = ttk.Button(button_frame, text="Stop",
                                      style="Big.TButton",
                                      command=self.stop_updates,
                                      state=tk.DISABLED)
        self.stop_button.grid(row=0, column=1, padx=5)

        self.status_var = tk.StringVar(value="Idle. Click Start to begin.")
        ttk.Label(self.master, textvariable=self.status_var,
                  style="Status.TLabel",
                  anchor=tk.W, padding=(10,0,10,5)).pack(fill=tk.X)

        self.master.bind("<space>", lambda e: self._toggle_start_stop())
        self.master.bind("<Escape>", lambda e: self.stop_updates())

    def _on_refresh_scale_move(self, value):
        try: self.refresh_seconds = int(float(value))
        except: self.refresh_seconds = DEFAULT_REFRESH_SECONDS

    def _toggle_start_stop(self):
        if self.running: self.stop_updates()
        else: self.start_updates()

    def start_updates(self):
        if self.running: return
        try:
            port = int(self.osc_port.get())
            if not (1 <= port <= 65535): raise ValueError
        except:
            messagebox.showerror("Invalid Port", "Enter valid port 1–65535.")
            return

        self.running = True
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.status_var.set("Running...")

        self._update_cycle()

    def stop_updates(self):
        if not self.running: return
        self.running = False
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.status_var.set("Stopped.")

    def _update_cycle(self):
        if not self.running: return

        try:
            osc_client = udp_client.SimpleUDPClient(self.osc_host.get(),
                                                    int(self.osc_port.get()))
        except Exception as e:
            self.status_var.set(f"OSC error: {e}")
            osc_client = None

        errors = 0

        for city in CITIES:
            weather = fetch_city_weather(city)
            iid = self.tree_items.get(city["slug"])

            if weather is None:
                errors += 1
                self.tree.item(iid, values=(city["name"],"ERR","ERR","ERR",
                                            time.strftime("%H:%M:%S")))
                continue

            temp = weather["temperature"]
            wind_speed = weather["wind_speed"]
            wind_dir = weather["wind_dir"]
            ts = weather["time"] or time.strftime("%Y-%m-%dT%H:%M:%S")

            dir_str = "-" if wind_dir is None else f"{wind_dir:.0f}° ({deg_to_compass(wind_dir)})"
            temp_str = "-" if temp is None else f"{temp:.1f}"
            wind_str = "-" if wind_speed is None else f"{wind_speed:.1f}"

            self.tree.item(iid, values=(city["name"], temp_str, wind_str, dir_str, ts))

            if osc_client:
                try:
                    base = f"/ukweather/{city['slug']}"
                    if temp is not None:
                        osc_client.send_message(base+"/temperature", float(temp))
                    if wind_speed is not None:
                        osc_client.send_message(base+"/wind_speed", float(wind_speed))
                    if wind_dir is not None:
                        osc_client.send_message(base+"/wind_dir_deg", float(wind_dir))
                except:
                    errors += 1

        if errors == 0:
            self.status_var.set(f"Last update OK at {time.strftime('%H:%M:%S')}")
        else:
            self.status_var.set(f"Update had {errors} error(s) at {time.strftime('%H:%M:%S')}")

        if self.running:
            self.master.after(self.refresh_seconds * 1000, self._update_cycle)

def main():
    root = tk.Tk()
    app = WeatherOSCApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
