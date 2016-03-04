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

# standard libary
from time import sleep,time
from signal import signal, SIGTERM, SIGINT
from threading import Event
from Queue import Queue
import json

# network
import zmq
from pyre import zhelper

# local package
from pupil_sync_complete import Pupil_Sync_Node, exit_thread
from const import *

logging.basicConfig(level=logging.DEBUG)

class Communicator(Pupil_Sync_Node):
    '''Provide simple interface to Pupil

    Callbacks:
    Are called i.a. when the Communicator receives notifications
    over the network. They include a timestamp since reception of
    notifications might be delayed.

    - connection_callback()

    - calibration_callback(event, timestamp, context)
        event: calibration callback event constant from 'const'
        timestamp: time of event
        context:
            - String, reason of failure on CALIBRATION_FAILED
            - String, name of calibration method on CALIBRATION_SUCCESSFULL
            - None, else

    - recording_callback(event, timestamp, context)
        event: recording callback event constant from 'const'
        timestamp: time of event
        context: Dict including
            - 'rec_path': Recording path (always present)
            - 'session_name': Name of recording session
                (Only present on RECORDING_STARTED)
    '''

    def __init__(self, **kwargs):
        if not 'name' in kwargs:
            kwargs['name'] = 'Pupil Interface Node'
        self._time_sync_node = None
        super(Communicator, self).__init__(**kwargs)
        self.sub_addr = kwargs.get('sub_addr','tcp://127.0.0.1')
        
        # set callbacks to None
        self.connection_callback = None
        self.calibration_callback = None
        self.recording_callback = None

        self.sub_pipe = zhelper.zthread_fork(self.context, self._sub_loop)
        self.event_q = Queue()
        # used to wait for events in wait*() calls
        self.wait_event = Event()

    def startRecording(self,session_name="Unnamed session",callback=None):
        if callback: self.recording_callback = callback
        self.notify_all({
            'subject': 'rec_should_start',
            'source': RECORDING_SOURCE_PUPIL_INTERFACE,
            'session_name': session_name,
            'network_propagate': True
        })
    def stopRecording(self,callback=None):
        if callback: self.recording_callback = callback
        self.notify_all({
            'subject': 'rec_should_stop',
            'source': RECORDING_SOURCE_PUPIL_INTERFACE,
            'network_propagate': True
        })

    def startCalibration(self,callback=None,context=None):
        logger.debug('startCalibration(%s, %s)'%(callback,context))
        if callback: self.calibration_callback = callback
        self.notify_all({
            'subject': 'cal_should_start',
            'network_propagate': True
        })

    def stopCalibration(self,callback=None):
        if callback: self.calibration_callback = callback
        self.notify_all({
            'subject': 'cal_should_stop',
            'network_propagate': True
        })

    def checkEvents(self):
        """
        Checks for events and calls appropriate callbacks.
        Should be called from the main thread.
        """
        processed_events = []
        while not self.event_q.empty():
            event = self.event_q.get()
            if 'notification' in event:
                n = event['notification']
                e = self._handle_notification(n)
                processed_events.insert(0, (e,n) )
            elif 'gaze_positions' in event:
                p = event['gaze_positions']
                logger.debug('Received gaze positions')
                processed_events.insert(0, (RCV_GAZE,p) )
            else:
                logger.warning('Unknown event: %s'%event)
        return processed_events

    def waitEvents(self,events,timeout=None):
        '''
        Waits and blocks the current thread until a specific event happens

        When the timeout argument is present and not None,
        it should be a floating point number specifying a
        timeout for the operation in seconds (or fractions thereof).
        '''
        while True:
            processed = self.checkEvents()
            for e,obj in processed:
                if isinstance(events, list) and e in events:
                    return (e,obj)
                elif e == events:
                    return (e,obj)
            # blocks thread until new events arrive
            self.wait_event.wait(timeout)

    @property
    def time_sync_node(self):
        return self._time_sync_node

    @time_sync_node.setter
    def time_sync_node(self, node):
        self._time_sync_node = node
        # TODO: network callback
    
    def on_notify(self,notification):
        self.event_q.put({'notification':notification})
        self.wait_event.set()
        self.wait_event.clear()

    def _handle_notification(self,notification):
        logger.warning(notification)

        event = None
        ts = notification.get('timestamp',None)

        if notification.get('subject',None) == 'calibration marker found':
            event = self._callCalibrationCallback(CAL_SMF,ts, None)
        
        elif notification.get('subject',None) == 'calibration marker sample completed':
            event = self._callCalibrationCallback(CAL_SC,ts, None)
        
        elif notification.get('subject',None) == 'calibration marker moved too quickly':
            event = self._callCalibrationCallback(CAL_MMTQ,ts, None)
        
        elif notification.get('subject',None) == 'calibration_successful':
            method = notification['method']
            event = self._callCalibrationCallback(CAL_SUC,ts, method)
        
        elif notification.get('subject',None) == 'calibration_failed':
            reason = notification['reason']
            event = self._callCalibrationCallback(CAL_FAIL,ts, reason)

        elif (notification.get('subject',None) == 'rec_started' and 
            notification.get('source',None) != RECORDING_SOURCE_PUPIL_INTERFACE):
            event = self._callRecordingCallback(REC_STA, ts, {
                'rec_path': notification['rec_path'],
                'session_name': notification['session_name']
            })

        elif (notification.get('subject',None) == 'rec_stopped' and 
            notification.get('source',None) != RECORDING_SOURCE_PUPIL_INTERFACE):
            event = self._callRecordingCallback(RECORDING_STOPPED, ts, {
                'rec_path': notification['rec_path']
            })
        return event

    def _sub_loop(self,context,pipe):
        port = "5000"
        socket = context.socket(zmq.SUB)
        socket.connect(self.sub_addr+':'+port)
        #get gaze data only
        socket.setsockopt(zmq.SUBSCRIBE, 'gaze_positions')

        poller = zmq.Poller()
        poller.register(pipe, zmq.POLLIN)
        poller.register(socket, zmq.POLLIN)

        while True:
            try:
                #this should not fail but it does sometimes. We need to clean this out.
                # I think we are not treating sockets correclty as they are not thread-save.
                items = dict(poller.poll())
            except zmq.ZMQError:
                logger.warning('Socket fail.')
                continue

            # get socket events
            if socket in items and items[socket] == zmq.POLLIN:
                topic,msg  = socket.recv_multipart()
                gaze_positions = json.loads(msg)
                self.event_q.put({topic:gaze_positions})
                self.wait_event.set()
                self.wait_event.clear()

            if pipe in items and items[pipe] == zmq.POLLIN:
                message = pipe.recv()
                # message to quit
                if message.decode('utf-8') == exit_thread:
                    break
        self.sub_pipe = None

    def _callCalibrationCallback(self, event, timestamp, context):
        if self._isValidCallback(self.calibration_callback):
            self.calibration_callback(event, timestamp, context)
        return event

    def _callRecordingCallback(self, event, timestamp, context):
        if self._isValidCallback(self.recording_callback):
            self.recording_callback(event, timestamp, context)
        return event

    def _isValidCallback(self,cb):
        return cb and hasattr(cb, '__call__')

    def close(self):
        self.sub_pipe.send(exit_thread)
        while self.sub_pipe:
            sleep(.01)
        super(Communicator, self).close()