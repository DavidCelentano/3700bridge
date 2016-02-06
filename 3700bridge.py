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

# creates bridge
def main(argv):

    # A BPDU
    class BDPU:
        def __init__(self, designated_bridge, rt_port, rt, cost):
            self.id = designated_bridge
            self.rt_port = rt_port
            self.rt = rt
            self.cost = cost

    # argc check
    if len(argv) < 2:
        raise ValueError('Bridge must have id and connect to LAN')

    id = argv[0]
    # initial lan addresses
    lan = argv[1:]
    # list of ports
    ports = {}
    ports_on = {}
    # stored BPDU
    # assume self is the root
    bpdu = BDPU(-1, id, id, 0)
    time_out = datetime.datetime.now()

    # creates ports and connects to them
    for x in range(len(lan)):
        s = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        s.connect(pad(lan[x]))
        ports[s] = lan[x]
        ports_on[s] = True


    # ready
    print "Bridge " + id + " starting up\n"

    # Main loop
    while True:
        # Calls select with all the ports; change the timeout value (1)
        ready_read, ready_write, ignore2 = select.select(ports.keys(), ports.keys(), [], 1)

        # Reads from each of the ready ports
        for x in ready_read:
            json_data = x.recv(1500)
            data = json.loads(json_data)
            src = data['source']
            dest = data['dest']
            type = data['type']
            full_msg = data['message']
            id = full_msg['id']
            if type == 'data':
                print 'Received Message {} on port {} from {} to {}'.format(id, x.fileno(), src, dest)
            elif type == 'bpdu':
                print 'Received BPDU {} on port {} from {} to {}'.format(id, x.fileno(), src, dest)
                rt = full_msg['root']
                cost = full_msg['cost']
                if rt < bpdu.rt \
                        or (rt == bpdu.rt and (cost < (bpdu.cost - 1))) \
                        or (rt == bpdu.rt and (cost == bpdu.cost - 1) and id < bpdu.id):
                    bpdu = BDPU(x, src, rt, cost + 1)

            #print json_data
            #print bpdu.rt
            #print bpdu.cost

        time_diff = datetime.datetime.now() - time_out
        total_milliseconds = time_diff.total_seconds() * 1000
        if total_milliseconds > 750:
            time_out = datetime.datetime.now()
            for x in ready_write:
                x.send(json.dumps({'source':id, 'dest':'ffff', 'type': 'bpdu',
                                   'message':{'id': id, 'root': bpdu.rt, 'cost': bpdu.cost}}))


if __name__ == "__main__":
    main(sys.argv[1:])