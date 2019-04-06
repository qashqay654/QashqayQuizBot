import os
import yaml
import numpy as np

from QReadWrite import QReadWrite
from QTypes import AnswerCorrectness, FileType


class QQuizKernelConfig:
    def __init__(self, game_mode: str):
        with open(os.path.join(game_mode, 'config.yaml'), 'r') as handle:
            config = yaml.load(handle, Loader=yaml.BaseLoader)
            self.allow_to_change_level = bool(int(config['allow_to_change_level']))
            self.random_levels = bool(int(config['random_levels']))
            self.allow_to_get_answer = bool(int(config['allow_to_get_answer']))
            self.intro_message = config['intro_message']


class QQuizKernel:

    def __init__(self, working_dir: str, game_mode: str, bot=None, chat_id=None):

        self.working_dir = os.path.join(working_dir, game_mode, 'master')
        self.config = QQuizKernelConfig(os.path.join(working_dir, game_mode))

        self.levels = sorted([dr for dr in os.listdir(self.working_dir) \
                              if os.path.isdir(os.path.join(self.working_dir, dr))])
        self._last_question_num = 0
        self.puzzle_dir = os.path.join(self.working_dir, self.levels[self._last_question_num])

        self.question = [[FileType.Text, "", "", False, False]]
        self.answer = [""]
        self.hint = [""]
        self.guess = [["", ""]]
        self.__get_question()
        if bot:
            bot.sendMessage(text=self.config.intro_message, chat_id=chat_id)

    def __get_question(self):
        self.levels = sorted([dr for dr in os.listdir(self.working_dir) \
                              if os.path.isdir(os.path.join(self.working_dir, dr))])
        self.puzzle_dir = os.path.join(self.working_dir, self.levels[self._last_question_num])
        self.question = QReadWrite.read_from_file(os.path.join(self.puzzle_dir, 'question.pickle'))
        pre_answer = QReadWrite.read_from_file(os.path.join(self.puzzle_dir, 'answer.pickle'))
        self.answer.clear()
        self.hint.clear()
        self.guess.clear()
        for answ in pre_answer:
            if answ.startswith('/') and len(answ[1:].split('/')) == 2:
                temp = answ[1:].split('/')
                self.guess.append([temp[0].strip().lower(), temp[1].strip()])
            elif answ.startswith("<") and answ.endswith(">"):
                self.hint.append(answ[1:-1].lower().strip())
            else:
                self.answer.append(answ.lower().strip())
        if not len(self.answer):
            self.answer.append("")
        if not len(self.hint):
            self.hint.append("")
        if not len(self.guess):
            self.guess.append(["", ""])

    def get_new_question(self):
        self.__get_question()
        return self.question, self.puzzle_dir

    def get_hint(self):
        if self.hint[-1]:
            return ",".join(self.hint)
        else:
            return "Для этой загадки нет подсказок"

    def check_answer(self, answer):
        if answer.lower() in self.answer:
            return AnswerCorrectness.CORRECT
        for guess in self.guess:
            if answer.lower() == guess[0]:
                return guess[1]
        else:
            return "Нет"

    @property
    def last_question_num(self):
        return self._last_question_num

    def next(self):
        if self.config.random_levels:
            self._last_question_num = np.random.randint(0, len(self.levels))
        else:
            self._last_question_num += 1
        if self._last_question_num >= len(self.levels):
            self._last_question_num = len(self.levels) - 1

    def get_all_levels(self):
        if self.config.allow_to_change_level:
            return [level.split('-@') for level in self.levels]
        else:
            return None

    def set_level(self, level):
        if self.config.allow_to_change_level:
            self._last_question_num = level

    def reset(self):
        self._last_question_num = 0

    def get_answer(self):
        if self.config.allow_to_get_answer:
            return self.answer[0]
        else:
            return "В данной игре нельзя посмотреть ответ"

# TODO: add level choose to game.
# TODO: get answer
# TODO: перевести на русский