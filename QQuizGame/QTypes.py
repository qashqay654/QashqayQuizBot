from enum import Enum, auto


class ConversationType(Enum):
    PRIVATE = 0
    GROUP = 1


class AnswerCorrectness(Enum):
    CORRECT = 0
    CLOSE = 1
    WRONG = 2


class FileType(Enum):
    Text = auto()
    Location = auto()
    Contact = auto()

    Photo = auto()
    Sticker = auto()
    Audio = auto()
    Voice = auto()
    Video = auto()
    VideoNote = auto()
    Document = auto()
    Animation = auto()


class AnswerType(Enum):
    Single = auto()
    Multiple = auto()
