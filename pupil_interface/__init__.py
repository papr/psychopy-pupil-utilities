'''
(*)~----------------------------------------------------------------------------
Pupil Interface - A simple API for custom scripts to interact
                  with Pupil (eye tracking platform)
Copyright (C) 2016 Pablo Prietz

Distributed under the terms of the GNU Lesser General Public License (LGPL v3.0).
License details are in the file license.txt, distributed as part of this software.
----------------------------------------------------------------------------~(*)
'''

__version__ = '0.1.1'

import logging
logger = logging.getLogger(__name__)

from time import sleep,time
from signal import signal, SIGTERM, SIGINT
from pupil_sync_complete import Pupil_Sync_Node

logging.basicConfig(level=logging.INFO)

class Communicator(object):
    '''Provide simple interface to Pupil
    '''
    def __init__(self, arg):
        super(Communicator, self).__init__()
        self.node = Pupil_Sync_Node(
            name="Pupil Interface Node",
            time_grandmaster=False
        )
        
    def trigger(self,frameid=None,context=None):
        pass

    def startRecording(self,session_name):
        pass
    def stopRecording(self):
        pass

    def startCalibration(self,context=None):
        pass
    def stopCalibration(self):
        pass