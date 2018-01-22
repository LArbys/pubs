#!/usr/bin/env python
## @namespace dstream.ds_daemon
#  @ingroup dstream
#  @brief Introduce simple daemon toolkit for executing projects
#  @details
#  Includes class proc_action (a unit process executor) and proc_daemon (a process manager)

# Python include
import time, copy, os, signal, sys
from subprocess   import Popen, PIPE
import threading
# dstream include
from pub_util     import pub_env
from ds_exception import DSException
from ds_proc_base import ds_base
from ds_api       import ds_master
from ds_data      import ds_project, ds_daemon, ds_daemon_log
# pub_dbi package include
from pub_dbi      import pubdb_conn_info, DBException
# pub_util package include
from pub_util     import pub_logger, pub_smtp, BaseException
from ds_messenger import daemon_messenger as d_msg
## @class proc_action
#  @brief A single process executor for a project
#  @details
#  Instantiated with project information, proc_action executes a project.\n
#  Currently executed process's stdout and stderr are simply handled via pipe.\n
#  One may improve this simple design to manage memory/cpu/wall-time of the process.\n
class proc_action(object):

    ## default ctor accepting ds_project instance
    def __init__(self, project_info,logger=None):

        self._logger = logger
        if not self._logger:
            self._logger = pub_logger.get_logger(self.__class__.__name__)

        ## Project information
        self._info = None

        ## Process handle
        self._proc = None

        ## Boolean for running process
        self._running = False

        self.set_info(project_info)

    ## project info updater
    def set_info(self,project_info):
        if not isinstance(project_info,ds_project):
            raise ValueError
        self._info = copy.copy(project_info)
        
    ## Simple method to access name of a project
    def name(self): return self._info._project

    ## Kill process
    def kill(self):
        if self.active():
            self._proc.kill()
            self._running = False

    ## Boolean function to check if there is a process instance
    def process_exist(self):
        if self._proc is None: return False
        return True

    ## Boolean function to check if the project's execution process is alive or not
    def active(self):
        if self._proc:
            self._running = (self._proc.poll() is None)
        return self._running

    ## Read lines from file.
    def _read(self, f, result):
        while f:
            line = f.readline()
            if line == '':
                break
            else:
                result.append(line)

    ## Read stdout and stderr from subprocess pipe, with timeout.
    def _communicate(self):

        # Stdout.

        out = []
        stdout_thread = threading.Thread(target=self._read, args=(self._proc.stdout, out))
        stdout_thread.setDaemon(True) # Allow main program to exit even if thread never finishes.
        stdout_thread.start()
        stdout_thread.join(60)  # Join with timeout.
        if stdout_thread.isAlive():
            self._logger.warning('Did not get EOF from stdout.  Thread leaked.')
        outstr = ''
        for line in out:
            outstr += line

        # Stderr.

        err = []
        stderr_thread = threading.Thread(target=self._read, args=(self._proc.stderr, err))
        stderr_thread.setDaemon(True) # Allow main program to exit even if thread never finishes.
        stderr_thread.start()
        stderr_thread.join(60)  # Join with timtout.
        if stderr_thread.isAlive():
            self._logger.warning('Did not get EOF from stderr.  Thread leaked.')
        errstr = ''
        for line in err:
            errstr += line

        # Done.

        return outstr, errstr

    ## @brief Clears a project process, if exists, and returns (stdout,stderr). 
    #  @details If process is active, it waits to finish. Use active() function\n
    #  before calling this to avoid waiting time.
    def clear(self):
        if self._proc is None: return (None,None,None)
        #(out,err) = self._proc.communicate()
        (out,err) = self._communicate()
        code = self._proc.poll()
        del self._proc
        self._running=False
        self._proc = None
        return (code,out,err)

    ## Opens a sub-process to execute a project
    def execute(self):
        try:
            #self._logger.info('Executing: \"%s\"' % self._info._command)
            #self._logger.info('Executing: \"%s\"' % str(self._info._command.split()))
            self._proc = Popen(self._info._command.split(None),
                               #shell=True,
                               stdout = PIPE,
                               stderr = PIPE)
            self._running = True
        except OSError as e:

            self._logger.error(e.strerror)
            self._logger.error('Error executing %s! Sending e-mail report...' % self._info._project)
            try:
                pub_smtp(receiver = self._info._email,
                         subject  = 'Failed execution of project %s' % self.name(),
                         text     = e.strerror)
            except BaseException as be:
                self._logger.critical('Project %s error could not be reported via email!' % self._info._project)                
                for line in be.v.split('\n'):
                    self._logger.error(line)
            raise DSException(e.strerror)

## @class proc_daemon
#  @brief Simple daemon tool to run registered projects
#  @details
#  Contains one function to continue an indefinite loop of loading project information\n
#  and execution at requested time. Loading of a project from DB is done in the other\n
#  function.
class proc_daemon(ds_base):

    ## default ctor does not require any input
    def __init__(self):

        super(proc_daemon,self).__init__()

        ## Constructor time
        self._creation_ts = time.time()

        ## API for proc_daemon is ds_master to interact with ProcessTable
        self._api = ds_master(pubdb_conn_info.admin_info(),logger=self._logger)

        ## Array of proc_action instance (one per project)
        self._project_v  = {}

        ## Array of execution timestamp (one per project)
        self._exe_time_v = {}

        ## Array of execution counter (one per project)
        self._exe_ctr_v = {}

        ## Network node name
        self._server = pub_env.kSERVER_NAME

        ## Server configuration ... instantiated within load_daemon
        self._config = None

        ## Log ... instantiated within load_daemon
        self._log = None

        ## Next execution timestamp ... for processing
        self._next_exec_time = time.time()

        ## SIGINT marker
        self._exit_routine = False

        ## Log function
        self._logger_func = None

        ## Server status handler
        self._server_handler = None

    ## Attach logger function dynamically
    def attach_logger_func(self,ptr):
        self._logger_func=ptr
        try:
            log = self._logger_func()
            if not type(log) == type(dict()):
                raise ValueError
        except ValueError as e:
            self.error('Attached logger function is incompatible!')
            return False
        return True

    ## Attach server status handler dynamically
    def attach_server_handler(self,ptr):
        self._server_handler=ptr
        try:
            status, msg = self._server_handler()
            if not type(status) == type(bool()) or not type(msg) == type(str()):
                raise ValueError
        except Exception as e:
            self.error('Attached server handler function is incompatible!')
            return False
        return True
            
    ## Access DB and load daemon info for execution
    def load_daemon(self):
        self._config = self._api.daemon_info(self._server)
        if not self._config:
            self.warning('Daemon configuration not found for server %s' % self._server)
            self._config = ds_daemon( server = self._server )

        if not self._log:
            self._log = ds_daemon_log(self._config._server,
                                      self._config._max_proj_ctr,
                                      self._config._lifetime)

        d_msg.set_address(self.__class__.__name__,
                          self._config._email,
                          self._config._server)

    ## Log daemon status
    def log_daemon(self):
        uptime   = int(time.time() - self._creation_ts)
        proj_ctr = 0
        for x in self._project_v.values():
            if x.active(): proj_ctr += 1

        hstore = dict()
        if self._logger_func:
            hstore = self._logger_func()
        self._log.log( proj_ctr = proj_ctr,
                       uptime   = uptime,
                       log      = hstore,
                       max_proj_ctr = self._config._max_proj_ctr,
                       lifetime = self._config._lifetime )

        self._api.log_daemon(self._log)

        if self._server_handler:
            status,msg = self._server_handler()

            if msg:
                if not status:
                    d_msg.email( self.__class__.__name__,
                                 subject  = '[DAEMON SHUT DOWN] Message from Server Handler',
                                 text     = msg)
                else:
                    d_msg.email( self.__class__.__name__,
                                 subject  = '[NOTICE] Message from Server Handler',
                                 text     = msg)
            self._exit_routine = not status

    ## Access DB and load projects for execution + update pre-loaded project information
    def load_projects(self):

        # Load new/updated projects
        msg = ''
        for x in self._api.list_all_projects():

            proj_ptr = None
            if x._project in self._project_v:
                proj_ptr = self._project_v[x._project]

            if x._server and not x._server in self._server:
                self.debug('Skipping a project on irrelevant server: %s' % x._project)
                continue
            
            #if proj_ptr and proj_ptr.active():
            #    self.info('Skipping update on project %s (still active)' % x._project)
            #    continue

            if not x._enable:
                if not proj_ptr:
                    self.debug('Skipping a disabled project: %s' % x._project)
                elif proj_ptr._info._enable:
                    self.info('Disabling project: %s' % x._project)
                    if not msg:
                        msg = 'Report @ proc_daemon::load_projects()\n'
                    msg += 'Disabling \'%s\'\n' % x._project
                    proj_ptr.set_info(x)
                continue

            if not proj_ptr:
                self.info('Enabling project %s' % x._project)
                if not msg:
                    msg = 'Report @ proc_daemon::load_projects()\n'
                msg += 'Enabling \'%s\'\n' % x._project
                self._project_v[x._project] = proc_action(x,self._logger)

            elif not proj_ptr._info._enable:
                self.info('Re-enabling project %s' % x._project)
                if not msg:
                    msg = 'Report @ proc_daemon::load_projects()\n'
                msg += 'Re-enabling project \'%s\'\n' % x._project
                proj_ptr.set_info(x)
                
            elif not x == self._project_v[x._project]._info:
                self.info('Updating project %s information' % x._project)
                if not msg:
                    msg = 'Report @ proc_daemon::load_projects()\n'
                msg += 'Updating project info for \'%s\'\n' % x._project
                proj_ptr.set_info(x)

            if not x._project in self._exe_time_v:
                self._exe_time_v[x._project] = None
                self._exe_ctr_v[x._project]  = 0

#        for p in rm_list:
#            print p, self._project_v[p].active()
#            if not self._project_v[p].active() is None:
#                self._project_v.pop(p)

        if msg and self._config:
            try:
                d_msg.email( self.__class__.__name__,
                             subject  = 'Project Info Update Report',
                             text     = msg)
            except BaseException as be:
                self._logger.critical('Project update could not be reported via email!')
                for line in be.v.split('\n'):
                    self._logger.error(line)

    ## List projects in the priority order to be executed
    def ordered_projects(self):
        # Prioritize execution by counter
        ctr_priority = {}
        for x in self._exe_ctr_v:
            ctr = self._exe_ctr_v[x]
            if not ctr in ctr_priority:
                ctr_priority[ctr]=[]
            ctr_priority[ctr].append(x)

        ctrs = ctr_priority.keys()
        ctrs.sort()
        projects = []
        for ctr in ctr_priority:
            for p in ctr_priority[ctr]:
                projects.append(p)
        return projects
        
    ## Access DB and bring project(s) table up-to-date with MainRun table
    def runsync_project(self,project=None):
        self._api.runsynch(project)

    ## Clean up @ end
    def finish(self):
        ctr=300
        if self._config:
            ctr = self._config._cleanup_time
        self.info('Program exit: waiting %d [sec] for all projects to end...' % ctr)
        ready = False
        while not ready and ctr:
            ready = True
            for p in self._project_v.values():
                if p.active():
                    ready = False
                    break
            time.sleep(1)
            ctr -= 1

        # string containing message to report
        message = ''
        if ctr:
            message = 'All projects finished gracefully.'
            self.info(message)
        else:
            message = 'There are still un-finished projects... killing them now.'
            self.warning(message)
            for x in self._project_v:
                self.warning('killing %s' % x)
                self._project_v[x].kill()

        try:
            d_msg.email( self.__class__.__name__,
                         subject  = 'Daemon ended!',
                         text     = 'Daemon has ended. The following message was produced:\n%s' % message)
        except BaseException as be:
            self._logger.critical('Project %s error could not be reported via email!' % self._info._project)                
            for line in be.v.split('\n'):
                self._logger.error(line)

    ## Initiate an indefinite loop of projects' info-loading & execution 
    def routine(self):

        routine_ctr=0
        routine_sleep=0
        while routine_ctr >= 0 and not self._exit_routine:

            routine_ctr+=1
            time.sleep(1)
            now_str  = time.strftime('%Y-%m-%d %H:%M:%S')
            now_ts   = time.time()
            self.debug(now_str)

            # If sleep is set, do nothing and continue
            if routine_sleep: 
                routine_sleep -=1
                continue

            try:
                self._api.connect()
                if not self._config:

                    self.load_daemon()

                    try:
                        msg  = 'Daemon has started @ %s\n' % self._config._server
                        msg += str(self._config)
                        d_msg.email( self.__class__.__name__,
                                     subject  = 'Daemon started!',
                                     text     = msg)
                    except BaseException as be:
                        self._logger.critical('Project %s error could not be reported via email!' % self._info._project)
                        for line in be.v.split('\n'):
                            self._logger.error(line)
                    
            except DBException as e:
                self.error('Failed connection to DB @ %s ... Retry in 1 minute' % now_str)
                routine_sleep = 60
                d_msg.email(self.__class__.__name__,
                            subject  = 'Daemon Error',
                            text = 'Failed to establish DB connection @ %s' % now_str)
                continue
            
            # Exit if time exceeds the daemon lifetime
            if self._config and (now_ts - self._creation_ts) > self._config._lifetime:
                self.warning('Exceeded pre-defined lifetime. Exiting...')
                break

            if (routine_ctr-1) % self._config._update_time == 0:
                
                self.info('Routine project update @ %s ' % now_str)
                if self._api.is_cursor_connected() is None:
                    self._api.connect()
                #else:
                #    self._api.reconnect()
                if not self._api.is_cursor_connected():
                    d_msg.email(self.__class__.__name__,
                                subject  = 'Daemon Error',
                                text = 'Failed to establish DB connection @ %s' % now_str)
                    continue
                if (routine_ctr-1):
                    self.load_daemon()
                if self._config._enable:
                    self.load_projects()
                self.log_daemon()

            if not self._config._enable:
                continue

            if (routine_ctr-1) % self._config._runsync_time == 0:

                self.info('Routine RunSync Start @ %s' % now_str)
                try:
                    for proj_name,proj_ptr in self._project_v.iteritems():

                        if not proj_ptr._info._enable: continue

                        self.runsync_project(proj_name)

                except Exception as runsync_error:
                    msg  = 'RunSync failed...\n'
                    msg += str(runsync_error)
                    self.error(msg)

                    try:
                        d_msg.email(self.__class__.__name__,
                                    subject  = 'Daemon Error',
                                    text = 'Failed to execute RunSynch @ %s' % now_str)
                                
                    except DSException as msg_error:
                        self.critical('Report to daemon experts failed!')

                self.info('Routine RunSync Done  @ %s' % now_str)

            if now_ts < self._next_exec_time: continue

            for proj in self.ordered_projects():

                if self._exit_routine: break
                
                proj_ptr = self._project_v[proj]
                if not proj_ptr._info._enable: continue

                active_ctr = 0
                for x in self._project_v:
                    if self._project_v[x].active(): active_ctr += 1

                if active_ctr >= self._config._max_proj_ctr:
                    self.info('Max number of simultaneous project execution reached.')
                    break
                
                last_ts = self._exe_time_v[proj]
                now_ts  = time.time()

                if now_ts < self._next_exec_time: continue

                proj_active = proj_ptr.active()
                if not proj_active:

                    if not proj_active and proj_ptr.process_exist():
                        self._api.project_stopped(proj)
                        self.info(' Clearing %s @ %s' % (proj, now_str))
                        (code,out,err) = proj_ptr.clear()

                        self.info(' %s returned %s @ %s' % (proj,code,now_str))

                        if out or err:
                            
                            self.info(' %s stdout/stderr:\n %s\n%s' % (proj,out,err))
                        
                    if ( last_ts is None or 
                         last_ts < ( now_ts - proj_ptr._info._period) ):

                        try:
                            self.info('Execute %s @ %s' % (proj,now_str))
                            proj_ptr.execute()
                            self._api.project_running(proj)
                            
                        except DSException as e:
                            self.critical('Call expert and review project %s' % proj)

                            try:
                                d_msg.email(self.__class__.__name__,
                                            subject  = 'Daemon Error',
                                            text = 'Failed to execute project \'%s\' @ %s' % (proj,now_str))
                                
                            except DSException as  e:
                                self.critical('Report to daemon experts failed!')

                        self._exe_time_v[proj] = time.time()
                        self._exe_ctr_v[proj] += 1
                        self._next_exec_time = self._exe_time_v[proj] + proj_ptr._info._sleep

        self.finish()
        self._exit_routine = False

if __name__ == '__main__':

    # if daemon is already running, do not allow another instance
    k=proc_daemon()

    # logger function attachment
    cmd=''
    if pub_env.kDAEMON_LOG_MODULE:
        modname = pub_env.kDAEMON_LOG_MODULE
        if modname.find('.') < 0:
            cmd = 'import %s as daemon_log_dict' % modname
        else:
            fname = modname[modname.rfind('.')+1:len(modname)]
            modname = modname[0:modname.rfind('.')]
            cmd = 'from %s import %s as daemon_log_dict' % (modname,fname)
        try:
            exec(cmd)
        except ImportError as e:
            cmd=''
            k.error('Failed to import a logger module: %s' % pub_env.kDAEMON_LOG_MODULE)
            sys.exit(1)
        if not k.attach_logger_func(daemon_log_dict):
            sys.exit(1)

    # server function attachment
    if pub_env.kDAEMON_HANDLER_MODULE:
        modname = pub_env.kDAEMON_HANDLER_MODULE
        if modname.find('.') < 0:
            cmd = 'import %s as daemon_server_handler' % modname
        else:
            fname = modname[modname.rfind('.')+1:len(modname)]
            modname = modname[0:modname.rfind('.')]
            cmd = 'from %s import %s as daemon_server_handler' % (modname,fname)
        try:
            exec(cmd)
        except ImportError:
            cmd=''
            k.error('Failed to import a logger module: %s' % pub_env.kDAEMON_HANDLER_MODULE)
            sys.exit(1)
        if not k.attach_server_handler(daemon_server_handler):
            sys.exit(1)

    ## For ctrl+C
    def sig_kill(signal,frame):
        k._exit_routine=True
        k.warning('SIGINT detected. Finishing the program gracefully.')
        k.warning('Terminating proc_daemon::routine function.')

    signal.signal(signal.SIGINT,  sig_kill)
    signal.signal(signal.SIGQUIT, sig_kill)
    signal.signal(signal.SIGTERM, sig_kill)
    k.routine()
