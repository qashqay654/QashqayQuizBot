import sys
import pickle
import os

from QTypes import FileType


def make_new_game(name):
    path = os.path.join('./game', name)
    if os.path.exists(path):
        print("Game is already made")
        return
    os.mkdir(path)
    os.mkdir(os.path.join(path, 'master'))
    sample_config = '''change_level_step: 0
random_levels: 0
allow_to_get_answer: 0
intro_message: Hello, world!'''
    with open(os.path.join(path, 'master', 'config.yaml'), 'w') as handle:
        handle.write(sample_config)
    sample_game = os.path.join(path, 'master', '999-@The End')
    os.mkdir(sample_game)
    sample_question = [[FileType.Text,
                        'Тебе под силу все вопросы на текущий момент! Это очень круто! Если у тебя есть интересные загадки, то можешь прислать их в @QashqayAuthorBot.',
                        '',
                        False,
                        False]]
    sample_answer = ['42']
    with open(os.path.join(sample_game, 'question.pickle'), 'wb') as handle:
        pickle.dump(sample_question, handle)
    with open(os.path.join(sample_game, 'answer.pickle'), 'wb') as handle:
        pickle.dump(sample_answer, handle)
    print("Success")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not len(args):
        print("Set game name as an argument")
    else:
        name = ' '.join(args)
        make_new_game(name)