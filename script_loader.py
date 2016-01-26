import sys, os, logging
from pyglui import ui
from plugin import Plugin

__version__ = '0.0.1'

import logging
logger = logging.getLogger(__name__)

class Script_Loader(Plugin):
	"""Script Loader Plugin
	Loads custom Python scripts.
	Implements simple interaction interface.
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
		if self.action_button:
			self.action_button = None

	def run_action(self):
		self.running = not self.running
		self.sync_buttons()

	def stop_action(self):
		self.running = not self.running
		self.sync_buttons()

	def sync_buttons(self):
		self.run_button.read_only = self.running
		self.stop_button.read_only = not self.running


	def select_script(self,script):
		logger.debug('Selected: %s'%script)
		self.selected_script = script

	def get_selected_script_label(self):
		if 	self.selected_script and \
			self.selected_script in self.scripts_found:
			return self.selected_script
		elif len(self.scripts_found) == 0 : return 'No scripts found'
		else: return 'No script selected'

#-- uiless --

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