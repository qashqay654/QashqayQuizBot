from setuptools import setup,find_packages
print(find_packages())
setup(
    name='QQuizGame',
    version='0.4',
    packages=['QQuizGame'],
    url='https://github.com/qashqay654/QashqayQuizBot',
    license='Apache License 2.0',
    author='qashqay',
    author_email='qashqay.sol@yandex.ru',
    description='',
    install_requires=["python-telegram-bot>=12.0.0b1", "natsort"]
)
