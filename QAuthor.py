import logging
from collections import defaultdict
import yaml
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, PicklePersistence, CallbackQueryHandler

from QReadWrite import QReadWrite


class QAuthorConfig:
    working_path = ""
    logger_path = ""
    token = ""
    save_media = True
    user_db_path = ""

    def __init__(self, config):
        with open(config, 'r') as handle:
            config = yaml.load(handle, Loader=yaml.BaseLoader)

            self.working_path = config['working_path']
            self.logger_path = config['logger_path']
            self.token = config['token']
            self.save_media = bool(config['save_media'])
            self.user_db_path = config['user_db_path']

    def __str__(self):
        return self.working_path + " " + self.logger_path + " " + str(self.save_media)


class QAuthor:

    def __init__(self, config_path):
        self.puzzle_buffer = defaultdict(list)
        self.answer_buffer = defaultdict(list)
        self.config = QAuthorConfig(config_path)

        puzzles_db = PicklePersistence(filename=self.config.user_db_path)
        self.updater = Updater(self.config.token, use_context=True, persistence=puzzles_db)
        self.init_dispatcher(self.updater.dispatcher)
        logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                            level=logging.INFO,
                            filename=self.config.logger_path,
                            filemode='a'
                            )
        self.logger = logging.getLogger(__name__)

    def start_polling(self, demon=True):
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
        return metadata

    def __start(self, update, context):
        metadata = self.__get_chat_meta(update, context)
        if not metadata:
            metadata['action'] = None
            metadata['question_num'] = defaultdict(int)
            metadata["puzzle_folder"] = "random_flood"
            metadata["name"] = ""
            self.logger.info('New user added %s', update.message.from_user)
        update.message.reply_text(text="""Hello! Welcome to the Puzzle Writer!
        How it works? At first send /new [name] to start entering your question. 
        Send a text of your puzzle as a normal telegram messages (as many as you want), also you can attach all types of media files.
        When you finish send /setanswer. After that, list all possible answers in different messages.
        When you done with the answer send /end to finish your question. 
        On every stage you can check your question by sending /preview.""")

    def __new(self, update, context):
        from_user = update.message.from_user.id
        metadata = self.__get_chat_meta(update, context)
        if metadata['action'] is not None:
            update.message.reply_text(
                text='Please finish your question or answer /setanswer or /end')
            return
        metadata['action'] = 'question'
        name = '_'.join(context.args)
        metadata['name'] = name
        self.puzzle_buffer[from_user].append([])
        self.answer_buffer[from_user].append([])
        if len(self.puzzle_buffer[from_user]) > 1:
            self.puzzle_buffer[from_user].pop(0)
        if len(self.answer_buffer[from_user]) > 1:
            self.answer_buffer[from_user].pop(0)
        update.message.reply_text(
            text="Go ahead! Send your puzzle as a normal messages and then write /setanswer")

    def __data_getter(self, update, context):
        from_user = update.message.from_user.id
        metadata = self.__get_chat_meta(update, context)
        if metadata['action'] == 'question':
            QReadWrite.push_puzzle(update.message, self.puzzle_buffer[from_user][-1])
        elif metadata['action'] == 'answer':
            if update.message.text:
                QReadWrite.push_answer(update.message, self.answer_buffer[from_user][-1])
            else:
                update.message.reply_text(
                    text="In current version answer can be only a text")

    def __end(self, update, context):
        metadata = self.__get_chat_meta(update, context)
        from_user = update.message.from_user.id
        if metadata['action'] != 'answer' or len(self.answer_buffer[from_user][-1]) < 1:
            update.message.reply_text(
                text="Please specify answer first /setanswer or start new question /new")
            return
        metadata['action'] = None
        update.message.reply_text(text='Thanx!')
        filename = QReadWrite.save_to_file(self.puzzle_buffer[from_user][-1], self.answer_buffer[from_user][-1],
                                                  update.message.from_user, metadata,
                                                  puzzle_dir=self.config.working_path,
                                                  bot=context.bot,
                                                  save_media=self.config.save_media
                                                  )
        self.logger.info('New puzzle saved from %s, filename %s',
                         update.message.from_user, filename)

    def __set_answer(self, update, context):
        from_user = update.message.from_user.id
        metadata = self.__get_chat_meta(update, context)
        if metadata['action'] != 'question' or len(self.puzzle_buffer[from_user][-1]) == 0:
            update.message.reply_text(
                text="Please begin question or finish previous answer /new or /end")
            return
        metadata['action'] = 'answer'
        update.message.reply_text(text="Enter all possible answers in different messages.When you finish enter /end.\n\
    If you want to add correct guess, fill it in tildas: ~guess~Message, and the Message will appear after that guess.\n\
    If you want to add hint, fill it in triangular brakets: <Hint>, and that Hint will appear in puzzle after /hint command")

    def __preview(self, update, context):
        metadata = self.__get_chat_meta(update, context)
        from_user = update.message.from_user.id
        if metadata['name']:
            update.message.reply_text(
                text="Name: " + " ".join(metadata['name'].split('_')))
        if len(self.puzzle_buffer[from_user][-1]) > 0:
            QReadWrite.send(self.puzzle_buffer[from_user][-1], context.bot,
                                   update.message.chat_id, preview=True)
        else:
            update.message.reply_text(text="Nothing in buffer")
        if metadata['action'] == 'answer' or metadata['action'] is None:
            answs = "Answers: "
            sep_a = ''
            guess = "Guess: "
            sep_g = ''
            hint = "Hint: "
            sep_h = ''
            for answ in self.answer_buffer[from_user][-1]:
                if answ.startswith('~'):
                    temp = answ[1:].split('~')
                    guess += sep_g + temp[0] + ' "' + temp[1] + '"'
                    sep_g = ', '
                elif answ.startswith("<") and answ.endswith(">"):
                    hint += sep_h + answ[1:-1]
                    sep_h = ', '
                else:
                    answs += sep_a + answ
                    sep_a = ', '
            update.message.reply_text(
                text=answs + "\n" + guess + "\n" + hint)

    def __set_name(self, update, context):
        metadata = self.__get_chat_meta(update, context)
        if metadata['action'] == 'question' or metadata['action'] == 'answer':
            name = '_'.join(context.args)
            metadata['name'] = name
            update.message.reply_text(text="New name set")
        else:
            update.message.reply_text(
                text="Question already saved. Please specify a name before calling /end next time")

    def __delete_last_update(self, update, context):
        from_user = update.message.from_user.id
        metadata = self.__get_chat_meta(update, context)
        if metadata['action'] == 'question' and len(self.puzzle_buffer[from_user][-1]) > 0:
            del self.puzzle_buffer[from_user][-1][-1]
            update.message.reply_text(text='Successfully deleted from buffer')
            return
        if metadata['action'] == 'answer' and len(self.answer_buffer[from_user][-1]) > 0:
            del self.answer_buffer[from_user][-1][-1]
            update.message.reply_text(text='Successfully deleted from buffer')
            return
        update.message.reply_text(text='Nothing to delete')

    def __delete_last_question(self, update, context):
        from_user = update.message.from_user.id
        metadata = self.__get_chat_meta(update, context)
        smth_del = False
        if metadata['action'] == 'question' and len(self.puzzle_buffer[from_user]) > 0:
            del self.puzzle_buffer[from_user][-1]
            update.message.reply_text(
                text='Successfully deleted full question from buffer')
            smth_del = True
        if metadata['action'] == 'answer' and len(self.answer_buffer[from_user]) > 0:
            del self.puzzle_buffer[from_user][-1]
            del self.answer_buffer[from_user][-1]
            update.message.reply_text(
                text='Successfully deleted full question from buffer')
            smth_del = True
        if not smth_del:
            update.message.reply_text(text='Nothing to delete')
        else:
            metadata['action'] = None

    def __help(self, update, context):
        update.message.reply_text(text="""At first send /new [name] to start entering your question. 
    Send a text of your puzzle as a normal telegram messages (as many as you want), also
    you can attach all types of media files.
    When you finish send /setanswer. After that, list all possible answers in different messages.
    When you done with the answer send /end to finish your question. 
    On every stage you can check your question by sending /preview.""")

    def __hard_reset(self, update, context):
        from_user = update.message.from_user.id
        metadata = self.__get_chat_meta(update, context)
        metadata['action'] = None
        self.puzzle_buffer[from_user] = []
        self.answer_buffer[from_user] = []

    def __get_current_state(self, update, context):
        metadata = self.__get_chat_meta(update, context)
        update.message.reply_text(text=metadata['action'])

    def __set_game_folder(self, update, context):
        update.message.reply_text(text='Choose game',
                                  reply_markup=QReadWrite.parse_game_folders_markup(update,
                                                                                           self.config.working_path))

    def __game_folder_button(self, update, context):
        query = update.callback_query
        metadata = self.__get_chat_meta(query, context)
        button = query.data.split('-')[-1]
        metadata['puzzle_folder'] = button
        query.edit_message_text(text='Writing to ' + button)

    def __get_game_folder(self, update, context):
        metadata = self.__get_chat_meta(update, context)
        update.message.reply_text(text='Current game: ' + metadata["puzzle_folder"])

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