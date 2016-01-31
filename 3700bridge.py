#!/usr/bin/python -u
# The -u makes output unbuffered, so it will show up immediately
import sys
import socket
import select


# pads the name with null bytes at the end
def pad(name):
    result = '\0' + name
    while len(result) < 108:
        result += '\0'
    return result


if __name__ == "__main__":
    id = sys.argv[1]
    LAN = sys.argv[2:]
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
            data = x.recv(1500)
            print(data)
