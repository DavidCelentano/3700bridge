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
        def __init__(self, bridge_id, rt_port, rt, cost):
            self.bridge_id = bridge_id
            self.rt_port = rt_port
            self.rt = rt
            self.cost = cost

    # argc check
    if len(argv) < 2:
        raise ValueError('Bridge must have id and connect to LAN')

    # bridge id
    my_id = argv[0]
    # print or not
    print_toggle = True
    # initial lan addresses
    lan_args = argv[1:]
    # list of ports
    ports = []
    # seen before
    seen_before = []
    # map of ports to lan number
    port_to_lan = {}
    # map of lans to ports
    lan_to_port = {}
    # map of sources to times
    src_timeout = {}
    # map of sources to ports
    src_to_port = {}
    # port activation status
    ports_on = {}

    # stored BPDU: assume self is the root
    bpdu = BPDU(my_id, 0, my_id, 0)
    # timer for sending another bpdu
    time_out = datetime.datetime.now()

    # creates all ports and connects to them
    for x in range(len(lan_args)):
        lan = lan_args[x]
        # if connected to same LAN multiple times, disable extras
        if lan[-1:] in lan_to_port:
            continue
        # connect to port
        s = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        s.connect(pad(lan))
        # record socket obj
        ports.append(s)
        # associate socket obj with LAN
        port_to_lan[s] = lan[-1:]
        # associate LAN with socket obj
        lan_to_port[lan[-1:]] = s
        # by default, keep port open
        ports_on[s] = True

    # ready print
    print 'Bridge ' + my_id + ' starting up' + ' The root is {} and the cost is {}'.format(bpdu.rt, bpdu.cost)
    # initial BPDU send
    for r in ports:
        r.send(form_bpdu(my_id, bpdu.rt, bpdu.cost))

    # for initial BPDU configuration
    port_to_lan[0] = 'this is a mistake'
    lan_to_port['this is a mistake'] = 0

    # Main loop
    while True:
        # Calls select with all the ports; change the timeout value (1)
        # Reinitialize list of ready ports
        ready_read, ignore, ignore2 = select.select(ports, ports, [], 0.1)

        # BPDU send timer (if BPDU times out)
        time_diff = datetime.datetime.now() - time_out
        total_milliseconds = time_diff.total_seconds() * 1000
        if total_milliseconds > 750:
            time_out = datetime.datetime.now()
            for x in ports:
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
            # if type is host data
            if type == 'data' and ports_on[x]:
                # random id for message
                msg_id = full_msg['id']
                if msg_id in seen_before:
                    continue
                seen_before.append(msg_id)
                src_to_port[src] = x
                src_timeout[src] = datetime.datetime.now()
                # if destination in forwarding table, and table is up-to-date
                if dest in src_to_port and (datetime.datetime.now() - src_timeout[dest]).total_seconds() <= 5 \
                        and ports_on[src_to_port[dest]]:
                    if print_toggle:
                        print 'Forwarding message {} from port {} to port {}'.format(msg_id, src_to_port[src].fileno(),
                                                                                 src_to_port[dest].fileno())
                    src_to_port[dest].send(json_data)
                # destination is not currently in forwarding table
                else:
                    k = 0
                    for port in ports:
                        if ports_on[port] and port != x:
                            k += 1
                            port.send(json_data)
                    if k == 0:
                        if print_toggle:
                            print 'Not forwarding message {} from port {}'.format(msg_id, src_to_port[src].fileno())
                    else:
                        if print_toggle:
                            print 'Broadcasting message {} to all ports except {}'.format(msg_id, src_to_port[src].fileno())
            # received BPDU
            elif type == 'bpdu':
                rt = full_msg['root']
                cost = full_msg['cost']
                if rt < bpdu.rt \
                        or (rt == bpdu.rt and (cost < (bpdu.cost - 1))) \
                        or (rt == bpdu.rt and (cost == bpdu.cost - 1) and src < bpdu.bridge_id):
                    # change own BPDU state
                    bpdu = BPDU(src, x, rt, cost + 1)
                    src_to_port = {}
                    src_timeout = {}
                    # send out update to all BPDU neighbors
                    for x in ports:
                       x.send(form_bpdu(my_id, bpdu.rt, bpdu.cost))
                    # reset timeout timer
                    time_out = datetime.datetime.now()
                # port closing





if __name__ == "__main__":
    main(sys.argv[1:])