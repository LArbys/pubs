#!/bin/sh

# Suppress the annoying "$1: unbound variable" error when no option
# was given
if [ -z $1 ] ; then
	echo "Usage: $0 [status|start|stop|restart] "
	exit 1
fi

daemon_script=$PUB_TOP_DIR/dstream/test_daemon.py
proc=$(ps aux | grep "dstream/test_daemon.py" | grep "python" | awk '{print $2}');

case $1 in
    (status)
    if [[ -z $proc ]]; then
	echo test_daemon is not running...;
    else
	echo test_daemon already running;
    fi
    ;;
    (start)
    if [[ -z $proc ]]; then
	echo starting test_daemon;
	export PUB_LOGGER_LEVEL=kLOGGER_INFO
	#export PUB_LOGGER_LEVEL=kLOGGER_DEBUG
	export PUB_LOGGER_DRAIN=kLOGGER_FILE
	cd $PUB_TOP_DIR
	nohup $PUB_TOP_DIR/dstream/test_daemon.py > $PUB_LOGGER_FILE_LOCATION/test_daemon.sh.log &
	cd -
    else
	echo test_daemon already running;
    fi
	;;
    (stop)
    if [[ -z $proc ]]; then
	echo test_daemon is not running...;
    else
	echo stopping test_daemon;
	kill $proc;
    fi
    ;;
    (kill)
    if [[ -z $proc ]]; then
	echo test_daemon is not running...;
    else
	echo killing test_daemon;
	kill -9 $proc;
    fi
    ;;
    (restart)
    if [[ $proc ]]; then
	echo restarting test_daemon;
	kill $proc;
    else
	echo starting test_daemon;
    fi
    export PUB_LOGGER_LEVEL=kLOGGER_INFO
    export PUB_LOGGER_DRAIN=kLOGGER_FILE
    nohup $PUB_TOP_DIR/dstream/test_daemon.py > $PUB_LOGGER_FILE_LOCATION/test_daemon.sh.log &
    ;;
esac

