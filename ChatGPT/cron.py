import logging
from ChatGPT.models import TelegramUsers
from ChatGPT.views import Console

logging.basicConfig(filename="status_log.log", filemode="a",
                    format="%(asctime)s %(levelname)s %(message)s")


def everyday_update():
    all_users = TelegramUsers.objects.all()
    for user in all_users:
        user.set_rpd(5)
    logging.basicConfig(
        handlers=[
            logging.FileHandler(
                "status_log.log",
                'a',
                'utf-8'
            )
        ],
        level=logging.ERROR,
        format='%(asctime)s - %(levelname)s : %(message)s'
    )
    logging.info("All users update!")
