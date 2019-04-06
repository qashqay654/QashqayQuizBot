import logging
from collections import defaultdict
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, PicklePersistence, CallbackQueryHandler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import yaml

from QReadWrite import QReadWrite
from QTypes import AnswerCorrectness
from QQuizKernel import QQuizKernel


class QGameConfig:
    working_dir = ""
    default_game = ""
    logger_path = ""
    token = ""
    user_db_path = ""
    no_spoilers_default = True

    def __init__(self, config):
        with open(config, 'r') as handle:
            config = yaml.load(handle, Loader=yaml.BaseLoader)
            self.working_dir = config['working_dir']
            self.default_game = config['default_game']
            self.logger_path = config['logger_path']
            self.token = config['token'] # TODO: add encryption
            self.user_db_path = config['user_db_path']

            self.no_spoilers_default = bool(int(config['no_spoilers_default']))


class QGame:
    __name__ = "QGame"

    def __init__(self, config_path: str):
        self.config = QGameConfig(config_path)
        puzzles_db = PicklePersistence(filename=self.config.user_db_path)
        self.updater = Updater(self.config.token, use_context=True, persistence=puzzles_db)
        self.init_dispatcher(self.updater.dispatcher)
        logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                            level=logging.INFO,
                            filename=self.config.logger_path,
                            filemode='a'
                            )
        self.logger = logging.getLogger(__name__)

    def start_polling(self, demon=False):
        self.updater.start_polling()
        if not demon:
            self.updater.idle()

    def stop_polling(self):
        self.updater.stop()

    def __get_chat_meta(self, update, context):
        if update.effective_message.chat.type == 'private':
            metadata = context.user_data
        else:
            metadata = context.chat_data

        if metadata:
            if 'game_type' not in metadata.keys():
                metadata['game_type'] = self.config.default_game
            if 'quiz' not in metadata.keys():
                metadata['quiz'] = {}
                metadata['quiz'][metadata['game_type']] = QQuizKernel(self.config.working_dir,
                                                                      metadata['game_type'],
                                                                      context.bot,
                                                                      update.effective_message.chat_id)
            if 'no_spoiler' not in metadata.keys():
                metadata['no_spoiler'] = self.config.no_spoilers_default
            if 'message_stack' not in metadata.keys():
                metadata['message_stack'] = []
        return metadata

    def __check_meta(self, metadata, update):
        if not metadata:
            update.effective_message.reply_text("Видимо что-то сломалось. Введите /start, чтобы начать")
        return metadata

    def __start(self, update, context):
        metadata = self.__get_chat_meta(update, context)
        chat_id = update.effective_message.chat_id

        if not metadata:
            metadata['game_type'] = self.config.default_game
            metadata['quiz'] = defaultdict(QQuizKernel)
            metadata['quiz'][metadata['game_type']] = QQuizKernel(self.config.working_dir,
                                                                  metadata['game_type']
                                                                  )
            metadata['no_spoiler'] = self.config.no_spoilers_default if update.effective_message.chat.type != 'private' else False
            metadata['message_stack'] = []

            reply_text = ("	Привет! Добро пожаловать в игру!\n"
                          "\n"
                          "Ниже появится первая загадка. Если у тебя есть идея ответа, то введи её после команды /answer в качестве аргумента, например: /answer Пушкин. Если ответ правильный, то ты сразу перейдешь к следующему уровню. Также не исключено, что автор вопроса добавил подсказку. Чтобы увидеть её вбей команду /hint. Если не получается найти ответ (либо ты уверен, что написал правильно, а глупый бот тебя не понимает), то введи /getanswer, и если режим игры позволяет просматривать ответы, то можешь проверить свои догадки. Также некоторые режими игры позволяют менять уровень, не решив прерыдущий. Для этого введи /setlevel и выбери нужный.\n"
                          "\n"
                          "В боте предусмотрено несколько видов и источников загадок. Полный список можно найти, введя /settings и выбрав опцию Игры. \n"
                          "\n"
                          "Для игры в групповых чатах предусмотрен режим No spoilers. Если включить его в меню /settings, то бот будет удалять все сообщения, относящиеся к предыдущему вопросу, чтобы остальные участники группы не видели ответов и могли решить загадку самостоятельно.\n"
                          "\n"
                          "Если хочешь начать игру сначала, то введи /reset, но учти, что тогда потеряются все сохранения.\n"
                          "\n"
                          "	Удачи!\n")

            metadata['message_stack'].append(
                context.bot.sendMessage(chat_id=chat_id, text=reply_text))
            self.logger.info('New user added %s', update.effective_message.from_user)
        question, path = metadata['quiz'][metadata['game_type']].get_new_question()
        metadata['message_stack'] += QReadWrite.send(question, context.bot, chat_id, path, preview=False)

    def __question(self, update, context):
        metadata = self.__check_meta(self.__get_chat_meta(update, context), update)
        if not metadata:
            return
        chat_id = update.effective_message.chat_id
        metadata['message_stack'].append(update.effective_message)
        question, path = metadata['quiz'][metadata['game_type']].get_new_question()

        metadata['message_stack'] += QReadWrite.send(question, context.bot, chat_id, path, preview=False)

    def __hint(self, update, context):
        metadata = self.__check_meta(self.__get_chat_meta(update, context), update)
        if not metadata:
            return
        chat_id = update.effective_message.chat_id

        help_reply = metadata['quiz'][metadata['game_type']].get_hint()
        metadata['message_stack'].append(update.effective_message)
        metadata['message_stack'].append(context.bot.sendMessage(chat_id=chat_id, text=help_reply))

    def __answer(self, update, context):
        metadata = self.__check_meta(self.__get_chat_meta(update, context), update)
        if not metadata:
            return

        chat_id = update.effective_message.chat_id
        metadata['message_stack'].append(update.effective_message)

        answer = ' '.join(context.args).lower()
        if not answer:
            metadata['message_stack'].append(
                update.effective_message.reply_text(text="Укажи ответ аргументом после команды /answer, например:\n /answer 1984"))
            return

        self.logger.info('User %s answered %s in game %s on question %s',
                         update.effective_message.from_user,
                         answer,
                         metadata['game_type'],
                         metadata['quiz'][metadata['game_type']].last_question_num
                         )
        correctness = metadata['quiz'][metadata['game_type']].check_answer(answer)
        if correctness == AnswerCorrectness.CORRECT:
            self.logger.info('User %s solved puzzle %s from %s',
                             update.effective_message.from_user, metadata['quiz'][metadata['game_type']].last_question_num, metadata['game_type'])
            if metadata['no_spoiler']:
                for msg in metadata['message_stack']:
                    try:
                        context.bot.deleteMessage(msg.chat_id, msg.message_id)
                    except:
                        self.logger.warning('No message "%s"', msg)
            metadata['message_stack'].clear()

            metadata['quiz'][metadata['game_type']].next()
            question, path = metadata['quiz'][metadata['game_type']].get_new_question()
            metadata['message_stack'] += QReadWrite.send(question, context.bot, chat_id, path, preview=False)

        elif type(correctness) == str:
            metadata['message_stack'].append(
                context.bot.sendMessage(chat_id=chat_id, text=correctness))
        else:
            self.logger.warning('Wrong answer type "%s"', correctness)

    def __get_answer(self, update, context):
        metadata = self.__check_meta(self.__get_chat_meta(update, context), update)
        chat_id = update.effective_message.chat_id
        context.bot.sendMessage(text=metadata['quiz'][metadata['game_type']].get_answer(), chat_id=chat_id)


    def __error(self, update, context):
        """Log Errors caused by Updates."""
        self.logger.warning('Update "%s" caused error "%s"', update, context.error)

    def __reset(self, update, context):
        metadata = self.__check_meta(self.__get_chat_meta(update, context), update)
        if not metadata:
            return
        update.effective_message.reply_text(self.__reset_text(),
                                  reply_markup=self.__reset_markup())

    def __reset_text(self):
        return "Точно? Все сохранения в игре удалятся."

    def __reset_markup(self):
        keyboard = [[InlineKeyboardButton("Точно", callback_data='reset-1'),
                     InlineKeyboardButton("Нет", callback_data='reset-0')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        return reply_markup

    def __reset_button(self, update, context):
        query = update.callback_query
        metadata = self.__check_meta(self.__get_chat_meta(update, context), update)
        chat_id = update.effective_message.chat_id
        if not metadata:
            return
        button = bool(int(query.data.split('-')[-1]))
        if bool(button):
            update.effective_message.delete()
            metadata['quiz'][metadata['game_type']].reset()
            question, path = metadata['quiz'][metadata['game_type']].get_new_question()
            metadata['message_stack'] += QReadWrite.send(question, context.bot, chat_id, path, preview=False)
            self.logger.info('User %s reset %s',
                             update.effective_message.from_user,
                             metadata['game_type'])
        else:
            update.effective_message.delete()

    def __settings(self, update, context):
        metadata = self.__check_meta(self.__get_chat_meta(update, context), update)
        if not metadata:
            return
        update.effective_message.reply_text(self.__settings_main_text(),
                                  reply_markup=self.__settings_main_markup())

    def __settings_main(self, update, context):
        query = update.callback_query
        metadata = self.__check_meta(self.__get_chat_meta(update, context), update)
        if not metadata:
            return

        query.edit_message_text(text=self.__settings_main_text(),
                                reply_markup=self.__settings_main_markup())

    def __settings_main_text(self):
        return 'Выбери нужную настройку'

    def __settings_main_markup(self):
        keyboard = [[InlineKeyboardButton("Игры", callback_data='m3-game_type'),
                     InlineKeyboardButton("No spoilers", callback_data='m2-diss_mode')],

                    [InlineKeyboardButton("Done", callback_data='done')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        return reply_markup

    def __settings_done(self, update, context):
        query = update.callback_query
        query.answer(text='Done')
        update.effective_message.delete()

    # Dissapearing mode settings

    def __settings_spoiler(self, update, context):
        query = update.callback_query
        metadata = self.__check_meta(self.__get_chat_meta(update, context), update)
        if not metadata:
            return
        query.edit_message_text(text=self.__settings_spoiler_text(metadata['no_spoiler']),
                                reply_markup=self.__settings_spoiler_markup())

    def __settings_spoiler_text(self, status):
        return "При включенном режиме no spoilers будут удаляться все старые вопросы и ответы, но работает он только в групповых чатах " + " (сейчас " + str(status) + ")"

    def __settings_spoiler_markup(self):
        keyboard = [[InlineKeyboardButton("Вкл", callback_data='m2_1-1'),
                     InlineKeyboardButton("Выкл", callback_data='m2_1-0')],
                    [InlineKeyboardButton("Главное меню", callback_data='main')]
                    ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        return reply_markup

    def __settings_spoiler_button(self, update, context):
        query = update.callback_query
        metadata = self.__check_meta(self.__get_chat_meta(update, context), update)
        if not metadata:
            return
        button = bool(int(query.data.split('-')[-1]))
        metadata['no_spoiler'] = button
        query.answer(text="Режим no spoilers включен" if button else "Режим no spoilers выключен")
        query.edit_message_text(
            text=self.__settings_main_text(),
            reply_markup=self.__settings_main_markup()
        )
        self.logger.info('User %s set spoiler mode to %s',
                         update.effective_message.from_user,
                         button)

    # Game mode settings

    def __settings_game(self, update, context):
        query = update.callback_query
        metadata = self.__check_meta(self.__get_chat_meta(update, context), update)
        if not metadata:
            return
        reply_markup = QReadWrite.parse_game_folders_markup(self.config.working_dir)
        query.edit_message_text(text=self.__settings_game_text(metadata['game_type']),
                                reply_markup=reply_markup)

    def __settings_game_text(self, status):
        return "Доступные игры " + " (сейчас " + str(status) + ")"

    def __settings_game_button(self, update, context):
        query = update.callback_query
        metadata = self.__check_meta(self.__get_chat_meta(update, context), update)
        chat_id = update.effective_message.chat_id
        if not metadata:
            return
        button = query.data.split('-')[-1]
        if button in metadata['quiz'].keys():
            metadata['game_type'] = button
        else:
            metadata['game_type'] = button
            metadata['quiz'][metadata['game_type']] = QQuizKernel(self.config.working_dir,
                                                                  metadata['game_type'],
                                                                  context.bot,
                                                                  update.effective_message.chat_id)
        self.logger.info('User %s set new game type %s',
                         update.effective_message.from_user,
                         metadata['game_type'])
        question, path = metadata['quiz'][metadata['game_type']].get_new_question()
        metadata['message_stack'] += QReadWrite.send(question, context.bot, chat_id, path, preview=False)

        query.answer(text='Теперь играем в ' + button)
        update.effective_message.delete()

    def __levels_markup(self, game):
        levels = game.get_all_levels()
        if not levels:
            return None
        keyboard = [[]]
        for i, level in enumerate(levels):
            if len(keyboard[-1]) == 1:
                keyboard.append([])
            num, lev = level[0], " ".join(level[1].split('_'))
            keyboard[-1].append(InlineKeyboardButton(str(int(num)+1)+'. '+lev, callback_data='game_level-' + str(i)))
        reply_markup = InlineKeyboardMarkup(keyboard)
        return reply_markup

    def __set_level(self, update, context):
        metadata = self.__check_meta(self.__get_chat_meta(update, context), update)
        chat_id = update.effective_message.chat_id
        levels_markup = self.__levels_markup(metadata['quiz'][metadata['game_type']])
        if levels_markup:
            update.effective_message.reply_text('Выберите уровень',
                                      reply_markup=levels_markup)
        else:
            update.effective_message.reply_text("Выбор уровня невозможен в этом режиме игры")

    def __levels_button(self, update, context):
        query = update.callback_query
        metadata = self.__check_meta(self.__get_chat_meta(update, context), update)
        chat_id = update.effective_message.chat_id
        if not metadata:
            return
        button = int(query.data.split('-')[-1])
        metadata['quiz'][metadata['game_type']].set_level(button)
        question, path = metadata['quiz'][metadata['game_type']].get_new_question()
        metadata['message_stack'] += QReadWrite.send(question, context.bot, chat_id, path, preview=False)
        update.effective_message.delete()

    def __help(self, update, context):
        chat_id = update.effective_message.chat_id
        context.bot.sendMessage(text=('/start - Начать игру\n'
                                      '/answer [ans] - Дать ответ на вопрос\n'
                                      '/repeat - Повторить последний вопрос\n'
                                      '/settings - Настройки игры (режим и no spoilers)\n'
                                      '/reset - Сброс прогресса игры \n'), chat_id=chat_id)

    def __credentials(self, update, context):
        chat_id = update.effective_message.chat_id
        context.bot.sendMessage(text="""
Данный бот создавался только с развлекательными целями и не несёт никакой коммерческой выгоды. Некоторые из игр в этом боте полностью скопированы с других ресурсов с загадками: Манул загадко (http://manulapuzzle.ru), Project Euler (https://projecteuler.net), Night Run. Создатели проекта ни коим образом не претендуют на авторство этих вопросов, а являются всего лишь большими фанатами этих ресурсов и хотят распространить их среди своих друзей и знакомых. Если ты являешься создателем или причастным к созданию этих задач и по каким-то причинам не доволен наличием твоих задач или упоминания ресурса в данном боте, то напиши пожалуйста на почту qashqay.sol@yandex.ru. Исходный код бота находится в открытом доступе https://github.com/qashqay654/QashqayQuizBot
""", chat_id=chat_id)



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
        dispatcher.add_handler(CallbackQueryHandler(self.__reset_button, pattern='^reset-'))

        dispatcher.add_handler(CommandHandler("settings", self.__settings,
                                              pass_user_data=True, pass_chat_data=True))
        dispatcher.add_handler(CallbackQueryHandler(self.__settings_main, pattern='main'))
        dispatcher.add_handler(CallbackQueryHandler(self.__settings_done, pattern='done'))
        dispatcher.add_handler(CallbackQueryHandler(self.__settings_spoiler, pattern='^m2-'))
        dispatcher.add_handler(CallbackQueryHandler(self.__settings_spoiler_button, pattern='^m2_1-'))
        dispatcher.add_handler(CallbackQueryHandler(self.__settings_game, pattern='^m3-'))
        dispatcher.add_handler(CallbackQueryHandler(self.__settings_game_button, pattern='^puzzname'))

        dispatcher.add_handler(CommandHandler("setlevel", self.__set_level,
                                              pass_user_data=True, pass_chat_data=True))
        dispatcher.add_handler(CallbackQueryHandler(self.__levels_button, pattern='^game_level-'))

        dispatcher.add_error_handler(self.__error)
        # TODO: add random talk
