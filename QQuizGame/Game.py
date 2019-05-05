import logging
import os
import pickle
import threading
from collections import defaultdict
from copy import deepcopy

import yaml
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import Unauthorized, ChatMigrated
from telegram.ext import Updater, CommandHandler, PicklePersistence, CallbackQueryHandler, MessageHandler, Filters

from QQuizGame import schedule
from QQuizGame.QuizKernel import QuizKernel
from QQuizGame.ReadWrite import ReadWrite
from QQuizGame.Types import AnswerCorrectness
from QQuizGame.logging_setup import setup_logger, init_logging_db, parse_upd


def check_meta(action_type):
    def decorator(func):
        def wrapper(class_self, update, context):
            class_self.db.insert_one(parse_upd(update, action_type))
            metadata = class_self.get_chat_meta(update, context)
            if not metadata:
                update.effective_message.reply_text("Видимо что-то сломалось. Введите /start, чтобы начать")
                class_self.db.insert_one(parse_upd(update, "NoMeta"))
                return
            return func(class_self, update, context)
        return wrapper
    return decorator


class GameConfig:
    def __init__(self, config):
        with open(config, 'r') as handle:
            config = yaml.load(handle, Loader=yaml.BaseLoader)
            self.games_db_path = config['games_db_path']
            self.default_game = config['default_game']
            self.logger_path = config['logger_path']
            self.token = config['token']  # TODO: add encryption
            self.user_db_path = config['user_db_path']
            self.no_spoilers_default = bool(int(config['no_spoilers_default']))
            self.admin_id = int(config['admin_id'])
            if 'game_of_the_day' in config:
                self.game_of_the_day = config['game_of_the_day']
                self.game_of_the_day_time = config['game_of_the_day_time']
                self.game_of_the_day_db_path = config['game_of_the_day_db_path']
            else:
                self.game_of_the_day = None
                self.game_of_the_day_time = "12:00"
                self.game_of_the_day_db_path = ''


class Game:
    __name__ = "Game"
    __version__ = 1.0

    def __init__(self, config_path: str):
        self.config = GameConfig(config_path)
        puzzles_db = PicklePersistence(filename=self.config.user_db_path)
        self.updater = Updater(self.config.token, use_context=True, persistence=puzzles_db)
        self.init_dispatcher(self.updater.dispatcher)

        self.logger = setup_logger(__name__,
                                   self.config.logger_path,
                                   logging.DEBUG)
        self.db = init_logging_db()

        self.game_of_day = None
        if self.config.game_of_the_day:
            path_dir = os.path.join(self.config.games_db_path, self.config.game_of_the_day, 'master')
            last_lev, message_buff = 0, []
            if os.path.exists(self.config.game_of_the_day_db_path):
                last_lev, message_buff = pickle.load(open(self.config.game_of_the_day_db_path, 'rb'))
            self.game_of_day = QuizKernel(path_dir, last_lev)
            self.__schedule_gotd()
            self.gotd_prev_message = message_buff
        self.input_event = self.__send_all_from_input()
        self.admin_text = ''

    def start_polling(self, demon=False):
        self.updater.start_polling()
        if not demon:
            self.updater.idle()

    def stop_polling(self):
        if hasattr(self, 'shed_event'):
            self.shed_event.set()
        if self.config.game_of_the_day:
            pickle.dump([self.game_of_day.last_question_num, self.gotd_prev_message],
                        open(self.config.game_of_the_day_db_path, 'wb'))
        self.input_event.set()
        self.updater.stop()

    def get_chat_meta(self, update, context):
        if update.effective_message.chat.type == 'private':
            metadata = context.user_data
        else:
            metadata = context.chat_data

        if metadata:
            if 'game_type' not in metadata.keys():
                metadata['game_type'] = self.config.default_game
            if 'quiz' not in metadata.keys():
                metadata['quiz'] = {}
                path_dir = os.path.join(self.config.games_db_path, metadata['game_type'], 'master')
                metadata['quiz'][metadata['game_type']] = QuizKernel(path_dir,
                                                                     context.bot,
                                                                     update.effective_message.chat_id)
            if 'no_spoiler' not in metadata.keys():
                metadata['no_spoiler'] = self.config.no_spoilers_default
            if 'message_stack' not in metadata.keys():
                metadata['message_stack'] = []
            if 'game_of_day' not in metadata.keys():
                metadata['game_of_day'] = True
            if 'answer_from_text' not in metadata.keys():
                metadata['answer_from_text'] = True
            if 'version' not in metadata.keys():
                metadata['version'] = self.__version__
                old_data = self.__get_game_meta(metadata['quiz'][metadata['game_type']])
                metadata['quiz'][metadata['game_type']] = QuizKernel(*old_data)
            if metadata['version'] != self.__version__:
                metadata['version'] = self.__version__
                old_data = self.__get_game_meta(metadata['quiz'][metadata['game_type']])
                metadata['quiz'][metadata['game_type']] = QuizKernel(*old_data)
        return metadata

    def save_reply(self, metadata=None, messages=None, goth=False):
        buffer = []
        check = False
        if metadata:
            buffer = metadata['message_stack']
            check = metadata['no_spoiler']
        if goth:
            buffer = self.gotd_prev_message
            check = True

        if type(messages) == list:
            for message in messages:
                if check:
                    buffer.append(message)
                self.db.insert_one(parse_upd(message, "Send"))
                if goth:
                    self.gotd_prev_message.append(message)
        else:
            if check:
                buffer.append(messages)
            self.db.insert_one(parse_upd(messages, "Send"))
            if goth:
                self.gotd_prev_message.append(messages)

    def __get_game_meta(self, game_metadata):
        try:
            old_data = game_metadata.serialize_to_db()
        except:
            old_data = game_metadata.working_dir, game_metadata.last_question_num
        return old_data

    def __start(self, update, context):
        metadata = self.get_chat_meta(update, context)
        chat_id = update.effective_message.chat_id

        if not metadata:
            metadata['game_type'] = self.config.default_game
            metadata['quiz'] = defaultdict(QuizKernel)
            path_dir = os.path.join(self.config.games_db_path, metadata['game_type'], 'master')
            metadata['quiz'][metadata['game_type']] = QuizKernel(path_dir, last_question=0)
            metadata['quiz_data'] = (path_dir, 0)
            metadata['no_spoiler'] = self.config.no_spoilers_default \
                if update.effective_message.chat.type != 'private' else False
            metadata['message_stack'] = []
            metadata['game_of_day'] = True
            metadata['answer_from_text'] = True
            metadata['version'] = self.__version__
            reply_text = ("	Привет! Добро пожаловать в игру!\n"
                          "\n"
                          '/answer [ans] - Дать ответ на вопрос (/+tab ответ)\n'
                          '/hint - Вызвать подсказку\n'
                          '/repeat - Повторить последний вопрос\n'
                          '/getanswer - Получить ответ\n'
                          '/setlevel - Выбрать уровень\n'
                          '/settings - Настройки игры (режим и no spoilers)\n'
                          '/start - Начать игру\n'
                          '/help - Вызвать подробную инструкцию\n'
                          '/credits - Авторам\n'
                          '/reset - Сброс прогресса игры \n'
                          "\n"
                          "	Удачи!\n")

            self.__set_game(update, context)

            self.save_reply(metadata, context.bot.sendMessage(chat_id=chat_id, text=reply_text))
            self.db.insert_one(parse_upd(update, "NewUser"))
            self.logger.info('New user added %s', update.effective_user)
        else:
            # этот странный трюк нужен в случае, если мы что-то обновили в игровом движке
            old_data = self.__get_game_meta(metadata['quiz'][metadata['game_type']])
            metadata['quiz'][metadata['game_type']] = QuizKernel(*old_data)

            question, path = metadata['quiz'][metadata['game_type']].get_new_question()

            self.save_reply(metadata, ReadWrite.send(question, context.bot, chat_id, path))
            self.db.insert_one(parse_upd(update, "NewUserRepeat"))

    @check_meta("Repeat")
    def __question(self, update, context):
        metadata = self.get_chat_meta(update, context)
        chat_id = update.effective_message.chat_id
        self.save_reply(metadata, update.effective_message)
        question, path = metadata['quiz'][metadata['game_type']].get_new_question()

        self.save_reply(metadata, ReadWrite.send(question, context.bot, chat_id, path))

    @check_meta("Hint")
    def __hint(self, update, context):
        metadata = self.get_chat_meta(update, context)

        chat_id = update.effective_message.chat_id

        help_reply = metadata['quiz'][metadata['game_type']].get_hint()

        self.save_reply(metadata, update.effective_message)
        self.save_reply(metadata, context.bot.sendMessage(chat_id=chat_id, text=help_reply))

    @check_meta("Answer")
    def __answer(self, update, context):
        metadata = self.get_chat_meta(update, context)

        chat_id = update.effective_message.chat_id
        self.save_reply(metadata, update.effective_message)

        if update.effective_message.text.startswith('/'):
            answer = ' '.join(context.args).lower()
        else:
            answer = update.effective_message.text
            if not metadata['answer_from_text']:
                return
        if not answer:
            self.save_reply(metadata,
                            update.effective_message.reply_text(text="Укажи ответ аргументом после команды /answer, например: "
                                                         "/answer 1984.\nЛайфхак: чтобы каждый раз не печатать слово "
                                                         "answer, можно воспользоваться комбинацией /+tab ответ"))
            return

        self.logger.info('User %s answered %s in game %s on question %s',
                         update.effective_user,
                         answer,
                         metadata['game_type'],
                         metadata['quiz'][metadata['game_type']].last_question_num
                         )
        correctness = metadata['quiz'][metadata['game_type']].check_answer(answer)
        if correctness == AnswerCorrectness.CORRECT:
            self.logger.info('User %s solved puzzle %s from %s',
                             update.effective_user,
                             metadata['quiz'][metadata['game_type']].last_question_num, metadata['game_type'])
            if metadata['no_spoiler']:
                for msg in metadata['message_stack']:
                    try:
                        context.bot.deleteMessage(msg.chat_id, msg.message_id)
                    except:
                        self.logger.warning('No message "%s"', msg)
            metadata['message_stack'].clear()

            metadata['quiz'][metadata['game_type']].next()
            question, path = metadata['quiz'][metadata['game_type']].get_new_question()

            self.save_reply(metadata, ReadWrite.send(question, context.bot, chat_id, path))

        elif type(correctness) == str:
            self.save_reply(metadata,
                update.effective_message.reply_text(text=correctness))
            # context.bot.sendMessage(chat_id=chat_id, text=correctness))
        else:
            self.logger.warning('Wrong answer type "%s"', correctness)

    @check_meta("GetAnswer")
    def __get_answer(self, update, context):
        metadata = self.get_chat_meta(update, context)
        chat_id = update.effective_message.chat_id
        self.save_reply(metadata,
                        context.bot.sendMessage(text=metadata['quiz'][metadata['game_type']].get_answer(),
                                                chat_id=chat_id))

    @check_meta("Error")
    def __error(self, update, context):
        """Log Errors caused by Updates."""
        self.logger.warning('Update "%s" caused error "%s"', update, context.error)

    @check_meta("Reset")
    def __reset(self, update, context):
        update.effective_message.reply_text(self.__reset_text(),
                                            reply_markup=self.__reset_markup())

    @staticmethod
    def __reset_text():
        return "Точно? Все сохранения в игре удалятся."

    @staticmethod
    def __reset_markup():
        keyboard = [[InlineKeyboardButton("Точно", callback_data='reset-1'),
                     InlineKeyboardButton("Нет", callback_data='reset-0')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        return reply_markup

    @check_meta("RecetButton")
    def __reset_button(self, update, context):
        query = update.callback_query
        metadata = self.get_chat_meta(update, context)
        chat_id = update.effective_message.chat_id
        if not metadata:
            return
        button = bool(int(query.data.split('-')[-1]))
        if bool(button):
            update.effective_message.delete()
            metadata['quiz'][metadata['game_type']].reset()
            question, path = metadata['quiz'][metadata['game_type']].get_new_question()
            self.save_reply(metadata, ReadWrite.send(question, context.bot, chat_id, path))
            self.logger.info('User %s reset %s',
                             update.effective_user,
                             metadata['game_type'])
        else:
            update.effective_message.delete()

    @check_meta("SetGame")
    def __set_game(self, update, context):
        metadata = self.get_chat_meta(update, context)
        chat_id = update.effective_message.chat_id
        reply_markup = ReadWrite.parse_game_folders_markup(self.config.games_db_path)
        self.save_reply(metadata,
                        context.bot.sendMessage(text=self.__settings_game_text(metadata['game_type'], False),
                                chat_id=chat_id,
                                reply_markup=reply_markup))

    @check_meta("Settings")
    def __settings(self, update, context):
        metadata = self.get_chat_meta(update, context)
        self.save_reply(metadata, update.effective_message.reply_text(self.__settings_main_text(),
                                            reply_markup=self.__settings_main_markup()))

    @check_meta("SettingsMain")
    def __settings_main(self, update, context):
        query = update.callback_query
        query.edit_message_text(text=self.__settings_main_text(),
                                reply_markup=self.__settings_main_markup())

    @staticmethod
    def __settings_main_text():
        return 'Выбери нужную настройку'

    @staticmethod
    def __settings_main_markup():
        keyboard = [[InlineKeyboardButton("Игры", callback_data='m1-game_type'),
                     InlineKeyboardButton("No spoilers", callback_data='m2-no_spoiler_mode')],
                    [InlineKeyboardButton("Загадка дня", callback_data='m3-gotd'),
                     InlineKeyboardButton("Быстрый ответ", callback_data='m4-afm')],
                    [InlineKeyboardButton("Done", callback_data='done')]
                    ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        return reply_markup

    # Game mode settings
    @check_meta("GameMode")
    def __settings_game(self, update, context):
        query = update.callback_query
        metadata = self.get_chat_meta(update, context)
        reply_markup = ReadWrite.parse_game_folders_markup(self.config.games_db_path)
        query.edit_message_text(text=self.__settings_game_text(metadata['game_type']),
                                reply_markup=reply_markup)

    @staticmethod
    def __settings_game_text(status, with_current=True):
        if with_current:
            return "Доступные игры " + " (сейчас " + str(status) + ")"
        else:
            return "Доступные игры"

    @check_meta("GameModeButton")
    def __settings_game_button(self, update, context):
        query = update.callback_query
        metadata = self.get_chat_meta(update, context)
        chat_id = update.effective_message.chat_id
        button = query.data.split('-')[-1]
        if button in metadata['quiz'].keys():
            metadata['game_type'] = button
            old_data = self.__get_game_meta(metadata['quiz'][metadata['game_type']])
            metadata['quiz'][metadata['game_type']] = QuizKernel(*old_data)
        else:
            metadata['game_type'] = button
            path_dir = os.path.join(self.config.games_db_path, metadata['game_type'], 'master')
            metadata['quiz'][metadata['game_type']] = QuizKernel(path_dir,
                                                                 0,
                                                                 context.bot,
                                                                 update.effective_message.chat_id)
        self.logger.info('User %s set new game type %s',
                         update.effective_user,
                         metadata['game_type'])
        question, path = metadata['quiz'][metadata['game_type']].get_new_question()
        self.save_reply(metadata, ReadWrite.send(question, context.bot, chat_id, path))

        query.answer(text='Теперь играем в ' + button)
        update.effective_message.delete()

    # Disappearing mode settings
    @check_meta("SpoilerMode")
    def __settings_spoiler(self, update, context):
        query = update.callback_query
        metadata = self.get_chat_meta(update, context)
        query.edit_message_text(text=self.__settings_spoiler_text(metadata['no_spoiler']),
                                reply_markup=self.__settings_spoiler_markup())

    @staticmethod
    def __settings_spoiler_text(status):
        return "При включенном режиме no spoilers будут удаляться все старые вопросы и ответы, но работает он только " \
               "в групповых чатах " + " (сейчас " + str(status) + ")"

    @staticmethod
    def __settings_spoiler_markup():
        keyboard = [[InlineKeyboardButton("Вкл", callback_data='m2_1-1'),
                     InlineKeyboardButton("Выкл", callback_data='m2_1-0')],
                    [InlineKeyboardButton("Главное меню", callback_data='main')]
                    ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        return reply_markup

    @check_meta("SpoilerModeButton")
    def __settings_spoiler_button(self, update, context):
        query = update.callback_query
        metadata = self.get_chat_meta(update, context)
        button = bool(int(query.data.split('-')[-1]))
        metadata['no_spoiler'] = button
        query.answer(text="Режим no spoilers включен" if button else "Режим no spoilers выключен")
        query.edit_message_text(
            text=self.__settings_main_text(),
            reply_markup=self.__settings_main_markup()
        )
        self.logger.info('User %s set spoiler mode to %s',
                         update.effective_user,
                         button)

    # Game of the day settings
    @check_meta("GOTD")
    def __settings_gotd(self, update, context):
        query = update.callback_query
        metadata = self.get_chat_meta(update, context)
        query.edit_message_text(text=self.__settings_gotd_text(metadata['game_of_day']),
                                reply_markup=self.__settings_gotd_markup())

    @staticmethod
    def __settings_gotd_text(status):
        return "При включенном режиме загадки дня, каждый день в чат будет приходить новый вопрос" + \
               " (сейчас " + str(status) + ")"

    @staticmethod
    def __settings_gotd_markup():
        keyboard = [[InlineKeyboardButton("Вкл", callback_data='m3_1-1'),
                     InlineKeyboardButton("Выкл", callback_data='m3_1-0')],
                    [InlineKeyboardButton("Главное меню", callback_data='main')]
                    ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        return reply_markup

    @check_meta("GOTDButton")
    def __settings_gotd_button(self, update, context):
        query = update.callback_query
        metadata = self.get_chat_meta(update, context)

        button = bool(int(query.data.split('-')[-1]))
        metadata['game_of_day'] = button
        query.answer(text="Режим загадки дня включен" if button else "Режим загадки дня выключен")
        query.edit_message_text(
            text=self.__settings_main_text(),
            reply_markup=self.__settings_main_markup()
        )
        self.logger.info('User %s set game of the day to %s',
                         update.effective_user,
                         button)

    # Answer message settings
    @check_meta("AnswerMode")
    def __settings_answer_message(self, update, context):
        query = update.callback_query
        metadata = self.get_chat_meta(update, context)
        query.edit_message_text(text=self.__settings_answer_message_text(metadata['answer_from_text']),
                                reply_markup=self.__settings_answer_message_markup())

    @staticmethod
    def __settings_answer_message_text(status):
        return "При включенном режиме, ответы будут приниматься через обычные текстовые сообщения." \
               "Пожалуйста учти, что бот логгирует все ответы на задания, чтобы улучшать ход игры," \
               "поэтому во включенном состоянии будут логироваться все сообщения в этом чате. " + \
               " (сейчас " + str(status) + ")"

    @staticmethod
    def __settings_answer_message_markup():
        keyboard = [[InlineKeyboardButton("Вкл", callback_data='m4_1-1'),
                     InlineKeyboardButton("Выкл", callback_data='m4_1-0')],
                    [InlineKeyboardButton("Главное меню", callback_data='main')]
                    ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        return reply_markup

    @check_meta("AnswerModeButton")
    def __settings_answer_message_button(self, update, context):
        query = update.callback_query
        metadata = self.get_chat_meta(update, context)
        button = bool(int(query.data.split('-')[-1]))
        metadata['answer_from_text'] = button
        query.answer(text="Ответы будут приниматься из сообщений" if button else "Ответ только после команды /answer")
        query.edit_message_text(
            text=self.__settings_main_text(),
            reply_markup=self.__settings_main_markup()
        )
        self.logger.info('User %s set answer message mode to %s',
                         update.effective_user,
                         button)

    @check_meta("Done")
    def __settings_done(self, update, context):
        query = update.callback_query
        query.answer(text='Done')
        update.effective_message.delete()

    @staticmethod
    def __levels_markup(game):
        levels = game.get_all_levels()
        if not levels:
            return None
        keyboard = [[]]
        for i, level in enumerate(levels):
            if len(keyboard[-1]) == 1:
                keyboard.append([])
            num, lev = level[0], " ".join(level[1].split('_'))
            keyboard[-1].append(
                InlineKeyboardButton(str(int(num) + 1) + '. ' + lev,
                                     callback_data='game_level-' + level[0] + "-@" + level[1]))
        keyboard.append([InlineKeyboardButton("Done", callback_data='done')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        return reply_markup

    @check_meta("SetLevel")
    def __set_level(self, update, context):  # todo: добавить кнопку exit
        metadata = self.get_chat_meta(update, context)
        levels_markup = self.__levels_markup(metadata['quiz'][metadata['game_type']])
        if levels_markup:
            update.effective_message.reply_text('Выберите уровень',
                                                reply_markup=levels_markup)
        else:
            update.effective_message.reply_text("Выбор уровня невозможен в этом режиме игры")

    @check_meta("SetLevelButton")
    def __levels_button(self, update, context):
        query = update.callback_query
        metadata = self.get_chat_meta(update, context)
        chat_id = update.effective_message.chat_id

        button = '-'.join(query.data.split('-')[1:])
        metadata['quiz'][metadata['game_type']].set_level_by_name(button)
        question, path = metadata['quiz'][metadata['game_type']].get_new_question()
        self.save_reply(metadata, ReadWrite.send(question, context.bot, chat_id, path))
        update.effective_message.delete()
        self.logger.info('User %s changed level to %s',
                         update.effective_user,
                         button)

    @check_meta("Help")
    def __help(self, update, context):
        chat_id = update.effective_message.chat_id
        context.bot.sendMessage(text=(
            "Если у тебя есть идея ответа, то введи её после команды /answer в качестве аргумента, например: /answer "
            "Пушкин. Если ответ правильный, то ты сразу перейдешь к следующему уровню. Также не исключено, "
            "что автор вопроса добавил подсказку. Чтобы увидеть её вбей команду /hint. Если не получается найти ответ "
            "(либо ты уверен, что написал правильно, а глупый бот тебя не понимает), то введи /getanswer, "
            "и если режим игры позволяет просматривать ответы, то можешь проверить свои догадки. Также некоторые "
            "режими игры позволяют менять уровень, не решив прерыдущий. Для этого введи /setlevel и выбери нужный.\n "
            "\n"
            "В боте предусмотрено несколько видов и источников загадок. Полный список можно найти, введя /settings и "
            "выбрав опцию Игры. \n "
            "\n"
            "Для игры в групповых чатах предусмотрен режим No spoilers. Если включить его в меню /settings, "
            "то бот будет удалять все сообщения, относящиеся к предыдущему вопросу, чтобы остальные участники группы "
            "не видели ответов и могли решить загадку самостоятельно.\n "
            "\n"
            "Если хочешь начать игру сначала, то введи /reset, но учти, что тогда потеряются все сохранения.\n"
        ), chat_id=chat_id)

    @check_meta("Credits")
    def __credentials(self, update, context):
        chat_id = update.effective_message.chat_id
        context.bot.sendMessage(text="""Данный бот создавался только с развлекательными целями и не несёт никакой 
        коммерческой выгоды. Некоторые из игр в этом боте полностью скопированы с других ресурсов с загадками: Манул 
        загадко (http://manulapuzzle.ru), Project Euler (https://projecteuler.net), Night Run. Создатели проекта ни 
        коим образом не претендуют на авторство этих вопросов, а являются всего лишь большими фанатами этих ресурсов 
        и хотят распространить их среди своих друзей и знакомых. Если ты являешься создателем или причастным к 
        созданию этих задач и по каким-то причинам не доволен наличием твоих задач или упоминания ресурса в данном 
        боте, то напиши пожалуйста на почту qashqay.sol@yandex.ru. Исходный код бота находится в открытом доступе 
        https://github.com/qashqay654/QashqayQuizBot""", chat_id=chat_id)

    def __game_of_the_day_send(self):
        if self.gotd_prev_message:
            self.game_of_day.next()
            for message in self.gotd_prev_message:
                try:
                    # self.updater.bot.edit_message_text(text=message.text,
                    #                                   chat_id=message.chat_id,
                    #                                   message_id=message.message_id)
                    self.updater.bot.delete_message(message.chat_id, message.message_id)
                except:
                    self.logger.warning('No message "%s"', message)
            self.gotd_prev_message.clear()

        keyboard = [[InlineKeyboardButton("Посмотреть ответ", callback_data='gotd_answ'),
                     InlineKeyboardButton("Скрыть", callback_data='done')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        if self.game_of_day:
            question, path = self.game_of_day.get_new_question()
        else:
            return
        user_data = self.updater.dispatcher.user_data
        for user in list(user_data):
            if user_data[user]:
                if 'game_of_day' not in user_data[user]:
                    user_data[user]['game_of_day'] = True
                if user_data[user]['game_of_day']:
                    try:
                        self.save_reply(messages=ReadWrite.send(question, self.updater.bot,
                                                                 user, path,
                                                                 reply_markup=reply_markup,
                                                                 game_of_day=True
                                                                 ), goth=True)
                    except Unauthorized as ua:
                        del user_data[user]
                        self.logger.warning("User %s is deleted", user)

        chat_data = self.updater.dispatcher.chat_data
        for chat in list(chat_data):
            if chat_data[chat]:
                if 'game_of_day' not in chat_data[chat]:
                    chat_data[chat]['game_of_day'] = True
                if chat_data[chat]['game_of_day']:
                    try:
                        self.save_reply(messages=ReadWrite.send(question, self.updater.bot,
                                                                 chat, path,
                                                                 reply_markup=reply_markup,
                                                                 game_of_day=True), goth=True)
                    except Unauthorized as ua:
                        del chat_data[chat]
                        self.logger.warning("Chat %s is deleted", chat)
                    except ChatMigrated as e:
                        chat_data[e.new_chat_id] = deepcopy(chat_data[chat])
                        del chat_data[chat]
                        self.logger.warning("Chat %s is migrated", chat)
                        self.save_reply(messages=ReadWrite.send(question, self.updater.bot,
                                                                 e.new_chat_id, path,
                                                                 reply_markup=reply_markup,
                                                                 game_of_day=True), goth=True)
        pickle.dump([self.game_of_day.last_question_num, self.gotd_prev_message],
                    open(self.config.game_of_the_day_db_path, 'wb'))

        self.logger.info('Game of the day send')

    def __repeat_goth(self, update, context):
        self.db.insert_one(parse_upd(update, "GothRepeat"))
        chat_id = update.effective_message.chat_id
        keyboard = [[InlineKeyboardButton("Посмотреть ответ", callback_data='gotd_answ'),
                     InlineKeyboardButton("Скрыть", callback_data='done')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        question, path = self.game_of_day.get_new_question()
        self.save_reply(messages=ReadWrite.send(question, self.updater.bot,
                                                 chat_id, path,
                                                 reply_markup=reply_markup,
                                                 game_of_day=True
                                                 ), goth=True)

    def __game_of_the_day_button(self, update, context):
        self.db.insert_one(parse_upd(update, "GothAnswerButton"))
        query = update.callback_query
        if self.game_of_day:
            query.answer(text=self.game_of_day.get_hint(), show_alert=True)

    def __schedule_gotd(self):
        schedule.every().day.at(self.config.game_of_the_day_time).do(self.__game_of_the_day_send)
        print("Scheduler set at " + self.config.game_of_the_day_time)
        self.shed_event = schedule.run_continuously()

    def __gotd_answer(self, update, context):
        self.db.insert_one(parse_upd(update, "GothAnswerAttempt"))
        chat_id = update.effective_message.chat_id

        answer = ' '.join(context.args).lower()
        if not answer:
            self.save_reply(messages=update.effective_message.reply_text(text="Укажи ответ аргументом после "
                                                                                   "команды /dq, например: "
                                                                                   "/dq 1984"), goth=True)
            return

        correctness = self.game_of_day.check_answer(answer)
        self.logger.info('User %s answered %s in %s',
                         update.effective_user,
                         answer,
                         "game of the day"
                         )
        if correctness == AnswerCorrectness.CORRECT:
            self.logger.info('User %s solved %s',
                             update.effective_user,
                             "game of the day"
                             )
            self.save_reply(messages=update.effective_message.reply_text(text="Правильно!"), goth=True)
        elif type(correctness) == str:
            self.save_reply(messages=
                context.bot.sendMessage(chat_id=chat_id, text=correctness), goth=True)
        else:
            self.logger.warning('Wrong answer type "%s"', correctness)

    def __send_all_from_admin(self, update, context):
        self.db.insert_one(parse_upd(update, "AdminMessage"))
        user_id = update.effective_message.from_user.id
        chat_id = update.effective_message.chat_id
        if user_id == self.config.admin_id:
            text = update.effective_message.text[11:].strip()  # ' '.join(context.args)
            if not text:
                update.effective_message.reply_text(text="Нет текста")
                return
            update.effective_message.reply_text(text="Preview")

            keyboard = [[InlineKeyboardButton("Шлем", callback_data='admin_send-1'),
                         InlineKeyboardButton("Не шлем", callback_data='admin_send-0')],
                        ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            context.bot.sendMessage(text=text, chat_id=chat_id, reply_markup=reply_markup)
            self.db.insert_one(parse_upd(update, "AdminMessage"))
            self.admin_text = text

    def __send_all_from_admin_button(self, update, context):
        self.db.insert_one(parse_upd(update, "AdminMessageButton"))
        query = update.callback_query
        button = bool(int(query.data.split('-')[-1]))
        query.edit_message_text(text=self.admin_text)
        if button:
            user_data = self.updater.dispatcher.user_data
            for user in list(user_data):
                if user_data[user]:
                    try:
                        self.db.insert_one(parse_upd(
                            self.updater.bot.sendMessage(text=self.admin_text, chat_id=user), 'Send'))
                    except Unauthorized as ua:
                        del user_data[user]
                        self.logger.warning("User %s is deleted", user)
            chat_data = self.updater.dispatcher.chat_data
            for chat in list(chat_data):
                if chat_data[chat]:
                    try:
                        self.db.insert_one(parse_upd(
                            self.updater.bot.sendMessage(text=self.admin_text, chat_id=chat), 'Send'))
                    except Unauthorized as ua:
                        del chat_data[chat]
                        self.logger.warning("Chat %s is deleted", chat)
                    except ChatMigrated as e:
                        chat_data[e.new_chat_id] = deepcopy(chat_data[chat])
                        del chat_data[chat]
                        self.logger.warning("Chat %s is migrated", chat)
                        self.db.insert_one(parse_upd(
                            self.updater.bot.sendMessage(text=self.admin_text, chat_id=e.new_chat_id), 'Send'))
        self.logger.info("Admin message send %s", self.admin_text)
        self.admin_text = ''

    def __send_all_from_input(self):
        cease_continuous_run = threading.Event()

        class MassiveSender(threading.Thread):
            @classmethod
            def run(cls):
                while not cease_continuous_run.is_set():
                    message = input()
                    if not message:
                        continue
                    confirm = ''
                    while confirm not in ['yes', 'no']:
                        print("Are you sure? [yes|no]")
                        confirm = input()
                    if confirm == 'no':
                        continue
                    else:
                        print('Sending')
                    user_data = self.updater.dispatcher.user_data
                    for user in list(user_data):
                        if user_data[user]:
                            try:
                                self.db.insert_one(parse_upd(self.updater.bot.sendMessage(text=message, chat_id=user), 'Send'))
                            except Unauthorized as ua:
                                del user_data[user]
                                self.logger.warning("User %s is deleted", user)
                    chat_data = self.updater.dispatcher.chat_data
                    for chat in list(chat_data):
                        if chat_data[chat]:
                            try:
                                self.db.insert_one(parse_upd(
                                    self.updater.bot.sendMessage(text=message, chat_id=chat), 'Send'))
                            except Unauthorized as ua:
                                del chat_data[chat]
                                self.logger.warning("Chat %s is deleted", chat)
                            except ChatMigrated as e:
                                chat_data[e.new_chat_id] = deepcopy(chat_data[chat])
                                del chat_data[chat]
                                self.logger.warning("Chat %s is migrated", chat)
                                self.db.insert_one(parse_upd(
                                    self.updater.bot.sendMessage(text=message, chat_id=e.new_chat_id), 'Send'))
                    self.logger.info("Admin message send %s", message)

        continuous_thread = MassiveSender()
        continuous_thread.daemon = True
        continuous_thread.start()
        return cease_continuous_run

    def init_dispatcher(self, dispatcher):
        dispatcher.add_handler(CommandHandler("start", self.__start,
                                              pass_user_data=True, pass_chat_data=True))
        dispatcher.add_handler(CommandHandler("hint", self.__hint,
                                              pass_user_data=True, pass_chat_data=True))
        dispatcher.add_handler(CommandHandler("answer", self.__answer,
                                              pass_args=True, pass_user_data=True, pass_chat_data=True))
        dispatcher.add_handler(CommandHandler("repeat", self.__question,
                                              pass_user_data=True, pass_chat_data=True))
        dispatcher.add_handler(CommandHandler("getanswer", self.__get_answer,
                                              pass_user_data=True, pass_chat_data=True))
        dispatcher.add_handler(CommandHandler("help", self.__help))
        dispatcher.add_handler(CommandHandler("credits", self.__credentials))

        dispatcher.add_handler(CommandHandler("reset", self.__reset,
                                              pass_user_data=True, pass_chat_data=True))
        dispatcher.add_handler(CommandHandler("dq", self.__gotd_answer))
        dispatcher.add_handler(CommandHandler("repeatdq", self.__repeat_goth))
        dispatcher.add_handler(CallbackQueryHandler(self.__reset_button, pattern='^reset-'))

        dispatcher.add_handler(CommandHandler("settings", self.__settings,
                                              pass_user_data=True, pass_chat_data=True))
        dispatcher.add_handler(CallbackQueryHandler(self.__settings_main, pattern='main'))
        dispatcher.add_handler(CallbackQueryHandler(self.__settings_done, pattern='done'))
        dispatcher.add_handler(CallbackQueryHandler(self.__settings_game, pattern='^m1-'))
        dispatcher.add_handler(CallbackQueryHandler(self.__settings_game_button, pattern='^puzzname'))
        dispatcher.add_handler(CallbackQueryHandler(self.__settings_spoiler, pattern='^m2-'))
        dispatcher.add_handler(CallbackQueryHandler(self.__settings_spoiler_button, pattern='^m2_1-'))
        dispatcher.add_handler(CallbackQueryHandler(self.__settings_gotd, pattern='^m3-'))
        dispatcher.add_handler(CallbackQueryHandler(self.__settings_gotd_button, pattern='^m3_1-'))
        dispatcher.add_handler(CallbackQueryHandler(self.__game_of_the_day_button, pattern='gotd_answ'))
        dispatcher.add_handler(CallbackQueryHandler(self.__settings_answer_message, pattern='^m4-'))
        dispatcher.add_handler(CallbackQueryHandler(self.__settings_answer_message_button, pattern='^m4_1-'))

        dispatcher.add_handler(CommandHandler("adminsend", self.__send_all_from_admin))
        dispatcher.add_handler(CallbackQueryHandler(self.__send_all_from_admin_button, pattern='^admin_send-'))

        dispatcher.add_handler(CommandHandler("setlevel", self.__set_level,
                                              pass_user_data=True, pass_chat_data=True))
        dispatcher.add_handler(CallbackQueryHandler(self.__levels_button, pattern='^game_level-'))

        dispatcher.add_handler(MessageHandler(Filters.text, self.__answer))
        dispatcher.add_error_handler(self.__error)
        # TODO: add random talk

# todo: прописать нормальный логгер вместо принтов
