############################
###### PYTHON MODULES ######
############################

from __future__ import absolute_import
from __future__ import print_function
import sys
import os
import os.path as path
import threading
import time
import datetime
import csv
from paramiko import SSHClient, AutoAddPolicy, ssh_exception
from datetime import datetime, timedelta
import binascii
import glob
from threading import Thread
import contextlib, io

# #################################################################################################

from lib.cr_common import *
from framework_core import SUITE_TYPE
from test_library.app_test_core import *
from test_library.test_library_core import TestStatus, TestEngineBase, SimpleTestcase, SimpleTestEngine
from tester_instrument.tester_core import *
from tester_instrument.os_interface import *
from tester_instrument.connections import *
from tester_instrument.sut_state import SUT_STATE
from tester_instrument.python_sv_instrument.cpu_device.cpu_core import CPU_TYPES
# #################################################################################################
# BASE Class
# #################################################################################################

class PI_PM_Testcase(AppTestcase):
	_default = {"_config_name": "PI_PM Testcase"}

	def __init__(self):
		super(PI_PM_Testcase, self).__init__()
		self.name = "PI_PM_test"
		self.target_script = "PI_PM_tests.py"
		self.workload_name = "PI_PM"
		self.targetlogfolder = None
		self.check_turbo_flag = False
		self.check_event_logs = False
		self.ptu_ct = None
		self.run_ptu = True
		self.ptu_runtime = 180
		self.os_power_policy = None
		self.tool = None
		self.supported_modes = [TESTER_ENUMS.STORAGE_MODES.LM1_WITH_APPDIRECT, TESTER_ENUMS.STORAGE_MODES.LM2, TESTER_ENUMS.STORAGE_MODES.MIXED_MODE,TESTER_ENUMS.STORAGE_MODES_HBM.HBM, TESTER_ENUMS.STORAGE_MODES_HBM.CACHE,TESTER_ENUMS.STORAGE_MODES_HBM.FLAT]
		self._start()

	def _start(self):
		self.product_class = PI_PM_TestEngine
		return self

# #################################################################################################
# Test Engine
# #################################################################################################
class PI_PM_TestEngine(AppTestEngine):
	class_lable = "PI_PM TestEngine"

	def __init__(self, config=None, tester=None):
		super(PI_PM_TestEngine, self).__init__(config, tester)
		self.pi_pm_applog_folder = "{}/PI_PM/{}".format(self._tester._manager.app_logs_target_path,self._config.targetlogfolder)
		self.pi_pm_app_path = "{}/PI_PM".format(self._tester._manager.app_target_path)
		self.pi_pm_applog_folder_win = os.path.join(self._tester._manager.app_logs_target_path_win, "PI_PM", self._config.targetlogfolder)
		self.pi_pm_app_path_win = os.path.join(self._tester._manager.app_target_path_win, "PI_PM")
		self.ptu_app_path_win = os.path.join(self._tester._manager.app_target_path_win, "ptu")
		self.speccpu_dir_win = os.path.join(self._tester._manager.app_target_path_win, "PI_PM", "cpu2017")
		self.pi_pm_applog_win = os.path.join(self._tester._manager.app_logs_target_path_win, "PI_PM")
		self.socwatch_path_win = os.path.join(self._tester._manager.app_target_path_win, "socwatch","64")
		self.ptu_dir = "{}/PI_PM/ptu".format(self._tester._manager.app_target_path)
		self.solar_app_path = '{}/solar'.format(self._tester._manager.app_target_path)
		self.solar_app_path_win = os.path.join(self._tester._manager.app_target_path_win, 'solar')
		self.msr_dir = '{}/PI_PM/msr-tools-master'.format(self._tester._manager.app_target_path)
		self.psys_log_path = "C:/temp/PI_PM_Psys"
		self.auto_logpath = "C:/temp/AutoLogs"
		self.app_pmutil_path='/root/apps/PM/pm_utility-master'
		self.test_logs = []
		self.pipm_app_log =None
		self.cpuidle_path = "/sys/devices/system/cpu/"
		self.ptu_log_file = None
		self.ptu_log_file1 = None
		self.overall_fail_summary = []
		self.overall_pass_summary = []
		self.cpu_type = None
	
	target_script = property(lambda self: self._config["target_script"])
	targetlogfolder = property(lambda self: self._config["targetlogfolder"])
	ptu_runtime = property( lambda self: self._config["ptu_runtime"])
	os_power_policy = property(lambda self: self._config["os_power_policy"])
	tool = property(lambda self: self._config["tool"])

	def setup_app(self):
		super(PI_PM_TestEngine,self).setup_app()
		return self.run_pi_pm_pre()

	def run_app(self):
		super(PI_PM_TestEngine,self).run_app()
		return self.run_pi_pm_main()

	def teardown_app(self):
		super(PI_PM_TestEngine,self).teardown_app()
		return self.run_pi_pm_post()

	def check_cpu_type(self):
		if self._tester._sut_control.cpus.name == CPU_TYPES.graniterapids.name:
			self.cpu_type = "GNR"
			self.app_pmutil_path = '/root/apps/pmutil'
		if self._tester._sut_control.cpus.name == CPU_TYPES.sierraforest.name:
			self.cpu_type = "SRF"
			self.app_pmutil_path = '/root/apps/pmutil'
		elif self._tester._sut_control.cpus.name in [CPU_TYPES.sapphirerapids.name,CPU_TYPES.sapphirerapids_hbm.name] :
			self.cpu_type = "SPR"
		self._tester.test_logger.log("************************   CPU TYPE : {}  ************************".format(self.cpu_type))

	def check_qdfvalue(self):
		self._tester.test_logger.log("Checking the QDF value on the platform")
		from namednodes import sv
		sockets = sv.socket.getAll()
		socket0 = sv.sockets[0]
		self.qdf_value=socket0.pcudata.global_qdf_fuse_string
		self.qdf_value=binascii.unhexlify("%x"%self.qdf_value).decode()
		self._tester.test_logger.log("The QDF value is : {}".format(self.qdf_value))
		# 'QUAB'

	def stop_ptu(self):
		if self._tester.sut_control.sut_os_type == TESTER_ENUMS.OS_TYPE.WINDOWS:
			self._tester._os_access.run_command('TASKKILL /F /FI "imagename eq ptu.exe"')
		else:
			self._tester._os_access.run_command("/root/apps/PI_PM/ptu/killptu.sh")
		self._tester.test_logger.log("PTU command has been stopped.")


	def pmutil_core_busy(self,thread,soc_val):
		if soc_val == 0:
			soc_val1 = 1
		elif soc_val == 1:
			soc_val1 = 0

		self.busy_thread = thread
		self._tester.test_logger.log("Thread {} in Socket {} will be busy and Socket {} will be idle".format(self.busy_thread,soc_val,soc_val1))
		set_busy_thread = "cd {} && ./pmutil_bin -keep_core_busy {}".format(self.app_pmutil_path, self.busy_thread)
		self._tester.test_logger.log("Running command :{}".format(set_busy_thread))
		self._tester._os_access.run_command(set_busy_thread)

	def stop_pmutil_threads(self):
		self._tester.test_logger.log("Killing all the pmutil threads running in the background..")
		cmd = "kill -9 `pgrep pmutil`"
		self._tester._os_access.run_command(cmd)

	def stop_fotonik(self):
		self._tester.test_logger.log("Killing the Fotonik tool..")
		if self._tester.sut_control.sut_os_type == TESTER_ENUMS.OS_TYPE.WINDOWS:
			self._tester._os_access.run_command('taskkill /IM "fotonik3d_r_base.ic19.0u4-win-sse4.2-r-20190416" /F')
		else:
			self._tester._os_access.run_command("kill -9 `pgrep fotonik`")
		self._tester.test_logger.log("Fotonik command has been stopped..")

	def run_ptu_workload(self, cfg):
		self._tester.test_logger.log("Going to run the PTU ct execution.....")
		if cfg == "" or cfg == "ct3":
			varmsg = "ct3"
			varcmd = "-ct 3"
		elif cfg == "ct4":
			varmsg = "ct4"
			varcmd = "-ct 4"
		elif cfg == "ct5":
			varmsg = "ct5"
			varcmd = "-ct 5"
		
		if self._tester.sut_control.sut_os_type == TESTER_ENUMS.OS_TYPE.CENTOS:
			ptu_command="cd {} && sudo modprobe msr && ./ptu {cmd} ".format(self.ptu_dir,cmd=varcmd)
					
		self._tester.test_logger.log("Running PTU command :{}".format(ptu_command))
		self._tester.sut_control.os_access.run_command(ptu_command, continue_on_ssh_loss=True, retry=0)
		time.sleep(30)

	def run_ptu_workload_with_cp(self,cpu_utilization):
		self._tester.test_logger.log("Going to run the PTU ct -cp {} execution.....".format(cpu_utilization))
		ptu_command="cd {} && sudo modprobe msr && ./ptu -ct 3 -cp {}".format(self.ptu_dir,cpu_utilization)
		self._tester.test_logger.log("Running PTU command :{}".format(ptu_command))
		self._tester.sut_control.os_access.run_command(ptu_command, continue_on_ssh_loss=True, retry=0)
		time.sleep(30)
			

	def run_ptu_ct(self):
		self.ptu_ct = self._config.ptu_ct
		self._tester.test_logger.log("Running PTU in background for {}".format(self.ptu_ct))

		ptu_ct_log = "{app_logs}/{sut}_ptu_ct_{time}.log".format(
			app_logs=self.pi_pm_applog_win, sut=self._tester.sut_control.hostname, time=self._tester._logger.make_ts(file_ts=True))
		self.run_ptu_ct_cmd='cd {app_path} && ptu.exe -ct {ptu} > {logfile}&'.format(app_path=self.ptu_app_path_win, ptu=self.ptu_ct, logfile=ptu_ct_log)
		self._tester.sut_control.os_access.run_command(self.run_ptu_ct_cmd)
		self.test_logs.append(ptu_ct_log)

	def run_ptu_monitor(self):
		self._tester.test_logger.log("Running PTU monitor....")
		self.logfilename = "{sut}_ptu_mon_{time}.log".format(
			sut=self._tester.sut_control.hostname, time=self._tester._logger.make_ts(file_ts=True))
		self.ptu_mon_log = "{app_logs}/{filename}".format(
			app_logs=self.pi_pm_applog_folder, filename=self.logfilename)
		
		ptu_command="cd {} && ./ptu -mon -filter 0x0F -l 1 -log -logdir {} -logname {} ".format(self.ptu_dir,self.pi_pm_applog_folder,self.logfilename)
		self.ptu_mon_cmd="sudo modprobe msr && "+ ptu_command

		#self.ptu_mon_cmd = "'cd {dir}; sudo modprobe msr && ./ptu -mon -filter 0x0f -l 1' > {log} 2>&1 &".format(dir=self.ptu_dir, log=self.ptu_mon_log)
		self._tester.sut_control.os_access.run_command(self.ptu_mon_cmd)
		self.test_logs.append(self.ptu_mon_log)
		time.sleep(30)
		self._tester.test_logger.log("Logs are saved in {}".format(self.ptu_mon_log))
		return self.ptu_mon_log


	def rdmsr_plat_energy_status(self):
		val1 = self._tester.sut_control.os_access.run_command('rdmsr 0x64d').combined_lines
		#self._tester.test_logger.log("1st RDMSR output : {}".format(val1))
		time.sleep(1)

		val2 = self._tester.sut_control.os_access.run_command('rdmsr 0x64d').combined_lines
		#self._tester.test_logger.log("2nd RDMSR output : {}".format(val2))
		
		reg1 = int(val1[0][-8:],16)
		tsc1 = int(val1[0][-16:-8],16)
		# self._tester.test_logger.log("1st Plt_energy output in int : {}".format(reg1))
		# self._tester.test_logger.log("tsc1 : {}".format(val1))

		reg2 = int(val2[0][-8:],16)
		tsc2 = int(val2[0][-16:-8],16)
		# self._tester.test_logger.log("2nd Plt_energy output in int: {}".format(reg2))
		# self._tester.test_logger.log("tsc2 : {}".format(val1))

		dt = (tsc2-tsc1)*10**-8
		#self._tester.test_logger.log("Delta TimeStamp : {}".format(dt))

		plat_power = (reg2 - reg1) / dt
		self._tester.test_logger.log('Plat_Power_Energy_Counters: {:.1f} W'.format(plat_power))
		
		return plat_power

	def plt_energy_status_diff(self,total_power_val,percent):
		self._tester.test_logger.log("Running power_plt_energy_status_loop from ipc window....")
		ts = datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d-%H-%M-%S')
		self.psys_log_file = "{}/Energy_Status_{}.log".format(self.auto_logpath,self.name,ts)
		log_list = []

		if self._tester.manager.cpu_project == CPU_PROJECT.SPR:
			import sapphirerapids.users.dalkatta.platform_power as pp
			self.plat_power= pp.platform_power_consumption()
			log_list.append('Plat_Power_Energy_Counters: {} W'.format(self.plat_power))

		elif self._tester.manager.cpu_project == CPU_PROJECT.GNR:
			import graniterapids.users.nkudliba.platform_power as ppp
			self.plat_power=ppp.platform_power_consumption()
			log_list.append('Plat_Power_Energy_Counters: {} W'.format(self.plat_power))

		self.total_power_val=total_power_val
		self.percent=percent
		self.lower_limit=self.total_power_val-((self.percent*total_power_val)/100)
		self.upper_limit=self.total_power_val+((self.percent*total_power_val)/100)
		if self.lower_limit <= int(self.plat_power) <= self.upper_limit:
			self._tester.test_logger.log(f"The platform power is with +/- {self.percent}% within the range!")
		else:
			self._tester.test_logger.log(f"The platform power exceeds the  +/- {self.percent}% range!")

		with open(self.psys_log_file, 'w') as log_file_handle:
				for line in log_list:
					log_file_handle.write("%s\n" %line)
		
		self._tester.test_logger.log("Power_Platform_Energy_Status_Loop Dump located in {path}".format(path=self.psys_log_file))


	def plt_energy_status(self):
		self._tester.test_logger.log("Running power_plt_energy_status_loop from MSR tool....")
		ts = datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d-%H-%M-%S')
		self.psys_log_file = "{}/Plt_Pwr_Energy_Status_{}_{}.log".format(self.auto_logpath,self.name,ts)
		end_time = time.time() + 120
		log_list = []
		if self._tester.manager.cpu_project == CPU_PROJECT.SPR:
			while time.time() < end_time:
				import sapphirerapids.users.dalkatta.platform_power as pp
				power_log = pp.platform_power_consumption()
				log_list.append('Plat_Power_Energy_Counters: {:.1f} W'.format(power_log))
				
			self._tester.test_logger.log("Going to write the power_status_loop_output to {} file".format(self.psys_log_file))   

		elif self._tester.manager.cpu_project == CPU_PROJECT.GNR:
			while time.time() < end_time:
				import graniterapids.users.nkudliba.platform_power as ppp
				power_log = ppp.platform_power_consumption()
				log_list.append('Plat_Power_Energy_Counters: {:.1f} W'.format(power_log))
				
			self._tester.test_logger.log("Going to write the power_status_loop_output to {} file".format(self.psys_log_file))

		else:
			self._tester.test_logger.log("Platform_power_measure is not supported for non SPR Platforms")

		with open(self.psys_log_file, 'w') as log_file_handle:
				for line in log_list:
					log_file_handle.write("%s\n" %line)

		self._tester.test_logger.log("Ran the power_plat_energy_status_loop for 1min...")       
		self._tester.test_logger.log("Power_Platform_Energy_Status_Loop Dump located in {path}".format(path=self.psys_log_file))


	def run_power_plt_energy_status_avg(self):
		self._tester.test_logger.log("Running power_plt_energy_status_loop from ipc window....")
		ts = datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d-%H-%M-%S')
		self.psys_log_file = "{}/Plt_Pwr_Energy_Status_{}_{}.log".format(self.auto_logpath,self.name,ts)
		end_time = time.time() + 60
		log_list = []
		if self._tester.manager.cpu_project == CPU_PROJECT.SPR:
			count=0
			val_sum=0
			while time.time() < end_time:
				import sapphirerapids.users.dalkatta.platform_power as pp
				power_log = pp.platform_power_consumption()
				val_sum += power_log
				log_list.append('Plat_Power_Energy_Counters: {:.1f} W'.format(power_log))
				count=count+1
			
			self.power_estimate_avg_value=int(val_sum/count)
			self._tester.test_logger.log("Average power estimate value: {}".format(self.power_estimate_avg_value))
			self._tester.test_logger.log("Going to write the power_status_loop_output to {} file".format(self.psys_log_file))

		elif self._tester.manager.cpu_project == CPU_PROJECT.GNR:
			count=0
			val_sum=0
			while time.time() < end_time:
				import sapphirerapids.users.dtthomps.platform_power_measure as p
				power_log= p.power_plat_energy_status_single()
				val_sum += power_log
				log_list.append('Plat_Power_Energy_Counters: {:.1f} W'.format(power_log))
				count=count+1

			self.power_estimate_avg_value=int(val_sum/count)
			self._tester.test_logger.log("Average power estimate value: {}".format(self.power_estimate_avg_value))
			self._tester.test_logger.log("Going to write the power_status_loop_output to {} file".format(self.psys_log_file))

		else:
			self._tester.test_logger.log("Platform_power_measure is not supported for non SPR Platforms")


		with open(self.psys_log_file, 'w') as log_file_handle:
			for line in log_list:
				log_file_handle.write("%s\n" %line)
		
		self._tester.test_logger.log("Ran the power_plat_energy_status_loop for 1min and recorded the average value...")        
		self._tester.test_logger.log("Power_Platform_Energy_Status_Loop Dump located in {path}".format(path=self.psys_log_file))
		return self.power_estimate_avg_value



	def run_power_plt_energy_status(self):
		self._tester.test_logger.log("Running power_plt_energy_status_loop from ipc window....")
		ts = datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d-%H-%M-%S')
		self.psys_log_file = "{}/Plt_Pwr_Energy_Status_{}_{}.log".format(self.auto_logpath,self.name,ts)
		end_time = time.time() + 60
		log_list = []
		if self._tester.manager.cpu_project == CPU_PROJECT.SPR:
			while time.time() < end_time:
				import sapphirerapids.users.dtthomps.platform_power_measure as p
				power_log = p.power_plat_energy_status_single()
				log_list.append('Plat_Power_Energy_Counters: {:.1f} W'.format(power_log))
				
			self._tester.test_logger.log("Going to write the power_status_loop_output to {} file".format(self.psys_log_file))

		elif self._tester.manager.cpu_project == CPU_PROJECT.GNR:
			while time.time() < end_time:
				import graniterapids.users.nkudliba.platform_power as ppp
				power_log=ppp.platform_power_consumption()
				log_list.append('Plat_Power_Energy_Counters: {:.1f} W'.format(power_log))

			self._tester.test_logger.log("Going to write the power_status_loop_output to {} file".format(self.psys_log_file))

		else:
			self._tester.test_logger.log("Platform_power_measure is not supported for non SPR Platforms")


		with open(self.psys_log_file, 'w') as log_file_handle:
			for line in log_list:
				log_file_handle.write("%s\n" %line)
		
		self._tester.test_logger.log("Ran the power_plat_energy_status_loop for 1min...")       
		self._tester.test_logger.log("Power_Platform_Energy_Status_Loop Dump located in {path}".format(path=self.psys_log_file))

	def run_power_plt_energy_status_single(self):       
		self._tester.test_logger.log("Running power_plt_energy_status_single from ipc window....")
		ts = datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d-%H-%M-%S')
		self.psys_log_file = "{}/Plt_Pwr_Energy_Status_Single{}_{}.log".format(self.auto_logpath,self.name,ts)
		log_list = []
		if self._tester.manager.cpu_project == CPU_PROJECT.SPR:
			import sapphirerapids.users.dtthomps.platform_power_measure as p
			power_log = p.power_plat_energy_status_single()
			log_list.append('Plat_Power_Energy_Counters: {:.1f} W'.format(power_log))
			self.power_plt_energy_status_single_value = power_log               
			self._tester.test_logger.log("Going to write the power_status_loop_output to {} file".format(self.psys_log_file))

			with open(self.psys_log_file, 'w') as log_file_handle:
				for line in log_list:
					log_file_handle.write("%s\n" %line)
		else:
			self._tester.test_logger.log("Platform_power_measure is not supported for non SPR Platforms")
		self._tester.test_logger.log("Ran the power_plat_energy_status_single...")      
		self._tester.test_logger.log("Power_Platform_Energy_Status_Single Dump located in {path}".format(path=self.psys_log_file))
		return self.power_plt_energy_status_single_value

	def run_platform_power_consumption(self):       
		self._tester.test_logger.log("Running run_platform_power_consumption from ipc window....")
		ts = datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d-%H-%M-%S')
		self.psys_log_file = "{}/platform_power_consumption{}_{}.log".format(self.auto_logpath,self.name,ts)
		log_list = []
		if self._tester.manager.cpu_project == CPU_PROJECT.SPR:
			import sapphirerapids.users.dalkatta.platform_power as pp
			power_log = pp.platform_power_consumption()
			data = re.findall(r"\d+\.\d+", str(power_log))
			self._tester.test_logger.log(data[0])           
			log_list.append('platform power (W) : {}'.format(data[0]))          
			self.plt_power_consumption = power_log              
			self._tester.test_logger.log("Going to write the power_power_consumption_output to {} file".format(self.psys_log_file))

		elif self._tester.manager.cpu_project == CPU_PROJECT.GNR:
			import graniterapids.users.nkudliba.platform_power as ppp
			power_log=ppp.platform_power_consumption()
			data = re.findall(r"\d+\.\d+", str(power_log))
			self._tester.test_logger.log(data[0])           
			log_list.append('platform power (W) : {}'.format(data[0]))          
			self.plt_power_consumption = power_log              
			self._tester.test_logger.log("Going to write the power_power_consumption_output to {} file".format(self.psys_log_file))

		else:
			self._tester.test_logger.log("Platform_power_consumption is not supported for non SPR Platforms")

		with open(self.psys_log_file, 'w') as log_file_handle:
				for line in log_list:
					log_file_handle.write("%s\n" %line)
		
		self._tester.test_logger.log("Ran the Plt_pwr_consumption...")      
		self._tester.test_logger.log("Platform_Power_Consumption Dump located in {path}".format(path=self.psys_log_file))
		return self.plt_power_consumption       


	def parse_psys_power_dump(self, filename, start_range, end_range):
		err_flag = False
		COMMENT_CHAR = '#'
		OPTION_CHAR =  '='
		filedata = open(filename)
		
		status_val_list = [ re.findall(r"Plat_Power_Energy_Counters: (\d+)", str(lines)) for lines in filedata ]
		for line in filedata:
			self._tester.test_logger.log(line)

		self._tester.test_logger.log("Output value from power_plt_energy_status dump is {}".format(status_val_list))        
		
		for value in status_val_list:
			if len(value)>0:
				try:
					if (int(self.min_range) <= int(value[0]) <= int(self.max_range)):
						self._tester.test_logger.log("PASS: The Power Platform Energy Status value {} is in expected range of {} and {}".format(value[0], self.min_range, self.max_range))
					else:
						self._tester.test_logger.log("FAIL: The Power Platform Energy Status value {} is not in the expected range of {} and {}".format(value[0], self.min_range, self.max_range))
						err_flag = True
				except Exception as e:
						self._tester.test_logger.log("Exception {} has occured while parsing Power Platform Energy Status value : {} ".format(e,int(value[0])))
						self._tester.test_logger.log("*************** Please Check log {} for more details**************************".format(filename))
						self._tester.test_logger.log("***************Continuing to parse next value**************************".format(e))
						continue
			else:
				pass
				

		return err_flag


	def msr_tools_installation(self):
		self._tester.test_logger.log("Installing msr tool...")
		self._tester.sut_control.os_access.run_command("cd {}".format(self.msr_dir))
		self._tester.sut_control.os_access.run_command("cd {}; chmod 777 *".format(self.msr_dir))
		self._tester.sut_control.os_access.run_command("cd {}; ./autogen.sh".format(self.msr_dir))
		self._tester.sut_control.os_access.run_command("cd {}; make install".format(self.msr_dir))

	def check_os_power_policy(self):
		self._tester.test_logger.log("The os_power_policy from comamnd line is  {}".format(self.os_power_policy))
		if self.os_power_policy == "powersave":
			power_cmd = "x86_energy_perf_policy -all power"
		elif self.os_power_policy == "performance":
			power_cmd = "x86_energy_perf_policy -all performance"
		elif self.os_power_policy == "balance_performance":
			power_cmd = "x86_energy_perf_policy -all balance-performance"
		elif self.os_power_policy =="balance_power":
			power_cmd = " x86_energy_perf_policy -all balance-power"
		power_policy_cmd = "cd {} && {}".format(self._tester.tester_functions.app_target_path,power_cmd)
		self._tester.test_logger.log("Triggering the command {}".format(power_policy_cmd))
		self._tester.sut_control.os_access.run_command(power_policy_cmd,verify=True, retry=0)
		time.sleep(60 * 5)

		
	def get_available_bitmap(self):
		self._tester.test_logger.log("Going to collect available bitmap on the system")
		self.socket_value = []
		if self.cpu_type in ["GNR","SRF"]:
			for socket in self._tester._pysv_mainframe._sockets:
				self._tester.test_logger.log("{}:".format( socket.name)) 
				self.value = socket.io0.uncore.punit.ptpcfsms.ptpcfsms.fused_cores_low_cfg.read()
				self._tester.test_logger.log("fused_cores_low_cfg : {}".format(self.value))
				self.socket_value.append(str(self.value))
		elif self.cpu_type == "SPR":
			for socket in self._tester._pysv_mainframe._sockets:
				self._tester.test_logger.log("{}:".format( socket.name)) 
				self.value = socket.uncore.punit.fused_cores_low_cfg.read()
				self._tester.test_logger.log("fused_cores_low_cfg : {}".format(self.value))
				self.socket_value.append(str(self.value))
		self._tester.test_logger.log("Socket Available Bit Map is {}".format(self.socket_value))
		return self.socket_value

	def get_resolved_core_bitmap(self):
		self._tester.test_logger.log("Going to collect available bitmap on the system")
		self.resolved_socket_value = []
		if self.cpu_type in ["GNR","SRF"]:
			for socket in self._tester._pysv_mainframe._sockets:
				self._tester.test_logger.log("{}:".format(socket.name))
				self.value = socket.io0.uncore.punit.ptpcfsms.ptpcfsms.resolved_cores_cfg.read()
				self._tester.test_logger.log("resolved_cores_cfg : {}".format(self.value))
				self.resolved_socket_value.append(str(self.value))
		elif self.cpu_type == "SPR":
			for socket in self._tester._pysv_mainframe._sockets:
				self._tester.test_logger.log("{}:".format(socket.name))
				self.value = socket.uncore.punit.resolved_cores_cfg.read()
				self._tester.test_logger.log("resolved_cores_cfg : {}".format(self.value))
				self.resolved_socket_value.append(str(self.value))
		self._tester.test_logger.log("Socket Available Bit Map is {}".format(self.resolved_socket_value))
		return self.resolved_socket_value


	def get_disable_bitmap(self):
		self._tester.test_logger.log("Going to collect disable bitmap on the system")
		self.socket_value = []
		if self.cpu_type in ["GNR","SRF"]:
			for socket in self._tester._pysv_mainframe._sockets:
				self._tester.test_logger.log("{}:".format(socket.name))
				self.value = socket.io0.uncore.punit.ptpcfsms.ptpcfsms.resolved_cores_cfg.read()
				self._tester.test_logger.log("resolved_cores_cfg : {}".format(self.value))
				self.socket_value.append(str(self.value))
		elif self.cpu_type == "SPR":
			for socket in self._tester._pysv_mainframe._sockets:
				self._tester.test_logger.log("{}:".format(socket.name))
				self.value = socket.uncore.punit.resolved_cores_cfg.read()
				self._tester.test_logger.log("resolved_cores_cfg : {}".format(self.value))
				self.socket_value.append(str(self.value))
		self._tester.test_logger.log("Socket Disable Bit Map is {}".format(self.socket_value))
		return self.socket_value

	def Convert_list_string(self,string):
		list1=[]
		list1[:0]=string
		return list1
	
	# binary number represented by "bin"
	def printOneComplement(self,bin):
		n = len(bin)
		ones = ""
		# for ones complement flip every bit
		for i in range(n):
			ones += self.flip(bin[i])
		ones = ones.strip("")
		return ones


	def msr_power_mgmt(self,rdmsr_data):
		self._tester.test_logger.log("rdmsr value is : {}".format(rdmsr_data))
		rdmsr = int(rdmsr_data[0],16)
		bin_value = bin(rdmsr).replace("0b", "")
		self._tester.test_logger.log("Binary equivalent of rdmsr value is {}".format(bin_value))
		rdmsr_list = self.Convert_list_string(bin_value)
		self._tester.test_logger.log("rdmsr list is : {}".format(rdmsr_list))
		self.sixth_elm = int(rdmsr_list[-7])
		self.eighth_elm = int(rdmsr_list[-9])
		# self.zeroeth_elm = int(rdmsr_list[-1])
		self._tester.test_logger.log("{} {}".format(self.sixth_elm, self.eighth_elm))
		return self.sixth_elm, self.eighth_elm

	def check_Pbit_value(self,rdmsr_data):
		self._tester.test_logger.log("rdmsr value is : {}".format(rdmsr_data))
		rdmsr = int(rdmsr_data[0],16)
		bin_value = str(bin(rdmsr).replace("0b", ""))
		self._tester.test_logger.log("Binary equivalent of rdmsr value is {}".format(bin_value))
		dec=bin_value[-8:]
		P01_bit=list(str(int(dec,2)))
		print(P01_bit)
		if len(P01_bit) == 2 and P01_bit[1] == '0':
				P01_bit = int(P01_bit[0])
		else:
			P01_bit = int(dec,2)
		rm = bin_value[:-8]
		me=rm[-8:]
		P1_bit=list(str(int(me,2)))
		if len(P1_bit) == 2 and P1_bit[1] == '0':
				P1_bit = int(P1_bit[0])
		else:
			P1_bit = int(me,2)
		
		rm = rm[:-8]
		gb=rm[-8:]
		Pn_bit=list(str(int(gb,2)))
		if len(Pn_bit) == 2 and Pn_bit[1] == '0':
				Pn_bit = int(Pn_bit[0])
		else:
			Pn_bit = int(gb,2)

		self._tester.test_logger.log("Pth bit Values from Register are P01_bit {} ".format(P01_bit))
		self._tester.test_logger.log("Pth bit Values from Register are P1_bit {} ".format(P1_bit))
		self._tester.test_logger.log("Pth bit Values from Register are Pn_bit {} ".format(Pn_bit))
		
		if self.cpu_type == "SPR":
			P01 = self._tester.sut_control.os_access.run_command("cat /sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq").combined_lines
			P01_val = P01[0]
			self._tester.test_logger.log("Value of P01_val {} ".format(P01_val))
			P01_output = int(P01_val[0:2])
			if int(P01_val[1]) == 0:
				P01_output = int(P01_val[0])
			P1 = self._tester.sut_control.os_access.run_command("cat /sys/devices/system/cpu/cpu0/cpufreq/base_frequency").combined_lines
			self._tester.test_logger.log("value of p01 after combined line command-2 : {}".format(P1))
			P02_val = P1[0]
			self._tester.test_logger.log("value of p02 that is 0th index of P1(P1[0]) after combined line command-2 : {}".format(P02_val))
			P1_output = int(P02_val[0:2])
			if int(P02_val[1]) == 0:
				P1_output = int(P02_val[0])
			Pn = self._tester.sut_control.os_access.run_command("cat /sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_min_freq").combined_lines
			P03_val = Pn[0]
			Pn_output = int(P03_val[0:2])
			if int(P03_val[1]) == 0:
				Pn_output = int(P03_val[0])
			self._tester.test_logger.log("Pth bit Values from OS are P01_output {}, P1_output {} and Pn_output {}".format(P01_output,P1_output,Pn_output))

			if P01_bit == P01_output:
				self._tester.test_logger.log("P01 values from rdmsr bit matched with OS level commands.Criteria is PASSED")
			else:
				self._tester.test_logger.log("P01_Bit:rdmsr val {} P01_output:OS val {}".format(P01_bit,P01_output))
				self._tester.exit_with_error("P01 values from rdmsr bit didnt matched with OS level commands.Criteria is FAILED")

			if P1_bit == P1_output:
				self._tester.test_logger.log("P1 values from rdmsr bit matched with OS level commands.Criteria is PASSED")
			else:
				self._tester.test_logger.log("P1_Bit:rdmsr val {} P01_output:OS val {}".format(P1_bit,P1_output))
				self._tester.exit_with_error("P1 values from rdmsr bit didnt matched with OS level commands.Criteria is FAILED")

			if Pn_bit == Pn_output:
				self._tester.test_logger.log("Pn values from rdmsr bit matched with OS level commands.Criteria is PASSED")
			else:
				self._tester.test_logger.log("Pn_Bit:rdmsr val {} Pn_output:OS val {}".format(Pn_bit,Pn_output))
				self._tester.exit_with_error("Pn values from rdmsr bit didnt matched with OS level commands.Criteria is FAILED")
			self._tester.test_logger.log("Verification is completed")

		return P01_bit,P1_bit,Pn_bit
	
	def bitmask_decreasedcore_calculation(self,socket_value, init_corecount):
		self.final_dict=[]
		self._tester.test_logger.log("Getting the bitmask decremented value..")
		value= self.socket_value
		for v1 in value:
			bit_val=v1[2:]
			self._tester.test_logger.log("Available bitmask is : {}".format(bit_val))
			bin_list1 = []
			for i in range(len(bit_val)):    
				s = bit_val[i]
				d = int(s,16)
				b = bin(d)
				if len(b) == 4:
					x = b.replace('0b','00')
				elif len(b) == 5:
					x = b.replace('0b','0')
				elif len(b) == 3:
					x = b.replace('0b','000')
				else:
					x = b.replace('0b','')
					
				bin_list1.append(x)
			bitmap_str = ''.join(map(str,bin_list1))

			setBits = [ones for ones in bitmap_str if ones=='1'] 
			self._tester.test_logger.log("Core count is {}".format(len(setBits)))
			if self.init_corecount==True:
				self.initial_core_count = len(setBits)
			else:
				self.decremented_core_count = len(setBits)
				break

			bit_val = self.Convert_list_string(bit_val)
			sub = int(bit_val[0],16) - 1
			bit_val[0]=hex(sub)[2:]
			bin_list2 = []
			for i in range(len(bit_val)):
				s = bit_val[i]
				d = int(s,16)
				b = bin(d)
				if len(b) == 4:
					x = b.replace('0b','00')
				elif len(b) == 5:
					x = b.replace('0b','0')
				elif len(b) == 3:
					x = b.replace('0b','000')
				else:
					x = b.replace('0b','')
					
				bin_list2.append(x)
			xx = bin_list2[0]
			ones_comp = self.printOneComplement(xx)
			v2 = v1[2:]
			s = hex(int(ones_comp,2))
			v3 = list(v2)

			for i in range(len(v3)):
				if i ==0:
					v3[i] = s
				else: 
					v3[i] = '0'


			new_value = "".join(v3)
			self._tester.test_logger.log("Final Decremented BitMap is {}".format(new_value))
			self.final_dict.append(new_value)

	def bitmask_singlecore_calculation(self,socket_value, init_corecount):
		self.final_dict=[]
		self._tester.test_logger.log("Getting the Bitmask Single Core value..")
		value= self.socket_value
		for v1 in value:
			bit_val=v1[2:]
			self._tester.test_logger.log("Available bitmask is : {}".format(bit_val))
			bin_list1 = []
			for i in range(len(bit_val)):    
				s = bit_val[i]
				d = int(s,16)
				b = bin(d)
				if len(b) == 4:
					x = b.replace('0b','00')
				elif len(b) == 5:
					x = b.replace('0b','0')
				elif len(b) == 3:
					x = b.replace('0b','000')
				else:
					x = b.replace('0b','')
					
				bin_list1.append(x)
			bitmap_str = ''.join(map(str,bin_list1))

			setBits = [ones for ones in bitmap_str if ones=='1'] 
			self._tester.test_logger.log("Core count is {}".format(len(setBits)))
			if self.init_corecount==True:
				self.initial_core_count = len(setBits)
			else:
				self.decremented_core_count = len(setBits)
				break

			bit_val = self.Convert_list_string(bit_val)

			if bin_list1[-1] in ['0001','0010','0100','1000']:
				pass
			elif bin_list1[-1] in ['1100','1010','1001','1111','1110','1011','1101']:
				bin_list1[-1] = '1000'
			elif bin_list1[-1] in ['0110','0101','0111']:
				bin_list1[-1] = '0100'
			elif bin_list1[-1] in ['0011']:
				bin_list1[-1] = '0010'

			bin_list1[-1] = self.printOneComplement(bin_list1[-1])
			s= hex(int(bin_list1[-1], 2))

			bit_val[-1] = s
			bin_list2 = []
			for i in range(len(bit_val)):
				
				s = bit_val[i]
				
				d = int(s,16)
				b = bin(d)
				if len(b) == 4:
					x = b.replace('0b','00')
				elif len(b) == 5:
					x = b.replace('0b','0')
				elif len(b) == 3:
					x = b.replace('0b','000')
				else:
					x = b.replace('0b','')
					
				bin_list2.append(x)
			self._tester.test_logger.log("Binary value of bitmask : {}".format(bin_list2))
			xx = bit_val[-1][2:]
			v2 = v1[2:]
			v3 = list(v2)

			for i in range(len(v3)):
				if i == (len(v3)-1):
					v3[i] = xx
				else:
					v3[i] = 'F'

			new_value = "".join(v3)
			new_value = '0x'+new_value
			self._tester.test_logger.log("Final Single Core BitMap is {}".format(new_value))
			self.final_dict.append(new_value)

	def check_dmesg_HWP(self):
		dmesg_value = self._tester.sut_control.os_access.run_command("dmesg | grep -i 'HWP enabled' ").combined_lines
		self._tester.test_logger.log("Dmesg value : {}".format(dmesg_value))
		dmesg_val_str = str(dmesg_value)
		if dmesg_val_str.find("HWP enabled"):
			self._tester.test_logger.log("HWP enabled in the BIOS")
			hwp = True
		else:
			self._tester.test_logger.log("HWP is Disabled in BIOS")
			hwp = False
		return hwp


	def setup_logging(self):
		if self._tester.sut_control.sut_os_type in [OS_TYPE.FEDORA.name, OS_TYPE.SLES.name, OS_TYPE.CENTOS.name, OS_TYPE.REDHAT.name, OS_TYPE.CLEARLINUX.name]:
			self._tester.test_logger.log("Will save logs to {}".format(self.pi_pm_applog_folder))
		elif self._tester.sut_control.sut_os_type == OS_TYPE.WINDOWS:
			self._tester.test_logger.log("Will save logs to {}".format(self.pi_pm_applog_folder_win))


	def check_rdmsr_value(self, register_val):
		self.register_val = register_val
		if self.cpu_type =="SPR":
			self._tester.test_logger.log("*******Checking Register value using MSR ***********")
			register_ret = self._tester.sut_control.os_access.run_command('rdmsr '+self.register_val).combined_lines
			self._tester.test_logger.log("RDMSR value for {} : {}".format(self.register_val, register_ret))
		elif self.cpu_type in ["GNR","SRF"]:
			self._tester.test_logger.log("****** Checking Register value using pmutil commands********")
			register_ret = self._tester.sut_control.os_access.run_command('cd {}; ./pmutil_bin -r '.format(self.app_pmutil_path)+self.register_val).combined_lines
			self._tester.test_logger.log("Value at {} using pmutil command is : {}".format(self.register_val, register_ret))
		return register_ret 

	def get_peci_val(self):
		self._tester.sut_control.os_access.run_command("cd /home/root;chmod 777 *".format(self.msr_dir))
		cmd = "cd /home/root;./power_peci.sh"
		#cmd = "/home/root/power_peci.sh"
		self.peci_val_list = self._tester.sut_control.bmc_access.run_command(cmd).combined_lines
		return self.peci_val_list


	def extract_peci_val(self, peci_val_list):
		self.peci_val_list = peci_val_list
		self._tester.test_logger.log(self.peci_val_list)
		self.peci_final_list =[]
		for ele in self.peci_val_list:
			out=ele.split('=')[1]
			self.peci_final_list.append(out[14:])
		self._tester.test_logger.log(self.peci_final_list)
		self.peci_soc0_energy1 = int(self.peci_final_list[0],16)
		self.peci_soc0_energy2 = int(self.peci_final_list[1],16)
		self.peci_soc1_energy1 = int(self.peci_final_list[2],16)
		self.peci_soc1_energy2 = int(self.peci_final_list[3],16)
		self.peci_plt_energy1 = int(self.peci_final_list[4],16)
		self.peci_plt_energy2 = int(self.peci_final_list[5],16)

		return [self.peci_soc0_energy1,self.peci_soc0_energy2,self.peci_soc1_energy1,self.peci_soc1_energy2,self.peci_plt_energy1,self.peci_plt_energy2]

	def get_rdmsr_val(self):
		self._tester.sut_control.os_access.run_command("cd {};chmod 777 *".format(self.msr_dir))
		cmd = "cd /root/apps/PI_PM/msr-tools-master;./power_rdmsr.sh"
		self.rdmsr_val_list = self._tester.sut_control.os_access.run_command(cmd).combined_lines

		return self.rdmsr_val_list

	def extract_rdmsr_val(self, rdmsr_val_list):
		self.rdmsr_val_list = rdmsr_val_list
		self._tester.test_logger.log(self.rdmsr_val_list)
		self.rdmsr_final_list =[]
		for ele in self.rdmsr_val_list:
			out=ele.split('=')[1]
			self.rdmsr_final_list.append(out[1:])
		self._tester.test_logger.log(self.rdmsr_final_list)
		#Socket energy 'cmd =./rdmsr 0x611'
		self.rdmsr_soc0_energy1 = int(self.rdmsr_final_list[0],16)
		self.rdmsr_soc0_energy2 = int(self.rdmsr_final_list[1],16)

		#Platform Energy and timestamp calculations. 'cmd=./rdmsr 0x64d'
		# print(self.rdmsr_final_list[2][-8:])
		# print(self.rdmsr_final_list[3][-8:])
		# print(self.rdmsr_final_list[2][-16:-8])
		# print(self.rdmsr_final_list[3][-16:-8])
		self.platform_energy_rdmsr1=int(self.rdmsr_final_list[2][-8:],16)
		self.platform_energy_rdmsr2=int(self.rdmsr_final_list[3][-8:],16)
		self.platform_energy_tsc1 = int(self.rdmsr_final_list[2][-16:-8],16)
		self.platform_energy_tsc2 =int(self.rdmsr_final_list[3][-16:-8],16)

		return [self.rdmsr_soc0_energy1,self.rdmsr_soc0_energy2,self.platform_energy_rdmsr1,self.platform_energy_tsc1,self.platform_energy_rdmsr2,self.platform_energy_tsc2]
	
	def run_ptu_mon_csv(self):
		self._tester.test_logger.log("Running PTU monitor....")
		self.logfilename = "PI_PM_{time}".format(time=self._tester._logger.make_ts(file_ts=True))
		self.ptu_mon_log = "{app_logs}/{filename}_ptumon.csv".format(app_logs=self.pi_pm_applog_folder, filename=self.logfilename)
		self._tester.sut_control.os_access.run_command("cd {};chmod 777 *".format(self.ptu_dir))
		self.ptu_mon_cmd = "cd {};./ptu -mon -filter 0x0F -csv -log -logdir {} -logname {}".format(self.ptu_dir, self.pi_pm_applog_folder,self.logfilename)
		self._tester.test_logger.log(self.ptu_mon_cmd)
		self._tester.sut_control.os_access.run_command(self.ptu_mon_cmd)
		return self.ptu_mon_log

	
	def check_cpu_power(self):
		self._tester.test_logger.log("PTU mon CSV log file path is {}".format(self.csv_filepath))
		col_list = ["Device" , " Power"]
		df = pd.read_csv(self.csv_filepath, usecols=col_list, index_col=[0])
		df1=df.head(-1)
		df1=df1.tail(2)
		self.power_output = df1.to_dict('dict')
		self._tester.test_logger.log("Power value for CPU0:{}".format(self.power_output[' Power']['  CPU0']))
		self._tester.test_logger.log("Power value for CPU1:{}".format(self.power_output[' Power']['  CPU1']))
		return self.power_output

	def calculate_pecentage_diff_with_logmsg(self, x, y, i, j, percent_value,log_str1,log_str2):
		self._tester.test_logger.log("checking % difference between the {} and {}".format(log_str1,log_str2))
		self.percent_value = percent_value
		self.soc0_val = x
		self.soc1_val = i 
		self.socket0_throttled_duration = y 
		self.socket1_throttled_duration = j

		# Calculation =>  a = (x-y) b=(x+y)/2 ; int(a/b*100) shpuld be in 1% range
		#if self.platform_rapl_perf_status_socket0 > self.socket0_throttled_duration_per_core_val:
		if self.soc0_val > self.socket0_throttled_duration and self.soc1_val > self.socket1_throttled_duration:
			a = self.soc0_val - self.socket0_throttled_duration
			b = (self.soc0_val + self.socket0_throttled_duration)/2 
			self.cal_socket0 = int((a/b)*100)

			a = self.soc1_val - self.socket1_throttled_duration
			b = (self.soc1_val + self.socket1_throttled_duration)/2 
			self.cal_socket1 =int((a/b)*100)

			if self.cal_socket0 <= self.percent_value and self.cal_socket1 <= self.percent_value:
				self._tester.test_logger.log("PASS: Percentage Difference between {} and {} for socket0 {} and socket1 {} =< {}%".format(log_str1,log_str2,self.cal_socket0, self.cal_socket1,self.percent_value))
			else:
				self._tester.exit_with_error("FAIL: Percentage Difference between {} and {} for socket0 {} and socket1 {} > {}%".format(log_str1,log_str2,self.cal_socket0, self.cal_socket1, self.percent_value))

		else:
			# Calculation =>  a = (y-x) b=(y+x)/2 ; int(a/b*100) should be in 1% range
			a = self.socket0_throttled_duration - self.soc0_val
			b = (self.socket0_throttled_duration + self.soc0_val)/2 
			self.cal_socket0 =int((a/b)*100)

			a = self.socket1_throttled_duration - self.soc1_val
			b = (self.socket1_throttled_duration + self.soc1_val)/2 
			self.cal_socket1 = int((a/b)*100)

			if self.cal_socket0 <= self.percent_value and self.cal_socket1 <= self.percent_value:
				self._tester.test_logger.log("PASS: Percentage Difference between {} and {} for socket0 {} and socket1 {} =< {}%".format(log_str1,log_str2,self.cal_socket0, self.cal_socket1,self.percent_value))
			else:
				self._tester.exit_with_error("FAIL: Percentage Difference between {} and {} for socket0 {} and socket1 {} > {}%".format(log_str1,log_str2,self.cal_socket0, self.cal_socket1, self.percent_value))

	def calculate_percent_diff_two_val(self,x,y,percent):
		self._tester.test_logger.log("Checking the % difference between the two platform power consumption value")
		self.percent_value=percent
		self.val1=x
		self.val2=y
		# y should be between +/- 3% of x

		self.lower_limit=self.val1-((self.percent_value*self.val1)/100)
		self.upper_limit=self.val1+((self.percent_value*self.val1)/100)
		if self.lower_limit <= self.val2 <= self.upper_limit:
			self._tester.test_logger.log("The platform power is with +/-3% within the range!")
		else:
			self._tester.exit_with_error("The platform power is out of +/-3% range!")



	def calculate_pecentage_diff(self, x, y, i, j, percent_value):
		self._tester.test_logger.log("Checking the % difference between the Platform_RAPL_Perf_Status with Throttling duration per core from PECI for the matching socket number")
		self.percent_value = percent_value
		self.soc0_val = x
		self.soc1_val = i 
		self.socket0_throttled_duration = y 
		self.socket1_throttled_duration = j

		# Calculation =>  a = (x-y) b=(x+y)/2 ; int(a/b*100) shpuld be in 1% range
		#if self.platform_rapl_perf_status_socket0 > self.socket0_throttled_duration_per_core_val:
		if self.soc0_val > self.socket0_throttled_duration:
			a = self.soc0_val - self.socket0_throttled_duration
			b = (self.soc0_val + self.socket0_throttled_duration)/2 
			self.cal_socket0 = int((a/b)*100)

			a = self.soc1_val - self.socket1_throttled_duration
			b = (self.soc1_val + self.socket1_throttled_duration)/2 
			self.cal_socket1 = int((a/b)*100)

			if self.cal_socket0 <= self.percent_value and self.cal_socket1 <= self.percent_value:
				self._tester.test_logger.log("PASS: %diff of platform_rapl_perf_status_socket and socket_throttled_duration_cores =< {}%".format(self.percent_value))
			else:
				self._tester.exit_with_error("FAIL: %diff of platform_rapl_perf_status_socket:{} and socket_throttled_duration_cores:{} > {}%".format(self.cal_socket0, self.cal_socket1, self.percent_value))

		else:
			# Calculation =>  a = (y-x) b=(y+x)/2 ; int(a/b*100) should be in 1% range
			a = self.socket0_throttled_duration - self.soc0_val
			b = (self.socket0_throttled_duration + self.soc0_val)/2 
			self.cal_socket0 = int((a/b)*100)

			a = self.socket1_throttled_duration - self.soc1_val
			b = (self.socket1_throttled_duration + self.soc1_val)/2 
			self.cal_socket1 = int((a/b)*100)

			if self.cal_socket0 <= self.percent_value and self.cal_socket1 <= self.percent_value:
				self._tester.test_logger.log("PASS: %diff of platform_rapl_perf_status_socket and socket_throttled_duration_cores =< {}%".format(self.percent_value))
			else:
				self._tester.exit_with_error("FAIL: %diff of platform_rapl_perf_status_socket:{} and socket_throttled_duration_cores:{} > 1%".format(self.cal_socket0, self.cal_socket1, self.percent_value))
	

	def set_and_check_peci_cmds(self,peci_cmds_soc0,peci_cmds_soc1):
		self._tester.test_logger.log("Setting the PPL1 to reduced platform power via PECI PCS and checking status code")

		self.output1 = self._tester.sut_control.bmc_access.run_command(self.peci_cmds_soc0, verify=True).combined_lines
		self._tester.test_logger.log("The peci_cmds output for Socket0 is {}".format(self.output1))

		self.output2 = self._tester.sut_control.bmc_access.run_command(self.peci_cmds_soc1, verify=True).combined_lines
		self._tester.test_logger.log("The peci_cmds output for Socket1 is {}".format(self.output2))

		if '40' in self.output1[0]:
			self._tester.test_logger.log("The 1st PECI command ran successfully and returned Completion Code(cc:40)")
		else:
			self._tester.exit_with_error(f"The 1st PECI command returned completion code: {self.output_status1[0]} , other than cc:40, Test Failed!")
		
		if '40' in self.output2[0]:
			self._tester.test_logger.log("The 2nd PECI command ran successfully and returned Completion Code(cc:40)")
		else:
			self._tester.exit_with_error(f"The 2nd PECI command returned completion code: {self.output_status1[0]} , other than cc:40, Test Failed!")
			   

		



	def check_peci_val_increment(self,peci_cmds_socket0,peci_cmds_socket1):
		self._tester.test_logger.log("Reading the PECI PCS POWER_THROTTLED_DURATION register via PECI cmds in bmc terminal")

		self.output = self._tester.sut_control.bmc_access.run_command(self.peci_cmds_socket0, verify=True).combined_lines
		self._tester.test_logger.log("The peci_cmds output for Socket0 is {}".format(self.output))
		self.peci_val = self.output[0][13:]
		self.peci_soc0_val = int(self.peci_val, 16)
		time.sleep(5)
		self.output = self._tester.sut_control.bmc_access.run_command(self.peci_cmds_socket0, verify=True).combined_lines
		self._tester.test_logger.log("The peci_cmds output for Socket0 is {}".format(self.output))
		self.peci_val = self.output[0][13:]
		self.peci1_soc0_val = int(self.peci_val, 16)

		if self.peci1_soc0_val > self.peci_soc0_val:
			self._tester.test_logger.log("PASS : PECI PCS register value has incremented successfully for Socket0 after launching PTU WL.")
		else:
			self._tester.test_logger.log("FAIL : PECI PCS register value has not incremented for Socket0 after launching PTU WL")

		self.output = self._tester.sut_control.bmc_access.run_command(self.peci_cmds_socket1, verify=True).combined_lines
		self._tester.test_logger.log("The peci_cmds output for Socket1 is {}".format(self.output))
		self.peci_val = self.output[0][13:]
		self.peci_soc1_val = int(self.peci_val, 16)
		time.sleep(5)
		self.output = self._tester.sut_control.bmc_access.run_command(self.peci_cmds_socket1, verify=True).combined_lines
		self._tester.test_logger.log("The peci_cmds output for Socket1 is {}".format(self.output))
		self.peci_val = self.output[0][13:]
		self.peci1_soc1_val = int(self.peci_val, 16)

		if self.peci1_soc1_val > self.peci_soc1_val:
			self._tester.test_logger.log("PASS : PECI PCS register value has incremented successfully for Socket1 after launching PTU WL.")
		else:
			self._tester.test_logger.log("FAIL : PECI PCS register value has not incremented for Socket1 after launching PTU WL")

		return [self.peci1_soc0_val, self.peci1_soc1_val]

	
	def check_peci_val_static(self,peci_cmds_socket0,peci_cmds_socket1):
		self._tester.test_logger.log("Reading the PECI PCS POWER_THROTTLED_DURATION via PECI Cmds in bmc terminal")
		err_flag = False

		self.output = self._tester.sut_control.bmc_access.run_command(self.peci_cmds_socket0, verify=True).combined_lines
		self._tester.test_logger.log("The peci_cmds output for Socket0 is {}".format(self.output))
		self.peci_val = self.output[0][13:]
		self.peci_soc0_val = int(self.peci_val, 16)
		time.sleep(5)
		self.output = self._tester.sut_control.bmc_access.run_command(self.peci_cmds_socket0, verify=True).combined_lines
		self._tester.test_logger.log("The peci_cmds output for Socket0 is {}".format(self.output))
		self.peci_val = self.output[0][13:]
		self.peci1_soc0_val = int(self.peci_val, 16)
		if self.peci1_soc0_val == self.peci_soc0_val:
			self._tester.test_logger.log("PASS : PECI PCS register value has not incremented for Socket0 after stopping PTU WL")
		else:
			err_flag = True
			self._tester.test_logger.log("FAIL : PECI PCS register value has incremented for Socket0 after stopping PTU WL")

		self.output = self._tester.sut_control.bmc_access.run_command(self.peci_cmds_socket1, verify=True).combined_lines
		self._tester.test_logger.log("The peci_cmds output for Socket1 is {}".format(self.output))
		self.peci_val = self.output[0][13:]
		self.peci_soc1_val = int(self.peci_val, 16)
		time.sleep(5)
		self.output = self._tester.sut_control.bmc_access.run_command(self.peci_cmds_socket1, verify=True).combined_lines
		self._tester.test_logger.log("The peci_cmds output for Socket1 is {}".format(self.output))
		self.peci_val = self.output[0][13:]
		self.peci1_soc1_val = int(self.peci_val, 16)
		if self.peci1_soc1_val == self.peci_soc1_val:
			self._tester.test_logger.log("PASS : PECI PCS register value has not incremented for Socket1")
		else:
			self._tester.test_logger.log("FAIL : PECI PCS register value has incremented for Socket1 after stopping PTU WL")
			err_flag = True
		
		if err_flag:
			self._tester.test_logger.log("FAIL : PECI PCS register value has incremented for Sockets after stopping the WL. Please check logs for details.")
		return [self.peci1_soc0_val, self.peci1_soc1_val]

	
	def frequency_calculator(self):
		_sv_sockets = self._tester.sv_control.sv_sockets
		for socket in _sv_sockets:
			sse_act_val = socket.pcudata.fused_turbo_ratio_limit_ratios_cdyn_index0_ratio7#SSE all core turbo
			avx2_bin_bucket7 = socket.pcudata.fused_turbo_ratio_limit_ratios_cdyn_index1_ratio7 #AVX2 all core turbo
			avx512_bin_bucket7 = socket.pcudata.fused_turbo_ratio_limit_ratios_cdyn_index2_ratio7 #avx512 all core turbo
			sse_freq_val = socket.pcudata.fused_config_tdp_0_cdyn_index0_p1_ratio #SSE P1
			avx2_freq_val = socket.pcudata.fused_config_tdp_0_cdyn_index1_p1_ratio #AVX2 P1
			avx512_freq_val = socket.pcudata.fused_config_tdp_0_cdyn_index2_p1_ratio #AVX512 P1
			sse_bin_bucket0 = socket.pcudata.fused_turbo_ratio_limit_ratios_cdyn_index0_ratio0
			avx2_bin_bucket0 = socket.pcudata.fused_turbo_ratio_limit_ratios_cdyn_index1_ratio0
			avx512_bin_bucket0 = socket.pcudata.fused_turbo_ratio_limit_ratios_cdyn_index2_ratio0
			tmul_bin_bucket0 =  socket.pcudata.fused_turbo_ratio_limit_ratios_cdyn_index3_ratio0
			tmul_freq = socket.pcudata.fused_config_tdp_0_cdyn_index3_p1_ratio
	

		#converting values to MGHZ
		self.sse_act_val = int(str(sse_act_val),16)*100
		self.sse_freq_val = int(str(sse_freq_val),16)*100
		self.sse_bin_bucket0 = int(str(sse_bin_bucket0),16)*100
		
		self.avx2_freq_val = int(str(avx2_freq_val),16)*100
		self.avx2_bin_bucket0 = int(str(avx2_bin_bucket0),16)*100
		self.avx2_bin_bucket7 = int(str(avx2_bin_bucket7),16)*100
		
		self.avx512_freq_val = int(str(avx512_freq_val),16)*100
		self.avx512_bin_bucket0 = int(str(avx512_bin_bucket0),16)*100
		self.avx512_bin_bucket7 = int(str(avx512_bin_bucket7),16)*100

		self.tmul_bin_bucket0 = int(str(tmul_bin_bucket0),16)*100
		self.tmul_freq = int(str(tmul_freq),16)*100
		
		self._tester.test_logger.log("SSE ACT Frequency is {}".format(self.sse_act_val))
		self._tester.test_logger.log("SSE P1 Frequency is {}".format(self.sse_freq_val))
		self._tester.test_logger.log("AVX2 P1 Frequency is {}".format(self.avx2_freq_val))
		self._tester.test_logger.log("AVX512 P1 Frequency is {}".format(self.avx512_freq_val))
		self._tester.test_logger.log("TMUL Frequency is {}".format(self.tmul_freq))
		#self._tester.test_logger.log("TDP Frequency is {}".format(self.tdp_val))
		self._tester.test_logger.log("SSE Bucket0 frequency is {}".format(self.sse_bin_bucket0))
		self._tester.test_logger.log("AVX2 Bucket0 frequency is {}".format(self.avx2_bin_bucket0))
		self._tester.test_logger.log("AVX512 Bucket0 frequency is {}".format(self.avx512_bin_bucket0))
		self._tester.test_logger.log("TMUL Bucket0 frequency is {}".format(self.tmul_bin_bucket0))
		
		return [self.sse_act_val,self.avx2_freq_val,self.avx512_freq_val,self.sse_freq_val,self.sse_bin_bucket0,self.avx2_bin_bucket0,self.avx512_bin_bucket0,self.tmul_bin_bucket0,self.tmul_freq,self.avx2_bin_bucket7,self.avx512_bin_bucket7]

	
	def get_sse_bucket_freq(self):
		_sv_sockets = self._tester.sv_control.sv_sockets
		sse_freqs = []
			
		if self.cpu_type == "SPR":
			for bkt in range(8):
				sse_freqs.append("socket.pcudata.fused_turbo_ratio_limit_ratios_cdyn_index0_ratio{}".format(bkt))
		
		elif self.cpu_type in ["GNR","SRF"]:
			if self._tester.sut_control.sut_os_type in [OS_TYPE.FEDORA.name, OS_TYPE.SLES.name, OS_TYPE.CENTOS.name, OS_TYPE.REDHAT.name, OS_TYPE.CLEARLINUX.name]:
				self.gnr_get_pmutil_freq()
				p1_freq_val = self.pmutil_P1_freq[0].split(":")[1][3:] #18181818
				if len(p1_freq_val) == 7:
					p1_freq_val = '0'+ p1_freq_val
				self.sse_bucket0_val = int(str(p1_freq_val[-2:]),16)*100
				self.sse_bucket1_val = int(str(p1_freq_val[-4:-2]),16)*100
				self.sse_bucket2_val = int(str(p1_freq_val[-6:-4]),16)*100
				self.sse_bucket3_val = int(str(p1_freq_val[-8:-6]),16)*100
				self.sse_bucket4_val = int(str(p1_freq_val[-10:-8]),16)*100
				self.sse_bucket5_val = int(str(p1_freq_val[-12:-10]),16)*100
				self.sse_bucket6_val = int(str(p1_freq_val[-14:-12]),16)*100
				self.sse_bucket7_val = int(str(p1_freq_val[:-14:1]),16)*100
	
			elif self._tester.sut_control.sut_os_type == OS_TYPE.WINDOWS.name:
				cfg = self.gnr_get_sst_pp_level()
				for bkt in range(8):
					if cfg in[0,1,2,3,4]:
						sse_freqs.append("socket.io0.fuses.punit_iosf_sb.pcode_sst_pp_{}_turbo_ratio_limit_ratios_cdyn_index0_ratio{} ".format(cfg,bkt))
		
		if self.cpu_type in ["GNR","SRF"] and self._tester.sut_control.sut_os_type in [OS_TYPE.FEDORA.name, OS_TYPE.SLES.name, OS_TYPE.CENTOS.name, OS_TYPE.REDHAT.name, OS_TYPE.CLEARLINUX.name]:
			pass
		else:
			self._tester.test_logger.log("PYSV commands for Fetching SSE Bucket frequency values are as below")
			for cmd in sse_freqs:
				self._tester.test_logger.log(cmd)
			
			for socket in _sv_sockets:
				#converting values to MGHZ
				self.sse_bucket0_val = int(str(eval(sse_freqs[0])),16)*100
				self.sse_bucket1_val = int(str(eval(sse_freqs[1])),16)*100
				self.sse_bucket2_val = int(str(eval(sse_freqs[2])),16)*100
				self.sse_bucket3_val = int(str(eval(sse_freqs[3])),16)*100
				self.sse_bucket4_val = int(str(eval(sse_freqs[4])),16)*100
				self.sse_bucket5_val = int(str(eval(sse_freqs[5])),16)*100
				self.sse_bucket6_val = int(str(eval(sse_freqs[6])),16)*100
				self.sse_bucket7_val = int(str(eval(sse_freqs[7])),16)*100

		return [self.sse_bucket0_val, self.sse_bucket1_val, self.sse_bucket2_val, self.sse_bucket3_val, self.sse_bucket4_val,self.sse_bucket5_val, self.sse_bucket6_val,self.sse_bucket7_val]


	def get_avx2_bucket_freq(self):
		avx2_freqs = []
		_sv_sockets = self._tester.sv_control.sv_sockets
			
		if self.cpu_type == "SPR":
			for bkt in range(8):
				avx2_freqs.append("socket.pcudata.fused_turbo_ratio_limit_ratios_cdyn_index1_ratio{}".format(bkt))
		
		elif self.cpu_type in ["GNR","SRF"]:
			if self._tester.sut_control.sut_os_type in [OS_TYPE.FEDORA.name, OS_TYPE.SLES.name, OS_TYPE.CENTOS.name, OS_TYPE.REDHAT.name, OS_TYPE.CLEARLINUX.name]:
	
				self.gnr_get_pmutil_freq()
				avx2_trl = self.pmutil_avx2_freq[0].split(":")[1][3:]
				self.avx2_bucket0_val = int(str(avx2_trl[-2:]),16)*100
				self.avx2_bucket1_val = int(str(avx2_trl[-4:-2]),16)*100
				self.avx2_bucket2_val = int(str(avx2_trl[-6:-4]),16)*100
				self.avx2_bucket3_val = int(str(avx2_trl[-8:-6]),16)*100
				self.avx2_bucket4_val = int(str(avx2_trl[-10:-8]),16)*100
				self.avx2_bucket5_val = int(str(avx2_trl[-12:-10]),16)*100
				self.avx2_bucket6_val = int(str(avx2_trl[-14:-12]),16)*100
				self.avx2_bucket7_val = int(str(avx2_trl[:-14:1]),16)*100

			elif self._tester.sut_control.sut_os_type == OS_TYPE.WINDOWS.name:  
				cfg = self.gnr_get_sst_pp_level()
				for bkt in range(8):
					if cfg in[0,1,2,3,4]:
						avx2_freqs.append("socket.io0.fuses.punit_iosf_sb.pcode_sst_pp_{}_turbo_ratio_limit_ratios_cdyn_index1_ratio{}".format(cfg,bkt))
		
		if self.cpu_type in ["GNR","SRF"] and self._tester.sut_control.sut_os_type in [OS_TYPE.FEDORA.name, OS_TYPE.SLES.name, OS_TYPE.CENTOS.name, OS_TYPE.REDHAT.name, OS_TYPE.CLEARLINUX.name]:
			pass
		else:   
			self._tester.test_logger.log("PYSV commands for Fetching SSE Bucket frequency values are as below")
			for cmd in avx2_freqs:
				self._tester.test_logger.log(cmd)
			
			for socket in _sv_sockets: 
				#converting values to MGHZ
				self.avx2_bucket0_val = int(str(eval(avx2_freqs[0])),16)*100
				self.avx2_bucket1_val = int(str(eval(avx2_freqs[1])),16)*100
				self.avx2_bucket2_val = int(str(eval(avx2_freqs[2])),16)*100
				self.avx2_bucket3_val = int(str(eval(avx2_freqs[3])),16)*100
				self.avx2_bucket4_val = int(str(eval(avx2_freqs[4])),16)*100
				self.avx2_bucket5_val = int(str(eval(avx2_freqs[5])),16)*100
				self.avx2_bucket6_val = int(str(eval(avx2_freqs[6])),16)*100
				self.avx2_bucket7_val = int(str(eval(avx2_freqs[7])),16)*100

		return [self.avx2_bucket0_val, self.avx2_bucket1_val, self.avx2_bucket2_val, self.avx2_bucket3_val, self.avx2_bucket4_val,self.avx2_bucket5_val, self.avx2_bucket6_val,self.avx2_bucket7_val]

	def get_avx512_bucket_freq(self):
		avx512_freqs = []
		_sv_sockets = self._tester.sv_control.sv_sockets
		
		if self.cpu_type == "SPR":
			for bkt in range(8):
				avx512_freqs.append("socket.pcudata.fused_turbo_ratio_limit_ratios_cdyn_index2_ratio{}".format(bkt))
		
		elif self.cpu_type in ["GNR","SRF"]:    
			if self._tester.sut_control.sut_os_type in [OS_TYPE.FEDORA.name, OS_TYPE.SLES.name, OS_TYPE.CENTOS.name, OS_TYPE.REDHAT.name, OS_TYPE.CLEARLINUX.name]:
			
				self.gnr_get_pmutil_freq()

				avx512_trl = self.pmutil_avx512_freq[0].split(":")[1][3:]
				
				#converting values to MGHZ
				self.avx512_bucket0_val = int(str(avx512_trl[-2:]),16)*100
				self.avx512_bucket1_val = int(str(avx512_trl[-4:-2]),16)*100
				self.avx512_bucket2_val = int(str(avx512_trl[-6:-4]),16)*100
				self.avx512_bucket3_val = int(str(avx512_trl[-8:-6]),16)*100
				self.avx512_bucket4_val = int(str(avx512_trl[-10:-8]),16)*100
				self.avx512_bucket5_val = int(str(avx512_trl[-12:-10]),16)*100
				self.avx512_bucket6_val = int(str(avx512_trl[-14:-12]),16)*100
				self.avx512_bucket7_val = int(str(avx512_trl[:-14:1]),16)*100

			elif self._tester.sut_control.sut_os_type == OS_TYPE.WINDOWS.name:
				cfg = self.gnr_get_sst_pp_level()
				for bkt in range(8):
					if cfg in[0,1,2,3,4]:
						avx512_freqs.append("socket.io0.fuses.punit_iosf_sb.pcode_sst_pp_{}_turbo_ratio_limit_ratios_cdyn_index2_ratio{}".format(cfg,bkt))
							
		if self.cpu_type in ["GNR","SRF"] and self._tester.sut_control.sut_os_type in [OS_TYPE.FEDORA.name, OS_TYPE.SLES.name, OS_TYPE.CENTOS.name, OS_TYPE.REDHAT.name, OS_TYPE.CLEARLINUX.name]:
			pass
		else:
			self._tester.test_logger.log("PYSV commands for Fetching AVX512 Bucket frequency values are as below")
			for cmd in avx512_freqs:
				self._tester.test_logger.log(cmd)
			
			for socket in _sv_sockets: 
				#converting values to MGHZ
				self.avx512_bucket0_val = int(str(eval(avx512_freqs[0])),16)*100
				self.avx512_bucket1_val = int(str(eval(avx512_freqs[1])),16)*100
				self.avx512_bucket2_val = int(str(eval(avx512_freqs[2])),16)*100
				self.avx512_bucket3_val = int(str(eval(avx512_freqs[3])),16)*100
				self.avx512_bucket4_val = int(str(eval(avx512_freqs[4])),16)*100
				self.avx512_bucket5_val = int(str(eval(avx512_freqs[5])),16)*100
				self.avx512_bucket6_val = int(str(eval(avx512_freqs[6])),16)*100
				self.avx512_bucket7_val = int(str(eval(avx512_freqs[7])),16)*100


		return [self.avx512_bucket0_val, self.avx512_bucket1_val, self.avx512_bucket2_val, self.avx512_bucket3_val, self.avx512_bucket4_val,self.avx512_bucket5_val, self.avx512_bucket6_val,self.avx512_bucket7_val]

	def get_num_cores(self):
		core_list = []
		_sv_sockets = self._tester.sv_control.sv_sockets
			
		if self.cpu_type == "SPR":
			for num in range(8):
				core_list.append("socket.pcudata.fused_turbo_ratio_limit_cores_numcore{}".format(num))

		elif self.cpu_type in ["GNR","SRF"]:
			if self._tester.sut_control.sut_os_type in [OS_TYPE.FEDORA.name, OS_TYPE.SLES.name, OS_TYPE.CENTOS.name, OS_TYPE.REDHAT.name, OS_TYPE.CLEARLINUX.name]:
				self.gnr_get_pmutil_freq()
				numcore_val = self.pmutil_numcore_val[0].split(":")[1][3:]
				self.numcore0 = int(str(numcore_val[-2:]),16)
				self.numcore1 = int(str(numcore_val[-4:-2]),16)
				self.numcore2 = int(str(numcore_val[-6:-4]),16)
				self.numcore3 = int(str(numcore_val[-8:-6]),16)
				self.numcore4 = int(str(numcore_val[-10:-8]),16)
				self.numcore5 = int(str(numcore_val[-12:-10]),16)
				self.numcore6 = int(str(numcore_val[-14:-12]),16)
				self.numcore7 = int(str(numcore_val[:-14:1]),16)

			elif self._tester.sut_control.sut_os_type == OS_TYPE.WINDOWS.name:
				cfg = self.gnr_get_sst_pp_level()
				for num in range(8):
					core_list.append("socket.io0.fuses.punit_iosf_sb.pcode_sst_pp_{}_turbo_ratio_limit_cores_numcore{}".format(cfg,num))
			
		if self.cpu_type in ["GNR","SRF"] and self._tester.sut_control.sut_os_type in [OS_TYPE.FEDORA.name, OS_TYPE.SLES.name, OS_TYPE.CENTOS.name, OS_TYPE.REDHAT.name, OS_TYPE.CLEARLINUX.name]:
			pass
		else:
			self._tester.test_logger.log("PYSV commands for Fetching NUMCORE values are as below")
			for cmd in core_list:
				self._tester.test_logger.log(cmd)
			
			for socket in _sv_sockets: 
				self.numcore0 = int(str(eval(core_list[0])),16)
				self.numcore1 = int(str(eval(core_list[1])),16)
				self.numcore2 = int(str(eval(core_list[2])),16)
				self.numcore3 = int(str(eval(core_list[3])),16)
				self.numcore4 = int(str(eval(core_list[4])),16)
				self.numcore5 = int(str(eval(core_list[5])),16)
				self.numcore6 = int(str(eval(core_list[6])),16)
				self.numcore7 = int(str(eval(core_list[7])),16)             

				# self.numcore0 = 4
				# self.numcore1 = 6
				# self.numcore2 = 8
				# self.numcore3 = 10
				# self.numcore4 = 12
				# self.numcore5 = 14
				# self.numcore6 = 16
				# self.numcore7 = 16                


		return [self.numcore0, self.numcore1, self.numcore2, self.numcore3, self.numcore4, self.numcore5, self.numcore6, self.numcore7]

	def get_disablemap_knob(self):
		self.socket_count = int(self._frame.sv_control.socket_count)
		self._tester.test_logger.log("Current Socket Count is : {}".format(self.socket_count))
		if self.socket_count == 2:
			self.socket0_knobvalue=self.final_dict[0]
			self.socket1_knobvalue=self.final_dict[1]
			self.knob ='CoreDisableMask_0={} , CoreDisableMask_1={}'.format(self.socket0_knobvalue,self.socket1_knobvalue)
		elif self.socket_count == 4:
			self.socket0_knobvalue=self.final_dict[0]
			self.socket1_knobvalue=self.final_dict[1]
			self.socket2_knobvalue=self.final_dict[2]
			self.socket3_knobvalue=self.final_dict[3]
			self.knob ='CoreDisableMask_0={} , CoreDisableMask_1={}, CoreDisableMask_2={} , CoreDisableMask_3={}'.format(self.socket0_knobvalue,self.socket1_knobvalue, self.socket2_knobvalue, self.socket3_knobvalue)
		self._tester.test_logger.log("Bios knob to set : {}".format(self.knob))
		return self.knob

	def hex_to_binary_converter(self,bit_val):
		self.bin_list1 = []
		for i in range(len(bit_val)):    
			s = bit_val[i]
			d = int(s,16)
			b = bin(d)
			if len(b) == 4:
				x = b.replace('0b','00')
			elif len(b) == 5:
				x = b.replace('0b','0')
			elif len(b) == 3:
				x = b.replace('0b','000')
			else:
				x = b.replace('0b','')  
			self.bin_list1.append(x)

		self.bitmap_str = ''.join(map(str,self.bin_list1))
		self.bitmap_list = list(self.bitmap_str)
		return [self.bitmap_list,self.bitmap_str,self.bin_list1]


	#Reduces number of core = difference between two buckets cores
	#Takes binary list and returns new reduced bit map in the form of hex string
	def core_disabler(self,bucket_core_diff,bitmap_list):
		count = 1
		for bit in range(len(bitmap_list)-1, -1, -1):
			if count<=bucket_core_diff:
				if bitmap_list[bit] =='1':
					bitmap_list[bit]='0'
					count=count+1
			else:
				break
		bit_val_str= ''.join(map(str,bitmap_list))
		self.bit_val_new=hex(int(bit_val_str, 2))[2:]
		return self.bit_val_new

	#Compares previous available bit map and reduced core bit map.
	#return list of changed indices and list of changed indices values.
	def get_reduced_core_val(self,bitmap_new, bitmap_old):
		self.non_match_bit_list = []
		self.non_match_indices_list = []
		for i, j in enumerate(bitmap_new):
			if bitmap_old[i] != j:
				self.non_match_indices_list.append(i)
				self.non_match_bit_list.extend(j)
		return[self.non_match_bit_list,self.non_match_indices_list]

	#flip the bit to 1 to 0
	def flip(self,c):
		return '1' if (c == '0') else '0'

	#takes input of binary list ['1000', '0000', '0000', '0000']
	#and returns complemented list
	def printOneComplement_new(self,dis_bit_list):
		comp_list = dis_bit_list
		self.new_comp_list =[]
		for ele in comp_list:
			n = len(ele)
			ones = ""
			# for ones complement flip every bit
			for j in range(n):
				ones += self.flip(ele[j])
			ones = ones.strip("")
			self.new_comp_list.append(ones)
		return self.new_comp_list

	#input binary list =  ['0111', '1111', '1111', '1111']
	#output converted hex list = ['7', 'f', 'f', 'f']
	def binary_to_hex_converter(self,new_comp_list):
		self.non_match_hex_list = []
		for i in new_comp_list:
			s = hex(int(i,2)).lstrip("0x").rstrip("L")
			self.non_match_hex_list.append(s)
		return self.non_match_hex_list

	#
	def get_final_disabled_bitmap(self,hex_list,non_match_indices_list,bitmap_old):
		for bit in range(len(bitmap_old)):
			bitmap_old[bit] = '0'
		for i in range(len(non_match_indices_list)):
			bitmap_old[non_match_indices_list[i]]=hex_list [i]

		self.new_value = "".join(bitmap_old)
		self.new_value = '0x'+self.new_value
		return self.new_value


	def disabled_bitmap_calculator(self,socket_value,bucket_core_diff):
		self.socket_value = socket_value
		self.final_dict =[]
		self.bucket_core_diff = bucket_core_diff
		for soc_val in self.socket_value:
			self.disabled_bitmap_flow(soc_val[2:],self.bucket_core_diff)
			self.final_dict.append(self.new_value)
		return self.final_dict


	def disabled_bitmap_flow(self,bit_val, bucket_core_diff):
		self._tester.test_logger.log("Available bitmask is : {}".format(bit_val))
		self.hex_to_binary_converter(bit_val)
		self.core_count = self.bitmap_list.count('1')
		self.core_disabler(bucket_core_diff,self.bitmap_list)
		self.hex_to_binary_converter(self.bit_val_new)
		self.core_count1 = self.bitmap_list.count('1')
		bitmap_new=list(self.bit_val_new)
		bitmap_old=list(bit_val)
		bitmap_str = "".join(bitmap_new)
		self.get_reduced_core_val(bitmap_new,bitmap_old)
		self.hex_to_binary_converter(self.non_match_bit_list)
		self.printOneComplement_new(self.bin_list1)
		self.binary_to_hex_converter(self.new_comp_list)
		self.get_final_disabled_bitmap(self.non_match_hex_list,self.non_match_indices_list,bitmap_old)
		return self.new_value,self.core_count1,self.core_count


	def collect_output_logs(self, output_lines):
		"""Parse the output lines and copy over any SUT logs to crauto logfiles that are labeled in the output."""
		
		for line in output_lines:
			if "collect_pipm_app_log" in line:
				self.pipm_app_log = line.split('=')[1].replace("['","").replace("']","")
			elif "collect_ptu_log" in line :
				self.ptu_log_file = line.split('=')[1].replace("['","").replace("']","")
			elif "monitor_log" in line :
				self.ptu_log_file1 = line.split('=')[1].replace("['","").replace("']","")

		return self.pipm_app_log , self.ptu_log_file, self.ptu_log_file1

	def all_core_c0_state(self):
		self._tester.test_logger.log("Put all cores in C0 state.")
		self._tester.sut_control.os_access.run_command("cd {}".format(self.pi_pm_app_path))
		self._tester.sut_control.os_access.run_command("cd {}; chmod 777 *".format(self.pi_pm_app_path))
		self._tester.sut_control.os_access.run_command("chmod 777 *".format(self.pi_pm_app_path))
		self._tester.sut_control.os_access.run_command("chmod -R a+rwx {}".format(self.cpuidle_path))
		output = self._tester.sut_control.os_access.run_command("cd {}; ./Activeidle.sh".format(self.pi_pm_app_path))
		return output.result_code


	def gnr_get_sst_pp_level(self):
		try:
			if self._tester.sut_control.sut_os_type in [OS_TYPE.FEDORA.name, OS_TYPE.SLES.name, OS_TYPE.CENTOS.name, OS_TYPE.REDHAT.name, OS_TYPE.CLEARLINUX.name]:
				#need to pass the pmutil o/p(status).
				self._tester._os_access.run_command("cd {};chmod 777 *".format(self.app_pmutil_path))
				cmd = "cd {} && ./pmutil_bin -tR SST_PP_STATUS".format(self.app_pmutil_path)
				self._tester.test_logger.log("Running pmutil command for SST_PP_LEVEL:{}".format(cmd))
				sst_pp_status = self._tester._os_access.run_command(cmd).combined_lines
				#sst_pp_status = ['SOCKET0 TPMI INSTANCE0: 0x8', 'SOCKET0 TPMI INSTANCE1: 0x8', 'SOCKET0 TPMI INSTANCE2: 0x8', 'SOCKET0 TPMI INSTANCE3: 0x8', 'SOCKET0 TPMI INSTANCE4: 0x8']
				#sst_pp_status = ['SOCKET0 PUNIT0: 0x03', 'SOCKET0 PUNIT1: 0x03', 'SOCKET0 PUNIT2: 0x03', 'SOCKET0 PUNIT3: 0x03', 'SOCKET0 PUNIT4: 0x03', '']
				
			
			elif self._tester.sut_control.sut_os_type == OS_TYPE.WINDOWS.name:
				# ss = tpmi.access_tpmi_mailbox('sst','sst_pp_status',instance=1)
				# self._tester.test_logger.log("type of ss {}".format(type(ss)))
				# self._tester.test_logger.log("val of ss {}".format(ss))
				sst_pp_status = int(str(tpmi.access_tpmi_mailbox('sst','sst_pp_status',instance=1)),16)#SSE all core turbo
			
			self._tester.test_logger.log("SST_PP_STATUS from CRAUTO : {}".format(sst_pp_status))
			if int(sst_pp_status[0].split(":")[1],16) <= 7 :
				sst_pp_level = int(sst_pp_status[0].split(":")[1],16)

			else:
				sst_pp_level = int(bin(int(sst_pp_status[0].split(":")[1],16))[3:],2)

		except Exception as e:
			self._tester.test_logger.log("Exception {} has occured while calculating SST_PP_LEVEL,So Assuming SST_PP_LEVEL as 0".format(e))
			sst_pp_level = 0

		self._tester.test_logger.log("SST_PP_LEVEL for Platform is : {}".format(sst_pp_level))
		return sst_pp_level
	
	def gnr_get_pysv_freq(self):
		import graniterapids.pm.tpmi_register as tpmi
		cfg = self.gnr_get_sst_pp_level()
		if cfg == 0:
			varcmd = "'SST_PP_INFO_0'"
			varcmd1 = "'SST_PP_INFO_4'"
			varcmd2 = "'SST_PP_INFO_1'"
			varcmd3 = "'SST_PP_INFO_5'"
			varcmd4 = "'SST_PP_INFO_6'"
			varcmd5 = "'SST_PP_INFO_7'"
			varcmd6 = "'SST_PP_INFO_10'"
		elif cfg in [1,2,3,4]:
			varcmd = "'PP{}_SST_PP_INFO_0'".format(cfg)
			varcmd1 = "'PP{}_SST_PP_INFO_4'".format(cfg)
			varcmd2 = "'PP{}_SST_PP_INFO_1'".format(cfg)
			varcmd3 = "'PP{}_SST_PP_INFO_5'".format(cfg)
			varcmd4 = "'PP{}_SST_PP_INFO_6'".format(cfg)
			varcmd5 = "'PP{}_SST_PP_INFO_7'".format(cfg)
			varcmd6 = "'PP{}_SST_PP_INFO_10'".format(cfg)

		p1_freq_val = str(eval("tpmi.access_tpmi_mailbox('sst',{},instance=1)".format(varcmd)))[2:]
		if len(p1_freq_val) == 7:
			p1_freq_val = '0'+ p1_freq_val
		act_freq_val = str(eval("tpmi.access_tpmi_mailbox('sst',{},instance=1)".format(varcmd1)))[2:]
		avx2_trl =str(eval("tpmi.access_tpmi_mailbox('sst',{},instance=1)".format(varcmd3)))[2:]
		avx512_trl = str(eval("tpmi.access_tpmi_mailbox('sst',{},instance=1)".format(varcmd4)))[2:]
		tmul_trl = str(eval("tpmi.access_tpmi_mailbox('sst',{},instance=1)".format(varcmd5)))[2:]


		self._tester.test_logger.log("P1 trl is : {} ".format(p1_freq_val))
		self._tester.test_logger.log("ACT trl is {} ".format(act_freq_val))
		self._tester.test_logger.log("AVX2 trl is {} ".format(avx2_trl))
		self._tester.test_logger.log("AVX512 trl is {} ".format(avx512_trl))
		self._tester.test_logger.log("TNUL trl is {} ".format(tmul_trl))


		# self._tester.test_logger.log(p1_freq_val)
		# self._tester.test_logger.log(act_freq_val)
		# self._tester.test_logger.log(avx2_trl)
		# self._tester.test_logger.log(avx512_trl)

		if p1_freq_val == '0' or act_freq_val== '0' or avx512_trl=='0' or avx2_trl=='0' :
			self._tester.test_logger.log("Assuming Hard coded Values for frequency as TRL values are Zero")
			self.sse_act_val = 2400
			self.sse_freq_val = 1800
			self.avx2_freq_val = 1600
			self.avx512_freq_val = 1500
			self.sse_bin_bucket0 = 1500
			self.avx2_bin_bucket0 = 1400
			self.avx2_bin_bucket7 = 1300
			self.avx512_bin_bucket0 = 1200
			self.avx512_bin_bucket7 = 1400
			self.tmul_bin_bucket0 = 1800

		else:
			self.sse_act_val = int(act_freq_val[0:2],16)*100
			self.sse_freq_val = int(p1_freq_val[-2:],16)*100
			self.sse_bin_bucket0 = int(act_freq_val[-2:],16)*100
			self.avx2_freq_val = int(p1_freq_val[4:6],16)*100
			self.avx512_freq_val = int(p1_freq_val[2:4],16)*100
			self.avx2_bin_bucket0 = int(avx2_trl[-2:],16)*100
			self.avx2_bin_bucket7 = int(avx2_trl[:-14:1],16)*100
			self.avx512_bin_bucket0 = int(avx512_trl[-2:],16)*100
			self.avx512_bin_bucket7 = int(avx512_trl[:-14:1],16)*100
			self.tmul_bin_bucket0 = int(tmul_trl[-2:],16)*100

		
		'''self.sse_bin_bucket0 = int(act_freq_val[-2:],16)*100
		self.sse_act_val = int(act_freq_val[0:2],16)*100#SSE_bin_bucket7
		self.sse_freq_val = int(p1_freq_val[-2:],16)*100

		self.avx2_bin_bucket0 = int(avx2_trl[-2:],16)*100
		self.avx2_bin_bucket7 = int(avx2_trl[:-14:1],16)*100
		self.avx2_freq_val = int(p1_freq_val[4:6],16)*100

		self.avx512_bin_bucket0 = int(avx512_trl[-2:],16)*100
		self.avx512_bin_bucket7 = int(avx512_trl[:-14:1],16)*100
		self.avx512_freq_val = int(p1_freq_val[2:4],16)*100

		self.tmul_bin_bucket0 = int(tmul_trl[-2:],16)*100'''
		
		
		self._tester.test_logger.log("SSE ACT Frequency is {}".format(self.sse_act_val))
		self._tester.test_logger.log("SSE P1 Frequency is {}".format(self.sse_freq_val))
		self._tester.test_logger.log("AVX2 P1 Frequency is {}".format(self.avx2_freq_val))
		self._tester.test_logger.log("AVX512 P1 Frequency is {}".format(self.avx512_freq_val))
		self._tester.test_logger.log("SSE Bucket0 frequency is {}".format(self.sse_bin_bucket0))
		self._tester.test_logger.log("AVX2 Bucket0 frequency is {}".format(self.avx2_bin_bucket0))
		self._tester.test_logger.log("AVX512 Bucket0 frequency is {}".format(self.avx512_bin_bucket0))
		self._tester.test_logger.log("TMUL Bucket0 frequency is {}".format(self.tmul_bin_bucket0))
		#self._tester.test_logger.log("SSE Bucket7 frequency is {}".format(self.sse_bin_bucket7))
		self._tester.test_logger.log("AVX2 Bucket7 frequency is {}".format(self.avx2_bin_bucket7))
		self._tester.test_logger.log("AVX512 Bucket7 frequency is {}".format(self.avx512_bin_bucket7))
		

	def gnr_get_pmutil_freq(self):
		cfg = self.gnr_get_sst_pp_level()
		if cfg == 0:
			varcmd = "SST_PP_INFO_0"
			varcmd1 = "SST_PP_INFO_4"
			varcmd2 = "SST_PP_INFO_1"
			varcmd3 = "SST_PP_INFO_5"
			varcmd4 = "SST_PP_INFO_6"
			varcmd5 = "SST_PP_INFO_7"
			varcmd6 = "SST_PP_INFO_10"
		elif cfg in [1,2,3,4]:
			varcmd = "PP{}_SST_PP_INFO_0".format(cfg)
			varcmd1 = "PP{}_SST_PP_INFO_4".format(cfg)
			varcmd2 = "PP{}_SST_PP_INFO_1".format(cfg)
			varcmd3 = "PP{}_SST_PP_INFO_5".format(cfg)
			varcmd4 = "PP{}_SST_PP_INFO_6".format(cfg)
			varcmd5 = "PP{}_SST_PP_INFO_7".format(cfg)
			varcmd6 = "PP{}_SST_PP_INFO_10".format(cfg)
	
		self.cmd_val = [varcmd,varcmd1,varcmd2,varcmd3,varcmd4,varcmd5,varcmd6]
		self.cmd_vars = ['pmutil_P1_cmd','pmutil_sse_cmd','pmutil_tdp_cmd','pmutil_avx2_cmd','pmutil_avx512_cmd','pmutil_tmul_cmd', 'pmutil_numcore_cmd']
		#self.freq_vars = ['pmutil_P1_freq','pmutil_act_freq','self.pmutil_tdp_freq','self.pmutil_avx2_freq','self.pmutil_avx512_freq','self.pmutil_tmul_freq']
		
		for var,cmd in zip(self.cmd_vars,self.cmd_val):
			globals()[var] = "cd {} && ./pmutil_bin -tR {}".format(self.app_pmutil_path, cmd)

		self._tester.test_logger.log("Running the pmutil commands for SST PP Level {}.....".format(cfg))

		self.pmutil_P1_freq = self.run_pmutil_cmd(pmutil_P1_cmd)
		self.pmutil_act_freq = self.run_pmutil_cmd(pmutil_sse_cmd)
		self.pmutil_tdp_freq = self.run_pmutil_cmd(pmutil_tdp_cmd)
		self.pmutil_avx2_freq = self.run_pmutil_cmd(pmutil_avx2_cmd)
		self.pmutil_avx512_freq = self.run_pmutil_cmd(pmutil_avx512_cmd)
		self.pmutil_tmul_freq = self.run_pmutil_cmd(pmutil_tmul_cmd)
		self.pmutil_numcore_val = self.run_pmutil_cmd(pmutil_numcore_cmd)

		self._tester.test_logger.log("pmutil output for SSE P1 is : {}".format(self.pmutil_P1_freq))
		self._tester.test_logger.log("pmutil output for SSE TRL is : {}".format(self.pmutil_act_freq))
		self._tester.test_logger.log("pmutil output for AVX2 TRL is : {}".format(self.pmutil_avx2_freq))
		self._tester.test_logger.log("pmutil output for AVX512 TRL is : {}".format(self.pmutil_avx512_freq))
		self._tester.test_logger.log("pmutil output for TMUL TRL is : {}".format(self.pmutil_tmul_freq))
		self._tester.test_logger.log("pmutil output for TDP is : {}".format(self.pmutil_tdp_freq))
		self._tester.test_logger.log("pmutil output for Numcore is : {}".format(self.pmutil_numcore_val))
		
	def run_pmutil_cmd(self,cmd):
		self._tester.test_logger.log("Running pmutil command :{}".format(cmd))
		output_list = self._tester._os_access.run_command(cmd).combined_lines
		time.sleep(10)
		return output_list


	def gnr_pmutil_frequency_calculator(self):
		self.gnr_get_pmutil_freq()
		#pmutil_P1_freq = ['SOCKET0 PUNIT0: 0x18181818', 'SOCKET0 PUNIT1: 0x18181818', 'SOCKET0 PUNIT2: 0x18181818', 'SOCKET0 PUNIT3: 0x18181818', 'SOCKET0 PUNIT4: 0x18181818', '']
		#pmutil_act_freq = ['SOCKET0 PUNIT0: 0x3782dace9d96a4a3', 'SOCKET0 PUNIT1: 0x3782dace9d96a4a3', 'SOCKET0 PUNIT2: 0x3782dace9d96a4a3', 'SOCKET0 PUNIT3: 0x3782dace9d96a4a3', 'SOCKET0 PUNIT4: 0x3782dace9d96a4a3', '']

		'''all ACT scenarios--representaion:
		63 59 55 51 47 43 39 35 31 27 23 19 15 11  7  3
		1  a  1  a  1  b  1  c  1  d  1  e  1  f  2  0
		0  1  2  3  4  5  6  7  8  9 10 11 12 13 14 15'''

		#converting values to MGHZ
		p1_freq_val = self.pmutil_P1_freq[0].split(":")[1][3:] #18181818
		if len(p1_freq_val) == 7:
			p1_freq_val = '0'+ p1_freq_val
		#print("p1 freq is",p1_freq_val)
		act_freq_val = self.pmutil_act_freq[0].split(":")[1][3:] #3782dace9d96a4a3
		#print(act_freq_val)
		tdp_freq_val = self.pmutil_tdp_freq[0].split(":")[1][3:]
		avx2_trl = self.pmutil_avx2_freq[0].split(":")[1][3:]
		avx512_trl = self.pmutil_avx512_freq[0].split(":")[1][3:]
		tmul_trl = self.pmutil_tmul_freq[0].split(":")[1][3:]

		self.sse_bin_bucket0 = int(act_freq_val[-2:],16)*100
		self.sse_act_val = int(act_freq_val[0:2],16)*100
		self.sse_freq_val = int(p1_freq_val[-2:],16)*100

		self.avx2_bin_bucket0 = int(avx2_trl[-2:],16)*100
		self.avx2_bin_bucket7 = int(avx2_trl[:-14:1],16)*100
		self.avx2_freq_val = int(p1_freq_val[4:6],16)*100

		self.avx512_bin_bucket0 = int(avx512_trl[-2:],16)*100
		self.avx512_bin_bucket7 = int(avx512_trl[:-14:1],16)*100
		self.avx512_freq_val = int(p1_freq_val[2:4],16)*100
		
		self.tmul_freq = int(p1_freq_val[0:2],16)*100
		self.tmul_bin_bucket0 = int(tmul_trl[14:],16)*100
		
		self.tdp_val = int(tdp_freq_val[0:2],16)*100
		
		# self.sse_act_val = 3000
		# self.sse_freq_val = 2200
		# self.sse_bin_bucket0 = 2100
		# self.avx2_bin_bucket0 = 2000
		# self.avx2_freq_val = 2300
		
		# self.avx512_bin_bucket0 = 2100
		# self.avx512_freq_val =2300        
		# self.tmul_freq = 1800
		# self.tmul_bin_bucket0 = 2200
		
		# self.tdp_val = 1800

		self._tester.test_logger.log("SSE ACT Frequency is {}".format(self.sse_act_val))
		self._tester.test_logger.log("SSE P1 Frequency is {}".format(self.sse_freq_val))
		self._tester.test_logger.log("AVX2 P1 Frequency is {}".format(self.avx2_freq_val))
		self._tester.test_logger.log("AVX512 P1 Frequency is {}".format(self.avx512_freq_val))
		self._tester.test_logger.log("TMUL Frequency is {}".format(self.tmul_freq))
		self._tester.test_logger.log("TDP Frequency is {}".format(self.tdp_val))
		self._tester.test_logger.log("SSE Bucket0 frequency is {}".format(self.sse_bin_bucket0))
		self._tester.test_logger.log("AVX2 Bucket0 frequency is {}".format(self.avx2_bin_bucket0))
		self._tester.test_logger.log("AVX512 Bucket0 frequency is {}".format(self.avx512_bin_bucket0))
		self._tester.test_logger.log("TMUL Bucket0 frequency is {}".format(self.tmul_bin_bucket0))
		
		self._tester.test_logger.log("SSE Bucket7 frequency is {}".format(self.sse_bin_bucket7))
		self._tester.test_logger.log("AVX2 Bucket7 frequency is {}".format(self.avx2_bin_bucket7))
		self._tester.test_logger.log("AVX512 Bucket7 frequency is {}".format(self.avx512_bin_bucket7))
		
	def spr_pmutil_calculator(self):
		self._tester.test_logger.log("Checking the Base frequency from parts")
		cmd1 = "cd {} && ./pmutil_bin -w 0xB1 -d 0".format(self.app_pmutil_path)
		cmd2 = "cd {} && ./pmutil_bin -w 0xB0 -d 0x80000a7f".format(self.app_pmutil_path)
		cmd3 = "cd {} && ./pmutil_bin -r 0xB1".format(self.app_pmutil_path)

		pmutil_freq_cmds =[cmd1,cmd2,cmd3]
		for cmd in pmutil_freq_cmds:
			os2p_combined_val = self._tester.sut_control.os_access.run_command(cmd).combined_lines

		self._tester.test_logger.log("OS2P_combined_val output is: {}".format(os2p_combined_val))
		if len(os2p_combined_val[0][2:]) == 7 or 8:
			os2p_combined_val = os2p_combined_val[0][2:]
			self._tester.test_logger.log(os2p_combined_val)
			self.avx2_p1 = int(os2p_combined_val[-4:-2],16)*100
			self.avx512_p1 = int(os2p_combined_val[-6:-4],16)*100
			self.sse_p1 = int(os2p_combined_val[-2:],16)*100
			self.tmul_p1 = int(os2p_combined_val[:-6:1],16)*100
			self._tester.test_logger.log("SSE BASE Frequency value from OS2P Mailbox is {}MHZ".format(self.sse_p1))
			self._tester.test_logger.log("TMUL BASE Frequency value from OS2P Mailbox is {}MHZ".format(self.tmul_p1))
			self._tester.test_logger.log("AVX2  BASE Frequency value from OS2P Mailbox is {}MHZ".format(self.avx2_p1))
			self._tester.test_logger.log("AVX512 BASE Frequency value from OS2P Mailbox is {}MHZ".format(self.avx512_p1))
		
		else:
			self._tester.exit_with_error("PMUTIL output for checking Base frequency from Parts is incorrect, Please verify")

		
		return self.sse_p1,self.tmul_p1,self.avx2_p1,self.avx512_p1

	def check_sut_os(self):
		if self._tester.sut_control.sut_os_type == TESTER_ENUMS.OS_TYPE.FEDORA:
			self.operating_system = "FEDORA"
		elif self._tester.sut_control.sut_os_type == TESTER_ENUMS.OS_TYPE.CENTOS:
			self.operating_system = "CENTOS"
		elif self._tester.sut_control.sut_os_type == TESTER_ENUMS.OS_TYPE.CLEARLINUX:
			self.operating_system = "CLEARLINUX"
		elif self._tester.sut_control.sut_os_type == TESTER_ENUMS.OS_TYPE.WINDOWS:
			self.operating_system = "WINDOWS"
		elif self._tester.sut_control.sut_os_type == TESTER_ENUMS.OS_TYPE.REDHAT:
			self.operating_system = "REDHAT"
		else:
			self._tester.exit_with_error("OS string not found")


	def run_pi_pm_pre(self):
		self._tester.test_logger.log("Preparing {t} test. Please wait ...".format(t=self._config.name))
		self._tester.test_logger.log("WL Tool to be used is {t}. Please wait ...".format(t=self.tool))
	
		#self.check_qdfvalue()
		self.check_cpu_type()
		self.check_sut_os()

		self.check_event_logs = self._config.check_event_logs
		if self.check_event_logs:
			if self._tester.sut_control.sut_os_type in [OS_TYPE.FEDORA.name, OS_TYPE.SLES.name, OS_TYPE.CENTOS.name, OS_TYPE.REDHAT.name, OS_TYPE.CLEARLINUX.name]:
				mca_err =[]
				mca_err=self._tester.sut_control.os_access.run_command('dmesg | grep mca').combined_lines
				if mca_err:
					self._tester.sut_control.os_access.run_command('dmesg -C')
				else:
					self._tester.test_logger.log("No dmesg error found for mca errors")
			elif self._tester.sut_control.sut_os_type == OS_TYPE.WINDOWS.name:
				view_event_log = self._tester.sut_control.os_access.run_command("powershell.exe;\"Get-EventLog -LogName System")
				self._tester.test_logger.log("The list of event logs available are : {}".format(view_event_log))
				self._tester.test_logger.log("Clearing the Event logs....")
				self._tester.sut_control.os_access.run_command("powershell.exe;\"Remove-EventLog -LogName System")
				self._tester.sut_control.os_access.run_command("powershell.exe;\"Get-EventLog -LogName System")

		self._tester.test_logger.log("{} test preparations are complete.".format(self._config.name))
			
	def run_pi_pm_main(self):
		self.check_sut_os()
		self.check_turbo_flag = self._config.check_turbo_flag
		#self.run_ptu = self._config.run_ptu
		#self.ptu_ct = self._config.ptu_ct
		self.turbo_enabled = False

		self._tester.test_logger.log("Check Turbo is {}".format(self.check_turbo_flag))
		if self.check_turbo_flag :
			#Read bios_knobs from ITP for TurboMode
			ret_code = self._tester._sut_control.read_bios_knob('TurboMode=0x1')
			self._tester.test_logger.log("Read bios knobs : {}".format(ret_code))   
			if ret_code == 0:
				self._tester.test_logger.log("Found BIOS Knob TurboMode is Enabled")
				self.turbo_enabled = True
			else:
				self._tester.test_logger.log("Found BIOS Knob TurboMode is Disabled")

		if self._config.name == "POWER_PSTATES_IDLE_SOCWATCH_LINUX":
			if self.os_power_policy != None:
				self._tester.test_logger.log("Checking for os_power_policy")
				self.check_os_power_policy()
				time.sleep(60)
		if self.cpu_type in ["GNR","SRF"]:
			self._tester.test_logger.log("Running the test on GNR....")
			
			if self._tester.sut_control.sut_os_type in [OS_TYPE.FEDORA.name, OS_TYPE.SLES.name, OS_TYPE.CENTOS.name, OS_TYPE.REDHAT.name, OS_TYPE.CLEARLINUX.name]:
				self._tester.test_logger.log("**********calculating sse P1 and SSE ACT using pmutil for LINUX Target******************")
				self.gnr_pmutil_frequency_calculator()
			elif self._tester.sut_control.sut_os_type == OS_TYPE.WINDOWS.name:
				self.gnr_get_pysv_freq()
		 
		elif self.cpu_type =="SPR":
			self._tester.test_logger.log("Running the test on SPR....")
			
			#calculating sse P1 and sse act from pysv
			self.frequency_calculator() 
			self._tester.test_logger.log("SSE P1 frequency values from pysv is {}MHZ".format(self.sse_freq_val))
			self._tester.test_logger.log("SSE ACT frequency values from pysv is {}MHZ".format(self.sse_act_val))

		self._tester.test_logger.log("Triggering {}_Testcase. Please wait for sometime to complete test".format(self._config.name))
		if self._tester.sut_control.sut_os_type in [OS_TYPE.FEDORA.name, OS_TYPE.SLES.name, OS_TYPE.CENTOS.name, OS_TYPE.REDHAT.name, OS_TYPE.CLEARLINUX.name]:
			if self.turbo_enabled:
				cmd = "python {dir}/{scr} --test {testname} --os {operatingsystem}  --turbo True --sse_p1_freq {ssep1} --sse_act_freq {ssef}".format(
					dir=self.pi_pm_app_path, 
					scr=self.target_script, 
					testname=self.name,
					operatingsystem=self.operating_system,
					ssep1 = self.sse_freq_val,
					ssef = self.sse_act_val)
			else:
				cmd = "python {dir}/{scr} --test {testname} --os {operatingsystem}  --sse_p1_freq {ssep1} --sse_act_freq {ssef} ".format(
					dir=self.pi_pm_app_path, 
					scr=self.target_script, 
					testname=self.name,
					operatingsystem=self.operating_system, 
					ssep1 = self.sse_freq_val,
					ssef = self.sse_act_val)

			self.result = self._tester.sut_control.os_access.run_command(cmd, verify=False, retry=0)
			self._tester.test_logger.log(str(self.result))

			# output_logfile=self._tester.sut_control.os_access.run_command('cd {} && ls -t | head -n1'.format(self.pi_pm_applog_folder)).combined_lines
			# self.applogfile=output_logfile[0]
			# self.pipm_app_log= "{t}/{appfile}".format(t=self.pi_pm_applog_folder, appfile=self.applogfile)
			# self._tester.test_logger.log("Applog is  :{}".format(self.pipm_app_log))
			self.collect_output_logs(self.result.combined_lines)
			self._tester.test_logger.log("PIPM app log is :{}".format(self.pipm_app_log))
			
			#Log copy to host
			# output_logfile=self._tester.sut_control.os_access.run_command('cd {} && ls -t | head -n1'.format(self.pi_pm_applog_folder)).combined_lines
			# self.applogfile=output_logfile[0]
			# self.pipm_app_log_1= "{t}/{appfile}".format(t=self.pi_pm_applog_folder, appfile=self.applogfile)
			self.test_logs.append(self.pipm_app_log)
			if self._config.name in ['TURBOSTATE_ENABLE_PTU_LINUX','EMR_TURBOSTATE_ENABLE_PTU_LINUX']:
				self._tester.test_logger.log("PTU app log is :{}".format(self.ptu_log_file))
				self.test_logs.append(self.ptu_log_file)

			if self._config.name in ['TURBOSTATE_DISABLE_SOCWATCH_LINUX','TURBOSTATE_ENABLE_SOCWATCH_LINUX','POWER_PSTATES_ALL_SOCWATCH_LINUX','POWER_PSTATES_IDLE_SOCWATCH_LINUX', 'POWER_PSTATES_DECREASED_CORECOUNT_LINUX']:
				self.test_logs.append('{t}/SoCWatchOutput.csv'.format(t=self.pi_pm_applog_folder))
				# ptu_logfile=self._tester.sut_control.os_access.run_command('cd {} && grep -iRl ptu * | tail -n1'.format(self.pi_pm_applog_folder)).combined_lines
				# self.ptufile=ptu_logfile[0]
				# self.pipm_ptu_log= "{t}/{appfile}".format(t=self.pi_pm_applog_folder, appfile=self.ptufile)
				# self.test_logs.append(self.pipm_ptu_log)

			elif self._config.name in ['UFS_SOLAR_LINUX']:
				self.test_logs.append('{}/Generated/SolarLog.csv'.format(self.solar_app_path))
				solar_logfile=self._tester.sut_control.os_access.run_command('cd {} && grep -iRl solar * | tail -n1'.format(self.pi_pm_applog_folder)).combined_lines
				self.solarfile=solar_logfile[0]
				self.pipm_solar_log= "{t}/{appfile}".format(t=self.pi_pm_applog_folder, appfile=self.solarfile)
				self.test_logs.append(self.pipm_solar_log)


		elif self._tester.sut_control.sut_os_type == OS_TYPE.WINDOWS.name:
			# self.pipm_app_log = "{app_logs}/{sut}_applog_{time}.log".format(
			#   app_logs=self.pi_pm_applog_win, 
			#   sut=self._tester.sut_control.hostname, 
			#   time=self._tester._logger.make_ts(file_ts=True))    
			if self.turbo_enabled:
				cmd = "powershell.exe; python {dir}//{scr} --test {testname} --os {operatingsystem} --turbo True --sse_p1_freq {ssep1} --sse_act_freq {ssef} --tool {wl} --cpu {cp}".format(
					dir=self.pi_pm_app_path_win, 
					scr=self.target_script, 
					testname=self.name,
					operatingsystem=self.operating_system,
					ssep1 = self.sse_freq_val, 
					ssef=self.sse_act_val,
					wl = self.tool,
					cp = self.cpu_type)
			else:
				cmd = "powershell.exe; python {dir}//{scr} --test {testname} --os {operatingsystem} --sse_p1_freq {ssep1} --sse_act_freq {ssef} --tool {wl} --cpu {cp}".format(
					dir=self.pi_pm_app_path_win, 
					scr=self.target_script, 
					testname=self.name,
					operatingsystem=self.operating_system,
					ssep1 = self.sse_freq_val, 
					ssef=self.sse_act_val,
					wl=self.tool,
					cp = self.cpu_type)
			self._tester.test_logger.log("triggering command :{}".format(cmd))
			
			self.result = self._tester.sut_control.os_access.run_command(cmd)
			self._tester.test_logger.log(str(self.result))
			
			self.collect_output_logs(self.result.combined_lines)
			self._tester.test_logger.log("PIPM app log is :{}".format(self.pipm_app_log))
			
			if self._config.name in ['TURBOSTATE_DISABLE_SOCWATCH_WINDOWS','TURBOSTATE_ENABLE_SOCWATCH_WINDOWS','POWER_PSTATES_ALL_SOCWATCH_WINDOWS','POWER_PSTATES_IDLE_SOCWATCH_WINDOWS','HWP_NATIVE_WITHOUTLEGACY_SOCWATCH_WINDOWS']:
				self.test_logs.append( os.path.join(self.socwatch_path_win, 'SoCWatchOutput.csv'))
			elif self._config.name in ['UFS_SOLAR_WINDOWS','POWER_HWP_PSTATES_ALL_SOLAR_WINDOWS','POWER_LEGACY_PSTATES_ALL_SOLAR_WINDOWS']:
				self.test_logs.append( os.path.join(self.solar_app_path_win, 'Generated', 'SolarLog.csv'))
			self.test_logs.append(self.pipm_app_log)

	def run_pi_pm_post(self):
		self._tester.test_logger.log("Resuming post test events...")
		if self.check_event_logs:
			if self._tester.sut_control.sut_os_type in [OS_TYPE.FEDORA.name, OS_TYPE.SLES.name, OS_TYPE.CENTOS.name, OS_TYPE.REDHAT.name, OS_TYPE.CLEARLINUX.name]:
				mca_err =[]
				mca_err=self._tester.sut_control.os_access.run_command('dmesg | grep mca').combined_lines
				if mca_err:
					self._tester.sut_control.os_access.run_command('dmesg -C')
				else:
					self._tester.test_logger.log("No dmesg error found for mca errors")

			elif self._tester.sut_control.sut_os_type == OS_TYPE.WINDOWS.name:
				whea_err=[]
				whea_err=self._tester.sut_control.os_access.run_command("powershell.exe;\"Get-EventLog -LogName System -Source WHEA-Logger").combined_lines
				if "No matches found" in str(whea_err):
					self._tester.test_logger.log("No WHEA errors found")
				else:
					self._tester.test_logger.log("WHEA errors found")
		self.copy_pi_pm_logs()
		self.pipm_parse_log(self.pipm_app_log)
		self._tester.test_logger.log("Autolog saved to {}.".format(self._tester._test_logger.auto_log_path))
		self._tester.test_logger.log("Applog saved to {}.".format(self.pipm_app_log))
		
	def copy_pi_pm_logs(self):
		for log in self.test_logs:
			try:
				log = log.strip() 
				dest_file = os.path.join(self._tester._manager.test_case_dir, os.path.basename(log))
				dest_file = dest_file.strip()
				self._tester.test_logger.log("destination log file path is {}".format(repr(dest_file)))
			except Exception as e:
				self._tester.test_logger.log("Exception {} has occured while copying test logs, Logs are not generated properly".format(e))
				self._tester.exit_with_error("FAILED: Test has Failed. Please check the logs for more details")

			if self._tester.sut_control.os_access.sftp_exists(log):
				self._tester.sut_control.os_access.sftp_copy(log, dest_file)
				if dest_file not in self._tester._logger.logfiles: self._tester._logger.add_logfile(dest_file)
			else:
				self._tester.test_logger._record_warning("{} not exists!".format(log))

	def pipm_parse_log(self,pipm_app_log):
		self._tester.test_logger.log("Going to Parse the Applog...")
		self.found_err = False

		for line in self.result.combined_lines:
			if any(Failure_strings in line for Failure_strings in("FAIL : CPU","FAIL : Linpack","FAIL : TDP","FAIL : CPUIDLE","FAIL : Legacy","FAIL : Decreased CoreCount","FAIL : EET_STATE","FAIL : Single Core")):
				self.found_err = True
				self._tester.test_logger.log("CPU Frequency values are not as expected")
				break
		if self.found_err :
			pass
		else:
			self._tester.test_logger.log("Checking if Test case  has passed.....")
			for line in self.result.combined_lines:
				if any(pass_strings in line for pass_strings in ("PASS : CPU","PASS : Linpack","PASS : TDP","PASS : CPUIDLE","PASS : Legacy","PASS : Decreased CoreCount","PASS : EET_STATE","PASS : Single Core")):
					break
			else:
				self.found_err = True
				self._tester.test_logger.log("**********************Multiple Failures are observed in logs*************************")   


		if self.found_err:
			self._tester.exit_with_error("FAILED: Test has Failed. Please check the logs for more details")
		else:
			self._tester.test_logger.log("PASSED: Test has Completed and Passed...")
	
			
	def pipm_parse_log_TTL(self,pipm_app_log):
		self._tester.test_logger.log("Going to Parse the Applog...")
		for line in self.result.combined_lines:
			if "Turbotable : FAIL" in line:
				self.overall_fail_summary.append(line)
			elif "Turbotable : PASS" in line:
				self.overall_pass_summary.append(line)

	def final_parser(self):
		self._tester.test_logger.log("overall_summary for fail turbotable buckets is {}".format(self.overall_fail_summary))
		self._tester.test_logger.log("overall_summary for pass turbotable buckets is {}".format(self.overall_pass_summary))

			
		self.found_err = False  

		if len(self.overall_pass_summary) == 0 and len(self.overall_fail_summary) == 0:
			self.found_err = True
			self._tester.test_logger.log("*********************One or More Turbotable Buckets have Failures*************************")
			self._tester.test_logger.log("**********************Please check logs carefully*************************")

		elif len(self.overall_pass_summary) > 0 and len(self.overall_fail_summary) > 0:
			self.found_err = True
			self._tester.test_logger.log("*********************Few Turbotable buckets have passed and few have failed*************************")
			self._tester.test_logger.log("**********************Please check logs carefully*************************")

		elif len(self.overall_pass_summary) > 0 and len(self.overall_fail_summary) == 0:
			self._tester.test_logger.log("*********************All Executed Turbotable buckets have PASSED*************************")
			self._tester.test_logger.log("**********************Please check logs carefully*************************")
		
		elif len(self.overall_pass_summary) == 0 and len(self.overall_fail_summary) > 0:
			self.found_err = True
			self._tester.test_logger.log("*********************All Executed Turbotable buckets have FAILED*************************")
			self._tester.test_logger.log("**********************Please check logs carefully*************************")

		else:
			self.found_err = True
			self._tester.test_logger.log("********************* Unable to verify Turbotable Buckets status *************************")
			self._tester.test_logger.log("**********************Please check logs carefully*************************")


		if self.found_err:
			self._tester.exit_with_error("FAILED: Turbotable Test has Failed for one or more BUCKETS. Please check the logs for more details")
		else:
			self._tester.test_logger.log("PASSED: Test has Completed and Passed...")


#################################################################################################
#crauto-14429
##################################################################################################

class PI_PM_EMR_TurboState_Enable_PTU_Test_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_EMR_TurboState_Enable_PTU_Test_Linux"}

	def __init__(self):
		super(PI_PM_EMR_TurboState_Enable_PTU_Test_Linux, self).__init__()
		self.name = "EMR_TURBOSTATE_ENABLE_PTU_LINUX" 
		self.targetlogfolder = "PI_PM_EMR_TurboState_Enable_PTU_Test_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "TurboMode=0x1"
		self.check_turbo_flag = True

	def _start(self):
		self.product_class = PI_PM_EMR_TurboState_Enable_PTU_Test_Linux_TestEngine
		return self

class PI_PM_EMR_TurboState_Enable_PTU_Test_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "Collect the frequency of CPU and observe whether it meets the requirements"

###############################################################################################

##################################################################################################

#CRAUTO-11823
##################################################################################################
class PI_PM_TurboState_DisableSocwatch_Test_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_TurboState_DisableSocwatch_Test_Linux"}

	def __init__(self):
		super(PI_PM_TurboState_DisableSocwatch_Test_Linux, self).__init__()
		self.name = "TURBOSTATE_DISABLE_SOCWATCH_LINUX" 
		self.targetlogfolder = "PI_PM_TurboState_DisableSocwatch_Test_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "TurboMode=0x0"
		self.ptu_ct = 3
		self.check_turbo_flag = False

	def _start(self):
		self.product_class = PI_PM_TurboState_DisableSocwatch_Test_Linux_TestEngine
		return self

class PI_PM_TurboState_DisableSocwatch_Test_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "Collect the frequency of CPU and observe whether it meets the requirements"

##################################################################################################

class PI_PM_TurboState_EnableSocwatch_Test_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_TurboState_EnableSocwatch_Test_Linux"}

	def __init__(self):
		super(PI_PM_TurboState_EnableSocwatch_Test_Linux, self).__init__()
		self.name = "TURBOSTATE_ENABLE_SOCWATCH_LINUX" 
		self.targetlogfolder = "PI_PM_TurboState_EnableSocwatch_Test_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "TurboMode=0x1"
		self.ptu_ct = 3
		self.check_turbo_flag = False

	def _start(self):
		self.product_class = PI_PM_TurboState_EnableSocwatch_Test_Linux_TestEngine
		return self

class PI_PM_TurboState_EnableSocwatch_Test_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "Collect the frequency of CPU and observe whether it meets the requirements"
##################################################################################################

class PI_PM_TurboState_Enable_PTU_Test_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_TurboState_Enable_PTU_Test_Linux"}

	def __init__(self):
		super(PI_PM_TurboState_Enable_PTU_Test_Linux, self).__init__()
		self.name = "TURBOSTATE_ENABLE_PTU_LINUX" 
		self.targetlogfolder = "PI_PM_TurboState_Enable_PTU_Test_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "TurboMode=0x1"
		self.check_turbo_flag = True

	def _start(self):
		self.product_class = PI_PM_TurboState_Enable_PTU_Test_Linux_TestEngine
		return self

class PI_PM_TurboState_Enable_PTU_Test_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "Collect the frequency of CPU and observe whether it meets the requirements"

###############################################################################################
class PI_PM_TurboState_DisableSocwatch_Test_Windows(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_TurboState_DisableSocwatch_Test_Windows"}

	def __init__(self):
		super(PI_PM_TurboState_DisableSocwatch_Test_Windows, self).__init__()
		self.name = "TURBOSTATE_DISABLE_SOCWATCH_WINDOWS" 
		self.targetlogfolder = "PI_PM_TurboState_DisableSocwatch_Test_Windows"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.WINDOWS]
		self.suite_membership = [SUITE_TYPE.WINDOWS_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "TurboMode=0x0"
		self.ptu_ct = 3
		self.check_turbo_flag = False

	def _start(self):
		self.product_class = PI_PM_TurboState_DisableSocwatch_Test_Windows_TestEngine
		return self

class PI_PM_TurboState_DisableSocwatch_Test_Windows_TestEngine(PI_PM_TestEngine):
	class_lable = "Collect the frequency of CPU and observe whether it meets the requirements"

###############################################################################################
class PI_PM_TurboState_EnableSocwatch_Test_Windows(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_TurboState_EnableSocwatch_Test_Windows"}

	def __init__(self):
		super(PI_PM_TurboState_EnableSocwatch_Test_Windows, self).__init__()
		self.name = "TURBOSTATE_ENABLE_SOCWATCH_WINDOWS" 
		self.targetlogfolder = "PI_PM_TurboState_EnableSocwatch_Test_Windows"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.WINDOWS]
		self.suite_membership = [SUITE_TYPE.WINDOWS_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "TurboMode=0x1"
		#self.ptu_ct = 3
		self.check_turbo_flag = False

	def _start(self):
		self.product_class = PI_PM_TurboState_EnableSocwatch_Test_Windows_TestEngine
		return self

class PI_PM_TurboState_EnableSocwatch_Test_Windows_TestEngine(PI_PM_TestEngine):
	class_lable = "Collect the frequency of CPU and observe whether it meets the requirements"

#################################################################################################
#CRAUTO-11824
#################################################################################################

class PI_PM_Power_Pstates_All_SoCwatch_Test_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_Power_Pstates_All_SoCwatch_Test_Linux"}

	def __init__(self):
		super(PI_PM_Power_Pstates_All_SoCwatch_Test_Linux, self).__init__()
		self.name = "POWER_PSTATES_ALL_SOCWATCH_LINUX" 
		self.targetlogfolder = "PI_PM_Power_Pstates_All_SoCwatch_Test_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "ProcessorEistEnable=0x1,TurboMode=0x1"
		self.check_turbo_flag = True
		self.ptu_ct = 1

	def _start(self):
		self.product_class = PI_PM_Power_Pstates_All_SoCwatch_Test_Linux_TestEngine
		return self

class PI_PM_Power_Pstates_All_SoCwatch_Test_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "Collect the frequency of CPU and observe whether it meets the requirements"

###############################################################################################

class PI_PM_Power_Pstates_All_SoCwatch_Test_Windows(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_Power_Pstates_All_SoCwatch_Test_Windows"}

	def __init__(self):
		super(PI_PM_Power_Pstates_All_SoCwatch_Test_Windows, self).__init__()
		self.name = "POWER_PSTATES_ALL_SOCWATCH_WINDOWS" 
		self.targetlogfolder = "PI_PM_Power_Pstates_All_SoCwatch_Test_Windows"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.WINDOWS]
		self.suite_membership = [SUITE_TYPE.WINDOWS_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "ProcessorEistEnable=0x1,TurboMode=0x1"
		self.check_turbo_flag = True
		#self.ptu_ct = 1

	def _start(self):
		self.product_class = PI_PM_Power_Pstates_All_SoCwatch_Test_Windows_TestEngine
		return self

class PI_PM_Power_Pstates_All_SoCwatch_Test_Windows_TestEngine(PI_PM_TestEngine):
	class_lable = "Collect the frequency of CPU and observe whether it meets the requirements"

##################################################################################################

class PI_PM_Power_Pmin_Idle_SoCwatch_Test_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_Power_Pmin_Idle_SoCwatch_Test_Linux"}

	def __init__(self):
		super(PI_PM_Power_Pmin_Idle_SoCwatch_Test_Linux, self).__init__()
		self.name = "POWER_PSTATES_IDLE_SOCWATCH_LINUX" 
		self.targetlogfolder = "PI_PM_Power_Pmin_Idle_SoCwatch_Test_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "ProcessorEistEnable=0x1, C6Enable=0x1, MonitorMWait=0x1"
		self.run_ptu = False
		self.check_turbo_flag = False

	def _start(self):
		self.product_class = PI_PM_Power_Pmin_Idle_SoCwatch_Test_Linux_TestEngine
		return self

class PI_PM_Power_Pmin_Idle_SoCwatch_Test_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "Collect the frequency of CPU and observe whether it meets the requirements"

###############################################################################################

class PI_PM_Power_Pmin_Idle_SoCwatch_Test_Windows(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_Power_Pmin_Idle_SoCwatch_Test_Windows"}

	def __init__(self):
		super(PI_PM_Power_Pmin_Idle_SoCwatch_Test_Windows, self).__init__()
		self.name = "POWER_PSTATES_IDLE_SOCWATCH_WINDOWS" 
		self.targetlogfolder = "PI_PM_Power_Pmin_Idle_SoCwatch_Test_Windows"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.WINDOWS]
		self.suite_membership = [SUITE_TYPE.WINDOWS_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "ProcessorEistEnable=0x1, C6Enable=0x1, MonitorMWait=0x1"
		self.run_ptu = False
		self.check_turbo_flag = False

	def _start(self):
		self.product_class = PI_PM_Power_Pmin_Idle_SoCwatch_Test_Windows_TestEngine
		return self

class PI_PM_Power_Pmin_Idle_SoCwatch_Test_Windows_TestEngine(PI_PM_TestEngine):
	class_lable = "Collect the frequency of CPU and observe whether it meets the requirements"

################################################################################################
class PI_PM_UFS_Solar_Test_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_UFS_Solar_Test_Linux"}

	def __init__(self):
		super(PI_PM_UFS_Solar_Test_Linux, self).__init__()
		self.name = "UFS_SOLAR_LINUX" 
		self.targetlogfolder = "PI_PM_UFS_Solar_Test_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.run_ptu = False
		self.check_turbo_flag = False
		self.check_event_logs = True

	def _start(self):
		self.product_class = PI_PM_UFS_Solar_Test_Linux_TestEngine
		return self

class PI_PM_UFS_Solar_Test_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "To cover the functional test of UFS feature on Linux"

###################################################################################################
class PI_PM_UFS_Solar_Test_Windows(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_UFS_Solar_Test_Windows"}

	def __init__(self):
		super(PI_PM_UFS_Solar_Test_Windows, self).__init__()
		self.name = "UFS_SOLAR_WINDOWS" 
		self.targetlogfolder = "PI_PM_UFS_Solar_Test_Windows"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.WINDOWS]
		self.suite_membership = [SUITE_TYPE.WINDOWS_SAT, SUITE_TYPE.UNDEFINED]
		self.run_ptu = False
		self.check_turbo_flag = False
		self.check_event_logs = True

	def _start(self):
		self.product_class = PI_PM_UFS_Solar_Test_Windows_TestEngine
		return self

class PI_PM_UFS_Solar_Test_Windows_TestEngine(PI_PM_TestEngine):
	class_lable = "To cover the functional test of UFS feature on Windows"

################################################################################################

class PI_PM_Legacy_Pstate_All_Solar_Test_Windows(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_Legacy_Pstate_All_Solar_Test_Windows"}

	def __init__(self):
		super(PI_PM_Legacy_Pstate_All_Solar_Test_Windows, self).__init__()
		self.name = "POWER_LEGACY_PSTATES_ALL_SOLAR_WINDOWS" 
		self.targetlogfolder = "PI_PM_Legacy_Pstate_All_Solar_Test_Windows"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.WINDOWS]
		self.suite_membership = [SUITE_TYPE.WINDOWS_SAT, SUITE_TYPE.UNDEFINED]
		self.run_ptu = False
		self.check_turbo_flag = False
		self.check_event_logs = True
		self.bios_knobs = "ProcessorHWPMEnable=0x0"


	def _start(self):
		self.product_class = PI_PM_Legacy_Pstate_All_Solar_Test_Windows_TestEngine
		return self

class PI_PM_Legacy_Pstate_All_Solar_Test_Windows_TestEngine(PI_PM_TestEngine):
	class_lable = "To cover the functional test of UFS feature on Windows"


#################################################################################################

class PI_PM_HWP_Pstate_All_Solar_Test_Windows(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_HWP_Pstate_All_Solar_Test_Windows"}

	def __init__(self):
		super(PI_PM_HWP_Pstate_All_Solar_Test_Windows, self).__init__()
		self.name = "POWER_HWP_PSTATES_ALL_SOLAR_WINDOWS" 
		self.targetlogfolder = "PI_PM_HWP_Pstate_All_Solar_Test_Windows"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.WINDOWS]
		self.suite_membership = [SUITE_TYPE.WINDOWS_SAT, SUITE_TYPE.UNDEFINED]
		self.run_ptu = False
		self.check_turbo_flag = False
		self.check_event_logs = True
		self.bios_knobs = "ProcessorHWPMEnable=0x1"

	def _start(self):
		self.product_class = PI_PM_HWP_Pstate_All_Solar_Test_Windows_TestEngine
		return self

class PI_PM_HWP_Pstate_All_Solar_Test_Windows_TestEngine(PI_PM_TestEngine):
	class_lable = "To cover the functional test of UFS feature on Windows"

##########################################################################################################################################################################################################

class PI_PM_TurboState_Disable_PTU_Test_Windows(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_TurboState_Disable_PTU_Test_Windows"}

	def __init__(self):
		super(PI_PM_TurboState_Disable_PTU_Test_Windows, self).__init__()
		self.name = "TURBOSTATE_DISABLE_PTU_WINDOWS" 
		self.targetlogfolder = "PI_PM_TurboState_Disable_PTU_Test_Windows"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.WINDOWS]
		self.suite_membership = [SUITE_TYPE.WINDOWS_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "TurboMode=0x0"
		#self.ptu_ct = 3
		self.check_turbo_flag = False

	def _start(self):
		self.product_class = PI_PM_TurboState_Disable_PTU_Test_Windows_TestEngine
		return self

class PI_PM_TurboState_Disable_PTU_Test_Windows_TestEngine(PI_PM_TestEngine):
	class_lable = "Collect the frequency of CPU and observe whether it meets the requirements"

##################################################################################################


class PI_PM_DecreasedCoreCount_SSE_Test_Windows(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_TurboBoost_DecreasedCoreCount_Test_Windows"}

	def __init__(self):
		super(PI_PM_DecreasedCoreCount_SSE_Test_Windows, self).__init__()
		self.name = "TURBOBOOST_DECREASED_CORECOUNT_SSE_WINDOWS" 
		self.targetlogfolder = "PI_PM_DecreasedCoreCount_SSE_Test_Windows"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.WINDOWS]
		self.suite_membership = [SUITE_TYPE.WINDOWS_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "TurboMode=0x1" 
		self.run_ptu = False
		self.check_turbo_flag = False
		self.bios_knob_set = False
		self.test_step = 1
	
	def _start(self):
		self.product_class = PI_PM_TurboBoost_DecreasedCoreCount_Test_Windows_TestEngine
		return self

###################################################################################################

class PI_PM_DecreasedCoreCount_AVX2_Test_Windows(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_DecreasedCoreCount_AVX2_Test_Windows"}

	def __init__(self):
		super(PI_PM_DecreasedCoreCount_AVX2_Test_Windows, self).__init__()
		self.name = "TURBOBOOST_DECREASED_CORECOUNT_AVX2_WINDOWS" 
		self.targetlogfolder = "PI_PM_DecreasedCoreCount_AVX2_Test_Windows"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.WINDOWS]
		self.suite_membership = [SUITE_TYPE.WINDOWS_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "TurboMode=0x1" 
		self.run_ptu = False
		self.check_turbo_flag = False
		self.bios_knob_set = False
		self.test_step = 2

	def _start(self):
		self.product_class = PI_PM_TurboBoost_DecreasedCoreCount_Test_Windows_TestEngine
		return self

###################################################################################################

class PI_PM_DecreasedCoreCount_AVX512_Test_Windows(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_DecreasedCoreCount_AVX512_Test_Windows"}

	def __init__(self):
		super(PI_PM_DecreasedCoreCount_AVX512_Test_Windows, self).__init__()
		self.name = "TURBOBOOST_DECREASED_CORECOUNT_AVX512_WINDOWS" 
		self.targetlogfolder = "PI_PM_DecreasedCoreCount_AVX512_Test_Windows"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.WINDOWS]
		self.suite_membership = [SUITE_TYPE.WINDOWS_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "TurboMode=0x1" 
		self.run_ptu = False
		self.check_turbo_flag = False
		self.bios_knob_set = False
		self.test_step = 3
	
	def _start(self):
		self.product_class = PI_PM_TurboBoost_DecreasedCoreCount_Test_Windows_TestEngine
		return self

###################################################################################################

class PI_PM_TurboBoost_DecreasedCoreCount_Test_Windows(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_TurboBoost_DecreasedCoreCount_Test_Windows"}

	def __init__(self):
		super(PI_PM_TurboBoost_DecreasedCoreCount_Test_Windows, self).__init__()
		self.name = "TURBOBOOST_DECREASED_CORECOUNT_WINDOWS" 
		self.targetlogfolder = "PI_PM_TurboBoost_DecreasedCoreCount_Test_Windows"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.WINDOWS]
		self.suite_membership = [SUITE_TYPE.WINDOWS_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "TurboMode=0x1" 
		self.run_ptu = False
		self.check_turbo_flag = False
		self.bios_knob_set = False
		self.test_step = 0
	
	def _start(self):
		self.product_class = PI_PM_TurboBoost_DecreasedCoreCount_Test_Windows_TestEngine
		return self

###################################################################################################

class PI_PM_TurboBoost_DecreasedCoreCount_Test_Windows_TestEngine(PI_PM_TestEngine):
	class_lable = "Collect the frequency of CPU and observe whether it meets the requirements"
	
	def run_pi_pm_main(self):
		self.test_step = self._config.test_step
		self._tester.test_logger.log("*********************************Test step is {} : Running {} Test******************************".format(self._config.test_step,self.name))
	
		self._tester.test_logger.log("Setting Power Scheme to 'Balanced' on the target via Control Panel")
		self._tester.sut_control.os_access.run_command("powercfg /setactive 381b4222-f694-41f0-9685-ff5bb260df2e")
		output=self._tester.sut_control.os_access.run_command("powercfg /list")
		self._tester.test_logger.log("Active* Power Scheme is : {}".format(output))
		self.get_available_bitmap()
		self.init_corecount=True
		self.bitmask_decreasedcore_calculation(self.socket_value,self.init_corecount)
		self._tester.test_logger.log("Final bitmask per socket is {}".format(self.final_dict))
		
		self.socket_count = int(self._frame.sv_control.socket_count)
		self._tester.test_logger.log("Current Socket Count is : {}".format(self.socket_count))
		if self.socket_count == 2:
			self.socket0_knobvalue=self.final_dict[0]
			self.socket1_knobvalue=self.final_dict[1]
			self.knob ='CoreDisableMask_0={} , CoreDisableMask_1={}'.format(self.socket0_knobvalue,self.socket1_knobvalue)
		elif self.socket_count == 4:
			self.socket0_knobvalue=self.final_dict[0]
			self.socket1_knobvalue=self.final_dict[1]
			self.socket2_knobvalue=self.final_dict[2]
			self.socket3_knobvalue=self.final_dict[3]
			self.knob ='CoreDisableMask_0={} , CoreDisableMask_1={}, CoreDisableMask_2={} , CoreDisableMask_3={}'.format(self.socket0_knobvalue,self.socket1_knobvalue, self.socket2_knobvalue, self.socket3_knobvalue)
		self._tester.test_logger.log("Bios knob to set : {}".format(self.knob))
		self._tester.sut_control.set_bios_knob(self.knob)
		self._tester.tester_functions.ac_power_cycle()
		self.bios_knob_set=True

		self.get_disable_bitmap()
		self.init_corecount=False
		self.bitmask_decreasedcore_calculation(self.socket_value,self.init_corecount)
		if self.decremented_core_count == int(self.initial_core_count - 1):
			self._tester.test_logger.log("Successfully decreased the core count using BitMap")
		else:
			self._tester.exit_with_error("FAIL: The decreased core count didnt match")

		if self.cpu_type == "SPR":
			self.frequency_calculator()
			self._tester.test_logger.log(" frequency values from _sv_sockets are SSE P1 {}MHZ, AVX2 P1 {}MHZ and AVX512 P1 {}MHZ".format(self.sse_freq_val,self.avx2_freq_val,self.avx512_freq_val))
			self._tester.test_logger.log(" frequency values from _sv_sockets are SSE ACT {}MHZ, AVX2 ACT {}MHZ and AVX512 ACT {}MHZ".format(self.sse_act_val,self.avx2_bin_bucket7,self.avx512_bin_bucket7))
		
		elif self.cpu_type in ["GNR","SRF"]:
			self.gnr_get_pysv_freq()

		cmd = "powershell.exe; python {dir}//{scr} --test {testname} --os {operatingsystem}  --sse_p1_freq {ssep1} --sse_act_freq {ssef} --avx2_freq {af2} --avx512_freq {af512} --test_step {tp} --cpu {cp} --tool {wl}".format(
			dir=self.pi_pm_app_path_win, 
			scr=self.target_script, 
			testname=self.name,
			operatingsystem=self.operating_system,
			ssep1 = self.sse_freq_val,
			ssef = self.sse_act_val,
			af2 = self.avx2_freq_val,
			af512 = self.avx512_freq_val,
			tp = self.test_step,
			cp = self.cpu_type,
			wl = self.tool)

		self._tester.test_logger.log(" Triggering the standalone command {}".format(cmd))
	
		self.result = self._tester.sut_control.os_access.run_command(cmd, verify=False, retry=0)
		self._tester.test_logger.log("Completed Test....")
		self._tester.test_logger.log(str(self.result))

		self.collect_output_logs(self.result.combined_lines)
		self._tester.test_logger.log("PIPM app log is :{}".format(self.pipm_app_log))
		
		self.test_logs.append(self.pipm_app_log)
		self.test_logs.append( os.path.join(self.socwatch_path_win, 'SoCWatchOutput.csv'))

		if self.bios_knob_set:
			self._tester.test_logger.log("Reverting BitMap Bios Knobs to default.") 
			self._tester.sut_control.reset_bios_knob()
			self._tester.tester_functions.ac_power_cycle()

		
################################################################################################

class PI_PM_TurboBoost_SingleCoreCount_Test_Windows(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_TurboBoost_SingleCoreCount_Test_Windows"}

	def __init__(self):
		super(PI_PM_TurboBoost_SingleCoreCount_Test_Windows, self).__init__()
		self.name = "TURBOBOOST_SINGLE_CORECOUNT_WINDOWS" 
		self.targetlogfolder = "PI_PM_TurboBoost_SingleCoreCount_Test_Windows"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.WINDOWS]
		self.suite_membership = [SUITE_TYPE.WINDOWS_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "TurboMode=0x1" 
		self.run_ptu = False
		self.check_turbo_flag = False
		self.bios_knob_set = False
		self.test_step = 0

	def _start(self):
		self.product_class = PI_PM_TurboBoost_SingleCoreCount_Test_Windows_TestEngine
		return self

###############################################################################################

class PI_PM_TurboBoost_SingleCoreCount_SSE_Test_Windows(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_TurboBoost_SingleCoreCount_SSE_Test_Windows"}

	def __init__(self):
		super(PI_PM_TurboBoost_SingleCoreCount_SSE_Test_Windows, self).__init__()
		self.name = "TURBOBOOST_SINGLE_CORECOUNT_SSE_WINDOWS" 
		self.targetlogfolder = "PI_PM_TurboBoost_SingleCoreCount_SSE_Test_Windows"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.WINDOWS]
		self.suite_membership = [SUITE_TYPE.WINDOWS_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "TurboMode=0x1" 
		self.run_ptu = False
		self.check_turbo_flag = False
		self.bios_knob_set = False
		self.test_step = 1

	def _start(self):
		self.product_class = PI_PM_TurboBoost_SingleCoreCount_Test_Windows_TestEngine
		return self

#################################################################
class PI_PM_TurboBoost_SingleCoreCount_AVX2_Test_Windows(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_TurboBoost_SingleCoreCount_AVX2_Test_Windows"}

	def __init__(self):
		super(PI_PM_TurboBoost_SingleCoreCount_AVX2_Test_Windows, self).__init__()
		self.name = "TURBOBOOST_SINGLE_CORECOUNT_AVX2_WINDOWS" 
		self.targetlogfolder = "PI_PM_TurboBoost_SingleCoreCount_AVX2_Test_Windows"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.WINDOWS]
		self.suite_membership = [SUITE_TYPE.WINDOWS_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "TurboMode=0x1" 
		self.run_ptu = False
		self.check_turbo_flag = False
		self.bios_knob_set = False
		self.test_step = 2

	def _start(self):
		self.product_class = PI_PM_TurboBoost_SingleCoreCount_Test_Windows_TestEngine
		return self
#######################################################################
class PI_PM_TurboBoost_SingleCoreCount_AVX512_Test_Windows(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_TurboBoost_SingleCoreCount_AVX512_Test_Windows"}

	def __init__(self):
		super(PI_PM_TurboBoost_SingleCoreCount_AVX512_Test_Windows, self).__init__()
		self.name = "TURBOBOOST_SINGLE_CORECOUNT_AVX512_WINDOWS" 
		self.targetlogfolder = "PI_PM_TurboBoost_SingleCoreCount_AVX512_Test_Windows"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.WINDOWS]
		self.suite_membership = [SUITE_TYPE.WINDOWS_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "TurboMode=0x1" 
		self.run_ptu = False
		self.check_turbo_flag = False
		self.bios_knob_set = False
		self.test_step = 3

	def _start(self):
		self.product_class = PI_PM_TurboBoost_SingleCoreCount_Test_Windows_TestEngine
		return self

############################################################################

class PI_PM_TurboBoost_SingleCoreCount_Test_Windows_TestEngine(PI_PM_TestEngine):
	class_lable = "Collect the frequency of CPU and observe whether it meets the requirements"

	def run_pi_pm_main(self):
		self.test_step = self._config.test_step
		self._tester.test_logger.log("*********************************Test step is {} : Running {} Test******************************".format(self._config.test_step,self.name))
		self._tester.test_logger.log("Setting Power Scheme to 'Balanced' on the target via Control Panel")
		self._tester.sut_control.os_access.run_command("powercfg /setactive 381b4222-f694-41f0-9685-ff5bb260df2e")
		output=self._tester.sut_control.os_access.run_command("powercfg /list")
		self._tester.test_logger.log("Active* Power Scheme is : {}".format(output))
		self.get_available_bitmap()
		self.init_corecount=True
		self.bitmask_singlecore_calculation(self.socket_value,self.init_corecount)
		self._tester.test_logger.log("Final bitmask per socket is {}".format(self.final_dict))
		
		self.socket_count = int(self._frame.sv_control.socket_count)
		self._tester.test_logger.log("Current Socket Count is : {}".format(self.socket_count))
		
		if self.socket_count == 2:
			self.socket0_knobvalue=self.final_dict[0]
			self.socket1_knobvalue=self.final_dict[1]
			self.knob ='CoreDisableMask_0={} , CoreDisableMask_1={}'.format(self.socket0_knobvalue,self.socket1_knobvalue)
		elif self.socket_count == 4:
			self.socket0_knobvalue=self.final_dict[0]
			self.socket1_knobvalue=self.final_dict[1]
			self.socket2_knobvalue=self.final_dict[2]
			self.socket3_knobvalue=self.final_dict[3]
			self.knob ='CoreDisableMask_0={} , CoreDisableMask_1={}, CoreDisableMask_2={} , CoreDisableMask_3={}'.format(self.socket0_knobvalue,self.socket1_knobvalue, self.socket2_knobvalue, self.socket3_knobvalue)
		self._tester.test_logger.log("Bios knob to set : {}".format(self.knob))
		self._tester.sut_control.set_bios_knob(self.knob)
		self._tester.tester_functions.ac_power_cycle()
		self.bios_knob_set=True
		self.get_disable_bitmap()
		self.init_corecount=False
		self.bitmask_singlecore_calculation(self.socket_value,self.init_corecount)
		if self.decremented_core_count == 1:
			self._tester.test_logger.log("Successfully with single core count using BitMap")
		else:
			self._tester.exit_with_error("FAIL: The single core count didnt match")

		#calculating sse P1 and sse act from pysv

		if self.cpu_type in ["GNR","SRF"]:
			self._tester.test_logger.log("Running the test on GNR....")
			self.gnr_get_pysv_freq()

		elif self.cpu_type =="SPR":
			self._tester.test_logger.log("Running the test on SPR....")
			self.frequency_calculator() 
			self._tester.test_logger.log("Frequency values are as follow : SSE bin Bucket0 :{}MHZ , AVX2 bin Bucket0 :{}MHZ, AVX512 bin Bucket0 :{}MHZ, TMUL bin bucket0 : {}MHZ from _sv_sockets".format(self.sse_bin_bucket0,self.avx2_bin_bucket0,self.avx512_bin_bucket0,self.tmul_bin_bucket0))
		

		#start standalone script
		self._tester.test_logger.log("Triggering {}_Testcase. Please wait for sometime to complete test".format(self._config.name))
		cmd = "powershell.exe; python {dir}//{scr} --test {testname} --os {operatingsystem}  --sse_bucket0_freq {ssef} --avx2_bucket0_freq {af2} --avx512_bucket0_freq {af512} --tmul_bucket0_freq {tmulf} --test_step {tp} --cpu {cp} --tool {wl}".format(
			dir=self.pi_pm_app_path_win,
			scr=self.target_script,
			testname=self.name,
			operatingsystem=self.operating_system,
			ssef = self.sse_bin_bucket0,
			af2=self.avx2_bin_bucket0,
			af512 = self.avx512_bin_bucket0,
			tmulf = self.tmul_bin_bucket0,
			tp = self.test_step,
			cp = self.cpu_type,
			wl = self.tool)
		self.result = self._tester.sut_control.os_access.run_command(cmd, verify=False, retry=0)
		self._tester.test_logger.log("Completed running the standalone.....")
		self._tester.test_logger.log(str(self.result))


		self.collect_output_logs(self.result.combined_lines)
		self._tester.test_logger.log("PIPM app log is :{}".format(self.pipm_app_log))
			

		self.test_logs.append(self.pipm_app_log)
		self.test_logs.append( os.path.join(self.socwatch_path_win, 'SoCWatchOutput.csv'))

		if self.bios_knob_set:
			self._tester.test_logger.log("Reverting BitMap Bios Knobs to default.") 
			self._tester.sut_control.reset_bios_knob()
			self._tester.tester_functions.ac_power_cycle()


################################################################################################
#CRAUTO-9244
class PI_PM_HWP_Disabled_SoCwatch_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_HWP_Disabled_SoCwatch_Linux"}

	def __init__(self):
		super(PI_PM_HWP_Disabled_SoCwatch_Linux, self).__init__()
		self.name = "HWP_DISABLED_SOCWATCH_LINUX" 
		self.targetlogfolder = "PI_PM_HWP_Disabled_SoCwatch_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "ProcessorHWPMEnable=0x0,TurboMode=0x1" 
		self.run_ptu = False
		self.check_turbo_flag = True
		self.bios_knob_set = False
	
	def _start(self):
		self.product_class = PI_PM_HWP_Disabled_SoCwatch_Linux_TestEngine
		return self

class PI_PM_HWP_Disabled_SoCwatch_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "Collect the frequency of CPU and observe whether it meets the requirements"
	
	def run_pi_pm_main(self):
		self.check_turbo_flag = self._config.check_turbo_flag
		self.turbo_enabled = False
		if self.check_turbo_flag :
			#Read bios_knobs from ITP for TurboMode
			ret_code = self._tester._sut_control.read_bios_knob('TurboMode=0x1')
			self._tester.test_logger.log("Read bios knobs : {}".format(ret_code))   
			if ret_code == 0:
				self._tester.test_logger.log("Found BIOS Knob TurboMode is Enabled")
				self.turbo_enabled = True
			else:
				self._tester.test_logger.log("Found BIOS Knob TurboMode is Disabled")

		if self.cpu_type =="SPR":
			self.msr_tools_installation()
			self.frequency_calculator()# calculating sse P1 and sse act from pysv
			self._tester.test_logger.log("SSE P1 and SSE ACT frequency values from _sv_sockets are {}MHZ and {}MHZ".format(self.sse_freq_val,self.sse_act_val))
		elif self.cpu_type in ["GNR","SRF"]:
			self.gnr_pmutil_frequency_calculator()  # changing values to MGHZ

		val = self.check_dmesg_HWP()
		if val:
			self._tester.test_logger.continue_with_warning("HWP Should be disabled while running HWP disabled Testcase, please check bios knobs")
	
		self.register_val="0x1AA"
		rdmsr_data = self.check_rdmsr_value(self.register_val)
		self.sixth_elm, self.eighth_elm = self.msr_power_mgmt(rdmsr_data)
		if self.sixth_elm == 0 and self.eighth_elm == 0:
			self._tester.test_logger.log("rdmsr bit[6].ENABLE_HWP = 0 and bit[8].ENABLE_OUT_OF_BAND_AUTONOMOUS = 0. Criteria is PASSED.")
		else:
			self._tester.exit_with_error("rdmsr bit[6].ENABLE_HWP and bit[8].ENABLE_OUT_OF_BAND_AUTONOMOUS are non zero. Criteria is FAILED.")

		#Trigger Standalone test
		self._tester.test_logger.log("Triggering {}_Testcase. Please wait for sometime to complete test".format(self._config.name))
		if self.turbo_enabled:
			cmd = "python {dir}/{scr} --test {testname} --os {operatingsystem}  --turbo True --sse_p1_freq {ssep1} --sse_act_freq {ssef} --cpu {ct}".format(
				dir=self.pi_pm_app_path, 
				scr=self.target_script, 
				testname=self.name,
				operatingsystem=self.operating_system,
				ssep1 = self.sse_freq_val, 
				ssef=self.sse_act_val,
				ct = self.cpu_type)
		else:
			cmd = "python {dir}/{scr} --test {testname} --os {operatingsystem} --sse_p1_freq {ssep1} --sse_act_freq {ssef}".format(
				dir=self.pi_pm_app_path, 
				scr=self.target_script, 
				testname=self.name,
				operatingsystem=self.operating_system,
				ssep1 = self.sse_freq_val, 
				ssef=self.sse_act_val,
				ct = self.cpu_type)
		self.result = self._tester.sut_control.os_access.run_command(cmd, verify=False, retry=0)
		self._tester.test_logger.log(str(self.result))
	
		#Log copy to host
		self.collect_output_logs(self.result.combined_lines)
		self._tester.test_logger.log("PIPM app log is:{}".format(self.pipm_app_log))
		self.test_logs.append(self.pipm_app_log)
		self.test_logs.append('{t}/SoCWatchOutput.csv'.format(t=self.pi_pm_applog_folder))
		# ptu_logfile=self._tester.sut_control.os_access.run_command('cd {} && grep -iRl ptu * | tail -n1'.format(self.pi_pm_applog_folder)).combined_lines
		# self.ptufile=ptu_logfile[0]
		# self.pipm_ptu_log= "{t}/{appfile}".format(t=self.pi_pm_applog_folder, appfile=self.ptufile)
		# self.test_logs.append(self.pipm_ptu_log)


################################################################################################
#CRAUTO-9248
class PI_PM_HWP_Native_Enabled_SoCwatch_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_HWP_Native_Enabled_SoCwatch_Linux"}

	def __init__(self):
		super(PI_PM_HWP_Native_Enabled_SoCwatch_Linux, self).__init__()
		self.name = "HWP_NATIVE_ENABLED_SOCWATCH_LINUX" 
		self.targetlogfolder = "PI_PM_HWP_Native_Enabled_SoCwatch_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "ProcessorHWPMEnable=0x1,TurboMode=0x1" 
		self.run_ptu = False
		self.check_turbo_flag = True
		self.bios_knob_set = False

	
	def _start(self):
		self.product_class = PI_PM_HWP_Native_Enabled_SoCwatch_Linux_TestEngine
		return self

class PI_PM_HWP_Native_Enabled_SoCwatch_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "Collect the frequency of CPU and observe whether it meets the requirements"
	
	def run_pi_pm_main(self):
		self.check_turbo_flag = self._config.check_turbo_flag
		self.turbo_enabled = False
		
		if self.check_turbo_flag:
			ret_code = self._tester._sut_control.read_bios_knob('TurboMode=0x1') # Read bios_knobs from ITP for TurboMode
			self._tester.test_logger.log("Value of ret_code {}".format(ret_code))
			self._tester.test_logger.log("Read bios knobs : {}".format(ret_code))
			if ret_code == 0:
				self._tester.test_logger.log("Found BIOS Knob TurboMode is Enabled")
				self.turbo_enabled = True
			else:
				self._tester.test_logger.log("Found BIOS Knob TurboMode is Disabled")
		
		if self.cpu_type =="SPR":
			self.msr_tools_installation()
			self.frequency_calculator()# calculating sse P1 and sse act from pysv
			self._tester.test_logger.log("SSE P1 and SSE ACT frequency values from _sv_sockets are {}MHZ and {}MHZ".format(self.sse_freq_val,self.sse_act_val))
		elif self.cpu_type in ["GNR","SRF"]:
			self.gnr_pmutil_frequency_calculator()  # changing values to MGHZ
			
		self.check_dmesg_HWP()
		
		self.register_val = "0x1AA"
		rdmsr_data = self.check_rdmsr_value(self.register_val)
		self.sixth_elm, self.eighth_elm = self.msr_power_mgmt(rdmsr_data)
		self._tester.test_logger.log("sixth elm : {} ,eighth elm : {}".format(self.sixth_elm, self.eighth_elm))
		if self.sixth_elm == 1 and self.eighth_elm == 0:
			self._tester.test_logger.log("rdmsr bit[6].ENABLE_HWP = 1 and bit[8].ENABLE_OUT_OF_BAND_AUTONOMOUS = 0. Criteria is PASSED.")
		else:
			self._tester.exit_with_error("rdmsr bit[6].ENABLE_HWP = 0 and bit[8].ENABLE_OUT_OF_BAND_AUTONOMOUS = 1. Criteria is FAILED.")

		self.register_val = "0x770"
		rdmsr_data = self.check_rdmsr_value(self.register_val)
		if int(rdmsr_data[0]) == 1:
			self._tester.test_logger.log("rdmsr bit[0]-[MSR IA32_PM_ENABLE bit[0] is HWP_ENABLE. Criteria is PASSED.")
		else:
			self._tester.exit_with_error("rdmsr bit[0]-[MSR IA32_PM_ENABLE bit[0] is not HWP_ENABLE. Criteria is FAILED.")
		
		self.register_val = "0x771"
		rdmsr_data = self.check_rdmsr_value(self.register_val)
		self.check_Pbit_value(rdmsr_data)
		self.check_sut_os()
		# Trigger Standalone test
		self._tester.test_logger.log("Triggering {}_Testcase. Please wait for sometime to complete test".format(self._config.name))
		if self.turbo_enabled:
			cmd = "python {dir}/{scr} --test {testname} --os {operatingsystem}  --turbo True --cpu {cpu} --sse_p1_freq {ssep1} --sse_act_freq {ssef}".format(
				dir=self.pi_pm_app_path,
				scr=self.target_script,
				testname=self.name,
				operatingsystem=self.operating_system,
				ssep1=self.sse_freq_val,
				ssef=self.sse_act_val,
				cpu = self.cpu_type)
		else:
			cmd = "python {dir}/{scr} --test {testname} --os {operatingsystem}  --cpu {cpu} --sse_p1_freq {ssep1} --sse_act_freq {ssef}".format(
				dir=self.pi_pm_app_path,
				scr=self.target_script,
				testname=self.name,
				operatingsystem=self.operating_system,
				ssep1=self.sse_freq_val,
				ssef=self.sse_act_val,
				cpu = self.cpu_type)
		self.result = self._tester.sut_control.os_access.run_command(cmd, verify=False, retry=0)
		self._tester.test_logger.log(str(self.result))
		#Log copy to host
		self.collect_output_logs(self.result.combined_lines)
		self._tester.test_logger.log("PIPM app log is:{}".format(self.pipm_app_log))
		self.test_logs.append(self.pipm_app_log)
		self.test_logs.append('{t}/SoCWatchOutput.csv'.format(t=self.pi_pm_applog_folder))
		# ptu_logfile=self._tester.sut_control.os_access.run_command('cd {} && ls -t | grep ptu_ct3 | head -n1'.format(self.pi_pm_applog_folder)).combined_lines
		# self.ptufile=ptu_logfile[0]
		# self.pipm_ptu_log= "{t}/{appfile}".format(t=self.pi_pm_applog_folder, appfile=self.ptufile)
		# self.test_logs.append(self.pipm_ptu_log)


################################################################################################
#CRAUTO-9247
class PI_PM_HWP_Native_Mode_Without_Legacy_SoCwatch_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_HWP_Native_Mode_Without_Legacy_SoCwatch_Linux"}

	def __init__(self):
		super(PI_PM_HWP_Native_Mode_Without_Legacy_SoCwatch_Linux, self).__init__()
		self.name = "HWP_NATIVE_WITHOUTLEGACY_SOCWATCH_LINUX" 
		self.targetlogfolder = "PI_PM_HWP_Native_Mode_Without_Legacy_SoCwatch_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "ProcessorHWPMEnable=0x3,TurboMode=0x1" 
		self.run_ptu = False
		self.check_turbo_flag = True
		self.bios_knob_set = False
	
	def _start(self):
		self.product_class = PI_PM_HWP_Native_Mode_Without_Legacy_SoCwatch_Linux_TestEngine
		return self

class PI_PM_HWP_Native_Mode_Without_Legacy_SoCwatch_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "Collect the frequency of CPU and observe whether it meets the requirements"
	
	def run_pi_pm_main(self):
		self.check_turbo_flag = self._config.check_turbo_flag
		self.turbo_enabled = False
		
		if self.check_turbo_flag:
			self._tester.test_logger.log("In check turbo flag")
			ret_code = self._tester._sut_control.read_bios_knob('TurboMode=0x1') # Read bios_knobs from ITP for TurboMode
			self._tester.test_logger.log("Value of ret_code {}".format(ret_code))
			self._tester.test_logger.log("Read bios knobs : {}".format(ret_code))
			if ret_code == 0:
				self._tester.test_logger.log("Found BIOS Knob TurboMode is Enabled")
				self.turbo_enabled = True
			else:
				self._tester.test_logger.log("Found BIOS Knob TurboMode is Disabled")
		
		if self.cpu_type =="SPR":
			self.msr_tools_installation()
			self.frequency_calculator()# calculating sse P1 and sse act from pysv
			self._tester.test_logger.log("SSE P1 and SSE ACT frequency values from _sv_sockets are {}MHZ and {}MHZ".format(self.sse_freq_val,self.sse_act_val))
		elif self.cpu_type in ["GNR","SRF"]:
			self.gnr_pmutil_frequency_calculator()  # changing values to MGHZ
			
		self.check_dmesg_HWP()

		self.register_val = "0x1AA"
		rdmsr_data = self.check_rdmsr_value(self.register_val)
		self.sixth_elm, self.eighth_elm = self.msr_power_mgmt(rdmsr_data)
		self._tester.test_logger.log("sixth elm : {} ,eighth elm : {}".format(self.sixth_elm, self.eighth_elm))
		if self.sixth_elm == 1 and self.eighth_elm == 0:
			self._tester.test_logger.log("rdmsr bit[6].ENABLE_HWP = 1 and bit[8].ENABLE_OUT_OF_BAND_AUTONOMOUS = 0. Criteria is PASSED.")
		else:
			self._tester.exit_with_error("rdmsr bit[6].ENABLE_HWP = 0 and bit[8].ENABLE_OUT_OF_BAND_AUTONOMOUS = 1. Criteria is FAILED.")

		self.register_val = "0x770"
		rdmsr_data = self.check_rdmsr_value(self.register_val)
		if int(rdmsr_data[0]) == 1:
			self._tester.test_logger.log("rdmsr bit[0]-[MSR IA32_PM_ENABLE bit[0] is HWP_ENABLE. Criteria is PASSED.")
		else:
			self._tester.exit_with_error("rdmsr bit[0]-[MSR IA32_PM_ENABLE bit[0] is not HWP_ENABLE. Criteria is FAILED.")

		self.register_val = "0x771"
		rdmsr_data = self.check_rdmsr_value(self.register_val)
		self.check_Pbit_value(rdmsr_data)
		
		self.check_sut_os()
		# Trigger Standalone test
		self._tester.test_logger.log("Triggering {}_Testcase. Please wait for sometime to complete test".format(self._config.name))
		if self.turbo_enabled:
			cmd = "python {dir}/{scr} --test {testname} --os {operatingsystem}  --turbo True --cpu {cpu} --sse_p1_freq {ssep1} --sse_act_freq {ssef}".format(
				dir=self.pi_pm_app_path,
				scr=self.target_script,
				testname=self.name,
				operatingsystem=self.operating_system,
				ssep1=self.sse_freq_val,
				ssef=self.sse_act_val,
				cpu = self.cpu_type)
		else:
			cmd = "python {dir}/{scr} --test {testname} --os {operatingsystem}  --cpu {cpu} --sse_p1_freq {ssep1} --sse_act_freq {ssef}".format(
				dir=self.pi_pm_app_path,
				scr=self.target_script,
				testname=self.name,
				operatingsystem=self.operating_system,
				ssep1=self.sse_freq_val,
				ssef=self.sse_act_val,
				cpu = self.cpu_type)
		self.result = self._tester.sut_control.os_access.run_command(cmd, verify=False, retry=0)
		self._tester.test_logger.log(str(self.result))

		#Log copy to host
		self.collect_output_logs(self.result.combined_lines)
		self._tester.test_logger.log("PIPM app log is:{}".format(self.pipm_app_log))
		self.test_logs.append(self.pipm_app_log)
		self.test_logs.append('{t}/SoCWatchOutput.csv'.format(t=self.pi_pm_applog_folder))
		# ptu_logfile=self._tester.sut_control.os_access.run_command('cd {} && ls -t | grep ptu_ct3 | head -n1'.format(self.pi_pm_applog_folder)).combined_lines
		# self.ptufile=ptu_logfile[0]
		# self.pipm_ptu_log= "{t}/{appfile}".format(t=self.pi_pm_applog_folder, appfile=self.ptufile)
		# self.test_logs.append(self.pipm_ptu_log)

###############################################################################################
#CRAUTO-9245
class PI_PM_HWP_Native_Mode_Without_Legacy_SoCwatch_Windows(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_HWP_Native_Mode_Without_Legacy_SoCwatch_Windows"}

	def __init__(self):
		super(PI_PM_HWP_Native_Mode_Without_Legacy_SoCwatch_Windows, self).__init__()
		self.name = "HWP_NATIVE_WITHOUTLEGACY_SOCWATCH_WINDOWS" 
		self.targetlogfolder = "PI_PM_HWP_Native_Mode_Without_Legacy_SoCwatch_Windows"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.WINDOWS]
		self.suite_membership = [SUITE_TYPE.WINDOWS_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "ProcessorHWPMEnable=0x3,TurboMode=0x1"
		self.run_ptu = False
		self.check_turbo_flag = True
		self.bios_knob_set=False

	def _start(self):
		self.product_class = PI_PM_HWP_Native_Mode_Without_Legacy_SoCwatch_Windows_TestEngine
		return self

class PI_PM_HWP_Native_Mode_Without_Legacy_SoCwatch_Windows_TestEngine(PI_PM_TestEngine):
	class_lable = "Collect the frequency of CPU and observe whether it meets the requirements"

################################################################################################
#CRAUTO-9246
class PI_PM_HWP_OOB_Mode_SoCwatch_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_HWP_OOB_Mode_SoCwatch_Linux"}

	def __init__(self):
		super(PI_PM_HWP_OOB_Mode_SoCwatch_Linux, self).__init__()
		self.name = "HWP_OOB_MODE_SOCWATCH_LINUX" 
		self.targetlogfolder = "PI_PM_HWP_OOB_Mode_SoCwatch_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "ProcessorHWPMEnable=0x2,TurboMode=0x1" 
		self.run_ptu = False
		self.check_turbo_flag = True
		self.bios_knob_set = False
	
	def _start(self):
		self.product_class = PI_PM_HWP_OOB_Mode_SoCwatch_Linux_TestEngine
		return self

class PI_PM_HWP_OOB_Mode_SoCwatch_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "Collect the frequency of CPU and observe whether it meets the requirements"
	
	def run_pi_pm_main(self):
		_sv_sockets = self._tester.sv_control.sv_sockets        
		self.msr_tools_installation()       
		self.register_val="0x1AA"
		self.rdmsr_data = self.check_rdmsr_value(self.register_val)
		self.sixth_elm, self.eighth_elm = self.msr_power_mgmt(self.rdmsr_data)
		if self.sixth_elm == 0 and self.eighth_elm == 1:
			self._tester.test_logger.log("rdmsr bit[6].ENABLE_HWP = 0 and bit[8].ENABLE_OUT_OF_BAND_AUTONOMOUS = 1. Criteria is PASSED.")
		else:
			self._tester.exit_with_error("rdmsr bit[6].ENABLE_HWP and bit[8].ENABLE_OUT_OF_BAND_AUTONOMOUS are not 0 and 1 respectively. Criteria is FAILED.")

		#Add check for PECI and hwp_capabilities
		self.output = self._tester.sut_control.bmc_access.run_command("peci_cmds rdpkgconfig 53 0", verify=True).combined_lines
		self._tester.test_logger.log("The peci_cmds output is {}".format(self.output))
		self.peci_val = self.output[0][13:]
		self.peci_decimal_val = int(self.peci_val, 16)
		self._tester.test_logger.log("The decimal output of peci_cmds is {}".format(self.peci_decimal_val))

		for socket in _sv_sockets:
			P01_val = socket.uncore.punit.hwp_capabilities.read()
			self._tester.test_logger.log("The hwp_capabilities value is {}".format(P01_val))

		P01_matching_value = str(P01_val)[2:]
		self.decimal_P01_val = int(P01_matching_value, 16)
		self._tester.test_logger.log("The hwp_capabilities decimal value is {}".format(self.decimal_P01_val))
		#Compare the peci and P01_matching value.
		if self.peci_decimal_val == self.decimal_P01_val:
			self._tester.test_logger.log("The peci_cmds and hwp_capabilities matched successfully.")
		else:
			self.continue_with_warning("ERROR: The peci_cmds and hwp_capabilities is not matching.")
		#calculating sse P1 and sse act from pysv
		self.frequency_calculator() 
		self._tester.test_logger.log("SSE P1 and SSE ACT frequency values from _sv_sockets are {}MHZ and {}MHZ".format(self.sse_freq_val,self.sse_act_val))
		self.check_sut_os()
		#Trigger Standalone test
		self._tester.test_logger.log("Triggering {}_Testcase. Please wait for sometime to complete test".format(self._config.name))
		cmd = "python {dir}/{scr} --test {testname} --os {operatingsystem}  --test_step 1 --sse_p1_freq {ssep1} --sse_act_freq {ssef} --tool {wl}".format(
		dir=self.pi_pm_app_path, 
		scr=self.target_script, 
		testname=self.name,
		operatingsystem=self.operating_system,
		ssep1 = self.sse_freq_val,
		ssef = self.sse_act_val,
		wl = self.tool)
		self.result = self._tester.sut_control.os_access.run_command(cmd, verify=False, retry=0)
		self._tester.test_logger.log(str(self.result))
	
		#Log copy to host
		self.collect_output_logs(self.result.combined_lines)
		self._tester.test_logger.log("PIPM app log is:{}".format(self.pipm_app_log))
		self.test_logs.append(self.pipm_app_log)
		self.test_logs.append('{t}/SoCWatchOutput.csv'.format(t=self.pi_pm_applog_folder))
		self.copy_pi_pm_logs()
		self.pipm_parse_log(self.pipm_app_log)
		
		#Setting the Pstate limitation to 2GHz
		self.output2 = self._tester.sut_control.bmc_access.run_command("peci_cmds wrpkgconfig 53 0x1 0x1400", verify=True)
		self._tester.test_logger.log("The peci_cmds output for setting the range to 2GHz is {}".format(self.output2))

		#Trigger Standalone test
		self._tester.test_logger.log("Triggering {}_Testcase. Please wait for sometime to complete test".format(self._config.name))
		cmd = "python {dir}/{scr} --test {testname} --os {operatingsystem}  --test_step 2".format(dir=self.pi_pm_app_path, scr=self.target_script, testname=self.name,operatingsystem=self.operating_system)
		self.result = self._tester.sut_control.os_access.run_command(cmd, verify=False, retry=0)
		self._tester.test_logger.log(str(self.result))


################################################################################################
#CRAUTO-9246
class PI_PM_HWP_OOB_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_HWP_OOB_Linux"}

	def __init__(self):
		super(PI_PM_HWP_OOB_Linux, self).__init__()
		self.name = "HWP_OOB_LINUX" 
		self.targetlogfolder = "PI_PM_HWP_OOB_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "ProcessorHWPMEnable=0x2,TurboMode=0x1" 
		self.run_ptu = False
		self.check_turbo_flag = True
		self.bios_knob_set = False
	
	def _start(self):
		self.product_class = PI_PM_HWP_OOB_Linux_TestEngine
		return self

class PI_PM_HWP_OOB_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "Collect the frequency of CPU and observe whether it meets the requirements"
	
	def run_pi_pm_main(self):
		self.register_val="0x1AA"
		rdmsr_data = self.check_rdmsr_value(self.register_val)
		self.sixth_elm, self.eighth_elm = self.msr_power_mgmt(rdmsr_data)
		if self.sixth_elm == 0 and self.eighth_elm == 1:
			self._tester.test_logger.log("bit[6].ENABLE_HWP = 0 and bit[8].ENABLE_OUT_OF_BAND_AUTONOMOUS = 1. Criteria is PASSED.")
		else:
			self._tester.test_logger.log("bit[6].ENABLE_HWP and bit[8].ENABLE_OUT_OF_BAND_AUTONOMOUS are not 0 and 1 respectively. Criteria is FAILED.")

		#Add check for PECI and hwp_capabilities
		self.output = self._tester.sut_control.bmc_access.run_command("peci_cmds rdpkgconfig 53 0", verify=True).combined_lines
		self._tester.test_logger.log("The peci_cmds output is {}".format(self.output))
		peci_list = []
		peci_list.append(self.output[0][11:])#['0x40c1223']#
		P01_bit,P1_bit,Pn_bit = self.check_Pbit_value(peci_list)
		
		self.register_val = "0x771"
		rdmsr_data = self.check_rdmsr_value(self.register_val)#['0x40c1223']#s
		P01_output,P1_output,Pn_output= self.check_Pbit_value(rdmsr_data)
		
		if P01_bit == P01_output:
			self._tester.test_logger.log("P01 values from rdmsr bit matched with PECI commands.Criteria is PASSED")
		else:
			self._tester.test_logger.log("P01_Bit:rdmsr val {} P01_output:PECI val {}".format(P01_bit,P01_output))
			self._tester.test_logger.log("P01 values from rdmsr bit didnt matched with PECI commands.Criteria is FAILED")

		if P1_bit == P1_output:
			self._tester.test_logger.log("P1 values from rdmsr bit matched with PECI commands.Criteria is PASSED")
		else:
			self._tester.test_logger.log("P1_Bit:rdmsr val {} P01_output:PECI Val {}".format(P1_bit,P1_output))
			self._tester.test_logger.log("P1 values from rdmsr bit didnt matched with PECI commands.Criteria is FAILED")

		if Pn_bit == Pn_output:
			self._tester.test_logger.log("Pn values from rdmsr bit matched with PECI commands.Criteria is PASSED")
		else:
			self._tester.test_logger.log("Pn_Bit:rdmsr val {} Pn_output:PECI val {}".format(Pn_bit,Pn_output))
			self._tester.test_logger.log("Pn values from rdmsr bit didnt matched with PECI commands.Criteria is FAILED")
		self._tester.test_logger.log("Verification is completed")

		self.gnr_pmutil_frequency_calculator()
		
		#Trigger Standalone test
		self._tester.test_logger.log("Triggering {}_Testcase. Please wait for sometime to complete test".format(self._config.name))
		cmd = "python {dir}/{scr} --test {testname} --os {operatingsystem}  --test_step 1 --sse_p1_freq {ssep1} --sse_act_freq {ssef} --cpu {ct}".format(
		dir=self.pi_pm_app_path, 
		scr=self.target_script, 
		testname=self.name,
		operatingsystem=self.operating_system,
		ssep1 = self.sse_freq_val,
		ssef = self.sse_act_val,
		ct = self.cpu_type)
		self.result = self._tester.sut_control.os_access.run_command(cmd, verify=False, retry=0)
		self._tester.test_logger.log(str(self.result))
	
		#Log copy to host
		self.collect_output_logs(self.result.combined_lines)
		self._tester.test_logger.log("PIPM app log is:{}".format(self.pipm_app_log))
		self.test_logs.append(self.pipm_app_log)
		self.test_logs.append('{t}/SoCWatchOutput.csv'.format(t=self.pi_pm_applog_folder))
		self.copy_pi_pm_logs()
		self.pipm_parse_log(self.pipm_app_log)
		
		#Setting the Pstate limitation 
		self._tester.test_logger.log("Limit Max frequency [15:8] = 0x10 = 1600 MHz and min frequency [7:0] = 0x0a = 1000 MHz.")
		self.output = self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x30 WrPkgConfig 53 0x1 0x100a", verify=True)
		self._tester.test_logger.log("The peci_cmds output for setting the range for CPU 0 is {}".format(self.output2))
		
		self.output = self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x31 WrPkgConfig 53 0x1 0x100a", verify=True)
		self._tester.test_logger.log("The peci_cmds output for setting the range for CPU 1 is {}".format(self.output2))

		#Trigger Standalone test
		self._tester.test_logger.log("Triggering {}_Testcase. Please wait for sometime to complete test".format(self._config.name))
		cmd = "python {dir}/{scr} --test {testname} --os {operatingsystem}  --test_step 2 --cpu {ct}".format(
			dir=self.pi_pm_app_path, 
			scr=self.target_script, 
			testname=self.name,
			operatingsystem=self.operating_system,
			ct = self.cpu_type)
		self.result = self._tester.sut_control.os_access.run_command(cmd, verify=False, retry=0)
		self._tester.test_logger.log(str(self.result))


		#Log copy to host
		self.collect_output_logs(self.result.combined_lines)
		self._tester.test_logger.log("PIPM app log is:{}".format(self.pipm_app_log))
		self.test_logs.append(self.pipm_app_log)
		self.test_logs.append('{t}/SoCWatchOutput.csv'.format(t=self.pi_pm_applog_folder))
		self.copy_pi_pm_logs()
		self.pipm_parse_log(self.pipm_app_log)
		
		#Setting the Peci back to Original Value
		self.output2 = self._tester.sut_control.bmc_access.run_command("peci_cmds wrpkgconfig 53 1 PECI_PSTATE", verify=True)
		self._tester.test_logger.log("The peci_cmds output for setting the value back to Original is {}".format(self.output2))



################################################################################################
# CRAUTO-15606
class PI_PM_Psys_Modify_PPL1_Peci_Verify_Power_Capping_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_Psys_ModifyPPL1_PECI_Verify_Power_Capping_Linux"}

	def __init__(self):
		super(PI_PM_Psys_Modify_PPL1_Peci_Verify_Power_Capping_Linux, self).__init__()
		self.name = "PSYS_MODIFY_PPL1_PECI_VERIFY_POWER_CAPPING_LINUX" 
		self.targetlogfolder = "PI_PM_Psys_Modify_PPL1_Peci_Verify_Power_Capping_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "PsysPowerLimitCsrLock=0x0,PsysPowerInfoLock=0x0,PsysPowerLimitAndInfo=0x1,PsysPowerDomain=0x1"
		self.run_ptu = True
		self.check_turbo_flag = False
		self.bios_knob_set = True
		self.min_range = 776
		self.max_range = 824

	def _start(self):
		self.product_class = PI_PM_Psys_Modify_PPL1_Peci_Verify_Power_Capping_Linux_TestEngine
		return self

class PI_PM_Psys_Modify_PPL1_Peci_Verify_Power_Capping_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "Collect the Power Platform Energy Status loop and observe whether it meets the expected range"
	
	def run_pi_pm_main(self):
		self.min_range = 776
		self.max_range = 824
		self._tester.test_logger.log("Running Psys_Modify_PPL1_Peci_Verify_Power_Capping_Linux")
		self._tester.test_logger.log("Setting the PPL1 via peci in bmc")
		self.socket_count = int(self._frame.sv_control.socket_count)
		if self.socket_count == 2:
			self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x30 wrpkgconfig 58 0 0x02661900", verify=True)
			self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x31 wrpkgconfig 58 0 0x02661900", verify=True)
		elif self.socket_count == 4:
			self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x32 wrpkgconfig 58 0 0x02661900", verify=True)
			self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x33 wrpkgconfig 58 0 0x02661900", verify=True)


		self._tester.test_logger.log("PECI Commands triggered successfully")
		
		self.wl_thread = thread_with_trace(target=self.run_ptu_workload, args=("ct3",), name="ptu") 
					
		self.wl_thread.start()
		time.sleep(30)
		if self._tester.manager.cpu_project == CPU_PROJECT.SPR:
			self.power_plt_energy_status_thread = thread_with_trace(target=self.plt_energy_status_diff, args=(800,3))
		
		elif self._tester.manager.cpu_project == CPU_PROJECT.GNR:
			self.power_plt_energy_status_thread = thread_with_trace(target=self.run_power_plt_energy_status)

		self.power_plt_energy_status_thread.start()
		time.sleep(120)
		self.power_plt_energy_status_thread.kill()  
		self.wl_thread.kill()
		time.sleep(10)
		self.stop_ptu()
		self._tester.test_logger.log("Completed PTU WL and Power_Platform_Energy_Status_Loop dump.. Going for Log parsing")
		self.test_logs.append(self.psys_log_file)

		self._tester.test_logger.log("The execution Psys_Modify_PPL1_Peci_Verify_Power_Capping_Linux is completed!")

		self._tester.test_logger.log("Resetting the PPL1 to Original value")
		if self.socket_count == 2:
			self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x30 wrpkgconfig 58 0 0x02663080", verify=True)
			self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x31 wrpkgconfig 58 0 0x02663080", verify=True)
		elif self.socket_count == 4:
			self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x30 wrpkgconfig 58 0 0x02663080", verify=True)
			self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x31 wrpkgconfig 58 0 0x02663080", verify=True)
			self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x32 wrpkgconfig 58 0 0x02663080", verify=True)
			self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x33 wrpkgconfig 58 0 0x02663080", verify=True)


		if self._tester.manager.cpu_project == CPU_PROJECT.GNR:
			status = self.parse_psys_power_dump(self.psys_log_file, self.min_range, self.max_range)

			if status:
				self._tester.exit_with_error("FAIL : Power_Platform_Energy_Status value not matching with the expected range. Please check the above logs for details")
			else:
				self._tester.test_logger.log("PASS : Power_Platform_Energy_Status value matched with the expected range.")  
	
	def run_pi_pm_post(self):
		pass

		
################################################################################################
# CRAUTO-15606
class PI_PM_Psys_Modify_PPL2_Peci_Verify_Power_Capping_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_Psys_Modify_PPL2_Peci_Verify_Power_Capping_Linux"}

	def __init__(self):
		super(PI_PM_Psys_Modify_PPL2_Peci_Verify_Power_Capping_Linux, self).__init__()
		self.name = "PSYS_MODIFY_PPL2_PECI_VERIFY_POWER_CAPPING_LINUX" 
		self.targetlogfolder = "PI_PM_Psys_Modify_PPL2_Peci_Verify_Power_Capping_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "PsysPowerLimitCsrLock=0x0,PsysPowerInfoLock=0x0,PsysPowerLimitAndInfo=0x1,PsysPowerDomain=0x1"
		self.run_ptu = True
		self.check_turbo_flag = False
		self.bios_knob_set = True
		self.min_range = 582
		self.max_range = 618

	def _start(self):
		self.product_class = PI_PM_Psys_Modify_PPL2_Peci_Verify_Power_Capping_Linux_TestEngine
		return self

class PI_PM_Psys_Modify_PPL2_Peci_Verify_Power_Capping_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "Collect the Power Platform Energy Status loop and observe whether it meets the expected range"
	
	def run_pi_pm_main(self):
		self._tester.test_logger.log("Running Psys_Modify_PPL2_Peci_Verify_Power_Capping_Linux")
		self._tester.test_logger.log("Setting the PPL2 via peci in bmc")
		self.min_range = 582
		self.max_range = 618
		self.socket_count = int(self._frame.sv_control.socket_count)
		if self.socket_count == 2:
			self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x30 wrpkgconfig 59 0 0x026612C0", verify=True)
			self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x31 wrpkgconfig 59 0 0x026612C0", verify=True)
		elif self.socket_count == 4:
			self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x32 wrpkgconfig 59 0 0x026612C0", verify=True)
			self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x33 wrpkgconfig 59 0 0x026612C0", verify=True)

		self._tester.test_logger.log("PECI Commands triggered successfully")
		
		self.wl_thread = thread_with_trace(target=self.run_ptu_workload, args=("ct3",), name="ptu")         
		self.wl_thread.start()
		time.sleep(30)
		self.power_plt_energy_status_thread = thread_with_trace(target=self.plt_energy_status_diff, args=(600,3))
		self.power_plt_energy_status_thread.start()
		time.sleep(180)
		self.power_plt_energy_status_thread.kill()
		self.wl_thread.kill()
		time.sleep(10)
		self.stop_ptu()
		self._tester.test_logger.log("Completed PTU WL and Power_Platform_Energy_Status_Loop dump.. Going for Log parsing")
		self.test_logs.append(self.psys_log_file)

		self._tester.test_logger.log("Resetting the PPL2 to Original value")
		if self.socket_count == 2:
			self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x30 wrpkgconfig 59 0 0x02663A30", verify=True)
			self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x31 wrpkgconfig 59 0 0x02663A30", verify=True)
		elif self.socket_count == 4:
			self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x32 wrpkgconfig 59 0 0x02663A30", verify=True)
			self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x33 wrpkgconfig 59 0 0x02663A30", verify=True)

			   
		status = self.parse_psys_power_dump(self.psys_log_file, self.min_range, self.max_range)

		if status:
			self._tester.exit_with_error("FAIL : Power_Platform_Energy_Status value not matching with the expected range. Please check the above logs for details")
		else:
			self._tester.test_logger.log("PASS : Power_Platform_Energy_Status value matched with the expected range.")
	
	def run_pi_pm_post(self):
		pass
		
######################################################################################################
# CRAUTO-15743
class PI_PM_Psys_Modify_PPL1_via_PECI_Verify_Power_Capping_2S_Linux(PI_PM_Testcase):
	_default = {"_config_name": "Psys_Modify_PPL1_via_PECI_Verify_Power_Capping_2S_Linux"}

	def __init__(self): 
		super(PI_PM_Psys_Modify_PPL1_via_PECI_Verify_Power_Capping_2S_Linux, self).__init__()
		self.name = "Psys_Modify_PPL1_via_PECI_Verify_Power_Capping_2S_Linux" 
		self.targetlogfolder = "Psys_Modify_PPL1_via_PECI_Verify_Power_Capping_2S_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "PsysPowerLimitCsrLock=0x0,PsysPowerInfoLock=0x0,PsysPowerLimitAndInfo=0x1,PsysPowerDomain=0x1"
		self.run_ptu = True
		self.check_turbo_flag = False
		self.bios_knob_set = True
		self.min_range = 582
		self.max_range = 618

	def _start(self):
		self.product_class = PI_PM_Psys_Modify_PPL1_via_PECI_Verify_Power_Capping_2S_Linux_TestEngine
		return self

class PI_PM_Psys_Modify_PPL1_via_PECI_Verify_Power_Capping_2S_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "Verify Power Capping correctly limits platform power consumption"
	
	def run_pi_pm_main(self):
		_sv_sockets = self._tester.sv_control.sv_sockets
		self.socket_count = int(self._frame.sv_control.socket_count)
		self._tester.test_logger.log("Running Psys_Modify_PPL1via_PMUtil_Verify_Power_Capping_Linux")

		#for ppl1 part
		self._tester.test_logger.log("Running PTU WL for Test")
		self.wl_thread = thread_with_trace(target=self.run_ptu_workload, args=("ct3",), name="ptu") 
		self.wl_thread.start()
		time.sleep(30)
		self.plt_power_status_value = self.run_platform_power_consumption()
		self.reduced_platform_power=int(self.plt_power_status_value*0.7)   # reduce plat power by 30%
		self.reduced_platform_power_hex=hex(self.reduced_platform_power)
		digit_to_extract=self.reduced_platform_power_hex[2:]
		last_val="0x0266"+ digit_to_extract
		self.peci_cmds_soc0 = "peci_cmds -a 0x30 wrpkgconfig 58 0 "+last_val
		self.peci_cmds_soc1 = "peci_cmds -a 0x31 wrpkgconfig 58 1 "+last_val

		self.set_and_check_peci_cmds(self.peci_cmds_soc0,self.peci_cmds_soc1)

		self.plt_power_status_value_1 = self.run_platform_power_consumption()

		#now compare and check if plt_power value is +/- 3% of reduced_platform power

		lower_val= self.reduced_platform_power - int((self.reduced_platform_power*3)/100)
		upper_val= self.reduced_platform_power + int((self.reduced_platform_power*3)/100)   

		if lower_val <= self.plt_power_status_value_1 <= upper_val:
			self._tester.test_logger.log("The Platform power values are within 3% of the previous specified value")
		else:
			self._tester.exit_with_error("The Platform power values are not within 3% of the previous specified value")

		#stopping ptu workload
		self.wl_thread.kill()
		time.sleep(10)
		self.stop_ptu()

		self._tester.test_logger.log("Setting PPL1 to original value via BMC:")

		self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x30 wrpkgconfig 58 0 0x02663080", verify=True)
		self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x31 wrpkgconfig 58 0 0x02663080", verify=True)

	def run_pi_pm_post(self):
		pass

######################################################################################################
class PI_PM_Psys_Modify_PPL2_via_PECI_Verify_Power_Capping_2S_Linux(PI_PM_Testcase):
	_default = {"_config_name": "Psys_Modify_PPL2_via_PECI_Verify_Power_Capping_2S_Linux"}

	def __init__(self): 
		super(PI_PM_Psys_Modify_PPL2_via_PECI_Verify_Power_Capping_2S_Linux, self).__init__()
		self.name = "Psys_Modify_PPL2_via_PECI_Verify_Power_Capping_2S_Linux" 
		self.targetlogfolder = "Psys_Modify_PPL2_via_PECI_Verify_Power_Capping_2S_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "PsysPowerLimitCsrLock=0x0,PsysPowerInfoLock=0x0,PsysPowerLimitAndInfo=0x1,PsysPowerDomain=0x1"
		self.run_ptu = True
		self.check_turbo_flag = False
		self.bios_knob_set = True
		self.min_range = 582
		self.max_range = 618

	def _start(self):
		self.product_class = PI_PM_Psys_Modify_PPL2_via_PECI_Verify_Power_Capping_2S_Linux_TestEngine
		return self



class PI_PM_Psys_Modify_PPL2_via_PECI_Verify_Power_Capping_2S_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "Verify Power Capping correctly limits platform power consumption"
	
	def run_pi_pm_main(self):
		self.min_range=582
		self.max_range=618
		_sv_sockets = self._tester.sv_control.sv_sockets
		self.socket_count = int(self._frame.sv_control.socket_count)
		self._tester.test_logger.log("Running Psys_Modify_PPL2_via_PMUtil_Verify_Power_Capping_Linux")

		#for ppl2 part
		self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x30 wrpkgconfig 59 0 0x026612C0", verify=True)
		self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x30 wrpkgconfig 59 1 0x026612C0", verify=True)

		self.wl_thread = thread_with_trace(target=self.run_ptu_workload_with_cp ,args=(50,))                    
		self.wl_thread.start()
		time.sleep(30)

		#run platform power consumption changed function
		
		self.power_plt_energy_status_thread = thread_with_trace(target=self.plt_energy_status)
		self.power_plt_energy_status_thread.start()
		time.sleep(120)

		#now compare and check if plt_power value is +/- 3% of reduced_platform power
		self.power_plt_energy_status_thread.kill()
		self._tester.test_logger.log("Completed Power_Platform_Energy_Status_Loop dump.. Going for Log parsing")
		self.test_logs.append(self.psys_log_file)
		status = self.parse_psys_power_dump(self.psys_log_file, self.min_range, self.max_range)
		
	
		#stop ptu operation
		self.wl_thread.kill()
		time.sleep(10)
		self.stop_ptu()

		#setting to original value
		self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x30 wrpkgconfig 59 0 0x02663A30", verify=True)
		self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x30 wrpkgconfig 59 0 0x02663A30", verify=True)


	def run_pi_pm_post(self):
		pass



		


	
#######################################################################################################
class PI_PM_Psys_Modify_PPL1_via_PMUtil_Verify_Power_Capping_2S_4S_Linux(PI_PM_Testcase):
	_default = {"_config_name": "Psys_Modify_PPL1_via_PMUtil_Verify_Power_Capping_2S_4S_Linux"}

	def __init__(self): 
		super(PI_PM_Psys_Modify_PPL1_via_PMUtil_Verify_Power_Capping_2S_4S_Linux, self).__init__()
		self.name = "Psys_Modify_PPL1_via_PMUtil_Verify_Power_Domain_Linux" 
		self.targetlogfolder = "Psys_Modify_PPL1_via_PMUtil_Verify_Power_Domain_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "PsysPowerLimitCsrLock=0x0,PsysPowerInfoLock=0x0,PsysPowerLimitAndInfo=0x1,PsysPowerDomain=0x1"
		self.run_ptu = True
		self.check_turbo_flag = False
		self.bios_knob_set = True
		self.min_range = 582
		self.max_range = 618

	def _start(self):
		self.product_class = PI_PM_Psys_Modify_PPL1_via_PMUtil_Verify_Power_Capping_2S_4S_Linux_TestEngine
		return self

class PI_PM_Psys_Modify_PPL1_via_PMUtil_Verify_Power_Capping_2S_4S_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "Collect the Power Platform Energy Status loop and observe whether it meets the expected range"
	
	def run_pi_pm_main(self):
		_sv_sockets = self._tester.sv_control.sv_sockets
		self.socket_count = int(self._frame.sv_control.socket_count)
		self._tester.test_logger.log("Running Psys_Modify_PPL1_and_PPL2_via_PMUtil_Verify_Power_Capping_Linux")

		#for ppl1 part
		self._tester.test_logger.log("Running PTU WL for Test")
		self.wl_thread = thread_with_trace(target=self.run_ptu_workload, args=("ct3",), name="ptu") 
		self.wl_thread.start()
		time.sleep(30)
		#read platform power consumption value
		self.plt_power_status_value = self.run_platform_power_consumption()
		self.reduced_platform_power=int(self.plt_power_status_value*0.7)   # reduce plat power by 30%
		self.reduced_platform_power_hex=hex(self.reduced_platform_power)
		digit_to_extract=self.reduced_platform_power_hex[2:]
		last_val="0x0266"+ digit_to_extract
		self.peci_cmds_soc0 = "peci_cmds -a 0x30 wrpkgconfig 58 0 "+last_val
		self.peci_cmds_soc1 = "peci_cmds -a 0x31 wrpkgconfig 58 1 "+last_val

		self.set_and_check_peci_cmds(self.peci_cmds_soc0,self.peci_cmds_soc1)

		#second read of platform power val
		self.plt_power_status_value_1 = self.run_platform_power_consumption()

		#read plat power and it should be +/- 3% of the old value set
		lower_val= self.reduced_platform_power - int((self.reduced_platform_power*3)/100)
		upper_val= self.reduced_platform_power + int((self.reduced_platform_power*3)/100)   

		if lower_val <= self.power_plt_energy_status_value_1 <= upper_val:
			self._tester.test_logger.log("The Platform power values are within 3% of the previous specified value")
		else:
			self._tester.exit_with_error("The Platform power values are not within 3% of the previous specified value")

		#stopping ptu workload
		self.wl_thread.kill()
		time.sleep(10)
	

		#setting ppl1 value to old values
		self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x30 wrpkgconfig 58 0 0x02663080", verify=True)
		self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x31 wrpkgconfig 58 0 0x02663080", verify=True)

		self._tester.test_logger.log("Test Psys_Modify_PPL1_via_PMUtil_Verify_Power_Capping_2S_4S_Linux completed!")


		

	def run_pi_pm_post(self):
		pass




#######################################################################################################
class PI_PM_Psys_Modify_PPL2_via_PMUtil_Verify_Power_Capping_2S_4S_Linux(PI_PM_Testcase):
	_default = {"_config_name": "Psys_Modify_PPL2_via_PMUtil_Verify_Power_Capping_Linux"}

	def __init__(self): 
		super(PI_PM_Psys_Modify_PPL1_via_PMUtil_Verify_Power_Capping_2S_4S_Linux, self).__init__()
		self.name = "Psys_Modify_PPL2_via_PMUtil_Verify_Power_Domain_Linux" 
		self.targetlogfolder = "Psys_Modify_PPL2_via_PMUtil_Verify_Power_Domain_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "PsysPowerLimitCsrLock=0x0,PsysPowerInfoLock=0x0,PsysPowerLimitAndInfo=0x1,PsysPowerDomain=0x1"
		self.run_ptu = True
		self.check_turbo_flag = False
		self.bios_knob_set = True
		self.min_range = 582
		self.max_range = 618

	def _start(self):
		self.product_class = PI_PM_Psys_Modify_PPL2_via_PMUtil_Verify_Power_Capping_2S_4S_Linux_TestEngine
		return self

class PI_PM_Psys_Modify_PPL2_via_PMUtil_Verify_Power_Capping_2S_4S_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "Collect the Power Platform Energy Status loop and observe whether it meets the expected range"

	def run_pi_pm_main(self):
		self.min_range = 582
		self.max_range = 618
		_sv_sockets = self._tester.sv_control.sv_sockets
		self.socket_count = int(self._frame.sv_control.socket_count)

		self._tester.test_logger.log("Test Psys_Modify_PPL2_via_PMUtil_Verify_Power_Capping_Linux started!")
		self._tester.test_logger.log("Running PTU WL for Test")
		self.wl_thread = thread_with_trace(target=self.run_ptu_workload_with_cp ,args=(50,))
		self.wl_thread.start()
		time.sleep(30)
		#reading platform power
		
		self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x30 wrpkgconfig 59 0 0x026612C0", verify=True)
		self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x31 wrpkgconfig 59 1 0x026612C0", verify=True)

		#read platform power consumption for ~1 minute:
		self.power_plt_energy_status_thread = thread_with_trace(target=self.plt_energy_status)
		self.power_plt_energy_status_thread.start()
		time.sleep(120)
		self.power_plt_energy_status_thread.kill()
		self._tester.test_logger.log("Completed Power_Platform_Energy_Status_Loop dump.. Going for Log parsing")
		self.test_logs.append(self.psys_log_file)
		status = self.parse_psys_power_dump(self.psys_log_file, self.min_range, self.max_range)
		self.wl_thread.kill()
		time.sleep(10)
		self.stop_ptu()

		self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x30 wrpkgconfig 59 0 0x02663A30", verify=True)
		self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x31 wrpkgconfig 59 0 0x02663A30", verify=True)

		
		self._tester.test_logger.log("Test Psys_Modify_PPL1_PPL2_via_PMUtil_Verify_Power_Capping_Linux completed!")


	def run_pi_pm_post(self):
		pass




#######################################################################################################

class PI_PM_Psys_Modify_PPL2_CSR_Verify_Power_Capping_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_Psys_Modify_PPL2_CSR_Verify_Power_Capping_Linux"}

	def __init__(self):
		super(PI_PM_Psys_Modify_PPL2_CSR_Verify_Power_Capping_Linux, self).__init__()
		self.name = "PSYS_MODIFY_PPL2_CSR_VERIFY_POWER_CAPPING_LINUX" 
		self.targetlogfolder = "PI_PM_Psys_Modify_PPL2_CSR_Verify_Power_Capping_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "PsysPowerLimitCsrLock=0x0,PsysPowerInfoLock=0x0,PsysPowerLimitAndInfo=0x1,PsysPowerDomain=0x1"
		self.run_ptu = True
		self.check_turbo_flag = False
		self.bios_knob_set = True
		self.min_range = 582
		self.max_range = 618

	def _start(self):
		self.product_class = PI_PM_Psys_Modify_PPL2_CSR_Verify_Power_Capping_Linux_TestEngine
		return self

class PI_PM_Psys_Modify_PPL2_CSR_Verify_Power_Capping_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "Collect the Power Platform Energy Status loop and observe whether it meets the expected range"
	
	def run_pi_pm_main(self):
		_sv_sockets = self._tester.sv_control.sv_sockets
		self.min_range = 582
		self.max_range = 618
		self._tester.test_logger.log("Running Psys_Modify_PPL2_Peci_Verify_Power_Capping_Linux")
		self._tester.test_logger.log("Setting the PPL2 via CSR")
		self.socket_count = int(self._frame.sv_control.socket_count)            
		for socket in _sv_sockets:
			socket.uncore.punit.platform_rapl_limit_cfg = 0x026612c002643080
			val = socket.uncore.punit.platform_rapl_limit_cfg.read()
			self._tester.test_logger.log("Reading the platform_rapl_limit_cfg value after setting it to '0x026612c002643080' : {}".format(val))

		self._tester.test_logger.log("CSR Commands for setting the PPL2 to 600W is triggered successfully")
		
		self.wl_thread = thread_with_trace(target=self.run_ptu_workload_with_cp ,args=(50,))                    
		self.wl_thread.start()
		time.sleep(60)
		self.power_plt_energy_status_thread = thread_with_trace(target=self.run_power_plt_energy_status)
		self.power_plt_energy_status_thread.start()
		time.sleep(120)
		self.power_plt_energy_status_thread.kill()
		self.wl_thread.kill()
		time.sleep(10)
		self.stop_ptu()
		self._tester.test_logger.log("Completed PTU WL and Power_Platform_Energy_Status_Loop dump.. Going for Log parsing")
		self.test_logs.append(self.psys_log_file)

		self._tester.test_logger.log("Resetting the PPL2 to Original value using CSR cmds")
		for socket in _sv_sockets:
			socket.uncore.punit.platform_rapl_limit_cfg = 0x63a3002663080
		self._tester.test_logger.log("CSR Commands for resetting the PPL2 to Original value is successfully")

		status = self.parse_psys_power_dump(self.psys_log_file, self.min_range, self.max_range)

		if status:
			self._tester.exit_with_error("FAIL : Power_Platform_Energy_Status value not matching with the expected range. Please check the above logs for details")
		else:
			self._tester.test_logger.log("PASS : Power_Platform_Energy_Status value matched with the expected range.")


	def pipm_parse_log(self,pipm_app_log):
		pass

#######################################################################################################

class PI_PM_Psys_Modify_PPL1_CSR_Verify_Power_Capping_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_Psys_Modify_PPL1_CSR_Verify_Power_Capping_Linux"}

	def __init__(self):
		super(PI_PM_Psys_Modify_PPL1_CSR_Verify_Power_Capping_Linux, self).__init__()
		self.name = "PSYS_MODIFY_PPL1_CSR_VERIFY_POWER_CAPPING_LINUX" 
		self.targetlogfolder = "PI_PM_Psys_Modify_PPL1_CSR_Verify_Power_Capping_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "PsysPowerLimitCsrLock=0x0,PsysPowerInfoLock=0x0,PsysPowerLimitAndInfo=0x1,PsysPowerDomain=0x1"
		self.run_ptu = True
		self.check_turbo_flag = False
		self.bios_knob_set = True
		self.min_range = 776
		self.max_range = 824

	def _start(self):
		self.product_class = PI_PM_Psys_Modify_PPL1_CSR_Verify_Power_Capping_Linux_TestEngine
		return self

class PI_PM_Psys_Modify_PPL1_CSR_Verify_Power_Capping_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "Collect the Power Platform Energy Status loop and observe whether it meets the expected range"
	
	def run_pi_pm_main(self):
		_sv_sockets = self._tester.sv_control.sv_sockets
		self.min_range = 776
		self.max_range = 824
		self._tester.test_logger.log("Running Psys_Modify_PPL1_Peci_Verify_Power_Capping_Linux")
		self._tester.test_logger.log("Setting the PPL1 via CSR")
		self.socket_count = int(self._frame.sv_control.socket_count)            
		for socket in _sv_sockets:
			socket.uncore.punit.platform_rapl_limit_cfg = 0x63a3002661900
			val = socket.uncore.punit.platform_rapl_limit_cfg.read()
			self._tester.test_logger.log("Reading the platform_rapl_limit_cfg value after setting it to '0x63a3002661900' : {}".format(val))

		self._tester.test_logger.log("CSR Commands for setting the PPL1 to 800W is triggered successfully")
		
		self.wl_thread = thread_with_trace(target=self.run_ptu_workload_with_cp ,args=(50,))                    
		self.wl_thread.start()
		time.sleep(60)
		self.power_plt_energy_status_thread = thread_with_trace(target=self.run_power_plt_energy_status)
		self.power_plt_energy_status_thread.start()
		time.sleep(120)
		self.power_plt_energy_status_thread.kill()
		self.wl_thread.kill()
		time.sleep(10)
		self.stop_ptu()
		self._tester.test_logger.log("Completed PTU WL and Power_Platform_Energy_Status_Loop dump.. Going for Log parsing")
		self.test_logs.append(self.psys_log_file)

		self._tester.test_logger.log("Resetting the PPL1 to Original value using CSR cmds")
		for socket in _sv_sockets:
			socket.uncore.punit.platform_rapl_limit_cfg = 0x63a3002663080
		self._tester.test_logger.log("CSR Commands for resetting the PPL1 to Original value is successfully")

		status = self.parse_psys_power_dump(self.psys_log_file, self.min_range, self.max_range)

		if status:
			self._tester.exit_with_error("FAIL : Power_Platform_Energy_Status value not matching with the expected range. Please check the above logs for details")
		else:
			self._tester.test_logger.log("PASS : Power_Platform_Energy_Status value matched with the expected range.")


#######################################################################################################

class PI_PM_TurboBoost_DecreasedCoreCount_Test_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_TurboBoost_DecreasedCoreCount_Test_Linux"}

	def __init__(self):
		super(PI_PM_TurboBoost_DecreasedCoreCount_Test_Linux, self).__init__()
		self.name = "TURBOBOOST_DECREASED_CORECOUNT_LINUX" 
		self.targetlogfolder = "PI_PM_TurboBoost_DecreasedCoreCount_Test_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "TurboMode=0x1" 
		self.bios_knob_set = False
		self.test_step = 0
	
	def _start(self):
		self.product_class = PI_PM_DecreasedCoreCount_Test_Linux_TestEngine
		return self

#######################################################################################################

class PI_PM_TurboBoost_DecreasedCoreCount_SSE_Test_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_TurboBoost_DecreasedCoreCount_SSE_Test_Linux"}

	def __init__(self):
		super(PI_PM_TurboBoost_DecreasedCoreCount_SSE_Test_Linux, self).__init__()
		self.name = "TURBOBOOST_DECREASED_CORECOUNT_SSE_LINUX" 
		self.targetlogfolder = "PI_PM_TurboBoost_DecreasedCoreCount_SSE_Test_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "TurboMode=0x1" 
		self.bios_knob_set = False
		self.test_step = 1
	
	def _start(self):
		self.product_class = PI_PM_DecreasedCoreCount_Test_Linux_TestEngine
		return self
#######################################################################################################

class PI_PM_TurboBoost_DecreasedCoreCount_AVX2_Test_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_TurboBoost_DecreasedCoreCount_AVX2_Test_Linux"}

	def __init__(self):
		super(PI_PM_TurboBoost_DecreasedCoreCount_AVX2_Test_Linux, self).__init__()
		self.name = "TURBOBOOST_DECREASED_CORECOUNT_AVX2_LINUX" 
		self.targetlogfolder = "PI_PM_TurboBoost_DecreasedCoreCount_AVX2_Test_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "TurboMode=0x1" 
		self.bios_knob_set = False
		self.test_step = 2
	
	def _start(self):
		self.product_class = PI_PM_DecreasedCoreCount_Test_Linux_TestEngine
		return self

#######################################################################################################

class PI_PM_TurboBoost_DecreasedCoreCount_AVX512_Test_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_TurboBoost_DecreasedCoreCount_AVX512_Test_Linux"}

	def __init__(self):
		super(PI_PM_TurboBoost_DecreasedCoreCount_AVX512_Test_Linux, self).__init__()
		self.name = "TURBOBOOST_DECREASED_CORECOUNT_AVX512_LINUX" 
		self.targetlogfolder = "PI_PM_TurboBoost_DecreasedCoreCount_AVX512_Test_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "TurboMode=0x1" 
		self.bios_knob_set = False
		self.test_step = 3
	
	def _start(self):
		self.product_class = PI_PM_DecreasedCoreCount_Test_Linux_TestEngine
		return self

#######################################################################################################

###################################################################################################
#CRAUTO-9047
class PI_PM_Pstates_Decreased_Corecount_Test_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_Pstates_Decreased_Corecount_Test_Linux"}

	def __init__(self):
		super(PI_PM_Pstates_Decreased_Corecount_Test_Linux, self).__init__()
		self.name = "POWER_PSTATES_DECREASED_CORECOUNT_LINUX" 
		self.targetlogfolder = "PI_PM_Pstates_Decreased_Corecount_Test_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "TurboMode=0x1,ProcessorEistEnable=0x1" 
		self.run_ptu = False
		self.check_turbo_flag = False
		self.bios_knob_set = True
		self.test_step = 4
	
	def _start(self):
		self.product_class = PI_PM_DecreasedCoreCount_Test_Linux_TestEngine
		return self
##############################################################################################################


class PI_PM_DecreasedCoreCount_Test_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "Collect the frequency of CPU and observe whether it meets the requirements"
	
	def run_pi_pm_main(self):
		self.test_step = self._config.test_step
		self._tester.test_logger.log("*********************************Test step is {} : Running {} Test******************************".format(self._config.test_step,self.name))
	
		self.get_available_bitmap()
		self.init_corecount=True
		self.bitmask_decreasedcore_calculation(self.socket_value,self.init_corecount)
		self._tester.test_logger.log("Final bitmask per socket is {}".format(self.final_dict))
		
		self.socket_count = int(self._frame.sv_control.socket_count)
		self._tester.test_logger.log("Current Socket Count is : {}".format(self.socket_count))
		if self.socket_count == 2:
			self.socket0_knobvalue=self.final_dict[0]
			self.socket1_knobvalue=self.final_dict[1]
			self.knob ='CoreDisableMask_0={} , CoreDisableMask_1={}'.format(self.socket0_knobvalue,self.socket1_knobvalue)
		elif self.socket_count == 4:
			self.socket0_knobvalue=self.final_dict[0]
			self.socket1_knobvalue=self.final_dict[1]
			self.socket2_knobvalue=self.final_dict[2]
			self.socket3_knobvalue=self.final_dict[3]
			self.knob ='CoreDisableMask_0={} , CoreDisableMask_1={}, CoreDisableMask_2={} , CoreDisableMask_3={}'.format(self.socket0_knobvalue,self.socket1_knobvalue, self.socket2_knobvalue, self.socket3_knobvalue)
		self._tester.test_logger.log("Bios knob to set : {}".format(self.knob))
		self._tester.sut_control.set_bios_knob(self.knob)
		self._tester.tester_functions.ac_power_cycle()
		self.bios_knob_set=True

		self.get_disable_bitmap()
		self.init_corecount=False
		self.bitmask_decreasedcore_calculation(self.socket_value,self.init_corecount)
		self._tester.test_logger.log("initial_core_count is  : {}".format(self.initial_core_count))
		
		if self.decremented_core_count == int(self.initial_core_count - 1):
			self._tester.test_logger.log("Successfully decreased the core count using BitMap")
		else:
			self._tester.exit_with_error("FAIL: The decreased core count didnt match")

		if self.cpu_type in ["GNR","SRF"]:
			self._tester.test_logger.log("Running the test on GNR....")
			#calculating sse P1 and sse act from pmutil
			self.gnr_pmutil_frequency_calculator()
			# self.sse_act_val = 2400
			# self.sse_freq_val = 1800
			# self.avx2_freq_val = 1600
			# self.avx512_freq_val = 1500
			
			self._tester.test_logger.log("SSE ACT Frequency is {}".format(self.sse_act_val))
			self._tester.test_logger.log("SSE P1 Frequency is {}".format(self.sse_freq_val))
			self._tester.test_logger.log("AVX2 P1 Frequency is {}".format(self.avx2_freq_val))
			self._tester.test_logger.log("AVX512 P1 Frequency is {}".format(self.avx512_freq_val))
		
		elif self.cpu_type =="SPR":
			self._tester.test_logger.log("Running the test on SPR....")
			#calculating sse P1 and sse act from pysv
			self.frequency_calculator() 
		
		self.check_sut_os()

		#start standalone script
		self._tester.test_logger.log("Triggering {}_Testcase. Please wait for sometime to complete test".format(self._config.name))
		cmd = "python {dir}/{scr} --test {testname} --os {operatingsystem}  --sse_p1_freq {ssep1} --sse_act_freq {ssef} --avx2_freq {af2} --avx512_freq {af512} --test_step {tp} --cpu {cp}".format(
			dir=self.pi_pm_app_path,
			scr=self.target_script,
			testname=self.name,
			operatingsystem=self.operating_system,
			ssep1 = self.sse_freq_val,
			ssef = self.sse_act_val,
			af2=self.avx2_freq_val,
			af512 = self.avx512_freq_val,
			tp = self.test_step,
			cp = self.cpu_type)

		self.result = self._tester.sut_control.os_access.run_command(cmd, verify=False, retry=0)
		self._tester.test_logger.log("Standalone test details **********")
		self._tester.test_logger.log(str(self.result))

		#Log copy to host
		self.collect_output_logs(self.result.combined_lines)
		self._tester.test_logger.log("PIPM app log is:{}".format(self.pipm_app_log))
		self.test_logs.append(self.pipm_app_log)
		if self.test_step == 0 or self.test_step == 4:
			self.test_logs.append('{t}/SoCWatchOutput.csv'.format(t=self.pi_pm_applog_folder))
		
		elif self.test_step == 1 or self.test_step == 2 or self.test_step == 3:
			self._tester.test_logger.log("PTU Monitor app log is :{}".format(self.ptu_log_file))
			self.test_logs.append(self.ptu_log_file)
		
		self.copy_pi_pm_logs()
		self.pipm_parse_log(self.pipm_app_log)
		
		if self.bios_knob_set:
			self._tester.test_logger.log("Reverting BitMap Bios Knobs to default.") 
			self._tester.sut_control.reset_bios_knob()
			self._tester.tester_functions.ac_power_cycle()


			
################################################################################################
#CRAUTO-9243
class PI_PM_HWP_OOB_Enabled_Disabled_Test_Windows(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_HWP_OOB_Enabled_Disabled_Test_Windows"}

	def __init__(self):
		super(PI_PM_HWP_OOB_Enabled_Disabled_Test_Windows, self).__init__()
		self.name = "HWP_OOB_WINDOWS" 
		self.targetlogfolder = "PI_PM_HWP_OOB_Enabled_Disabled_Test_Windows"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.WINDOWS]
		self.suite_membership = [SUITE_TYPE.WINDOWS_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "ProcessorHWPMEnable=0x2,TurboMode=0x1,ProcessorEppProfile=0xFF"
		self.run_ptu = False
		self.bios_knob_set=False

	def _start(self):
		self.product_class = PI_PM_HWP_OOB_Enabled_Disabled_Test_Windows_TestEngine
		return self

class PI_PM_HWP_OOB_Enabled_Disabled_Test_Windows_TestEngine(PI_PM_TestEngine):
	class_lable = "Collect the frequency of CPU and observe whether it meets the requirements"


	def run_pi_pm_main(self):
		if self.cpu_type == "SPR":
			self.frequency_calculator() 
			self._tester.test_logger.log("SSE P1 and SSE ACT frequency values from _sv_sockets are {}MHZ and {}MHZ".format(self.sse_freq_val,self.sse_act_val))
			self.hwp_oob_enabled()
			self.copy_pi_pm_logs()
			self.pipm_parse_log(self.pipm_app_log)
			self.hwp_oob_disabled()
			
		elif self.cpu_type in ["GNR","SRF"]:
			self.gnr_get_pysv_freq()
			self.hwp_oob_enabled()


		self._tester.test_logger.log("Set the OS Processor Power Management set back to highest power consumption.")
		self._tester.test_logger.log("Setting Minimum processorstate to 5% and Maximum A processor state to 100% on the target via Control Panel")
		self._tester.sut_control.os_access.run_command("powercfg -setacvalueindex SCHEME_BALANCED SUB_PROCESSOR PROCTHROTTLEMAX 100")
		self._tester.sut_control.os_access.run_command("powercfg -setacvalueindex SCHEME_BALANCED SUB_PROCESSOR PROCTHROTTLEMIN 5")
		self._tester.sut_control.os_access.run_command("powercfg.exe -setactive SCHEME_CURRENT")
	
	def power_cycle_and_waitforosboot(self):
		self._tester.sut_control.ac_power_cycle(verify=False)
		if not self._tester.sut_control.wait_for_os():
			self._tester.exit_with_error("Unable to ping target after power cycle Exiting script ")
		# Sleeping for 1 minute after power cycle   
		time.sleep(60)


	def hwp_oob_enabled(self):
		_sv_sockets = self._tester.sv_control.sv_sockets
		self._tester.test_logger.log("Setting Minimum and Maximum A processor state to 5% on the target via Control Panel")
		self._tester.sut_control.os_access.run_command("powercfg -setacvalueindex SCHEME_BALANCED SUB_PROCESSOR PROCTHROTTLEMAX 5")
		self._tester.sut_control.os_access.run_command("powercfg -setacvalueindex SCHEME_BALANCED SUB_PROCESSOR PROCTHROTTLEMIN 5")
		self._tester.sut_control.os_access.run_command("powercfg.exe -setactive SCHEME_CURRENT")
		
		self._tester.test_logger.log("Triggering {}_Testcase_step 1. Please wait for sometime to complete test".format(self._config.name))
		cmd = "powershell.exe; python {dir}//{scr} --test {testname} --os {operatingsystem}  --test_step {step} --sse_p1_freq {ssep1} --sse_act_freq {ssef} --tool {wl}".format(
			dir=self.pi_pm_app_path_win, 
			scr=self.target_script, 
			testname=self.name,
			operatingsystem=self.operating_system,
			step=1,
			ssep1 = self.sse_freq_val,
			ssef = self.sse_act_val,
			wl = self.tool)
		self.result = self._tester.sut_control.os_access.run_command(cmd, verify=True, retry=0)
		self._tester.test_logger.log("Completed running the standalone.....for {}_Testcase_step 1".format(self._config.name))
		self._tester.test_logger.log(str(self.result))

		self.collect_output_logs(self.result.combined_lines)
		self._tester.test_logger.log("PIPM app log is :{}".format(self.pipm_app_log))

		self.test_logs.append(self.pipm_app_log)
		self.test_logs.append( os.path.join(self.socwatch_path_win, 'SoCWatchOutput.csv'))
		
	def hwp_oob_disabled(self):
		#Starting step 2 of the test case
		self.knob = "ProcessorHWPMEnable=0x0"
		self._tester.test_logger.log("Bios knob to set : {}".format(self.knob))
		self._tester.sut_control.set_bios_knob(self.knob)
		self.power_cycle_and_waitforosboot()
		self.bios_knob_set=True

		self._tester.test_logger.log("Setting Minimum and Maximum A processor state to 5% on the target via Control Panel")
		self._tester.sut_control.os_access.run_command("powercfg -setacvalueindex SCHEME_BALANCED SUB_PROCESSOR PROCTHROTTLEMAX 5")
		self._tester.sut_control.os_access.run_command("powercfg -setacvalueindex SCHEME_BALANCED SUB_PROCESSOR PROCTHROTTLEMIN 5")
		self._tester.sut_control.os_access.run_command("powercfg.exe -setactive SCHEME_CURRENT")
		
		for socket in _sv_sockets:
			self.register_val = socket.uncore.punit.hwp_capabilities.most_efficient_performance.read()
			self._tester.test_logger.log("Most Efficient frequency value from pythinsv is {}".format(self.register_val))
			self.ret_value = str(self.register_val)
			Pn_freq = int(self.ret_value, 16)*100
			self._tester.test_logger.log("Pn frequency value in MHZ is {}".format(type(Pn_freq)))
		self._tester.test_logger.log("Pn Frequency value is {}".format(Pn_freq))
		
		
		self._tester.test_logger.log("Triggering {}_Testcase_step 2. Please wait for sometime to complete test".format(self._config.name))
		cmd = "powershell.exe; python {dir}//{scr} --test {testname} --os {operatingsystem}  --pn_val {pf} --test_step {step} --tool {wl}".format(
			dir=self.pi_pm_app_path_win, 
			scr=self.target_script, 
			testname=self.name,
			operatingsystem=self.operating_system,
			pf = Pn_freq, 
			step=2,
			wl = self.tool)
		self.result = self._tester.sut_control.os_access.run_command(cmd, verify=False, retry=0)
		self._tester.test_logger.log("Completed running the standalone.....for {}_Testcase_step 2".format(self._config.name))
		self._tester.test_logger.log(str(self.result))

		self.collect_output_logs(self.result.combined_lines)
		self._tester.test_logger.log("PIPM app log is :{}".format(self.pipm_app_log))
		
		self.test_logs.append(self.pipm_app_log)
		self.test_logs.append(os.path.join(self.socwatch_path_win, 'SoCWatchOutput.csv'))
		
		

#######################################################################################################
#CRAUTO-10302

class PI_PM_Psys_Verify_PECI_PCS_Platform_Power_Throttled_Duration_2S_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_Psys_Verify_PECI_PCS_Platform_Power_Throttled_Duration_2S_Linux"}

	def __init__(self):
		super(PI_PM_Psys_Verify_PECI_PCS_Platform_Power_Throttled_Duration_2S_Linux, self).__init__()
		self.name = "PSYS_VERIFY_PECI_PCS_PLATFORM_POWER_THROTTLED_DURATION_2S_LINUX" 
		self.targetlogfolder = "PI_PM_Psys_Verify_PECI_PCS_Platform_Power_Throttled_Duration_2S_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "PsysPowerLimitCsrLock=0x0,PsysPowerInfoLock=0x0,PsysPowerLimitAndInfo=0x1,PsysPowerDomain=0x1"
		self.run_ptu = True
		self.bios_knob_set = True
		
	def _start(self):
		self.product_class = PI_PM_Psys_Verify_PECI_PCS_Platform_Power_Throttled_Duration_2S_Linux_TestEngine
		return self

class PI_PM_Psys_Verify_PECI_PCS_Platform_Power_Throttled_Duration_2S_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "This test case ensures the PECI PCS PLATFORM_RAPL_THROTTLED_DURATION is updated correctly upon a platform RAPL limit. Compare the Value reported with Platform_RAPL_Perf_Status"

	def run_pi_pm_main(self):
		_sv_sockets = self._tester.sv_control.sv_sockets

		for i in range(1,4):
			self.rapl_perf_list =[]

			self._tester.test_logger.log("Running PTU WL for Test {}".format(i))

			if i == 1:
				self.wl_thread = thread_with_trace(target=self.run_ptu_workload, args=("ct3",), name="ptu")
			elif i == 2:
				self.wl_thread = thread_with_trace(target=self.run_ptu_workload, args=("ct4",), name="ptu")
			elif i == 3:
				self.wl_thread = thread_with_trace(target=self.run_ptu_workload, args=("ct5",), name="ptu")



			if self._tester.manager.cpu_project == CPU_PROJECT.GNR:
				self._tester.test_logger.log("Running ptu mon as background task..")
				self.mon_thread = thread_with_trace(target=self.run_ptu_monitor)                    
				self.mon_thread.start()


			self._tester.test_logger.log("Running PTU WL for Test {}".format(i))
			self.wl_thread.start()
			time.sleep(10)
			#read platform power consumption value
			self.power_plt_energy_status_value = self.run_platform_power_consumption()

			#reduce it by 45% 
			if self._tester.manager.cpu_project == CPU_PROJECT.GNR:
				self.power_plt_energy_status_value = self.run_platform_power_consumption()
				self.reduced_platform_power=self.power_plt_energy_status_value*0.55   # reduce plat power by 45%
				socket.uncore.punit.platform_rapl_limit_cfg.ppl1 = self.reduced_platform_power * 8
				#Again read the value for platform power consumption value
				self.power_plt_energy_status_value_1=self.run_platform_power_consumption()

				#now checking the values are within 3% of the specified value
				self.calculate_percent_diff_two_val(self.power_plt_energy_status_value,self.power_plt_energy_status_value_1,percent=3)

				self.peci_cmds_socket0 = "peci_cmds -a 0x30 RdPkgConfig 11 0xFE"
				self.peci_cmds_socket1 = "peci_cmds -a 0x31 RdPkgConfig 11 0xFE"
				self.check_peci_val_increment(self.peci_cmds_socket0,self.peci_cmds_socket1) 
				self.wl_thread.kill()
				time.sleep(10)
				self.mon_thread.kill()
				time.sleep(30)
				self.result_post_ptu_stop = self.check_peci_val_static(self.peci_cmds_socket0,self.peci_cmds_socket1) 
				self.soc0_peci_val = self.result_post_ptu_stop[0]
				self.soc1_peci_val = self.result_post_ptu_stop[1]
				#reading the plat_rapl_perf_status
				if self.socket_count == 2:
					self.soc0_rapl_perf_cmd = "cd {} && ./pmutil_bin -S 0 -p 0 -tr 0x0 0x140".format(self.app_pmutil_path)
					self.soc0_rapl_perf = self._tester.sut_control.os_access.run_command(self.soc0_rapl_perf_cmd)
					self.soc1_rapl_perf_cmd = "cd {} && ./pmutil_bin -S 1 -p 0 -tr 0x0 0x140".format(self.app_pmutil_path)
					self.soc1_rapl_perf = self._tester.sut_control.os_access.run_command(self.soc1_rapl_perf_cmd)
				elif self.socket_count==4:
					self.soc2_rapl_perf_cmd = "cd {} && ./pmutil_bin -S 2 -p 0 -tr 0x0 0x140".format(self.app_pmutil_path)
					self.soc2_rapl_perf = self._tester.sut_control.os_access.run_command(self.soc2_rapl_perf_cmd)
					self.soc3_rapl_perf_cmd = "cd {} && ./pmutil_bin -S 3 -p 0 -tr 0x0 0x140".format(self.app_pmutil_path)
					self.soc3_rapl_perf = self._tester.sut_control.os_access.run_command(self.soc3_rapl_perf_cmd)

				
				output = self._tester.sut_control.os_access.run_command("lscpu | grep Core").combined_lines
				self.cores_per_socket = int(output[0].split(':')[1])
		
				# Calculation socket0_throttled_duration_per_core (hex) = socket0_throttled_duration (hex) / cores_per_socket (hex)
				self.socket0_throttled_duration_per_core_val = int(self.soc0_peci_val/self.cores_per_socket)
				self.socket1_throttled_duration_per_core_val = int(self.soc1_peci_val/self.cores_per_socket)
				self._tester.test_logger.log("Throttling Duration per core for Socket0".format(self.socket0_throttled_duration_per_core_val))
				self._tester.test_logger.log("Throttling Duration per core for Socket1".format(self.socket1_throttled_duration_per_core_val))

				self.calculate_pecentage_diff(x=self.soc0_rapl_perf, y=self.socket0_throttled_duration_per_core_val, i=self.soc1_rapl_perf, j=self.socket1_throttled_duration_per_core_val, percent_value=1)
				self._tester.test_logger.log("Psys_Verify_PECI_PCS_Platform_Power_Throttled_Duration__2S_Linux_SPR passed for Test{}".format(i))


			elif  self._tester.manager.cpu_project == CPU_PROJECT.SPR:
				self.plt_power_status_value = self.run_platform_power_consumption()
				self.reduced_platform_power=int(self.plt_power_status_value*0.7)
				self.reduced_platform_power_hex=hex(self.reduced_platform_power)
				digit_to_extract=self.reduced_platform_power_hex[2:]
				last_val="0x0266"+ digit_to_extract
				self.peci_cmds_soc0 = "peci_cmds -a 0x30 wrpkgconfig 58 0 "+last_val
				self.peci_cmds_soc1 = "peci_cmds -a 0x31 wrpkgconfig 58 1 "+last_val
				#now run the peci_cmds wrpkgconfig as bmc commands and check status code
				#making a new fucntion for that
				self.set_and_check_peci_cmds(self.peci_cmds_soc0,self.peci_cmds_soc1)
				
				self.peci_cmds_socket0 = "peci_cmds -a 0x30 RdPkgConfig 11 0xFE"
				self.peci_cmds_socket1 = "peci_cmds -a 0x31 RdPkgConfig 11 0xFE"
				self.check_peci_val_static(self.peci_cmds_socket0,self.peci_cmds_socket1) 

				self.wl_thread = thread_with_trace(target=self.run_ptu_workload, args=("ct3",), name="ptu")
				self.wl_thread.start()
				time.sleep(10)
				self.check_peci_val_increment(self.peci_cmds_socket0,self.peci_cmds_socket1) 
				self.wl_thread.kill() #update this in pf file
				time.sleep(10)
				self.result_post_ptu_stop=self.check_peci_val_static(self.peci_cmds_socket0,self.peci_cmds_socket1)
				self.socket0_throttled_duration_cores = self.result_post_ptu_stop[0]
				self.socket1_throttled_duration_cores = self.result_post_ptu_stop[1] 
				#now platform rapl perf status 
				self.pysv_register_val=[]
				for socket in _sv_sockets:
					self.register_val = socket.uncore.punit.platform_rapl_perf_status.read()
					self.ret_value = str(self.register_val)[2:]
					self.int_register_val = int(self.ret_value, 16)
					self.pysv_register_val.append(self.int_register_val)

				self._tester.test_logger.log("The Platform_rapl_perf_status values are: {}".format(self.pysv_register_val))
				self.platform_rapl_perf_status_socket0 = self.pysv_register_val[0]
				self.platform_rapl_perf_status_socket1 = self.pysv_register_val[1]


				output = self._tester.sut_control.os_access.run_command("lscpu | grep Core").combined_lines
				self.cores_per_socket = int(output[0].split(':')[1])
		
				# Calculation socket0_throttled_duration_per_core (hex) = socket0_throttled_duration (hex) / cores_per_socket (hex)
				
				self.socket0_throttled_duration_per_core_val = int(self.socket0_throttled_duration_cores/self.cores_per_socket)
				self.socket1_throttled_duration_per_core_val = int(self.socket1_throttled_duration_cores/self.cores_per_socket)
				self._tester.test_logger.log("Throttling Duration per core for Socket0".format(self.socket0_throttled_duration_per_core_val))
				self._tester.test_logger.log("Throttling Duration per core for Socket1".format(self.socket1_throttled_duration_per_core_val))

				self.calculate_pecentage_diff(x=self.platform_rapl_perf_status_socket0, y=self.socket0_throttled_duration_per_core_val, i=self.platform_rapl_perf_status_socket1, j=self.socket1_throttled_duration_per_core_val, percent_value=1)
				self._tester.test_logger.log("Psys_Verify_PECI_PCS_Platform_Power_Throttled_Duration_2S_Linux_GNR passed for Test{}".format(i))

				

	def run_pi_pm_post(self):
		pass



####################################################################################################
#CRAUTO-10304
class PI_PM_SocketRAPL_Verify_Socket_Power_Limit_Indicator_Via_PECI_2S_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_SocketRAPL_Verify_Socket_Power_Limit_Indicator_Via_PECI_2S_Linux"}

	def __init__(self):
		super(PI_PM_SocketRAPL_Verify_Socket_Power_Limit_Indicator_Via_PECI_2S_Linux, self).__init__()
		self.name = "PI_PM_SOCKET_RAPL_VERIFY_SOCKET_POWER_LIMIT_INDICATOR_PECI_2S_LINUX" 
		self.targetlogfolder = "PI_PM_SocketRAPL_Verify_Socket_Power_Limit_Indicator_Via_PECI_2S_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		#Package RAPL Limit MSR Lock <Disable> Package RAPL Limit CSR Lock <Disable>
		self.bios_knobs = "TurboPowerLimitLock=0x0,TurboPowerLimitCsrLock=0x0"      
		self.run_ptu = True
		self.bios_knob_set = True
		
	def _start(self):
		self.product_class = PI_PM_SocketRAPL_Verify_Socket_Power_Limit_Indicator_Via_PECI_2S_Linux_TestEngine
		return self

class PI_PM_SocketRAPL_Verify_Socket_Power_Limit_Indicator_Via_PECI_2S_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "Validate PECI PCS Index 8 parameter 0xFF Socket Power Limit Indicator. Verify counter increments upon frequency throttle below P1."

	def run_pi_pm_main(self):
		_sv_sockets = self._tester.sv_control.sv_sockets

		self._tester.test_logger.log("Setting the PL1 to 20% lower than TDP")
		for socket in _sv_sockets:
			self.pkg_tdp_original_val = int(socket.uncore.punit.package_power_sku.pkg_tdp)
			self.pkg_tdp_original_val_inwatts = int(self.pkg_tdp_original_val/8)
			self._tester.test_logger.log("The Original tdp value in Watts is {}".format(self.pkg_tdp_original_val_inwatts))
			self.reduced_tdp_val = int(self.pkg_tdp_original_val_inwatts * 0.80)
			self.pl1_original_hex = socket.uncore.punit.package_rapl_limit_cfg
			self.pl1_pkg_pwr_lim = socket.uncore.punit.package_rapl_limit.pkg_pwr_lim_1
			self._tester.test_logger.log("The Original PL1 value is {} and pkg_pwr_lim_1 value is {}".format(self.pl1_original_hex, self.pl1_pkg_pwr_lim))
		#Using pmutil.              
		self._tester.test_logger.log("Setting the PL1 to 20% lower than TDP Watt value: {} using the pmutil".format(self.reduced_tdp_val))
		set_pkg_pwr_cmd = "cd {} && ./pmutil_bin -set_pl1 {}".format(self.app_pmutil_path, self.reduced_tdp_val)
		self._tester.test_logger.log("Running command :{}".format(set_pkg_pwr_cmd))
		self._tester._os_access.run_command(set_pkg_pwr_cmd)

		for socket in _sv_sockets:
			self.new_pl1_value = socket.uncore.punit.package_rapl_limit.pkg_pwr_lim_1
			self._tester.test_logger.log("The PL1 value after 20% reduced TDP is {}".format(self.new_pl1_value))

		for i in range(1,4):
			if i == 1:
				self.wl_thread = thread_with_trace(target=self.run_ptu_workload, args=("ct3",), name="ptu") 
			elif i == 2:
				self.wl_thread = thread_with_trace(target=self.run_ptu_workload, args=("ct4",), name="ptu")
			elif i == 3:
				self.wl_thread = thread_with_trace(target=self.run_ptu_workload, args=("ct5",), name="ptu") 

			self.peci_cmds_socket0="peci_cmds -a 0x30 RdPkgConfig 8 0xFF"
			self.peci_cmds_socket1="peci_cmds -a 0x31 RdPkgConfig 8 0xFF"
			self._tester.test_logger.log("Running PTU WL for Test {}".format(i))
			self.wl_thread.start()
			time.sleep(60)
			self.check_peci_val_increment(self.peci_cmds_socket0,self.peci_cmds_socket1) # peci_cmds -a 0x30 RdPkgConfig 8 0xff

			self.wl_thread.kill()
			time.sleep(10)
			self.stop_ptu()
			time.sleep(30)
			
			self.result_post_ptu_stop = self.check_peci_val_static(self.peci_cmds_socket0,self.peci_cmds_socket1) # peci_cmds -a 0x30 RdPkgConfig 8 0xff 

		self._tester.test_logger.log("The Test is completed. So setting the PL1 back to original TDP value {}".format(self.pkg_tdp_original_val_inwatts))           
		self._tester.test_logger.log("Setting the PL1 to TDP Watt value: {} using the pmutil".format(self.pkg_tdp_original_val_inwatts))
		set_pkg_pwr_cmd_posttest = "cd {} && ./pmutil_bin -set_pl1 {}".format(self.app_pmutil_path, self.pkg_tdp_original_val_inwatts)
		self._tester.test_logger.log("Running command :{}".format(set_pkg_pwr_cmd_posttest))
		self._tester._os_access.run_command(set_pkg_pwr_cmd_posttest)
		time.sleep(30)

		for socket in _sv_sockets:
			self.read_val_posttest = socket.uncore.punit.package_rapl_limit.pkg_pwr_lim_1
			self._tester.test_logger.log("The PL1 value setting it to original TDP is {}".format(self.read_val_posttest))
			self._tester.test_logger.log("The PL1 is set back to {}".format(self.read_val_posttest))


###################################################################################################
#CRAUTO-10305
class PI_PM_Psys_Verify_Platform_Power_Limit_Indicator_Via_PECI_2S_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_Psys_Verify_Platform_Power_Limit_Indicator_Via_PECI_2S_Linux"}

	def __init__(self):
		super(PI_PM_Psys_Verify_Platform_Power_Limit_Indicator_Via_PECI_2S_Linux, self).__init__()
		self.name = "PSYS_VERIFY_PLATFORM_POWER_LIMIT_INDICATOR_PECI_2S_LINUX" 
		self.targetlogfolder = "PI_PM_Psys_Verify_Platform_Power_Limit_Indicator_Via_PECI_2S_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "PsysPowerLimitCsrLock=0x0,PsysPowerInfoLock=0x0,PsysPowerLimitAndInfo=0x1,PsysPowerDomain=0x1"
		self.bios_knob_set = True
		
	def _start(self):
		self.product_class = PI_PM_Psys_Verify_Platform_Power_Limit_Indicator_Via_PECI_2S_Linux_TestEngine
		return self

class PI_PM_Psys_Verify_Platform_Power_Limit_Indicator_Via_PECI_2S_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "Validate PECI PCS Index 8 parameter 0xFE Platform Power Limit Indicator. Verify counter increments upon frequency throttle below P1."

	def run_pi_pm_main(self):
		_sv_sockets = self._tester.sv_control.sv_sockets

		for socket in _sv_sockets:
			if self._tester.manager.cpu_project == CPU_PROJECT.SPR:
				self.pl1_original_val = socket.uncore.punit.platform_rapl_limit_cfg
			elif self._tester.manager.cpu_project == CPU_PROJECT.GNR:
				self.pl1_original_val = socket.io0.uncore.punit.ptpcioregs.ptpcioregs.platform_rapl_limit_cfg
			self._tester.test_logger.log("The Original PPL1 value is {}".format(self.pl1_original_val))
			self._tester.test_logger.log("Setting the PPL1 to 600W / 0x63a30026612c0")
			if self._tester.manager.cpu_project == CPU_PROJECT.SPR:
				socket.uncore.punit.platform_rapl_limit_cfg = 0x63a30026612c0
				read_val_pretest = socket.uncore.punit.platform_rapl_limit_cfg.read()
			elif  self._tester.manager.cpu_project == CPU_PROJECT.GNR:
				socket.io0.uncore.punit.ptpcioregs.ptpcioregs.platform_rapl_limit_cfg = 0x63a30026612c0
				read_val_pretest = socket.io0.uncore.punit.ptpcioregs.ptpcioregs.platform_rapl_limit_cfg.read()

			if read_val_pretest == "0x63a30026612c0":
				self._tester.test_logger.log("The PL1 is successfully set to {} and type is {}".format(read_val_pretest, type(read_val_pretest)))
			else:
				self._tester.test_logger.log("The PL1 is successfully set to {} and type is {}. Else condition".format(read_val_pretest, type(read_val_pretest)))


		for i in range(1,4):
			if i == 1:
				self.wl_thread = thread_with_trace(target=self.run_ptu_workload, args=("ct3",), name="ptu") 
			elif i == 2:
				self.wl_thread = thread_with_trace(target=self.run_ptu_workload, args=("ct4",), name="ptu")
			elif i == 3:
				self.wl_thread = thread_with_trace(target=self.run_ptu_workload, args=("ct5",), name="ptu")

			self.peci_cmds_socket0="peci_cmds -a 0x30 RdPkgConfig 0x8 0xFE"
			self.peci_cmds_socket1="peci_cmds -a 0x31 RdPkgConfig 0x8 0xFE"

			self._tester.test_logger.log("Running ptu mon as background task..")
			self.mon_thread = thread_with_trace(target=self.run_ptu_monitor)                    
			self.mon_thread.start()

			self._tester.test_logger.log("Running PTU WL for Test {}".format(i))
			self.wl_thread.start()
			time.sleep(10)
			if self._tester.manager.cpu_project == CPU_PROJECT.SPR:
				self.power_plt_energy_status_value1 = self.run_platform_power_consumption() #1st power val: 926 w
				self.reduced_platform_power=self.power_plt_energy_status_value1*0.7
				for socket in _sv_sockets:
					socket.uncore.punit.platform_rapl_limit_cfg.ppl1 = (int(self.reduced_platform_power * 8))
				self.power_plt_energy_status_value2 = self.run_platform_power_consumption()

				#for spr:
				#these  plat_power2  should be +/- 3% of reduced_plat_power
				val1= int(self.reduced_platform_power)
				val2= int(self.power_plt_energy_status_value2)

				lower_limit= val1-((val1*3)/100)
				upper_limit= val1-((val1*3)/100)

				if lower_limit <= val2 <= upper_limit:
					self._tester.test_logger.log("The platform power is with +/- 3% within the range!")
				else:
					self._tester.test_logger.log("The platform power exceeds the +/-3% range!")


			elif self._tester.manager.cpu_project == CPU_PROJECT.GNR:
				#for gnr:
				#plat_power must be +/- 5% of 600w
				self.power_plt_energy_status_value1 = self.run_platform_power_consumption()
				lower_limit= 570
				upper_limit=630
				if lower_limit <= self.power_plt_energy_status_value1 <= upper_limit:
					self._tester.test_logger.log("The platform power is with +/- 5% within the range!")
				else:
					self._tester.test_logger.log("The platform power exceeds the  +/-3% range!")


			#self.calculate_pecentage_diff(x=self.power_plt_energy_status_value, y=600, i=self.power_plt_energy_status_value, j=600, percent_value=5)
			self.check_peci_val_increment(self.peci_cmds_socket0,self.peci_cmds_socket1) #peci_cmds -a 0x30 RdPkgConfig 0x8 0xFE #socket0
			self.wl_thread.kill()
			time.sleep(10)
			self._tester.test_logger.log("Killing the current workload")
			self.mon_thread.kill()
			self._tester.test_logger.log("Killing the ptu monitor.")
			time.sleep(60)
			self.check_peci_val_static(self.peci_cmds_socket0,self.peci_cmds_socket1) #peci_cmds -a 0x30 RdPkgConfig 8 0xFE
			self._tester.test_logger.log("Verify_Platform_Power_Limit_Indicator_Via_PECI_2S_Linux Passed for Test {}".format(i))

		self._tester.test_logger.log("The Test is completed. So setting the PPL1 back to original value")           
		for socket in _sv_sockets:
			self._tester.test_logger.log("The Original PPL1 value is {}".format(self.pl1_original_val))
			if self._tester.manager.cpu_project == CPU_PROJECT.SPR:
				socket.uncore.punit.package_rapl_limit_cfg = self.pl1_original_val
			elif self._tester.manager.cpu_project == CPU_PROJECT.GNR:
				socket.io0.uncore.punit.ptpcioregs.ptpcioregs.platform_rapl_limit_cfg=self.pl1_original_val

			time.sleep(10)
			read_val_posttest = socket.uncore.punit.package_rapl_limit_cfg.read()
			self._tester.test_logger.log("The PPL1 is set back to {}".format(read_val_posttest))


	def run_pi_pm_post(self):
		pass

####################################################################################################
#CRAUTO-10307
class PI_PM_SOCKETRAPL_Verify_Socket_Power_Limit_Indicator_Via_PECI_With_Turbo_Activation_Ratio_2S_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_SOCKETRAPL_Verify_Socket_Power_Limit_Indicator_Via_PECI_With_Turbo_Activation_Ratio_2S_Linux"}

	def __init__(self):
		super(PI_PM_SOCKETRAPL_Verify_Socket_Power_Limit_Indicator_Via_PECI_With_Turbo_Activation_Ratio_2S_Linux, self).__init__()
		self.name = "PI_PM_SOCKET_RAPL_VERIFY_SOCKET_POWER_LIMIT_INDICATOR_PECI_WITH_TURBO_ACTIVATION_RATIO_2S_LINUX" 
		self.targetlogfolder = "PI_PM_SOCKETRAPL_Verify_Socket_Power_Limit_Indicator_Via_PECI_With_Turbo_Activation_Ratio_2S_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "TurboPowerLimitLock=0x0,TurboPowerLimitCsrLock=0x0"
		#Package RAPL Limit MSR Lock <Disable> Package RAPL Limit CSR Lock <Disable>
		self.run_ptu = True
		self.bios_knob_set = True
		
	def _start(self):
		self.product_class = PI_PM_SOCKETRAPL_Verify_Socket_Power_Limit_Indicator_Via_PECI_With_Turbo_Activation_Ratio_2S_Linux_TestEngine
		return self

class PI_PM_SOCKETRAPL_Verify_Socket_Power_Limit_Indicator_Via_PECI_With_Turbo_Activation_Ratio_2S_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "Validate PECI PCS Index 8 parameter 0xFF Socket Power Limit Indicator with Turbo Activation Ratio is set. Verify counter increments upon frequency throttle below the new P1 value."

	def run_pi_pm_main(self):
		_sv_sockets = self._tester.sv_control.sv_sockets

		self._tester.test_logger.log("Set new Turbo Activation ratio via BMC terminal using PECI")
		self._tester.sut_control.bmc_access.run_command("peci_cmds wrpkgconfig 33 0 0x18", verify=True).combined_lines
		time.sleep(10)
		self.output = self._tester.sut_control.bmc_access.run_command("peci_cmds rdpkgconfig 33 0", verify=True).combined_lines
		self._tester.test_logger.log("The peci_cmds output for Turbo Activation is {}".format(self.output))
		self.peci_val = self.output[0][13:]
		self._tester.test_logger.log("The peci_cmds output is successfully set to {}".format(self.peci_val))
		time.sleep(5)

		self._tester.test_logger.log("Setting the PL1 to 20% lower than TDP")
		for socket in _sv_sockets:
			self.pkg_tdp_original_val = int(socket.uncore.punit.package_power_sku.pkg_tdp)
			self.pkg_tdp_original_val_inwatts = int(self.pkg_tdp_original_val/8)
			self._tester.test_logger.log("The Original tdp value in Watts is {}".format(self.pkg_tdp_original_val_inwatts))
			self.reduced_tdp_val = int(self.pkg_tdp_original_val_inwatts * 0.80)
			self.pl1_original_hex = socket.uncore.punit.package_rapl_limit_cfg
			self.pl1_pkg_pwr_lim = socket.uncore.punit.package_rapl_limit.pkg_pwr_lim_1
			self._tester.test_logger.log("The Original PL1 value is {} and pkg_pwr_lim_1 value is {}".format(self.pl1_original_hex, self.pl1_pkg_pwr_lim))
		#Using pmutil.              
		self._tester.test_logger.log("Setting the PL1 to 20% lower than TDP Watt value: {} using the pmutil".format(self.reduced_tdp_val))
		set_pkg_pwr_cmd = "cd {} && ./pmutil_bin -set_pl1 {}".format(self.app_pmutil_path, self.reduced_tdp_val)
		self._tester.test_logger.log("Running command :{}".format(set_pkg_pwr_cmd))
		self._tester._os_access.run_command(set_pkg_pwr_cmd)

		for socket in _sv_sockets:
			self.new_pl1_value = socket.uncore.punit.package_rapl_limit.pkg_pwr_lim_1
			self._tester.test_logger.log("The PL1 value after 20% reduced TDP is {}".format(self.new_pl1_value))

		for i in range(1,4):
			self._tester.test_logger.log("Running PTU WL for Test {}".format(i))
			if i == 1:
				self.wl_thread = thread_with_trace(target=self.run_ptu_workload, args=("ct3",), name="ptu") 
			elif i == 2:
				self.wl_thread = thread_with_trace(target=self.run_ptu_workload, args=("ct4",), name="ptu")
			elif i == 3:
				self.wl_thread = thread_with_trace(target=self.run_ptu_workload, args=("ct5",), name="ptu")

			self.peci_cmds_socket0="peci_cmds -a 0x30 RdPkgConfig 8 0xFF"
			self.peci_cmds_socket1="peci_cmds -a 0x31 RdPkgConfig 8 0xFF"

			self.wl_thread.start()
			time.sleep(60)
			self.check_peci_val_increment(self.peci_cmds_socket0,self.peci_cmds_socket1) # peci_cmds -a 0x30 RdPkgConfig 8 0xFF
			self.wl_thread.kill()
			time.sleep(10)
			self.stop_ptu()
			time.sleep(30)
			self.result_post_ptu_stop = self.check_peci_val_static(self.peci_cmds_socket0,self.peci_cmds_socket1) # peci_cmds -a 0x30 RdPkgConfig 8 0xff

		self._tester.test_logger.log("The Test is completed. So setting the PL1 back to original TDP value {}".format(self.pkg_tdp_original_val_inwatts))           
		self._tester.test_logger.log("Setting the PL1 to TDP Watt value: {} using the pmutil".format(self.pkg_tdp_original_val_inwatts))
		set_pkg_pwr_cmd_posttest = "cd {} && ./pmutil_bin -set_pl1 {}".format(self.app_pmutil_path, self.pkg_tdp_original_val_inwatts)
		self._tester.test_logger.log("Running command :{}".format(set_pkg_pwr_cmd_posttest))
		self._tester._os_access.run_command(set_pkg_pwr_cmd_posttest)
		time.sleep(30)

		for socket in _sv_sockets:
			self.read_val_posttest = socket.uncore.punit.package_rapl_limit.pkg_pwr_lim_1
			self._tester.test_logger.log("The PL1 is set back to {} successfully".format(self.read_val_posttest))


###################################################################################################
#CRAUTO-10308
class PI_PM_SOCKETRAPL_Verify_PECI_PCS_Socket_Power_Throttled_Duration_Below_Base_Frequency_2S_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_SOCKETRAPL_Verify_PECI_PCS_Socket_Power_Throttled_Duration_Below_Base_Frequency_2S_Linux"}

	def __init__(self):
		super(PI_PM_SOCKETRAPL_Verify_PECI_PCS_Socket_Power_Throttled_Duration_Below_Base_Frequency_2S_Linux, self).__init__()
		self.name = "PI_PM_SOCKET_RAPL_VERIFY_PECI_PCS_SOCKET_POWER_THROTTLED_DURATION_BELOW_BASE_FREQ_2S_LINUX" 
		self.targetlogfolder = "PI_PM_SOCKETRAPL_Verify_PECI_PCS_Socket_Power_Throttled_Duration_Below_Base_Frequency_2S_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "TurboPowerLimitLock=0x0,TurboPowerLimitCsrLock=0x0"
		self.run_ptu = True
		self.bios_knob_set = True
				
	def _start(self):
		self.product_class = PI_PM_SOCKETRAPL_Verify_PECI_PCS_Socket_Power_Throttled_Duration_Below_Base_Frequency_2S_Linux_TestEngine
		return self

class PI_PM_SOCKETRAPL_Verify_PECI_PCS_Socket_Power_Throttled_Duration_Below_Base_Frequency_2S_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "This test case ensures the PECI PCS Socket_RAPL_THROTTLED_DURATION is updated correctly upon frequency throttle below P1 due to power throttling "

	def run_pi_pm_main(self):
		_sv_sockets = self._tester.sv_control.sv_sockets
		self._tester.test_logger.log("Running ptu mon as background task..")
		self.mon_thread = thread_with_trace(target=self.run_ptu_monitor)                    
		self.mon_thread.start()
		time.sleep(60)

		self._tester.test_logger.log("Setting the PL1 to 20% lower than TDP")
		for socket in _sv_sockets:
			self.pkg_tdp_original_val = int(socket.uncore.punit.package_power_sku.pkg_tdp)
			self.pkg_tdp_original_val_inwatts = int(self.pkg_tdp_original_val/8)
			self._tester.test_logger.log("The Original tdp value in Watts is {}".format(self.pkg_tdp_original_val_inwatts))
			self.reduced_tdp_val = int(self.pkg_tdp_original_val_inwatts * 0.80)
			self.pl1_original_hex = socket.uncore.punit.package_rapl_limit_cfg
			self.pl1_pkg_pwr_lim = socket.uncore.punit.package_rapl_limit.pkg_pwr_lim_1
			self._tester.test_logger.log("The Original PL1 value is {} and pkg_pwr_lim_1 value is {}".format(self.pl1_original_hex, self.pl1_pkg_pwr_lim))
		#Using pmutil.              
		self._tester.test_logger.log("Setting the PL1 to 20% lower than TDP Watt value: {} using the pmutil".format(self.reduced_tdp_val))
		set_pkg_pwr_cmd = "cd {} && ./pmutil_bin -set_pl1 {}".format(self.app_pmutil_path, self.reduced_tdp_val)
		self._tester.test_logger.log("Running command :{}".format(set_pkg_pwr_cmd))
		self._tester._os_access.run_command(set_pkg_pwr_cmd)

		for socket in _sv_sockets:
			self.new_pl1_value = socket.uncore.punit.package_rapl_limit.pkg_pwr_lim_1
			self._tester.test_logger.log("The PL1 value after 20% reduced TDP is {}".format(self.new_pl1_value))


		for i in range(1,4):
			if i == 1:
				self.wl_thread = thread_with_trace(target=self.run_ptu_workload, args=("ct3",), name="ptu") 
			elif i == 2:
				self.wl_thread = thread_with_trace(target=self.run_ptu_workload, args=("ct4",), name="ptu")
			elif i == 3:
				self.wl_thread = thread_with_trace(target=self.run_ptu_workload, args=("ct5",), name="ptu") 

			self.peci_cmds_socket0="peci_cmds -a 0x30 RdPkgConfig 11 0xFF"
			self.peci_cmds_socket1="peci_cmds -a 0x31 RdPkgConfig 11 0xFF"

			self._tester.test_logger.log("Running PTU WL for Test {} to increase platform power consumption".format(i))
			self.wl_thread.start()
			time.sleep(60)
			self.check_peci_val_increment(self.peci_cmds_socket0,self.peci_cmds_socket1) # peci_cmds -a 0x30 RdPkgConfig 11 0xFF #socket0
			self.wl_thread.kill()
			self.mon_thread.kill()
			time.sleep(10)
			self.stop_ptu()
			time.sleep(30)
			self.result_post_ptu_stop = self.check_peci_val_static(self.peci_cmds_socket0,self.peci_cmds_socket1) # peci_cmds -a 0x30 RdPkgConfig 11 0xFF #socket0
			self.soc0_peci_val = self.result_post_ptu_stop[0]
			self.soc1_peci_val = self.result_post_ptu_stop[1]
			self._tester.test_logger.log("The soc0 peci value is {} and soc1 peci value is {}".format(self.soc0_peci_val, self.soc1_peci_val))

			self.rapl_perf_list = []
			for socket in _sv_sockets:
				retval = int(socket.uncore.punit.package_rapl_perf_status)
				self.rapl_perf_list.append(retval)

			self._tester.test_logger.log("The rapl_perf output is {}".format(self.rapl_perf_list))
			self.soc0_rapl_perf = self.rapl_perf_list[0]
			self.soc1_rapl_perf = self.rapl_perf_list[1]

			output = self._tester.sut_control.os_access.run_command("lscpu | grep Core").combined_lines
			self.cores_per_socket = int(output[0].split(':')[1])
			
		
			# Calculation socket0_throttled_duration_per_core (hex) = socket0_throttled_duration (hex) / cores_per_socket (hex)
			self.socket0_throttled_duration_per_core_val = int(self.soc0_peci_val/self.cores_per_socket)
			self.socket1_throttled_duration_per_core_val = int(self.soc1_peci_val/self.cores_per_socket)
			self._tester.test_logger.log("Throttling Duration per core for Socket0: {}".format(self.socket0_throttled_duration_per_core_val))
			self._tester.test_logger.log("Throttling Duration per core for Socket1: {}".format(self.socket1_throttled_duration_per_core_val))

			self.calculate_pecentage_diff(x=self.soc0_rapl_perf, y=self.socket0_throttled_duration_per_core_val, i=self.soc1_rapl_perf, j=self.socket1_throttled_duration_per_core_val, percent_value=1)
			self._tester.test_logger.log("Verify_PECI_PCS_Socket_Power_Throttled_Duration Passed for Test{}".format(i))


		self._tester.test_logger.log("The Test is completed. So setting the PL1 back to original TDP value {}".format(self.pkg_tdp_original_val_inwatts))           
		self._tester.test_logger.log("Setting the PL1 to TDP Watt value: {} using the pmutil".format(self.pkg_tdp_original_val_inwatts))
		set_pkg_pwr_cmd_posttest = "cd {} && ./pmutil_bin -set_pl1 {}".format(self.app_pmutil_path, self.pkg_tdp_original_val_inwatts)
		self._tester.test_logger.log("Running command :{}".format(set_pkg_pwr_cmd_posttest))
		self._tester._os_access.run_command(set_pkg_pwr_cmd_posttest)
		time.sleep(30)

		for socket in _sv_sockets:
			self.read_val_posttest = socket.uncore.punit.package_rapl_limit.pkg_pwr_lim_1
			self._tester.test_logger.log("The PL1 is set back to {} successfully".format(self.read_val_posttest))

##############################################################################################################################

#CRAUTO-10306
class PI_PM_SocketRapl_Verify_PECI_PCS_Socket_Power_Throttled_Duration_2S_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_SocketRapl_Verify_PECI_PCS_Socket_Power_Throttled_Duration_2S_Linux"}

	def __init__(self):
		super(PI_PM_SocketRapl_Verify_PECI_PCS_Socket_Power_Throttled_Duration_2S_Linux, self).__init__()
		self.name = "PI_PM_SOCKET_RAPL_VERIFY_PECI_PCS_SOCKET_POWER_THROTTLED_DURATION_2S_LINUX" 
		self.targetlogfolder = "PI_PM_SocketRapl_Verify_PECI_PCS_Socket_Power_Throttled_Duration_2S_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		#self.bios_knobs = ""
		self.run_ptu = True
		self.bios_knob_set = True
		
	def _start(self):
		self.product_class = PI_PM_SocketRapl_Verify_PECI_PCS_Socket_Power_Throttled_Duration_2S_Linux_TestEngine
		return self

class PI_PM_SocketRapl_Verify_PECI_PCS_Socket_Power_Throttled_Duration_2S_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "Collect the Power Platform Energy Status loop and observe whether it meets the expected range"

	def run_pi_pm_main(self):
		_sv_sockets = self._tester.sv_control.sv_sockets

		for i in range(1,4):
			self.socketrapl_register_val = []

			self._tester.test_logger.log("Running PI_PM_SocketRapl_Verify_PECI_PCS_Socket_Power_Throttled_Duration_2S_Linux -- Test {}".format(i))
			if i == 1:
				self.wl_thread = thread_with_trace(target=self.run_ptu_workload, args=("ct3",), name="ptu")
			elif i == 2:
				self.wl_thread = thread_with_trace(target=self.run_ptu_workload, args=("ct4",), name="ptu")
			elif i == 3:
				self.wl_thread = thread_with_trace(target=self.run_ptu_workload, args=("ct5",), name="ptu")
			
			self.wl_thread.start()
			time.sleep(60)

			self._tester.test_logger.log("Reading the PECI PCS SOCKET_POWER_THROTTLED_DURATION via PECI in bmc after launching the PTU WL")
			self.peci_cmds_socket0="peci_cmds -a 0x30 RdPkgConfig 11 0xFF"
			self.peci_cmds_socket1="peci_cmds -a 0x31 RdPkgConfig 11 0xFF"
			self.check_peci_val_increment(self.peci_cmds_socket0,self.peci_cmds_socket1)
			self.wl_thread.kill()
			time.sleep(10)
			self.stop_ptu()
			time.sleep(30)
			self.result_post_ptu_stop = self.check_peci_val_static(self.peci_cmds_socket0,self.peci_cmds_socket1)
			self.socket0_throttled_duration_cores = self.result_post_ptu_stop[0]
			self.socket1_throttled_duration_cores = self.result_post_ptu_stop[1]

			for socket in _sv_sockets:
				self.register_val = socket.uncore.punit.package_rapl_perf_status.read()
				self.ret_value = str(self.register_val)[2:]
				self.int_register_val = int(self.ret_value, 16)
				self.socketrapl_register_val.append(self.int_register_val)

			self._tester.test_logger.log(self.socketrapl_register_val)
			self.package_rapl_perf_status_socket0 = self.socketrapl_register_val[0]
			self.package_rapl_perf_status_socket1 = self.socketrapl_register_val[1]

			output = self._tester.sut_control.os_access.run_command("lscpu | grep Core").combined_lines
			self.cores_per_socket = int(output[0].split(':')[1])
		
			self.socket0_throttled_duration_per_core_val = int(self.socket0_throttled_duration_cores/self.cores_per_socket)
			self.socket1_throttled_duration_per_core_val = int(self.socket1_throttled_duration_cores/self.cores_per_socket)
			self._tester.test_logger.log("Throttling Duration per core for Socket0".format(self.socket0_throttled_duration_per_core_val))
			self._tester.test_logger.log("Throttling Duration per core for Socket1".format(self.socket1_throttled_duration_per_core_val))

			self.calculate_pecentage_diff(x=self.package_rapl_perf_status_socket0, y=self.socket0_throttled_duration_per_core_val, i=self.package_rapl_perf_status_socket1, j=self.socket1_throttled_duration_per_core_val, percent_value=1)
			self._tester.test_logger.log("Verify_PECI_PCS_Socket_Power_Throttled_Duration Passed for Test{}".format(i))

	

##############################################################################################################################

#CRAUTO-10310
class PI_PM_Psys_Verify_PECI_PCS_Platform_Power_Throttled_Duration_Below_Base_Frequency_2S_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_Psys_Verify_PECI_PCS_Platform_Power_Throttled_Duration_Below_Base_Frequency_2S_Linux"}

	def __init__(self):
		super(PI_PM_Psys_Verify_PECI_PCS_Platform_Power_Throttled_Duration_Below_Base_Frequency_2S_Linux, self).__init__()
		self.name = "PSYS_VERIFY_PECI_PCS_PLATFORM_POWER_THROTTLED_DURATION_BELOW_BASE_FREQUENCY_2S_LINUX" 
		self.targetlogfolder = "Psys_Verify_PECI_PCS_Platform_Power_Throttled_Duration_Below_Base_Frequency_2S_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "PsysPowerLimitCsrLock=0x0,PsysPowerInfoLock=0x0,PsysPowerLimitAndInfo=0x1,PsysPowerDomain=0x1"
		#Package RAPL Limit MSR Lock <Disable> Package RAPL Limit CSR Lock <Disable>
		self.run_ptu = True
		self.bios_knob_set = True
		
	def _start(self):
		self.product_class = PI_PM_Psys_Verify_PECI_PCS_Platform_Power_Throttled_Duration_Below_Base_Frequency_2S_Linux_TestEngine
		return self

class PI_PM_Psys_Verify_PECI_PCS_Platform_Power_Throttled_Duration_Below_Base_Frequency_2S_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "Collect the Power Platform Energy Status loop and observe whether it meets the expected range"

	def run_pi_pm_main(self):
		_sv_sockets = self._tester.sv_control.sv_sockets
		self.socket_count= int(self._frame.sv_control.socket_count)
		self._tester.test_logger.log("Running Psys_Verify_PECI_PCS_Platform_Power_Throttled_Duration_Below_Base_Frequency_2S_Linux")

		for i in range(1,4):
			self.rapl_perf_list =[]
			'''
			self._tester.test_logger.log("Setting the PPL1 via CSR")            
			for socket in _sv_sockets:
				socket.uncore.punit.platform_rapl_limit_cfg = 0x63a30026612c0
				val = socket.uncore.punit.platform_rapl_limit_cfg.read()
				self._tester.test_logger.log("Reading the platform_rapl_limit_cfg value after setting it to '0x63a30026612c0' : {}".format(val))

			self._tester.test_logger.log("CSR Commands for setting the PPL1 to 600W is triggered successfully")
			'''
			if i == 1:
				self.wl_thread = thread_with_trace(target=self.run_ptu_workload, args=("ct3",), name="ptu") 
			elif i == 2:
				self.wl_thread = thread_with_trace(target=self.run_ptu_workload, args=("ct4",), name="ptu")
			elif i == 3:
				self.wl_thread = thread_with_trace(target=self.run_ptu_workload, args=("ct5",), name="ptu")



			if self._tester.manager.cpu_project == CPU_PROJECT.SPR:
				self._tester.test_logger.log("Running ptu mon as background task..")
				self.mon_thread = thread_with_trace(target=self.run_ptu_monitor)                    
				self.mon_thread.start()


			self._tester.test_logger.log("Running PTU WL for Test {}".format(i))
			self.wl_thread.start()
			time.sleep(30)
			
			if self._tester.manager.cpu_project == CPU_PROJECT.SPR:
				self.power_plt_energy_status_value = self.run_platform_power_consumption()
				self.reduced_platform_power=self.power_plt_energy_status_value*0.7
				for socket in _sv_sockets:
					socket.uncore.punit.platform_rapl_limit_cfg.ppl1 = int(self.reduced_platform_power * 8)
				#Again read the value for platform power consumption value
				self.power_plt_energy_status_value_1=self.run_platform_power_consumption()

				#now checking the values are within 3% of the specified value
				self.calculate_percent_diff_two_val(self.power_plt_energy_status_value,self.power_plt_energy_status_value_1,percent=3)

				self.peci_cmds_socket0 = "peci_cmds -a 0x30 RdPkgConfig 11 0xFE"
				self.peci_cmds_socket1 = "peci_cmds -a 0x31 RdPkgConfig 11 0xFE"
				self.check_peci_val_increment(self.peci_cmds_socket0,self.peci_cmds_socket1) 
				self.wl_thread.kill()
				time.sleep(10)
				self._tester.test_logger.log("PTU thread has been stopped.")
				self.mon_thread.kill()
				self._tester.test_logger.log("PTU monitor operation stopped.")
				time.sleep(30)
				self.result_post_ptu_stop = self.check_peci_val_static(self.peci_cmds_socket0,self.peci_cmds_socket1) 
				self.soc0_peci_val = self.result_post_ptu_stop[0]
				self.soc1_peci_val = self.result_post_ptu_stop[1]

				for socket in _sv_sockets:
					self.register_val = socket.uncore.punit.platform_rapl_perf_status.read()
					self.ret_value = str(self.register_val)[2:]
					self.int_register_val = int(self.ret_value, 16)
					self.rapl_perf_list.append(self.int_register_val)

				self._tester.test_logger.log("The rapl_perf output is {}".format(self.rapl_perf_list))
				self.soc0_rapl_perf = self.rapl_perf_list[0]
				self.soc1_rapl_perf = self.rapl_perf_list[1]

				output = self._tester.sut_control.os_access.run_command("lscpu | grep Core").combined_lines
				self.cores_per_socket = int(output[0].split(':')[1])
		
				# Calculation socket0_throttled_duration_per_core (hex) = socket0_throttled_duration (hex) / cores_per_socket (hex)
				self.socket0_throttled_duration_per_core_val = int(self.soc0_peci_val/self.cores_per_socket)
				self.socket1_throttled_duration_per_core_val = int(self.soc1_peci_val/self.cores_per_socket)
				self._tester.test_logger.log("Throttling Duration per core for Socket0".format(self.socket0_throttled_duration_per_core_val))
				self._tester.test_logger.log("Throttling Duration per core for Socket1".format(self.socket1_throttled_duration_per_core_val))

				self.calculate_pecentage_diff(x=self.soc0_rapl_perf, y=self.socket0_throttled_duration_per_core_val, i=self.soc1_rapl_perf, j=self.socket1_throttled_duration_per_core_val, percent_value=1)
				self._tester.test_logger.log("Psys_Verify_PECI_PCS_Platform_Power_Throttled_Duration_Below_Base_Frequency_2S_Linux_SPR passed for Test{}".format(i))


			elif  self._tester.manager.cpu_project == CPU_PROJECT.GNR:
				self.power_plt_energy_status_value = self.run_platform_power_consumption()
				self.reduced_platform_power=int(self.power_plt_energy_status_value*0.7)
				self.reduced_platform_power_hex=hex(self.reduced_platform_power)
				digit_to_extract=self.reduced_platform_power_hex[2:]
				last_val="0x0266"+ digit_to_extract
				self.peci_cmds_soc0 = "peci_cmds -a 0x30 wrpkgconfig 58 0 "+last_val
				self.peci_cmds_soc1 = "peci_cmds -a 0x31 wrpkgconfig 58 1 "+last_val
				#now run the peci_cmds wrpkgconfig as bmc commands and check status code
				#making a new fucntion for that

				self.set_and_check_peci_cmds(self.peci_cmds_soc0,self.peci_cmds_soc1)

				
				self.peci_cmds_socket0 = "peci_cmds -a 0x30 RdPkgConfig 11 0xFE"
				self.peci_cmds_socket1 = "peci_cmds -a 0x31 RdPkgConfig 11 0xFE"
				self.check_peci_val_static(self.peci_cmds_socket0,self.peci_cmds_socket1) 

				self.wl_thread_1 = thread_with_trace(target=self.run_ptu_workload, args=("ct3",), name="ptu")
				self.wl_thread.start()
				time.sleep(10)
				self.check_peci_val_increment(self.peci_cmds_socket0,self.peci_cmds_socket1) 
				self.wl_thread.kill()
				self.wl_thread_1.kill()
				time.sleep(10)
				self.result_post_ptu_stop=self.check_peci_val_static(self.peci_cmds_socket0,self.peci_cmds_socket1)
				self.soc0_peci_val = self.result_post_ptu_stop[0]
				self.soc1_peci_val = self.result_post_ptu_stop[1] 
				#now platform rapl perf status read using pmutil

				if self.socket_count == 2:
					self.soc0_rapl_perf_cmd = "cd {} && ./pmutil_bin -S 0 -p 0 -tr 0x0 0x140".format(self.app_pmutil_path)
					self.soc0_rapl_perf = self._tester.sut_control.os_access.run_command(self.soc0_rapl_perf_cmd)
					self.soc1_rapl_perf_cmd = "cd {} && ./pmutil_bin -S 1 -p 0 -tr 0x0 0x140".format(self.app_pmutil_path)
					self.soc1_rapl_perf = self._tester.sut_control.os_access.run_command(self.soc1_rapl_perf_cmd)
				elif self.socket_count==4:
					self.soc2_rapl_perf_cmd = "cd {} && ./pmutil_bin -S 2 -p 0 -tr 0x0 0x140".format(self.app_pmutil_path)
					self.soc2_rapl_perf = self._tester.sut_control.os_access.run_command(self.soc2_rapl_perf_cmd)
					self.soc3_rapl_perf_cmd = "cd {} && ./pmutil_bin -S 3 -p 0 -tr 0x0 0x140".format(self.app_pmutil_path)
					self.soc3_rapl_perf = self._tester.sut_control.os_access.run_command(self.soc3_rapl_perf_cmd)

				output = self._tester.sut_control.os_access.run_command("lscpu | grep Core").combined_lines
				self.cores_per_socket = int(output[0].split(':')[1])
		
				# Calculation socket0_throttled_duration_per_core (hex) = socket0_throttled_duration (hex) / cores_per_socket (hex)
				if self.socket_count == 2:
					self.socket0_throttled_duration_per_core_val = int(self.soc0_peci_val/self.cores_per_socket)
					self.socket1_throttled_duration_per_core_val = int(self.soc1_peci_val/self.cores_per_socket)
					self._tester.test_logger.log("Throttling Duration per core for Socket0".format(self.socket0_throttled_duration_per_core_val))
					self._tester.test_logger.log("Throttling Duration per core for Socket1".format(self.socket1_throttled_duration_per_core_val))

					self.calculate_pecentage_diff(x=self.soc0_rapl_perf, y=self.socket0_throttled_duration_per_core_val, i=self.soc1_rapl_perf, j=self.socket1_throttled_duration_per_core_val, percent_value=1)
					self._tester.test_logger.log("Psys_Verify_PECI_PCS_Platform_Power_Throttled_Duration_Below_Base_Frequency_2S_Linux_GNR passed for Test{}".format(i))



				elif self.socket_count == 4:
					self.socket2_throttled_duration_per_core_val = int(self.soc2_peci_val/self.cores_per_socket)
					self.socket3_throttled_duration_per_core_val = int(self.soc3_peci_val/self.cores_per_socket)
					self._tester.test_logger.log("Throttling Duration per core for Socket2".format(self.socket2_throttled_duration_per_core_val))
					self._tester.test_logger.log("Throttling Duration per core for Socket3".format(self.socket3_throttled_duration_per_core_val))


					self.calculate_pecentage_diff(x=self.soc2_rapl_perf, y=self.socket2_throttled_duration_per_core_val, i=self.soc3_rapl_perf, j=self.socket3_throttled_duration_per_core_val, percent_value=1)
					self._tester.test_logger.log("Psys_Verify_PECI_PCS_Platform_Power_Throttled_Duration_Below_Base_Frequency_4S_Linux_GNR passed for Test{}".format(i))


	def run_pi_pm_post(self):
		pass


##############################################################################################################################
#CRAUTO-10309

class PI_PM_Psys_Verify_PECI_Platform_Power_Limit_Indicator_Non_Zero_Turbo_Activation_2S_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_Psys_Verify_PECI_Platform_Power_Limit_Indicator_Non_Zero_Turbo_Activation_2S_Linux"}

	def __init__(self):
		super(PI_PM_Psys_Verify_PECI_Platform_Power_Limit_Indicator_Non_Zero_Turbo_Activation_2S_Linux, self).__init__()
		self.name = "PSYS_VERIFY_PECI_PLATFORM_POWER_LIMIT_INDICATOR_NON_ZERO_TURBO_ACTIVATION_2S_LINUX" 
		self.targetlogfolder = "Psys_Verify_PECI_Platform_Power_Limit_Indicator_Non_Zero_Turbo_Activation_2S_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "PsysPowerLimitCsrLock=0x0,PsysPowerInfoLock=0x0,PsysPowerLimitAndInfo=0x1,PsysPowerDomain=0x1"
		#Package RAPL Limit MSR Lock <Disable> Package RAPL Limit CSR Lock <Disable>
		self.run_ptu = True
		self.bios_knob_set = True
		
	def _start(self):
		self.product_class = PI_PM_Psys_Verify_PECI_Platform_Power_Limit_Indicator_Non_Zero_Turbo_Activation_2S_Linux_TestEngine
		return self

class PI_PM_Psys_Verify_PECI_Platform_Power_Limit_Indicator_Non_Zero_Turbo_Activation_2S_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "Collect the Power Platform Energy Status loop and observe whether it meets the expected range"

	def run_pi_pm_main(self):
		_sv_sockets = self._tester.sv_control.sv_sockets
		self._tester.test_logger.log("Running Psys_Verify_PECI_Platform_Power_Limit_Indicator_Non_Zero_Turbo_Activation_2S_Linux")
		self._tester.test_logger.log("Set new Turbo Activation ratio via PECI in BMC terminal")

		self.peci_cmds_set_soc0 = "peci_cmds -a 0x30 Wrpkgconfig 33 0 0x18"
		self.peci_cmds_set_soc1 = "peci_cmds -a 0x31 Wrpkgconfig 33 0 0x18"
		self.peci_cmds_read_soc0 = "peci_cmds -a 0x30 RdPkgConfig 11 0xFE"
		self.peci_cmds_read_soc1 = "peci_cmds -a 0x31 RdPkgConfig 11 0xFE"
		self.expected_turbo_val =["   cc:0x40 0x00000018"]

		self._tester.test_logger.log("Setting new Turbo Activation ratio for socket 0 and socket 1 via PECI cmds")
		self._tester.sut_control.bmc_access.run_command(self.peci_cmds_set_soc0, verify=True)
		self._tester.sut_control.bmc_access.run_command(self.peci_cmds_set_soc1, verify=True)
		time.sleep(5)
		self._tester.test_logger.log("Reading new Turbo Activation ratio for socket 0 and socket 1 via PECI cmds")
		self.output = self._tester.sut_control.bmc_access.run_command(self.peci_cmds_read_soc0, verify=True).combined_lines
		self.output1 = self._tester.sut_control.bmc_access.run_command(self.peci_cmds_read_soc1, verify=True).combined_lines
	

		if self.output and self.output1 == self.expected_turbo_val:
			self._tester.test_logger.log("New Turbo activation status is set properly to {}".format(self.expected_turbo_val))
		else:
			self._tester.test_logger.log("Failed to set new Turbo activation status")

		for socket in _sv_sockets:
			self.pl1_original_val = socket.uncore.punit.platform_rapl_limit_cfg
			self._tester.test_logger.log("The Original PL1 value is {}".format(self.pl1_original_val))
			self._tester.test_logger.log("Setting the PL1 to 600W / 0x63a30026612c0")
			socket.uncore.punit.platform_rapl_limit_cfg = 0x63a30026612c0
			read_val_pretest = socket.uncore.punit.platform_rapl_limit_cfg.read()
			if read_val_pretest == "0x63a30026612c0":
				self._tester.test_logger.log("The PL1 is successfully set to {} and type is {}".format(read_val_pretest, type(read_val_pretest)))
			else:
				self._tester.test_logger.log("The PL1 is successfully set to {} and type is {}. Else condition".format(read_val_pretest, type(read_val_pretest)))


		for i in range(1,4):
			if i == 1:
				self.wl_thread = thread_with_trace(target=self.run_ptu_workload, args=("ct3",), name="ptu") 
			elif i == 2:
				self.wl_thread = thread_with_trace(target=self.run_ptu_workload, args=("ct4",), name="ptu")
			elif i == 3:
				self.wl_thread = thread_with_trace(target=self.run_ptu_workload, args=("ct5",), name="ptu")

			self.peci_cmds_socket0="peci_cmds -a 0x30 RdPkgConfig 0x8 0xFE"
			self.peci_cmds_socket1="peci_cmds -a 0x31 RdPkgConfig 0x8 0xFE"

			self._tester.test_logger.log("Running PTU WL for Test {}".format(i))
			self.wl_thread.start()
			time.sleep(60)
			self.power_plt_energy_status_value = self.run_power_plt_energy_status_single()
			time.sleep(10)

			self.calculate_pecentage_diff(x=self.power_plt_energy_status_value, y=600, i=self.power_plt_energy_status_value, j=600, percent_value=5)
			self.check_peci_val_increment(self.peci_cmds_socket0,self.peci_cmds_socket1) #peci_cmds -a 0x30 RdPkgConfig 0x8 0xFE #socket0
			self.wl_thread.kill()
			time.sleep(10)
			self.stop_ptu()
			time.sleep(60)
			self.check_peci_val_static(self.peci_cmds_socket0,self.peci_cmds_socket1) #peci_cmds -a 0x30 RdPkgConfig 8 0xFE
			self._tester.test_logger.log("Verify_Platform_Power_Limit_Indicator_Via_PECI_2S_Linux Passed for Test {}".format(i))

		self._tester.test_logger.log("The Test is completed. So setting the PL1 back to original value")            
		for socket in _sv_sockets:
			self._tester.test_logger.log("The Original PL1 value is {}".format(self.pl1_original_val))
			socket.uncore.punit.package_rapl_limit_cfg = self.pl1_original_val
			time.sleep(10)
			read_val_posttest = socket.uncore.punit.package_rapl_limit_cfg.read()
			self._tester.test_logger.log("The PL1 is set back to {}".format(read_val_posttest))


##############################################################################################################################
#CRAUTO-9400
class PI_PM_TMUL_SoCwatch_Test_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_TMUL_SoCwatch_Test_Linux"}

	def __init__(self):
		super(PI_PM_TMUL_SoCwatch_Test_Linux, self).__init__()
		self.name = "TMUL_LINUX" 
		self.targetlogfolder = "PI_PM_TMUL_BENCHDNN_Test_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.run_ptu = False
		self.check_turbo_flag = False
		self.bios_knob_set = False
	
	def _start(self):
		self.product_class = PI_PM_TMUL_SoCwatch_Test_Linux_TestEngine
		return self
##########################################################################################################

class PI_PM_TMUL_Frequency_F16_Test_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_TMUL_SoCwatch_Test_Linux"}

	def __init__(self):
		super(PI_PM_TMUL_Frequency_F16_Test_Linux, self).__init__()
		self.name = "TMUL_LINUX_F16" 
		self.targetlogfolder = "PI_PM_TMUL_Frequency_Test_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.run_ptu = False
		self.check_turbo_flag = False
		self.bios_knob_set = False
		self.tool = "tmul_F16"
	
	def _start(self):
		self.product_class = PI_PM_TMUL_SoCwatch_Test_Linux_TestEngine
		return self

#####################################################################################################
class PI_PM_TMUL_Frequency_Test_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_TMUL_SoCwatch_Test_Linux"}

	def __init__(self):
		super(PI_PM_TMUL_Frequency_Test_Linux, self).__init__()
		self.name = "TMUL_LINUX_INT8BF16" 
		self.targetlogfolder = "PI_PM_TMUL_Frequency_Test_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.run_ptu = False
		self.check_turbo_flag = False
		self.bios_knob_set = False
		self.tool = "tmul"
	
	def _start(self):
		self.product_class = PI_PM_TMUL_SoCwatch_Test_Linux_TestEngine
		return self

########################################################################################################
class PI_PM_TMUL_SoCwatch_Test_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "Run BenchDNN tests and verify if operating frequency is in between TMUL and SSE"
	
	def run_pi_pm_main(self):
		self.tool = self._config.tool
		self.turbo_enabled = False
		ret_code = self._tester._sut_control.read_bios_knob('TurboMode=0x1')
		self._tester.test_logger.log("Status of bios knob verification is : {}".format(ret_code))   
		if ret_code == 0:
			self._tester.test_logger.log("BIOS Knob TurboMode is Enabled!!!")
			self.turbo_enabled = True
		else:
			self._tester.test_logger.log("BIOS Knob TurboMode is Disabled!!!")

		if self._tester._sut_control.cpus.name == CPU_TYPES.sapphirerapids.name:
			self.frequency_calculator() 
			self._tester.test_logger.log("Frequency values are TMUL {}MHZ ,SSE P1 {}MHZ and SSE ACT {}MHZ  from _sv_sockets".format(self.tmul_freq,self.sse_freq_val,self.sse_act_val))
			self.spr_pmutil_calculator()

			self._tester.test_logger.log("Comparing TMUL P1 Frequency value from OS2P Mailbox and pysv ")
			if self.sse_freq_val == self.sse_p1:
				self._tester.test_logger.log("PASS: TMUL P1 Frequency value from OS2P Mailbox {} and pysv {} are equal! ".format(self.tmul_p1,self.tmul_freq))
			else:
				self._tester.exit_with_error("FAIL: TMUL P1 Frequency value from OS2P Mailbox {} and pysv {} are not equal! ".format(self.tmul_p1,self.tmul_freq))
		elif  self._tester._sut_control.cpus.name == CPU_TYPES.graniterapids.name:
			self._tester.test_logger.log("Runninig the test on GNR")
			self.gnr_pmutil_frequency_calculator()
		
		self.check_sut_os()
		#start standalone script
		self._tester.test_logger.log("Triggering {}_Testcase. Please wait for sometime to complete test".format(self._config.name))
		#cmd = "python {dir}/{scr} --test {testname} --os {operatingsystem} ".format(dir=self.pi_pm_app_path, scr=self.target_script, testname=self.name,operatingsystem=self.operating_system,qdfvalue=self.qdf_value)
		cmd = "chmod -R 777 {dir}".format(dir=self.pi_pm_app_path)
		self.result = self._tester.sut_control.os_access.run_command(cmd, verify=False, retry=0)
		cmd = "cd {dir} && python {dir}/{scr} --test {testname} --os {operatingsystem}  --tmul_freq {tf} --sse_act_freq {ssef} --sse_p1_freq {ssep1} --tool {tool} --cpu {cp}".format(
			dir=self.pi_pm_app_path,
			scr=self.target_script,
			testname=self.name,
			operatingsystem=self.operating_system,
			tf=self.tmul_freq,
			ssef=self.sse_act_val,
			tool = self.tool,
			cp = self.cpu_type,
			ssep1 = self.sse_freq_val)

		if (self.turbo_enabled):
			cmd = cmd + " --turbo True"
		self.result = self._tester.sut_control.os_access.run_command(cmd, verify=False, retry=0)
		self._tester.test_logger.log("Standalone test details **********")
		self._tester.test_logger.log(str(self.result))

		#Log copy to host
		self.collect_output_logs(self.result.combined_lines)
		self._tester.test_logger.log("PIPM app log is:{}".format(self.pipm_app_log))
		self.test_logs.append(self.pipm_app_log)
		if self.cpu_type == "SPR":
			self.test_logs.append('{t}/SoCWatchOutput.csv'.format(t=self.pi_pm_applog_folder))
		else:
			self.test_logs.append(self.ptu_log_file)
		
		self.copy_pi_pm_logs()
		self.pipm_parse_log(self.pipm_app_log)
		
############################################################################################################
#CRAUTO-9397
class PI_PM_Flex_Ratio_Basic_Enable_Test_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_Flex_Ratio_Basic_Enable_Test_Linux"}

	def __init__(self):
		super(PI_PM_Flex_Ratio_Basic_Enable_Test_Linux, self).__init__()
		self.name = "FLEX_RATIO_BASIC_ENABLE_LINUX" 
		self.targetlogfolder = "PI_PM_Flex_Ratio_Basic_Enable_Test_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "TurboMode=0x0, EETurboDisable=0x1, ProcessorFlexibleRatioOverrideEnable=0x1"
		self.run_ptu = False
		self.check_turbo_flag = False

	def _start(self):
		self.product_class = PI_PM_Flex_Ratio_Basic_Enable_Test_Linux_TestEngine
		return self

class PI_PM_Flex_Ratio_Basic_Enable_Test_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "This TestCase verifies processor frequency when Flex Ratio is enabled."

	def run_pi_pm_main(self):

		self.check_sut_os() 
		if self.cpu_type in ["GNR","SRF"]:
			self._tester.test_logger.log("Runninig the test on GNR")
			self.gnr_pmutil_frequency_calculator()
			self.set_reduced_speed(self.sse_freq_val)

			self._tester.test_logger.log("Checking the new changed flex ratio P1 frequency using pmutil")
			self.pmutil_cmd = "cd {}; ./pmutil_bin -r 0x194".format(self.app_pmutil_path)
			self._tester.test_logger.log("Pmutil command to check changed Flex raio P1 frequency is {}".format(self.pmutil_cmd))
			self.flex_freq = self._tester.sut_control.os_access.run_command(self.pmutil_cmd).combined_lines
			self._tester.test_logger.log("Flex Ratio P1 frequency from pmutil is {}".format(self.flex_freq[0]))
			
			self._tester.test_logger.log("Check if 16th bit from Flex Ratio P1 is set to 1 or not ")
			self.nth_bit = self.check_nth_bit(self.flex_freq[0],16) #need to check 16th bit
			if self.nth_bit == True:
				self._tester.test_logger.log("PASS : Bit [16] for Flex Ratio P1 frequency {} is set to 1 ".format(self.flex_freq[0]))   
			else:
				self._tester.test_logger.log("FAIL : Bit [16] is not set to 1")

			self._tester.test_logger.log("Check if Flex Ratio override is equal to the changed flex ratio P1 frequency ")
			self.pmutil_reduced_freq = int(self.flex_freq[0][3:5],16)
			self._tester.test_logger.log("Flex Ratio override from pmutil is {}".format(self.pmutil_reduced_freq))
			
			if self.pmutil_reduced_freq == self.flex_reduced_speed:
				self._tester.test_logger.log("PASS : Flex Ratio override from pmutil {} matches to the changed Flex Ratio P1 frequency {}".format(self.pmutil_reduced_freq,self.flex_reduced_speed))
			else:
				self._tester.test_logger.log("FAIL : Flex Ratio override from pmutil {}  does not match to the changed Flex Ratio P1 frequency {}".format(self.pmutil_reduced_freq,self.flex_reduced_speed))
	
		elif self.cpu_type =="SPR":
			self._tester.test_logger.log("Running the test on SPR....")
			self.frequency_calculator()
			self.set_reduced_speed(self.sse_freq_val)

		#start standalone script for triggering the SocWatch Tool
		self._tester.test_logger.log("Triggering {}_Testcase. Please wait for sometime to complete test".format(self._config.name))
		cmd = "python {dir}/{scr} --test {testname} --os {operatingsystem}  --bios_val {ssep1} --cpu {cp}".format(
			dir=self.pi_pm_app_path, 
			scr=self.target_script, 
			testname=self.name, 
			operatingsystem=self.operating_system, 
			ssep1=self.reduced_speed,
			cp = self.cpu_type)
		self.result = self._tester.sut_control.os_access.run_command(cmd, verify=False, retry=0)
		self._tester.test_logger.log("Standalone test details **********")
		self._tester.test_logger.log(str(self.result))
		self.collect_output_logs(self.result.combined_lines)

		#Log copy to host
		# output_logfile=self._tester.sut_control.os_access.run_command('cd {} && ls -t | head -n1'.format(self.pi_pm_applog_folder)).combined_lines
		# self.applogfile=output_logfile[0]
		# self.pipm_app_log= "{t}/{appfile}".format(t=self.pi_pm_applog_folder, appfile=self.applogfile)
		self._tester.test_logger.log("PIPM app log is:{}".format(self.pipm_app_log))
		self.test_logs.append(self.pipm_app_log)
		if self.cpu_type == "SPR":
			self.test_logs.append('{t}/SoCWatchOutput.csv'.format(t=self.pi_pm_applog_folder))
		elif self.cpu_type in ["GNR","SRF"]:
			self._tester.test_logger.log("PTU mon log is:{}".format(self.ptu_mon_log))
			self.test_logs.append(self.ptu_log_file)
	


	def check_nth_bit(self,str_hex, nth_bit):
		return (int(str_hex, 16) & 2 **(nth_bit - 1)) >> (nth_bit - 1) == 1

	def set_reduced_speed(self, sse_freq_val):
		self._tester.test_logger.log("SSE P1 frequency value from _sv_sockets is  {}MHZ".format(self.sse_freq_val))
		self._tester.test_logger.log("Set CPU Core Flex Ratio value below base P1 frequency")
		self.reduced_speed = int(int(self.sse_freq_val) - 200)
		self.flex_reduced_speed = int(self.reduced_speed/100)
		self.knob_val = hex(self.flex_reduced_speed)
		self.knob ='ProcessorFlexibleRatio={}'.format(self.knob_val)
		self._tester.test_logger.log("setting BIOS knob {} for Reduced CPU Core Flex Ratio".format(self.knob_val))
		self._tester.sut_control.set_bios_knob(self.knob)
		self._tester.tester_functions.ac_power_cycle()
		self.bios_knob_set=True
	
#######################################################################################################
#CRAUTO-10436
class PI_PM_Psys_Basic_Psys_Mode_Discovery_Primary_Skt0_2S_And_Primary_Skt0_Skt2_4S_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_Psys_Basic_Psys_Mode_Discovery_Primary_Skt0_2S_And_Primary_Skt0_Skt2_4S_Linux"}

	def __init__(self):
		super(PI_PM_Psys_Basic_Psys_Mode_Discovery_Primary_Skt0_2S_And_Primary_Skt0_Skt2_4S_Linux, self).__init__()
		self.name = "PSYS_BASIS_PSYS_MODE_DISCOVERY_PRIMARY_SKT0_2S_PRIMARY_SKT0_SKT2_4S_LINUX" 
		self.targetlogfolder = "PI_PM_Psys_Basic_Psys_Mode_Discovery_Primary_Skt0_2S_And_Primary_Skt0_Skt2_4S_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "PsysPowerDomain=0x1"
		self.bios_knob_set = True
		
	def _start(self):
		self.product_class = PI_PM_Psys_Basic_Psys_Mode_Discovery_Primary_Skt0_2S_And_Primary_Skt0_Skt2_4S_Linux_TestEngine
		return self

class PI_PM_Psys_Basic_Psys_Mode_Discovery_Primary_Skt0_2S_And_Primary_Skt0_Skt2_4S_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "With Socket0 set as the Primary Socket, verify Psys parameters (Min/Max PPL1, Min/Max PPl2, TW1, TW2) are set correctly when Psys mode enabled via BIOS Setup."
	
	def run_pi_pm_main(self):
		_sv_sockets = self._tester.sv_control.sv_sockets
		self.ppl1_max_val = []
		self.ppl2_max_val = []
		self.ppl1_min_val = []
		self.max_time_window = []
		self.plt_power_info = []

		self._tester.test_logger.log("Running PI_PM_Psys_Basic_Psys_Mode_Discovery_Primary_Skt0_2S_And_Primary_Skt0_Skt2_4S_Linux")
		
		self._tester.test_logger.log("Checking the Power Suppy Unit count from bmc terminal and set bios knob accordingly...")
		self.psulist = self._tester.sut_control.bmc_access.run_command("ipmitool sensor list | grep 'In Voltage'", verify=True).combined_lines
		self._tester.test_logger.log("The PSU available on this platform are : {}".format(self.psulist))
		self.output = self._tester.sut_control.bmc_access.run_command("ipmitool sensor list | grep -c 'In Voltage'", verify=True).combined_lines
		self.psu_count = int(self.output[0])
		self._tester.test_logger.log("The PSU Count is : {}".format(self.psu_count))
		if self.psu_count == 1:
			self.knob = 'PsysPowerLimitAndInfo=0x1'
		elif self.psu_count == 2:
			self.knob ='PsysPowerLimitAndInfo=0x3'

		self._tester.test_logger.log("Bios knob to set : {}".format(self.knob))
		self._tester.sut_control.set_bios_knob(self.knob)
		self._tester.tester_functions.ac_power_cycle()
		self.bios_knob_set=True     

		self._tester.test_logger.log("Verify Max PPL1, Min PPL1, Max PPL2, and Max Time Window Values by reading PLATFORM_POWER_INFO MSR")
		self.socket_count = int(self._frame.sv_control.socket_count)

		soc_count=0
		for socket in _sv_sockets:
			self._tester.test_logger.log("-------------------------Socket {}-------------------------".format(soc_count))
			ppl1_max = socket.uncore.punit.platform_power_info.max_ppl1_value.read()
			self._tester.test_logger.log("Maximum PPL1 value for Socket{} is: {}".format(soc_count, ppl1_max))
			self.ppl1_max_val.append(ppl1_max)

			ppl1_min = socket.uncore.punit.platform_power_info.min_ppl1_value.read()
			self._tester.test_logger.log("Minimum PPL1 value for Socket{} is : {}".format(soc_count, ppl1_min))
			self.ppl1_min_val.append(ppl1_min)

			ppl2_max = socket.uncore.punit.platform_power_info.max_ppl2_value.read()
			self._tester.test_logger.log("Maximum PPL2 value for Socket{} is : {}".format(soc_count, ppl2_max))
			self.ppl2_max_val.append(ppl2_max)

			max_time = socket.uncore.punit.platform_power_info.max_time_window.read()
			self._tester.test_logger.log("Maximum_time_window value for Socket{} is : {}".format(soc_count, max_time))
			self.max_time_window.append(max_time)

			plt_pwr_info = socket.uncore.punit.platform_power_info.read()
			self._tester.test_logger.log("The Platform power info for Socket{} is : {}".format(soc_count, plt_pwr_info))
			self.plt_power_info.append(plt_pwr_info)

			soc_count += 1
		self._tester.test_logger.log("-------------------------------------------------------------------")
		self._tester.test_logger.log("Max PPL1, Min PPL1, Max PPL2, and Max Time Window Values are recorded successfully")
		
		output = self._tester.sut_control.os_access.run_command("lscpu | grep Thread").combined_lines
		self.thread_per_core = int(output[0].split(':')[1])
		self._tester.test_logger.log("Threads per core is: {}".format(self.thread_per_core))
		if self.thread_per_core==1:
			numa_cpus_exp = r"(?<=NUMA node\d CPU\(s\):)(?:\s*)(\d+)(?:[,-]?)(\d+)?"
		else:
			numa_cpus_exp = r"(?<=NUMA node\d CPU\(s\):)(?:\s*)(\d+)(?:[,-]?)(\d+)(?:,?)(\d+)(?:-)(\d+)"

		numaoutput = self._tester.sut_control.os_access.run_command("lscpu | grep 'NUMA node0'").combined_lines
		numa_cpus_as_string = re.findall(numa_cpus_exp,numaoutput[0])
		self._tester.test_logger.log("NUMA Node output for CPU Cores are :{}".format(numa_cpus_as_string))
	

		if self.socket_count == 2:
			self.plt_power_soc0 = str(self.plt_power_info[0])[2:]
			self.plt_power_soc1 = str(self.plt_power_info[1])[2:]
			s0_numanode = int(numa_cpus_as_string[0][0])
			s1_numanode = (int(numa_cpus_as_string[0][1]) + 1)
			self.rdmsr_soc0 = self._tester.sut_control.os_access.run_command('cd {} && rdmsr -p {} 0x665'.format(self.msr_dir, s0_numanode)).combined_lines
			self.rdmsr_soc1 = self._tester.sut_control.os_access.run_command('cd {} && rdmsr -p {} 0x665'.format(self.msr_dir, s1_numanode)).combined_lines
			self._tester.test_logger.log("Socket0 rdmsr output is {}".format(self.rdmsr_soc0[0]))
			self._tester.test_logger.log("Socket1 rdmsr output is {}".format(self.rdmsr_soc1[0]))


			if (self.plt_power_soc0 == self.rdmsr_soc0[0]) and (self.plt_power_soc1 == self.rdmsr_soc1[0]):
				self._tester.test_logger.log("PASS: Platform_power_info value matched with the MSR read.")
			else:
				self._tester.exit_with_error("FAIL: Platform_power_info value S0:{}, S1:{} not matching with the MSR read value of S0:{}, S1:{}".format(self.plt_power_soc0, self.plt_power_soc1, self.rdmsr_soc0[0], self.rdmsr_soc1[0]))

		if self.socket_count == 4:
			self.plt_power_soc0 = str(self.plt_power_info[0])[2:]
			self.plt_power_soc1 = str(self.plt_power_info[1])[2:]
			self.plt_power_soc2 = str(self.plt_power_info[2])[2:]
			self.plt_power_soc3 = str(self.plt_power_info[3])[2:]
			s0_numanode = int(numa_cpus_as_string[0][0])
			s1_numanode = (int(numa_cpus_as_string[0][1]) + 1)
			s2_numanode = int(numa_cpus_as_string[0][2])
			s3_numanode = (int(numa_cpus_as_string[0][3]) + 1)
			self.rdmsr_soc0 = self._tester.sut_control.os_access.run_command('cd {} && rdmsr -p {} 0x665'.format(self.msr_dir, s0_numanode)).combined_lines
			self.rdmsr_soc1 = self._tester.sut_control.os_access.run_command('cd {} && rdmsr -p {} 0x665'.format(self.msr_dir, s1_numanode)).combined_lines
			self.rdmsr_soc2 = self._tester.sut_control.os_access.run_command('cd {} && rdmsr -p {} 0x665'.format(self.msr_dir, s2_numanode)).combined_lines
			self.rdmsr_soc3 = self._tester.sut_control.os_access.run_command('cd {} && rdmsr -p {} 0x665'.format(self.msr_dir, s3_numanode)).combined_lines
			self._tester.test_logger.log("Socket0 rdmsr output is {}".format(self.rdmsr_soc0[0]))
			self._tester.test_logger.log("Socket1 rdmsr output is {}".format(self.rdmsr_soc1[0]))
			self._tester.test_logger.log("Socket2 rdmsr output is {}".format(self.rdmsr_soc2[0]))
			self._tester.test_logger.log("Socket3 rdmsr output is {}".format(self.rdmsr_soc3[0]))
			if (self.plt_power_soc0 == self.rdmsr_soc0[0]) and (self.plt_power_soc1 == self.rdmsr_soc1[0]):
				self._tester.test_logger.log("PASS: Platform_power_info value matched with the MSR read for Socket 0 and Socket 1")
				
				if (self.plt_power_soc2 == self.rdmsr_soc2[0]) and (self.plt_power_soc3 == self.rdmsr_soc3[0]):
					self._tester.test_logger.log("PASS: Platform_power_info value matched with the MSR read for Socket 2 and Socket 3")
				else:
					self._tester.exit_with_error("FAIL: Platform_power_info value S2:{}, S3:{} not matching with the MSR read value of S2:{}, S3:{}".format(self.plt_power_soc2, self.plt_power_soc3, self.rdmsr_soc2[0], self.rdmsr_soc3[0]))

			else:
				self._tester.exit_with_error("FAIL: Platform_power_info value S0:{}, S1:{} not matching with the MSR read value of S0:{}, S1:{}".format(self.plt_power_soc0, self.plt_power_soc1, self.rdmsr_soc0[0], self.rdmsr_soc1[0]))

		
#######################################################################################################
#CRAUTO-10438

class PI_PM_Psys_Verify_Psys_Fuses_Set_Correctly_2S_4S_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_Psys_Verify_Psys_Fuses_Set_Correctly_2S_4S_Linux"}

	def __init__(self):
		super(PI_PM_Psys_Verify_Psys_Fuses_Set_Correctly_2S_4S_Linux, self).__init__()
		self.name = "PSYS_VERIFY_FUSES_SET_CORRECTLY_2S_4S_LINUX" 
		self.targetlogfolder = "PI_PM_Psys_Verify_Psys_Fuses_Set_Correctly_2S_4S_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "PsysPowerLimitCsrLock=0x0,PsysPowerInfoLock=0x0,PsysPowerLimitAndInfo=0x1,PsysPowerDomain=0x1"
		self.bios_knob_set = True
		
	def _start(self):
		self.product_class = PI_PM_Psys_Verify_Psys_Fuses_Set_Correctly_2S_4S_Linux_TestEngine
		return self

class PI_PM_Psys_Verify_Psys_Fuses_Set_Correctly_2S_4S_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "Check Psys-related fuses and compare values reported into PLATFORM_POWER_INFO, RAPL_LIMITS, ENERGY_STATUS, PERF_STATUS etc"
	
	def run_pi_pm_main(self):
		_sv_sockets = self._tester.sv_control.sv_sockets
		self.psys_enable = []
		self.fuse_punit_value = []
		
		self._tester.test_logger.log("Running PI_PM_Psys_Verify_Psys_Fuses_Set_Correctly_2S_4S_Linux")
		
		self._tester.test_logger.log("Verify the platform supports Psys by reading the Psys Enable fuse.")
		self.socket_count = int(self._frame.sv_control.socket_count)

		soc_count=0
		for socket in _sv_sockets:
			fuse_val = socket.tile0.fuses.load_fuse_ram()
			time.sleep(10)
			psys_enb = socket.tile0.fuses.punit.pcode_psys_enable

			self._tester.test_logger.log("punit.pcode_psys_enable value for Socket{} is : {}".format(soc_count, psys_enb))
			self.psys_enable.append(psys_enb)

			if psys_enb != 0x1:
				self._tester.exit_with_error("FAIL: Psys Enable fuse is not set. The Platform must be enabled for Psys.")
			else:
				self._tester.test_logger.log("PASS: Pcode_psys_enable value is successfully set. Psys is enabled.") 
			soc_count += 1  

		soc_count = 0
		for socket in _sv_sockets:
			long_clamp_dft = socket.tile0.fuses.punit.pcode_long_clamp_default
			long_clamp_lock = socket.tile0.fuses.punit.pcode_long_clamp_lock
			short_clamp_dft = socket.tile0.fuses.punit.pcode_short_clamp_default
			short_clamp_lock = socket.tile0.fuses.punit.pcode_short_clamp_lock
			# self._tester.test_logger.log("pcode_long_clamp_default value is : {}".format(long_clamp_dft))
			# self._tester.test_logger.log("pcode_long_clamp_lock value is : {}".format(long_clamp_lock))
			# self._tester.test_logger.log("pcode_short_clamp_default value is : {}".format(short_clamp_dft))
			# self._tester.test_logger.log("pcode_short_clamp_lock value is : {}".format(short_clamp_lock))

			self.fuse_punit_value.append(long_clamp_lock)
			self.fuse_punit_value.append(long_clamp_dft)
			self.fuse_punit_value.append(short_clamp_dft)
			self.fuse_punit_value.append(short_clamp_lock)

			self._tester.test_logger.log("Fuse_punit_values for pcode_long_clamp_default, pcode_long_clamp_lock, pcode_short_clamp_default and pcode_short_clamp_lock for Socket{} are : {}".format(soc_count, self.fuse_punit_value))

			if all(self.fuse_punit_value) == 0x1:
				self._tester.test_logger.log("PASS: Clamp_lock and Clamp_default values are verified successfully")
			else:
				self._tester.exit_with_error("FAIL: Clamp_lock and Clamp_default values are not 0x1. Please check logs for details.")
			soc_count += 1


#######################################################################################################
#CRAUTO-10440
class PI_PM_Psys_Verify_PLATFORM_RAPL_PERF_STATUS_MSR_Update_RAPL_Limit_2S_4S_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_Psys_Verify_PLATFORM_RAPL_PERF_STATUS_MSR_Update_RAPL_Limit_2S_4S_Linux"}

	def __init__(self):
		super(PI_PM_Psys_Verify_PLATFORM_RAPL_PERF_STATUS_MSR_Update_RAPL_Limit_2S_4S_Linux, self).__init__()
		self.name = "PSYS_VERIFY_PLATFORM_RAPL_PERF_STATUS_MSR_UPDATES_RAPL_LIMIT_2S_4S_LINUX" 
		self.targetlogfolder = "PI_PM_Psys_Verify_PLATFORM_RAPL_PERF_STATUS_MSR_Update_RAPL_Limit_2S_4S_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "PsysPowerLimitCsrLock=0x0,PsysPowerInfoLock=0x0,PsysPowerLimitAndInfo=0x1,PsysPowerDomain=0x1"
		self.bios_knob_set = True
		
	def _start(self):
		self.product_class = PI_PM_Psys_Verify_PLATFORM_RAPL_PERF_STATUS_MSR_Update_RAPL_Limit_2S_4S_Linux_TestEngine
		return self

class PI_PM_Psys_Verify_PLATFORM_RAPL_PERF_STATUS_MSR_Update_RAPL_Limit_2S_4S_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "This test case ensures the PLATFORM_RAPL_PERF_STATUS MSR is updated correctly upon a platform RAPL limit."
	
	def run_pi_pm_main(self):
		_sv_sockets = self._tester.sv_control.sv_sockets
		self.socket_count = int(self._frame.sv_control.socket_count)
		self.error_flag = False
		self._tester.test_logger.log("PI_PM_Psys_Verify_PLATFORM_RAPL_PERF_STATUS_MSR_Update_RAPL_Limit_2S_4S")
		
		for socket in _sv_sockets:
			self.pl1_original_val = socket.uncore.punit.platform_rapl_limit_cfg
			self._tester.test_logger.log("The Original PPL1 value is {}".format(self.pl1_original_val))
			self._tester.test_logger.log("Setting the PPL1 to 600W / 0x63a30026612c0")
			socket.uncore.punit.platform_rapl_limit_cfg = 0x63a30026612c0
			read_val_pretest = socket.uncore.punit.platform_rapl_limit_cfg.read()
			self._tester.test_logger.log("PPL1 is set to {}".format(read_val_pretest))

		self.wl_thread = thread_with_trace(target=self.run_ptu_workload, args=("ct3",), name="ptu") 
		self._tester.test_logger.log("Running PTU WL for Test PTU ct3 with cpu cpu_utilization as 80")
		self.wl_thread.start()
		time.sleep(30)
		#reading plat power and reducing by 30% and writing new value
		self.power_plt_energy_status_value = self.run_platform_power_consumption()
		self.reduced_platform_power=self.power_plt_energy_status_value * 0.7
		for socket in _sv_sockets:
			socket.uncore.punit.platform_rapl_limit_cfg.ppl1 = int(self.reduced_platform_power * 8)

		self._tester.test_logger.log("Checking the Platform RAPL Performance Status increment during WL done...")

		if self._tester.manager.cpu_project == CPU_PROJECT.SPR:
			if self.socket_count == 2:
				for i in range(1,6):
					soc_count=0
					for socket in _sv_sockets:
						retvalue1 = socket.uncore.punit.platform_rapl_perf_status
						self._tester.test_logger.log("platform_rapl_perf_status value for Socket{} is : {}".format(soc_count, retvalue1))
						time.sleep(10)
						retvalue2 = socket.uncore.punit.platform_rapl_perf_status
						self._tester.test_logger.log("platform_rapl_perf_status value for Socket{} is : {}".format(soc_count, retvalue2))

						if int(retvalue2) > int(retvalue1):
							self._tester.test_logger.log("PASS: Platform_rapl_perf_status values are incrementing while PTU Workload is running")
						else:
							self._tester.test_logger.log("FAIL: Platform_rapl_perf_status values are not incrementing while PTU Workload is running.")

						soc_count += 1
				

			elif self.socket_count == 4:
				for i in range(1,6):
					soc_count=2
					for socket in _sv_sockets:
						retvalue1 = socket.uncore.punit.platform_rapl_perf_status
						self._tester.test_logger.log("platform_rapl_perf_status value for Socket{} is : {}".format(soc_count, retvalue1))
						time.sleep(10)
						retvalue2 = socket.uncore.punit.platform_rapl_perf_status
						self._tester.test_logger.log("platform_rapl_perf_status value for Socket{} is : {}".format(soc_count, retvalue2))

						if int(retvalue2) > int(retvalue1):
							self._tester.test_logger.log("PASS: Platform_rapl_perf_status values are incrementing while PTU Workload is running")
						else:
							self._tester.test_logger.log("FAIL: Platform_rapl_perf_status values are not incrementing while PTU Workload is running.")

						soc_count += 1

				
		elif self._tester.manager.cpu_project == CPU_PROJECT.GNR:
			if self.socket_count == 2:
				for i in range(1,6):
					soc_count=0
					for socket in _sv_sockets:
						retvalue1 = socket.io0.uncore.punit.ptpcioregs.ptpcioregs.platform_rapl_perf_status
						self._tester.test_logger.log("platform_rapl_perf_status value for Socket{} is : {}".format(soc_count, retvalue1))
						time.sleep(10)
						retvalue2 = socket.io0.uncore.punit.ptpcioregs.ptpcioregs.platform_rapl_perf_status
						self._tester.test_logger.log("platform_rapl_perf_status value for Socket{} is : {}".format(soc_count, retvalue2))

						if int(retvalue2) > int(retvalue1):
							self._tester.test_logger.log("PASS: Platform_rapl_perf_status values are incrementing while PTU Workload is running")
						else:
							self._tester.test_logger.log("FAIL: Platform_rapl_perf_status values are not incrementing while PTU Workload is running.")

						soc_count += 1
				

			elif self.socket_count == 4:
				for i in range(1,6):
					soc_count=2
					for socket in _sv_sockets:
						retvalue1 = socket.io0.uncore.punit.ptpcioregs.ptpcioregs.platform_rapl_perf_status
						self._tester.test_logger.log("platform_rapl_perf_status value for Socket{} is : {}".format(soc_count, retvalue1))
						time.sleep(10)
						retvalue2 = socket.io0.uncore.punit.ptpcioregs.ptpcioregs.platform_rapl_perf_status
						self._tester.test_logger.log("platform_rapl_perf_status value for Socket{} is : {}".format(soc_count, retvalue2))

						if int(retvalue2) > int(retvalue1):
							self._tester.test_logger.log("PASS: Platform_rapl_perf_status values are incrementing while PTU Workload is running")
						else:
							self._tester.test_logger.log("FAIL: Platform_rapl_perf_status values are not incrementing while PTU Workload is running.")

						soc_count += 1


				
		self.wl_thread.kill()
		time.sleep(10)
		self.stop_ptu()
		time.sleep(30)

		self._tester.test_logger.log("Checking the Platform RAPL Performance Status static during no WL run...")
		#checking for spr and gnr rapl perf status static check

		if self._tester.manager.cpu_project == CPU_PROJECT.SPR:
			if self.socket_count == 2:
				for i in range(1,6):
					soc_count=0
					for socket in _sv_sockets:
						retvalue3 = socket.uncore.punit.platform_rapl_perf_status
						self._tester.test_logger.log("platform_rapl_perf_status value for Socket{} is : {}".format(soc_count, retvalue1))
						time.sleep(10)
						retvalue4 = socket.uncore.punit.platform_rapl_perf_status
						self._tester.test_logger.log("platform_rapl_perf_status value for Socket{} is : {}".format(soc_count, retvalue2))

						if int(retvalue3) == int(retvalue4):
							self._tester.test_logger.log("PASS: Platform_rapl_perf_status values are static when PTU Workload is stopped")
						else:
							self._tester.test_logger.log("FAIL: Platform_rapl_perf_status values are not static when PTU Workload is stopped.")

						soc_count += 1

				
			elif self.socket_count == 4:
				for i in range(1,6):
					soc_count=2
					for socket in _sv_sockets:
						retvalue3 = socket.uncore.punit.platform_rapl_perf_status
						self._tester.test_logger.log("platform_rapl_perf_status value for Socket{} is : {}".format(soc_count, retvalue1))
						time.sleep(10)
						retvalue4 = socket.uncore.punit.platform_rapl_perf_status
						self._tester.test_logger.log("platform_rapl_perf_status value for Socket{} is : {}".format(soc_count, retvalue2))

						if int(retvalue3) == int(retvalue4):
							self._tester.test_logger.log("PASS: Platform_rapl_perf_status values are static when PTU Workload is stopped")
						else:
							self._tester.test_logger.log("FAIL: Platform_rapl_perf_status values are not static when PTU Workload is stopped.")

						soc_count += 1
				

		elif self._tester.manager.cpu_project == CPU_PROJECT.GNR:
			if self.socket_count == 2:
				for i in range(1,6):
					soc_count=0
					for socket in _sv_sockets:
						retvalue3 = socket.io0.uncore.punit.ptpcioregs.ptpcioregs.platform_rapl_perf_status
						self._tester.test_logger.log("platform_rapl_perf_status value for Socket{} is : {}".format(soc_count, retvalue1))
						time.sleep(10)
						retvalue4 = socket.io0.uncore.punit.ptpcioregs.ptpcioregs.platform_rapl_perf_status
						self._tester.test_logger.log("platform_rapl_perf_status value for Socket{} is : {}".format(soc_count, retvalue2))

						if int(retvalue3) == int(retvalue4):
							self._tester.test_logger.log("PASS: Platform_rapl_perf_status values are static when PTU Workload is stopped")
						else:
							self._tester.test_logger.log("FAIL: Platform_rapl_perf_status values are not static when PTU Workload is stopped.")

						soc_count += 1
				

			elif self.socket_count == 4:
				for i in range(1,6):
					soc_count=2
					for socket in _sv_sockets:
						retvalue3 = socket.io.uncore.punit.ptpcioregs.ptpcioregs.platform_rapl_perf_status
						self._tester.test_logger.log("platform_rapl_perf_status value for Socket{} is : {}".format(soc_count, retvalue1))
						time.sleep(10)
						retvalue4 = socket.io.uncore.punit.ptpcioregs.ptpcioregs.platform_rapl_perf_status
						self._tester.test_logger.log("platform_rapl_perf_status value for Socket{} is : {}".format(soc_count, retvalue2))

						if int(retvalue3) == int(retvalue4):
							self._tester.test_logger.log("PASS: Platform_rapl_perf_status values are static when PTU Workload is stopped")
						else:
							self._tester.test_logger.log("FAIL: Platform_rapl_perf_status values are not static when PTU Workload is stopped.")

						soc_count += 1
				


		self._tester.test_logger.log("The Test is completed")
		if self._tester.manager.cpu_project == CPU_PROJECT.SPR:
			self._tester.test_logger.log("So setting the PPL1 back to original value")          
			for socket in _sv_sockets:
				self._tester.test_logger.log("The Original PPL1 value is {}".format(self.pl1_original_val))
				socket.uncore.punit.package_rapl_limit_cfg = self.pl1_original_val
				time.sleep(10)
				read_val_posttest = socket.uncore.punit.package_rapl_limit_cfg.read()
				self._tester.test_logger.log("The PPL1 is set back to {}".format(read_val_posttest))

	def run_pi_pm_post(self):
		pass



#######################################################################################################

#CRAUTO-10284
class PI_PM_AVX2_AVX512_Turbo_Disabled_Base_Frequency_Linpack_Test_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_AVX2_AVX512_Turbo_Disabled_Base_Frequency_Linpack_Test_Linux"}

	def __init__(self):
		super(PI_PM_AVX2_AVX512_Turbo_Disabled_Base_Frequency_Linpack_Test_Linux, self).__init__()
		self.name = "AVX2_AVX512_TURBO_DISABLED_BASE_FREQUENCY_LINPACK_LINUX" 
		self.targetlogfolder = "PI_PM_AVX2_AVX512_Turbo_Disabled_Base_Frequency_Linpack_Test_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "TurboMode=0x0"
		self.run_ptu = False
		self.check_turbo_flag = False
		self.bios_knob_set = False
	
	def _start(self):
		self.product_class = PI_PM_AVX2_AVX512_Turbo_Disabled_Base_Frequency_Linpack_Test_Linux_TestEngine
		return self

class PI_PM_AVX2_AVX512_Turbo_Disabled_Base_Frequency_Linpack_Test_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "This Test Case verifies processor AVX2 and AVX512 Base frequency by running optimized linpack test."
	
	def run_pi_pm_main(self):
		self._tester.test_logger.log("Running the test on SPR....")
		#calculating avx2,avx512 and sse act from pysv
		self.frequency_calculator() 
		self._tester.test_logger.log("AVX2,AVX512 and SSE ACT frequency values from _sv_sockets are {}MHZ,{}MHZ and {}MHZ".format(self.avx2_freq_val,self.avx512_freq_val,self.sse_act_val))

		#avx2 and avx512mailbox frequency value from pmutil
		self.spr_pmutil_calculator()
		#comparing AVX2 frequency from OS2P and pysv
		self._tester.test_logger.log("Comparing AVX2 Frequency value from OS2P Mailbox and pysv ")
		if self.avx2_freq_val == self.avx2_p1:
			self._tester.test_logger.log("PASS: AVX2 Frequency value from OS2P Mailbox {} and pysv {} are equal! ".format(self.avx2_p1,self.avx2_freq_val))
		else:
			self._tester.exit_with_error("FAIL: AVX2 Frequency value from OS2P Mailbox {} and pysv {} are not equal! ".format(self.avx2_p1,self.avx2_freq_val))
		
		#comparing AVX512 frequency from OS2P and pysv
		self._tester.test_logger.log("Comparing AVX512 Frequency value from OS2P Mailbox and pysv ")
		if self.avx512_freq_val == self.avx512_p1:
			self._tester.test_logger.log("PASS: AVX512 Frequency value from OS2P Mailbox {} and pysv {} are equal! ".format(self.avx512_p1,self.avx512_freq_val))
		else:
			self._tester.exit_with_error("FAIL: AVX512 Frequency value from OS2P Mailbox {} and pysv {} are not equal! ".format(self.avx512_p1,self.avx512_freq_val))

		self.check_sut_os()

		#start standalone script
		self._tester.test_logger.log("Triggering {}_Testcase. Please wait for sometime to complete test".format(self._config.name))
		#cmd = "python {dir}/{scr} --test {testname} --os {operatingsystem} ".format(dir=self.pi_pm_app_path, scr=self.target_script, testname=self.name,operatingsystem=self.operating_system,qdfvalue=self.qdf_value)
		cmd = "chmod -R 777 {dir}".format(dir=self.pi_pm_app_path)
		self.result = self._tester.sut_control.os_access.run_command(cmd, verify=False, retry=0)
		cmd = "cd {dir} && python {dir}/{scr} --test {testname} --os {operatingsystem}  --avx2_freq {af2} --avx512_freq {af512} --sse_act_freq {ssef}".format(
			dir=self.pi_pm_app_path, 
			scr=self.target_script, 
			testname=self.name,
			operatingsystem=self.operating_system,
			af2=self.avx2_freq_val,
			af512 = self.avx512_freq_val,
			ssef=self.sse_act_val)

		self.result = self._tester.sut_control.os_access.run_command(cmd, verify=False, retry=0)
		self._tester.test_logger.log("Standalone test details **********")
		self._tester.test_logger.log(str(self.result))

		#Log copy to host
		self.collect_output_logs(self.result.combined_lines)
		self._tester.test_logger.log("PIPM app log is:{}".format(self.pipm_app_log))
		self.test_logs.append(self.pipm_app_log)
		self.test_logs.append('{t}/SoCWatchOutput.csv'.format(t=self.pi_pm_applog_folder))
		
		
############################################################################################################
#CRAUTO-10183
class PI_PM_AVX2_AVX512_Turbo_Enabled_Base_Frequency_Linpack_Test_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_AVX2_AVX512_Turbo_Enabled_Base_Frequency_Linpack_Test_Linux"}

	def __init__(self):
		super(PI_PM_AVX2_AVX512_Turbo_Enabled_Base_Frequency_Linpack_Test_Linux, self).__init__()
		self.name = "AVX2_AVX512_TURBO_ENABLED_BASE_FREQUENCY_LINPACK_LINUX" 
		self.targetlogfolder = "PI_PM_AVX2_AVX512_Turbo_Enabled_Base_Frequency_Linpack_Test_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "TurboMode=0x1"
		self.run_ptu = False
		self.check_turbo_flag = False
		self.bios_knob_set = False
	
	def _start(self):
		self.product_class = PI_PM_AVX2_AVX512_Turbo_Enabled_Base_Frequency_Linpack_Test_Linux_TestEngine
		return self

class PI_PM_AVX2_AVX512_Turbo_Enabled_Base_Frequency_Linpack_Test_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "This Test Case verifies processor AVX2 and AVX512 Base frequency by running optimized linpack test."
	
	def run_pi_pm_main(self):
		self._tester.test_logger.log("Running the test on SPR....")
		#calculating avx2,avx512 and sse act from pysv
		self.frequency_calculator() 
		self._tester.test_logger.log("AVX2,AVX512 and SSE ACT frequency values from _sv_sockets are {}MHZ,{}MHZ and {}MHZ".format(self.avx2_freq_val,self.avx512_freq_val,self.sse_act_val))
		self.spr_pmutil_calculator()
		#comparing AVX2 frequency from OS2P and pysv
		self._tester.test_logger.log("Comparing AVX2 Frequency value from OS2P Mailbox and pysv ")
		if self.avx2_freq_val == self.avx2_p1:
			self._tester.test_logger.log("PASS: AVX2 Frequency value from OS2P Mailbox {} and pysv {} are equal! ".format(self.avx2_p1,self.avx2_freq_val))
		else:
			self._tester.exit_with_error("FAIL: AVX2 Frequency value from OS2P Mailbox {} and pysv {} are not equal! ".format(self.avx2_p1,self.avx2_freq_val))
		
		#comparing AVX512 frequency from OS2P and pysv
		self._tester.test_logger.log("Comparing AVX512 Frequency value from OS2P Mailbox and pysv ")
		if self.avx512_freq_val == self.avx512_p1:
			self._tester.test_logger.log("PASS: AVX512 Frequency value from OS2P Mailbox {} and pysv {} are equal! ".format(self.avx512_p1,self.avx512_freq_val))
		else:
			self._tester.exit_with_error("FAIL: AVX512 Frequency value from OS2P Mailbox {} and pysv {} are not equal! ".format(self.avx512_p1,self.avx512_freq_val))
		
		self.check_sut_os()

		#start standalone script
		self._tester.test_logger.log("Triggering {}_Testcase. Please wait for sometime to complete test".format(self._config.name))
		cmd = "chmod -R 777 {dir}".format(dir=self.pi_pm_app_path)
		self.result = self._tester.sut_control.os_access.run_command(cmd, verify=False, retry=0)
		cmd = "cd {dir} && python {dir}/{scr} --test {testname} --os {operatingsystem}  --avx2_freq {af2} --avx512_freq {af512} --sse_act_freq {ssef}".format(
			dir=self.pi_pm_app_path, 
			scr=self.target_script, 
			testname=self.name,
			operatingsystem=self.operating_system,
			af2=self.avx2_freq_val,
			af512 = self.avx512_freq_val,
			ssef=self.sse_act_val)

		self.result = self._tester.sut_control.os_access.run_command(cmd, verify=False, retry=0)
		self._tester.test_logger.log("Standalone test details **********")
		self._tester.test_logger.log(str(self.result))

		#Log copy to host
		self.collect_output_logs(self.result.combined_lines)
		self._tester.test_logger.log("PIPM app log is:{}".format(self.pipm_app_log))
		self.test_logs.append(self.pipm_app_log)
		self.test_logs.append('{t}/SoCWatchOutput.csv'.format(t=self.pi_pm_applog_folder))

# #################################################################################################
#######################################################################################################

#CRAUTO-10182
class PI_PM_SSE_Turbo_Enabled_Base_Frequency_Linpack_Test_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_SSE_Turbo_Enabled_Base_Frequency_Linpack_Test_Linux"}

	def __init__(self):
		super(PI_PM_SSE_Turbo_Enabled_Base_Frequency_Linpack_Test_Linux, self).__init__()
		self.name = "SSE_TURBO_ENABLED_BASE_FREQUENCY_LINPACK_LINUX" 
		self.targetlogfolder = "PI_PM_SSE_Turbo_Enabled_Base_Frequency_Linpack_Test_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "TurboMode=0x1"
		self.run_ptu = False
		self.check_turbo_flag = False
		self.bios_knob_set = False
	
	def _start(self):
		self.product_class = PI_PM_SSE_Turbo_Enabled_Base_Frequency_Linpack_Test_Linux_TestEngine
		return self

class PI_PM_SSE_Turbo_Enabled_Base_Frequency_Linpack_Test_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "This Test Case verifies processor SSE Base frequency by running optimized linpack test."
	
	def run_pi_pm_main(self):
		self._tester.test_logger.log("Running the test on SPR....")
		#calculating sse P1 and sse act from pysv
		self.frequency_calculator()
		self.spr_pmutil_calculator()
		#comparing SSE P1 frequency from OS2P and pysv
		self._tester.test_logger.log("Comparing SSE P1 Frequency value from OS2P Mailbox and pysv ")
		if self.sse_freq_val == self.sse_p1:
			self._tester.test_logger.log("PASS: SSE P1 Frequency value from OS2P Mailbox {} and pysv {} are equal! ".format(self.sse_p1,self.sse_freq_val))
		else:
			self._tester.exit_with_error("FAIL: SSE P1 Frequency value from OS2P Mailbox {} and pysv {} are not equal! ".format(self.sse_p1,self.sse_freq_val))

		self.check_sut_os()

		#start standalone script
		self._tester.test_logger.log("Triggering {}_Testcase. Please wait for sometime to complete test".format(self._config.name))
		cmd = "chmod -R 777 {dir}".format(dir=self.pi_pm_app_path)
		self.result = self._tester.sut_control.os_access.run_command(cmd, verify=False, retry=0)
		cmd = "cd {dir} && python {dir}/{scr} --test {testname} --os {operatingsystem}  --sse_p1_freq {ssep1} --sse_act_freq {ssef}".format(
			dir=self.pi_pm_app_path, 
			scr=self.target_script, 
			testname=self.name,
			operatingsystem=self.operating_system,
			ssep1=self.sse_freq_val,
			ssef=self.sse_act_val)

		self.result = self._tester.sut_control.os_access.run_command(cmd, verify=False, retry=0)
		self._tester.test_logger.log("Standalone test details **********")
		self._tester.test_logger.log(str(self.result))

		#Log copy to host
		self.collect_output_logs(self.result.combined_lines)
		self._tester.test_logger.log("PIPM app log is:{}".format(self.pipm_app_log))
		self.test_logs.append(self.pipm_app_log)
		self.test_logs.append('{t}/SoCWatchOutput.csv'.format(t=self.pi_pm_applog_folder))

		
############################################################################################################
#######################################################################################################

#CRAUTO-10283
class PI_PM_SSE_Turbo_Disabled_Base_Frequency_Linpack_Test_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_SSE_Turbo_Disabled_Base_Frequency_Linpack_Test_Linux"}

	def __init__(self):
		super(PI_PM_SSE_Turbo_Disabled_Base_Frequency_Linpack_Test_Linux, self).__init__()
		self.name = "SSE_TURBO_DISABLED_BASE_FREQUENCY_LINPACK_LINUX" 
		self.targetlogfolder = "PI_PM_SSE_Turbo_Disabled_Base_Frequency_Linpack_Test_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "TurboMode=0x0"
		self.run_ptu = False
		self.check_turbo_flag = False
		self.bios_knob_set = False
	
	def _start(self):
		self.product_class = PI_PM_SSE_Turbo_Enabled_Base_Frequency_Linpack_Test_Linux_TestEngine
		return self

class PI_PM_SSE_Turbo_Disabled_Base_Frequency_Linpack_Test_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "This Test Case verifies processor SSE Base frequency by running optimized linpack test."
	
	def run_pi_pm_main(self):
		self._tester.test_logger.log("Running the test on SPR....")
		#calculating sse P1 and sse act from pysv
		self.frequency_calculator() 
		self._tester.test_logger.log("SSE P1 and SSE ACT frequency values from _sv_sockets are {}MHZ and {}MHZ".format(self.sse_freq_val,self.sse_act_val))
		self.spr_pmutil_calculator()
		self._tester.test_logger.log("SSE Frequency value from OS2P Mailbox is {}MHZ".format(self.sse_p1))

		#comparing SSE P1 frequency from OS2P and pysv
		self._tester.test_logger.log("Comparing SSE P1 Frequency value from OS2P Mailbox and pysv ")
		if self.sse_freq_val == self.sse_p1:
			self._tester.test_logger.log("PASS: SSE P1 Frequency value from OS2P Mailbox {} and pysv {} are equal! ".format(self.sse_p1,self.sse_freq_val))
		else:
			self._tester.exit_with_error("FAIL: SSE P1 Frequency value from OS2P Mailbox {} and pysv {} are not equal! ".format(self.sse_p1,self.sse_freq_val))

		self.check_sut_os()
	
		#start standalone script
		self._tester.test_logger.log("Triggering {}_Testcase. Please wait for sometime to complete test".format(self._config.name))
		#cmd = "python {dir}/{scr} --test {testname} --os {operatingsystem} ".format(dir=self.pi_pm_app_path, scr=self.target_script, testname=self.name,operatingsystem=self.operating_system,qdfvalue=self.qdf_value)
		cmd = "chmod -R 777 {dir}".format(dir=self.pi_pm_app_path)
		self.result = self._tester.sut_control.os_access.run_command(cmd, verify=False, retry=0)
		cmd = "cd {dir} && python {dir}/{scr} --test {testname} --os {operatingsystem}  --sse_p1_freq {ssep1} --sse_act_freq {ssef}".format(
			dir=self.pi_pm_app_path, 
			scr=self.target_script, 
			testname=self.name,
			operatingsystem=self.operating_system,
			ssep1=self.sse_freq_val,
			ssef=self.sse_act_val)

		self.result = self._tester.sut_control.os_access.run_command(cmd, verify=False, retry=0)
		self._tester.test_logger.log("Standalone test details **********")
		self._tester.test_logger.log(str(self.result))

		#Log copy to host
		self.collect_output_logs(self.result.combined_lines)
		self._tester.test_logger.log("PIPM app log is:{}".format(self.pipm_app_log))
		self.test_logs.append(self.pipm_app_log)
		self.test_logs.append('{t}/SoCWatchOutput.csv'.format(t=self.pi_pm_applog_folder))

		
############################################################################################################
#CRAUTO-9530
class PI_PM_TurboBoost_SingleCoreValidation_Test_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_TurboBoost_SingleCoreValidation_2S_4S_Test_Linux"}

	def __init__(self):
		super(PI_PM_TurboBoost_SingleCoreValidation_Test_Linux, self).__init__()
		self.name = "TURBOBOOST_SINGLE_CORE_VALIDATION_LINUX" 
		self.targetlogfolder = "PI_PM_TurboBoost_SingleCoreValidation_Test_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "TurboMode=0x1" 
		self.run_ptu = False
		self.check_turbo_flag = False
		self.bios_knob_set = False
		self.test_step = 0

	def _start(self):
		self.product_class = PI_PM_TurboBoost_SingleCoreValidation_Test_Linux_TestEngine
		return self

############################################################################################################
#CRAUTO-13780
class PI_PM_TurboBoost_SingleCore_SSE_Test_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_TurboBoost_SingleCore_SSE_Test_Linux"}

	def __init__(self):
		super(PI_PM_TurboBoost_SingleCore_SSE_Test_Linux, self).__init__()
		self.name = "TURBOBOOST_SINGLE_CORE_SSE_LINUX" 
		self.targetlogfolder = "PI_PM_TurboBoost_SingleCore_SSE_Test_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "TurboMode=0x1" 
		self.bios_knob_set = False
		self.test_step = 1

	def _start(self):
		self.product_class = PI_PM_TurboBoost_SingleCoreValidation_Test_Linux_TestEngine
		return self

############################################################################################################
#CRAUTO-13781
class PI_PM_TurboBoost_SingleCore_AVX2_Test_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_TurboBoost_SingleCore_AVX2_Test_Linux"}

	def __init__(self):
		super(PI_PM_TurboBoost_SingleCore_AVX2_Test_Linux, self).__init__()
		self.name = "TURBOBOOST_SINGLE_CORE_AVX2_LINUX" 
		self.targetlogfolder = "PI_PM_TurboBoost_SingleCore_AVX2_test_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "TurboMode=0x1" 
		self.bios_knob_set = False
		self.test_step = 2

	def _start(self):
		self.product_class = PI_PM_TurboBoost_SingleCoreValidation_Test_Linux_TestEngine
		return self
############################################################################################################
#CRAUTO-13782
class PI_PM_TurboBoost_SingleCore_AVX512_Test_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_TurboBoost_SingleCore_AVX512_Test_Linux"}

	def __init__(self):
		super(PI_PM_TurboBoost_SingleCore_AVX512_Test_Linux, self).__init__()
		self.name = "TURBOBOOST_SINGLE_CORE_AVX512_LINUX" 
		self.targetlogfolder = "PI_PM_TurboBoost_SingleCore_AVX512_Test_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "TurboMode=0x1" 
		self.bios_knob_set = False
		self.test_step = 3

	def _start(self):
		self.product_class = PI_PM_TurboBoost_SingleCoreValidation_Test_Linux_TestEngine
		return self

##################################################################################################################
class PI_PM_TurboBoost_SingleCoreValidation_Test_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "Collect the frequency of CPU and observe whether it meets the requirements"

	def run_pi_pm_main(self):
		self.test_step = self._config.test_step
		self._tester.test_logger.log("*********************************Test step is {} : Running {} Test******************************".format(self._config.test_step,self.name))
		self.get_available_bitmap()
		self.init_corecount=True
		self.bitmask_singlecore_calculation(self.socket_value,self.init_corecount)
		self._tester.test_logger.log("Final bitmask per socket is {}".format(self.final_dict))
		
		self.socket_count = int(self._frame.sv_control.socket_count)
		self._tester.test_logger.log("Current Socket Count is : {}".format(self.socket_count))
		
		if self.socket_count == 2:
			self.socket0_knobvalue=self.final_dict[0]
			self.socket1_knobvalue=self.final_dict[1]
			self.knob ='CoreDisableMask_0={} , CoreDisableMask_1={}'.format(self.socket0_knobvalue,self.socket1_knobvalue)
		elif self.socket_count == 4:
			self.socket0_knobvalue=self.final_dict[0]
			self.socket1_knobvalue=self.final_dict[1]
			self.socket2_knobvalue=self.final_dict[2]
			self.socket3_knobvalue=self.final_dict[3]
			self.knob ='CoreDisableMask_0={} , CoreDisableMask_1={}, CoreDisableMask_2={} , CoreDisableMask_3={}'.format(self.socket0_knobvalue,self.socket1_knobvalue, self.socket2_knobvalue, self.socket3_knobvalue)
		self._tester.test_logger.log("Bios knob to set : {}".format(self.knob))
		self._tester.sut_control.set_bios_knob(self.knob)
		self._tester.tester_functions.ac_power_cycle()
		self.bios_knob_set=True
		self.get_disable_bitmap()
		self.init_corecount=False
		self.bitmask_singlecore_calculation(self.socket_value,self.init_corecount)
		if self.decremented_core_count == 1:
			self._tester.test_logger.log("Successfully with single core count using BitMap")
		else:
			self._tester.exit_with_error("FAIL: The single core count didnt match")

		if self.cpu_type in ["GNR","SRF"]:
			self._tester.test_logger.log("Running the test on GNR....")
			#calculating sse P1 and sse act from pmutil
			self.gnr_pmutil_frequency_calculator()
		elif self.cpu_type =="SPR":
			self._tester.test_logger.log("Running the test on SPR....")
			#calculating sse P1 and sse act from pysv
			self.frequency_calculator() 
		
		self._tester.test_logger.log("Frequency values are as follow : SSE bin Bucket0 :{}MHZ , AVX2 bin Bucket0 :{}MHZ, AVX512 bin Bucket0 :{}MHZ, TMUL bin bucket0 : {}MHZ from _sv_sockets".format(self.sse_bin_bucket0,self.avx2_bin_bucket0,self.avx512_bin_bucket0,self.tmul_bin_bucket0))
	
		self.check_sut_os()
		
		#start standalone script
		self._tester.test_logger.log("Triggering {}_Testcase. Please wait for sometime to complete test".format(self._config.name))
		cmd = "python {dir}/{scr} --test {testname} --os {operatingsystem} --sse_bucket0_freq {ssef} --avx2_bucket0_freq {af2} --avx512_bucket0_freq {af512} --tmul_bucket0_freq {tmulf} --test_step {ts} ".format(
			dir=self.pi_pm_app_path, 
			scr=self.target_script, 
			testname=self.name,
			operatingsystem=self.operating_system,
			ssef = self.sse_bin_bucket0,
			af2=self.avx2_bin_bucket0,
			af512 = self.avx512_bin_bucket0,
			tmulf = self.tmul_bin_bucket0,
			ts = self.test_step)
		
		self.result = self._tester.sut_control.os_access.run_command(cmd, verify=False, retry=0)
		self._tester.test_logger.log("Standalone test details **********")
		self._tester.test_logger.log(str(self.result))
		self.collect_output_logs(self.result.combined_lines)

		#Log copy to host
		# output_logfile=self._tester.sut_control.os_access.run_command('cd {} && ls -t | head -n1'.format(self.pi_pm_applog_folder)).combined_lines
		# self.applogfile=output_logfile[0]
		# self.pipm_app_log= "{t}/{appfile}".format(t=self.pi_pm_applog_folder, appfile=self.applogfile)
		self._tester.test_logger.log("PIPM app log is:{}".format(self.pipm_app_log))
		self.test_logs.append(self.pipm_app_log)
		if self.test_step == 0:
			self.test_logs.append('{t}/SoCWatchOutput.csv'.format(t=self.pi_pm_applog_folder))
		
		elif self.test_step == 1 or self.test_step == 2 or self.test_step == 3:
			self._tester.test_logger.log("PTU Monitor app log is :{}".format(self.ptu_log_file))
			self.test_logs.append(self.ptu_log_file)
		
		self.copy_pi_pm_logs()
		self.pipm_parse_log(self.pipm_app_log)

		if self.bios_knob_set:
			self._tester.test_logger.log("Reverting BitMap Bios Knobs to default.")
			self._tester.sut_control.reset_bios_knob()
			self._tester.tester_functions.ac_power_cycle()

############################################################################################################
#######################################################################################################
#CRAUTO-10565
class PI_PM_Psys_Basic_Psys_Mode_Discovery_Peci_Primary_Skt0_2S_And_Primary_Skt0_Skt2_4S_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_Psys_Basic_Psys_Mode_Discovery_Peci_Primary_Skt0_2S_And_Primary_Skt0_Skt2_4S_Linux"}

	def __init__(self):
		super(PI_PM_Psys_Basic_Psys_Mode_Discovery_Peci_Primary_Skt0_2S_And_Primary_Skt0_Skt2_4S_Linux, self).__init__()
		self.name = "PSYS_BASIC_PSYS_MODE_DISCOVERY_PECI_PRIMARY_SKT0_2S_PRIMARY_SKT0_SKT2_4S_LINUX" 
		self.targetlogfolder = "PI_PM_Psys_Basic_Psys_Mode_Discovery_Peci_Primary_Skt0_2S_And_Primary_Skt0_Skt2_4S_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "PsysPowerDomain=0x1"
		self.bios_knob_set = True
		
	def _start(self):
		self.product_class = PI_PM_Psys_Basic_Psys_Mode_Discovery_Peci_Primary_Skt0_2S_And_Primary_Skt0_Skt2_4S_Linux_TestEngine
		return self

class PI_PM_Psys_Basic_Psys_Mode_Discovery_Peci_Primary_Skt0_2S_And_Primary_Skt0_Skt2_4S_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "With Socket0 set as the Primary Socket, verify Psys parameters (Min/Max PPL1, Min/Max PPl2, TW1, TW2) are set correctly when Psys mode enabled via BIOS Setup."
	
	def run_pi_pm_main(self):
		_sv_sockets = self._tester.sv_control.sv_sockets

		self._tester.test_logger.log("Running PI_PM_Psys_Basic_Psys_Mode_Discovery_Peci_Primary_Skt0_2S_And_Primary_Skt0_Skt2_4S_Linux")
		self._tester.test_logger.log("Checking the Power Suppy Unit count from bmc terminal and set bios knob accordingly...")
		self.psulist = self._tester.sut_control.bmc_access.run_command("ipmitool sensor list | grep 'In Voltage'", verify=True).combined_lines
		self._tester.test_logger.log("The PSU available on this platform are : {}".format(self.psulist))
		self.output = self._tester.sut_control.bmc_access.run_command("ipmitool sensor list | grep -c 'In Voltage'", verify=True).combined_lines
		self.psu_count = int(self.output[0])
		self._tester.test_logger.log("The PSU Count is : {}".format(self.psu_count))
		if self.psu_count == 1:
			self.knob = 'PsysPowerLimitAndInfo=0x1'
		elif self.psu_count == 2:
			self.knob ='PsysPowerLimitAndInfo=0x3'

		self._tester.test_logger.log("Bios knob to set : {}".format(self.knob))
		#self._tester.sut_control.set_bios_knob(self.knob)
		#self._tester.tester_functions.ac_power_cycle()
		#self.bios_knob_set=True        

		self._tester.test_logger.log("Verify Max PPL1 and min PPL via PLATFORM_POWER_INFO CSR")
		self.socket_count = int(self._frame.sv_control.socket_count)

		self.plt_power_list = []
		soc_count=0
		for socket in _sv_sockets:
			self._tester.test_logger.log("-------------------------Socket {}-------------------------".format(soc_count))
			plt_power = socket.uncore.punit.platform_power_info.read()
			self._tester.test_logger.log("Platform power info for Socket{} is: {}".format(soc_count, plt_power))
			self.plt_power_list.append(str(plt_power))
			soc_count += 1
		self._tester.test_logger.log("-------------------------------------------------------------------")
		self._tester.test_logger.log("Platform power info Values are recorded successfully")
		self._tester.test_logger.log("List is {}".format(self.plt_power_list))

		#conversion
		self.power_list =[]
		for ele in self.plt_power_list:
			plt_power = ele.split('x')[1]
			plt_power ='00'+ plt_power
			self.power_list.append(plt_power)
		self._tester.test_logger.log("Converted list is {}".format(self.power_list))

		if self.socket_count == 2:
			self._tester.test_logger.log("Via Pythonsv CSR, Read Max PPL1 and Min PPL ")
			self.plt_power_soc0_index28 = self.power_list[0][-8:]
			self.plt_power_soc1_index28 = self.power_list[1][-8:]
			self.plt_power_soc0_index29 = self.power_list[0][-16:-8]
			self.plt_power_soc1_index29 = self.power_list[1][-16:-8]
			
			self._tester.test_logger.log("Via PythonSV CSR, Platform power for socket0 PPL1 is {}".format(self.plt_power_soc0_index28))
			self._tester.test_logger.log("Via PythonSV CSR, Platform power for socket1 PPL1 is {}".format(self.plt_power_soc1_index28))
			self._tester.test_logger.log("Via PythonSV CSR, Platform power for socket0 PPL2 and TW is {}".format(self.plt_power_soc0_index29))
			self._tester.test_logger.log("Via PythonSV CSR, Platform power for socket1 PPL2 and TW is {}".format(self.plt_power_soc1_index29))
			
			self._tester.test_logger.log("Via PECI PCS, Read Max PPL1 index 28 and Min PPL index 29")
			self.output_soc0_index28 = self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x30 rdpkgconfig 28 0xfe", verify=True).combined_lines
			self.output_soc1_index28 = self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x31 rdpkgconfig 28 0xfe", verify=True).combined_lines
			self.output_soc0_index29 = self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x30 rdpkgconfig 29 0xfe", verify=True).combined_lines
			self.output_soc1_index29 = self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x31 rdpkgconfig 29 0xfe", verify=True).combined_lines
			
			self.peci_soc0_index28 = self.peci_val_converter(self.output_soc0_index28)
			self.peci_soc1_index28 = self.peci_val_converter(self.output_soc1_index28)
			self.peci_soc0_index29 = self.peci_val_converter(self.output_soc0_index29)
			self.peci_soc1_index29 = self.peci_val_converter(self.output_soc1_index29)
			
			self._tester.test_logger.log("Via PECI PCS for socket0 index 28 is {}".format(self.peci_soc0_index28))
			self._tester.test_logger.log("Via PECI PCS for socket1 index 28 is {}".format(self.peci_soc1_index28))
			self._tester.test_logger.log("Via PECI PCS for socket0 index 29 is {}".format(self.peci_soc0_index29))
			self._tester.test_logger.log("Via PECI PCS for socket1 index 29 is {}".format(self.peci_soc1_index29))
			
			#index28 comparison for soc0 and soc1
			if ((self.plt_power_soc0_index28 == self.peci_soc0_index28) and (self.plt_power_soc1_index28 == self.peci_soc1_index28)):
				self._tester.test_logger.log("PASS: Max PPL1 reported value for Socket0 and Socket 1 matched with the peci read for index28.")
			else:
				self._tester.exit_with_error("FAIL: Max PPL1 reported value for Socket0:{}, Socket1:{} not matching with the peci read value of Socket0:{}, Socket1:{} for index28".format(self.plt_power_soc0_index28, self.plt_power_soc1_index28, self.peci_soc0_index28, self.peci_soc1_index28))
			
			#index29 comparison socket 0 and socket 1
			if (self.plt_power_soc0_index29 == self.peci_soc0_index29) and (self.plt_power_soc1_index29 == self.peci_soc1_index29):
				self._tester.test_logger.log("PASS: Max PPL2 and TW reported value for Socket0 and Socket 1 matched with the peci read for index29.")
			else:
				self._tester.exit_with_error("FAIL: Max PPL2 and TW reported value for Socket0:{}, Socket1:{} not matching with the peci read value of Socket0:{}, Socket1:{} for index29".format(self.plt_power_soc0_index29, self.plt_power_soc1_index29, self.peci_soc0_index29, self.peci_soc1_index29))
		
		if self.socket_count == 4:
			self._tester.test_logger.log("Via Pythonsv CSR, Read Max PPL1 and Min PPL")
			self.plt_power_soc0_index28 = self.power_list[0][-8:]
			self.plt_power_soc1_index28 = self.power_list[1][-8:]
			self.plt_power_soc2_index28 = self.power_list[2][-8:]
			self.plt_power_soc3_index28 = self.power_list[3][-8:]
			self.plt_power_soc0_index29 = self.power_list[0][-16:-8]
			self.plt_power_soc1_index29 = self.power_list[1][-16:-8]
			self.plt_power_soc2_index29 = self.power_list[2][-16:-8]
			self.plt_power_soc3_index29 = self.power_list[3][-16:-8]
			self._tester.test_logger.log("Via PythonSV CSR, Platform power for socket0 PPL1 is {}".format(self.plt_power_soc0_index28))
			self._tester.test_logger.log("Via PythonSV CSR, Platform power for socket1 PPL1 is {}".format(self.plt_power_soc1_index28))
			self._tester.test_logger.log("Via PythonSV CSR, Platform power for socket2 PPL1 is {}".format(self.plt_power_soc2_index28))
			self._tester.test_logger.log("Via PythonSV CSR, Platform power for socket3 PPL1 is {}".format(self.plt_power_soc3_index28))
			self._tester.test_logger.log("Via PythonSV CSR, Platform power for socket0 PPL2 and TW is {}".format(self.plt_power_soc0_index29))
			self._tester.test_logger.log("Via PythonSV CSR, Platform power for socket1 PPL2 and TW is {}".format(self.plt_power_soc1_index29))
			self._tester.test_logger.log("Via PythonSV CSR, Platform power for socket2 PPL2 and TW is {}".format(self.plt_power_soc2_index29))
			self._tester.test_logger.log("Via PythonSV CSR, Platform power for socket3 PPL2 and TW is {}".format(self.plt_power_soc3_index29))

			self._tester.test_logger.log("Via PECI PCS, Read Max PPL1 index 28 and Min PPL index 29")
			self.output_soc0_index28 = self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x30 rdpkgconfig 28 0xfe", verify=True).combined_lines
			self.output_soc1_index28 = self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x31 rdpkgconfig 28 0xfe", verify=True).combined_lines
			self.output_soc2_index28 = self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x32 rdpkgconfig 28 0xfe", verify=True).combined_lines
			self.output_soc3_index28 = self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x33 rdpkgconfig 28 0xfe", verify=True).combined_lines
			self.output_soc0_index29 = self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x30 rdpkgconfig 29 0xfe", verify=True).combined_lines
			self.output_soc1_index29 = self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x31 rdpkgconfig 29 0xfe", verify=True).combined_lines
			self.output_soc2_index29 = self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x32 rdpkgconfig 29 0xfe", verify=True).combined_lines
			self.output_soc3_index29 = self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x33 rdpkgconfig 29 0xfe", verify=True).combined_lines
			
			self.peci_soc0_index28 = self.peci_val_converter(self.output_soc0_index28)
			self.peci_soc1_index28 = self.peci_val_converter(self.output_soc1_index28)
			self.peci_soc2_index28 = self.peci_val_converter(self.output_soc2_index28)
			self.peci_soc3_index28 = self.peci_val_converter(self.output_soc3_index28)
			self.peci_soc0_index29 = self.peci_val_converter(self.output_soc0_index29)
			self.peci_soc1_index29 = self.peci_val_converter(self.output_soc1_index29)
			self.peci_soc2_index29 = self.peci_val_converter(self.output_soc2_index29)
			self.peci_soc3_index29 = self.peci_val_converter(self.output_soc3_index29)

			self._tester.test_logger.log("Via PECI PCS for socket0 index 28 is {}".format(self.peci_soc0_index28))
			self._tester.test_logger.log("Via PECI PCS for socket1 index 28 is {}".format(self.peci_soc1_index28))
			self._tester.test_logger.log("Via PECI PCS for socket2 index 28 is {}".format(self.peci_soc2_index28))
			self._tester.test_logger.log("Via PECI PCS for socket3 index 28 is {}".format(self.peci_soc3_index28))
			self._tester.test_logger.log("Via PECI PCS for socket0 index 29 is {}".format(self.peci_soc0_index29))
			self._tester.test_logger.log("Via PECI PCS for socket1 index 29 is {}".format(self.peci_soc1_index29))
			self._tester.test_logger.log("Via PECI PCS for socket2 index 29 is {}".format(self.peci_soc2_index29))
			self._tester.test_logger.log("Via PECI PCS for socket3 index 29 is {}".format(self.peci_soc3_index29))
			
			#index28 comparison for soc0 and soc1
			if ((self.plt_power_soc0_index28 == self.peci_soc0_index28) and (self.plt_power_soc1_index28 == self.peci_soc1_index28)):
				self._tester.test_logger.log("PASS: Max PPL1 reported value for Socket0 and Socket 1  matched with the peci read for index28.")
			else:
				self._tester.exit_with_error("FAIL: Max PPL1 reported value for Socket0:{}, Socket1:{} not matching with the peci read value of Socket0:{}, Socket1:{} for index28".format(self.plt_power_soc0_index28, self.plt_power_soc1_index28, self.peci_soc0_index28, self.peci_soc1_index28))
			
			#index28 comparison for soc2 and soc3
			if ((self.plt_power_soc2_index28 == self.peci_soc2_index28) and (self.plt_power_soc3_index28 == self.peci_soc3_index28)):
				self._tester.test_logger.log("PASS: Max PPL1 reported value for Socket2 and Socket3 matched with the peci read for index28.")
			else:
				self._tester.exit_with_error("FAIL: Max PPL1 reported value for Socket2:{}, Socket3:{} not matching with the peci read value of Socket2:{}, Socket3:{} for index28".format(self.plt_power_soc2_index28, self.plt_power_soc3_index28, self.peci_soc2_index28, self.peci_soc3_index28))

			#index29 comparison for soc0 and soc1
			if (self.plt_power_soc0_index29 == self.peci_soc0_index29) and (self.plt_power_soc1_index29 == self.peci_soc1_index29):
				self._tester.test_logger.log("PASS: Max PPL2 and TW reported value for Socket0 and Socket 1 matched with the peci read for index29.")
			else:
				self._tester.exit_with_error("FAIL: Max PPL2 and TW reported value for Socket0:{}, Socket1:{} not matching with the peci read value of Socket0:{}, Socket1:{} for index29".format(self.plt_power_soc0_index29, self.plt_power_soc1_index29, self.peci_soc0_index29, self.peci_soc1_index29))
			
			#index29 comparison for soc2 and soc3
			if (self.plt_power_soc2_index29 == self.peci_soc2_index29) and (self.plt_power_soc3_index29 == self.peci_soc3_index29):
				self._tester.test_logger.log("PASS: Max PPL2 and TW reported value for Socket2 and Socket3 matched with the peci read for index29.")
			else:
				self._tester.exit_with_error("FAIL: Max PPL2 and TW reported value for Socket2:{}, Socket3:{} not matching with the peci read value of Socket2:{}, Socket3:{} for index29".format(self.plt_power_soc0_index29, self.plt_power_soc1_index29, self.peci_soc0_index29, self.peci_soc1_index29))

	def peci_val_converter(self,peci_output):
		self.peci_val = peci_output[0][13:]
		return self.peci_val


#######################################################################################################

#CRAUTO-10303
class PI_PM_SocketRapl_Verify_Package_Energy_Counter_Values_PECI_2S_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_SocketRapl_Verify_Package_Energy_Counter_Values_PECI_2S_Linux"}

	def __init__(self):
		super(PI_PM_SocketRapl_Verify_Package_Energy_Counter_Values_PECI_2S_Linux, self).__init__()
		self.name = "PI_PM_SOCKET_RAPL_VERIFY_PACKAGE_ENERGY_COUNTER_PECI_2S_LINUX" 
		self.targetlogfolder = "PI_PM_SocketRapl_Verify_Package_Energy_Counter_Values_PECI_2S_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		#self.bios_knobs = ""
		self.run_ptu = True
		self.bios_knob_set = True
		
	def _start(self):
		self.product_class = PI_PM_SocketRapl_Verify_Package_Energy_Counter_Values_PECI_2S_Linux_TestEngine
		return self

class PI_PM_SocketRapl_Verify_Package_Energy_Counter_Values_PECI_2S_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "Collect the Package Accumulated Energy Status loop and observe whether it meets the expected range"
	
	def run_pi_pm_main(self):
		self.pipm_app_log =""
		self._tester.test_logger.log("Running PI_PM_SocketRapl_Verify_Package_Energy_Counter_Values_PECI_2S_Linux")
		self.msr_tools_installation()
		self.mon_thread = thread_with_trace(target=self.run_ptu_mon_csv)                    
		self.mon_thread.start()
		time.sleep(120)
		self.wl_thread = thread_with_trace(target=self.run_ptu_workload, args=("ct3",), name="ptu")                 
		self.wl_thread.start()
		time.sleep(30)

		self._tester.test_logger.log("Reading the  Package_Energy_Staus via PECI  in bmc and  via MSR for Socket0")
		self.register_val_soc0 = "0x611"
		self.output= self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x30 RdPkgConfig 3 0xff", verify=True).combined_lines
		time.sleep(0.5)
		self.rdmsr_data_soc0 = self._tester.sut_control.os_access.run_command('rdmsr 0x611').combined_lines
		#int conversion for peci and msr values
		self.peci_val = self.output[0][13:]
		self.peci_decimal_val_soc0 = int(self.peci_val, 16)
		self.package_energay_rdmsr_soc0=int(self.rdmsr_data_soc0[0],16)


		self._tester.test_logger.log("Reading the  Package_Energy_Staus via PECI in bmc and via MSR for Socket1")
		self.register_val_soc1 = "-p 56 0x611"
		self.output = self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x31 RdPkgConfig 3 0xff", verify=True).combined_lines
		time.sleep(0.5)
		self.rdmsr_data_soc1 = self._tester.sut_control.os_access.run_command('rdmsr -p 56 0x611').combined_lines
		#int conversion for peci and msr values
		self.peci_val = self.output[0][13:]
		self.peci_decimal_val_soc1 = int(self.peci_val, 16)
		self.package_energay_rdmsr_soc1=int(self.rdmsr_data_soc1[0],16)

		#percentage calcualation

		self.calculate_pecentage_diff_with_logmsg(x=self.package_energay_rdmsr_soc0,y=self.peci_decimal_val_soc0,i=self.package_energay_rdmsr_soc1,j=self.peci_decimal_val_soc1,percent_value=2.5,log_str1 = "Package Energy status via PECI",log_str2 = "Package Energy status via MSR")

		self._tester.test_logger.log("Reading the Package Accumulated Energy Status via PECI in bmc for Socket0")
		self.peci_val_list = self.get_peci_val()
		self.output = self.extract_peci_val(self.peci_val_list)
		self._tester.test_logger.log("Stopped PTU mon thread")
		self.stop_ptu()
		self.mon_thread.kill()
		self.wl_thread.kill()
		
		self.Package_Energy_Consumed_skt0_1 = self.output[0]
		self._tester.test_logger.log("The peci_cmds output for 1st run is {}".format(self.output[0]))
		
		self.Package_Energy_Consumed_skt0_2 = self.output[1]
		self._tester.test_logger.log("The peci_cmds output for 2nd run is {}".format(self.output[1]))
		
		if self.Package_Energy_Consumed_skt0_2 > self.Package_Energy_Consumed_skt0_1:
			self._tester.test_logger.log("PASS : Package Accumulated Energy value is incrementing for Socket0...")
		else:
			self._tester.exit_with_error("FAIL : Package Accumulated Energy value is not incrementing for socket0. {} and {}".format(self.Package_Energy_Consumed_skt0_1, self.Package_Energy_Consumed_skt0_2))
		
		self._tester.test_logger.log("Reading the Package Accumulated Energy Status via PECI in bmc for Socket1")
		
		self.Package_Energy_Consumed_skt1_1 = self.output[2]
		self._tester.test_logger.log("The peci_cmds output for 1st run is {}".format(self.output[2]))
		
		self.Package_Energy_Consumed_skt1_2 = self.output[3]
		self._tester.test_logger.log("The peci_cmds output for 2nd run is {}".format(self.output[3]))
		
		if self.Package_Energy_Consumed_skt1_2 > self.Package_Energy_Consumed_skt1_1:
			self._tester.test_logger.log("PASS : Package Accumulated Energy value is incrementing for socket1...")
		else:
			self._tester.exit_with_error("FAIL : Package Accumulated Energy value is not incrementing for socket1. {} and {}".format(self.Package_Energy_Consumed_skt1_1, self.Package_Energy_Consumed_skt1_2))
		
		self._tester.test_logger.log("Calculate Package Power Consumption for each socket and Determine Results")

		#Socket0_Power = ((Package_Energy_Consumed_skt0_2 - Package_Energy_Consumed_skt0_1) * 2^(-14)) / Time Delay
		self.Socket0_Power = int (((self.Package_Energy_Consumed_skt0_2 - self.Package_Energy_Consumed_skt0_1)* 2**(-14)) / 1)
		self._tester.test_logger.log("Package Power Consumption for socket0 is {}".format(self.Socket0_Power))

		#Socket1_Power = ((Package_Energy_Consumed_skt1_2 - Package_Energy_Consumed_skt1_1) * 2^(-14)) / Time Delay
		self.Socket1_Power = int (((self.Package_Energy_Consumed_skt1_2 - self.Package_Energy_Consumed_skt1_1)* 2**(-14)) / 1)
		self._tester.test_logger.log("Package Power Consumption for socket1 is {}".format(self.Socket1_Power))

		#copying PTU mon log to host
		self.test_logs.append(self.ptu_mon_log)
		time.sleep(30)
		self.copy_pi_pm_logs()
		time.sleep(30)
		self.csv_filepath= os.path.join(self._tester._manager.test_case_dir, os.path.basename(self.ptu_mon_log))

		#checking CPU power data from PTU Monitor
		self.power_cpu = self.check_cpu_power()
		self.Cpu0_power = int(self.power_cpu[' Power']['  CPU0'])
		self.Cpu1_power = int(self.power_cpu[' Power']['  CPU1'])
		self._tester.test_logger.log("Power reading from PTU mon log for CPU0 is {}".format(self.Cpu0_power))

		self.calculate_pecentage_diff_with_logmsg(x=self.Socket0_Power,y=self.Cpu0_power,i=self.Socket1_Power,j=self.Cpu1_power,percent_value = 5,log_str1 = "Package Power consumption via PECI",log_str2 = "CPU Power reading via PTU Monitor")
	
	def pipm_parse_log(self,pipm_app_log):
		pass

####################################################################################################### 

#CRAUTO-10437
class PI_PM_Psys_Verify_Platform_and_Processor_Energy_Counter_Values_MSR_2S_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_Psys_Verify_Platform_and_Processor_Energy_Counter_Values_MSR_2S_Linux"}

	def __init__(self):
		super(PI_PM_Psys_Verify_Platform_and_Processor_Energy_Counter_Values_MSR_2S_Linux, self).__init__()
		self.name = "PSYS_VERIFY_PLATFORM_AND_PROCESSOR_ENERGY_COUNTER_MSR_2S_LINUX" 
		self.targetlogfolder = "PI_PM_Psys_Verify_Platform_and_Processor_Energy_Counter_Values_MSR_2S_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "PsysPowerLimitCsrLock=0x0,PsysPowerInfoLock=0x0,PsysPowerLimitAndInfo=0x1,PsysPowerDomain=0x1"
		self.run_ptu = True
		self.bios_knob_set = False
		
	def _start(self):
		self.product_class = PI_PM_Psys_Verify_Platform_and_Processor_Energy_Counter_Values_MSR_2S_Linux_TestEngine
		return self

class PI_PM_Psys_Verify_Platform_and_Processor_Energy_Counter_Values_MSR_2S_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "Validate Platform (MSR 0x64D) and Processor (MSR 0x611) Energy Counter Values Are Correct"
	
	def run_pi_pm_main(self):
		self.pipm_app_log = ""
		self._tester.test_logger.log("Running PI_PM_Psys_Verify_Platform_and_Processor_Energy_Counter_Values_MSR_2S_Linux")
		self.msr_tools_installation()
		self.mon_thread = thread_with_trace(target = self.run_ptu_mon_csv)          
		self.mon_thread.start()
		time.sleep(120)
		self.wl_thread = thread_with_trace(target=self.run_ptu_workload_with_cp ,args=(80,))                    
		self.wl_thread.start()
		time.sleep(30)
		
		self._tester.test_logger.log("Read platform power consumption Via PythonSV.")
		self.power_plt_energy_status_value = self.run_platform_power_consumption()
		self._tester.test_logger.log("Platform power consumption Via PythonSV is {}".format(self.power_plt_energy_status_value))
		self._tester.test_logger.log("Performing two reads of Package_Energy_Staus and Platform_Energy_Staus via MSR")
		self.rdmsr_val_list = self.get_rdmsr_val()
		self.rdmsr_data = self.extract_rdmsr_val(self.rdmsr_val_list)
		self._tester.test_logger.log("Stopping PTU mon thread")
		self.stop_ptu()
		self.mon_thread.kill()
		self.wl_thread.kill()
		self.package_energy_rdmsr1=self.rdmsr_data[0]
		self.package_energy_rdmsr2=self.rdmsr_data[1]
		self._tester.test_logger.log("Package_Energy_Staus values for read 0 is {} and read 1 is {} via MSR".format(self.package_energy_rdmsr1,self.package_energy_rdmsr2))
		self.platform_energy_rdmsr1 = self.rdmsr_data[2]
		self.platform_energy_tsc1 = self.rdmsr_data[3]
		self.platform_energy_rdmsr2 = self.rdmsr_data[4]
		self.platform_energy_tsc2 = self.rdmsr_data[5]
		self._tester.test_logger.log("Platform_Energy_Staus values for read 0 is {} and read 1 is {} via MSR".format(self.platform_energy_rdmsr1,self.platform_energy_rdmsr2))
		self._tester.test_logger.log("Time stamp counter for read 0 is {} and read 1 is {} via MSR".format(self.platform_energy_tsc1,self.platform_energy_tsc2))
		
		self._tester.test_logger.log("Calculate Processor Package Power Consumption and Determine Results")
		#Package Power = [(Energy_Value_2 - Energy_Value_1) * (61 * 10^-6)] / Time Delay
		self.package_power = ((self.package_energy_rdmsr2-self.package_energy_rdmsr1) * (2**(-14)))/1
		self._tester.test_logger.log("Package Power Consumption is {}".format(self.package_power))
		
		#copying PTU mon log to host
		self.test_logs.append(self.ptu_mon_log)
		time.sleep(30)
		self.copy_pi_pm_logs()
		time.sleep(30)
		self.csv_filepath= os.path.join(self._tester._manager.test_case_dir, os.path.basename(self.ptu_mon_log))

		#checking CPU power data from PTU Monitor
		self.power_cpu = self.check_cpu_power()
		self.Cpu0_power = int(self.power_cpu[' Power']['  CPU0'])
		#self.Cpu1_power = int(self.power_cpu[' Power']['  CPU1'])
		self._tester.test_logger.log("Power reading from PTU mon log for CPU0 is {}".format(self.Cpu0_power))

		self.calculate_pecentage_diff_with_logmsg(x=self.package_power,
									y=self.Cpu0_power,
									i=self.package_power,
									j=self.Cpu0_power,
									percent_value = 5,
									log_str1 = "Package Energy status via MSR",
									log_str2 = "CPU power via PTU monitor")

		self._tester.test_logger.log("Calculate Platform Power Consumption and Determine Results")

		'''if TSC_1 > TSC_0 : 
								TSC_delta = (TSC_1 - TSC_0) * 10^-8
				else 
								new_TSC_0 = 0xffff ffff - TSC_0
								new_TSC_1 = TSC_1
								TSC_delta = (new_TSC_0 + new_TSC_1) * 10^-8

		platform_power = energy_delta/TSC_delta'''

		#Time Delay calculations:
		if self.platform_energy_tsc2 > self.platform_energy_tsc1:
			self.tsc_delta = (self.platform_energy_tsc2 - self.platform_energy_tsc1) * 10**-8
		else:
			self.tsc_val = "ffffffff"
			self.tsc_val_int = int(self.tsc_val,16)
			self.platform_energy_tsc1 = self.tsc_vl_int - self.platform_energy_tsc1
			self.platform_energy_tsc2 = self.platform_energy_tsc2
			self.tsc_delta = (self.platform_energy_tsc1 + self.platform_energy_tsc2) * 10**-8

		#Platform Power = (Total_Energy_Consumed_2 - Total_Energy_Consumed_1) / Time Delay
		self._tester.test_logger.log("TSC delta is {}".format(self.tsc_delta))

		self.platform_power = (self.platform_energy_rdmsr2-self.platform_energy_rdmsr1) /self.tsc_delta
		self._tester.test_logger.log("calculated Platform Power Consumption is {}".format(self.platform_power))

		self.calculate_pecentage_diff_with_logmsg(x=self.platform_power,
									y=self.power_plt_energy_status_value,
									i=self.platform_power,
									j=self.power_plt_energy_status_value,
									percent_value = 5,
									log_str1 = "Platform Energy status via run_platform_power_consumption",
									log_str2 = "Platform Power Consumption via MSR")

	
	def pipm_parse_log(self,pipm_app_log):
		pass

###########################################################################################################
#CRAUTO-10301
class PI_PM_Psys_Verify_Platform_Energy_Counter_Values_PECI_2S_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_Psys_Verify_Platform_Energy_Counter_Values_PECI_2S_Linux"}

	def __init__(self):
		super(PI_PM_Psys_Verify_Platform_Energy_Counter_Values_PECI_2S_Linux, self).__init__()
		self.name = "PSYS_VERIFY_PLATFORM_ENERGY_COUNTER_PECI_2S_LINUX" 
		self.targetlogfolder = "PI_PM_Psys_Verify_Platform_Energy_Counter_Values_PECI_2S_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "PsysPowerLimitCsrLock=0x0,PsysPowerInfoLock=0x0,PsysPowerLimitAndInfo=0x1,PsysPowerDomain=0x1"
		self.run_ptu = True
		self.bios_knob_set = True
		
	def _start(self):
		self.product_class = PI_PM_Psys_Verify_Platform_Energy_Counter_Values_PECI_2S_Linux_TestEngine
		return self

class PI_PM_Psys_Verify_Platform_Energy_Counter_Values_PECI_2S_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "Validate PECI PCS Index 3 parameter 0xFE Platform Accumulated Energy Status. Verify counter increments. Verify that it reports correct values by calculate Platform Power value and compare with Platform_Energy_Status MSR. Verify the counter overflow. "
	
	def run_pi_pm_main(self):
		self._tester.test_logger.log("Running PI_PM_Psys_Verify_Platform_Energy_Counter_Values_PECI_2S_Linux")
		self.mon_thread = thread_with_trace(target=self.run_ptu_monitor)                
		self.mon_thread.start()
		time.sleep(60)
		self.wl_thread = thread_with_trace(target=self.run_ptu_workload, args=("ct3",), name="ptu")         
		self.wl_thread.start()
		time.sleep(60)

		
		self._tester.test_logger.log("Reading the Platform Accumulated Energy Status via PECI in bmc")
		self.energy_status_1 = self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x30 RdPkgConfig 3 0xFE", verify=True).combined_lines
		self.current_plt_energy_val_1 = int(self.energy_status_1[0][13:],16)
		self.total_energy_consumed_1= int(self.energy_status_1[31:0],16)
		
		time.sleep(1)
		self.energy_status_2 = self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x30 RdPkgConfig 3 0xFE", verify=True).combined_lines
		self.current_plt_energy_val_2 = int(self.energy_status_2[0][13:],16)
		self.total_energy_consumed_2= int(self.energy_status_1[31:0],16)

		
		self._tester.test_logger.log("The peci_cmds output for 1st run is {}".format(self.current_plt_energy_val_1))
		self._tester.test_logger.log("The peci_cmds output for 2nd run is {}".format(self.current_plt_energy_val_2))
		
		if self.current_plt_energy_val_2 > self.current_plt_energy_val_1:
			self._tester.test_logger.log("Platform Accumulated Energy value is incrementing...")
		else:
			self._tester.test_logger.log("FAIL : Platform Accumulated Energy value is not incrementing. {} and {}".format(self.peci_decimal_val1, self.peci_decimal_val2))
		
		self._tester.test_logger.log("Read platform power consumption Via PythonSV.")
		self.plt_power_consumption = self.run_power_plt_energy_status_avg()


		#Platform Power = (Total_Energy_Consumed_2 - Total_Energy_Consumed_1) / Time Delay
		self.plt_power = int((self.total_energy_consumed_2 - self.total_energy_consumed_1) / 1)
		self._tester.test_logger.log("The Platform power calculated from Total Energy Consumed in 1 seconds is {}".format(self.plt_power))

		#5% range
		if self._tester.manager.cpu_project == CPU_PROJECT.SPR:
			self.fivepercent_val = int(self.plt_power*0.05)
			self.min_range = int(self.plt_power - self.fivepercent_val)
			self.max_range = int(self.plt_power + self.fivepercent_val)

		elif self._tester.manager.cpu_project == CPU_PROJECT.GNR:
			self.onepercent_val = int(self.plt_power*0.01)
			self.min_range = int(self.plt_power - self.onepercent_val)
			self.max_range = int(self.plt_power + self.onepercent_val)
	
		if self.min_range <= int(self.plt_power_consumption) <= self.max_range:
			self._tester.test_logger.log("PASS : Power_Platform_Energy_Status value matched with the expected range.")
		else:
			self._tester.test_logger.log("FAIL : Power_Platform_Energy_Status value not matching with the expected range of {} annd {}. Please check the above logs for details".format(self.min_range, self.max_range))
		
		self._tester.test_logger.log("Verify the Platform_Energy_Status PECI value is not overflowing after 18 bits, please wait it will take a while")
		
		self._tester.test_logger.log("Checking the PECI cmd for RdPkgConfig 3 0xFE")
		self.result = self._tester.sut_control.bmc_access.run_command("peci_cmds RdPkgConfig 3 0xFE", verify=True).combined_lines
		self.current_plt_energy_val = int(self.result[0][13:],16)
		self._tester.test_logger.log("The peci_cmds output for 0xFE is {}".format(self.current_plt_energy_val))
		if self.current_plt_energy_val > int('0x700000',16):
			self._tester.test_logger.log("PASS:counter overflow validated.Platform_Energy_Status PECI value is not overflowing after 18 bits.")
		else:
			self._tester.test_logger.log("Via BMC terminal keep checking the below register incrementing, Monitor bit [19], and determine the results.")
			self._tester.test_logger.log("The peci_cmds output for 0xFE is {}".format(self.current_plt_energy_val))
			self.delta_energy = int(458752-self.current_plt_energy_val)
			self._tester.test_logger.log("The delta energy is {}".format(self.delta_energy))
			self.delta_energy = int(self.delta_energy)

			self.remaining_time_in_seconds = int(self.delta_energy/self.plt_power)+60
			self._tester.test_logger.log("The remaining_time_in_seconds is {}".format(self.remaining_time_in_seconds))
			while True:
				end_time = time.time() + self.remaining_time_in_seconds
				while time.time()<end_time:
					self.result = self._tester.sut_control.bmc_access.run_command("peci_cmds RdPkgConfig 3 0xFE", verify=True).combined_lines
					self.peci_val_FE = self.result[0][11:]
					self._tester.test_logger.log("The peci_cmds output for 0xFE is {}".format(self.peci_val_FE))
					self.val = self.check_nth_bit(str_hex = self.peci_val_FE, nth_bit = 19)
					if self.val:
						self._tester.test_logger.log("PASS:The peci_cmds output {} for Monitor bit [19] is set to 1.".format(self.peci_val_FE))
						break
					else:
						self._tester.test_logger.log("The peci_cmds output {} for Monitor bit [19] is not set to 1. We will keep monitoring register till {} seconds.".format(self.peci_val_FE,self.remaining_time_in_seconds))

				self._tester.exit_with_error("FAIL:Counter overflew before reaching the bit 19.{} seconds exausted and Monitor bit [19] is not set to 1")
				
				
		self.wl_thread.kill()
		time.sleep(10)
		self.mon_thread.kill()
			
	def check_nth_bit(self, str_hex, nth_bit):
		return (int(str_hex, 16) & 2 **(nth_bit - 1)) >> (nth_bit - 1) == 1

	def run_pi_pm_post(self):
		pass


############################################################################################################

class PI_PM_Psys_Modify_PPL1_via_PMUtil_Verify_Power_Capping_Root_2S_Linux(PI_PM_Testcase):
	_default = {"_config_name": "Psys_Modify_PPL1_via_PMUtil_Verify_Power_Capping_Root_2S_Linux"}

	def __init__(self): 
		super(PI_PM_Psys_Modify_PPL1_via_PMUtil_Verify_Power_Capping_2S_4S_Linux, self).__init__()
		self.name = "Psys_Modify_PPL1_via_PMUtil_Verify_Power_Capping_Linux" 
		self.targetlogfolder = "Psys_Modify_PPL1_via_PMUtil_Verify_Power_Capping_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "PsysPowerLimitCsrLock=0x0,PsysPowerInfoLock=0x0,PsysPowerLimitAndInfo=0x1,PsysPowerDomain=0x1"
		self.run_ptu = True
		self.check_turbo_flag = False
		self.bios_knob_set = True
		self.min_range = 582
		self.max_range = 618

	def _start(self):
		self.product_class = PI_PM_Psys_Modify_PPL1_via_PMUtil_Verify_Power_Capping_Root_2S_Linux_TestEngine
		return self

class PI_PM_Psys_Modify_PPL1_via_PMUtil_Verify_Power_Capping_Root_2S_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "Collect the Power Platform Energy Status loop and observe whether it meets the expected range"
	
	def run_pi_pm_main(self):
		sv_sockets = self._tester.sv_control.sv_sockets
		self.socket_count = int(self._frame.sv_control.socket_count)
		self._tester.test_logger.log("Running Psys_Modify_PPL1_via_PMUtil_Verify_Power_Capping_2S_Linux")

		self._tester.test_logger.log("Running PTU WL for Test")
		self.wl_thread = thread_with_trace(target=self.run_ptu_workload_with_cp ,args=(50,))
		self.wl_thread.start()
		time.sleep(30)

		self.power_plt_energy_status = self.run_power_plt_energy_status_avg()
		self.reduced_platform_power=int(self.plt_power_status_value*0.7)

		for socket in _sv_sockets:
			socket.uncore.punit.platform_rapl_limit_cfg.ppl1= self.reduced_platform_power*8

		self._tester.test_logger.log("Reading platform power consumption for 2nd time")
		self.power_plt_energy_status_value2 = self.run_platform_power_consumption()

		#platform power must be +/- 3% of reduced power limit(step 8)

		val1= int(self.reduced_platform_power)
		val2= int(self.power_plt_energy_status_value2)

		lower_limit= val1-((val1*3)/100)
		upper_limit= val1-((val1*3)/100)

		if lower_limit <= val2 <= upper_limit:
			self._tester.test_logger.log("The platform power is with +/- 3% within the range!")
		else:
			self._tester.test_logger.log("The platform power exceeds the +/-3% range!")

		self._tester.test_logger.log("Stopping the ptu operations !")
		self.wl_thread.kill()

		self._tester.test_logger.log("Setting PPL1 to its original values!")

		for socket in _sv_sockets:
			socket.io0.uncore.punit.ptpcioregs.ptpcioregs.platform_rapl_limit_cfg= 0x63a3002663080

		self._tester.test_logger.log("The test :Psys_Modify_PPL1_via_PMUtil_Verify_Power_Capping_Root_2S_Linux has completed.")


	def run_pi_pm_post(self):
		pass




############################################################################################################
class PI_PM_Psys_Modify_PPL2_via_PMUtil_Verify_Power_Capping_Root_2S_Linux(PI_PM_Testcase):
	_default = {"_config_name": "Psys_Modify_PPL2_via_PMUtil_Verify_Power_Capping_Root_2S_Linux"}

	def __init__(self): 
		super(PI_PM_Psys_Modify_PPL2_via_PMUtil_Verify_Power_Capping_2S_4S_Linux, self).__init__()
		self.name = "Psys_Modify_PPL2_via_PMUtil_Verify_Power_Capping_Linux" 
		self.targetlogfolder = "Psys_Modify_PPL2_via_PMUtil_Verify_Power_Capping_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "PsysPowerLimitCsrLock=0x0,PsysPowerInfoLock=0x0,PsysPowerLimitAndInfo=0x1,PsysPowerDomain=0x1"
		self.run_ptu = True
		self.check_turbo_flag = False
		self.bios_knob_set = True
		self.min_range = 582
		self.max_range = 618

	def _start(self):
		self.product_class = PI_PM_Psys_Modify_PPL2_via_PMUtil_Verify_Power_Capping_Root_2S_Linux_TestEngine
		return self

class PI_PM_Psys_Modify_PPL2_via_PMUtil_Verify_Power_Capping_Root_2S_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "Collect the Power Platform Energy Status loop and observe whether it meets the expected range"

	def run_pi_pm_main(self):
		sv_sockets = self._tester.sv_control.sv_sockets
		self.socket_count = int(self._frame.sv_control.socket_count)
		self._tester.test_logger.log("Running Psys_Modify_PPL2_via_PMUtil_Verify_Power_Capping_2S_Linux")

		self._tester.test_logger.log("Running PTU WL for Test")
		self.wl_thread = thread_with_trace(target=self.run_ptu_workload_with_cp ,args=(50,))
		self.wl_thread.start()
		time.sleep(30)

		self.power_plt_energy_status = self.run_power_plt_energy_status_avg()

		self.reduced_platform_power=int(self.plt_power_status_value*0.7)

		for socket in _sv_sockets:
			socket.uncore.punit.platform_rapl_limit_cfg.ppl2= self.reduced_platform_power*8

		self._tester.test_logger.log("Reading platform power consumption for 2nd time")
		self.power_plt_energy_status_value2 = self.run_platform_power_consumption()

		val1= int(self.power_plt_energy_status)
		val2= int(self.power_plt_energy_status_value2)

		lower_limit= val1-((val1*3)/100)
		upper_limit= val1-((val1*3)/100)

		if lower_limit <= val2 <= upper_limit:
			self._tester.test_logger.log("The platform power is with +/- 3% within the range!")
		else:
			self._tester.test_logger.log("The platform power exceeds the +/-3% range!")

		self._tester.test_logger.log("Stopping the ptu operations !")
		self.wl_thread.kill()

		self._tester.test_logger.log("Setting PPL1 to its original values!")

		for socket in _sv_sockets:
			socket.io0.uncore.punit.ptpcioregs.ptpcioregs.platform_rapl_limit_cfg= 0x63a3002663080

		self._tester.test_logger.log("The test :Psys_Modify_PPL1_via_PMUtil_Verify_Power_Capping_Root_2S_Linux has completed.")


	def run_pi_pm_post(self):
		pass




############################################################################################################

class PI_PM_POVRAY_TDP_VERIFICATION_LINUX(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_POVRAY_TDP_Verification_Test_Linux"}

	def __init__(self):
		super(PI_PM_POVRAY_TDP_VERIFICATION_LINUX, self).__init__()
		self.name = "POVRAY_TDP_VERIFICATION_LINUX" 
		self.targetlogfolder = "PI_PM_TDP_Verification_Test_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "TurboMode=0x0" 
		self.run_ptu = False
		self.check_turbo_flag = False
		self.bios_knob_set = False
		self.tool = "povray"
	
	def _start(self):
		self.product_class = PI_PM_TDP_Verification_Test_Linux_TestEngine
		return self

		
############################################################################################################

#######################################################################################################

#CRAUTO-11227
class PI_PM_TDP_Verification_Test_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_TDP_Verification_Test_Linux"}

	def __init__(self):
		super(PI_PM_TDP_Verification_Test_Linux, self).__init__()
		self.name = "TDP_VERIFICATION_LINUX" 
		self.targetlogfolder = "PI_PM_TDP_Verification_Test_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.run_ptu = False
		self.check_turbo_flag = False
		self.bios_knob_set = False
		self.tool = "ptu"
	
	def _start(self):
		self.product_class = PI_PM_TDP_Verification_Test_Linux_TestEngine
		return self

class PI_PM_TDP_Verification_Test_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "This testcase will be used to check the TDP using the PTU."
	
	def run_pi_pm_main(self):
		self.check_sut_os() 
		self.tool = self._config.tool
		if self.cpu_type =="SPR":
			self._tester.test_logger.log("Running test on SPR ")
			_sv_sockets = self._tester.sv_control.sv_sockets
			from namednodes import sv
			sockets = sv.socket.getAll()
			socket0 = sv.sockets[0]
			tdp_val_s0 = socket0.uncore.punit.package_power_sku_cfg.pkg_tdp
			self.tdp_val = int(int(str(tdp_val_s0), 16) / 8)  
			self._tester.test_logger.log("TDP value from pysv is {}W".format(self.tdp_val))
		
			#calculate TDP value from pmutil
			cmd1 = "cd {} && ./pmutil_bin -w 0xB1 -d 0".format(self.app_pmutil_path)
			cmd2 = "cd {} && ./pmutil_bin -w 0xB0 -d 0x8000037f".format(self.app_pmutil_path)
			cmd3 = "cd {} && ./pmutil_bin -r 0xB1".format(self.app_pmutil_path)
			
			pmutil_freq_cmds = [cmd1, cmd2, cmd3]
			
			for cmd in pmutil_freq_cmds:
				self.tdp_power_pmutil = self._tester.sut_control.os_access.run_command(cmd).combined_lines
			self._tester.test_logger.log("TDP frequency command output is: {}".format(self.tdp_power_pmutil))
			
			self.tdp_power_pmutil = self.tdp_power_pmutil[0].replace("0x", "").replace("\n", "")
			self.tdp_power_pmutil = ('0' * (8 - len(self.tdp_power_pmutil))) + self.tdp_power_pmutil
				
		elif self.cpu_type in ["GNR","SRF"]:
			self._tester.test_logger.log("Runninig the test on GNR")
			self.gnr_pmutil_frequency_calculator()  # changing values to MGHZ
			self.tdp_freq_val = self.pmutil_tdp_freq[0].split(":")[1][3:] 
			self.tdp_freq_ratio = self.tdp_freq_val[2:6]
			self.tdp_val = int((int(self.tdp_freq_ratio,16))/8)
			self._tester.test_logger.log("Value of the TDP using SST-PP level is {}".format(self.tdp_val))
			
			self.pmutil_cmd = "cd {}; ./pmutil_bin -r 0x614".format(self.app_pmutil_path)
			self._tester.test_logger.log("pmutil command to check TDP from MSR {} ".format(self.pmutil_cmd))
			self.tdp_power_pmutil = self._tester.sut_control.os_access.run_command(self.pmutil_cmd).combined_lines
			self.tdp_power_pmutil = ('0' * (8 - len(self.tdp_power_pmutil[0]))) + self.tdp_power_pmutil[0]
		
		#Final TDP Calculations for GNR and SPR
		self.tdp_power_val_pmutil = bin(int(self.tdp_power_pmutil, 16))[-15:]
		self.tdp_power_val_pmutil = int(self.tdp_power_val_pmutil, 2)
		self._tester.test_logger.log("TDP value from pmutil is {}W".format(self.tdp_power_val_pmutil))

		# comparing TDP from pmutil commands
		self._tester.test_logger.log("Comparing TDP value from SST-PP level command and from MSR .. ")
		if self.tdp_val == self.tdp_power_val_pmutil:
			self._tester.test_logger.log("PASS: TDP value from MSR {} and SST-PP level command {} are equal! ".format(self.tdp_power_val_pmutil, self.tdp_val))
		else:
			self._tester.test_logger.log("FAIL: TDP value from MSR {} and SST-PP level {} are not equal! ".format(self.tdp_power_val_pmutil,self.tdp_val))

		# start standalone script
		self._tester.test_logger.log("Triggering {}_Testcase. Please wait for sometime to complete test".format(self._config.name))
		cmd = "chmod -R 777 {dir}".format(dir=self.pi_pm_app_path)
		result = self._tester.sut_control.os_access.run_command(cmd, verify=False, retry=0)
		cmd = "cd {dir} && python {dir}/{scr} --test {testname} --os {operatingsystem}  --tdp_val {tdp} --ptu_runtime {ptm} --tool {tool} --cpu {cp}".format(
			dir=self.pi_pm_app_path,
			scr=self.target_script,
			testname=self.name,
			operatingsystem=self.operating_system,
			tdp=self.tdp_val,
			ptm=self.ptu_runtime,
			tool = self.tool,
			cp = self.cpu_type
		)
		self.result = self._tester.sut_control.os_access.run_command(cmd, verify=False, retry=0)
		self._tester.test_logger.log("Standalone test details **********")
		self._tester.test_logger.log(str(self.result))
		self.collect_output_logs(self.result.combined_lines)

		#Log copy to host
		self._tester.test_logger.log("PIPM app log is :{}".format(self.pipm_app_log))
		self._tester.test_logger.log("PTU Monitor app log for CT1 workload flow is :{}".format(self.ptu_log_file))
		if self.tool == "ptu":
			self._tester.test_logger.log("PTU Monitor app log for CT2 Workload flow is :{}".format(self.ptu_log_file1))
			self.test_logs.append(self.ptu_log_file1)
		
		self.test_logs.append(self.pipm_app_log)
		self.test_logs.append(self.ptu_log_file)
		
		self.copy_pi_pm_logs()
		self.pipm_parse_log(self.pipm_app_log)

		
############################################################################################################
#######################################################################################################

#CRAUTO-11062
class PI_PM_ActiveIdle_C0_All_cores_Test_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_ActiveIdle_C0_All_cores_Test_Linux"}

	def __init__(self):
		super(PI_PM_ActiveIdle_C0_All_cores_Test_Linux, self).__init__()
		self.name = "ACTIVEIDLE_C0_ALL_CORE_LINUX" 
		self.targetlogfolder = "PI_PM_ActiveIdle_C0_All_cores_Test_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.run_ptu = False
		self.check_turbo_flag = False
		self.bios_knob_set = False
	
	def _start(self):
		self.product_class = PI_PM_ActiveIdle_C0_All_cores_Test_Linux_TestEngine
		return self

class PI_PM_ActiveIdle_C0_All_cores_Test_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "This testcase will be used to check ensure all cores run at SSE ACT when all cores are put in C0 Active idle."
	
	def run_pi_pm_main(self):
		
		if self.cpu_type =="SPR":
			#calculating sse act from pysv
			self.frequency_calculator()
			self._tester.test_logger.log("SSE ACT frequency value from _sv_sockets is {}MHZ".format(self.sse_act_val))
		elif self.cpu_type in ["GNR","SRF"]:
			self.gnr_pmutil_frequency_calculator() 
		#Put CPUS in idle State
		self.output = self.all_core_c0_state()
		if self.output == 0:
			self._tester.test_logger.log("PASS:All CPUS are in idle state")
		else:
			self._tester.exit_with_error("FAIL: Failed to put CPUS in idle state")

		self.check_sut_os()

		#start standalone script
		self._tester.test_logger.log("Triggering {}_Testcase. Please wait for sometime to complete test".format(self._config.name))
		cmd = "chmod -R 777 {dir}".format(dir=self.pi_pm_app_path)
		result = self._tester.sut_control.os_access.run_command(cmd, verify=False, retry=0)
		cmd = "cd {dir} && python {dir}/{scr} --test {testname} --os {operatingsystem} --cpu {cpu} --ptu_runtime {ptm} --sse_act_freq {ssef}".format(
			dir=self.pi_pm_app_path, 
			scr=self.target_script, 
			testname=self.name,
			operatingsystem=self.operating_system,
			ptm=self.ptu_runtime,
			cpu=self.cpu_type,
			ssef = self.sse_act_val
			)
			

		self.result = self._tester.sut_control.os_access.run_command(cmd, verify=False, retry=0)
		self._tester.test_logger.log("Standalone test details **********")
		self._tester.test_logger.log(str(self.result))
		self.collect_output_logs(self.result.combined_lines)

		#Log copy to host
		# output_logfile=self._tester.sut_control.os_access.run_command('cd {} && ls -t | head -n1'.format(self.pi_pm_applog_folder)).combined_lines
		# self.applogfile=output_logfile[0]
		# self.pipm_app_log= "{t}/{appfile}".format(t=self.pi_pm_applog_folder, appfile=self.applogfile)
		self.test_logs.append(self.pipm_app_log)
		self.test_logs.append(self.ptu_log_file)
		self.copy_pi_pm_logs()
		self.pipm_parse_log(self.pipm_app_log)


############################################################################################################
#######################################################################################################
#CRAUTO-10964   
class PI_PM_Performance_UFS_Perf_P_Limit_2S_4S_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_Performance_UFS_Perf_P_Limit_2S_4S_Linux"}

	def __init__(self):
		super(PI_PM_Performance_UFS_Perf_P_Limit_2S_4S_Linux, self).__init__()
		self.name = "UFS_PERF_P_LIMIT_LINUX" 
		self.targetlogfolder = "PI_PM_Performance_UFS_Perf_P_Limit_2S_4S_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "PerfPlimitDifferential=0x1,PerfPLimitClipC=0x1F,PerfPLmtThshld=0x0F,PerfPLimitEn=0x01"
		self.bios_knob_set = True
		
	def _start(self):
		self.product_class = PI_PM_Performance_UFS_Perf_P_Limit_2S_4S_Linux_TestEngine
		return self

class PI_PM_Performance_UFS_Perf_P_Limit_2S_4S_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "This testcase will be used to check if the mesh frequencies of each are following each other by the differential value mentioned in the Perf-P Limit configuration ."
	
	def run_pi_pm_main(self):
		if self.os_power_policy != None:
			self._tester.test_logger.log("Checking for os_power_policy")
			self.check_os_power_policy()
		time.sleep(60)
		_sv_sockets = self._tester.sv_control.sv_sockets
		self.mesh_freq = []
		self.plimit_diff_val = []
		self.numa_strings = []
		self.socket_count = int(self._frame.sv_control.socket_count)
		
		output = self._tester.sut_control.os_access.run_command("lscpu | grep Thread").combined_lines
		self.thread_per_core = int(output[0].split(':')[1])
		self._tester.test_logger.log("Threads per core is: {}".format(self.thread_per_core))
		if self.thread_per_core==1:
			numa_cpus_exp = r"(?<=NUMA node\d CPU\(s\):)(?:\s*)(\d+)(?:[,-]?)(\d+)?"
		else:
			numa_cpus_exp = r"(?<=NUMA node\d CPU\(s\):)(?:\s*)(\d+)(?:[,-]?)(\d+)(?:,?)(\d+)(?:-)(\d+)"
		
		
		for soc in range(self.socket_count):
			cmd = "lscpu | grep 'NUMA node{}'".format(soc)
			numaoutput = self._tester.sut_control.os_access.run_command(cmd).combined_lines
			numa_cpus_as_string = re.findall(numa_cpus_exp,numaoutput[0])
			self.numa_strings.append(numa_cpus_as_string)
			self._tester.test_logger.log("NUMA Node output for socket{} is:{}".format(soc,numa_cpus_as_string))
		self._tester.test_logger.log("NUMA list is {}".format(self.numa_strings))

		
		soc_count=0
		self.error_count = 0
		for socket in _sv_sockets:
			self._tester.test_logger.log("Keep Thread from socket {} busy and check the uncore mesh frequency".format(soc_count))
			self._tester.test_logger.log("Check Perf p limit configuration")
			self._tester.test_logger.log("-------------------------Socket {}-------------------------".format(soc_count))
			self.perf_plimit_differential_val = socket.uncore.punit.perf_p_limit_control_cfg.perf_plimit_differential.read()
			self._tester.test_logger.log("Perf P Limit differential value for Socket{} is: {}".format(soc_count, self.perf_plimit_differential_val))
			self.plimit_diff_val.append(self.perf_plimit_differential_val)
			self._tester.test_logger.log("-------------------------------------------------------------------")
			self._tester.test_logger.log("Perf P Limit differential value recorded successfully")

		
			if soc_count == 0:  
			#pmutil
				self.busy_thread =random.randint(int(self.numa_strings[0][0][0]),int(self.numa_strings[0][0][1]))
			else:
				self.busy_thread =random.randint(int(self.numa_strings[1][0][0]),int(self.numa_strings[1][0][1]))

			t = thread_with_trace(target = self.pmutil_core_busy,args=(self.busy_thread,soc_count,))
			t.start()
			time.sleep(10)
			
			self._tester.test_logger.log("check the uncore mesh frequency for 40 seconds")
			end_time = time.time() + 40
			while time.time()<end_time:
				for socket in _sv_sockets:
					self.soc_mesh = socket.uncore.pcodeio_map.io_wp_cfc_cv_ps_0.ratio.read()
					#self._tester.test_logger.log(str(self.soc_mesh))
					self.mesh_freq.append(self.soc_mesh)

			t.kill()
			self.stop_pmutil_threads()
			time.sleep(5)
			self._tester.test_logger.log("Logged Mesh Frequency Values are : {}".format(self.mesh_freq))
			self.diffrential_freqs = [freq - self.mesh_freq[count-1] for count,freq in enumerate(self.mesh_freq)][1:]

			self._tester.test_logger.log("Differential between Logged Mesh Frequency Values are : {}".format(self.diffrential_freqs))
			self._tester.test_logger.log("Comparing uncore mesh frequency differential with Perf P Limit differential from plimit configuration")
			for freq in self.diffrential_freqs:
				if abs(freq)== int(self.plimit_diff_val[0]):
					self._tester.test_logger.log("PASS: Frequencies of each socket are following each other by the differential value {} mentioned in the Perf-P Limit configuration".format(self.plimit_diff_val[0]))
				else:
					self._tester.test_logger.log("FAIL:  Frequencies of each socket are not following each other by the differential value {}".format(self.plimit_diff_val[0]))
					self.error_count = self.error_count+1
			soc_count += 1

		if self.socket_count == 2:
			err_val = 4
		elif self.socket_count == 4:
			err_val = 8

		if self.error_count <= err_val:
			self._tester.test_logger.log("PASS: Frequencies of each socket are following each other by the differential value")
		else:
			self._tester.test_logger.log("Check Logs carefully,Collectively for all sockets {} incorrect values are ignored".format(err_val))
			self._tester.test_logger.log("Failures are Exceeding set limit so Test Considered as FAIL")
			self._tester.exit_with_error("FAIL: Frequencies are not following each other by the differential value")

	def run_pi_pm_post(self):
		self._tester.test_logger.log("Post Test Events completed")

#######################################################################################################
#CRAUTO-9399
#######################################################################################################
class PI_PM_TurboBoost_TurboTablesVerification_Test_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_TurboBoost_TurboTablesVerification_Test_Linux"}

	def __init__(self):
		super(PI_PM_TurboBoost_TurboTablesVerification_Test_Linux, self).__init__()
		self.name = "TURBOTABLEVERIFICATION_LINUX" 
		self.targetlogfolder = "PI_PM_TurboBoost_TurboTablesVerification_Test_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS                                 
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "TurboMode=0x1" 
		self.bios_knob_set = False
		self.test_step = 0
	
	def _start(self):
		self.product_class = PI_PM_TurboBoost_TurboTablesVerification_Test_common_TestEngine
		return self

#######################################################################################################
#######################################################################################################
class PI_PM_TurboTablesVerification_SSE_Test_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_TurboTablesVerification_SSE_Test_Linux"}

	def __init__(self):
		super(PI_PM_TurboTablesVerification_SSE_Test_Linux, self).__init__()
		self.name = "TURBOTABLEVERIFICATION_CORECOUNT_SSE_LINUX" 
		self.targetlogfolder = "PI_PM_TurboTablesVerification_SSE_Test_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "TurboMode=0x1" 
		self.bios_knob_set = False
		self.test_step = 1
	
	def _start(self):
		self.product_class = PI_PM_TurboBoost_TurboTablesVerification_Test_common_TestEngine
		return self

######################################################################################################
#######################################################################################################
class PI_PM_TurboTablesVerification_AVX2_Test_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_TurboTablesVerification_AVX2_Test_Linux"}

	def __init__(self):
		super(PI_PM_TurboTablesVerification_AVX2_Test_Linux, self).__init__()
		self.name = "TURBOTABLEVERIFICATION_CORECOUNT_AVX2_LINUX" 
		self.targetlogfolder = "PI_PM_TurboTablesVerification_AVX2_Test_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "TurboMode=0x1" 
		self.bios_knob_set = False
		self.test_step = 2
	
	def _start(self):
		self.product_class = PI_PM_TurboBoost_TurboTablesVerification_Test_common_TestEngine
		return self

######################################################################################################
#######################################################################################################
class PI_PM_TurboTablesVerification_AVX512_Test_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_TurboTablesVerification_AVX512_Test_Linux"}

	def __init__(self):
		super(PI_PM_TurboTablesVerification_AVX512_Test_Linux, self).__init__()
		self.name = "TURBOTABLEVERIFICATION_CORECOUNT_AVX512_LINUX" 
		self.targetlogfolder = "PI_PM_TurboTablesVerification_AVX512_Test_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "TurboMode=0x1" 
		self.bios_knob_set = False
		self.test_step = 3
	
	def _start(self):
		self.product_class = PI_PM_TurboBoost_TurboTablesVerification_Test_common_TestEngine
		return self

######################################################################################################
#######################################################################################################
#CRAUTO-9398
# #################################################################################################
class PI_PM_TurboBoost_TurboTablesVerification_Test_Windows(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_TurboBoost_TurboTablesVerification_Test__Windows"}

	def __init__(self):
		super(PI_PM_TurboBoost_TurboTablesVerification_Test_Windows, self).__init__()
		self.name = "TURBOTABLEVERIFICATION_WINDOWS" 
		self.targetlogfolder = "PI_PM_TurboBoost_TurboTablesVerification_Test_Windows"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.WINDOWS]
		self.suite_membership = [SUITE_TYPE.WINDOWS_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "TurboMode=0x1" 
		self.run_ptu = False
		self.check_turbo_flag = False
		self.bios_knob_set = False
		self.test_step = 0

	def _start(self):
		self.product_class = PI_PM_TurboBoost_TurboTablesVerification_Test_common_TestEngine
		return self

#######################################################################################################
# #################################################################################################
class PI_PM_TurboTablesVerification_SSE_Test_Windows(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_TurboTablesVerification_SSE_Test_Windows"}

	def __init__(self):
		super(PI_PM_TurboTablesVerification_SSE_Test_Windows, self).__init__()
		self.name = "TURBOTABLEVERIFICATION_SSE_WINDOWS" 
		self.targetlogfolder = "PI_PM_TurboTablesVerification_SSE_Test_Windows"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.WINDOWS]
		self.suite_membership = [SUITE_TYPE.WINDOWS_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "TurboMode=0x1" 
		self.run_ptu = False
		self.check_turbo_flag = False
		self.bios_knob_set = False
		self.test_step = 1

	def _start(self):
		self.product_class = PI_PM_TurboBoost_TurboTablesVerification_Test_common_TestEngine
		return self
#########################################################################################################
# #################################################################################################
class PI_PM_TurboTablesVerification_AVX2_Test_Windows(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_TurboTablesVerification_AVX2_Test_Windows"}

	def __init__(self):
		super(PI_PM_TurboTablesVerification_AVX2_Test_Windows, self).__init__()
		self.name = "TURBOTABLEVERIFICATION_AVX2_WINDOWS" 
		self.targetlogfolder = "PI_PM_TurboTablesVerification_AVX2_Test_Windows"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.WINDOWS]
		self.suite_membership = [SUITE_TYPE.WINDOWS_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "TurboMode=0x1" 
		self.run_ptu = False
		self.check_turbo_flag = False
		self.bios_knob_set = False
		self.test_step = 2

	def _start(self):
		self.product_class = PI_PM_TurboBoost_TurboTablesVerification_Test_common_TestEngine
		return self
########################################################################################################
# #################################################################################################
class PI_PM_TurboTablesVerification_AVX512_Test_Windows(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_TurboTablesVerification_AVX512_Test__Windows"}

	def __init__(self):
		super(PI_PM_TurboTablesVerification_AVX512_Test_Windows, self).__init__()
		self.name = "TURBOTABLEVERIFICATION_AVX512_WINDOWS" 
		self.targetlogfolder = "PI_PM_TurboTablesVerification_AVX512_Test_Windows"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.WINDOWS]
		self.suite_membership = [SUITE_TYPE.WINDOWS_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "TurboMode=0x1" 
		self.run_ptu = False
		self.check_turbo_flag = False
		self.bios_knob_set = False
		self.test_step = 3

	def _start(self):
		self.product_class = PI_PM_TurboBoost_TurboTablesVerification_Test_common_TestEngine
		return self
#####################################################################################################

class PI_PM_TurboBoost_TurboTablesVerification_Test_common_TestEngine(PI_PM_TestEngine):
	class_lable = "Collect the frequency of CPU and observe whether it meets the requirements"
	
	def run_pi_pm_main(self):

		self.test_step = self._config.test_step
		self._tester.test_logger.log("*********************************Test step is {} : Running {} Test******************************".format(self._config.test_step,self.name))
	
		if self.cpu_type == "SPR":
			self._tester.test_logger.log("Running test on SPR")
	
			if self._tester.sut_control.sut_os_type in [OS_TYPE.FEDORA.name, OS_TYPE.SLES.name, OS_TYPE.CENTOS.name, OS_TYPE.REDHAT.name, OS_TYPE.CLEARLINUX.name]:
				self.spr_pmutil_calculator()
				
			self.frequency_calculator()

		elif self.cpu_type in ["GNR","SRF"]:
			self._tester.test_logger.log("Running test on GNR")
			if self._tester.sut_control.sut_os_type in [OS_TYPE.FEDORA.name, OS_TYPE.SLES.name, OS_TYPE.CENTOS.name, OS_TYPE.REDHAT.name, OS_TYPE.CLEARLINUX.name]:
				self.gnr_pmutil_frequency_calculator()
			elif self._tester.sut_control.sut_os_type == OS_TYPE.WINDOWS.name:
				self.gnr_get_pysv_freq()

		self.avx2_p1 = self.avx2_freq_val
		self.avx512_p1 = self.avx512_freq_val
		self.sse_p1 = self.sse_freq_val
		
		self._tester.test_logger.log("SSE BASE Frequency value from pythonsv is {}MHZ".format(self.sse_p1))
		self._tester.test_logger.log("AVX2  BASE Frequency value from pythonsv is {}MHZ".format(self.avx2_p1))
		self._tester.test_logger.log("AVX512 BASE Frequency value from pythonsv is {}MHZ".format(self.avx512_p1))

		self._tester.test_logger.log("Turbo Frequency checks fuses from Pythonsv")
		self.sse_freqs = self.get_sse_bucket_freq()
		self.avx2_freqs = self.get_avx2_bucket_freq()
		self.avx512_freqs = self.get_avx512_bucket_freq()
		for i in range(3):
			if i == 0:
				for freq in range(len(self.sse_freqs)) :
					self._tester.test_logger.log("Turbo SSE frequency for Bucket{} is : {}".format(freq,self.sse_freqs[freq]))
			if i == 1 :
				for freq in range(len(self.avx2_freqs)) :
					self._tester.test_logger.log("Turbo AVX2 frequency for Bucket{} is : {}".format(freq,self.avx2_freqs[freq]))

			if i == 2:
				for freq in range(len(self.avx2_freqs)) :
					self._tester.test_logger.log("Turbo AVX512 frequency for Bucket{} is : {}".format(freq,self.avx2_freqs[freq]))


		self._tester.test_logger.log("Number of cores check using pythonsv:")
		self.core_vals = self.get_num_cores()
		self._tester.test_logger.log("Num core list is {}".format(self.core_vals))
		for core in range(len(self.core_vals)):
			self._tester.test_logger.log("Numacore{} is : {}".format(core, self.core_vals[core]))

		self.check_sut_os()

		#For Bucket 7
		self._tester.test_logger.log("Starting Testflow for Bucket 7")
		self._tester.test_logger.log("Total Number of cores for Bucket 7 : {}".format(self.numcore7))
		self._tester.test_logger.log("Write Disable Bitmap: [0] on all the sockets for bucket 7")
		self.socket_count = int(self._frame.sv_control.socket_count)
		if self.socket_count == 2:
			self.knob ='CoreDisableMask_0=0x0 , CoreDisableMask_1=0x0'
		elif self.socket_count == 4:
			self.knob ='CoreDisableMask_0=0x0 , CoreDisableMask_1=0x0, CoreDisableMask_2=0x0 , CoreDisableMask_3=0x0'       
		self._tester.test_logger.log("Bios knob to set : {}".format(self.knob))
		self._tester.sut_control.set_bios_knob(self.knob)
		self._tester.tester_functions.ac_power_cycle()
		self._tester.test_logger.log("Triggering Workloads for Bucket 7 frequencies")
		self.standalone_engine(self.sse_bucket7_val,7)
		self.copy_log_host()

		#For Bucket 7 & 6
		self.turbo_table_flow(numcore_old = self.numcore7, numcore_new = self.numcore6 , val_old = 7, val_new = 6, freq_val = self.sse_bucket6_val)
		#For Bucket 6 & 5
		self.turbo_table_flow(numcore_old = self.numcore6, numcore_new = self.numcore5 , val_old = 6, val_new = 5, freq_val = self.sse_bucket5_val)
		#For Bucket 5 & 4
		self.turbo_table_flow(numcore_old = self.numcore5, numcore_new = self.numcore4 , val_old = 5, val_new = 4, freq_val = self.sse_bucket4_val)
		#For Bucket 4 & 3
		self.turbo_table_flow(numcore_old = self.numcore4, numcore_new = self.numcore3 , val_old = 4, val_new = 3, freq_val = self.sse_bucket3_val)
		#For Bucket 3 & 2
		self.turbo_table_flow(numcore_old = self.numcore3, numcore_new = self.numcore2 , val_old = 3, val_new = 2, freq_val = self.sse_bucket2_val)
		#For Bucket 2 & 1
		self.turbo_table_flow(numcore_old = self.numcore2, numcore_new = self.numcore1 , val_old = 2, val_new = 1, freq_val = self.sse_bucket1_val)
		#For Bucket 1 & 1
		self.turbo_table_flow(numcore_old = self.numcore1, numcore_new = self.numcore0 , val_old = 1, val_new = 0, freq_val = self.sse_bucket0_val)
		
		if self.bios_knob_set:
			self._tester.test_logger.log("Reverting BitMap Bios Knobs to default.") 
			self._tester.sut_control.reset_bios_knob()
			self._tester.tester_functions.ac_power_cycle()

	def standalone_engine(self,bucket_sse_freq,bucket_num):
		if self._tester.sut_control.sut_os_type in [OS_TYPE.FEDORA.name, OS_TYPE.SLES.name, OS_TYPE.CENTOS.name, OS_TYPE.REDHAT.name, OS_TYPE.CLEARLINUX.name]:
			self._tester.test_logger.log("Triggering {}_Testcase. Please wait for sometime to complete test".format(self._config.name))
			cmd = "python {dir}/{scr} --test {testname} --os {operatingsystem}  --sse_p1_freq {ssep1} --sse_act_freq {ssef} --avx2_freq {af2} --avx512_freq {af512} --bucket_val {b_val} --test_step {ts} --cpu {ct}".format(
				dir=self.pi_pm_app_path,
				scr=self.target_script,
				testname=self.name,
				operatingsystem=self.operating_system,
				ssep1 = self.sse_p1,
				ssef = bucket_sse_freq,
				af2=self.avx2_p1,
				af512 = self.avx512_p1,
				b_val = bucket_num,
				ts= self.test_step,
				ct = self.cpu_type)
			self.result = self._tester.sut_control.os_access.run_command(cmd, verify=False, retry=0)
			self._tester.test_logger.log("Standalone test details **********")
			self._tester.test_logger.log(str(self.result))
			self.collect_output_logs(self.result.combined_lines)
			self.test_logs.append(self.pipm_app_log)

			if self.test_step == 0:
				self.test_logs.append('{t}/SoCWatchOutput.csv'.format(t=self.pi_pm_applog_folder))
		
			elif self.test_step == 1 or self.test_step == 2 or self.test_step == 3:
				self._tester.test_logger.log("PTU Monitor app log is :{}".format(self.ptu_log_file))
				self.test_logs.append(self.ptu_log_file)
			
		elif self._tester.sut_control.sut_os_type == OS_TYPE.WINDOWS.name:
			#start standalone script
			self._tester.test_logger.log("Triggering {}_Testcase. Please wait for sometime to complete test".format(self._config.name))
			cmd = "powershell.exe; python {dir}//{scr} --test {testname} --os {operatingsystem}  --sse_p1_freq {ssep1} --sse_act_freq {ssef} --avx2_freq {af2} --avx512_freq {af512} --bucket_val {b_val} --test_step {ts} --tool {wl}".format(
				dir=self.pi_pm_app_path_win,
				scr=self.target_script,
				testname=self.name,
				operatingsystem=self.operating_system,
				ssep1 = self.sse_p1,
				ssef = bucket_sse_freq,
				af2=self.avx2_p1,
				af512 = self.avx512_p1,
				b_val = bucket_num,
				ts = self.test_step,
				ct = self.cpu_type,
				wl =self.tool)
			self.result = self._tester.sut_control.os_access.run_command(cmd, verify=False, retry=0)
			self._tester.test_logger.log("Completed running the standalone.....")
			self._tester.test_logger.log(str(self.result))
			self.collect_output_logs(self.result.combined_lines)
			self._tester.test_logger.log("PIPM app log is :{}".format(self.pipm_app_log))

			self.test_logs.append(self.pipm_app_log)
			self.test_logs.append( os.path.join( self.socwatch_path_win, 'SoCWatchOutput.csv'))

	def copy_log_host(self):
		# output_logfile=self._tester.sut_control.os_access.run_command('cd {} && ls -t | head -n1'.format(self.pi_pm_applog_folder)).combined_lines
		# self.applogfile=output_logfile[0]
		# self.pipm_app_log= "{t}/{appfile}".format(t=self.pi_pm_applog_folder, appfile=self.applogfile)
		self.copy_pi_pm_logs()
		self.pipm_parse_log_TTL(self.pipm_app_log)

	def turbo_table_flow(self,numcore_old,numcore_new,val_old,val_new,freq_val):
		self.bucket_core_diff = int(numcore_old - numcore_new)
		if self.bucket_core_diff == 0:
			self._tester.test_logger.log("The corecount For Bucket {} is same as Bucket {} so Frequency values are also same".format(val_new,val_old))
			self._tester.test_logger.log("So Skipping the WORKLOAD flow for Bucket {}".format(val_new))
		else:
			self._tester.test_logger.log("***********************Starting Testflow for BUCKET {}******************************".format(val_new))
			self._tester.test_logger.log("Reducing the Active core count to: {}".format(numcore_new))
			if numcore_new == 6:
				self._tester.test_logger.log("Bucket Number is : {}".format(numcore_new))
				self.get_available_bitmap()
				self.disabled_bitmap_calculator(self.socket_value,self.bucket_core_diff)
			else:
				self._tester.test_logger.log("Bucket Number is : {}".format(numcore_new))
				self.get_resolved_core_bitmap()
				self.disabled_bitmap_calculator(self.resolved_socket_value,self.bucket_core_diff)
			
			self._tester.test_logger.log("Reduced core count is : {}".format(self.core_count1))
			self._tester.test_logger.log("Final Disable Bitmap per socket is {}".format(self.final_dict))
			self.get_disablemap_knob()
			self._tester.sut_control.set_bios_knob(self.knob)
			self._tester.tester_functions.ac_power_cycle()
			self.bios_knob_set=True
			self._tester.test_logger.log("*********************Triggering Workloads for BUCKET {} frequencies********************".format(val_new))
			self.standalone_engine(freq_val,val_new)
			self.copy_log_host()
			self._tester.test_logger.log("Autolog saved to {}.".format(self._tester._test_logger.auto_log_path))
			self._tester.test_logger.log("PIPM Applog for Bucket {} is saved at {}.".format(val_new,self.pipm_app_log))
		
	def run_pi_pm_post(self):
		self._tester.test_logger.log("Resuming post test events...")
		self.final_parser()

	
################################################################################################
#CRAUTO-12847
################################################################################################
class PI_PM_EET_Enable_Performance_Mode_Test_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_EET_Enable_Performance_Mode_Test_Linux"}

	def __init__(self):
		super(PI_PM_EET_Enable_Performance_Mode_Test_Linux, self).__init__()
		self.name = "EET_STATE_LINUX" 
		self.targetlogfolder = "PI_PM_EET_Enable_Performance_Mode_Test_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]                           
		self.bios_knob_set = "TurboMode=0x0,EETurboDisable=0x0,EetOverrideEn=0x1,ProcessorHWPMEnable=0x3,"
		self.bios_knob_set = True

	def _start(self):
		self.product_class = PI_PM_EET_Enable_Performance_Mode_Test_Linux_TestEngine
		return self

class PI_PM_EET_Enable_Performance_Mode_Test_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "This testcase will be used when PCU detects high utilization on core, the turbo frequency will be increased. "

	def run_pi_pm_main(self):
		_sv_sockets = self._tester.sv_control.sv_sockets
		self.soc_num = int(self._frame.sv_control.socket_count)
		self._tester.test_logger.log("Number of scokets are {}".format(self.soc_num))
		self._tester.sut_control.itp_control.itp_halt()
		soc_count = 0
		for socket in _sv_sockets:
			self._tester.test_logger.log("***********Check if EET Mode is set to Fine grained mode : Socket {}**************".format(soc_count))
			#self._tester.test_logger.log("socket data {}".format(socket.cpu.cores.threads.ucode_cr_energy_performance_bias.energy_policy.read()))
			self.eet_mode = socket.uncore.punit.dynamic_perf_power_ctl_cfg.eet_override_enable.read()
			#self._tester.test_logger.log(self.eet_mode)
			if int(str(self.eet_mode),16) == 1:
				self._tester.test_logger.log("PASS : EET is set to Fine Grained Mode for socket {}".format(soc_count))
			else:
				self._tester.test_logger.log("EET Mode is not set to Fine grained Mode so setting it now")
				socket.uncore.punit.dynamic_perf_power_ctl_cfg.eet_override_enable=1
				time.sleep(2)
				self._tester.test_logger.log("PASS : EET is set to Fine Grained Mode for socket {}".format(soc_count))
			soc_count += 1
		_sv_sockets = self._tester.sv_control.sv_sockets
		soc_count = 0
		for socket in _sv_sockets:  
			self._tester.test_logger.log("Check the Energy Efficiency policy is set to Performance mode {}".format(socket.cpu.cores.threads.ucode_cr_energy_performance_bias.energy_policy.read()))
			register_val = socket.cpu.cores.threads.ucode_cr_energy_performance_bias.energy_policy.read()
			#self._tester.test_logger.log("energy_policy values are : {}".format(register_val))
			register_val_list = list(register_val)
			#self._tester.test_logger.log(register_val_list)
			if int(str(register_val_list[0]),16) == 0:
				self._tester.test_logger.log("PASS : Energy Efficiency policy is in Performance mode for Socket {}".format(soc_count))
			else:
				self._tester.test_logger.log("Currently Energy Efficiency policy is not set to Performance mode,So writing to register")
				socket.cpu.cores.threads.ucode_cr_energy_performance_bias.write(0x00000000)
				time.sleep(2)
				self._tester.test_logger.log("PASS : Energy Efficiency policy is in Performance mode for Socket {}".format(soc_count))
			soc_count += 1

		self._tester.sut_control.itp_control.itp_go()
		#self._tester.sut_control.pysv_mainframe.itp_control.ITP_GO_EVENT.add_rcvr_post( self._tester.sut_control.wait_for_os)
		self._tester.sut_control.itp_control.ITP_GO_EVENT.bypass_post_rcvrs( self._tester.sut_control._handel_os_down)
		
		time.sleep(10)

		self._tester.test_logger.log("Fetching Frequncy Values from pysv")
		self.frequency_calculator()
		self._tester.test_logger.log(" Frequency value from _sv_sockets for SSE P1 {}MHZ".format(self.sse_freq_val))
		self._tester.test_logger.log(" frequency value from _sv_sockets for SSE ACT {}MHZ".format(self.sse_act_val))
		self.check_sut_os()

		#start standalone script
		self._tester.test_logger.log("Triggering {}_Testcase. Please wait for sometime to complete test".format(self._config.name))
		cmd = "chmod -R 777 {dir}".format(dir=self.pi_pm_app_path)
		result = self._tester.sut_control.os_access.run_command(cmd, verify=False, retry=0)
		cmd = "cd {dir} && python {dir}/{scr} --test {testname} --os {operatingsystem} --sse_p1_freq {ssep1} --sse_act_freq {ssef} --ptu_runtime {ptm}".format(
			dir=self.pi_pm_app_path, 
			scr=self.target_script, 
			testname=self.name,
			operatingsystem=self.operating_system,
			ssep1 = self.sse_freq_val,
			ssef = self.sse_act_val,
			ptm=self.ptu_runtime
			)
		self.result = self._tester.sut_control.os_access.run_command(cmd, verify=False, retry=0)
		self._tester.test_logger.log("Standalone test details **********")
		self._tester.test_logger.log(str(self.result))
		self.collect_output_logs(self.result.combined_lines)

		#Log copy to host
		# output_logfile=self._tester.sut_control.os_access.run_command('cd {} && ls -t | head -n1'.format(self.pi_pm_applog_folder)).combined_lines
		# self.applogfile=output_logfile[0]
		# self.pipm_app_log_1= "{t}/{appfile}".format(t=self.pi_pm_applog_folder, appfile=self.applogfile)
		self._tester.test_logger.log("PIPM app log is :{}".format(self.pipm_app_log))
		self._tester.test_logger.log("PTU app log is :{}".format(self.ptu_log_file))
		self.test_logs.append(self.pipm_app_log)
		self.test_logs.append(self.ptu_log_file)
		self.copy_pi_pm_logs()
		self.pipm_parse_log(self.pipm_app_log)

# #################################################################################################
############################################################################################################
#CRAUTO-13368
############################################################################################################
class PI_PM_SSE_GNR_Turbo_Enabled_Base_Frequency_Linpack_Test_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_SSE_GNR_Turbo_Enabled_Base_Frequency_Linpack_Test_Linux"}

	def __init__(self):
		super(PI_PM_SSE_GNR_Turbo_Enabled_Base_Frequency_Linpack_Test_Linux, self).__init__()
		self.name = "SSE_GNR_TURBO_ENABLED_BASE_FREQUENCY_LINPACK_LINUX" 
		self.targetlogfolder = "PI_PM_SSE_GNR_Turbo_Enabled_Base_Frequency_Linpack_Test_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "TurboMode=0x1"
		self.run_ptu = False
		self.check_turbo_flag = False
		self.bios_knob_set = False
	
	def _start(self):
		self.product_class = PI_PM_SSE_GNR_Turbo_Enabled_Base_Frequency_Linpack_Test_Linux_TestEngine
		return self

class PI_PM_SSE_GNR_Turbo_Enabled_Base_Frequency_Linpack_Test_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "This Test Case verifies processor AVX2 Base frequency by running optimized linpack test."
	
	def run_pi_pm_main(self):
		if self.cpu_type in ["GNR","SRF"]:
			self._tester.test_logger.log("Running the test on GNR....")
			self._tester.test_logger.log("**********calculating SSE P1 and SSE ACT using pmutil for LINUX Target******************")
			self.gnr_pmutil_frequency_calculator()

		else:
			self._tester.exit_with_error("Test Case is implemeted only for GNR, please Select correct Platform")

		self.check_sut_os()
		
		#start standalone script
		self._tester.test_logger.log("Triggering {}_Testcase. Please wait for sometime to complete test".format(self._config.name))
		cmd = "chmod -R 777 {dir}".format(dir=self.pi_pm_app_path)
		result = self._tester.sut_control.os_access.run_command(cmd, verify=False, retry=0)
		cmd = "cd {dir} && python {dir}/{scr} --test {testname} --os {operatingsystem} --turbo True  --sse_act_freq {ssef} --sse_p1_freq {ssep1}".format(
			dir=self.pi_pm_app_path, 
			scr=self.target_script, 
			testname=self.name,
			operatingsystem=self.operating_system,
			ssef=self.sse_act_val,
			ssep1=self.sse_freq_val)

		self.result = self._tester.sut_control.os_access.run_command(cmd, verify=False, retry=0)
		self._tester.test_logger.log("Standalone test details **********")
		self._tester.test_logger.log(str(self.result))

		#Log copy to host
		self.collect_output_logs(self.result.combined_lines)
		self._tester.test_logger.log("PIPM app log is:{}".format(self.pipm_app_log))
		self.test_logs.append(self.pipm_app_log)
		self.test_logs.append('{t}/SoCWatchOutput.csv'.format(t=self.pi_pm_applog_folder))

############################################################################################################
############################################################################################################
#CRAUTO-13370
############################################################################################################
class PI_PM_SSE_GNR_Turbo_Disabled_Base_Frequency_Linpack_Test_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_SSE_Turbo_Disabled_Base_Frequency_Linpack_Test_Linux"}

	def __init__(self):
		super(PI_PM_SSE_GNR_Turbo_Disabled_Base_Frequency_Linpack_Test_Linux, self).__init__()
		self.name = "SSE_GNR_TURBO_DISABLED_BASE_FREQUENCY_LINPACK_LINUX" 
		self.targetlogfolder = "PI_PM_SSE_GNR_Turbo_Disabled_Base_Frequency_Linpack_Test_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "TurboMode=0x1"
		self.run_ptu = False
		self.check_turbo_flag = False
		self.bios_knob_set = False
	
	def _start(self):
		self.product_class = PI_PM_SSE_GNR_Turbo_Disabled_Base_Frequency_Linpack_Test_Linux_TestEngine
		return self

class PI_PM_SSE_GNR_Turbo_Disabled_Base_Frequency_Linpack_Test_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "This Test Case verifies processor AVX2 Base frequency by running optimized linpack test."
	
	def run_pi_pm_main(self):
		if self.cpu_type in ["GNR","SRF"]:
			self._tester.test_logger.log("Running the test on GNR....")
			self._tester.test_logger.log("**********calculating SSE P1 using pmutil for LINUX Target******************")
			self.gnr_pmutil_frequency_calculator()
		else:
			self._tester.exit_with_error("Test Case is implemeted only for GNR, please Select correct Platform")

		self.check_sut_os()
		
		#start standalone script
		self._tester.test_logger.log("Triggering {}_Testcase. Please wait for sometime to complete test".format(self._config.name))
		cmd = "chmod -R 777 {dir}".format(dir=self.pi_pm_app_path)
		result = self._tester.sut_control.os_access.run_command(cmd, verify=False, retry=0)
		cmd = "cd {dir} && python {dir}/{scr} --test {testname} --os {operatingsystem} --sse_p1_freq {ssep1}".format(
			dir=self.pi_pm_app_path, 
			scr=self.target_script, 
			testname=self.name,
			operatingsystem=self.operating_system,
			ssep1=self.sse_freq_val)

		self.result = self._tester.sut_control.os_access.run_command(cmd, verify=False, retry=0)
		self._tester.test_logger.log("Standalone test details **********")
		self._tester.test_logger.log(str(self.result))

		#Log copy to host
		self.collect_output_logs(self.result.combined_lines)
		self._tester.test_logger.log("PIPM app log is:{}".format(self.pipm_app_log))
		self.test_logs.append(self.pipm_app_log)
		self.test_logs.append('{t}/SoCWatchOutput.csv'.format(t=self.pi_pm_applog_folder))

############################################################################################################
############################################################################################################
#CRAUTO-13371
############################################################################################################
class PI_PM_AVX2_Turbo_Enabled_Base_Frequency_Linpack_Test_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_AVX2_Turbo_Enabled_Base_Frequency_Linpack_Test_Linux"}

	def __init__(self):
		super(PI_PM_AVX2_Turbo_Enabled_Base_Frequency_Linpack_Test_Linux, self).__init__()
		self.name = "AVX2_TURBO_ENABLED_BASE_FREQUENCY_LINPACK_LINUX" 
		self.targetlogfolder = "PI_PM_AVX2_Turbo_Enabled_Base_Frequency_Linpack_Test_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "TurboMode=0x1"
		self.run_ptu = False
		self.check_turbo_flag = False
		self.bios_knob_set = False
	
	def _start(self):
		self.product_class = PI_PM_AVX2_Turbo_Enabled_Base_Frequency_Linpack_Test_Linux_TestEngine
		return self

class PI_PM_AVX2_Turbo_Enabled_Base_Frequency_Linpack_Test_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "This Test Case verifies processor AVX2 Base frequency by running optimized linpack test."
	
	def run_pi_pm_main(self):
		if self.cpu_type in ["GNR","SRF"]:
			self._tester.test_logger.log("Running the test on GNR....")
			self._tester.test_logger.log("**********calculating AVX2 P1 and SSE ACT using pmutil for LINUX Target******************")
			self.gnr_pmutil_frequency_calculator()
		else:
			self._tester.exit_with_error("Test Case is implemeted only for GNR, please Select correct Platform")

		self.check_sut_os()
		
		#start standalone script
		self._tester.test_logger.log("Triggering {}_Testcase. Please wait for sometime to complete test".format(self._config.name))
		cmd = "chmod -R 777 {dir}".format(dir=self.pi_pm_app_path)
		result = self._tester.sut_control.os_access.run_command(cmd, verify=False, retry=0)
		cmd = "cd {dir} && python {dir}/{scr} --test {testname} --os {operatingsystem} --turbo True --avx2_freq {af2} --sse_act_freq {ssef}".format(
			dir=self.pi_pm_app_path, 
			scr=self.target_script, 
			testname=self.name,
			operatingsystem=self.operating_system,
			af2=self.avx2_freq_val,
			ssef=self.sse_act_val)

		self.result = self._tester.sut_control.os_access.run_command(cmd, verify=False, retry=0)
		self._tester.test_logger.log("Standalone test details **********")
		self._tester.test_logger.log(str(self.result))

		#Log copy to host
		self.collect_output_logs(self.result.combined_lines)
		self._tester.test_logger.log("PIPM app log is:{}".format(self.pipm_app_log))
		self.test_logs.append(self.pipm_app_log)
		self.test_logs.append('{t}/SoCWatchOutput.csv'.format(t=self.pi_pm_applog_folder))

############################################################################################################
#CRAUTO-13372
############################################################################################################
class PI_PM_AVX2_Turbo_Disabled_Base_Frequency_Linpack_Test_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_AVX2_Turbo_Disabled_Base_Frequency_Linpack_Test_Linux"}

	def __init__(self):
		super(PI_PM_AVX2_Turbo_Disabled_Base_Frequency_Linpack_Test_Linux, self).__init__()
		self.name = "AVX2_TURBO_DISABLED_BASE_FREQUENCY_LINPACK_LINUX" 
		self.targetlogfolder = "PI_PM_AVX2_Turbo_Disabled_Base_Frequency_Linpack_Test_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "TurboMode=0x0"
		self.run_ptu = False
		self.check_turbo_flag = False
		self.bios_knob_set = False
	
	def _start(self):
		self.product_class = PI_PM_AVX2_Turbo_Disabled_Base_Frequency_Linpack_Test_Linux_TestEngine
		return self

class PI_PM_AVX2_Turbo_Disabled_Base_Frequency_Linpack_Test_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "This Test Case verifies processor AVX2 Base frequency by running optimized linpack test."
	
	def run_pi_pm_main(self):
		if self.cpu_type in ["GNR","SRF"]:
			self._tester.test_logger.log("Running the test on GNR....")
			self._tester.test_logger.log("**********calculating AVX2 P1 and SSE P1 using pmutil for LINUX Target******************")
			self.gnr_pmutil_frequency_calculator()
		else:
			self._tester.exit_with_error("Test Case is implemeted only for GNR, please Select correct Platform")

		self.check_sut_os()
		
		#start standalone script
		self._tester.test_logger.log("Triggering {}_Testcase. Please wait for sometime to complete test".format(self._config.name))
		cmd = "chmod -R 777 {dir}".format(dir=self.pi_pm_app_path)
		result = self._tester.sut_control.os_access.run_command(cmd, verify=False, retry=0)
		cmd = "cd {dir} && python {dir}/{scr} --test {testname} --os {operatingsystem}  --avx2_freq {af2} --sse_p1_freq {ssep1}".format(
			dir=self.pi_pm_app_path, 
			scr=self.target_script, 
			testname=self.name,
			operatingsystem=self.operating_system,
			af2=self.avx2_freq_val,
			ssep1=self.sse_freq_val)

		self.result = self._tester.sut_control.os_access.run_command(cmd, verify=False, retry=0)
		self._tester.test_logger.log("Standalone test details **********")
		self._tester.test_logger.log(str(self.result))

		#Log copy to host
		self.collect_output_logs(self.result.combined_lines)
		self._tester.test_logger.log("PIPM app log is:{}".format(self.pipm_app_log))
		self.test_logs.append(self.pipm_app_log)
		self.test_logs.append('{t}/SoCWatchOutput.csv'.format(t=self.pi_pm_applog_folder))

############################################################################################################
#CRAUTO-13373
############################################################################################################
class PI_PM_AVX512_Turbo_Enabled_Base_Frequency_Linpack_Test_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_AVX512_Turbo_Enabled_Base_Frequency_Linpack_Test_Linux"}

	def __init__(self):
		super(PI_PM_AVX512_Turbo_Enabled_Base_Frequency_Linpack_Test_Linux, self).__init__()
		self.name = "AVX512_TURBO_ENABLED_BASE_FREQUENCY_LINPACK_LINUX" 
		self.targetlogfolder = "PI_PM_AVX512_Turbo_Enabled_Base_Frequency_Linpack_Test_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "TurboMode=0x1"
		self.run_ptu = False
		self.check_turbo_flag = False
		self.bios_knob_set = False
	
	def _start(self):
		self.product_class = PI_PM_AVX512_Turbo_Enabled_Base_Frequency_Linpack_Test_Linux_TestEngine
		return self

class PI_PM_AVX512_Turbo_Enabled_Base_Frequency_Linpack_Test_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "This Test Case verifies processor AVX512 Base frequency by running optimized linpack test."
	
	def run_pi_pm_main(self):
		if self.cpu_type in ["GNR","SRF"]:
			self._tester.test_logger.log("Running the test on GNR....")
			self._tester.test_logger.log("**********calculating AVX512 P1 and SSE ACT using pmutil for LINUX Target******************")
			self.gnr_pmutil_frequency_calculator()
		else:
			self._tester.exit_with_error("Test Case is implemeted only for GNR, please Select correct Platform")

		self.check_sut_os()
		
		#start standalone script
		self._tester.test_logger.log("Triggering {}_Testcase. Please wait for sometime to complete test".format(self._config.name))
		cmd = "chmod -R 777 {dir}".format(dir=self.pi_pm_app_path)
		result = self._tester.sut_control.os_access.run_command(cmd, verify=False, retry=0)
		cmd = "cd {dir} && python {dir}/{scr} --test {testname} --os {operatingsystem} --turbo True  --avx512_freq {af2} --sse_act_freq {ssef}".format(
			dir=self.pi_pm_app_path, 
			scr=self.target_script, 
			testname=self.name,
			operatingsystem=self.operating_system,
			af2=self.avx512_freq_val,
			ssef=self.sse_act_val)

		self.result = self._tester.sut_control.os_access.run_command(cmd, verify=False, retry=0)
		self._tester.test_logger.log("Standalone test details **********")
		self._tester.test_logger.log(str(self.result))

		#Log copy to host
		self.collect_output_logs(self.result.combined_lines)
		self._tester.test_logger.log("PIPM app log is:{}".format(self.pipm_app_log))
		self.test_logs.append(self.pipm_app_log)
		self.test_logs.append('{t}/SoCWatchOutput.csv'.format(t=self.pi_pm_applog_folder))

############################################################################################################
#CRAUTO-13374
############################################################################################################
class PI_PM_AVX512_Turbo_Disabled_Base_Frequency_Linpack_Test_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_AVX512_Turbo_Disabled_Base_Frequency_Linpack_Test_Linux"}

	def __init__(self):
		super(PI_PM_AVX512_Turbo_Disabled_Base_Frequency_Linpack_Test_Linux, self).__init__()
		self.name = "AVX512_TURBO_DISABLED_BASE_FREQUENCY_LINPACK_LINUX" 
		self.targetlogfolder = "PI_PM_AVX512_Turbo_Disabled_Base_Frequency_Linpack_Test_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "TurboMode=0x0"
		self.run_ptu = False
		self.check_turbo_flag = False
		self.bios_knob_set = False
	
	def _start(self):
		self.product_class = PI_PM_AVX512_Turbo_Disabled_Base_Frequency_Linpack_Test_Linux_TestEngine
		return self

class PI_PM_AVX512_Turbo_Disabled_Base_Frequency_Linpack_Test_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "This Test Case verifies processor AVX512 Base frequency by running optimized linpack test."
	
	def run_pi_pm_main(self):
		if self.cpu_type in ["GNR","SRF"]:
			self._tester.test_logger.log("Running the test on GNR....")
			self._tester.test_logger.log("**********calculating AVX512 P1 and SSE P1 using pmutil for LINUX Target******************")
			self.gnr_pmutil_frequency_calculator()
		else:
			self._tester.exit_with_error("Test Case is implemeted only for GNR, please Select correct Platform")

		self.check_sut_os()
		
		#start standalone script
		self._tester.test_logger.log("Triggering {}_Testcase. Please wait for sometime to complete test".format(self._config.name))
		cmd = "chmod -R 777 {dir}".format(dir=self.pi_pm_app_path)
		result = self._tester.sut_control.os_access.run_command(cmd, verify=False, retry=0)
		cmd = "cd {dir} && python {dir}/{scr} --test {testname} --os {operatingsystem}  --avx512_freq {af2} --sse_p1_freq {ssep1}".format(
			dir=self.pi_pm_app_path, 
			scr=self.target_script, 
			testname=self.name,
			operatingsystem=self.operating_system,
			af2=self.avx512_freq_val,
			ssep1=self.sse_freq_val)

		self.result = self._tester.sut_control.os_access.run_command(cmd, verify=False, retry=0)
		self._tester.test_logger.log("Standalone test details **********")
		self._tester.test_logger.log(str(self.result))

		#Log copy to host
		self.collect_output_logs(self.result.combined_lines)
		self._tester.test_logger.log("PIPM app log is:{}".format(self.pipm_app_log))
		self.test_logs.append(self.pipm_app_log)
		self.test_logs.append('{t}/SoCWatchOutput.csv'.format(t=self.pi_pm_applog_folder))

# #################################################################################################
class PI_PM_Basic_Psys_Mode_Discovery_Via_PECI_Root_Skt0_2S_4S_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_Basic_Psys_Mode_Discovery_Via _PECI_Psys_Root_Skt0_2S_4S_Linux"}

	def __init__(self):
		super(PI_PM_Basic_Psys_Mode_Discovery_Via _PECI_Psys_Root_Skt0_2S_4S_Linux, self).__init__()
		self.name = "PSYS_BASIC_MODE_DISCOVERY_VIA_PECI_ROOT_SKT0_2S_4S_LINUX" 
		self.targetlogfolder = "PI_PM_Basic_Psys_Mode_Discovery_Via _PECI_2S_4S_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "PsysPowerDomain=0x1"
		self.bios_knob_set = True
		
	def _start(self):
		self.product_class = PI_PM_Basic_Psys_Mode_Discovery_Via _PECI_Root_Skt0_2S_4S_Linux_TestEngine
		return self

class PI_PM_Basic_Psys_Mode_Discovery_Via _PECI_Root_Skt0_2S_4S_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "verify Psys parameters verify Psys parameters (Min/Max PPL1, Min/Max PPl2, TW1, TW2) are set correctly when Psys mode enabled via BIOS Setup."

	def run_pi_pm_main(self):
		_sv_sockets = self._tester.sv_control.sv_sockets

		self._tester.test_logger.log("Running PI_PM_Psys_Basic_Psys_Mode_Discovery_Peci_Primary_Skt0_2S_And_Primary_Skt0_Skt2_4S_Linux")
		self._tester.test_logger.log("Checking the Power Suppy Unit count from bmc terminal and set bios knob accordingly...")
		self.psulist = self._tester.sut_control.bmc_access.run_command("ipmitool sensor list | grep 'In Voltage'", verify=True).combined_lines
		self._tester.test_logger.log("The PSU available on this platform are : {}".format(self.psulist))
		self.output = self._tester.sut_control.bmc_access.run_command("ipmitool sensor list | grep -c 'In Voltage'", verify=True).combined_lines
		self.psu_count = int(self.output[0])
		self._tester.test_logger.log("The PSU Count is : {}".format(self.psu_count))
		if self.psu_count == 1:
			self.knob = 'PsysPowerLimitAndInfo=0x1'
		elif self.psu_count == 2:
			self.knob ='PsysPowerLimitAndInfo=0x3'

		self._tester.test_logger.log("Bios knob to set : {}".format(self.knob))

		self.socket_count = int(self._frame.sv_control.socket_count)

		if self.socket_count == 2:

			self._tester.test_logger.log("Via PECI PCS, Reading Max PPL1 index 28 and Min PPL index 29")
			self.output_soc0_index28 = self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x30 rdpkgconfig 28 0xfe", verify=True).combined_lines
			self.output_soc1_index28 = self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x31 rdpkgconfig 28 0xfe", verify=True).combined_lines
			self.output_soc0_index29 = self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x30 rdpkgconfig 29 0xfe", verify=True).combined_lines
			self.output_soc1_index29 = self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x31 rdpkgconfig 29 0xfe", verify=True).combined_lines
			
			#for socket-0
			self.max_ppl1_soc0_peci= self.output_soc0_index28[0][16:0]
			self.min_ppl1_soc0_peci= self.output_soc0_index28[0][31:17]
			self.max_ppl2_soc0_peci= self.output_soc0_index29[0][16:0]
			self.max_time_window_soc0_peci= self.output_soc0_index29[0][22:17]
			self._tester.test_logger.log("Via PECI PCS Max PPL1, Min PPL1, Max PPL2 and Max Time Window has been read for socket-0")


			#for socket-1
			self.max_ppl1_soc1_peci= self.output_soc1_index28[0][16:0]
			self.min_ppl1_soc1_peci= self.output_soc1_index28[0][31:17]
			self.max_ppl2_soc1_peci= self.output_soc1_index29[0][16:0]
			self.max_time_window_soc1_peci= self.output_soc1_index29[0][22:17]
			self._tester.test_logger.log("Via PECI PCS Max PPL1, Min PPL1, Max PPL2 and Max Time Window has been read for socket-1")

			
			cmd_0 = "cd {} && ./pmutil_bin -S 0 -p 0 -tR PLATFORM_RAPL_PL_INFO".format(self.app_pmutil_path)
			self._tester.test_logger.log("Running pmutil command :{} for extracting power info for socket-0".format(cmd_0))
			plat_rapl_pl_info_0 = self._tester._os_access.run_command(cmd).combined_lines

			#for socket-0 through tpmi
			self.max_ppl1_soc0_tpmi= self.plat_rapl_pl_info_0[0][16:0]
			self.min_ppl1_soc0_tpmi= self.plat_rapl_pl_info_0[0][31:17]
			self.max_ppl2_soc0_tpmi= self.plat_rapl_pl_info_0[0][48:32]
			self.max_time_window_soc0_tpmi= self.plat_rapl_pl_info_0[0][55:49]
			self._tester.test_logger.log("Via TPMI Max PPL1, Min PPL1, Max PPL2 and Max Time Window has been read for socket-0")

			cmd_1 = "cd {} && ./pmutil_bin -S 1 -p 0 -tR PLATFORM_RAPL_PL_INFO".format(self.app_pmutil_path)
			self._tester.test_logger.log("Running pmutil command :{} for extracting power info for socket-1".format(cmd_1))
			plat_rapl_pl_info_1 = self._tester._os_access.run_command(cmd).combined_lines

			#for socket-1 through tpmi
			self.max_ppl1_soc1_tpmi= self.plat_rapl_pl_info_1[0][16:0]
			self.min_ppl1_soc1_tpmi= self.plat_rapl_pl_info_1[0][31:17]
			self.max_ppl2_soc1_tpmi= self.plat_rapl_pl_info_1[0][16:0]
			self.max_time_window_soc1_tpmi= self.plat_rapl_pl_info_1[0][22:17]
			self._tester.test_logger.log("Via TPMI Max PPL1, Min PPL1, Max PPL2 and Max Time Window has been read for socket-1")

			self._tester.test_logger.log("Comparing values from PECI PCS with those obtained from TPMI for Socket-0")

			if self.max_ppl1_soc0_peci == self.max_ppl1_soc0_tpmi and self.min_ppl1_soc0_peci==self.min_ppl1_soc0_tpmi and self.max_ppl2_soc0_peci == self.max_ppl2_soc0_tpmi and self.max_time_window_soc0_peci == self.max_time_window_soc0_tpmi:
				self._tester.test_logger.log("All values for PECI PCS and TPMI are same. Test Passed for socket-0")
			else:
				self._tester.test_logger.log("Values are different for socket-0. Test failed!")

			if self.max_ppl1_soc1_peci == self.max_ppl1_soc1_tpmi and self.min_ppl1_soc1_peci==self.min_ppl1_soc1_tpmi and self.max_ppl2_soc1_peci == self.max_ppl2_soc1_tpmi and self.max_time_window_soc1_peci == self.max_time_window_soc1_tpmi:
				self._tester.test_logger.log("All values for PECI PCS and TPMI are same. Test Passed for socket-1")
			else:
				self._tester.test_logger.log("Values are different for socket-1.Test failed!")

		if self.socket_count == 4:

			self._tester.test_logger.log("Via PECI PCS, Reading Max PPL1 index 28 and Min PPL index 29")
			self.output_soc0_index28 = self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x30 rdpkgconfig 28 0xfe", verify=True).combined_lines
			self.output_soc1_index28 = self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x31 rdpkgconfig 28 0xfe", verify=True).combined_lines
			self.output_soc2_index28 = self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x32 rdpkgconfig 28 0xfe", verify=True).combined_lines
			self.output_soc3_index28 = self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x33 rdpkgconfig 28 0xfe", verify=True).combined_lines
			self.output_soc0_index29 = self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x30 rdpkgconfig 29 0xfe", verify=True).combined_lines
			self.output_soc1_index29 = self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x31 rdpkgconfig 29 0xfe", verify=True).combined_lines
			self.output_soc2_index29 = self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x32 rdpkgconfig 29 0xfe", verify=True).combined_lines
			self.output_soc3_index29 = self._tester.sut_control.bmc_access.run_command("peci_cmds -a 0x33 rdpkgconfig 29 0xfe", verify=True).combined_lines
			
			#for socket-0
			self.max_ppl1_soc0_peci= self.output_soc0_index28[0][16:0]
			self.min_ppl1_soc0_peci= self.output_soc0_index28[0][31:17]
			self.max_ppl2_soc0_peci= self.output_soc0_index29[0][16:0]
			self.max_time_window_soc0_peci= self.output_soc0_index29[0][22:17]
			self._tester.test_logger.log("Via PECI PCS Max PPL1, Min PPL1, Max PPL2 and Max Time Window has been read for socket-0")


			#for socket-1
			self.max_ppl1_soc1_peci= self.output_soc1_index28[0][16:0]
			self.min_ppl1_soc1_peci= self.output_soc1_index28[0][31:17]
			self.max_ppl2_soc1_peci= self.output_soc1_index29[0][16:0]
			self.max_time_window_soc1_peci= self.output_soc1_index29[0][22:17]
			self._tester.test_logger.log("Via PECI PCS Max PPL1, Min PPL1, Max PPL2 and Max Time Window has been read for socket-1")

			#for socket-2
			self.max_ppl1_soc2_peci= self.output_soc2_index28[0][16:0]
			self.min_ppl1_soc2_peci= self.output_soc2_index28[0][31:17]
			self.max_ppl2_soc2_peci= self.output_soc2_index29[0][16:0]
			self.max_time_window_soc2_peci= self.output_soc2_index29[0][22:17]
			self._tester.test_logger.log("Via PECI PCS Max PPL1, Min PPL1, Max PPL2 and Max Time Window has been read for socket-2")

			#for socket-3
			self.max_ppl1_soc3_peci= self.output_soc3_index28[0][16:0]
			self.min_ppl1_soc3_peci= self.output_soc3_index28[0][31:17]
			self.max_ppl2_soc3_peci= self.output_soc3_index29[0][16:0]
			self.max_time_window_soc3_peci= self.output_soc3_index29[0][22:17]
			self._tester.test_logger.log("Via PECI PCS Max PPL1, Min PPL1, Max PPL2 and Max Time Window has been read for socket-3")

			
			cmd_0 = "cd {} && ./pmutil_bin -S 0 -p 0 -tR PLATFORM_RAPL_PL_INFO".format(self.app_pmutil_path)
			self._tester.test_logger.log("Running pmutil command :{} for extracting power info for socket-0".format(cmd_0))
			plat_rapl_pl_info_0 = self._tester._os_access.run_command(cmd).combined_lines

			#for socket-0 through tpmi
			self.max_ppl1_soc0_tpmi= self.plat_rapl_pl_info_0[0][16:0]
			self.min_ppl1_soc0_tpmi= self.plat_rapl_pl_info_0[0][31:17]
			self.max_ppl2_soc0_tpmi= self.plat_rapl_pl_info_0[0][48:32]
			self.max_time_window_soc0_tpmi= self.plat_rapl_pl_info_0[0][55:49]
			self._tester.test_logger.log("Via TPMI Max PPL1, Min PPL1, Max PPL2 and Max Time Window has been read for socket-0")

			cmd_1 = "cd {} && ./pmutil_bin -S 1 -p 0 -tR PLATFORM_RAPL_PL_INFO".format(self.app_pmutil_path)
			self._tester.test_logger.log("Running pmutil command :{} for extracting power info for socket-1".format(cmd_1))
			plat_rapl_pl_info_1 = self._tester._os_access.run_command(cmd).combined_lines

			#for socket-1 through tpmi
			self.max_ppl1_soc1_tpmi= self.plat_rapl_pl_info_1[0][16:0]
			self.min_ppl1_soc1_tpmi= self.plat_rapl_pl_info_1[0][31:17]
			self.max_ppl2_soc1_tpmi= self.plat_rapl_pl_info_1[0][16:0]
			self.max_time_window_soc1_tpmi= self.plat_rapl_pl_info_1[0][22:17]
			self._tester.test_logger.log("Via TPMI Max PPL1, Min PPL1, Max PPL2 and Max Time Window has been read for socket-1")

			cmd_2 = "cd {} && ./pmutil_bin -S 2 -p 0 -tR PLATFORM_RAPL_PL_INFO".format(self.app_pmutil_path)
			self._tester.test_logger.log("Running pmutil command :{} for extracting power info for socket-2".format(cmd_1))
			plat_rapl_pl_info_2 = self._tester._os_access.run_command(cmd).combined_lines

			#for socket-2 through tpmi
			self.max_ppl1_soc2_tpmi= self.plat_rapl_pl_info_2[0][16:0]
			self.min_ppl1_soc2_tpmi= self.plat_rapl_pl_info_2[0][31:17]
			self.max_ppl2_soc2_tpmi= self.plat_rapl_pl_info_2[0][16:0]
			self.max_time_window_soc2_tpmi= self.plat_rapl_pl_info_2[0][22:17]
			self._tester.test_logger.log("Via TPMI Max PPL1, Min PPL1, Max PPL2 and Max Time Window has been read for socket-2")

			cmd_3 = "cd {} && ./pmutil_bin -S 3 -p 0 -tR PLATFORM_RAPL_PL_INFO".format(self.app_pmutil_path)
			self._tester.test_logger.log("Running pmutil command :{} for extracting power info for socket-3".format(cmd_1))
			plat_rapl_pl_info_3 = self._tester._os_access.run_command(cmd).combined_lines

			#for socket-3 through tpmi
			self.max_ppl1_soc3_tpmi= self.plat_rapl_pl_info_3[0][16:0]
			self.min_ppl1_soc3_tpmi= self.plat_rapl_pl_info_3[0][31:17]
			self.max_ppl2_soc3_tpmi= self.plat_rapl_pl_info_3[0][16:0]
			self.max_time_window_soc3_tpmi= self.plat_rapl_pl_info_3[0][22:17]
			self._tester.test_logger.log("Via TPMI Max PPL1, Min PPL1, Max PPL2 and Max Time Window has been read for socket-3")

			

			self._tester.test_logger.log("Comparing values from PECI PCS with those obtained from TPMI for Socket-0")

			if self.max_ppl1_soc0_peci == self.max_ppl1_soc0_tpmi and self.min_ppl1_soc0_peci==self.min_ppl1_soc0_tpmi and self.max_ppl2_soc0_peci == self.max_ppl2_soc0_tpmi and self.max_time_window_soc0_peci == self.max_time_window_soc0_tpmi:
				self._tester.test_logger.log("All values for PECI PCS and TPMI are same. Test Passed for socket-0")
			else:
				self._tester.test_logger.log("Values are different for socket-0. Test failed!")

			if self.max_ppl1_soc1_peci == self.max_ppl1_soc1_tpmi and self.min_ppl1_soc1_peci==self.min_ppl1_soc1_tpmi and self.max_ppl2_soc1_peci == self.max_ppl2_soc1_tpmi and self.max_time_window_soc1_peci == self.max_time_window_soc1_tpmi:
				self._tester.test_logger.log("All values for PECI PCS and TPMI are same. Test Passed for socket-1")
			else:
				self._tester.test_logger.log("Values are different for socket-1.Test failed!")

			if self.max_ppl1_soc2_peci == self.max_ppl1_soc2_tpmi and self.min_ppl_soc2_peci==self.min_ppl1_soc2_tpmi and self.max_ppl2_soc2_peci == self.max_ppl2_soc2_tpmi and self.max_time_window_soc2_peci == self.max_time_window_soc2_tpmi:
				self._tester.test_logger.log("All values for PECI PCS and TPMI are same. Test Passed for socket-2")
			else:
				self._tester.test_logger.log("Values are different for socket-2.Test failed!")

			if self.max_ppl1_soc3_peci == self.max_ppl1_soc3_tpmi and self.min_ppl1_soc3_peci==self.min_ppl1_soc3_tpmi and self.max_ppl2_soc3_peci == self.max_ppl2_soc3_tpmi and self.max_time_window_soc3_peci == self.max_time_window_soc3_tpmi:
				self._tester.test_logger.log("All values for PECI PCS and TPMI are same. Test Passed for socket-3")
			else:
				self._tester.test_logger.log("Values are different for socket-3.Test failed!")			
#####################################################################################################
class PI_PM_Psys_Basic_Psys_Mode_Discovery_Skt0_Root_2S_And_Skt0_Skt2_Root_4S_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_Psys_Basic_Psys_Mode_Discovery_Skt0_Root_2S_And_Skt0_Skt2_Root_4S_Linux"}

	def __init__(self):
		super(PI_PM_Psys_Basic_Psys_Mode_Discovery_Skt0_Root_2S_And_Skt0_Skt2_Root_4S_Linux, self).__init__()
		self.name = "PSYS_BASIC_PSYS_MODE_DISCOVERY_SKT0_ROOT_2S_SKT0_SKT2_ROOT_4S_LINUX" 
		self.targetlogfolder = "PI_PM_Psys_Basic_Psys_Mode_Discovery_Skt0_Root_2S_And_Skt0_Skt2_Root_4S_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "PsysPowerDomain=0x1"
		self.bios_knob_set = True
		
	def _start(self):
		self.product_class = PI_PM_Psys_Basic_Psys_Mode_Discovery_Skt0_Root_2S_And_Skt0_Skt2_Root_4S_Linux_TestEngine
		return self

class PI_PM_Psys_Basic_Psys_Mode_Discovery_Skt0_Root_2S_And_Skt0_Skt2_Root_4S_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "With Socket0 set"

	def run_pi_pm_main(self):
		_sv_sockets = self._tester.sv_control.sv_sockets
		self.socket_count = int(self._frame.sv_control.socket_count)

		self._tester.test_logger.log("Running PI_PM_Psys_Basic_Psys_Mode_Discovery_Skt0_Root_2S_And_Skt0_Skt2_Root_4S_Linux")
        
        self._tester.test_logger.log("Checking the Power Suppy Unit count from bmc terminal and set bios knob accordingly...")
        self.psulist = self._tester.sut_control.bmc_access.run_command("ipmitool sensor list | grep 'In Voltage'", verify=True).combined_lines
        self._tester.test_logger.log("The PSU available on this platform are : {}".format(self.psulist))
        self.output = self._tester.sut_control.bmc_access.run_command("ipmitool sensor list | grep -c 'In Voltage'", verify=True).combined_lines
        self.psu_count = int(self.output[0])
        self._tester.test_logger.log("The PSU Count is : {}".format(self.psu_count))
        if self.psu_count == 1:
            self.knob = 'PsysPowerLimitAndInfo=0x1'
        elif self.psu_count == 2:
            self.knob ='PsysPowerLimitAndInfo=0x3'

        self._tester.test_logger.log("Bios knob to set : {}".format(self.knob))
        self._tester.sut_control.set_bios_knob(self.knob)
        self._tester.tester_functions.ac_power_cycle()
        self.bios_knob_set=True

        #calculating max ppl1, min ppl1, max ppl2, max time window values for 2 sockets using TPMI
        if self.socket_count==2:

        	self._tester.test_logger.log("Calculating max ppl1, min ppl1, max ppl2, max time window values for 2-sockets using TPMI ")
        	cmd_0 = "cd {} && ./pmutil_bin -S 0 -p 0 -tR PLATFORM_RAPL_PL_INFO".format(self.app_pmutil_path)
			self._tester.test_logger.log("Running pmutil command :{} for extracting power info for socket-0".format(cmd_0))
			plat_rapl_pl_info_0 = self._tester._os_access.run_command(cmd).combined_lines

			#for socket-0 through tpmi
			self.max_ppl1_soc0_tpmi= self.plat_rapl_pl_info_0[0][16:0]
			self.min_ppl1_soc0_tpmi= self.plat_rapl_pl_info_0[0][31:17]
			self.max_ppl2_soc0_tpmi= self.plat_rapl_pl_info_0[0][48:32]
			self.max_time_window_soc0_tpmi= self.plat_rapl_pl_info_0[0][55:49]
			self._tester.test_logger.log("Via TPMI Max PPL1, Min PPL1, Max PPL2 and Max Time Window has been read for socket-0")

			cmd_1 = "cd {} && ./pmutil_bin -S 1 -p 0 -tR PLATFORM_RAPL_PL_INFO".format(self.app_pmutil_path)
			self._tester.test_logger.log("Running pmutil command :{} for extracting power info for socket-1".format(cmd_1))
			plat_rapl_pl_info_1 = self._tester._os_access.run_command(cmd).combined_lines

			#for socket-1 through tpmi
			self.max_ppl1_soc1_tpmi= self.plat_rapl_pl_info_1[0][16:0]
			self.min_ppl1_soc1_tpmi= self.plat_rapl_pl_info_1[0][31:17]
			self.max_ppl2_soc1_tpmi= self.plat_rapl_pl_info_1[0][16:0]
			self.max_time_window_soc1_tpmi= self.plat_rapl_pl_info_1[0][22:17]
			self._tester.test_logger.log("Via TPMI Max PPL1, Min PPL1, Max PPL2 and Max Time Window has been read for socket-1")

			#using msr is not clear
			#msr value calculations will be added here

		if self.socket_count==4:

			#set socket-2 as primary socket
			self._tester.test_logger.log("Calculating max ppl1, min ppl1, max ppl2, max time window values for 4-sockets using TPMI ")

			cmd_0 = "cd {} && ./pmutil_bin -S 0 -p 0 -tR PLATFORM_RAPL_PL_INFO".format(self.app_pmutil_path)
			self._tester.test_logger.log("Running pmutil command :{} for extracting power info for socket-0".format(cmd_0))
			plat_rapl_pl_info_0 = self._tester._os_access.run_command(cmd).combined_lines

			#for socket-0 through tpmi
			self.max_ppl1_soc0_tpmi= self.plat_rapl_pl_info_0[0][16:0]
			self.min_ppl1_soc0_tpmi= self.plat_rapl_pl_info_0[0][31:17]
			self.max_ppl2_soc0_tpmi= self.plat_rapl_pl_info_0[0][48:32]
			self.max_time_window_soc0_tpmi= self.plat_rapl_pl_info_0[0][55:49]
			self._tester.test_logger.log("Via TPMI Max PPL1, Min PPL1, Max PPL2 and Max Time Window has been read for socket-0")

			cmd_1 = "cd {} && ./pmutil_bin -S 1 -p 0 -tR PLATFORM_RAPL_PL_INFO".format(self.app_pmutil_path)
			self._tester.test_logger.log("Running pmutil command :{} for extracting power info for socket-1".format(cmd_1))
			plat_rapl_pl_info_1 = self._tester._os_access.run_command(cmd).combined_lines

			#for socket-1 through tpmi
			self.max_ppl1_soc1_tpmi= self.plat_rapl_pl_info_1[0][16:0]
			self.min_ppl1_soc1_tpmi= self.plat_rapl_pl_info_1[0][31:17]
			self.max_ppl2_soc1_tpmi= self.plat_rapl_pl_info_1[0][16:0]
			self.max_time_window_soc1_tpmi= self.plat_rapl_pl_info_1[0][22:17]
			self._tester.test_logger.log("Via TPMI Max PPL1, Min PPL1, Max PPL2 and Max Time Window has been read for socket-1")

			cmd_2 = "cd {} && ./pmutil_bin -S 2 -p 0 -tR PLATFORM_RAPL_PL_INFO".format(self.app_pmutil_path)
			self._tester.test_logger.log("Running pmutil command :{} for extracting power info for socket-2".format(cmd_1))
			plat_rapl_pl_info_2 = self._tester._os_access.run_command(cmd).combined_lines

			#for socket-2 through tpmi
			self.max_ppl1_soc2_tpmi= self.plat_rapl_pl_info_2[0][16:0]
			self.min_ppl1_soc2_tpmi= self.plat_rapl_pl_info_2[0][31:17]
			self.max_ppl2_soc2_tpmi= self.plat_rapl_pl_info_2[0][16:0]
			self.max_time_window_soc2_tpmi= self.plat_rapl_pl_info_2[0][22:17]
			self._tester.test_logger.log("Via TPMI Max PPL1, Min PPL1, Max PPL2 and Max Time Window has been read for socket-2")

			cmd_3 = "cd {} && ./pmutil_bin -S 3 -p 0 -tR PLATFORM_RAPL_PL_INFO".format(self.app_pmutil_path)
			self._tester.test_logger.log("Running pmutil command :{} for extracting power info for socket-3".format(cmd_1))
			plat_rapl_pl_info_3 = self._tester._os_access.run_command(cmd).combined_lines

			#for socket-3 through tpmi
			self.max_ppl1_soc3_tpmi= self.plat_rapl_pl_info_3[0][16:0]
			self.min_ppl1_soc3_tpmi= self.plat_rapl_pl_info_3[0][31:17]
			self.max_ppl2_soc3_tpmi= self.plat_rapl_pl_info_3[0][16:0]
			self.max_time_window_soc3_tpmi= self.plat_rapl_pl_info_3[0][22:17]
			self._tester.test_logger.log("Via TPMI Max PPL1, Min PPL1, Max PPL2 and Max Time Window has been read for socket-3")


			#msr part is left






######################################################################################################
class PI_PM_Psys_Verify_PLATFORM_RAPL_PERF_STATUS_MSR_Update_RAPL_Limit_2S_4S_Any_Socket_Linux(PI_PM_Testcase):
	_default = {"_config_name": "PI_PM_Psys_Verify_PLATFORM_RAPL_PERF_STATUS_MSR_Update_RAPL_Limit_2S_4S_Linux"}

	def __init__(self):
		super(PI_PM_Psys_Verify_PLATFORM_RAPL_PERF_STATUS_MSR_Update_RAPL_Limit_2S_4S_Any_Socket_Linux, self).__init__()
		self.name = "PSYS_VERIFY_PLATFORM_RAPL_PERF_STATUS_MSR_UPDATES_RAPL_LIMIT_2S_4S_Any_Socket_LINUX" 
		self.targetlogfolder = "PI_PM_Psys_Verify_PLATFORM_RAPL_PERF_STATUS_MSR_Update_RAPL_Limit_2S_4S_Any_Socket_Linux"
		self.supported_os_types = [TESTER_ENUMS.OS_TYPE.LINUX,
								   TESTER_ENUMS.OS_TYPE.FEDORA,
								   TESTER_ENUMS.OS_TYPE.SLES,
								   TESTER_ENUMS.OS_TYPE.REDHAT,
								   TESTER_ENUMS.OS_TYPE.CLEARLINUX,
								   TESTER_ENUMS.OS_TYPE.CENTOS,
								   ]
		self.suite_membership = [SUITE_TYPE.LINUX_SAT, SUITE_TYPE.UNDEFINED]
		self.bios_knobs = "PsysPowerDomain=0x1"
		self.bios_knob_set = True
		
	def _start(self):
		self.product_class = PI_PM_Psys_Verify_PLATFORM_RAPL_PERF_STATUS_MSR_Update_RAPL_Limit_2S_4S_Any_Socket_Linux_TestEngine
		return self

class PI_PM_Psys_Verify_PLATFORM_RAPL_PERF_STATUS_MSR_Update_RAPL_Limit_2S_4S_Any_Socket_Linux_TestEngine(PI_PM_TestEngine):
	class_lable = "This test case ensures the PLATFORM_RAPL_PERF_STATUS MSR is updated correctly upon a platform RAPL limit."
	
	def run_pi_pm_main(self):
		_sv_sockets = self._tester.sv_control.sv_sockets
		self.socket_count = int(self._frame.sv_control.socket_count)
		self._tester.test_logger.log("Running PI_PM_Psys_Verify_PLATFORM_RAPL_PERF_STATUS_MSR_Update_RAPL_Limit_2S_4S_Any_Socket_Linux")
		
		self._tester.test_logger.log("Checking the Power Suppy Unit count from bmc terminal and set bios knob accordingly...")
		self.psulist = self._tester.sut_control.bmc_access.run_command("ipmitool sensor list | grep 'In Voltage'", verify=True).combined_lines
		self._tester.test_logger.log("The PSU available on this platform are : {}".format(self.psulist))
		self.output = self._tester.sut_control.bmc_access.run_command("ipmitool sensor list | grep -c 'In Voltage'", verify=True).combined_lines
		self.psu_count = int(self.output[0])
		self._tester.test_logger.log("The PSU Count is : {}".format(self.psu_count))
		if self.psu_count == 1:
			self.knob = 'PsysPowerLimitAndInfo=0x1'
		elif self.psu_count == 2:
			self.knob ='PsysPowerLimitAndInfo=0x3'  #dummy value, actual value will be provided

		self._tester.test_logger.log("Bios knob to set : {}".format(self.knob))
		self._tester.sut_control.set_bios_knob(self.knob)
		self._tester.tester_functions.ac_power_cycle()
		self.bios_knob_set=True


		self.wl_thread = thread_with_trace(target=self.run_ptu_workload, args=("ct3",), name="ptu") 
		self._tester.test_logger.log("Running PTU WL for Test PTU ct3 with cpu cpu_utilization as 80")
		self.wl_thread.start()
		time.sleep(30)

		#read the platform power 
		self._tester.test_logger.log("Reading platform power comsumption")
		self.power_plt_energy_status_value = self.run_platform_power_consumption()

		self.reduced_platform_power=self.power_plt_energy_status_value * 0.7
		for socket in _sv_sockets:
			socket.uncore.punit.platform_rapl_limit_cfg.ppl1 = int(self.reduced_platform_power * 8)

		self._tester.test_logger.log("Perform multiple reads of PLATFORM_RAPL_PERF_STATUS MSR and confirm it's value is incrementing.")
		self._tester._os_access.run_command("cd {};chmod 777 *".format(self.app_pmutil_path))

		for i in range(0,4):
			cmd_1 = "cd {} && ./pmutil_bin -S {} -p 0 -tr 0x0 0x140".format(self.app_pmutil_path,i)
			self._tester.test_logger.log("Running pmutil command :{} for 1st read".format(cmd))
			plat_rapl_perf_status_msr_1 = self._tester._os_access.run_command(cmd).combined_lines

			cmd_2 = "cd {} && ./pmutil_bin -S {} -p 0 -tr 0x0 0x140".format(self.app_pmutil_path,i)
			self._tester.test_logger.log("Running pmutil command :{} for 2nd read".format(cmd))
			plat_rapl_perf_status_msr_2 = self._tester._os_access.run_command(cmd).combined_lines

			#the bit value reading for msr_status from pmutil to be implemented after pmutil works
			#converting from hex to int

			if int(plat_rapl_perf_status_msr_2) > int(plat_rapl_perf_status_msr_1):
				self._tester.test_logger.log("PLATORM_RAPL_PERF_STATUS MSR is incrementing for socket {}".format(i))
			else:
				self._tester.exit_with_error("PLATORM_RAPL_PERF_STATUS MSR is not incrementing for socket {}, Test failed!".format(i))


		self._tester.test_logger.log("Stopping PTU operations.")
		self.wl_thread.kill()

		for i in range(0,4):
			cmd_1 = "cd {} && ./pmutil_bin -S {} -p 0 -tr 0x0 0x140".format(self.app_pmutil_path,i)
			self._tester.test_logger.log("Running pmutil command :{} for 1st read".format(cmd))
			plat_rapl_perf_status_msr_1 = self._tester._os_access.run_command(cmd).combined_lines

			cmd_2 = "cd {} && ./pmutil_bin -S {} -p 0 -tr 0x0 0x140".format(self.app_pmutil_path,i)
			self._tester.test_logger.log("Running pmutil command :{} for 2nd read".format(cmd))
			plat_rapl_perf_status_msr_2 = self._tester._os_access.run_command(cmd).combined_lines

			#the bit value reading for msr_status from pmutil to be implemented after pmutil works
			#converting from hex to int

			if int(plat_rapl_perf_status_msr_2) == int(plat_rapl_perf_status_msr_1):
				self._tester.test_logger.log("PLATORM_RAPL_PERF_STATUS MSR is static for socket {}".format(i))
			else:
				self._tester.exit_with_error("PLATORM_RAPL_PERF_STATUS MSR is not static for socket {}, Test failed!".format(i))


		#reboot and set those bios knobs according new configuration for GNR 2s and 4s.
		if self.psu_count == 1:
			self.knob = 'PsysPowerLimitAndInfo=0x1'
		elif self.psu_count == 2:
			self.knob ='PsysPowerLimitAndInfo=0x3'

		#PsysPowerLimitDomain=manual
		#set new configuration for GNR
		#After setting the socket values for 2S and 4S for GNR, confirm the same with tpmi

		if self.socket_count==2:
			#for 2s platform socket-1 is primary and socket-0 is leaf
			cmd_0 = "cd {} && ./pmutil_bin -S 0 -p 0 -tr 0 0x150".format(self.app_pmutil_path)
			soc0_val = self._tester._os_access.run_command(cmd_0).combined_lines
			cmd_1 = "cd {} && ./pmutil_bin -S 1 -p 0 -tr 0x0 0x150".format(self.app_pmutil_path)
			soc1_val = self._tester._os_access.run_command(cmd_0).combined_lines

			if soc1_val[0]==1:
				self._tester.test_logger.log("Socket 1 is set as Psys Root")
			else:
				self._tester.exit_with_error("Socket 1 is not set as Psys Root. Test failed")

			#checking for Domain_id for Psys root and leaf

			if soc0_val[3:1] == soc1_val[3:1]:
				self._tester.test_logger.log("The Domain_ID of Psys Root(1) and leaf(0) is same")
			else:
				self._tester.exit_with_error("The Domain_ID of Psys Root(1) and leaf(0) is different. Test failed.")

		elif self.socket_count==4:
			#for 4s platform socket-1 is root and socket-0 is leaf for socket-1
			#socket-3 is root and socket-2 is leaf for socket-3

			cmd_0 = "cd {} && ./pmutil_bin -S 0 -p 0 -tr 0 0x150".format(self.app_pmutil_path)
			soc0_val = self._tester._os_access.run_command(cmd_0).combined_lines
			cmd_1 = "cd {} && ./pmutil_bin -S 1 -p 0 -tr 0x0 0x150".format(self.app_pmutil_path)
			soc1_val = self._tester._os_access.run_command(cmd_0).combined_lines
			cmd_2 = "cd {} && ./pmutil_bin -S 2 -p 0 -tr 0 0x150".format(self.app_pmutil_path)
			soc2_val = self._tester._os_access.run_command(cmd_0).combined_lines
			cmd_3 = "cd {} && ./pmutil_bin -S 3 -p 0 -tr 0x0 0x150".format(self.app_pmutil_path)
			soc3_val = self._tester._os_access.run_command(cmd_0).combined_lines


			if soc1_val[0]==1:
				self._tester.test_logger.log("Socket 1 is set as Psys Root")
			else:
				self._tester.exit_with_error("Socket 1 is not set as Psys Root. Test failed")

			if soc3_val[0]==1:
				self._tester.test_logger.log("Socket 3 is set as Psys Root")
			else:
				self._tester.exit_with_error("Socket 3 is not set as Psys Root. Test failed")


			if soc0_val[3:1] == soc1_val[3:1]:
				self._tester.test_logger.log("The Domain_ID of Psys Root(1) and leaf(0) is same")
			else:
				self._tester.exit_with_error("The Domain_ID of Psys Root(1) and leaf(0) is different. Test failed.")


			if soc2_val[3:1] == soc3_val[3:1]:
				self._tester.test_logger.log("The Domain_ID of Psys Root(3) and leaf(2) is same")
			else:
				self._tester.exit_with_error("The Domain_ID of Psys Root(3) and leaf(2) is different. Test failed.")

#######################################################################################################################


























#######################################################################################################


def main():
	pass

# #################################################################################################

if __name__ == '__main__':
	main()