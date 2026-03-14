import time

from logs import taglog

def begin_polling():
    """
    Begin polling for new YouTube videos.
    """
    taglog("YOUTUBE", "Starting YouTube polling...")
    while True:
        try:
            check_for_new_videos()
        except Exception as e:
            taglog("YOUTUBE", f"Error during polling: {e}")
        time.sleep(60)  # Poll every 60 seconds