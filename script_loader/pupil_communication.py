import os, sys, platform, logging, colorlog
from uuid import uuid4
from collections import namedtuple
if platform.system() == 'Darwin' and getattr(sys, 'frozen', False):
	from billiard import Process, Pipe, forking_enable
	forking_enable(0)
else:
	from multiprocessing import Process, Pipe

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
	def __init__(self, g_pool, pipe):
		self.g_pool = g_pool
		self.pipe = pipe
		self.tasks = []
		self.answers = {}

	def __create_finish_callback(self,task_id,blocking=False):
		self.tasks.append(task_id)
		self.answers[task_id] = None

		def finished_callback():
			'''
			poll all available messages and return finish state
			'''

			# Create named tuple for returning multiple values
			Response = namedtuple('FinishedCallbackResponse',['finished','answer'])

			# check if task is done and answer is still unprocessed
			# return immediatly if True
			answer = None
			if not task_id in self.tasks:
				if task_id in self.answers:
					answer = self.answers[task_id]
					del self.answers[task_id]
				logger.debug('Task %s already done'%task_id)
				return Response(True, answer)

			# loop runs until specific task was answered
			while self.pipe and (self.pipe.poll() or blocking):
				msg = self.pipe.recv()
				resp_id = msg['id']
				
				answer = None
				# Test if msg has answer key
				if 'answer' in msg:
					answer = msg['answer']

				if resp_id in self.tasks:
					self.tasks.remove(resp_id)
					self.answers[resp_id] = answer
				if resp_id == task_id:
					del self.answers[resp_id]
					break
				# Reset answer
				answer = None
				logger.debug("Task [%s]: %s"%(resp_id, answer))
			return Response(not task_id in self.tasks, answer)

		return finished_callback

	def trigger(self,frameid=None,context=None):
		'''trigger
		'''
		now = self.g_pool.capture.get_timestamp()
		msg = {
			'cmd':'trigger',
			'timestamp':now,
			'frameid':None,
			'context':None
		}
		if frameid:
			msg['frameid'] = frameid
		if context:
			msg['context'] = context
		try:
			self.pipe.send(msg)
		except AttributeError as e:
			logger.error('trigger<%s,%s>: %s'%(frameid,context,e))
		except ValueError as e:
			msg['context'] = None
			logger.error('trigger<%s,%s>: %s'%(frameid,context,e))
			self.pipe.send(msg)
		except Exception as e:
			logger.debug(e)

		return None

	def calibrate(self,blocking=False,context=None):
		'''calibrate
		Starts calibration.
		Returns finished_callback which returns True
			if the calibration has finished
		blocking decides if finished_callback blocks until done or not
		'''

		task_id = uuid4()
		cb = self.__create_finish_callback(task_id,blocking)

		now = self.g_pool.capture.get_timestamp()
		msg = {
			'cmd':'calibrate',
			'timestamp':now,
			'id': task_id,
			'context':None
		}
		if context:
			msg['context'] = context

		try:
			self.pipe.send(msg)
		except AttributeError as e:
			logger.error('calibrate<%s,%s>: %s'%(blocking,context,e))
		except ValueError as e:
			msg['context'] = None
			logger.error('calibrate<%s,%s>: %s'%(blocking,context,e))
			self.pipe.send(msg)
		except Exception as e:
			logger.warning(e)

		return cb

pupil_helper = None

def main(g_pool, script, communication):
	global pupil_helper
	pupil_helper = PupilCommunication(g_pool, communication)
	head, tail = os.path.split(script)
	sys.path.append(head)
	name, ext = tail.rsplit('.',1)
	#__import__(name)
	try:
		__import__(name)
	except Exception as e:
		logger.error('import error (%s): %s'%(tail,e))