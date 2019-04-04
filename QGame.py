import logging
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
            self.token = config['token']
            self.user_db_path = config['user_db_path']
            self.no_spoilers_default = bool(int(config['no_spoilers_default']))


class QGame:

    def __init__(self, config_path: str):
        self.config = QGameConfig(config_path)
        print('started')
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
        if update.message.chat.type == 'private':
            metadata = context.user_data
        else:
            metadata = context.chat_data

        if metadata:
            if 'game_type' not in metadata.keys():
                metadata['game_type'] = self.config.default_game
            if 'quiz' not in metadata.keys():
                metadata['quiz'] = {}
                metadata['quiz'][metadata['game_type']] = QQuizKernel(self.config.working_dir, metadata['game_type'])
            if 'no_spoiler' not in metadata.keys():
                metadata['no_spoiler'] = self.config.no_spoilers_default
            if 'message_stack' not in metadata.keys():
                metadata['message_stack'] = []
        return metadata

    def __check_meta(self, metadata, update):
        if metadata:
            return metadata
        else:
            update.message.reply_text("Please write '/start' first")
            return metadata

    def __start(self, update, context):
        metadata = self.__get_chat_meta(update, context)
        chat_id = update.message.chat_id

        if not metadata:
            metadata['game_type'] = self.config.default_game
            metadata['quiz'] = {}
            metadata['quiz'][metadata['game_type']] = QQuizKernel(self.config.working_dir, metadata['game_type'])
            metadata['no_spoiler'] = self.config.no_spoilers_default if update.message.chat.type != 'private' else False
            metadata['message_stack'] = []

            reply_text = ('Hi! Welcome to the game!\n'
                          'Seems that you are newbie. You will receive first question soon, try to be creative in '
                          'answering)\n '
                          'If you know the answer write /answer <your guess>.\n'
                          'If you need a hint try to write /hint, maybe kernell will give you some idea.\n'
                          '/settings\n'
                          '/reset\n'
                          '/repeat\n')
            # settings_func(update, context)

            metadata['message_stack'].append(
                context.bot.sendMessage(chat_id=chat_id, text=reply_text))
        question, path = metadata['quiz'][metadata['game_type']].get_new_question()
        QReadWrite.send(question, context.bot, chat_id, path, preview=False)

    def __question(self, update, context):
        metadata = self.__check_meta(self.__get_chat_meta(update, context), update)
        if not metadata:
            return
        chat_id = update.message.chat_id
        metadata['message_stack'].append(update.message)
        question, path = metadata['quiz'][metadata['game_type']].get_new_question()

        QReadWrite.send(question, context.bot, chat_id, path, preview=False)

    def __hint(self, update, context):
        metadata = self.__check_meta(self.__get_chat_meta(update, context), update)
        if not metadata:
            return
        chat_id = update.message.chat_id

        help_reply = metadata['quiz'][metadata['game_type']].get_hint()
        metadata['message_stack'].append(update.message)
        metadata['message_stack'].append(context.bot.sendMessage(chat_id=chat_id, text=help_reply))

    def __answer(self, update, context):
        metadata = self.__check_meta(self.__get_chat_meta(update, context), update)
        if not metadata:
            return

        chat_id = update.message.chat_id
        metadata['message_stack'].append(update.message)

        for msg in metadata['message_stack']:
            self.logger.info('%s', msg)
        answer = ' '.join(context.args).lower()
        if not answer:
            metadata['message_stack'].append(
                update.message.reply_text(text="Please specify answer as an argument after command:\n /answer 1984"))
            return
        correctness = metadata['quiz'][metadata['game_type']].check_answer(answer)
        if correctness == AnswerCorrectness.CORRECT:
            if metadata['no_spoiler']:
                for msg in metadata['message_stack']:
                    #try:
                    context.bot.deleteMessage(msg.chat_id, msg.message_id)
                    #except:
                    #    self.logger.warning('No message "%s"', msg)
            metadata['message_stack'].clear()

            metadata['quiz'][metadata['game_type']].next()
            question, path = metadata['quiz'][metadata['game_type']].get_new_question()
            QReadWrite.send(question, context.bot, chat_id, path, preview=False)

        elif type(correctness) == str:
            metadata['message_stack'].append(
                context.bot.sendMessage(chat_id=chat_id, text=correctness))
        else:
            self.logger.warning('Wrong answer type "%s"', correctness)

    def __error(self, update, context):
        """Log Errors caused by Updates."""
        self.logger.warning('Update "%s" caused error "%s"', update, context.error)

    def __reset(self, update, context):
        metadata = self.__check_meta(self.__get_chat_meta(update, context), update)
        if not metadata:
            return
        update.message.reply_text(self.__reset_text(),
                                  reply_markup=self.__reset_markup())

    def __reset_text(self):
        return "Are you sure? All progress will be lost"

    def __reset_markup(self):
        keyboard = [[InlineKeyboardButton("Yes", callback_data='reset-1'),
                     InlineKeyboardButton("No", callback_data='reset-0')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        return reply_markup

    def __reset_button(self, update, context):
        query = update.callback_query
        metadata = self.__check_meta(self.__get_chat_meta(query, context), query)
        chat_id = query.message.chat_id
        if not metadata:
            return
        button = bool(int(query.data.split('-')[-1]))
        if bool(button):
            query.message.delete()
            metadata['quiz'][metadata['game_type']].reset()
            question, path = metadata['quiz'][metadata['game_type']].get_new_question()
            QReadWrite.send(question, context.bot, chat_id, path, preview=False)
        else:
            query.message.delete()

    def __settings(self, update, context):
        metadata = self.__check_meta(self.__get_chat_meta(update, context), update)
        if not metadata:
            return
        update.message.reply_text(self.__settings_main_text(),
                                  reply_markup=self.__settings_main_markup())

    def __settings_main(self, update, context):
        query = update.callback_query
        metadata = self.__check_meta(self.__get_chat_meta(query, context), query)
        if not metadata:
            return

        query.edit_message_text(text=self.__settings_main_text(),
                                reply_markup=self.__settings_main_markup())

    def __settings_main_text(self):
        return 'Settings'

    def __settings_main_markup(self):
        keyboard = [[InlineKeyboardButton("Game Mode", callback_data='m3-game_type'),
                     InlineKeyboardButton("No spoiler", callback_data='m2-diss_mode')],

                    [InlineKeyboardButton("Done", callback_data='done')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        return reply_markup

    def __settings_done(self, update, context):
        query = update.callback_query
        query.answer(text='Done')
        query.message.delete()

    # Dissapearing mode settings

    def __settings_spoiler(self, update, context):
        query = update.callback_query
        metadata = self.__check_meta(self.__get_chat_meta(query, context), query)
        if not metadata:
            return
        query.edit_message_text(text=self.__settings_spoiler_text(metadata['no_spoiler']),
                                reply_markup=self.__settings_spoiler_markup())

    def __settings_spoiler_text(self, status):
        return "No spoiler mode will delete all old answers and questions" + " (now " + str(status) + ")"

    def __settings_spoiler_markup(self):
        keyboard = [[InlineKeyboardButton("On", callback_data='m2_1-1'),
                     InlineKeyboardButton("Off", callback_data='m2_1-0')],
                    [InlineKeyboardButton("Main menu", callback_data='main')]
                    ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        return reply_markup

    def __settings_spoiler_button(self, update, context):
        query = update.callback_query
        metadata = self.__check_meta(self.__get_chat_meta(query, context), query)
        if not metadata:
            return
        button = bool(int(query.data.split('-')[-1]))
        metadata['no_spoiler'] = button
        query.answer(text="Successfully set no spoiler mode" if button else "Successfully unset no spoiler mode")
        query.edit_message_text(
            text=self.__settings_main_text(),
            reply_markup=self.__settings_main_markup()
        )

    # Game mode settings

    def __settings_game(self, update, context):
        query = update.callback_query
        metadata = self.__check_meta(self.__get_chat_meta(query, context), query)
        if not metadata:
            return
        reply_markup = metadata['quiz'][metadata['game_type']].all_game_types_markup()
        query.edit_message_text(text=self.__settings_game_text(metadata['game_type']),
                                reply_markup=reply_markup)

    def __settings_game_text(self, status):
        return "What type of the game you want?" + " (now " + str(status) + ")"

    def __settings_game_button(self, update, context):
        query = update.callback_query
        metadata = self.__check_meta(self.__get_chat_meta(query, context), query)
        if not metadata:
            return
        button = query.data.split('-')[-1]
        if button in metadata['quiz'].keys():
            metadata['game_type'] = button
        else:
            metadata['game_type'] = button
            metadata['quiz'][metadata['game_type']] = QQuizKernel(self.config.working_dir, metadata['game_type'])

        query.answer(text='New game mode ' + button)
        query.edit_message_text(
            text=self.__settings_main_text(),
            reply_markup=self.__settings_main_markup()
        )

    def init_dispatcher(self, dispatcher):
        dispatcher.add_handler(CommandHandler("start", self.__start,
                                              pass_user_data=True, pass_chat_data=True))
        dispatcher.add_handler(CommandHandler("hint", self.__hint,
                                              pass_user_data=True, pass_chat_data=True))
        dispatcher.add_handler(CommandHandler("answer", self.__answer,
                                              pass_args=True, pass_user_data=True, pass_chat_data=True))
        dispatcher.add_handler(CommandHandler("repeat", self.__question,
                                              pass_user_data=True, pass_chat_data=True))

        dispatcher.add_handler(CommandHandler("reset", self.__reset,
                                              pass_user_data=True, pass_chat_data=True))
        dispatcher.add_handler(CallbackQueryHandler(self.__reset_button, pattern='^reset-'))

        dispatcher.add_handler(CommandHandler("settings", self.__settings))
        dispatcher.add_handler(CallbackQueryHandler(self.__settings_main, pattern='main'))
        dispatcher.add_handler(CallbackQueryHandler(self.__settings_done, pattern='done'))
        dispatcher.add_handler(CallbackQueryHandler(self.__settings_spoiler, pattern='^m2-'))
        dispatcher.add_handler(CallbackQueryHandler(self.__settings_spoiler_button, pattern='^m2_1-'))
        dispatcher.add_handler(CallbackQueryHandler(self.__settings_game, pattern='^m3-'))
        dispatcher.add_handler(CallbackQueryHandler(self.__settings_game_button, pattern='^puzzname'))

        dispatcher.add_error_handler(self.__error)
        # TODO: add random talk
