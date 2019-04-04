from QAuthor import QAuthor
from QGame import QGame

if __name__ == "__main__":
    #auth = QAuthor("./configs/qauthor_config.yaml")
    #auth.start_polling(demon=False)

    game = QGame("./configs/qgame_config.yaml")
    game.start_polling(demon=False)