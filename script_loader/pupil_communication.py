import os, sys, platform, logging, colorlog
from uuid import uuid4
from collections import namedtuple
if platform.system() == 'Darwin' and getattr(sys, 'frozen', False):
	from billiard import Process, Pipe, Queue, forking_enable
	forking_enable(0)
else:
	from multiprocessing import Process, Pipe

from const import (
	START_CALIBRATION,
	STOP_CALIBRATION,
	START_RECORDING,
	STOP_RECORDING,
	TRIGGER,
	ACTION_CALIBRATION,
	ACTION_RECORDING,
	EXIT
)

logger = colorlog.getLogger('pupil_communication')
logger.propagate = False
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logger.level)
ch.setFormatter(colorlog.ColoredFormatter(
	#"%(log_color)s%(levelname)-8s%(reset)s %(blue)s%(message)s",
	"WORLD Process [%(log_color)s%(levelname)s%(reset)s] %(name)s : %(message)s",
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
	def __init__(self, g_pool, cmd_pipe, event_queue):
		self.g_pool = g_pool
		self.cmd_pipe = cmd_pipe
		self.event_queue = event_queue
		self.tasks = []
		self.answers = {}
		self.recent_events = None

	def __create_status_callback():
		pass

	def __create_finish_callback(self,task_id,blocking=False):
		self.tasks.append(task_id)
		self.answers[task_id] = None

		def finished_callback(blocking=blocking):
			'''
			poll all available messages and return finish state
			'''

			# Create named tuple for returning multiple values
			Response = namedtuple('FinishedCallbackResponse',['finished','successful','answer'])

			# check if task is done and answer is still unprocessed
			# return immediatly if True
			answer = None
			successful = False
			if not task_id in self.tasks:
				if task_id in self.answers:
					answer = self.answers[task_id]
					del self.answers[task_id]
				logger.debug('Task %s already done'%task_id)
				return Response(True, answer)

			# loop runs until specific task was answered
			while self.cmd_pipe and (self.cmd_pipe.poll() or blocking):
				msg = self.cmd_pipe.recv()
				resp_id = msg['id']
				
				successful = msg.get('successful', False)
				answer = msg.get('answer', None)

				if resp_id in self.tasks:
					self.tasks.remove(resp_id)
					self.answers[resp_id] = answer
				if resp_id == task_id:
					del self.answers[resp_id]
					break
				# Reset answer
				answer = None
				logger.debug("Task [%s]: %s"%(resp_id, answer))
			return Response(not task_id in self.tasks, successful, answer)

		return finished_callback

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

	def __startProcedure(self, command, blocking=False,context=None):
		task_id = uuid4()
		cb = self.__create_finish_callback(task_id,blocking)
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
			logger.error('record<%s,%s>: %s'%(blocking,context,e))
		except ValueError as e:
			msg['context'] = None
			logger.error('record<%s,%s>: %s'%(blocking,context,e))
			self.cmd_pipe.send(msg)
		except Exception as e:
			logger.warning(e)

		return cb

	def _stopProcedure(self, command, blocking=False, context=False):
		now = self.g_pool.capture.get_timestamp()
		msg = {
			'cmd':command,
			'timestamp':now
		}
		try:
			self.cmd_pipe.send(msg)
		except Exception as e:
			logger.warning(e)

	def startRecording(self,session_name,blocking=False):
		'''startRecording
		Starts recording.
		Returns finished_callback which returns True
			if the calibration has finished
		blocking decides if finished_callback blocks until done or not
		'''
		return self.__startProcedure(START_RECORDING, blocking, session_name)

	def stopRecording(self):
		'''stopRecording
		Stops an ongoing recording session.
		If the recording was started by calling startCalibration its callback
			will return when the recording has stopped.
		'''
		self._stopProcedure(STOP_RECORDING)

	def startCalibration(self,blocking=False,context=None):
		'''startCalibration
		Starts calibration.
		Returns finished_callback which returns True
			if the calibration has finished
		blocking decides if finished_callback blocks until done or not
		'''
		return self.__startProcedure(START_CALIBRATION, blocking, context)

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
