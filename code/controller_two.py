from ryu.base import app_manager
from ryu.controller import mac_to_port
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.mac import haddr_to_bin
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

class ControllerTwo(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(ControllerTwo, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.arp_table = {}

        self.arp_table["10.0.0.1"] = "00:00:00:00:00:01"
        self.arp_table["10.0.0.2"] = "00:00:00:00:00:02"
        self.arp_table["10.0.0.3"] = "00:00:00:00:00:03"

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # install the table-miss flow entry.
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)

        #set pre-installed rule for s1, s2, s5
        if datapath.id == 1:
            self.add_switch1_rules(datapath, 40000) 
        if datapath.id == 2:
            self.add_switch2_rules(datapath, 40000)
        if datapath.id == 5:
            self.add_switch5_rules(datapath, 40000)

    def add_switch1_rules(self, datapath, priority = 1):
        self.add_rules(datapath, priority, "10.0.0.1", "10.0.0.2", 2)
        self.add_rules(datapath, priority, None, "10.0.0.3", 3)

    def add_switch2_rules(self, datapath, priority = 1):
        self.add_rules(datapath, priority, "10.0.0.1", "10.0.0.2", 2)
        self.add_rules(datapath, priority, None, "10.0.0.3", 3)

    def add_switch5_rules(self, datapath, priority = 1):
        self.add_rules(datapath, priority, None, "10.0.0.3", 1)

    def add_rules(self, datapath, priority = 1, ipv4_src = None, ipv4_dst = None, fwd_port = None):
        parser = datapath.ofproto_parser
        if ipv4_src is None and ipv4_dst is None:
            match = parser.OFPMatch(eth_type = ether.ETH_TYPE_IP, ip_proto = inet.IPPROTO_UDP)
        elif ipv4_src is None:
            match = parser.OFPMatch(eth_type = ether.ETH_TYPE_IP, ip_proto = inet.IPPROTO_UDP, ipv4_dst = ipv4_dst)
        elif ipv4_dst is None:
            match = parser.OFPMatch(eth_type = ether.ETH_TYPE_IP, ip_proto = inet.IPPROTO_UDP, ipv4_src = ipv4_src)
        else:
            match = parser.OFPMatch(eth_type = ether.ETH_TYPE_IP, ip_proto = inet.IPPROTO_UDP, ipv4_src = ipv4_src, ipv4_dst = ipv4_dst)
        if fwd_port is None:
            actions = []
        else:
            actions = [parser.OFPActionOutput(fwd_port)]
        self.add_flow(datapath, priority, match, actions)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        in_port = msg.match['in_port']

        dpid = datapath.id
        self.mac_to_port.setdefault(dpid, {})

        pkt = packet.Packet(msg.data)
        pkt_ethernet = pkt.get_protocols(ethernet.ethernet)
        pkt_arp = pkt.get_protocol(arp.arp)
        pkt_ipv4 = pkt.get_protocol(ipv4.ipv4)
        pkt_icmp = pkt.get_protocol(icmp.icmp)
        pkt_udp = pkt.get_protocol(udp.udp)
        if not pkt_ethernet:
            return
        if pkt_arp:
            self._handle_arp(datapath, in_port, pkt_arp)
            return  
        if pkt_ipv4:
            if pkt_icmp:
                self._handle_icmp(datapath, in_port, pkt_ipv4, pkt_icmp)
                return
            if pkt_udp:
                self._arrange_path(datapath, in_port, pkt_ipv4, pkt_udp) # add flows to switches according to the traffic statistic, defined in monitor_two.py
                return

    def _handle_arp(self, datapath, port, pkts, pkt_arp):
        if pkt_arp.opcode != arp.ARP_REQUEST:
            return
        arp_resolve_mac = self.arp_table[pkt_arp.dst_ip]
        eth_pkt = pkts.get_protocol(ethernet.ethernet)
        pkt = packet.Packet()
        pkt.add_protocol(ethernet.ethernet(ethertype = ether.ETH_TYPE_ARP, dst = eth_pkt.src, src = arp_resolve_mac))
        pkt.add_protocol(arp.arp(opcode = arp.ARP_REPLY, src_mac = arp_resolve_mac, src_ip = pkt_arp.dst_ip, dst_mac = pkt_arp.src_mac, dst_ip = pkt_arp.src_ip))
        self._send_packet(datapath, port, pkt)

    def _handle_icmp(self, datapath, port, pkt_ipv4, pkt_icmp):
        if pkt_icmp.type != icmp.ICMP_ECHO_REQUEST:
            return
        icmp_resolve_src_mac = self.arp_table[pkt_ipv4.src]
        icmp_resolve_dst_mac = self.arp_table[pkt_ipv4.dst]
        pkt = packet.Packet()
        pkt.add_protocol(ethernet.ethernet(ethertype = ether.ETH_TYPE_IP, dst = icmp_resolve_src_mac, src = icmp_resolve_dst_mac))
        pkt.add_protocol(ipv4.ipv4(dst = pkt_ipv4.src, src = pkt_ipv4.dst, proto = pkt_ipv4.proto))
        pkt.add_protocol(icmp.icmp(type_ = icmp.ICMP_ECHO_REPLY, code = icmp.ICMP_ECHO_REPLY_CODE, csum = 0, data = pkt_icmp.data))
        self._send_packet(datapath, port, pkt)