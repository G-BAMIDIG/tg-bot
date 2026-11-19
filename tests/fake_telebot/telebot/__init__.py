"""Offline stand-in for pyTelegramBotAPI used by tests/run_tests.py.
It records everything the bot sends and lets tests deliver fake updates."""
from . import types, handler_backends


class _Obj:
    def __init__(self, **kw): self.__dict__.update(kw)


class TeleBot:
    def __init__(self, token, parse_mode=None, use_class_middlewares=False):
        self.token = token
        self.sent, self._m, self._c, self._mw = [], [], [], []
        self.fail_for = set()      # chat ids that behave like "blocked the bot"
        self.markup_edits = []

    # --- registration (mirrors the real decorators) ---
    def message_handler(self, commands=None, func=None, content_types=None):
        def d(f):
            self._m.append({"commands": commands, "func": func, "content_types": content_types, "handler": f})
            return f
        return d

    def callback_query_handler(self, func=None):
        def d(f):
            self._c.append({"func": func, "handler": f}); return f
        return d

    def setup_middleware(self, mw): self._mw.append(mw)

    # --- outgoing API ---
    def _check(self, chat_id):
        if chat_id in self.fail_for:
            raise Exception("403 Forbidden: bot was blocked by the user")

    def send_message(self, chat_id, text, reply_markup=None, parse_mode=None):
        self._check(chat_id)
        self.sent.append({"type": "message", "chat_id": chat_id, "text": text, "reply_markup": reply_markup, "parse_mode": parse_mode})
        return types.Message(types.Chat(chat_id), None, text=text)

    def send_photo(self, chat_id, photo, caption=None, reply_markup=None, parse_mode=None):
        self._check(chat_id)
        self.sent.append({"type": "photo", "chat_id": chat_id, "photo": photo, "caption": caption, "reply_markup": reply_markup})
        return types.Message(types.Chat(chat_id), None, text=caption)

    def send_video(self, chat_id, video, caption=None, reply_markup=None, parse_mode=None):
        self._check(chat_id)
        self.sent.append({"type": "video", "chat_id": chat_id, "caption": caption, "reply_markup": reply_markup})

    def send_document(self, chat_id, document, caption=None, reply_markup=None):
        self._check(chat_id)
        data = document.read() if hasattr(document, "read") else document
        self.sent.append({"type": "document", "chat_id": chat_id, "data": data, "caption": caption})

    def edit_message_text(self, text, chat_id, message_id, reply_markup=None, parse_mode=None):
        self.sent.append({"type": "edit", "chat_id": chat_id, "text": text, "reply_markup": reply_markup, "parse_mode": parse_mode})

    def edit_message_reply_markup(self, chat_id, message_id, reply_markup=None):
        self.markup_edits.append((chat_id, message_id, reply_markup))

    def answer_callback_query(self, call_id, text=None):
        self.sent.append({"type": "answer_cb", "text": text})

    def reply_to(self, message, text):
        self.sent.append({"type": "reply", "chat_id": message.chat.id, "text": text})

    def get_me(self): return _Obj(username="testbot")
    def get_file(self, file_id): return _Obj(file_path=f"photos/{file_id}.jpg")
    def download_file(self, path): return b"\xff\xd8fake-jpeg-bytes"
    def infinity_polling(self): pass

    # --- test-only: deliver an update through middlewares + the first matching handler ---
    def dispatch_message(self, message):
        for mw in self._mw:
            if isinstance(mw.pre_process(message, {}), handler_backends.CancelUpdate):
                return
        cmd = message.text[1:].split()[0].split("@")[0] if message.text and message.text.startswith("/") else None
        for h in self._m:
            if h["content_types"] and (message.photo is None) and "photo" in h["content_types"] and "text" not in h["content_types"]:
                continue
            if h["content_types"] == ["photo"] and message.photo is None:
                continue
            if h["content_types"] == ["video"] and message.video is None:
                continue
            if h["commands"] is not None:
                if cmd in h["commands"]:
                    h["handler"](message); return
                continue
            if h["func"] is None or h["func"](message):
                h["handler"](message); return

    def dispatch_callback(self, call):
        for mw in self._mw:
            if isinstance(mw.pre_process(call, {}), handler_backends.CancelUpdate):
                return
        for h in self._c:
            if h["func"](call):
                h["handler"](call); return
