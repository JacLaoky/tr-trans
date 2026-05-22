from deep_translator import GoogleTranslator


class TranslationEngine:
    def __init__(self, source: str = "ko", target: str = "zh-TW"):
        self._source = source
        self._target = target
        self._client = GoogleTranslator(source=source, target=target)
        self._cache: dict[str, str] = {}

    def translate(self, text: str) -> str:
        if not text or not text.strip():
            return ""
        key = text.strip()
        if key in self._cache:
            return self._cache[key]
        try:
            result = self._client.translate(key)
            if result:
                self._cache[key] = result
                # Keep cache bounded
                if len(self._cache) > 500:
                    oldest = next(iter(self._cache))
                    del self._cache[oldest]
                return result
        except Exception as e:
            return f"[翻譯失敗: {e}]"
        return ""
