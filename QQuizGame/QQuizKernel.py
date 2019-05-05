import os
import re

import numpy as np
import yaml
from natsort import natsorted

from QQuizGame.QReadWrite import QReadWrite
from QQuizGame.QTypes import AnswerCorrectness, FileType


class QQuizKernelConfig:
    def __init__(self, game_mode: str):
        with open(os.path.join(game_mode, 'config.yaml'), 'r') as handle:
            config = yaml.load(handle, Loader=yaml.BaseLoader)
            self.change_level_step = int(config['change_level_step'])
            self.random_levels = bool(int(config['random_levels']))
            self.allow_to_get_answer = bool(int(config['allow_to_get_answer']))
            self.intro_message = config['intro_message']


class QQuizKernel:

    def __init__(self, working_dir: str, last_question=0, bot=None, chat_id=None):

        # print("Game initialized")
        self.working_dir = working_dir
        self.config = QQuizKernelConfig(working_dir)

        self._last_question_num = last_question
        self.puzzle_dir = os.path.join(self.working_dir,
                                       self.__list_levels()[self._last_question_num])

        self.question = [[FileType.Text, "", "", False, False]]
        self.answer = [""]
        self.hint = [""]
        self.guess = [["", ""]]
        self.solved_levels = set()  # todo: запоминать пройденные уровни
        self.__get_question()
        if bot:
            bot.sendMessage(text=self.config.intro_message, chat_id=chat_id)

    def serialize_to_db(self):
        return self.working_dir, self._last_question_num

    def __list_levels(self):
        return natsorted([dr for dr in os.listdir(self.working_dir)
                          if os.path.isdir(os.path.join(self.working_dir, dr)) and not dr.startswith('-')])

    def __get_question(self):
        levels = self.__list_levels()
        self.puzzle_dir = os.path.join(self.working_dir, levels[self._last_question_num])
        self.question = QReadWrite.read_from_file(os.path.join(self.puzzle_dir, 'question.pickle'))
        pre_answer = QReadWrite.read_from_file(os.path.join(self.puzzle_dir, 'answer.pickle'))
        self.answer.clear()
        self.hint.clear()
        self.guess.clear()
        for answ in pre_answer:
            if answ.startswith('?') and len(answ[1:].split('?')) == 2:
                temp = answ[1:].split('?')
                self.guess.append([temp[0].strip().lower().replace('ё', 'е'), temp[1].strip()])
            elif answ.startswith("<") and answ.endswith(">"):
                self.hint.append(answ[1:-1].lower().strip())
            else:
                self.answer.append(answ.lower().strip().replace('ё', 'е'))
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
            return re.sub("(^|[.?!])\s*([a-zA-Zа-яА-я])", lambda p: p.group(0).upper(), ",".join(self.hint))
        else:
            return "Для этой загадки нет подсказок"

    def check_answer(self, answer):
        if answer.lower().replace('ё', 'е') in self.answer:
            # self.solved_levels.add(self._last_question_num)
            return AnswerCorrectness.CORRECT
        for guess in self.guess:
            if answer.lower().replace('ё', 'е') == guess[0]:
                return guess[1]
        else:
            return "Нет"

    @property
    def last_question_num(self):
        return self._last_question_num

    def next(self):
        levels = self.__list_levels()
        if self.config.random_levels:
            self._last_question_num = np.random.randint(0, len(levels))  # TODO: переделать, чтобы не повторялись уровни
        else:
            self._last_question_num += 1
        if self._last_question_num >= len(levels):
            self._last_question_num = len(levels) - 1

    def get_all_levels(self):
        if self.config.change_level_step:
            levels = self.__list_levels()
            return [level.split('-@') for level in levels[::self.config.change_level_step] if 'The End' not in level]
        else:
            return None

    def set_level(self, level):
        if self.config.change_level_step:
            self._last_question_num = level

    def set_level_by_name(self, name):
        if self.config.change_level_step:
            levels = self.__list_levels()
            if name in levels:
                self._last_question_num = levels.index(name)
            else:
                print('no such level', name, 'in', levels)

    def reset(self):
        self._last_question_num = 0

    def get_answer(self):
        if self.config.allow_to_get_answer:
            return re.sub("(^|[.?!])\s*([a-zA-Zа-яА-я])", lambda p: p.group(0).upper(), self.answer[0])
        else:
            return "В данной игре нельзя посмотреть ответ"
