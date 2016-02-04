import sys, os, platform, time, logging, colorlog

from pupil_communication import main as pupil_communication_main

from pyglui import ui
from plugin import Plugin

__version__ = '0.0.2'

logger = colorlog.getLogger(__name__)
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

if platform.system() == 'Darwin' and getattr(sys, 'frozen', False):
	from billiard import Process, Pipe, Value, forking_enable
	forking_enable(0)
else:
	from multiprocessing import Process, Pipe

class Script_Loader(Plugin):
	"""Script Loader Plugin
	Loads custom Python scripts.
	Implements simple interaction interface.

	Runs PupilCommunication.main in seperate process.
	PupilCommunication handles inter-process communication and provides
	high level interaction interface for the loaded custom script.

	Every API call on PupilCommunication returns a finished_callback.
	This callback can be blocking depending on a parameter passed on
	to the API call. It returns a named tuple FinishedCallbackResponse.

	FinishedCallbackResponse has two components. One boolean one, called
	finished, which is True after the specific API call has finished. The
	second one is an object which passed as answer to the specific API call.
	It is called answer and is None by default.

	"""

	uniqueness = 'not_unique'
	order = .4

	def __init__(self,g_pool,selected_script=None):
		super(Script_Loader, self).__init__(g_pool)
		self.script_dir = os.path.join(self.g_pool.user_dir, 'custom_scripts')
		if not os.path.isdir(self.script_dir):
			os.mkdir(self.script_dir)
		self.scripts_found = self.list_custom_scripts(self.script_dir)
		self.select_script(selected_script)
		self.running = False
		self.script_process = None
		self.script_pipe = None

		# None, if action is not running. task_id or [task_id] if running
		# Is list if action allows multiple executions in parallel
		self.current_actions = {
			'calibration': None
		}

#-- uiful --

	def init_gui(self):
		self.menu = ui.Growing_Menu('Script Loader')
		self.g_pool.sidebar.append(self.menu)
		self.menu.append(ui.Selector('Select Script',
			selection	= self.scripts_found,
			labels 		= [p.replace('_',' ').replace('.py','') for p in self.scripts_found],
			setter 		= self.select_script,
			getter 		= self.get_selected_script_label
		))

		self.run_button = ui.Button('Run Script',self.run_action)
		self.menu.append(self.run_button)
		self.stop_button = ui.Button('Stop Script',self.stop_action)
		self.menu.append(self.stop_button)
		self.sync_buttons()

		self.menu.append(ui.Button('Close',self.close))
		self.menu.append(ui.Info_Text('This plugin runs custom Python scripts'+
			'and provides an interface to the Pupil software for the script'))

	def get_init_dict(self):
		return {
			'selected_script': self.selected_script
		}

	def close(self):
		self.alive = False

	def cleanup(self):
		self.deinit_gui()

	def deinit_gui(self):
		if self.menu:
			self.g_pool.sidebar.remove(self.menu)
			self.menu = None
		if self.run_button:
			self.run_button = None
		if self.stop_button:
			self.stop_button = None

	def run_action(self):
		self.run_script()

	def stop_action(self):
		self.running = False
		self.sync_buttons()
		logger.info('Stopped %s'%self.selected_script)

	def sync_buttons(self):
		self.run_button.read_only = self.running
		self.stop_button.read_only = not self.running

	def update(self,frame,events):
		self.communicate()
	
	def on_notify(self,notification):
		if (notification['subject'] == 'cal_finished' and 
			self.current_actions['calibration']):
			task_id = self.current_actions['calibration']
			self.current_actions['calibration'] = None
			logger.debug('Received cal_finished notification [%s]'%task_id)
			resp = {
				'id': task_id,
				'successful': notification['successful'],
				'error_code': notification['error_code'],
				'answer': notification['reason']
			}
			try:
				self.script_pipe.send(resp)
			except Exception as e:
				logger.error('Sending response failed: %s'%e)

	def select_script(self,script):
		if script == 'No script selected':
			self.selected_script = None
		else: self.selected_script = script
		logger.debug('Selected: %s'%script)

	def get_selected_script_label(self):
		if 	self.selected_script and \
			self.selected_script in self.scripts_found:
			return self.selected_script
		elif len(self.scripts_found) == 0 : return 'No scripts found'
		else: return 'No script selected'

#-- uiless --

	def run_script(self, script=None):
		if not script:
			script = self.selected_script

		# check if it is still not set
		if not script:
			logger.error('Select script to run')
			self.running = False
		else:
			script_path = os.path.join(self.script_dir,script)			
			cmd_script_end,self.script_pipe = Pipe(True)
			self.script_process = Process(target=pupil_communication_main,args=(script_path,cmd_script_end))
			self.script_process.start()
			cmd_script_end.close()
			self.running = True
			logger.info('Starting %s'%script)
		self.sync_buttons()
	
	def communicate(self):
		if self.running and self.script_pipe and self.script_pipe.poll():
			#block and listen for commands from world process.
			try:
				msg = self.script_pipe.recv()
				cmd = msg['cmd']
				if cmd == 'Exit':
					self.running = False
					logger.info('%s finished running'%self.selected_script)
				elif cmd == 'trigger':
					trig = msg['timestamp']
					frameid = msg['frameid']
					context = msg['context']
					logger.debug("trigger (%f): %s [%s]"%(trig,frameid,context))
				elif cmd == 'calibrate':
					task_id = msg['id']
					self.calibrate(task_id)

			except EOFError:
				logger.debug("Child process closed pipe at %f"%time.time())
				logger.info('%s finished running'%self.selected_script)
				self.running = False
			except KeyboardInterrupt:
				self.running = False
				logger.info('%s interrupted'%self.selected_script)
			except Exception as e:
				self.running = False
				logger.info('%s interrupted because: %s'%(self.selected_script,e))
		
		if not self.running:
			if self.script_process:
				if self.script_process.is_alive():
					self.script_process.terminate()
				self.script_process = None
			if self.script_pipe:
				self.script_pipe.close()
				self.script_pipe = None
			self.sync_buttons()

	def calibrate(self,task_id):
		if self.current_actions['calibration']:
			resp = {
				'id': task_id,
				'answer': 'Warning: Calibration already running.'
			}
			self.script_pipe.send(resp)
		else:
			self.current_actions['calibration'] = task_id
			self.notify_all({
				'subject': 'cal_should_start'
			})


	def list_custom_scripts(self,script_dir):
		custom_scripts = []
		for f in os.listdir(script_dir):
			logger.debug('Scanning: %s'%f)
			try:
				if os.path.isfile(os.path.join(script_dir,f)):
					name, ext = f.rsplit('.',1)
					if ext in ['py']:
						logger.debug('Found: %s'%f)
						custom_scripts.append(f)
			except Exception as e:
				logger.error("Failed to load '%s'. Reason: '%s' "%(d,e))
		return custom_scripts