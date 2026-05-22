import time
from deep_translator import GoogleTranslator
from deep_translator.exceptions import TranslationNotFound, RequestError


class TranslationEngine:
    def __init__(self, source: str = "ko", target: str = "zh-TW"):
        self._source = source
        self._target = target
        self._cache: dict[str, str] = {}
        self._client = self._new_client()

    def _new_client(self) -> GoogleTranslator:
        return GoogleTranslator(source=self._source, target=self._target)

    def translate(self, text: str) -> str:
        if not text or not text.strip():
            return ""
        key = text.strip()
        if key in self._cache:
            return self._cache[key]

        # Retry up to 3 times — Google Translate occasionally returns empty
        for attempt in range(3):
            try:
                result = self._client.translate(key)
                if result and result.strip():
                    self._store(key, result.strip())
                    return result.strip()
                # Empty result: recreate client and retry
                self._client = self._new_client()
                time.sleep(0.4 * (attempt + 1))

            except TranslationNotFound:
                self._client = self._new_client()
                time.sleep(0.4 * (attempt + 1))

            except RequestError as e:
                return f"[網路錯誤: {e}]"

            except Exception as e:
                return f"[翻譯失敗: {e}]"

        return "[無法翻譯]"

    def _store(self, key: str, value: str):
        self._cache[key] = value
        if len(self._cache) > 500:
            del self._cache[next(iter(self._cache))]
