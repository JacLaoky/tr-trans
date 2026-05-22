import time
from deep_translator import GoogleTranslator
from deep_translator.exceptions import TranslationNotFound, RequestError


_DEEPSEEK_SYSTEM = (
    "你是韓服跑跑卡丁車（Tales Runner 韓服）的專業翻譯助手。"
    "將使用者傳來的韓文遊戲文字翻譯成繁體中文。"
    "規則：\n"
    "1. 只輸出翻譯結果，不要解釋、不要加括號備注。\n"
    "2. 遊戲技能/道具名稱保留原意，人名請音譯。\n"
    "3. 若是遊戲系統訊息（如「連線失敗」「伺服器維護」）請直譯。\n"
    "4. 若輸入明顯不是韓文，原文輸出即可。"
)


class TranslationEngine:
    def __init__(self, config=None, source: str = "ko", target: str = "zh-TW"):
        self._config = config
        self._source = source
        self._target = target
        self._cache: dict[str, str] = {}
        self._google_client: GoogleTranslator | None = None
        self._ai_client = None

    # ------------------------------------------------------------------ #
    # Public                                                               #
    # ------------------------------------------------------------------ #

    def translate(self, text: str) -> str:
        if not text or not text.strip():
            return ""
        key = text.strip()
        if key in self._cache:
            return self._cache[key]

        backend = self._config.get("translation_backend", "google") if self._config else "google"
        api_key = self._config.get("deepseek_api_key", "") if self._config else ""

        if backend == "deepseek" and api_key:
            result = self._translate_deepseek(key, api_key)
        else:
            result = self._translate_google(key)

        if result and not result.startswith("["):
            self._store(key, result)
        return result

    def update_config(self, config):
        """Call after saving new settings so the engine picks them up."""
        self._config = config
        self._ai_client = None  # force re-init with new key/model

    # ------------------------------------------------------------------ #
    # Backends                                                             #
    # ------------------------------------------------------------------ #

    def _translate_google(self, text: str) -> str:
        for attempt in range(3):
            try:
                if not self._google_client:
                    self._google_client = GoogleTranslator(
                        source=self._source, target=self._target
                    )
                result = self._google_client.translate(text)
                if result and result.strip():
                    return result.strip()
                self._google_client = None
                time.sleep(0.4 * (attempt + 1))
            except TranslationNotFound:
                self._google_client = None
                time.sleep(0.4 * (attempt + 1))
            except RequestError as e:
                return f"[網路錯誤: {e}]"
            except Exception as e:
                return f"[翻譯失敗: {e}]"
        return "[無法翻譯]"

    def _translate_deepseek(self, text: str, api_key: str) -> str:
        try:
            import openai
            if not self._ai_client:
                model = (self._config.get("deepseek_model", "deepseek-v4-flash")
                         if self._config else "deepseek-v4-flash")
                self._ai_client = openai.OpenAI(
                    api_key=api_key,
                    base_url="https://api.deepseek.com",
                )
                self._model = model

            resp = self._ai_client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": _DEEPSEEK_SYSTEM},
                    {"role": "user",   "content": text},
                ],
                max_tokens=256,
                temperature=0.1,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            return f"[DeepSeek 失敗: {e}]"

    # ------------------------------------------------------------------ #
    # Cache                                                                #
    # ------------------------------------------------------------------ #

    def _store(self, key: str, value: str):
        self._cache[key] = value
        if len(self._cache) > 500:
            del self._cache[next(iter(self._cache))]
