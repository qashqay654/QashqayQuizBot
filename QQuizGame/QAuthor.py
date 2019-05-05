import logging
from collections import defaultdict

import yaml
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, PicklePersistence, CallbackQueryHandler

from QQuizGame.QReadWrite import QReadWrite
from QQuizGame.logging_setup import setup_logger

class QAuthorConfig:
    working_path = ""
    default_game = ""
    logger_path = ""
    token = ""
    save_media = True
    user_db_path = ""

    def __init__(self, config):
        with open(config, 'r') as handle:
            config = yaml.load(handle, Loader=yaml.BaseLoader)

            self.working_path = config['working_path']
            self.default_game = config['default_game']
            self.logger_path = config['logger_path']
            self.token = config['token']  # TODO: add encryption
            self.save_media = bool(int(config['save_media']))
            self.user_db_path = config['user_db_path']


class QAuthor:
    __name__ = "QAuthor"

    def __init__(self, config_path: str):
        self.config = QAuthorConfig(config_path)

        puzzles_db = PicklePersistence(filename=self.config.user_db_path)
        self.updater = Updater(self.config.token, use_context=True, persistence=puzzles_db)
        self.init_dispatcher(self.updater.dispatcher)

        self.logger = setup_logger(__name__,
                                   self.config.logger_path,
                                   logging.INFO)

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

        if "puzzle_buffer" not in metadata:
            metadata["puzzle_buffer"] = []
        if "answer_buffer" not in metadata:
            metadata["answer_buffer"] = []
        if "action" not in metadata:
            metadata["action"] = None
        if "question_num" not in metadata:
            metadata["question_num"] = defaultdict(int)
        if "puzzle_folder" not in metadata:
            metadata["puzzle_folder"] = self.config.default_game
        if "name" not in metadata:
            metadata["name"] = ""

        return metadata

    def __start(self, update, context):
        metadata = self.__get_chat_meta(update, context)
        if not metadata:
            metadata['puzzle_buffer'] = []
            metadata['answer_buffer'] = []
            metadata['action'] = None
            metadata['question_num'] = defaultdict(int)
            metadata["puzzle_folder"] = self.config.default_game
            metadata["name"] = ""
            self.logger.info('New user added %s', update.effective_user)
        update.effective_message.reply_text(text="""Hello! Welcome to the Puzzle Writer! How it works? At first send 
        /new [name] to start entering your question. Send a text of your puzzle as a normal telegram messages (as 
        many as you want), also you can attach all types of media files. When you finish send /setanswer. After that, 
        list all possible answers in different messages. When you done with the answer send /end to finish your 
        question. On every stage you can check your question by sending /preview.""")

    def __new(self, update, context):
        metadata = self.__get_chat_meta(update, context)
        if metadata['action'] is not None:
            update.effective_message.reply_text(
                text='Please finish your question or answer /setanswer or /end')
            return

        name = '_'.join(context.args)
        if self.__check_name(name):
            metadata['name'] = name
        else:
            update.effective_message.reply_text(text=name + " is not valid")
            return
        metadata['action'] = 'question'
        metadata['puzzle_buffer'].append([])
        metadata['answer_buffer'].append([])
        if len(metadata['puzzle_buffer']) > 1:
            metadata['puzzle_buffer'].pop(0)
        if len(metadata['answer_buffer']) > 1:
            metadata['answer_buffer'].pop(0)
        update.effective_message.reply_text(
            text="Go ahead! Send your puzzle as a normal messages and then write /setanswer")

    def __data_getter(self, update, context):
        metadata = self.__get_chat_meta(update, context)
        if not update.message:
            update.effective_message.reply_text(text="Editing is not allowed in puzzle writer. Please use /dellastupd "
                                                     "to change previous sentence.")
            return
        if metadata['action'] == 'question':
            QReadWrite.push_puzzle(update.message, metadata['puzzle_buffer'][-1])
        elif metadata['action'] == 'answer':
            if update.message.text:
                QReadWrite.push_answer(update.message, metadata['answer_buffer'][-1])
            else:
                update.message.reply_text(
                    text="In current version answer can be only a text")

    def __end(self, update, context):
        metadata = self.__get_chat_meta(update, context)
        if metadata['action'] != 'answer' or len(metadata['answer_buffer'][-1]) < 1:
            update.effective_message.reply_text(
                text="Please specify answer first /setanswer or start new question /new")
            return
        metadata['action'] = None
        update.effective_message.reply_text(text='Thanx!')
        filename = QReadWrite.save_to_file(metadata['puzzle_buffer'][-1], metadata['answer_buffer'][-1],
                                           update.effective_message.from_user, metadata,
                                           puzzle_dir=self.config.working_path,
                                           bot=context.bot,
                                           save_media=self.config.save_media
                                           )
        self.logger.info('New puzzle saved from %s, filename %s',
                         update.effective_user, filename)

    def __set_answer(self, update, context):
        metadata = self.__get_chat_meta(update, context)
        if metadata['action'] != 'question' or len(metadata['puzzle_buffer'][-1]) == 0:
            update.effective_message.reply_text(
                text="Please begin question or finish previous answer /new or /end")
            return
        metadata['action'] = 'answer'
        update.effective_message.reply_text(text="Enter all possible answers in different messages.When you finish "
                                                 "enter /end.\n If you want to add correct guess, fill it in tildas: "
                                                 "~guess~Message, and the Message will appear after that guess.\n If "
                                                 "you want to add hint, fill it in triangular brakets: <Hint>, "
                                                 "and that Hint will appear in puzzle after /hint command")

    def __preview(self, update, context):
        metadata = self.__get_chat_meta(update, context)
        if metadata['action']:
            if len(metadata['puzzle_buffer'][-1]) > 0:
                if metadata['name']:
                    update.effective_message.reply_text(
                        text="Name: " + " ".join(metadata['name'].split('_')))

                QReadWrite.send(metadata['puzzle_buffer'][-1], context.bot,
                                update.effective_message.chat_id)

            else:
                update.effective_message.reply_text(text="Nothing in buffer")
            if metadata['action'] == 'answer' or metadata['action'] is None:
                answs = "Answers: "
                sep_a = ''
                guess = "Guess: "
                sep_g = ''
                hint = "Hint: "
                sep_h = ''
                for answ in metadata['answer_buffer'][-1]:
                    if answ.startswith('?') and len(answ[1:].split('?')) == 2:
                        temp = answ[1:].split('?')
                        guess += sep_g + temp[0] + ' "' + temp[1] + '"'
                        sep_g = ', '
                    elif answ.startswith("<") and answ.endswith(">"):
                        hint += sep_h + answ[1:-1]
                        sep_h = ', '
                    else:
                        answs += sep_a + answ
                        sep_a = ', '
                update.effective_message.reply_text(
                    text=answs + "\n" + guess + "\n" + hint)
        else:
            update.effective_message.reply_text(text="Nothing in buffer")

    @staticmethod
    def __check_name(name):
        restricted_chars = set('< >|\:()&;.,-?*')
        if any((c in restricted_chars) for c in name):
            return False
        else:
            return True

    def __set_name(self, update, context):
        metadata = self.__get_chat_meta(update, context)
        if metadata['action'] == 'question' or metadata['action'] == 'answer':
            name = '_'.join(context.args)
            if self.__check_name(name):
                metadata['name'] = name
                update.effective_message.reply_text(text="New name: " + name)
            else:
                update.effective_message.reply_text(text=name + " is not valid")
        else:
            update.effective_message.reply_text(
                text="Question already saved. Please specify a name before calling /end next time")

    def __delete_last_update(self, update, context):
        metadata = self.__get_chat_meta(update, context)
        if metadata['action'] == 'question' and len(metadata['puzzle_buffer'][-1]) > 0:
            del metadata['puzzle_buffer'][-1][-1]
            update.effective_message.reply_text(text='Successfully deleted from buffer')
            return
        if metadata['action'] == 'answer' and len(metadata['answer_buffer'][-1]) > 0:
            del metadata['answer_buffer'][-1][-1]
            update.effective_message.reply_text(text='Successfully deleted from buffer')
            return
        update.effective_message.reply_text(text='Nothing to delete')

    def __delete_last_question(self, update, context):
        metadata = self.__get_chat_meta(update, context)
        smth_del = False
        if metadata['action'] == 'question' and len(metadata['puzzle_buffer']) > 0:
            del metadata['puzzle_buffer'][-1]
            update.effective_message.reply_text(
                text='Successfully deleted full question from buffer')
            smth_del = True
        if metadata['action'] == 'answer' and len(metadata['answer_buffer']) > 0:
            del metadata['puzzle_buffer'][-1]
            del metadata['answer_buffer'][-1]
            update.effective_message.reply_text(
                text='Successfully deleted full question from buffer')
            smth_del = True
        if not smth_del:
            update.effective_message.reply_text(text='Nothing to delete')
        else:
            metadata['action'] = None

    @staticmethod
    def __help(update, context):
        update.effective_message.reply_text(text="""At first send /new [name] to start entering your question. 
    Send a text of your puzzle as a normal telegram messages (as many as you want), also
    you can attach all types of media files.
    When you finish send /setanswer. After that, list all possible answers in different messages.
    When you done with the answer send /end to finish your question. 
    On every stage you can check your question by sending /preview.""")

    def __hard_reset(self, update, context):
        metadata = self.__get_chat_meta(update, context)
        metadata['action'] = None
        metadata['puzzle_buffer'] = []
        metadata['answer_buffer'] = []

    def __get_current_state(self, update, context):
        metadata = self.__get_chat_meta(update, context)
        update.effective_message.reply_text(text=metadata['action'])

    def __set_game_folder(self, update, context):
        update.effective_message.reply_text(text='Choose game',
                                            reply_markup=QReadWrite.parse_game_folders_markup(self.config.working_path,
                                                                                              True))

    def __game_folder_button(self, update, context):
        query = update.callback_query
        metadata = self.__get_chat_meta(update, context)
        button = query.data.split('-')[-1]
        metadata['puzzle_folder'] = button
        query.edit_message_text(text='Writing to ' + button)

    def __get_game_folder(self, update, context):
        metadata = self.__get_chat_meta(update, context)
        update.effective_message.reply_text(text='Current game: ' + metadata["puzzle_folder"])

    def init_dispatcher(self, dispatcher):
        dispatcher.add_handler(CommandHandler("start", self.__start,
                                              pass_user_data=True, pass_chat_data=True
                                              ))
        dispatcher.add_handler(CommandHandler("new", self.__new,
                                              pass_user_data=True, pass_chat_data=True))
        dispatcher.add_handler(CommandHandler("setanswer", self.__set_answer,
                                              pass_user_data=True, pass_chat_data=True))
        dispatcher.add_handler(CommandHandler("setname", self.__set_name,
                                              pass_user_data=True, pass_chat_data=True))
        dispatcher.add_handler(CommandHandler("dellastupd", self.__delete_last_update,
                                              pass_user_data=True, pass_chat_data=True))
        dispatcher.add_handler(CommandHandler("dellastpuzzle", self.__delete_last_question,
                                              pass_user_data=True, pass_chat_data=True))
        dispatcher.add_handler(CommandHandler("preview", self.__preview))
        dispatcher.add_handler(CommandHandler("end", self.__end,
                                              pass_user_data=True, pass_chat_data=True))
        dispatcher.add_handler(CommandHandler("hardreset", self.__hard_reset, pass_user_data=True, pass_chat_data=True))
        dispatcher.add_handler(
            CommandHandler("curstate", self.__get_current_state, pass_user_data=True, pass_chat_data=True))

        dispatcher.add_handler(CommandHandler("setgame", self.__set_game_folder))
        dispatcher.add_handler(CommandHandler("getgame", self.__get_game_folder))
        dispatcher.add_handler(CommandHandler('help', self.__help))

        dispatcher.add_handler(CallbackQueryHandler(self.__game_folder_button, pattern='^puzzname'))
        dispatcher.add_handler(MessageHandler(~Filters.command, self.__data_getter))
