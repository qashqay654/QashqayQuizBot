

from QReadWrite import QReadWrite
from QTypes import AnswerCorrectness, FileType

class QQuizKernel:
    __last_question_num = 0

    def __init__(self, game_mode: str):
        self.__last_question_num = 0

    def get_new_question(self):
        #text = QUESTION[self.__language] + " " + \
        #    str(self.__last_question_num)+": "+u'счеты\n'
        #text += "(495)*5+(8182)"
        return [[FileType.Text, "123", "222", False, False]]

    def get_hint(self):
        return "456"

    def check_answer(self, answer):
        true_answer = '4852'
        close_guesses = []
        if answer == true_answer:
            return AnswerCorrectness.CORRECT
        elif answer in close_guesses:
            return '789'
        else:
            return '1011'

    @property
    def last_question_num(self):
        return self.__last_question_num

    @property
    def language(self):
        return self.__language

    def set_new_language(self, lang):
        self.__language = lang

    def next(self):
        self.__last_question_num += 1

    def reset(self):
        self.__last_question_num = 0