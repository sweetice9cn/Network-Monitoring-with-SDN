from operator import attrgetter

import controller_two
import matplotlib
matplotlib.use('agg')
import matplotlib.pyplot as plt
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER, DEAD_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.lib import hub
from ryu.ofproto import ether
from ryu.ofproto import inet
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import ether_types
from ryu.lib import mac
from ryu.lib.packet import arp
from ryu.lib.packet import ipv4
from ryu.lib.packet import icmp
from ryu.lib.packet import udp


class MonitorTwo(controller_two.ControllerTwo):

    def __init__(self, *args, **kwargs):
        super(MonitorTwo, self).__init__(*args, **kwargs)
        self.datapaths = {}

        self.time = []

        # all links for h1 -> h2, h1 -> h3, and h2 -> h3
        # variables used to store current traffic amount over time
        self.s3_s1 = [0] 
        self.s1_s4 = [0] 
        self.s3_s2 = [0]
        self.s2_s4 = [0]
        self.s1_s5 = [0]
        self.s2_s5 = [0]
        self.s4_s1 = [0]
        self.s4_s2 = [0]

        # variables used to store all accumulative traffic amount
        self.s3_s1_acc = [0] 
        self.s1_s4_acc = [0] 
        self.s3_s2_acc = [0]
        self.s2_s4_acc = [0]
        self.s1_s5_acc = [0]
        self.s2_s5_acc = [0]
        self.s4_s1_acc = [0]
        self.s4_s2_acc = [0]

        # all paths involved
        self.s3_s1_s4 = 0 # h1->h2
        self.s3_s2_s4 = 0 # h1->h2
        self.s3_s1_s5 = 0 # h1->h3
        self.s3_s2_s5 = 0 # h1->h3
        self.s4_s1_s5 = 0 # h2->h3
        self.s4_s2_s5 = 0 # h2->h3

        self.monitor_thread = hub.spawn(self._monitor)

    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def _state_change_handler(self, ev):
        datapath = ev.datapath
        if ev.state == MAIN_DISPATCHER:
            if datapath.id not in self.datapaths:
                self.logger.debug('register datapath: %016x', datapath.id)
                self.datapaths[datapath.id] = datapath
        elif ev.state == DEAD_DISPATCHER:
            if datapath.id in self.datapaths:
                self.logger.debug('unregister datapath: %016x', datapath.id)
                del self.datapaths[datapath.id]

    def _monitor(self):
        timer = -10 # discard first value since UDP flow not start yet
        while timer <= 660: # monitor the traffic load for longer than 10 mins
            if timer >= 0:
                self.time.append(timer)
            timer = timer + 10
            for dp in self.datapaths.values():
                self._request_stats(dp)
            hub.sleep(10) # monitor the traffic load every 10 secs
        # plotting
        self._plot(self.time, self.s3_s1, 's3_s1')
        self._plot(self.time, self.s1_s4, 's1_s4')
        self._plot(self.time, self.s3_s2, 's3_s2')
        self._plot(self.time, self.s2_s4, 's2_s4')
        self._plot(self.time, self.s1_s5, 's1_s5')
        self._plot(self.time, self.s2_s5, 's2_s5')
        self._plot(self.time, self.s4_s1, 's4_s1')
        self._plot(self.time, self.s4_s2, 's4_s2')

    def _plot(self, time, linkTraffic, linkName):
        linkTraffic[1] = 0 # the first value is the accumulated value rather than the interval value, reset it to 0 for plotting at time = 0s
        plt.plot(time, linkTraffic[1:])
        plt.xlabel('Time in secs')
        plt.ylabel('Rate in bits/s')
        plt.grid()
        plt.legend([linkName], loc = 'upper right')
        path = 'Downloads/' + linkName + '_two.png'
        plt.savefig(path, bbox_inches='tight')
        plt.clf()

    def _request_stats(self, datapath):
        self.logger.debug('send stats request: %016x', datapath.id)
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        req = parser.OFPFlowStatsRequest(datapath)
        datapath.send_msg(req)

        req = parser.OFPPortStatsRequest(datapath, 0, ofproto.OFPP_ANY)
        datapath.send_msg(req)

    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def _flow_stats_reply_handler(self, ev):
        body = ev.msg.body

        '''self.logger.info('flowpath         '
                         'out-port packets  bytes')
        self.logger.info('---------------- '
                         '-------- -------- --------')
        for stat in sorted([flow for flow in body if flow.priority >= 1],
                           key=lambda flow: (flow.instructions[0].actions[0])):
            self.logger.info('%016x %8x %8d %8d',
                             ev.msg.datapath.id,
                             stat.instructions[0].actions[0].port,
                             stat.packet_count, stat.byte_count)'''

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def _port_stats_reply_handler(self, ev):
        body = ev.msg.body

        '''self.logger.info('datapath         port     '
                         'rx-pkts  rx-bytes rx-error '
                         'tx-pkts  tx-bytes tx-error')
        self.logger.info('---------------- -------- '
                         '-------- -------- -------- '
                         '-------- -------- --------')'''

        # calculate traffic speed for different links
        for stat in sorted(body, key=attrgetter('port_no')):
            '''self.logger.info('%016x %8x %8d %8d %8d %8d %8d %8d',
                             ev.msg.datapath.id, stat.port_no,
                             stat.rx_packets, stat.rx_bytes, stat.rx_errors,
                             stat.tx_packets, stat.tx_bytes, stat.tx_errors)'''
            if ev.msg.datapath.id == 3 and stat.port_no == 2: # link s3_s1
                self._calculate_speed(self.s3_s1, self.s3_s1_acc, stat.tx_bytes)
            if ev.msg.datapath.id == 1 and stat.port_no == 2: # link s1_s4
                self._calculate_speed(self.s1_s4, self.s1_s4_acc, stat.tx_bytes)
            if ev.msg.datapath.id == 3 and stat.port_no == 3: # link s3_s2
                self._calculate_speed(self.s3_s2, self.s3_s2_acc, stat.tx_bytes)
            if ev.msg.datapath.id == 2 and stat.port_no == 2: # link s2_s4
                self._calculate_speed(self.s2_s4, self.s2_s4_acc, stat.tx_bytes)
            if ev.msg.datapath.id == 1 and stat.port_no == 3: # link s1_s5
                self._calculate_speed(self.s1_s5, self.s1_s5_acc, stat.tx_bytes)
            if ev.msg.datapath.id == 2 and stat.port_no == 3: # link s2_s5
                self._calculate_speed(self.s2_s5, self.s2_s5_acc, stat.tx_bytes)
            if ev.msg.datapath.id == 4 and stat.port_no == 2: # link s4_s1
                self._calculate_speed(self.s4_s1, self.s4_s1_acc, stat.tx_bytes)
            if ev.msg.datapath.id == 4 and stat.port_no == 3: # link s4_s2
                self._calculate_speed(self.s4_s2, self.s4_s2_acc, stat.tx_bytes)

    def _calculate_speed(self, link, acc, tx_bytes):
        size = len(acc)
        acc.append(tx_bytes)
        link.append((tx_bytes - acc[size - 1]) / 10 * 8) # (cumulative value minus last stored value) divided by time interval multiply by 8bits/byte

    # since the UDP flows are one direction in this lab, we add flows for all switches in the chosen path at a time when a new flow arrived from the host
    def _arrange_path(self, datapath, in_port, pkt_ipv4, pkt_udp):
        # path load is the load of the link currently undergoes the maximum traffic on this path 
        self.s3_s1_s4 = max(self.s3_s1[len(self.s3_s1) - 1], self.s1_s4[len(self.s1_s4) - 1])
        self.s3_s2_s4 = max(self.s3_s2[len(self.s3_s2) - 1], self.s2_s4[len(self.s2_s4) - 1])
        self.s3_s1_s5 = max(self.s3_s1[len(self.s3_s1) - 1], self.s1_s5[len(self.s1_s5) - 1])
        self.s3_s2_s5 = max(self.s3_s2[len(self.s3_s2) - 1], self.s2_s5[len(self.s2_s5) - 1])
        self.s4_s1_s5 = max(self.s4_s1[len(self.s4_s1) - 1], self.s1_s5[len(self.s1_s5) - 1])
        self.s4_s2_s5 = max(self.s4_s2[len(self.s4_s2) - 1], self.s2_s5[len(self.s2_s5) - 1])
        dpid = datapath.id
        if dpid == 3: # rules for h1->h2 and h1->h3
            if self.s3_s1_s4 <= self.s3_s2_s4: # compare load
                self._add_UDP_rules(datapath, in_port, pkt_udp, 40000, "10.0.0.1", "10.0.0.2", 2)
            else:
                self._add_UDP_rules(datapath, in_port, pkt_udp, 40000, "10.0.0.1", "10.0.0.2", 3)
            if self.s3_s1_s5 <= self.s3_s2_s5: # compare load
                self._add_UDP_rules(datapath, in_port, pkt_udp, 40000, "10.0.0.1", "10.0.0.3", 2)
            else:
                self._add_UDP_rules(datapath, in_port, pkt_udp, 40000, "10.0.0.1", "10.0.0.3", 3)
        if dpid == 4: # rules for h2->h3
            self._add_UDP_rules(datapath, in_port, pkt_udp, 40000, "10.0.0.1", "10.0.0.2", 1)
            if self.s4_s1_s5 <= self.s4_s2_s5: # compare load
                self._add_UDP_rules(datapath, in_port, pkt_udp, 40000, "10.0.0.2", "10.0.0.3", 2)
            else:
                self._add_UDP_rules(datapath, in_port, pkt_udp, 40000, "10.0.0.2", "10.0.0.3", 3)
        self._send_UDP_msg(datapath, in_port, pkt_ipv4, pkt_udp)

    def _add_UDP_rules(self, datapath, in_port, pkt_udp, priority, ipv4_src, ipv4_dst, fwd_port):
        parser = datapath.ofproto_parser
        match = parser.OFPMatch(in_port = in_port, eth_type = ether.ETH_TYPE_IP, ip_proto = inet.IPPROTO_UDP, ipv4_src = ipv4_src, ipv4_dst = ipv4_dst, udp_src = pkt_udp.src_port, udp_dst = pkt_udp.dst_port)
        actions = [parser.OFPActionOutput(fwd_port)]
        self.add_flow(datapath, priority, match, actions)

    def _send_UDP_msg(self, datapath, in_port, pkt_ipv4, pkt_udp):
        resolve_src_mac = self.arp_table[pkt_ipv4.src]
        resolve_dst_mac = self.arp_table[pkt_ipv4.dst]
        pkt = packet.Packet()
        pkt.add_protocol(ethernet.ethernet(ethertype = ether.ETH_TYPE_IP, dst = resolve_src_mac, src = resolve_dst_mac))
        pkt.add_protocol(ipv4.ipv4(dst = pkt_ipv4.src, src = pkt_ipv4.dst, proto = pkt_ipv4.proto))
        pkt.add_protocol(udp.udp(src_port = pkt_udp.dst_port, dst_port = pkt_udp.src_port))
        self._send_packet(datapath, in_port, pkt)

    def _send_packet(self, datapath, port, pkt):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        pkt.serialize()
        data = pkt.data
        actions = [parser.OFPActionOutput(port = port)]
        out = parser.OFPPacketOut(datapath = datapath, buffer_id = ofproto.OFP_NO_BUFFER, in_port = ofproto.OFPP_CONTROLLER, actions = actions, data = data)
        datapath.send_msg(out)

    def add_flow(self, datapath, priority, match, actions):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(datapath = datapath, priority = priority, match = match, instructions = inst)
        datapath.send_msg(mod)