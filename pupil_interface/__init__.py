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
from zmq.utils.monitor import recv_monitor_message
from pyre import zhelper

# local package
from pupil_sync_complete import Pupil_Sync_Node, exit_thread
from const import *

logging.basicConfig(level=logging.INFO)

class Communicator(Pupil_Sync_Node):
    '''Provide simple interface to Pupil

    Callbacks:
    Are called i.a. when the Communicator receives notifications
    over the network. They include a timestamp since reception of
    notifications might be delayed.

    - network_callback(event, context)
        event: NET_JOIN or NET_EXIT
        context: dict with uuid, name, group of origin

    - subscription_callback(event,context)
        event: EVENT_RECEIVED_GAZE_POSITIONS
        context: gaze position published by Pupil server

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
        super(Communicator, self).__init__(**kwargs)
        self.sub_addr = kwargs.get('sub_addr','tcp://127.0.0.1')
        self.sub_port = kwargs.get('sub_port','5000')
        # set callbacks to None
        self.network_callback = None
        self.subscription_callback = None
        self.calibration_callback = None
        self.recording_callback = None

        # used to wait for events in wait*() calls
        self.wait_event = Event()
        self.event_q = Queue()
        self.sub_pipe = zhelper.zthread_fork(self.context, self._sub_loop)

    #(*)~------------------------------------------------------------------~(*)#

    def startRecording(self,session_name="Unnamed session",callback=None):
        if callback: self.recording_callback = callback
        self.notify_all({
            'subject': 'should_start_recording',
            'source': RECORDING_SOURCE_PUPIL_INTERFACE,
            'session_name': session_name,
            'network_propagate': True
        })
    def stopRecording(self,callback=None):
        if callback: self.recording_callback = callback
        self.notify_all({
            'subject': 'should_stop_recording',
            'source': RECORDING_SOURCE_PUPIL_INTERFACE,
            'network_propagate': True
        })
    def startCalibration(self,callback=None):
        if callback: self.calibration_callback = callback
        self.notify_all({
            'subject': 'should_start_calibration',
            'network_propagate': True
        })
    def stopCalibration(self,callback=None):
        if callback: self.calibration_callback = callback
        self.notify_all({
            'subject': 'should_stop_calibration',
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
                self._callSubscriptionCallback(RCV_GAZE,p)
                processed_events.insert(0, (RCV_GAZE,p) )

            elif 'net_sync' in event:
                msg_type, cmds = event['net_sync']
                if msg_type == "JOIN":
                    uuid,name,group = cmds
                    if group == self.group:
                        e = {'uuid':uuid, 'name':name,'group':group}
                        processed_events.insert(0,(NET_JOIN,e))
                        self._callNetworkCallback(NET_JOIN,e)

                elif msg_type == "EXIT":
                    uuid,name,group = cmds
                    if group == self.group:
                        e = {'uuid':uuid, 'name':name,'group':group}
                        processed_events.insert(0,(NET_EXIT,e))
                        self._callNetworkCallback(NET_EXIT,e)

            elif 'net_subscription' in event:
                event_dict = event['net_subscription']
                if event_dict['event'] == zmq.EVENT_CONNECTED:
                    endp = event_dict['endpoint']
                    if endp == (self.sub_addr+':'+self.sub_port):
                        processed_events.insert(0,(NET_CONN,endp))
                        self._callNetworkCallback(NET_CONN,endp)
                elif event_dict['event'] == zmq.EVENT_DISCONNECTED:
                    endp = event_dict['endpoint']
                    if endp == (self.sub_addr+':'+self.sub_port):
                        processed_events.insert(0,(NET_DISC,endp))
                        self._callNetworkCallback(NET_DISC,endp)
            else:
                logger.warning('Unknown event: %s'%event)
        return processed_events

    def waitAnyEvent(self,events, timeout=None):
        '''
        Waits and blocks the current thread until a specified events happens.

        When the timeout argument is present and not None,
        it should be a floating point number specifying a
        timeout for the operation in seconds (or fractions thereof).
        '''
        return self._waitEvents(False,events,timeout)

    def waitAllEvents(self,events,timeout=None):
        '''
        Waits and blocks the current thread until all specified events happened.
        '''
        return self._waitEvents(True,events,timeout)

    def _waitEvents(self,waitForAll,events,timeout=None):
        event_pool = {}
        foundAtLeastOneSpecifiedEvent = False
        if timeout != None:
            deadline = self.get_time() + timeout
        while True:
            processed = self.checkEvents()
            for e,obj in processed:
                event_pool[e] = obj
                if isinstance(events, list) and e in events:
                    events.remove(e)
                    foundAtLeastOneSpecifiedEvent = True
                elif e == events:
                    return event_pool
                # if waitForAll: test if all events were found
                if not events or (not waitForAll and foundAtLeastOneSpecifiedEvent):
                    return event_pool
            if timeout and timeout <= 0:
                break
            if timeout != None:
                timeout = deadline - self.get_time()
            # blocks thread until new events arrive
            self.wait_event.wait(timeout)
        event_pool[TIME_OUT] = None
        return event_pool

    def close(self):
        if self.sub_pipe:
            self.sub_pipe.send(exit_thread)
            while self.sub_pipe:
                sleep(.01)
        super(Communicator, self).close()

    #(*)~------------------------------------------------------------------~(*)#

    def on_notify(self,notification):
        self.event_q.put({'notification':notification})
        self.wait_event.set()
        self.wait_event.clear()

    def _handle_notification(self,notification):
        '''
        Looks for specific notifications to trigger matching events.

        `notification` is the received notification dictionary.

        Returns event constant.

        Can be overwritten to support custom event notifications.
        Should call super(). If super() returns `None` the notification was not recognized.
        '''
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
            event = self._callRecordingCallback(REC_STO, ts, {
                'rec_path': notification['rec_path']
            })
        return event

    def _handle_network(self,network):
        '''
        Overwrite to get network events
        '''
        msg_type, cmds = super(Communicator, self)._handle_network(network)
        self.queueEvent({'net_sync':(msg_type,cmds)})
        return (msg_type, cmds)

    def _sub_loop(self,context,pipe):
        '''
        Subscription Thread Loop

        Connects to the Pupil Server given by `sub_addr:sub_port`.
        Adds
        '''
        socket = context.socket(zmq.SUB)
        network_mon = socket.get_monitor_socket()
        socket.connect(self.sub_addr+':'+self.sub_port)
        #get gaze data only
        socket.setsockopt(zmq.SUBSCRIBE, 'gaze_positions')

        poller = zmq.Poller()
        poller.register(pipe, zmq.POLLIN)
        poller.register(socket, zmq.POLLIN)
        poller.register(network_mon, zmq.POLLIN)

        while True:
            try:
                #this should not fail but it does sometimes. We need to clean this out.
                # I think we are not treating sockets correclty as they are not thread-save.
                items = dict(poller.poll())
            except zmq.ZMQError:
                logger.warning('Socket fail.')
                continue

            if network_mon in items and items[network_mon] == zmq.POLLIN:
                mon_msg = recv_monitor_message(network_mon)
                if mon_msg['event'] == zmq.EVENT_CONNECTED:
                    self.queueEvent({'net_subscription':mon_msg})
                # TODO: disconnect event?

            # get socket events
            if socket in items and items[socket] == zmq.POLLIN:
                topic,msg  = socket.recv_multipart()
                data = json.loads(msg)
                self.queueEvent({topic:data})

            if pipe in items and items[pipe] == zmq.POLLIN:
                message = pipe.recv()
                # message to quit
                if message.decode('utf-8') == exit_thread:
                    break
        self.sub_pipe = None
        network_mon.close()

    def _callCalibrationCallback(self, event, timestamp, context):
        if self._isValidCallback(self.calibration_callback):
            self.calibration_callback(event, timestamp, context)
        return event

    def _callRecordingCallback(self, event, timestamp, context):
        if self._isValidCallback(self.recording_callback):
            self.recording_callback(event, timestamp, context)
        return event

    def _callNetworkCallback(self, event, context):
        if self._isValidCallback(self.network_callback):
            self.network_callback(event,context)
        return event

    def _callSubscriptionCallback(self, event, context):
        if self._isValidCallback(self.subscription_callback):
            self.subscription_callback(event,context)
        return event

    def _isValidCallback(self,cb):
        return cb and hasattr(cb, '__call__')

    def queueEvent(self,event):
        self.event_q.put(event)
        self.wait_event.set()
        self.wait_event.clear()
