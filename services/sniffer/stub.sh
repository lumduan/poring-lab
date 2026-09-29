#!/bin/sh
# Placeholder: proves the service wiring (profile, shared netns, capability) and does nothing else.
echo "sniffer: placeholder -- no capture implemented (see services/sniffer/README.md)."
echo "sniffer: sharing rathena's network namespace; interfaces visible here:"
cat /proc/net/dev | tail -n +3 | cut -d: -f1 | tr -s ' ' | sed 's/^/  -/'
exec sleep infinity
