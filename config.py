# config.py

import os

# Базовые настройки
DEBUG = True
SECRET_KEY = "super-secret-key"

# Пути
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAVE_DIR = "/home/woodver/preset"

# Внешний API
EXTERNAL_API = "http://192.168.11.7"
