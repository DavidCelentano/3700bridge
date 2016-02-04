#!/usr/bin/python -u
# The -u makes output unbuffered, so it will show up immediately
import sys
import socket
import select
import json
import datetime


# pads the name with null bytes at the end
def pad(name):
    result = '\0' + name
    while len(result) < 108:
        result += '\0'
    return result


class BDPU:
    def __init__(self, rt, count):
        self.time = datetime.datetime.now()
        self.rt = rt
        self.count = count


def main(argv):

    class BDPU:
        def __init__(self, rt_port, rt, count):
            self.time = datetime.datetime.now()
            self.rt_port = rt_port
            self.rt = rt
            self.count = count

    if len(argv) < 2:
        raise ValueError('Bridge must have id and connect to LAN')
    id = argv[0]
    LAN = argv[1:]
    sockets = []
    bpdu = BDPU(id, id, 0)

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

        portno = 0
        # Reads from each fo the ready sockets
        for x in ready:
            json_data = x.recv(1500)
            data = json.loads(json_data)
            src = data['source']
            dest = data['dest']
            type = data['type']
            full_msg = data['message']
            id = full_msg['id']
            if type == 'data':
                print 'Received Message {} on port {} from {} to {}'.format(id, portno, src, dest)
            if type == 'bdpu':
                rt = full_msg['root']
                cost = full_msg['cost']
                if rt < bpdu.rt:
                    bpdu.rt = rt

            print json_data
            portno += 1


if __name__ == "__main__":
    main(sys.argv[1:])
