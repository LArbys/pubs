## @namespace dstream_online.check_tape
#  @ingroup check_tape
#  @brief Defines a project check_tape
#  @author yuntse
#  This hasn't been completed.
#  Need to consider the cases
#  1. file in the dropbox, but not yet tape
#  2. file in both the dropbox and tape
#  3. file in neither the dropbox nor tape

# python include
import time, sys, os
# pub_dbi package include
from pub_dbi import DBException
# pub_util package include
from pub_util import pub_smtp
# dstream class include
from dstream import DSException
from dstream import ds_project_base
from dstream import ds_status
import samweb_cli
import traceback

class check_tape( ds_project_base ):

    _project = 'check_tape'

    ## @brief default ctor can take # runs to process for this instance
    def __init__( self, arg = '' ):

        # Call base class ctor
        super( check_tape, self ).__init__( arg )

        if not arg:
            self.error('No project name specified!')
            raise Exception

        self._project = arg

        self._nruns = None
        self._parent_project = ''
        self._infile_format = ''
        self._experts = ''
        self._data = ''

    ## @brief method to retrieve the project resource information if not yet done
    def get_resource( self ):

        resource = self._api.get_resource( self._project )

        self._nruns = int(resource['NRUNS'])
        self._parent_project = resource['PARENT_PROJECT']
        self._infile_format = resource['INFILE_FORMAT']
        self._experts = resource['EXPERTS']


    ## @brief check file location
    def check_location( self ):

        # Attempt to connect DB. If failure, abort
        if not self.connect():
            self.error('Cannot connect to DB! Aborting...')
            return

        # If resource info is not yet read-in, read in.
        if self._nruns is None:
            self.get_resource()

        # Fetch runs from DB and process for # runs specified for this instance.
        ctr = self._nruns
        for x in self.get_xtable_runs( [self._project, self._parent_project], [1, 0] ):

            # Counter decreases by 1
            ctr -= 1

            (run, subrun) = (int(x[0]), int(x[1]))

            # Report starting
            self.info('Checking tape: run=%d, subrun=%d ...' % (run,subrun))

            statusCode = 1

            in_file = self._infile_format % ( run, subrun )
            samweb = samweb_cli.SAMWebClient(experiment="uboone")

            loc = {}

            try:
                loc = samweb.locateFile(filenameorid=in_file)
                if loc:
                    if loc[0]['location_type'] == 'tape':
                        statusCode = 2

            except samweb_cli.exceptions.FileNotFound:
                subject = 'Failed to locate file %s at SAM' % in_file
                text = 'File %s is not found at SAM!' % in_file

                pub_smtp( os.environ['PUB_SMTP_ACCT'], os.environ['PUB_SMTP_SRVR'], os.environ['PUB_SMTP_PASS'], self._experts, subject, text )

                statusCode = 100


            # Create a status object to be logged to DB (if necessary)
            status = ds_status( project = self._project,
                                run     = run,
                                subrun  = subrun,
                                seq     = 0,
                                status  = statusCode,
                                data    = self._data )

            # Log status
            self.log_status( status )

            # Break from loop if counter became 0
            if not ctr: break
 

    ## @brief obtain checksum
    def find_checksum( self ):

        # Attempt to connect DB. If failure, abort
        if not self.connect():
            self.error('Cannot connect to DB! Aborting...')
            return

        # If resource info is not yet read-in, read in.
        if self._nruns is None:
            self.get_resource()

        # Fetch runs from DB and process for # runs specified for this instance.
        ctr = self._nruns
        for x in self.get_xtable_runs( [self._project, self._parent_project], [2, 0] ):

            # Counter decreases by 1
            ctr -= 1

            (run, subrun) = (int(x[0]), int(x[1]))

            # Report starting
            self.info('Checking tape: run=%d, subrun=%d ...' % (run,subrun))

            statusCode = 2

            in_file = self._infile_format % ( run, subrun )
            samweb = samweb_cli.SAMWebClient(experiment="uboone")

            meta = {}
            try:
                meta = samweb.getMetadata(filenameorid=in_file)
                checksum_info = meta['checksum'][0].split(':')
                if checksum_info[0] == 'enstore':
                    self._data = checksum_info[1]
                    statusCode = 0

                else:
                    statusCode = 1

            except samweb_cli.exceptions.FileNotFound:
                subject = 'Failed to locate file %s at SAM' % in_file
                text = 'File %s is not found at SAM!' % in_file

                pub_smtp( os.environ['PUB_SMTP_ACCT'], os.environ['PUB_SMTP_SRVR'], os.environ['PUB_SMTP_PASS'], self._experts, subject, text )

                statusCode = 100

            # Create a status object to be logged to DB (if necessary)
            status = ds_status( project = self._project,
                                run     = run,
                                subrun  = subrun,
                                seq     = 0,
                                status  = statusCode,
                                data    = self._data )

            # Log status
            self.log_status( status )

            # Break from loop if counter became 0
            if not ctr: break


if __name__ == '__main__':

    proj_name = sys.argv[1]

    obj = check_tape( proj_name )

    obj.check_location()

    obj.find_checksum()