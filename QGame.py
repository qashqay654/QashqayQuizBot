from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, PicklePersistence, CallbackQueryHandler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from QReadWrite import QReadWrite
from QTypes import AnswerCorrectness


class QGame:
    config = None
    logger = None

    def __init__(self):
        pass

    def __get_chat_meta(self, update, context):
        if update.message.chat.type == 'private':
            metadata = context.user_data
        else:
            metadata = context.chat_data

        if metadata:
            if 'game_type' not in metadata.keys():
                metadata['game_type'] = "manul_puzzle"
            # if 'questions' not in metadata.keys():
            #    metadata['questions'] = {}
            #    metadata['questions'][metadata['game_type']] = Questions(
            #        update.message.from_user.language_code, 0)
            if 'no_spoiler' not in metadata.keys():
                metadata['no_spoiler'] = True
            if 'message_stack' not in metadata.keys():
                metadata['question_message_stack'] = []
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
            metadata['game_type'] = "manul_puzzle"
            metadata['quiz'] = {}
            metadata['quiz'][metadata['game_type']] = Questions(0)
            metadata['no_spoiler'] = True
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

        question = metadata['quiz'][metadata['game_type']].get_new_question()
        QReadWrite.send(question, context.bot, chat_id, )  # TODO: add folder path

    def __question(self, update, context):
        metadata = self.__check_meta(self.__get_chat_meta(update, context), update)
        if not metadata:
            return
        chat_id = update.message.chat_id
        metadata['message_stack'].append(update.message)
        question = metadata['quiz'][metadata['game_type']].get_new_question()

        QReadWrite.send(question, context.bot, chat_id, )  # TODO: add folder path

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

        answer = ' '.join(context.args).lower()
        if not answer:
            metadata['message_stack'].append(
                update.message.reply_text(text="Please specify answer as an argument after command:\n /answer 1984"))
            return
        correctness = metadata['quiz'][metadata['game_type']].check_answer(answer)
        if correctness == AnswerCorrectness.CORRECT:
            if metadata['no_spoiler']:
                for msg in metadata['message_stack']:
                    try:
                        context.bot.deleteMessage(msg.chat_id, msg.message_id)
                    except:
                        self.logger.warning('No message "%s"', msg)
            metadata['message_stack'].clear()

            metadata['quiz'][metadata['game_type']].next()
            question = metadata['quiz'][metadata['game_type']].get_new_question()
            QReadWrite.send(question, context.bot, chat_id, )  # TODO: add folder path

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
            question = metadata['quiz'][metadata['game_type']
            ].get_new_question()
            QReadWrite.send(question, context.bot, chat_id, )  # TODO: add folder path
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
        return "Dissapearing mode will delete all old answers and questions" + " (now " + str(status) + ")"

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
        query.answer(text="Successfully set dissapearing mode" if button else "Successfully unset dissapearing mode")
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
        language = metadata['quiz'][metadata['game_type']].language
        query.edit_message_text(text=self.__settings_game_text(metadata['game_type']),
                                reply_markup=QReadWrite.parse_game_folders_markup(self.config.working_path))

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
            metadata['questions'][metadata['game_type']] = Questions(0)

        query.answer(text='New game mode ' + button)
        query.edit_message_text(
            text=self.__settings_main_text(),
            reply_markup=self.__settings_main_markup()
        )

