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


# form the bpdu to be sent
def form_bpdu(id, rt, cost):
    return json.dumps({'source': id, 'dest': 'ffff', 'type': 'bpdu',
                       'message':{'root': rt, 'cost': cost}})


# creates bridge
def main(argv):

    # A BPDU
    class BPDU:
        def __init__(self, designated_bridge, rt_port, rt, cost):
            self.id = designated_bridge
            self.rt_port = rt_port
            self.rt = rt
            self.cost = cost

    # argc check
    if len(argv) < 2:
        raise ValueError('Bridge must have id and connect to LAN')

    my_id = argv[0]
    # initial lan addresses
    lan_args = argv[1:]
    # list of ports
    ports = []
    # map of file descriptor to ports
    file_no_to_port = {}
    # map of ports to lan number
    port_to_lan = {}
    # map of lans to ports
    lan_to_port = {}
    # map of sources to times
    src_timeout = {}
    # port activation status
    ports_on = {}
    # map of sources to ports
    src_to_port = {}
    # temporary replacement for forwarding table and loops
    seen_before = []
    # stored BPDU
    # assume self is the root
    bpdu = BPDU(my_id, 0, my_id, 0)
    # time before sending another bpdu
    time_out = datetime.datetime.now()

    # creates ports and connects to them
    for x in range(len(lan_args)):
        # if connected to same LAN multiple times
        if lan_args[x] in lan_to_port:
            continue
        s = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        s.connect(pad(lan_args[x]))
        ports.append(s)
        port_to_lan[s] = lan_args[x]
        file_no_to_port[s.fileno] = s
        lan_to_port[lan_args[x]] = s
        ports_on[s] = True

    # ready
    print 'Bridge ' + my_id + ' starting up' + ' The root is {} and the cost is {}'.format(bpdu.rt, bpdu.cost)
    ready_read, ready_write, ignore2 = select.select(ports, ports, [], 1)
    for r in ready_write:
        r.send(form_bpdu(my_id, bpdu.rt, bpdu.cost))

    # Main loop
    while True:
        # Calls select with all the ports; change the timeout value (1)
        ready_read, ready_write, ignore2 = select.select(ports, ports, [], 1)

        # Reads from each of the ready ports
        for x in ready_read:
            json_data = x.recv(1500)
            data = json.loads(json_data)
            src = data['source']
            dest = data['dest']
            type = data['type']
            full_msg = data['message']
            if type == 'data' and ports_on[x]:
                msg_id = full_msg['id']
                if dest in src_to_port and (datetime.datetime.now() - src_timeout[dest]).total_seconds() < 4:
                    if ports_on[src_to_port[dest]]:
                        if src_to_port[dest] in ready_write:
                            print 'Forwarding message {} to port {}'.format(msg_id, src_to_port[dest])
                            src_to_port[dest].send(json_data)
                            break
                else:
                    src_to_port[src] = x
                    src_timeout[src] = datetime.datetime.now()
                    print 'Broadcasting message {} to all ports'.format(msg_id)
                    for s in ready_write:
                        if ports_on[s] and not(s is x):
                            s.send(json_data)
            # received BPDU
            elif type == 'bpdu':
                rt = full_msg['root']
                cost = full_msg['cost']
                # if more correct BPDU
                if rt < bpdu.rt \
                        or (rt == bpdu.rt and (cost < (bpdu.cost - 1))) \
                        or (rt == bpdu.rt and (cost == bpdu.cost - 1) and src < bpdu.id):
                    # change own BPDU state
                    bpdu = BPDU(src, x.fileno(), rt, cost + 1)
                    # send out update to all BPDU neighbors
                    for x in ready_write:
                       x.send(form_bpdu(my_id, bpdu.rt, bpdu.cost))
                    # reset timeout timer
                    time_out = datetime.datetime.now()
                # figure out what I meant with this
                #if cost == bpdu.cost and src < bpdu.id:
                    #ports_on[x] = False
                    #print "enabled false!!!!!!!!!!!!!!!!!!"
                #print 'The root is {} and the cost is {} and my designated bridge is {}'.format(bpdu.rt, bpdu.cost, bpdu.id)

            #print json_data
            #print bpdu.rt
            #print bpdu.cost

        # BPDU send timer (if BPDU times out)
        time_diff = datetime.datetime.now() - time_out
        total_milliseconds = time_diff.total_seconds() * 1000
        if total_milliseconds > 750:
            time_out = datetime.datetime.now()
            for x in ready_write:
                x.send(form_bpdu(my_id, bpdu.rt, bpdu.cost))


if __name__ == "__main__":
    main(sys.argv[1:])