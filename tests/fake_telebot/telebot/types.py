"""Minimal stand-in for pyTelegramBotAPI's `telebot.types`, only for running tests offline."""
class WebAppInfo:
    def __init__(self, url): self.url = url
class InlineKeyboardButton:
    def __init__(self, text, callback_data=None, url=None, web_app=None):
        self.text, self.callback_data, self.url, self.web_app = text, callback_data, url, web_app
    def __repr__(self): return f"Btn({self.text!r})"
class InlineKeyboardMarkup:
    def __init__(self, row_width=3): self.rows = []
    def add(self, *b): self.rows.append(list(b))
    def all_buttons(self): return [b for r in self.rows for b in r]
class User:
    def __init__(self, id, username=None): self.id, self.username = id, username
class Chat:
    def __init__(self, id): self.id = id
class Photo:
    def __init__(self, file_id): self.file_id = file_id
class Video:
    def __init__(self, file_id): self.file_id = file_id
class Message:
    _c = [0]
    def __init__(self, chat, from_user, text=None, photo=None, video=None):
        Message._c[0] += 1
        self.message_id = Message._c[0]
        self.chat, self.from_user, self.text, self.photo, self.video = chat, from_user, text, photo, video
class CallbackQuery:
    _c = [0]
    def __init__(self, from_user, message, data):
        CallbackQuery._c[0] += 1
        self.id = CallbackQuery._c[0]
        self.from_user, self.message, self.data = from_user, message, data
