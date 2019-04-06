import os
import pickle
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from QTypes import FileType


class QReadWrite:
    def __init__(self):
        pass

    @staticmethod
    def get_message_meta(message):
        if message.text:
            return FileType.Text, False, message.text, ""
        elif message.location:
            return FileType.Location, False, message.location.longitude, message.location.latitude
        elif message.contact:
            return FileType.Contact, False, message.contact.phone_number, message.contact.first_name
        elif message.photo:
            return FileType.Photo, True, message.photo[-1].file_id, message.caption
        elif message.sticker:
            return FileType.Sticker, True, message.sticker.file_id, ""
        elif message.audio:
            return FileType.Audio, True, message.audio.file_id, message.caption
        elif message.voice:
            return FileType.Voice, True, message.voice.file_id, message.caption
        elif message.video:
            return FileType.Video, True, message.video.file_id, message.caption
        elif message.video_note:
            return FileType.VideoNote, True, message.video_note.file_id, message.caption
        elif message.document:
            return FileType.Document, True, message.document.file_id, message.caption
        elif message.animation:
            return FileType.Animation, True, message.animation.file_id, message.caption

    @staticmethod
    def push_puzzle(message, buffer):
        mes_type, is_media, first_field, second_field = QReadWrite.get_message_meta(message)
        buffer.append([mes_type, first_field, second_field, is_media, False])

    @staticmethod
    def push_answer(message, buffer):
        buffer.append(message.text)

    @staticmethod
    def send(buffer, bot, chat_id, puzzle_dir="", preview=True):
        message_stack = []
        if '-@' in puzzle_dir:
            num, name = puzzle_dir.split('/')[-1].split('-@')
            message_stack.append(bot.sendMessage(chat_id, text=str(int(num)+1) +". "+ " ".join(name.split('_'))))
        for message in buffer:
            message_type = message[0]
            first_field = message[1]
            second_field = message[2]
            if message[4] and not preview:
                first_field = open(os.path.join(puzzle_dir, first_field), 'rb')
            if message_type == FileType.Text:
                message_stack.append(bot.sendMessage(chat_id, text=first_field))
            elif message_type == FileType.Location:
                message_stack.append(bot.sendLocation(
                    chat_id, longitude=first_field, latitude=second_field))
            elif message_type == FileType.Contact:
                message_stack.append(bot.sendContact(
                    chat_id, phone_number=first_field, first_name=second_field))
            elif message_type == FileType.Photo:
                message_stack.append(bot.sendPhoto(chat_id, first_field, caption=second_field))
            elif message_type == FileType.Sticker:
                message_stack.append(bot.sendSticker(chat_id, first_field))
            elif message_type == FileType.Audio:
                message_stack.append(bot.sendAudio(chat_id, first_field, caption=second_field))
            elif message_type == FileType.Voice:
                message_stack.append(bot.sendVoice(chat_id, first_field, caption=second_field))
            elif message_type == FileType.Video:
                message_stack.append(bot.sendVideo(chat_id, first_field, caption=second_field))
            elif message_type == FileType.VideoNote:
                message_stack.append(bot.sendVideoNote(chat_id, first_field))
            elif message_type == FileType.Document:
                message_stack.append(bot.sendDocument(chat_id, first_field, caption=second_field))
            elif message_type == FileType.Animation:
                message_stack.append(bot.sendAnimation(chat_id, first_field, caption=second_field))
        return message_stack

    @staticmethod
    def save_to_file(message, answer, from_user, user_meta, puzzle_dir, bot=None, save_media=True):
        user_dir = os.path.join(puzzle_dir, user_meta['puzzle_folder'], from_user.username)
        if not os.path.exists(user_dir):
            os.makedirs(user_dir)
        puzzle_dir_ = os.path.join(user_dir, str(user_meta['question_num'][user_meta['puzzle_folder']]))
        if user_meta['name']:
            puzzle_dir_ += '-@' + user_meta['name']
        if not os.path.exists(puzzle_dir_):
            os.makedirs(puzzle_dir_)

        filename_q = os.path.join(puzzle_dir_, 'question.pickle')
        filename_a = os.path.join(puzzle_dir_, 'answer.pickle')

        for i, msg in enumerate(message):
            if save_media and msg[3]:
                unique_filename = os.path.join(puzzle_dir_, msg[1])
                bot.getFile(msg[1]).download(unique_filename)
                message[i][-1] = True

        with open(filename_q, 'wb') as handle:
            pickle.dump(message, handle)
        with open(filename_a, 'wb') as handle:
            pickle.dump(answer, handle)
        user_meta['question_num'][user_meta['puzzle_folder']] += 1
        return filename_q

    @staticmethod
    def parse_game_folders_markup(parent):
        dirs = os.listdir(parent)
        keyboard = [[]]
        for dr in dirs:
            if dr.startswith('.'): continue
            if len(keyboard[-1]) == 2:
                keyboard.append([])
            keyboard[-1].append(InlineKeyboardButton(dr, callback_data='puzzname-' + dr))
        reply_markup = InlineKeyboardMarkup(keyboard)
        return reply_markup

    @staticmethod
    def read_from_file(file_path):
        with open(file_path, 'rb') as handle:
            return pickle.load(handle)



