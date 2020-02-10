from operator import attrgetter

import controller_one
import matplotlib
matplotlib.use('agg')
import matplotlib.pyplot as plt
import numpy as np
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER, DEAD_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.lib import hub


class MonitorOne(controller_one.ControllerOne):

    def __init__(self, *args, **kwargs):
        super(MonitorOne, self).__init__(*args, **kwargs)
        self.datapaths = {}

        self.time = []

        # all links for h1 -> h2, h1 -> h3, and h2 -> h3
        # variables used to store current traffic amount over time
        self.s3_s1 = [] 
        self.s1_s4 = [] 
        self.s3_s2 = []
        self.s2_s4 = []
        self.s1_s5 = []
        self.s2_s5 = []
        self.s4_s1 = []
        self.s4_s2 = []

        # variables used to store all accumulative traffic amount
        self.s3_s1_acc = [0] 
        self.s1_s4_acc = [0] 
        self.s3_s2_acc = [0]
        self.s2_s4_acc = [0]
        self.s1_s5_acc = [0]
        self.s2_s5_acc = [0]
        self.s4_s1_acc = [0]
        self.s4_s2_acc = [0]

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
        timer = -10 #discard first value since UDP flow not start yet
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
        linkTraffic[0] = 0 # the first value is the accumulated value rather than the interval value, reset it to 0 for plotting at time = 0s
        plt.plot(time, linkTraffic)
        plt.xlabel('Time in secs')
        plt.ylabel('Rate in bits/s')
        plt.grid()
        plt.legend([linkName], loc = 'upper right')
        path = 'Downloads/' + linkName + '_one.png'
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

        # calculate traffic speed for different link
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
        link.append((tx_bytes - acc[size - 1]) / 10 * 8) # speed = (cumulative value minus last stored value) divided by time interval multiply by 8bits/byte
