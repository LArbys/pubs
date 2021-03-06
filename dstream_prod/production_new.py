## @namespace dstream_prod.production
#  @ingroup dstream_prod
#  @brief Defines a project production
#  @author yuntse

# python include
import time,os,sys,time
import subprocess, traceback
import shutil
import StringIO
# pub_dbi package include
from pub_dbi import DBException
# pub_util package include
from pub_util import pub_smtp
# dstream class include
from dstream import DSException
from dstream import ds_project_base
from dstream import ds_status
# From larbatch
import project
import project_utilities
import larbatch_posix
from project_modules.pubsdeadenderror import PubsDeadEndError
from project_modules.pubsinputerror import PubsInputError

## @class production
#  @brief A fake job submission process, only printing out the commands
#  @details
#  This production project prints out the job submission commands using project.py
class production(ds_project_base):

    PROD_STATUS = ( kDONE,
                    kINITIATED,
                    kTOBEVALIDATED,
                    kSUBMITTED,
                    kRUNNING,
                    kFINISHED,
                    kTOBERECOVERED,
                    kREADYFORSAM,
                    kDECLARED,
                    kSTORED ) = xrange(10)

    JOBSUB_LOG = '%s/joblist.txt' % os.environ['PUB_LOGGER_FILE_LOCATION']

    # Define project name as class attribute
    _project = 'production'

    ## @brief default ctor can take # runs to process for this instance
    def __init__( self, proj_name='', table_name='' ):

        # Call base class ctor
        super(production,self).__init__(proj_name)

        if not proj_name:
            self.error('No project name specified!')
            raise Exception

        if table_name == '':
            table_name = proj_name

        self._project = proj_name
        self._table = table_name
        self._parent  = ''
        self._parent_status = None
        # Actions associated with single subruns.

        self.PROD_ACTION = { self.kDONE          : self.checkNext,
                             self.kINITIATED     : None,
                             self.kTOBEVALIDATED : self.isRunning,
                             self.kSUBMITTED     : self.isRunning,
                             self.kRUNNING       : self.isRunning,
                             self.kFINISHED      : self.check,
                             self.kTOBERECOVERED : self.single_recover,
                             self.kREADYFORSAM   : self.declare,
                             self.kDECLARED      : self.store,
                             self.kSTORED        : self.check_location }
        self.PROD_MULTIACTION = { self.kDONE          : None,
                                  self.kINITIATED     : self.submit,
                                  self.kTOBEVALIDATED : None,
                                  self.kSUBMITTED     : None,
                                  self.kRUNNING       : None,
                                  self.kFINISHED      : None,
                                  self.kTOBERECOVERED : None,
                                  self.kREADYFORSAM   : None,
                                  self.kDECLARED      : None,
                                  self.kSTORED        : None }
        self._max_runid   = None
        self._min_runid   = None
        self._max_status  = len(self.PROD_STATUS)
        self._min_status  = 0
        self._nruns       = None
        self._njobs       = 0
        self._njobs_limit = None
        self._njobs_tot   = 0
        self._njobs_tot_limit = None
        self._nsubruns    = []
        self._store       = {}
        self._storeana    = {}
        self._add_location = {}
        self._add_location_ana = {}
        self._check = {}
	self._fast_check = {}
        self._checkana = {}
        self._xml_file    = ''
        self._xml_outdir   = ''
        self._xml_template = False
        self._xml_rep_var  = {}
        self._stage_names   = []
        self._stage_digits  = []
        self._nresubmission = 3
        self._digit_to_name = {}
        self._name_to_digit = {}
        self._digit_to_nsubruns = {}
        self._data = "None"
        self._runid_status = {}
        self._jobstat = ''
        if not self.loadProjectParams():
            self.info('Failed to load project @ %s' % self.now_str())
            sys.exit(1)

    def getXML(self,run,remake=False):

        if not self._xml_template: return self._xml_file
        
        out_xml_name = '%s/%s_run_%07d.xml' % (self._xml_outdir,self._project,int(run))

        if os.path.isfile(out_xml_name):
            out_ctime = os.path.getctime(out_xml_name)
            in_ctime  = os.path.getctime(self._xml_template)

            if in_ctime > out_ctime:
                self.warning('Re-creating XML file as input is newer (%s)' % out_xml_name)
                remake = True

        if not remake and os.path.isfile(out_xml_name): return out_xml_name

        if not os.path.isfile(self._xml_template):
            raise DSException('Input XML template does not exist: %s' % self._xml_template)

        fout = open(out_xml_name,'w')
        contents = open(self._xml_template,'r').read()
        contents = contents.replace('REP_RUN_NUMBER','%d' % int(run))
        contents = contents.replace('REP_ZEROPAD_RUN_NUMBER','%07d' % int(run))
        for key,value in self._xml_rep_var.iteritems():
            contents = contents.replace(key,value)
        fout.write(contents)
        fout.close()

        return out_xml_name

    def loadProjectParams( self ):

        # Attempt to connect DB. If failure, abort
        if not self.connect():
	    self.error('Cannot connect to DB! Aborting...')
	    return False

        proj_info = self._api.project_info(self._project)
        
        try:
            if 'PARENT' in proj_info._resource:
                self._parent = proj_info._resource['PARENT']
                exec('self._parent_status = int(%s)' % proj_info._resource['PARENT_STATUS'])
            self._nruns = int(proj_info._resource['NRUNS'])
            if 'XML_TEMPLATE' in proj_info._resource:
                if self._xml_file:
                    raise DSException('Resource has both XMLFILE and XML_TEMPLATE (not allowed!)')
                self._xml_template = proj_info._resource['XML_TEMPLATE']
                self._xml_outdir = proj_info._resource['XML_OUTDIR']
                if not '/' in self._xml_template:
                    self._xml_template = '%s/dstream_prod/xml/%s' % (os.environ['PUB_TOP_DIR'],self._xml_template)
                if not os.path.isfile(self._xml_template):
                    raise DSException('XML template file not found: %s' % self._xml_template)
                if not os.path.isdir(self._xml_outdir):
                    os.makedirs(self._xml_outdir)
            elif not 'XMLFILE' in proj_info._resource:
                raise DSException('XML file not specified in resource!')
            else:
                self._xml_file = proj_info._resource['XMLFILE']
                if not os.path.isfile(self._xml_file):
                    raise DSException('XML file not found: %s' % self._xml_file)

            # Store XML replacement variables if appropriate
            for key,value in proj_info._resource.iteritems():
                if not key.startswith('PUBS_XMLVAR_'): continue
                
                if not self._xml_template:
                    raise DSException('XML template file not set but replacement variable set! (%s)' % key)

                self._xml_rep_var[key]=value

            self._nresubmission = int(proj_info._resource['NRESUBMISSION'])
            self._experts = proj_info._resource['EXPERTS']
            self._period = proj_info._period
            self._version = proj_info._ver
            self._stage_names  = proj_info._resource['STAGE_NAME'].split(':')
            self._stage_digits = [int(x) for x in proj_info._resource['STAGE_STATUS'].split(':')]
            if not len(self._stage_names) == len(self._stage_digits):
                raise Exception
            for x in xrange(len(self._stage_names)):
                name  = self._stage_names[x]
                digit = self._stage_digits[x]
                self._digit_to_name[digit]=name
                self._name_to_digit[name]=digit
            self._max_runid = (int(proj_info._resource['MAX_RUN']),int(proj_info._resource['MAX_SUBRUN']))
            if proj_info._resource.has_key('MIN_RUN') and proj_info._resource.has_key('MIN_SUBRUN'):
                self._min_runid = (int(proj_info._resource['MIN_RUN']),int(proj_info._resource['MIN_SUBRUN']))

            if proj_info._resource.has_key('MAX_STATUS'):
                self._max_status = int(proj_info._resource['MAX_STATUS'])
            if proj_info._resource.has_key('MIN_STATUS'):
                self._min_status = int(proj_info._resource['MIN_STATUS'])

            # Set subrun multiplicity.

            if proj_info._resource.has_key('NSUBRUNS'):
                self._nsubruns = [int(x) for x in proj_info._resource['NSUBRUNS'].split(':')]
            else:
                self._nsubruns = [12] * len(self._stage_names)
            if len(self._nsubruns) != len(self._stage_digits):
                raise Exception
            for x in xrange(len(self._stage_digits)):
                digit = self._stage_digits[x]
                nsubruns = self._nsubruns[x]
                self._digit_to_nsubruns[digit] = nsubruns

            if 'NJOBS_LIMIT' in proj_info._resource:
                self._njobs_limit = int(proj_info._resource['NJOBS_LIMIT'])
            if 'NJOBS_TOTAL_LIMIT' in proj_info._resource:
                self._njobs_tot_limit = int(proj_info._resource['NJOBS_TOTAL_LIMIT'])

            # Set store flag.
            if proj_info._resource.has_key('STORE'):
                store_v = [int(x) for x in proj_info._resource['STORE'].split(':')]
            else:
                # Default is to store only final stage.
                store_v = [0] * len(self._stage_names)
                store_v[-1] = 1
            for x in xrange(len(self._stage_digits)):
                self._store[self._stage_digits[x]] = store_v[x]

            # Set storeana flag.
            if proj_info._resource.has_key('STOREANA'):
                storeana_v = [int(x) for x in proj_info._resource['STOREANA'].split(':')]
            else:

                # Default is to store only final stage.

                storeana_v = [0] * len(self._stage_names)
                storeana_v[-1] = 1
            for x in xrange(len(self._stage_digits)):
                self._storeana[self._stage_digits[x]] = storeana_v[x]

            # Set add location flag.
            if proj_info._resource.has_key('ADD_LOCATION'):
                add_location_v = [int(x) for x in proj_info._resource['ADD_LOCATION'].split(':')]
            else:
                # Default is to not add locations.
                add_location_v = [0] * len(self._stage_names)
            for x in xrange(len(self._stage_digits)):
                self._add_location[self._stage_digits[x]] = add_location_v[x]

            # Set add analysis location flag.
            if proj_info._resource.has_key('ADD_LOCATION_ANA'):
                add_location_ana_v = [int(x) for x in proj_info._resource['ADD_LOCATION_ANA'].split(':')]
            else:
                # Default is to not add analysis locations.
                add_location_ana_v = [0] * len(self._stage_names)
            for x in xrange(len(self._stage_digits)):
                self._add_location_ana[self._stage_digits[x]] = add_location_v[x]

            # Set check flag.
            check_v = []
            if proj_info._resource.has_key('CHECK'):
                check_v = [int(x) for x in proj_info._resource['CHECK'].split(':')]
            else:
                # Default is to check all stages.
                check_v = [1] * len(self._stage_names)


            # Set fast check flag.
            check_f = []
            if proj_info._resource.has_key('FASTCHECK'):
                check_f = [int(x) for x in proj_info._resource['FASTCHECK'].split(':')]
		#set check_v back to zero
		check_v = [0] * len(self._stage_names)		
				
            else:
                # Default is to not do fast check all stages.
                check_f = [0] * len(self._stage_names)
            
            for x in xrange(len(self._stage_digits)):
                self._check[self._stage_digits[x]] = check_v[x]
	    
	    for x in xrange(len(self._stage_digits)):
                self._fast_check[self._stage_digits[x]] = check_f[x]

            # Set checkana flag.
            if proj_info._resource.has_key('CHECKANA'):
                checkana_v = [int(x) for x in proj_info._resource['CHECKANA'].split(':')]
            else:
                # Default is to not do analysis check on any stages.
                checkana_v = [0] * len(self._stage_names)
            for x in xrange(len(self._stage_digits)):
                self._checkana[self._stage_digits[x]] = checkana_v[x]

        except Exception as e:
            self.error('Failed to load project parameters...')
            raise e


        # Get job stat
        jobstat = self._jobstat_from_log()
        if not jobstat[0]:
            self.warning('Fetching job status from log file failed! Try running cmd...')
            jobstat = self._jobstat_from_cmd()
        
        if not jobstat[0]:
            text = ''
            if not jobstat[1]:
                text = 'No job log found...'
            else:
                text = 'Job log indicates query has failed (see below).\n %s' % jobstat[1]
            self.error(text)
            raise DSException()
        
        self._jobstat = jobstat[1]
        self._njobs_tot = len(self._jobstat.split('\n'))
        if self._njobs_tot > 2:
            self._njobs_tot -= 2
        self.info('Project loaded @ %s' % self.now_str())
        return True

    def now_str(self):
        return time.strftime('%Y-%m-%d %H:%M:%S')

    def checkNext( self, statusCode, istage, run, subrun ):

        if istage in self._stage_digits:
            statusCode = istage + self.kINITIATED
            self.info( "Next stage, statusCode: %d" % statusCode )
            self._data = ''

        return statusCode

    def _jobstat_from_log(self, submit_time=None):
        result = (False,'')
        if not os.path.isfile(self.JOBSUB_LOG):
            self.error('Batch job log file not available... (check daemon, should not happen)')
            return result

        # Make sure log has been updated more recently than most recent submit.

        mod_time = os.path.getmtime(self.JOBSUB_LOG)
        self.info('Job log modification time: %s' % time.ctime(mod_time))
        if submit_time:
            self.info('Submit time: %s' % time.ctime(submit_time))
            if mod_time < submit_time + 60:
                return result

        log_age = time.time() - mod_time
        if log_age + 10 > self._period:
            return result

        contents = open(self.JOBSUB_LOG,'r').read()
        return (self._check_jobstat_str(contents),contents)

    def _jobstat_from_cmd(self,jobid=None):
        cmd = ['jobsub_q', '--user', os.environ['USER'] ]
        if jobid:
            cmd.append('--jobid')
            cmd.append('%s' % jobid)
        try:
            proc = subprocess.Popen( cmd, stdout = subprocess.PIPE, stderr = subprocess.STDOUT )
            jobout, joberr = proc.communicate()
        except Exception:
            self.error('Failed to execute a command: %s' % ' '.join(cmd))
            self.error('Reporting Output:\n %s' % jobout)
            return (False,jobout)

        # Check if te return code is 0
        proc_return = proc.poll()
        if proc_return != 0:
            self.error('Non-zero return code (%s) from %s' % (proc_return,cmd))
            self.error('Reporting Output:\n %s' % jobout)
            return (False,jobout)

        return (self._check_jobstat_str(jobout),jobout)

    def _check_jobstat_str(self,stat_str):

        # Check job out
        failure_codes = ['Traceback (most recent call last):',
                         'Failed to fetch']
        success_codes = ['JOBSUBJOBID']
        for code in failure_codes:
            if stat_str.find(code) >=0:
                #print "found:",code
                return False
        for code in success_codes:
            if stat_str.find(code) < 0:
                #print "not found:",code
                return False
        return True

    # This function checks whether a single (run, subrun) pair is good or not.
    # Return True (good) or False (bad).

    def check_subrun(self, stagename, run, subrun):

        self.info('Checking input readiness for run %d, subrun %d' % (run,subrun))

        xml = self.getXML(run)
        self.info('XML = %s' % xml)

        # First check if we are reading files from sam.

        probj = project.get_project(xml, '', stagename)
        stobj = probj.get_stage(stagename)

        # If we are not reading from files (generator or sam input), always return True.

        
        if stobj.inputfile == '' and stobj.inputlist == '':
            return True

        # Check if this (run, subrun) has pubs input available.
        result = False
        try:
            real_stdout = sys.stdout
            real_stderr = sys.stderr
            sys.stdout = StringIO.StringIO()
            sys.stderr = StringIO.StringIO()
            project.get_pubs_stage(xml, '', stagename, run, [subrun], self._version)
            result = True
            strout = sys.stdout.getvalue()
            strerr = sys.stderr.getvalue()
            sys.stdout = real_stdout
            sys.stderr = real_stderr
            if strout:
                self.info(strout)
            if strerr:
                self.warning(strerr)
        except:
            sys.stdout = real_stdout
            sys.stderr = real_stderr
            result = False

        if not result:
            self.info('Input not ready.')

        # Done.

        return result

    def submit( self, statusCode, istage, run, subruns ):
        current_status = statusCode + istage
        error_status   = current_status + 1000
        
        # Report starting
        self.info('Submit run %d, subruns %s' % (run, str(subruns)))
        self.info('XML = %s' % self.getXML(run))
        self._data = str( self._data )

        # Main command
        stage = self._digit_to_name[istage]
        try:
            real_stdout = sys.stdout
            real_stderr = sys.stderr
            sys.stdout = StringIO.StringIO()
            sys.stderr = StringIO.StringIO()
            probj, stobj = project.get_pubs_stage(self.getXML(run), '', stage, run, subruns,
                                                  self._version)
            strout = sys.stdout.getvalue()
            strerr = sys.stderr.getvalue()
            sys.stdout = real_stdout
            sys.stderr = real_stderr
            if strout:
                self.info(strout)
            if strerr:
                self.warning(strerr)
        except PubsDeadEndError:
            sys.stdout = real_stdout
            sys.stderr = real_stderr
            self.info('Exception PubsDeadEndError raised by project.get_pubs_stage')
            return 100
        except PubsInputError:
            sys.stdout = real_stdout
            sys.stderr = real_stderr
            self.info('Exception PubsInputError raised by project.get_pubs_stage')
            return current_status
        except:
            sys.stdout = real_stdout
            sys.stderr = real_stderr
            self.error('Exception raised by project.get_pubs_stage:')
            e = sys.exc_info()
            for item in e:
                self.error(item)
            for line in traceback.format_tb(e[2]):
                self.error(line)
            return current_status

        # Make sure we are getting job fcl from the correct uboonecode version.

        if probj.release_tag != os.environ['UBOONECODE_VERSION']:
            self.error('Project version mismatch between environment and xml file.')
            raise Exception

        # Submit job.
        jobid=''
        try:
            real_stdout = sys.stdout
            real_stderr = sys.stderr
            sys.stdout = StringIO.StringIO()
            sys.stderr = StringIO.StringIO()

            # Submit jobs.

            jobid = project.dosubmit(probj, stobj)
            strout = sys.stdout.getvalue()
            strerr = sys.stderr.getvalue()
            sys.stdout = real_stdout
            sys.stderr = real_stderr
            if strout:
                self.info(strout)
            if strerr:
                self.warning(strerr)
        except:
            sys.stdout = real_stdout
            sys.stderr = real_stderr
            self.error('Exception raised by project.dosubmit:')
            e = sys.exc_info()
            for item in e:
                self.error(item)
            for line in traceback.format_tb(e[2]):
                self.error(line)
            return current_status
        self.info( 'Submit jobs: xml: %s, stage: %s' %( self.getXML(run), stage ) )

        # Delete the job log, which is now obsolete.

        try:
            os.remove(self.JOBSUB_LOG)
        except:
            pass

        # Tentatively do so; need to change!!!
        if not jobid:
            self.error('Failed to fetch job log id...')
            subject = 'Failed to fetch job log id while submitting project %s stage %s.' % (
                probj.name, stobj.name)
            text = subject
            text += '\n'
            text += 'Status code is set to %d!\n\n' % error_status
            pub_smtp(receiver = self._experts,
                     subject = subject,
                     text = text)
            return error_status

        # Now grab the parent job id and submit time.
        single_data = '%s+%f' % (jobid, time.time())

        statusCode = istage + self.kSUBMITTED
        self.info( "Submitted jobs, jobid: %s, status: %d" % ( single_data, statusCode ) )

        self._njobs += len(subruns)
        self._njobs_tot += len(subruns)

        # Here we need to convert the job data into a list with one entry for each subrun.
        # In case of input from sam, we keep the original job id and copy it for each job,
        # since we have no way of knowing what the job ids of the parallel workers will
        # be at this point.  This jobid will be the dagman jobid, which will run until
        # every worker is finished.
        # In case of input from a file list, increment the process number encoded in
        # the job id for each subrun, up to stobj.num_jobs jobs.

        n1 = single_data.find('.')
        n2 = single_data.find('@')
        multi_data = []
        if n1 > 0 and n2 > 0 and n2 > n1 and stobj.inputlist != '':
            head = single_data[:n1+1]
            tail = single_data[n2:]
            process=0
            for subrun in subruns:
                if process < stobj.num_jobs:
                    multi_data.append('%s%d%s' % (head, process, tail))
                else:
                    multi_data.append('Merge %d' % subruns[0])
                process += 1
        else:
            for subrun in subruns:
                multi_data.append(single_data)
        self._data = multi_data

        # Pretend I'm doing something
        #time.sleep(5)

        # Here we may need some checks
        return statusCode

    def isRunning( self, statusCode, istage, run, subrun ):
        current_status = statusCode + istage
        error_status   = current_status + 1000

        self._data = str( self._data )

        # Merged subruns handled here.

        if self._data[:5] == 'Merge' and self._data.find(':') < 0:
            merge_subrun = int(self._data[5:])
            merge_runid = (run, merge_subrun)
            if self._runid_status.has_key(merge_runid):
                merge_status = self._runid_status[merge_runid]
            else:
                merge_ds_status = self._api.get_status(ds_status(self._table, run, merge_subrun, 0))
                merge_status = merge_ds_status._status
                self._runid_status[merge_runid] = merge_status

            if merge_status in [istage + self.kSUBMITTED, istage + self.kRUNNING]:
                self._njobs += 1

            if merge_status == istage + self.kREADYFORSAM or \
                    merge_status == istage + self.kDECLARED or \
                    merge_status == istage + 10:

                # If we get here, the merge batch job was successful, and we
                # can set the status for this subrun to ignore further processing.

                return 100

            elif self._runid_status[merge_runid] == istage + self.kTOBERECOVERED:

                # If we get here, the merge batch job failed.  Set the 
                # status for this subrun to recover.

                return istage + self.kTOBERECOVERED

            elif self._runid_status[merge_runid] > 1000:

                self.error('Merged job failed (run,subrun) = (%d,%d) for subrun %d' % (run,subrun,merge_subrun))
                return current_status + 1000

            else:
                # Any other status, leave the current status the same.
                return current_status

        # Check the status of all job ids listed in job data.

        is_running = False
        for job_data in self._data.strip().split(':'):
            job_data_list = job_data.split('+')
            jobid = job_data_list[0]
            if len(jobid) < 2:
                continue

            #if len(job_data_list) > 1:
            #    submit_time = float(job_data_list[1])
            #else:
            #    submit_time = float(0)

            job_status = 0
            target_jobs = [x for x in self._jobstat.split('\n') if x.startswith(jobid)]
            for line in target_jobs:
                words = line.split()
                job_state = words[5]
                if job_state == 'X':
                    continue
                job_status = self.kSUBMITTED
                is_running = True
                if job_state == 'R':
                    job_status = self.kRUNNING
                    statusCode = self.kRUNNING
                    break
            msg = 'jobid: %s: ' % jobid
            if job_status == self.kSUBMITTED:
                msg += 'SUBMITTED'
            elif job_status == self.kRUNNING:
                msg += 'RUNNING'
            elif job_status == 0:
                msg += 'FINISHED'
            else:
                msg += 'UNKNOWN'
            self.info(msg)

        if not is_running:
            statusCode = self.kFINISHED
        else:
            self._njobs += 1
        statusCode += istage
        return statusCode

    def check( self, statusCode, istage, run, subrun ):
        self.info('Check run %d, subrun %d' % (run, subrun))
        self.info('XML = %s' % self.getXML(run))
        self._data = str( self._data )
        nSubmit     = None
	samweb = project_utilities.samweb()

        # Get the number of job submissions.
        if self._data != None and len(self._data) > 0:

            holder = self._data.split(':')
            nSubmit = len(holder)

        # Check the finished jobs
        stage = self._digit_to_name[istage]

        # Get project and stage object.
        try:
            real_stdout = sys.stdout
            real_stderr = sys.stderr
            sys.stdout = StringIO.StringIO()
            sys.stderr = StringIO.StringIO()
            probj, stobj = project.get_pubs_stage(self.getXML(run), '', stage, run, [subrun], self._version)
            strout = sys.stdout.getvalue()
            strerr = sys.stderr.getvalue()
            sys.stdout = real_stdout
            sys.stderr = real_stderr
            if strout:
                self.info(strout)
            if strerr:
                self.warning(strerr)
        except:
            sys.stdout = real_stdout
            sys.stderr = real_stderr
            self.error('Exception raised by project.get_pubs_stage:')
            e = sys.exc_info()
            for item in e:
                self.error(item)
            for line in traceback.format_tb(e[2]):
                self.error(line)
            return statusCode + istage 

        # Make sure there is only a single subdirectory in the output and log directories.

        nout = 0
        nlog = 0
        for path, subdirs, files in larbatch_posix.walk(stobj.outdir):
            #self.debug(path)
            dname = path.split('/')[-1]
            if not len(dname.split('_'))==2 or not dname.split('_')[0].isdigit() or not dname.split('_')[1].isdigit():
                continue
            if path != stobj.outdir:
                nout += 1
            if nout > 1:
                self.info('Deleting extra output directory %s' % path)
                shutil.rmtree(path)
                nout -= 1
        for path, subdirs, files in larbatch_posix.walk(stobj.logdir):
            #self.debug(path)
            dname = path.split('/')[-1]
            if not len(dname.split('_'))==2 or not dname.split('_')[0].isdigit() or not dname.split('_')[1].isdigit():
                continue
            if path != stobj.logdir:
                nlog += 1

        # If there is more than one subdirectory in either place, return an error.

        if nout > 1 or nlog > 1:
            self.error('More than one batch subdirectory.')
            self.error('Output directory: %s' % stobj.outdir)
            self.error('Log directory: %s' % stobj.logdir)
            return statusCode + 1000

        # Do check.
        try:
            self.info('Invoking project.doshorten')
            real_stdout = sys.stdout
            real_stderr = sys.stderr
            sys.stdout = StringIO.StringIO()
            sys.stderr = StringIO.StringIO()
            project.doshorten(stobj)
            check_status = 0
            if self._check[istage]:
                self.info('Invoking project.docheck for artroot files')
                check_status = project.docheck(probj, stobj, ana=False)
            elif self._checkana[istage]:
                self.info('Invoking project.docheck for analysis files')
                check_status = project.docheck(probj, stobj, ana=True)
	    elif self._fast_check[istage]:
	         self.info('Invoking project.doquickcheck for artroot files')
		 check_status = project.doquickcheck(probj, stobj, ana=True)
	        	                
            strout = sys.stdout.getvalue()
            strerr = sys.stderr.getvalue()
            sys.stdout = real_stdout
            sys.stderr = real_stderr
            if strout:
                self.info(strout)
            if strerr:
                self.warning(strerr)
        except:
            sys.stdout = real_stdout
            sys.stderr = real_stderr
            self.error('Exception raised by project.docheck:')
            e = sys.exc_info()
            for item in e:
                self.error(item)
            for line in traceback.format_tb(e[2]):
                self.error(line)
            check_status = 1
        nopubs_stobj = stobj
	nopubs_stobj.pubs_output = 0
	dim = project_utilities.dimensions(probj, nopubs_stobj, ana=False)
	#add run numbers to sam query
	dim = dim + (" and run_number %d.%d" % (run, subrun) )
	#swap the "anylocation" flag to "physicallocation" if it exists.
	#if the "anylocation" flag doesn't exist, don't do anything since SAM defaults to physical
	
	if("anylocation" in dim):
	  dim = dim.replace("anylocation", "physical", 1)
        
        # Update pubs status.
        if check_status == 0:
           statusCode = self.kREADYFORSAM
           self._data = ''
	
	
	#See if we can find the file in SAM. If we can, then the job (probably) finished okay, despite what PUBs thinks
	elif samweb.countFiles(dimensions=dim) > 0:
	   self.info('Run: %d Subrun: %d Failed check, but file exists in SAM. Assuming all is OK' % (run, subrun) )
	   statusCode = self.kREADYFORSAM
           self._data = ''

        elif nSubmit > self._nresubmission:
           # If the sample has been submitted more than a certain number
           # of times, email the expert, and move on to the next stage
           subject = "%s jobs fails after %d resubmissions" % (self._project,nSubmit)
           text = """
Sample     : %s
Stage      : %s
Job IDs    : %s
           """ % ( self._project, self._digit_to_name[istage], self._data.split(':')[2:] )
           try:
               pub_smtp( os.environ['PUB_SMTP_ACCT'], os.environ['PUB_SMTP_SRVR'], os.environ['PUB_SMTP_PASS'], self._experts, subject, text )
           except Exception:
               self.error('Failed to send emails...')
               self.error(text)

           #statusCode = self.kDONE
           #istage += 10
           statusCode += 1000
        else:
           statusCode = self.kTOBERECOVERED

        statusCode += istage
        self.info("Checked job, status: %d" % statusCode)

        # Pretend I'm doing something
        #time.sleep(5)

        # Here we may need some checks

        return statusCode
    # def check()

    # Single-subrun recovery.

    def single_recover( self, statusCode, istage, run, subrun ):
        result = self.recover(statusCode, istage, run, [subrun])
        self._data = self._data[0]
        return result

    # Multiple-subrun recovery.

    def recover( self, statusCode, istage, run, subruns ):
        current_status = statusCode + istage
        error_status   = current_status + 1000
                             
        # Report starting
        self.info('Recover run %d, subruns %s' % (run, str(subruns)))
        self.info('XML = %s' % self.getXML(run))
        self._data = str( self._data )

        # Main command
        stage = self._digit_to_name[istage]
        try:
            real_stdout = sys.stdout
            real_stderr = sys.stderr
            sys.stdout = StringIO.StringIO()
            sys.stderr = StringIO.StringIO()
            probj, stobj = project.get_pubs_stage(self.getXML(run), '', stage, run, subruns,
                                                  self._version)
            strout = sys.stdout.getvalue()
            strerr = sys.stderr.getvalue()
            sys.stdout = real_stdout
            sys.stderr = real_stderr
            if strout:
                self.info(strout)
            if strerr:
                self.warning(strerr)
        except PubsInputError:
            sys.stdout = real_stdout
            sys.stderr = real_stderr
            self.info('Exception PubsInputError raised by project.get_pubs_stage')
            return current_status
        except:
            self.error('Exception raised by project.get_pubs_stage:')
            e = sys.exc_info()
            for item in e:
                self.error(item)
            for line in traceback.format_tb(e[2]):
                self.error(line)
            return current_status

        # Make sure we are getting job fcl from the correct uboonecode version.

        if probj.release_tag != os.environ['UBOONECODE_VERSION']:
            self.error('Project version mismatch between environment and xml file.')
            raise Exception

        # Submit job.
        jobid=''
        try:
            real_stdout = sys.stdout
            real_stderr = sys.stderr
            sys.stdout = StringIO.StringIO()
            sys.stderr = StringIO.StringIO()
            jobid = project.dosubmit(probj, stobj)
            strout = sys.stdout.getvalue()
            strerr = sys.stderr.getvalue()
            sys.stdout = real_stdout
            sys.stderr = real_stderr
            if strout:
                self.info(strout)
            if strerr:
                self.warning(strerr)
        except:
            sys.stdout = real_stdout
            sys.stderr = real_stderr
            self.error('Exception raised by project.dosubmit:')
            e = sys.exc_info()
            for item in e:
                self.error(item)
            for line in traceback.format_tb(e[2]):
                self.error(line)
            return current_status
        self.info( 'Resubmit jobs: xml: %s, stage: %s' %( self.getXML(run), stage ) )

        # Tentatively do so; need to change!!!
        if not jobid:
            self.error('Failed to fetch job log id...')
            subject = 'Failed to fetch job log id while submitting project %s stage %s.' % (
                probj.name, stobj.name)
            text = subject
            text += '\n'
            text += 'Status code is set to %d!\n\n' % error_status
            pub_smtp(receiver = self._experts,
                     subject = subject,
                     text = text)
            return error_status

        # Now grab the parent job id and submit time
        single_data = '%s+%f' % (jobid, time.time())
        original_data = None
        if self._data != None and self._data != "None" and len(self._data) != 0:
            original_data = self._data

        statusCode = istage + self.kSUBMITTED
        self.info( "Resubmitted jobs, job id: %s, status: %d" % ( self._data, statusCode ) )

        # Here we need to convert the job data into a list with one entry for each subrun.
        # In case of input from sam, we keep the original job id and copy it for each job,
        # since we have no way of knowing what the job ids of the parallel workers will
        # be at this point.  This jobid will be the dagman jobid, which will run until
        # every worker is finished.
        # In case of input from a file list, increment the process number encoded in
        # the job id for each subrun, up to stobj.num_jobs jobs.

        n1 = single_data.find('.')
        n2 = single_data.find('@')
        multi_data = []
        if n1 > 0 and n2 > 0 and n2 > n1 and stobj.inputlist != '':
            head = single_data[:n1+1]
            tail = single_data[n2:]
            process=0
            for subrun in subruns:
                if process < stobj.num_jobs:
                    if original_data != None:
                        multi_data.append('%s:%s%d%s' % (original_data, head, process, tail))
                    else:
                        multi_data.append('%s%d%s' % (head, process, tail))
                else:
                    multi_data.append('Merge %d' % subruns[0])
                process += 1
        else:
            for subrun in subruns:
                if original_data != None:
                    multi_data.append('%s:%s' % (original_data, single_data))
                else:
                    multi_data.append(single_data)
        self._data = multi_data



        # Pretend I'm doing something
        #time.sleep(5)

        # Here we may need some checks
        return statusCode

    # def recover()
        
    def __decode_status__(self,arg):
        try:
            arg = int(arg)
        except ValueError:
            raise
        arg = arg%10
        if not arg in self.__class__.PROD_STATUS:
            self.error( 'HEY this is not a valid status code!: %d' % arg )
        return arg
    # def __decode_status__()

    def declare( self, statusCode, istage, run, subrun ):

        self.info('Declare run %d, subrun %d' % (run, subrun))
        self.info('XML = %s' % self.getXML(run))

        # Get stage name.
        stage = self._digit_to_name[istage]

        # Get project and stage object.
        try:
            real_stdout = sys.stdout
            real_stderr = sys.stderr
            sys.stdout = StringIO.StringIO()
            sys.stderr = StringIO.StringIO()
            probj, stobj = project.get_pubs_stage(self.getXML(run), '', stage, run, [subrun], self._version)
            strout = sys.stdout.getvalue()
            strerr = sys.stderr.getvalue()
            sys.stdout = real_stdout
            sys.stderr = real_stderr
            if strout:
                self.info(strout)
            if strerr:
                self.warning(strerr)
        except:
            sys.stdout = real_stdout
            sys.stderr = real_stderr
            self.error('Exception raised by project.get_pubs_stage:')
            e = sys.exc_info()
            for item in e:
                self.error(item)
            for line in traceback.format_tb(e[2]):
                self.error(line)
            return statusCode + istage 

        # Do declaration.
        try:
            real_stdout = sys.stdout
            real_stderr = sys.stderr
            sys.stdout = StringIO.StringIO()
            sys.stderr = StringIO.StringIO()

            # Declare artroot files.

            bookdir = stobj.logdir
            try:
                bookdir = stobj.bookdir
            except:
                bookdir = stobj.logdir
            declare_status = project.docheck_declarations(bookdir, stobj.outdir,
                                                          declare=True, ana=False)

            # Declare analysis root files.

            if declare_status == 0:
                declare_status = project.docheck_declarations(bookdir, stobj.outdir,
                                                              declare=True, ana=True)

            # Create artroot dataset definition.

            if declare_status == 0:
                nopubs_stobj = stobj
                nopubs_stobj.pubs_output = 0
                dim = project_utilities.dimensions(probj, nopubs_stobj, ana=False)
                declare_status = project.docheck_definition(stobj.defname, dim, True)

            # Create analysis dataset definition.

            if declare_status == 0:
                nopubs_stobj = stobj
                nopubs_stobj.pubs_output = 0
                dim = project_utilities.dimensions(probj, nopubs_stobj, ana=True)
                declare_status = project.docheck_definition(stobj.ana_defname, dim, True)

            strout = sys.stdout.getvalue()
            strerr = sys.stderr.getvalue()
            sys.stdout = real_stdout
            sys.stderr = real_stderr
            if strout:
                self.info(strout)
            if strerr:
                self.warning(strerr)
        except:
            sys.stdout = real_stdout
            sys.stderr = real_stderr
            self.error('Exception raised by project.docheck_definitions:')
            e = sys.exc_info()
            for item in e:
                self.error(item)
            for line in traceback.format_tb(e[2]):
                self.error(line)
            return statusCode + istage

        # Update pubs status.
        if declare_status == 0:
           statusCode = self.kDECLARED

        statusCode += istage
        self.info("SAM declarations, status: %d" % statusCode)

        # Pretend I'm doing something
        #time.sleep(5)

        # Here we may need some checks

        return statusCode
    # def declare( self, statusCode, istage, run, subrun ):


    def store( self, statusCode, istage, run, subrun ):

        # Check store flag.

        if not self._store[istage] and not self._storeana[istage] and not self._add_location[istage] and not self._add_location_ana[istage]:
            self.info('Skipping store.')
            #statusCode = self.kDONE
            #istage += 10
            statusCode = self.kSTORED
            return statusCode + istage

        self.info('Store run %d, subrun %d' % (run, subrun))
        self.info('XML = %s' % self.getXML(run))

        # Get stage name.
        stage = self._digit_to_name[istage]

        # Get project and stage object.
        try:
            real_stdout = sys.stdout
            real_stderr = sys.stderr
            sys.stdout = StringIO.StringIO()
            sys.stderr = StringIO.StringIO()
            probj, stobj = project.get_pubs_stage(self.getXML(run), '', stage, run, [subrun], self._version)
            strout = sys.stdout.getvalue()
            strerr = sys.stderr.getvalue()
            sys.stdout = real_stdout
            sys.stderr = real_stderr
            if strout:
                self.info(strout)
            if strerr:
                self.warning(strerr)
        except:
            sys.stdout = real_stdout
            sys.stderr = real_stderr
            self.error('Exception raised by project.get_pubs_stage:')
            e = sys.exc_info()
            for item in e:
                self.error(item)
            for line in traceback.format_tb(e[2]):
                self.error(line)
            return statusCode + istage 

        # Do store.
        try:
            real_stdout = sys.stdout
            real_stderr = sys.stderr
            sys.stdout = StringIO.StringIO()
            sys.stderr = StringIO.StringIO()

            # Store files.

            store_status = 0
            if self._store[istage] or self._add_location[istage]:
                self.info('Storing artroot files.')
                dim = project_utilities.dimensions(probj, stobj, ana=False)
                store_status = project.docheck_locations(dim, stobj.outdir, 
                                                         add=self._add_location[istage],
                                                         clean=False,
                                                         remove=False,
                                                         upload=self._store[istage])

            if (self._storeana[istage] or self._add_location_ana[istage]) and store_status == 0 and stobj.ana_data_tier != '':
                self.info('Storing analysis root files.')
                dim = project_utilities.dimensions(probj, stobj, ana=True)
                store_status = project.docheck_locations(dim, stobj.outdir, 
                                                         add=self._add_location_ana[istage],
                                                         clean=False,
                                                         remove=False,
                                                         upload=self._storeana[istage])

            strout = sys.stdout.getvalue()
            strerr = sys.stderr.getvalue()
            sys.stdout = real_stdout
            sys.stderr = real_stderr
            if strout:
                self.info(strout)
            if strerr:
                self.warning(strerr)
        except:
            sys.stdout = real_stdout
            sys.stderr = real_stderr
            self.error('Exception raised by project.docheck_locations:')
            e = sys.exc_info()
            for item in e:
                self.error(item)
            for line in traceback.format_tb(e[2]):
                self.error(line)
            return statusCode + istage

        # Update pubs status.
        if store_status == 0:
           statusCode = self.kSTORED

        # Pretend I'm doing something
        #time.sleep(5)

        statusCode += istage
        self.info("SAM store, status: %d" % statusCode)

        # Pretend I'm doing something
        #time.sleep(5)

        # Here we may need some checks

        return statusCode
    # def store( self, statusCode, istage, run, subrun ):


    def check_location( self, statusCode, istage, run, subrun ):
        self.info('Check location for run %d, subrun %d' % (run, subrun))
        self.info('XML = %s' % self.getXML(run))

        # Check store flag.

        if not self._store[istage] and not self._storeana[istage] and not self._add_location[istage] and not self._add_location_ana[istage]:
            self.info('Skipping check location.')
            statusCode = self.kDONE
            istage += 10
            return statusCode + istage

        # Get stage name.
        stage = self._digit_to_name[istage]

        # Get project and stage object.
        try:
            real_stdout = sys.stdout
            real_stderr = sys.stderr
            sys.stdout = StringIO.StringIO()
            sys.stderr = StringIO.StringIO()
            probj, stobj = project.get_pubs_stage(self.getXML(run), '', stage, run, [subrun], self._version)
            strout = sys.stdout.getvalue()
            strerr = sys.stderr.getvalue()
            sys.stdout = real_stdout
            sys.stderr = real_stderr
            if strout:
                self.info(strout)
            if strerr:
                self.warning(strerr)
        except:
            sys.stdout = real_stdout
            sys.stderr = real_stderr
            self.error('Exception raised by project.get_pubs_stage:')
            e = sys.exc_info()
            for item in e:
                self.error(item)
            for line in traceback.format_tb(e[2]):
                self.error(line)
            return statusCode + istage 

        # Check for locations.

        samweb = project_utilities.samweb()

        loc_status = 0
        if self._store[istage] or self._add_location[istage]:
            nfile = 0
            loc_status = 1
            dim = project_utilities.dimensions(probj, stobj, ana=False)
            filelist = samweb.listFiles(dimensions=dim, stream=True)
            while 1:
                try:
                    filename = filelist.next()
                except StopIteration:
                    break

                # Got a filename.

                nfile = nfile + 1
                self.info('Checking location: %s' % filename)

                # Look for locations.

                has_location = False
                sam_locs = samweb.locateFile(filenameorid=filename)
                for sam_loc in sam_locs:
                    has_location = True
                    break
                if has_location:
                    self.info('Artroot file has location.')
                    loc_status = 0
                else:
                    self.info('Artroot file does not have a location.')
            if nfile == 0:
                loc_status = 0

        loc_status_ana = 0
        if self._storeana[istage] or self._add_location_ana[istage]:
            nfile_ana = 0
            loc_status_ana = 1
            dim = project_utilities.dimensions(probj, stobj, ana=True)
            filelist = samweb.listFiles(dimensions=dim, stream=True)
            while 1:
                try:
                    filename = filelist.next()
                except StopIteration:
                    break

                # Got a filename.

                nfile_ana = nfile_ana + 1
                self.info('Checking location: %s' % filename)

                # Look for locations.

                has_location = False
                sam_locs = samweb.locateFile(filenameorid=filename)
                for sam_loc in sam_locs:
                    has_location = True
                    break
                if has_location:
                    self.info('Analysis file has location.')
                    loc_status_ana = 0
                else:
                    self.info('Analysis file does not have a location.')
            if nfile_ana == 0:
                loc_status_ana = 0

        # Update pubs status.
        if loc_status == 0 and loc_status_ana == 0:
           statusCode = self.kDONE
           istage += 10

        # Pretend I'm doing something
        #time.sleep(5)

        # If all the stages complete, send an email to experts
        if not istage in self._stage_digits:
            self.info("Completed: %s Run %d SubRun %d" % (self._project,run,subrun))

        statusCode += istage
        self.info("SAM store, status: %d" % statusCode)

        # Pretend I'm doing something
        #time.sleep(5)

        # Here we may need some checks

        return statusCode
    # def check_location( self, statusCode, istage, run, subrun ):


    ## @brief access DB and retrieves new runs
    def process( self ):

        # Get a fresh production proxy.

        if os.environ.has_key('X509_USER_CERT') and os.environ.has_key('X509_USER_KEY'):
            cmd=['voms-proxy-init',
                 '-hours', '24',
                 '-rfc',
                 '-cert', os.environ['X509_USER_CERT'],
                 '-key', os.environ['X509_USER_KEY'],
                 '-voms', 'fermilab:/fermilab/uboone/Role=Production']
            try:
                subprocess.check_call(cmd, stdout=-1, stderr=-1)
                self.info('Succeeded to get production grid proxy')
                os.environ['X509_USER_PROXY'] = subprocess.check_output(['voms-proxy-info', '-path']).strip()
                self.info('Proxy path: %s' % os.environ['X509_USER_PROXY'])
                del os.environ['X509_USER_CERT']
                del os.environ['X509_USER_KEY']
            except:
                self.info('Failed to get production grid proxy')

        ctr = self._nruns
        #return
        # Kazu's version of submit jobs
        stage_v  = list(self._stage_digits)
        stage_v.reverse()
        status_v = list(self.PROD_STATUS)
        status_v.reverse()
        # temporary fix: record the processed run and only process once per process function call
        processed_run=[]
        for istage in stage_v:
            self.info('Inspecting stage %s @ %s' % (istage,self.now_str()))
            for istatus in status_v:
                if istatus > self._max_status:
                    continue
                if istatus < self._min_status:
                    continue
                fstatus = istage + istatus

                if istatus == self.kINITIATED:
                    if self._njobs_limit and self._njobs > self._njobs_limit:
                        self.info('Skipping job submission stage: # running/queued project jobs = %d > set limit (%d)' % (self._njobs,self._njobs_limit))
                        continue
                    if self._njobs_tot_limit and self._njobs_tot > self._njobs_tot_limit:
                        self.info('Skipping job submission stage: # running/queued total jobs = %d > set limit (%d)' % (self._njobs_tot,self._njobs_tot_limit))
                        continue

                self.info('Inspecting status %s @ %s' % (fstatus,self.now_str()))
                
                target_list = []
                if fstatus == self.kINITIATED and self._parent:
                    target_list = self.get_xtable_runs([self._table,self._parent],[fstatus,self._parent_status])
                else:
                    target_list = self.get_runs( self._table, fstatus )

                run_subruns = {}
                nsubruns = 0
                for x in target_list:

                    if istatus == self.kINITIATED:
                        if self._njobs_limit and self._njobs > self._njobs_limit:
                            self.info('Breaking from job submission stage: # running/queued project jobs = %d > set limit (%d)' % (self._njobs,self._njobs_limit))
                            break
                        if self._njobs_tot_limit and self._njobs_tot > self._njobs_tot_limit:
                            self.info('Breaking from job submission stage: # running/queued total jobs = %d > set limit (%d)' % (self._njobs_tot,self._njobs_tot_limit))
                            break
                    
                    run    = int(x[0])
                    subrun = int(x[1])
                    runid = (run,subrun)

                    if self._max_runid and runid > self._max_runid:
                        self.debug('Ignoring (run,subrun) = (%d,%d) above set run range max (%d,%d)' % (run,subrun,self._max_runid[0],self._max_runid[1]))
                        continue
                    if self._min_runid and runid < self._min_runid:
                        self.debug('Ignoring (run,subrun) = (%d,%d) below set run range min (%d,%d)' % (run,subrun,self._min_runid[0],self._min_runid[1]))
                        continue
                    if runid in processed_run: continue
                    processed_run.append(runid)

                    if istatus == self.kINITIATED or istatus == self.kTOBERECOVERED:
                        if not self.check_subrun(self._digit_to_name[istage], run, subrun):
                            self.debug('Skipping (run,subrun) = (%d,%d) ... not ready to be process next stage' % (run,subrun))
                            continue

                    self.info('Found run/subrun: %s/%s' % (run,subrun))
                    if not run_subruns.has_key(run):
                        self.info('Found run: %s ... inspecting @ %s' % (run,self.now_str()))
                        run_subruns[run] = set()
                    if not subrun in run_subruns[run]:
                        run_subruns[run].add(subrun)
                        nsubruns += 1

                    if nsubruns >= self._nruns:
                        self.info('Quitting run/subrun loop because of nruns limit')
                        break

                # Loop over runs.
                for run in sorted(run_subruns.keys(), reverse=True):
                    all_subruns = run_subruns[run].copy()

                    # Process subruns in groups.

                    subruns = []
                    while len(all_subruns) > 0:
                        subrun = all_subruns.pop()
                        subruns.append(subrun)
                        if len(subruns) >= self._digit_to_nsubruns[istage] or len(all_subruns) == 0:

                            subruns.sort()
                            statusCode = self.__decode_status__( fstatus )

                            # Do actions associated with multiple subruns.

                            multiaction = self.PROD_MULTIACTION[statusCode]
                            if multiaction != None:
                                status = self._api.get_status(ds_status(self._table,
                                                                        run, subruns[0], 0))
                                self._data = status._data
                                self.info('Starting a multiple subrun action: %s @ %s' % (
                                        multiaction.__name__, self.now_str()))
                                self.info('Run %s' % run)
                                self.info('Subruns: %s' % str(subruns))

                                # Multiaction might truncate subrun list.

                                before_subruns = set(subruns)
                                statusCode = multiaction( statusCode, istage, run, subruns )

                                # Return unprocessed subruns to original set of subruns.

                                unprocessed_subruns = before_subruns - set(subruns)
                                if len(unprocessed_subruns) > 0:
                                    self.info('Unprocessed subruns: %s' % unprocessed_subruns)
                                    all_subruns.update(unprocessed_subruns)

                                # Done.

                                self.info('Finished a multiple subrun action: %s @ %s' % (
                                        multiaction.__name__, self.now_str()))

                                # Create a status object to be logged to DB (if necessary)
                                # Do this for each subrun.

                                process = 0
                                for subrun in subruns:
                                    data = self._data
                                    if type(self._data) == type([]):
                                        if process < len(self._data):
                                            data = self._data[process]
                                        else:
                                            data = None
                                    status = ds_status( project = self._table,
                                                        run     = run,
                                                        subrun  = subrun,
                                                        seq     = 0,
                                                        status  = statusCode,
                                                        data    = data )
                                    runid = (run, subrun)
                                    self._runid_status[runid] = statusCode

                                    # Log status
                                    self.log_status( status )
                                    process += 1

                                # Counter decreases by number of subruns
                                if fstatus != statusCode:
                                    ctr -= len(subruns)

                                # Break from loop if counter became 0
                                if ctr < 0:
                                    self.info('Quitting because of nruns limit')
                                    return

                            subruns = []


                    # Loop over subruns and do single-subrun actions.

                    for subrun in run_subruns[run]:

                        statusCode = self.__decode_status__( fstatus )
                        action = self.PROD_ACTION[statusCode]
                        if action != None:

                            # Read data.

                            status = self._api.get_status(ds_status(self._table,
                                                                    run, subrun, 0))
                            old_data  = status._data
                            old_state = status._status
                            self._data = status._data

                            self.info('Starting an action: %s @ %s' % (
                                    action.__name__,self.now_str()))
                            statusCode = action( statusCode, istage, run, subrun )
                            self.info('Finished an action: %s @ %s' % (
                                    action.__name__,self.now_str()))

                            # Create a status object to be logged to DB (if necessary)
                            if not old_state == statusCode or not self._data == old_data:
                                self.log_status( ds_status( project = self._table,
                                                            run     = run,
                                                            subrun  = subrun,
                                                            seq     = 0,
                                                            status  = statusCode,
                                                            data    = self._data ) )

                                # Counter decreases by 1
                                ctr -=1

                            runid = (run, subrun)
                            self._runid_status[runid] = statusCode

                            # Break from loop if counter became 0
                            if ctr < 0:
                                self.info('Quitting because of nruns limit')
                                return
        return


# A unit test section
if __name__ == '__main__':

    proj_name = sys.argv[1]
    if len(sys.argv) > 2:
        table_name = sys.argv[2]
    else:
        table_name = proj_name

    test_obj = production(proj_name, table_name)
    
    now_str = time.strftime('%Y-%m-%d %H:%M:%S')
    test_obj.info("Project %s start @ %s" % (proj_name,now_str))
    
    test_obj.process()
    
    now_str = time.strftime('%Y-%m-%d %H:%M:%S')
    test_obj.info("Project %s end @ %s" % (proj_name,now_str))

    #sys.exit(0)
    os._exit(0)
