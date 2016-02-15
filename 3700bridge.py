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
        def __init__(self, des_bridge, rt_port, rt, cost):
            self.des_bridge = des_bridge
            self.rt_port = rt_port
            self.rt = rt
            self.cost = cost

    # argc check
    if len(argv) < 2:
        raise ValueError('Bridge must have id and connect to LAN')

    # bridge id
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

    # stored BPDU: assume self is the root
    bpdu = BPDU(my_id, 0, my_id, 0)
    # timer for sending another bpdu
    time_out = datetime.datetime.now()

    # creates all ports and connects to them
    for x in range(len(lan_args)):
        # if connected to same LAN multiple times, disable extras
        if lan_args[x] in lan_to_port:
            continue
        # connect to port
        s = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        s.connect(pad(lan_args[x]))
        # record socket obj
        ports.append(s)
        # associate socket obj with LAN
        port_to_lan[s] = lan_args[x]
        # for opposite of s.fileno
        file_no_to_port[s.fileno] = s
        # associate LAN with socket obj
        lan_to_port[lan_args[x]] = s
        # seen before
        #seen_before = []
        # by default, keep port open
        ports_on[s] = True

    # ready print
    print 'Bridge ' + my_id + ' starting up' + ' The root is {} and the cost is {}'.format(bpdu.rt, bpdu.cost)
    # initialize ports to read and write to
    ready_read, ready_write, ignore2 = select.select(ports, ports, [], 1)
    # initial BPDU send
    for r in ready_write:
        r.send(form_bpdu(my_id, bpdu.rt, bpdu.cost))

    # Main loop
    while True:
        # Calls select with all the ports; change the timeout value (1)
        # Reinitialize list of ready ports
        ready_read, ready_write, ignore2 = select.select(ports, ports, [], 1)

        # BPDU send timer (if BPDU times out)
        time_diff = datetime.datetime.now() - time_out
        total_milliseconds = time_diff.total_seconds() * 1000
        if total_milliseconds > 750:
            time_out = datetime.datetime.now()
            for x in ready_write:
                x.send(form_bpdu(my_id, bpdu.rt, bpdu.cost))

        # Reads from each of the ready ports
        for x in ready_read:
            # JSON decoding
            json_data = x.recv(1500)
            data = json.loads(json_data)
            # sent from
            src = data['source']
            # sending to
            dest = data['dest']
            # msg type
            type = data['type']
            # contents of message
            full_msg = data['message']
            # if type is host to host data
            if type == 'data' and ports_on[x]:
                # random id for message
                msg_id = full_msg['id']
                #if msg_id in seen_before:
                #    continue
                #seen_before.append(msg_id)
                src_to_port[src] = x
                src_timeout[src] = datetime.datetime.now()
                # if destination in forwarding table, and table is up-to-date
                if dest in src_to_port and (datetime.datetime.now() - src_timeout[dest]).total_seconds() <= 5 \
                        and ports_on[src_to_port[dest]] and src_to_port[dest] in ready_write:
                    print 'Forwarding message {} to port {}'.format(msg_id, src_to_port[dest])
                    src_to_port[dest].send(json_data)
                # destination is not currently in forwarding table
                else:
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
                        or (rt == bpdu.rt and (cost == bpdu.cost - 1) and src < bpdu.des_bridge):
                    # change own BPDU state
                    bpdu = BPDU(src, x.fileno(), rt, cost + 1)
                    # send out update to all BPDU neighbors
                    for x in ready_write:
                       x.send(form_bpdu(my_id, bpdu.rt, bpdu.cost))
                    # reset timeout timer
                    time_out = datetime.datetime.now()
                # determines the designated bridge on the LAN's
                # if equal distance to root and
                #elif cost == bpdu.cost and src < my_id:
                    #ports_on[x] = False
                    #print "enabled false!!!!!!!!!!!!!!!!!!"
                #print 'The root is {} and the cost is {} and my designated bridge is {}'.format(bpdu.rt, bpdu.cost, bpdu.id)

            #print json_data
            #print bpdu.rt
            #print bpdu.cost




if __name__ == "__main__":
    main(sys.argv[1:])