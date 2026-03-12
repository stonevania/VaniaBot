from pathlib import Path
import os
import logging

script_dir = Path(__file__).parent
file_path = script_dir / "bot.log"
logger = logging.FileHandler(filename="discord.log", encoding="utf-8", mode="w")

def getLogger():
    return logger

def taglog(src, msg):
    print(f"[{src}] {msg}")

    try:
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(f"[{src}] {msg}\n")
    except Exception as e:
        print(f"Failed to log message: {e}")