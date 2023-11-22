import os
import logging

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'ERROR',
            'class': 'logging.FileHandler',
            'filename': os.path.join(os.path.dirname(__file__), 'error.log'),
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file'],
            'level': os.getenv('DJANGO_LOG_LEVEL', 'ERROR'),
        },
    },
}