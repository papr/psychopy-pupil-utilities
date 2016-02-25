import logging
logger = logging.getLogger(__name__)

from time import sleep,time
from signal import signal, SIGTERM, SIGINT
from pupil_sync_complete import Pupil_Sync_Node

logging.basicConfig(level=logging.INFO)
node = Pupil_Sync_Node(name="Script Node",time_grandmaster=False)

running = True
def quit(signum, frame):
    global running
    running = False
signal(SIGTERM, quit)
signal(SIGINT, quit)

while running:
    sleep(1)
    print node.sync_status_info(),node.get_time()
    node.request_group_timestamps()
node.close()