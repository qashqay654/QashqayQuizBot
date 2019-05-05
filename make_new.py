
import os
import pickle
import sys
import argparse

from QQuizGame.Types import FileType

DEFAULT_GAME_CONFIG = '''change_level_step: 0
random_levels: 0
allow_to_get_answer: 0
intro_message: Hello, world!'''


def dir_creator(path):
    folders = []
    while 1:
        path, folder = os.path.split(path)

        if folder != "":
            folders.append(folder)
        else:
            if path != "":
                folders.append(path)

            break

    folders.reverse()
    tmp_fold = ''
    for fold in folders:
        tmp_fold = os.path.join(tmp_fold, fold)
        if not os.path.exists(tmp_fold):
            print('making dir', tmp_fold)
            os.mkdir(tmp_fold)
    return tmp_fold


def make_new_game(name):
    sample_game = os.path.join(name, 'master', '999-@The End')
    dir_creator(sample_game)

    sample_config = DEFAULT_GAME_CONFIG

    sample_question = [[FileType.Text,
                        'Тебе под силу все вопросы на текущий момент! Это очень круто! Если у тебя есть интересные загадки, то можешь прислать их в @QashqayAuthorBot.',
                        '',
                        False,
                        False]]
    sample_answer = ['42']

    with open(os.path.join(name, 'master', 'config.yaml'), 'w') as handle:
        handle.write(sample_config)
    with open(os.path.join(sample_game, 'question.pickle'), 'wb') as handle:
        pickle.dump(sample_question, handle)
    with open(os.path.join(sample_game, 'answer.pickle'), 'wb') as handle:
        pickle.dump(sample_answer, handle)
    print("Success")

def make_new_env(game_path=None, logs_path=None, users_data_path=None):
    if not game_path:
        game_path = "./game/"

    if os.path.exists(game_path):
        print(game_path + " already exists")
    else:
        os.mkdir(game_path)
        print(game_path + " created")

    if not logs_path:
        logs_path = "./logs/"

    if os.path.exists(logs_path):
        print(logs_path + " already exists")
    else:
        os.mkdir(logs_path)
        print(logs_path + " created")

    if not users_data_path:
        users_data_path = "./users_data/"

    if os.path.exists(users_data_path):
        print(users_data_path + " already exists")
    else:
        os.mkdir(users_data_path)
        print(users_data_path + " created")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("type", type=str,
                        choices=['game', 'env'])
    parser.add_argument("-gp", "--gamepath", type=str,
                        default=None,
                        help='Path to the game storage'
                        )
    parser.add_argument("-lp", "--logpath", type=str,
                        default=None,
                        help='Path to the logs storage'
                        )
    parser.add_argument("-up", "--userpath", type=str,
                        default=None,
                        help='Path to the users db storage'
                        )
    parser.add_argument("gamename", type=str,
                        nargs="?",
                        default=None,
                        help='Name of the new game'
                        )
    args = parser.parse_args()
    if args.type == 'game':
        if not args.gamename:
            raise ValueError("game name is required")

        make_new_game(args.gamename)
    elif args.type == 'env':
        make_new_env(args.gamepath,
                     args.logpath,
                     args.userpath
                     )