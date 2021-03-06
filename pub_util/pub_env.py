import os,sys,socket

#
# Age of Eric Church
#
kAGE_OF_CHURCH=50

#
# Server name
#
kSERVER_NAME=socket.gethostname()

#
# Logger message level definition & default
#
(kLOGGER_DEBUG,
 kLOGGER_INFO,
 kLOGGER_WARNING,
 kLOGGER_ERROR,
 kLOGGER_EXCEPTION) = (10,20,30,40,50)

kLOGGER_LEVEL = kLOGGER_INFO
if 'PUB_LOGGER_LEVEL' in os.environ:
    exec('kLOGGER_LEVEL=int(%s)' % os.environ['PUB_LOGGER_LEVEL'])
#
# Logger drain definition & default
#

(kLOGGER_COUT,kLOGGER_FILE) = xrange(2)

kLOGGER_DRAIN = kLOGGER_COUT

if 'PUB_LOGGER_DRAIN' in os.environ:

    exec('kLOGGER_DRAIN=int(%s)' % os.environ['PUB_LOGGER_DRAIN'])
    
    if not kLOGGER_DRAIN in [kLOGGER_COUT,kLOGGER_FILE]:
        sys.stderr.write('PUB_LOGGER_DEST env. value is invalid (%s)!' % os.environ['PUB_LOGGER_DRAIN'])
        sys.exit(1)

#
# Logger file drain path default
#
kLOGGER_FILE_LOCATION = os.environ['PWD']
if 'PUB_LOGGER_FILE_LOCATION' in os.environ:
    exec('kLOGGER_FILE_LOCATION=\'%s\'' % os.environ['PUB_LOGGER_FILE_LOCATION'])
    if not os.path.isdir(kLOGGER_FILE_LOCATION):
        sys.stderr.write('PUB_LOGGER_FILE_LOCATION env. value is non-existing directory (%s)!' % os.environ['PUB_LOGGER_FILE_LOCATION'])
        sys.exit(1)

#
# Emailer config
#
kSMTP_ACCT = ''
kSMTP_SRVR = ''
kSMTP_PASS = ''
if 'PUB_SMTP_ACCT' in os.environ:
    exec('kSMTP_ACCT=\'%s\'' % os.environ['PUB_SMTP_ACCT'])
if 'PUB_SMTP_SRVR' in os.environ:
    exec('kSMTP_SRVR=\'%s\'' % os.environ['PUB_SMTP_SRVR'])
if 'PUB_SMTP_PASS' in os.environ:
    exec('kSMTP_PASS=\'%s\'' % os.environ['PUB_SMTP_PASS'])

#
# Daemon server functions
#
kDAEMON_LOG_MODULE = ''
if 'PUB_DAEMON_LOG_MODULE' in os.environ:
    kDAEMON_LOG_MODULE = os.environ['PUB_DAEMON_LOG_MODULE']
kDAEMON_HANDLER_MODULE = ''
if 'PUB_DAEMON_HANDLER_MODULE' in os.environ:
    kDAEMON_HANDLER_MODULE = os.environ['PUB_DAEMON_HANDLER_MODULE']
    
