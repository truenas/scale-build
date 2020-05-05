#!/bin/sh

exit_err() {
	if [ -n "$2" ] ; then
		EXIT_CODE=$2
	else
		EXIT_CODE=1
	fi
	echo "ERROR: $1" >&2
	exit $EXIT_CODE
}
