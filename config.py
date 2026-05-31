import json
import os

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")

DEFAULTS = {
    "capture_region": None,
    "window_title": None,
    "mode": "inplace",
    "ocr_hanzi": False,
    "translation_backend": "google",
    "deepseek_api_key": "",
    "deepseek_model": "deepseek-v4-flash",
    "capture_interval": 0.8,
    "auto_stop": True,
    "translation_source": "ko",
    "translation_target": "zh-TW",
    "overlay_alpha": 0.88,
    "overlay_font_size": 15,
    "overlay_x": 10,
    "overlay_y": 10,
    "overlay_width": 420,
    "history_size": 6,
    "answer_popup_x": None,   # saved by dragging the answer popup
    "answer_popup_y": None,
}


class Config:
    def __init__(self):
        self._data = DEFAULTS.copy()
        self._load()

    def _load(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    self._data.update(json.load(f))
            except Exception:
                pass

    def save(self):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def get(self, key, fallback=None):
        return self._data.get(key, fallback if fallback is not None else DEFAULTS.get(key))

    def set(self, key, value):
        self._data[key] = value
        self.save()
