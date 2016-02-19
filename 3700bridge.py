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
def form_bpdu(cur_id, rt, cost):
    return json.dumps({'source': cur_id, 'dest': 'ffff', 'type': 'bpdu',
                       'message': {'root': rt, 'cost': cost}})


# creates bridge
def main(argv):

    # A BPDU
    class BPDU:
        def __init__(self, bridge_id, rt, cost, rt_port = 0):
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
    if my_id == '9a3a':
        print_toggle = True
    # id of bridge on root port
    root_port_bridge = my_id
    # initial lan addresses
    lan_args = argv[1:]
    # list of ports
    ports = []
    # map of ports to lan number
    port_to_lan = {}
    # map of ports to their dedicated bridges
    port_to_bridge = {}
    # map of lans to ports
    lan_to_port = {}
    # map of sources to times
    src_timeout = {}
    # map of sources to ports
    src_to_port = {}
    # port activation status
    ports_on = {}
    # bridge timeouts
    bridge_timeout = {}
    # stored BPDU: assume self is the root
    bpdu = BPDU(my_id, my_id, 0)
    # timer for sending another bpdu
    time_out = datetime.datetime.now()

    # creates all ports and connects to them
    for lan_index in (x for x in range(len(lan_args)) if not (lan_args[x][-1:] in lan_to_port)):
        lan = lan_args[lan_index]
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
        port_to_bridge[s] = bpdu

    # ready print
    print 'Bridge {} starting up'.format(my_id)
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

        # timeout on all other BPDU's
        dropped_bridges = []
        for key in bridge_timeout.keys():
            time_stamp = datetime.datetime.now()
            time_diff = (time_stamp - bridge_timeout[key]).total_seconds() * 1000
            if time_diff > 750:
                del bridge_timeout[key]  # the name of the dropped bridge
                dropped_bridges.append(key)

        # reset if necessary (assumes a bridge drop)
        if len(dropped_bridges) > 0:
            # reset state for reconvergence
            bpdu = BPDU(my_id, my_id, 0)
            root_port_bridge = my_id
            # reset forwarding table
            src_to_port = {}
            # reset forwarding table timeouts
            src_timeout = {}
            # check for presence in dictionary
            for key in port_to_bridge.keys():
                # remove as designated bridge
                ports_on[key] = True
                if port_to_bridge[key] in dropped_bridges:
                    port_to_bridge[key] = bpdu
            # reset bpdu timeout
            time_out = datetime.datetime.now()
            # send out new bpdu's for reconvergence
            for send_bpdu_port in ports:
                send_bpdu_port.send(form_bpdu(my_id, bpdu.rt, bpdu.cost))


        # BPDU send timer
        time_diff = datetime.datetime.now() - time_out
        total_milliseconds = time_diff.total_seconds() * 1000
        if total_milliseconds > 500:
            time_out = datetime.datetime.now()
            for send_port in ports:
                send_port.send(form_bpdu(my_id, bpdu.rt, bpdu.cost))

        # Reads from each of the ready ports
        for read_port in ready_read:
            # JSON decoding
            json_data = read_port.recv(1500)
            data = json.loads(json_data)
            # sent from
            src = data['source']
            # sending to
            dest = data['dest']
            # msg type
            msg_type = data['type']
            # contents of message
            full_msg = data['message']
            # file number
            r_port_no = read_port.fileno()
            # if type is host data
            if msg_type == 'data' and ports_on[read_port]:
                # random id for message
                msg_id = full_msg['id']
                # record in forwarding table
                src_to_port[src] = read_port
                # reset timer on host
                now = datetime.datetime.now()
                src_timeout[src] = now
                if print_toggle:
                    print 'Received message {} on port {} from {} to {}'.format(msg_id, r_port_no, src, dest)
                # if destination in forwarding table, and table is up-to-date, and port is open
                if dest in src_to_port and (now - src_timeout[dest]).total_seconds() <= 5 and ports_on[src_to_port[dest]]:
                    dest_port = src_to_port[dest]
                    if dest_port != read_port:
                        if print_toggle:
                            src_no = r_port_no
                            dest_no = dest_port.fileno()
                            print 'Forwarding message {} from port {} to port {}'.format(msg_id, src_no, dest_no)
                        dest_port.send(json_data)
                    else:
                        if print_toggle:
                            print 'Not forwarding message {} from port {}'.format(msg_id, r_port_no)

                # destination is not currently in forwarding table
                else:
                    k = 0
                    for port in (x for x in ports if (ports_on[x] and x != read_port)):
                        k += 1
                        port.send(json_data)
                    if k == 0:
                        if print_toggle:
                            print 'Not forwarding message {} from port {}'.format(msg_id, r_port_no)
                    else:
                        if print_toggle:
                            print 'Broadcasting message {} to all ports except {}'.format(msg_id, r_port_no)

            # received BPDU
            elif msg_type == 'bpdu':
                rt = full_msg['root']
                cost = full_msg['cost']
                bridge_timeout[src] = datetime.datetime.now()
                des_bridge = port_to_bridge[read_port]
                port_lan = port_to_lan[read_port]
                if rt < bpdu.rt \
                        or (rt == bpdu.rt and (cost < (bpdu.cost - 1))) \
                        or (rt == bpdu.rt and (cost == bpdu.cost - 1) and src < root_port_bridge):
                    # change own BPDU state
                    bpdu = BPDU(my_id, rt, cost + 1, read_port.fileno())
                    root_port_bridge = src
                    if print_toggle:
                        print 'New root: {}/{}'.format(my_id, bpdu.rt)
                        print 'Root port: {}/{}'.format(my_id, bpdu.rt_port)
                    src_to_port = {}
                    src_timeout = {}
                    # send out update to all BPDU neighbors
                    for every_port in ports:
                        every_port.send(form_bpdu(my_id, bpdu.rt, bpdu.cost))
                    # reset timeout timer
                    time_out = datetime.datetime.now()
                    '''if print_toggle:
                        print '{} is not the designated bridge for LAN {}'.format(my_id, port_lan)'''
                # for upcoming if
                less_rt = rt < des_bridge.rt
                equal_rt = rt == des_bridge.rt
                less_cost = cost < des_bridge.cost
                equal_cost = cost == des_bridge.cost
                less_id = src < des_bridge.bridge_id
                # This bridge should be the designated bridge for this port
                if less_rt or (equal_rt and less_cost) or (equal_rt and equal_cost and less_id):
                    # make this bridge the designated bridge
                    port_to_bridge[read_port] = BPDU(src, rt, cost)
                    # if it should be closed
                    if read_port.fileno() != bpdu.rt_port:
                        if ports_on[read_port]:
                            ports_on[read_port] = False
                            if print_toggle:
                                print 'Disabled port: {} to LAN {}'.format(r_port_no, port_lan)
                    elif not (ports_on[read_port]):
                        ports_on = True
                        if print_toggle:
                                print 'Enabled port: {} to LAN {}'.format(r_port_no, port_lan)
                    if print_toggle:
                        print '{} is the designated bridge for ' \
                              'LAN {} {}: {} {}: {}'.format(src, port_lan, src, cost, des_bridge.bridge_id, des_bridge.cost)
                # check if I am the designated bridge for this port
                elif bpdu.rt < des_bridge.rt or (bpdu.rt == des_bridge.rt and bpdu.cost < des_bridge.cost) \
                     or (bpdu.rt == des_bridge.rt and bpdu.cost == des_bridge.cost and my_id < des_bridge.bridge_id):
                    port_to_bridge[read_port] = bpdu
                    ports_on[read_port] = True
                    if print_toggle:
                        print '{} is the designated bridge for ' \
                              'LAN {} {}: {} {}: {}'.format(my_id, port_lan, my_id, bpdu.cost, des_bridge.bridge_id, des_bridge.cost)

                if print_toggle:
                    print 'the root is {} and ' \
                          'my cost is {} and my LANs: {} are {}'.format(bpdu.rt, bpdu.cost, port_to_lan.values()[1:],
                                                                        ports_on.values())
            elif msg_type != 'data':
                raise RuntimeWarning('Malformed message: being discarded')


if __name__ == "__main__":
    main(sys.argv[1:])