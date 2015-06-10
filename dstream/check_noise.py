## @namespace dstream.CHECK_NOISE
#  @ingroup dstream
#  @brief Defines a project check_noise
#  @author david caratelli

# python include
import time
import subprocess
import glob
import os
# pub_dbi package include
from pub_dbi import DBException
# dstream class include
from dstream import DSException
from dstream import ds_project_base
from dstream import ds_status

## @class check_noise
#  @brief check noise on newly created binary file
#  @details
#  check noise values on newly created binary file
class check_noise(ds_project_base):

    # Define project name as class attribute
    _project = 'check_noise'

    ## @brief default ctor can take # runs to process for this instance
    def __init__(self,nruns=None):


        print "called constructor"
        # Call base class ctor
        super(check_noise,self).__init__()

        self._nruns = None
        self._in_dir = ''   # where to find the data! data! data! me wants data!
        self._out_dir = ''  # where should output plots/files be placed?
        self._infile_format = ''  # what is the format of the file-name?
        self._experts  = ''  
        self._lowN     = 0  # what counts as low noise? any value below this value is reported
        self._highN    = 1000  # what counts as high noise? any value above this value is reported
        self._bashScript = '' # script to be run
        self._bashInput  = '' # input file for bash script
        self._bashOutput = '' # where the bash script should move files to

    ## @brief method to retrieve the project resource information if not yet done
    def get_resource( self ):

        resource = self._api.get_resource( self._project )

        self._nruns  = int(resource['NRUNS'])
        self._in_dir = '%s' % (resource['INDIR'])
        self._out_dir = '%s' % (resource['OUTDIR'])
        self._infile_format = resource['INFILE_FORMAT']
        self._parent_project = resource['PARENT_PROJECT']
        self._experts = resource['EXPERTS']
        self._lowN = float(resource['LOWNOISE'])
        self._highN = float(resource['HIGHNOISE'])
        self._bashScript = resource['BASH_SCRIPT']
        self._bashInput  = resource['BASH_INPUT']
        self._bashOutput = resource['BASH_OUTPUT']
   
        

    ## @brief access DB and retrieves new runs
    def process_newruns(self):

        self.info('starting! here we go...')

        # Attempt to connect DB. If failure, abort
        if not self.connect():
	    self.error('Cannot connect to DB! Aborting...')
	    return

        # If resource info is not yet read-in, read in.
        if self._nruns is None:
            self.get_resource()

        # get path variables for bash script
        try:
            pubs_top = str(os.environ.get('PUB_TOP_DIR'))
            self.info('PUBS TOP DIR is: %s'%pubs_top)
            script_info = '%s/%s'%(pubs_top,self._bashScript)
            script_input = '%s/%s'%(pubs_top,self._bashInput)
            script_output = '%s/%s'%(pubs_top,self._bashOutput)
            script_log    = '%s/%s/log.txt'%(pubs_top,self._bashOutput)
            self.info('SCRIPT: %s'%script_info)
            self.info('SCRIPT INPUT: %s'%script_input)
            self.info('SCRIPT OUTPUT: %s'%script_output)
        except:
            self.error('variables for bash script not defined correctly!')

        # open a file where to store run information
        ffiles = open(script_input,'w+')


        self.info('Here, self._nruns=%d ... ' % (self._nruns))

        # Fetch runs from DB and process for # runs specified for this instance.
        ctr = self._nruns
        #for x in self.get_xtable_runs( [self._project, self._parent_project], [1, 0] ):
        runs_to_do = self.get_runs(self._project,1)
        print "Runs to do: %i"%len(runs_to_do)
        #for x in runs_to_do:
        for x in xrange(10):

            # Counter decreases by 1
            ctr -=1

            #(run, subrun) = (int(x[0]), int(x[1]))
            (run, subrun) = ( 305, ctr)

            # Report starting
            self.info('preparing noisy channel list: run=%d, subrun=%d ...' % (run,subrun))
            
            # set status code
            statusCode = 1

            # create text file containing path to binary files to be analyzed
            binfilepath = self._in_dir
            # get the file that matches the infile format and has
            # the correct run/subrun numbers
            binfilepath_holder = binfilepath+'/'+self._infile_format % (run, subrun)
            self.info('searching for run file of format %s'%binfilepath_holder)
            filelist = glob.glob( binfilepath_holder )
            
            if (len(filelist) > 1):
                self.error('More than one files match the condition for this run, subrun (%i,%i) which should be unique'%(run,subrun))
                statusCode = 666                
            elif (len(filelist) == 0):
                self.error('No files match the condition for this run, subrun (%i,%i)'%(run,subrun))
                statusCode = 666                
            
            else:

                self.info('found file %s'%filelist[0])

                try:
                    # path to file for this run/subrun
                    inputfilepath = filelist[0]
                    # execute noise_check script
                    # prepare a text file that contains the path to this file
                    ffiles.write(inputfilepath+' '+str(run)+' '+str(subrun)+'\n')

                except:
                    self.error('Could not write file path to file')
                    statuscode = 666

    
                    
                # Report finishing
                self.info('done preparing noisy channel list: run=%d, subrun=%d ...' % (run,subrun) )

                # Create a status object to be logged to DB (if necessary)
                # Let's say we set the status to be 10
                status = ds_status( project = self._project,
                                    run     = run,
                                    subrun  = subrun,
                                    seq     = 0,#int(x[2]),
                                    status  = statusCode )
            

            # Log status
            #self.log_status( status )

            # Break from loop if counter became 0
            if not ctr: break

        ffiles.close()

        # run bash script!

        try:
            subprocess.Popen(['sh',script_info,script_input,script_output,script_log])
        except:
            self.error('could not run bash script!')

# A unit test section
if __name__ == '__main__':

    test_obj = check_noise()

    test_obj.process_newruns()



