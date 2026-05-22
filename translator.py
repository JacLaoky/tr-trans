import time
from deep_translator import GoogleTranslator
from deep_translator.exceptions import TranslationNotFound, RequestError


_DEEPSEEK_SYSTEM = (
    "你是韓服跑跑卡丁車（Tales Runner 韓服）的專業翻譯助手。"
    "將使用者傳來的韓文遊戲文字翻譯成繁體中文。\n"
    "遊戲背景：Tales Runner 韓服包含漢字（한자）測驗關卡，"
    "題目會出現漢字並考其韓語讀音（독음）或意義。\n"
    "規則：\n"
    "1. 只輸出翻譯結果，不要解釋、不要加括號備注。\n"
    "2. 漢字測驗題直譯，例如「(八)의 독음은?」→「(八)的讀音是？」。\n"
    "3. 選項如「오/구/칠/팔」是韓語數字讀音，翻譯成對應漢字數字：오=五、구=九、칠=七、팔=八。\n"
    "4. 遊戲技能/道具名稱保留原意，人名請音譯。\n"
    "5. 若輸入明顯不是韓文，原文輸出即可。"
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
        results = self.translate_batch([text])
        return results[0] if results else ""

    def translate_batch(self, texts: list[str], log_cb=None) -> list[str]:
        """Translate multiple texts; uses one API call for DeepSeek."""
        if not texts:
            return []

        backend = self._config.get("translation_backend", "google") if self._config else "google"
        api_key = self._config.get("deepseek_api_key", "") if self._config else ""

        if backend == "deepseek" and api_key:
            if log_cb:
                log_cb(f"[翻譯引擎] DeepSeek ({self._config.get('deepseek_model', 'deepseek-v4-flash')})")
            return self._batch_deepseek(texts, api_key, log_cb=log_cb)
        else:
            if log_cb:
                log_cb("[翻譯引擎] Google Translate")
            return [self._translate_google(t) for t in texts]

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

    def _batch_deepseek(self, texts: list[str], api_key: str, log_cb=None) -> list[str]:
        # Return cached items immediately
        results = [self._cache.get(t.strip(), "") for t in texts]
        missing_idx = [i for i, r in enumerate(results) if not r]
        if not missing_idx:
            return results

        missing_texts = [texts[i].strip() for i in missing_idx]
        try:
            import openai
            if not self._ai_client:
                self._ai_client = openai.OpenAI(
                    api_key=api_key,
                    base_url="https://api.deepseek.com",
                )
                self._model = (self._config.get("deepseek_model", "deepseek-v4-flash")
                               if self._config else "deepseek-v4-flash")

            # Send all texts in one numbered request
            prompt = "\n".join(f"{i+1}. {t}" for i, t in enumerate(missing_texts))
            system = (_DEEPSEEK_SYSTEM +
                      "\n請按相同編號格式輸出繁體中文翻譯，每行一條，格式：「1. 翻譯結果」。")
            resp = self._ai_client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": prompt},
                ],
                max_tokens=512,
                temperature=0.1,
            )
            raw = resp.choices[0].message.content.strip()
            if log_cb:
                log_cb(f"[DeepSeek 回應] {raw[:120]}{'…' if len(raw) > 120 else ''}")
            translated = self._parse_numbered(raw, len(missing_texts))
            for i, (orig, trans) in enumerate(zip(missing_texts, translated)):
                if trans and not trans.startswith("["):
                    self._store(orig, trans)
                results[missing_idx[i]] = trans or orig

        except Exception as e:
            err = f"[DeepSeek 失敗: {e}]"
            if log_cb:
                log_cb(err)
            for i in missing_idx:
                results[i] = err

        return results

    @staticmethod
    def _parse_numbered(text: str, count: int) -> list[str]:
        """Parse '1. xxx\n2. yyy' response into a list of strings."""
        out = [""] * count
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            dot = line.find(".")
            if dot > 0 and line[:dot].isdigit():
                idx = int(line[:dot]) - 1
                if 0 <= idx < count:
                    out[idx] = line[dot + 1:].strip()
        # Fallback: if parsing fails, split by newline
        if all(v == "" for v in out):
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            for i in range(min(count, len(lines))):
                out[i] = lines[i]
        return out

    # ------------------------------------------------------------------ #
    # Cache                                                                #
    # ------------------------------------------------------------------ #

    def _store(self, key: str, value: str):
        self._cache[key] = value
        if len(self._cache) > 500:
            del self._cache[next(iter(self._cache))]
