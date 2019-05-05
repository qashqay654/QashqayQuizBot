# QashqayQuizBot

This bot is created to make simple quiz games.
It's a test project in aim of getting some experience in
telegram bots.

To start new bot clone this repo, exec 
```bash
git clone https://github.com/qashqay654/QashqayQuizBot.git ;
cd QashqayQuizBot ;
python setup.py install ;
```
After this steps you will have an installed version on bot kernels.
Then you can create new project folder and call environment generator:
```bash
cd ~ ; mkdir TestQQuizBot ; cd TestQQuizBot;
../QashqayQuizBot/make_new.py env ;
../QashqayQuizBot/make_new.py game ./game/test ; 
```

Copy sample configs from `configs` folder and fill them.
Copy `start_bots.py` to your folder and run it. If everything is ok, 
you should have two bots working on your machine.