#!/usr/bin/python -u
# The -u makes output unbuffered, so it will show up immediately
import sys
import socket
import select
import json


# pads the name with null bytes at the end
def pad(name):
    result = '\0' + name
    while len(result) < 108:
        result += '\0'
    return result


def main(argv):
    if len(argv) < 2:
        raise ValueError('Bridge must have id and connect to LAN')
    id = argv[0]
    LAN = argv[1:]
    sockets = []

    # creates sockets and connects to them
    for x in range(len(LAN)):
        s = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        s.connect(pad(LAN[x]))
        sockets.append(s)

    print "Bridge " + id + " starting up\n"

    # Main loop
    while True:
        # Calls select with all the sockets; change the timeout value (1)
        ready, ignore, ignore2 = select.select(sockets, [], [], 1)

        # Reads from each fo the ready sockets
        for x in ready:
            json_data = x.recv(1500)
            data = json.loads(json_data)
            src = data['source']
            dest = data['dest']
            type = data['type']
            full_msg = data['message']
            id = full_msg['id']
            if type == 'bdpu':
                rt = full_msg['root']
                cost = full_msg['cost']
            print json_data

if __name__ == "__main__":
    main(sys.argv[1:])
