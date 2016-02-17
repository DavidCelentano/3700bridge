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
    if my_id == 'ff1a':
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
    # bridge timeouts
    bridge_timeout = {}
    # stored BPDU: assume self is the root
    bpdu = BPDU(my_id, 0, my_id, 0)
    # timer for sending another bpdu
    time_out = datetime.datetime.now()
    # designated bridge flags
    des_bridge_flags = {}

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
        des_bridge_flags[s] = True

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

        # timeout on all other BPDU's
        reset_count = 0
        for key in bridge_timeout.keys():
            time_stamp = datetime.datetime.now()
            time_diff = (time_stamp - bridge_timeout[key]).total_seconds() * 1000
            if time_diff > 750:
                del bridge_timeout[key]
                reset_count += 1

        # reset if necessary
        if reset_count > 0:
            bpdu = BPDU(my_id, 0, my_id, 0)
            src_to_port = {}
            src_timeout = {}
            for key in des_bridge_flags.keys():
                des_bridge_flags[key] = True
                ports_on[key] = True
            time_out = datetime.datetime.now()
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
            type = data['type']
            # contents of message
            full_msg = data['message']

            # if type is host data
            if type == 'data' and ports_on[read_port]:
                # random id for message
                msg_id = full_msg['id']
                # the cheap way out
                '''if msg_id in seen_before:
                    continue
                seen_before.append(msg_id)'''
                # record in forwarding table
                src_to_port[src] = read_port
                # reset timer on host
                now = datetime.datetime.now()
                src_timeout[src] = now
                # if destination in forwarding table, and table is up-to-date, and port is open
                if dest in src_to_port and (now - src_timeout[dest]).total_seconds() <= 5 and ports_on[src_to_port[dest]]:
                    dest_port = src_to_port[dest]
                    if print_toggle:
                        src_no = src_to_port[src].fileno()
                        dest_no = dest_port.fileno()
                        print 'Forwarding message {} from port {} to port {}'.format(msg_id, src_no, dest_no)
                    dest_port.send(json_data)
                # destination is not currently in forwarding table
                else:
                    k = 0
                    for port in (x for x in ports if (ports_on[x] and x != read_port)):
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
                bridge_timeout[src] = datetime.datetime.now()
                if rt < bpdu.rt \
                        or (rt == bpdu.rt and (cost < (bpdu.cost - 1))) \
                        or (rt == bpdu.rt and (cost == bpdu.cost - 1) and src < bpdu.bridge_id):
                    # change own BPDU state
                    bpdu = BPDU(src, read_port, rt, cost + 1)
                    src_to_port = {}
                    src_timeout = {}
                    # send out update to all BPDU neighbors
                    for every_port in ports:
                       every_port.send(form_bpdu(my_id, bpdu.rt, bpdu.cost))
                    # reset timeout timer
                    time_out = datetime.datetime.now()
                    des_bridge_flags[read_port] = False
                    if print_toggle:
                        print 'I am not the designated bridge for LAN {}'.format(port_to_lan[read_port])
                elif (rt == bpdu.rt and cost < bpdu.cost) or (rt == bpdu.rt and cost == bpdu.cost and src < my_id):
                    des_bridge_flags[read_port] = False
                    if print_toggle:
                        print 'I am not the designated bridge for LAN {}'.format(port_to_lan[read_port])
                else:
                    if print_toggle:
                        print 'I am the designated bridge for LAN {} my: {} {} yours: {} {}'.format(port_to_lan[read_port], bpdu.cost, my_id, cost, src)

    for port in ports:
        if not(des_bridge_flags[port]) and port != bpdu.rt_port:
            ports_on[port] = False
            if print_toggle:
                print 'Closing port {} ({}) to LAN {}'.format(port.fileno(), port, port_to_lan[port])

if __name__ == "__main__":
    main(sys.argv[1:])