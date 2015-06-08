#!/usr/bin/env bash

# If PUB_TOP_DIR not set, try to guess
if [[ -z $PUB_TOP_DIR ]]; then
    # Find the location of this script:
    me="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
    # Find the directory one above.
    export PUB_TOP_DIR="$( cd "$( dirname "$me" )" && pwd )"
fi

#
# PSQL configuration
#
export PGOPTIONS="-c client_min_messages=WARNING";

#
# Python configuration
#
# Set PATH
export PATH=$PUB_TOP_DIR/bin:$PATH
# Set PYTHONPATH
export PYTHONPATH=$PUB_TOP_DIR:$PYTHONPATH
# BIN executable directory
export PUB_BIN_DIR=$PUB_TOP_DIR
export PATH=$PUB_BIN_DIR:$PATH

#
# Project configuration
# 
# Default logger level
export PUB_LOGGER_LEVEL=kLOGGER_DEBUG
# Default message drain
export PUB_LOGGER_DRAIN=kLOGGER_COUT
#export PUB_LOGGER_DRAIN=kLOGGER_FILE
export PUB_LOGGER_FILE_LOCATION=$PUB_TOP_DIR/log

#
# Daemon configuration
#
export PUB_DAEMON_LOG_MODULE=""
export PUB_DAEMON_HANDLER_MODULE=""

#
# Server-specific configuration
#
case `uname -n` in
    (*uboonegpvm*)
	echo Setting up for uboonegpvm...
	if [ -z $HOME/.sqlaccess/prod_access.sh ]; then
	    echo 'Configuration @ gpvm requires \$HOME/.sqlaccess/prod_access.sh!'
	    echo 'Exiting...'
	    echo 
	    return;
	fi
	source $HOME/.sqlaccess/prod_access.sh
	source /grid/fermiapp/products/uboone/setup_uboone.sh
	setup psycopg2 v2_5_4
	setup uboonecode v04_08_01 -q e7:prof
	setup larbatch v01_09_00 
	export PUB_LOGGER_FILE_LOCATION=$PUB_TOP_DIR/log/`uname -n`
	mkdir -p $PUB_LOGGER_FILE_LOCATION;
	export PUB_DAEMON_LOG_MODULE=dstream_prod.gpvm_logger
	;;
    (*ubdaq-prod*)
	echo Setting up for ubdaq-prod machines...
        source /uboonenew/setup_online.sh
	source $PUB_TOP_DIR/config/ubdaq_conf.sh
	setup git
	setup psycopg2 v2_5_4
        setup postgresql v9_3_6 -q p278
        export PYTHONPATH=${POSTGRESQL_LIBRARIES}/python2.7/site-packages:${PYTHONPATH}
	export PUB_LOGGER_FILE_LOCATION=$PUB_TOP_DIR/log/`uname -n`
	mkdir -p $PUB_LOGGER_FILE_LOCATION;

	case `uname -n` in
	    (ubdaq-prod-smc)
		export PUB_DAEMON_LOG_MODULE=dstream_online.ubdaq_logger_smc
		export PUB_DAEMON_HANDLER_MODULE=dstream_online.ubdaq_handler_smc
		;;
	    (ubdaq-prod-evb)
		export PUB_DAEMON_LOG_MODULE=dstream_online.evb_logger
		export PUB_DAEMON_HANDLER_MODULE=dstream_online.evb_handler
		;;
	    (ubdaq-prod-near1)
	        #
                # This is not guaranteed to work (Kazu June-02-2015)
                #

		export PUB_DAEMON_LOG_MODULE=dstream_online.near1_logger
		export PUB_DAEMON_HANDLER_MODULE=dstream_online.near1_handler

		export UBOONEDAQ_HOME_DIR=${HOME}/development
		cd $UBOONEDAQ_HOME_DIR/build
	        # Install will go to version specified in ../uboonedaq/projects/ups/product_deps
		export CET_PRIVATE_UPS_DIR=${HOME}/install/privateups
		export PRIVATE_UPS_DIR=${HOME}/development/install
		source ../uboonedaq/projects/ups/setup_for_development -d;
		
		source /uboone/larsoft/setup
		source $PUB_TOP_DIR/config/ubdaq_conf.sh
		export PRODUCTS=/home/echurch/larclient/prof.slf6.v04_05_00/localProducts_larsoft_v04_05_00_e7_prof:${PRODUCTS}
 		setup uboonecode v04_05_00 -q e7:prof
		source /home/$USER/development/uboonedaq/projects/cpp2py/config/setup_cpp2py.sh
		setup sam_web_client
		setup ifdhc
		unsetup uboonedaq_datatypes
		setup uboonedaq_datatypes v5_00_01 -qe7:prof

		;;
	esac
	;;
    (*)
	export PUB_DAEMON_LOG_MODULE=ds_server_dummy.dummy_logger
	export PUB_DAEMON_HANDLER_MODULE=ds_server_dummy.dummy_handler
	echo No special setup done for the server `uname -n`
	;;
esac



