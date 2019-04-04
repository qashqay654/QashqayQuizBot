from QAuthor import QAuthor

if __name__ == "__main__":

    auth = QAuthor("./configs/qauthor_config.yaml")
    auth.start_polling(demon=True)