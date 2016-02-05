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

def main(argv):

    # The stored BPDU
    class BDPU:
        def __init__(self, designated_bridge, rt_port, rt, cost):
            self.time = datetime.datetime.now()
            self.id = designated_bridge
            self.rt_port = rt_port
            self.rt = rt
            self.cost = cost

    # argc check
    if len(argv) < 2:
        raise ValueError('Bridge must have id and connect to LAN')

    id = argv[0]
    lan = argv[1:]
    sockets = []
    # assume self is the host
    bpdu = BDPU(-1, id, id, 0)
    i = 0

    # creates sockets and connects to them
    for x in range(len(lan)):
        s = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        s.connect(pad(lan[x]))
        sockets.append(s)

    # ready
    print "Bridge " + id + " starting up\n"

    # Main loop
    while True:
        # Calls select with all the sockets; change the timeout value (1)
        ready_read, ready_write, ignore2 = select.select(sockets, sockets, [], 1)

        portno, works = 0, 0
        # Reads from each of the ready sockets
        for x in ready_read:
            json_data = x.recv(1500)
            data = json.loads(json_data)
            src = data['source']
            dest = data['dest']
            type = data['type']
            full_msg = data['message']
            id = full_msg['id']
            if type == 'data':
                print 'Received Message {} on port {} from {} to {}'.format(id, portno, src, dest)
            elif type == 'bpdu':
                rt = full_msg['root']
                cost = full_msg['cost']
                if rt < bpdu.rt:
                    bpdu = BDPU(x, src, rt, cost + 1)
                elif rt == bpdu.rt:
                    if cost < (bpdu.cost - 1):
                        bpdu = BDPU(x, src, rt, cost + 1)
                    elif cost == (bpdu.cost - 1) and id == bpdu.id:
                        bpdu = BDPU(x, src, rt, cost + 1)

            print json_data
            #print bpdu.rt
            #print bpdu.cost
            portno += 1
        i += 1
        if i % 10000 == 0:
            #print "Sending BPDU"
            for x in ready_write:
                x.send(json.dumps({'source':id, 'dest':'ffff', 'type': 'bpdu',
                                  'message':{'id': id, 'root': bpdu.rt, 'cost': bpdu.cost}}))


if __name__ == "__main__":
    main(sys.argv[1:])