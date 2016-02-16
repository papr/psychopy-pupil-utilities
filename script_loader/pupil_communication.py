import os, sys, platform, logging, colorlog
from uuid import uuid4
from collections import namedtuple
if platform.system() == 'Darwin' and getattr(sys, 'frozen', False):
	from billiard import Process, Pipe, Queue, forking_enable
	forking_enable(0)
else:
	from multiprocessing import Process, Pipe

from const import (
	# commands
	START_CALIBRATION,
	STOP_CALIBRATION,
	START_RECORDING,
	STOP_RECORDING,
	TRIGGER,
	
	# concurrent action identifier
	ACTION_CALIBRATION,
	ACTION_RECORDING,
	
	EXIT,

	# callback statuscodes
	CBSC_STATUS_UNSPECIFIED,
	CBSC_CALIBRATION_SUCCESSFULL,
	CBSC_CALIBRATION_FAILED,
	CBSC_RECORDING_STARTED,
	CBSC_RECORDING_STOPPED
)

logger = colorlog.getLogger('pupil_communication')
logger.propagate = False
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logger.level)
ch.setFormatter(colorlog.ColoredFormatter(
	#"%(log_color)s%(levelname)-8s%(reset)s %(blue)s%(message)s",
	"WORLD Process [%(log_color)s%(levelname)s%(reset)s] %(name)s: %(message)s",
	datefmt=None,
	reset=True,
	log_colors={
		'DEBUG': 'cyan',
		'INFO': 'green',
		'WARNING': 'yellow',
		'ERROR': 'red',
		'CRITICAL': 'red,bg_white',
	},
	secondary_log_colors={},
	style='%'
))
logger.addHandler(ch)

class PupilCommunication:
	'''PupilCommunication
	'''

	'''StatusCallbackResponse
	changed: BOOL, True if status has changed
	status: STRING, new status as string
	statusCode: INT, new status as int, 0: done
	result: OBJECT, result object
	'''
	StatusCallbackResponse = namedtuple('StatusCallbackResponse',
		['changed', 'status', 'statusCode', 'result'])

	class TaskState:
		'''TaskState: Helper object to keep track of task states

		processed: BOOL, True if state change was processed
		status: STRING, current status as string
		statusCode: INT, current status as int, -1: unspecified, 0: done
		result: OBJECT, result object for current state
		'''
		def __init__(self,
				processed=True,
				status=None,
				statusCode=CBSC_STATUS_UNSPECIFIED,
				result=None):
			self.processed = processed
			self.status = status
			self.statusCode = statusCode
			self.result = result

		def __str__(self):
			return '<TaskState pr: %s, st: %s, stc: %i, r: %s>'%(
				self.processed,self.status,self.statusCode,self.result)
		def __repr__(self):
			return self.__str__()

		def callbackResponse(self):
			'''Generates StatusCallbackResponse from current state'''
			return PupilCommunication.StatusCallbackResponse(
					not self.processed,
					self.status,
					self.statusCode,
					self.result)

	def __init__(self, g_pool, cmd_pipe, event_queue):
		self.g_pool = g_pool
		self.cmd_pipe = cmd_pipe
		self.event_queue = event_queue
		self.recent_events = None
		self.states = {}

	def __create_status_callback(self,task_id):
		if task_id in self.states:
			raise Exception('Task with id %s already existing.'%task_id)

		# create entry for task_id
		self.states[task_id] = PupilCommunication.TaskState(True)

		def status_callback(blocking=True):	

			# Task not present anymore. 
			if not task_id in self.states:
				return PupilCommunication.StatusCallbackResponse(
					True,'unspecified',CBSC_STATUS_UNSPECIFIED,None)

			current_state = self.states[task_id]

			# unprocessed status change.
			if not current_state.processed:
				resp = current_state.callbackResponse()
				# cleanup if task is done or unspecified:
				if resp.statusCode <= 0:
					del self.states[task_id]
				# task not done, but current state is processed
				else:
					current_state.processed =  True
				return resp

			# current state was processed already; looking for updates
			while self.cmd_pipe and (self.cmd_pipe.poll() or blocking):
				msg = self.cmd_pipe.recv()
				resp_id = msg.get('id',None)
				status = msg.get('status', 'unspecified')
				statusCode = msg.get('statusCode', CBSC_STATUS_UNSPECIFIED)
				result = msg.get('result', None)

				# no response id found; ignore message
				if not resp_id:
					continue

				# update corresponding state
				# (including target state where resp_id == task_id,
				#  see case below)
				if resp_id in self.states:
					resp_state = self.states[resp_id]
					resp_state.processed = False
					resp_state.status = status
					resp_state.statusCode = statusCode
					resp_state.result = result

				# check if this callback has responsibility for found message
				if resp_id == task_id:
					resp = current_state.callbackResponse()
					# cleanup if task is done or unspecified:
					if resp.statusCode <= 0:
						del self.states[task_id]
					# task not done, but current state is processed
					else:
						current_state.processed =  True
					return resp

			# No state update found
			return current_state.callbackResponse()
			#-- End callback definition
		return status_callback

	def __poll_event_queue(self):
		'''__poll_event_queue
		Poll pipe to get most recent events
		'''
		while self.event_queue and not self.event_queue.empty():
			try:
				self.recent_events = self.event_queue.get_nowait()
			except Queue.Empty:
				pass
			except Exception as e:
				logger.warning('Exception while getting recent events: %s'%e)
			

	def pupilPositions(self):
		self.__poll_event_queue()
		if self.recent_events:
			return self.recent_events['pupil_positions']
		return None

	def gazePositions(self):
		self.__poll_event_queue()
		if self.recent_events:
			return self.recent_events['gaze_positions']
		return None

	def trigger(self,frameid=None,context=None):
		'''trigger
		'''
		now = self.g_pool.capture.get_timestamp()
		msg = {
			'cmd':TRIGGER,
			'timestamp':now,
			'frameid':frameid,
			'context':context
		}

		try:
			self.cmd_pipe.send(msg)
		except AttributeError as e:
			logger.error('trigger<%s,%s>: %s'%(frameid,context,e))
		except ValueError as e:
			msg['context'] = None
			logger.error('trigger<%s,%s>: %s'%(frameid,context,e))
			self.cmd_pipe.send(msg)
		except Exception as e:
			logger.debug(e)

		return None

	def __startProcedure(self, command,context=None):
		task_id = uuid4()
		cb = self.__create_status_callback(task_id)
		now = self.g_pool.capture.get_timestamp()
		msg = {
			'cmd':command,
			'timestamp':now,
			'id': task_id,
			'context': None
		}
		if context:
			msg['context'] = context

		try:
			self.cmd_pipe.send(msg)
		except AttributeError as e:
			logger.error('record<%s>: %s'%(context,e))
		except ValueError as e:
			msg['context'] = None
			logger.error('record<%s>: %s'%(context,e))
			self.cmd_pipe.send(msg)
		except Exception as e:
			logger.warning(e)

		return cb

	def _stopProcedure(self, command, context=False):
		now = self.g_pool.capture.get_timestamp()
		msg = {
			'cmd':command,
			'timestamp':now
		}
		try:
			self.cmd_pipe.send(msg)
		except Exception as e:
			logger.warning(e)

	def startRecording(self,session_name):
		'''startRecording
		Starts recording.
		Returns finished_callback which returns True
			if the calibration has finished
		'''
		return self.__startProcedure(START_RECORDING, session_name)

	def stopRecording(self):
		'''stopRecording
		Stops an ongoing recording session.
		If the recording was started by calling startCalibration its callback
			will return when the recording has stopped.
		'''
		self._stopProcedure(STOP_RECORDING)

	def startCalibration(self,context=None):
		'''startCalibration
		Starts calibration.
		Returns finished_callback which returns True
			if the calibration has finished
		'''
		return self.__startProcedure(START_CALIBRATION, context)

	def stopCalibration(self):
		'''stopCalibration
		Stops an ongoing calibration procedure.
		If the calibration was started by calling startCalibration its callback
			will return when the calibration has stopped.
		'''
		self._stopProcedure(STOP_CALIBRATION)

pupil_helper = None

def main(g_pool, script, cmd_pipe, event_queue):
	global pupil_helper
	pupil_helper = PupilCommunication(g_pool, cmd_pipe, event_queue)
	head, tail = os.path.split(script)
	sys.path.append(head)
	name, ext = tail.rsplit('.',1)
	#__import__(name)
	try:
		__import__(name)
	except Exception as e:
		logger.error('import error (%s): %s'%(tail,e))

	# close queue gracefully
	event_queue.close()
	event_queue.join_thread()
