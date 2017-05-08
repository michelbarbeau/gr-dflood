#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2016 Michel Barbeau, Carleton University.
# Version: May 8, 2016
#
# This is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3, or (at your option)
# any later version.
#
# This software is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this software; see the file COPYING.  If not, write to
# the Free Software Foundation, Inc., 51 Franklin Street,
# Boston, MA 02110-1301, USA.
#

# The program has four entry points:
# 1. "Constructor": __init__()
# 2. Handler: radio_rx()
#    Handles a message from the radio.
#    Call sequence: _radio_rx() ->

import random
import sys
import threading
import time
from collections import namedtuple

import numpy
import pmt
from gnuradio import gr


class dflood(gr.basic_block):
    """
    The module implements the protocol originally described in:
    R. Otnes and S. Haavik, "Duplicate reduction with adaptive backoff for a
    flooding-based underwater  network protocol," OCEANS - Bergen, 2013 MTS/IEEE,
    Bergen, 2013, pp. 1-6.
    and:
    A. Komulainen and J. Nilsson, "Capacity improvements for reduced flooding using
    distance to sink information in underwater networks," Underwater Communications
    and Networking (UComms), 2014, Sestri Levante, 2014, pp. 1-5.
    """

    def __init__(self,
                 # Address
                 addr=0,
                 # My sink address
                 my_sink_addr=0,
                 # Sink packet broadcast interval (s)
                 broadcast_interval=30,
                 # when true, log error messages to a file
                 errors_to_file=False,
                 # when true, write received data to a file
                 data_to_file=False,
                 # Minimum packet forwarding delay (s)
                 Tmin=5,
                 # Maximum packet forwarding delay (s)
                 Tmax=65,
                 # Maximum number of duplicates
                 Ndupl=2,
                 # Life time of a packet table entry (s)
                 Plt=120,
                 # Life time of a sink table entry (s)
                 Slt=50,
                 # Robustness factor
                 R=2,
                 # debug mode
                 debug=False,
                 # FEC mode,
                 FEC=None
                 ):
        gr.basic_block.__init__(self,
                                name="dflood",
                                in_sig=None,
                                out_sig=None)

        # lock for exclusive access
        self.lock = threading.RLock()

        if errors_to_file:
            # redirect standard error stream to a file
            errorFilename = "errors_" + str(addr) + ".txt"
            sys.stderr = open(errorFilename, "w")
            sys.stderr.write(
                "*** START: " + time.asctime(time.localtime(time.time())) + "\n")
        if data_to_file:
            # redirect standard output stream to a file
            dataFilename = "data_" + str(addr) + ".txt"
            sys.stdout = open(dataFilename, "w")
            sys.stdout.write(
                "***START: " + time.asctime(time.localtime(time.time())) + "\n")

        # sink packet broadcast period
        self.broadcast_interval = broadcast_interval
        # Life time of a sink table entry
        self.Tmin = Tmin
        self.Tmax = Tmax
        self.Ndupl = Ndupl
        self.Plt = Plt
        self.Slt = Slt
        self.R = R
        self.FEC = FEC
        self.large_backoff = 5
        self.small_backoff = 2.5
        self.low_backoff = 1
        1
        # message i/o for radio interface
        self.message_port_register_out(pmt.intern('to_radio'))
        self.message_port_register_in(pmt.intern('from_radio'))
        self.set_msg_handler(pmt.intern('from_radio'), self.radio_rx)
        # message i/o for app interface
        self.message_port_register_out(pmt.intern('to_app'))
        self.message_port_register_in(pmt.intern('from_app'))
        self.set_msg_handler(pmt.intern('from_app'), self.app_rx)
        self.message_port_register_in(pmt.intern('from_app_arq'))
        # message i/o for ctrl interface
        self.message_port_register_out(pmt.intern('ctrl_out'))
        self.message_port_register_in(pmt.intern('ctrl_in'))
        self.set_msg_handler(pmt.intern('ctrl_in'), self.ctrl_rx)

        # --- Constants
        # sink address
        self.SINK_ADDR = my_sink_addr
        self.PKT_PROT_ID = 0
        self.PKT_SNDR = 1  # sender
        # original source (sink if sink pckt & sensor if data pkt)
        self.PKT_SRC = 2
        self.PKT_SN = 3  # Sequence number
        self.PKT_HC = 4  # Hop Count
        # -- Data packet
        self.DATA_PKT_MIN_LENGTH = 7  # data packet length
        self.DATA_PROTO = 0
        # bytes 0 to 4 are PKT_PROT_ID, PKT_SNDR, PKT_SRC, PKT_SN and PKT_HC
        self.DATA_PKT_DEST = 5  # destination sink
        self.DATA_PKT_TTL = 6  # time to live
        # -- Sink packet
        self.SINK_PKT_LENGTH = 5  # sink packet length
        self.SINK_PROTO = 1  # Protocol ID field
        # bytes 0 to 4 are PKT_PROT_ID, PKT_SNDR, PKT_SRC, PKT_SN and PKT_HC
        # -- Receive notification
        self.RECV_NOTI_LENGTH = 4  # sink packet length
        self.NOTI_PROTO = 2
        # bytes 0 to 3 are PKT_PROT_ID, PKT_SNDR, PKT_SRC and PKT_SN

        # --- State variables
        # debug mode flag
        self.debug_stderr = debug
        # node address
        self.addr = addr
        # sink packet sequence number
        self.sequence_number = 0
        # time of last transmission of sink packet (used by sink only)
        self.sink_pkt_xmit_time = None
        # data packet number
        self.pkt_cnt = 0
        # nodesNeighborTable
        self.neighborTable = {}
        self.emaAlpha = 0.8
        # --- Sink-neighbor table
        self.sinkNeighborTable = {}
        # key
        # ["sink","neighbor"]
        # value
        self.SinkNeighborVal = namedtuple(
            "SinkNeighborVal",
            ["last_rcvd_seq_num",  # last received sequence number
             "min_dx_to_sink",
             "last_time_heard",
             "broadcast_interval"])

        # --- Sink table
        self.sinkTable = {}
        # key
        # "sink"
        # value
        self.SinkVal = namedtuple("SinkVal", [
            "highest_rcvd_seq_num",
            "min_dx_to_sink",
            "last_time_heard",
            "forwarding_time",
            "scheduled",
            "temp_min_dx_to_sink"])

        # --- Data packet table
        self.dataPacketTable = {}
        # key
        #  ["source","seq_num", "dest"])
        # value
        self.DataPktVal = namedtuple("DataPktVal", [
            "data",
            "last_time_heard",
            "forwarding_time",
            "scheduled",
            "duplicates"])

    # ---------------------------------------
    # scan and update the sink-neighbor table
    # ---------------------------------------
    def check_sink_neighbor_table(self):
        # get current time
        time_now = time.time()
        # take a copy of key list
        keys = self.sinkNeighborTable.keys()
        for key in keys:
            # get time since a packet for this sink-neighbor has been heard
            diff = time_now - self.sinkNeighborTable[key].last_time_heard
            # lost path to that sink-neighbor?
            if diff > self.Slt:
                # yes! remove the sink-neighbor
                self.sinkNeighborTable.pop(key, None)
                # log the change
                if self.debug_stderr:
                    sys.stderr.write(
                        "%d: in check_sink_neighbor_table(): "
                        "sink-neighbor dropped: %s\n" %
                        (self.addr, key))

    # ---------------------------------------
    # find minium address in neighbor table
    # ---------------------------------------
    def minium_addr_in_sink_neighbor_table(self):
        keylist = []
        for key in self.sinkNeighborTable.keys():
            keylist.append(key[0])
        return min(keylist)

    # ------------------------------
    # scan and update the sink table
    # ------------------------------

    def check_sink_table(self):
        # get current time
        time_now = time.time()
        # take a copy of keyk list
        keys = self.sinkTable.keys()
        for key in keys:
            # get time since a packet for this sink has been heard
            diff = time_now - self.sinkTable[key].last_time_heard
            # lost path to that sink?
            if diff > self.Slt:
                # yes! remove the sink
                self.sinkTable.pop(key, None)
                # log the change
                if self.debug_stderr:
                    sys.stderr.write("%d: in check_sink_table(): sink dropped: %s\n" %
                                     (self.addr, key))

    # -------------------------------------
    # scan and update the data packet table
    # -------------------------------------
    def check_data_packet_table(self):
        # get current time
        time_now = time.time()
        # take a copy of key list
        keys = self.dataPacketTable.keys()
        for key in keys:
            # get time since a packet for this sink has been heard
            diff = time_now - self.dataPacketTable[key].last_time_heard
            # packet lifetime expired?
            if diff > self.Plt:
                # yes! remove the packet
                self.dataPacketTable.pop(key, None)
                # log the change
                if self.debug_stderr:
                    sys.stderr.write("%d: in check_data_packet_table(): packet dropped: %s\n" %
                                     (self.addr, key))

    # -------------------------------------
    # Handle a message from the application
    # msg = message from the application
    # -------------------------------------
    def app_rx(self, msg):
        # get exclusive access
        with self.lock:
            self._app_rx(msg)

    # ---------------------------------------------------------------
    # Handle a message from the application, exclusive access assumed
    # msg = message from the application
    # ---------------------------------------------------------------
    def _app_rx(self, msg):
        # verify structure, must be meta-data pair
        try:
            meta = pmt.car(msg)
            data = pmt.cdr(msg)
        except:
            # wrong structure!
            if self.debug_stderr:
                sys.stderr.write("in _app_rx(): message is not a PDU\n")
            # do nothing!
            return
        # is data a vector of unsigned chars?
        if pmt.is_u8vector(data):
            # yes! convert to python data type
            data = pmt.u8vector_elements(data)
        else:
            # no!
            if self.debug_stderr:
                sys.stderr.write("in _app_rx(): data is not a u8vector\n")
            # do nothing!
            return
        # convert meta data to a Python dictionary
        meta_dict = pmt.to_python(meta)
        if not (type(meta_dict) is dict):
            meta_dict = {}
        # send the packet
        self.send_pkt_radio(data, meta_dict, self.pkt_cnt)
        # increment packet number
        self.pkt_cnt = (self.pkt_cnt + 1) % 256

    # --------------------------------
    # pretty printing of a data packet
    # --------------------------------
    def print_pkt(self, pkt):
        # is packet length valid?
        if (len(pkt) < self.DATA_PKT_MIN_LENGTH):  # no!
            sys.stderr.write("in print_pkt(): packet too short!\n")
            return
        # print protocol id
        sys.stderr.write("PROT ID: %d (DATA_PROTO) " % pkt[self.PKT_PROT_ID])
        # print sender address
        sys.stderr.write("SNDR: %d " % pkt[self.PKT_SNDR])
        # print source address
        sys.stderr.write("SNSOR: %d " % pkt[self.PKT_SRC])
        # print sequence number
        sys.stderr.write("SN: %d " % pkt[self.PKT_SN])
        # print hop count
        sys.stderr.write("HC: %d " % pkt[self.PKT_HC])
        # destination sink
        sys.stderr.write("DST: %d " % pkt[self.DATA_PKT_DEST])
        # TTL
        sys.stderr.write("TTL: %d\n" % pkt[self.DATA_PKT_TTL])
        # packet has payload?
        if (len(pkt) > self.DATA_PKT_MIN_LENGTH):  # Yes!
            # print data
            sys.stderr.write("DATA: ")
            for i in range(self.DATA_PKT_MIN_LENGTH, len(pkt)):
                sys.stderr.write("%d " % pkt[i])
            sys.stderr.write("\n")

    # -----------------------------------------
    # Transmit a data packet
    # pdu_tuple = PDU pair (payload,meta data)
    # pkt_cnt = sequence number for that packet
    # -----------------------------------------
    def send_pkt_radio(self, payload, meta_dict, pkt_cnt):
        # sink in Sink table?
        if not self.SINK_ADDR in self.sinkTable.keys():
            if self.debug_stderr:
                # yes! log the packet
                sys.stderr.write(
                    "%d:in send_pkt_radio(): dropping packet\n" % self.addr)
            # drop the packet
            return
        # yes! get the value paired with the sink key
        aSinkVal = self.sinkTable[self.SINK_ADDR]
        # yes! data packet header structure
        data = [self.DATA_PROTO, self.addr, self.addr, pkt_cnt, aSinkVal.min_dx_to_sink,
                self.SINK_ADDR, aSinkVal.min_dx_to_sink + self.R]
        # add payload
        if payload is None:
            payload = []
        elif isinstance(payload, str):
            payload = map(ord, list(payload))
        elif not isinstance(payload, list):
            payload = list(payload)
        data += payload
        # debug mode enabled?
        if self.debug_stderr:
            # yes! log the packet
            sys.stderr.write(
                "%d:in send_pkt_radio(): sending packet:\n" % self.addr)
            self.print_pkt(data)
        # conversion to PMT PDU (meta data, data)
        pdu = pmt.cons(
            pmt.to_pmt({}),
            pmt.init_u8vector(len(data), data))
        # push to radio msg port
        self.message_port_pub(pmt.intern('to_radio'), pdu)

    # -------------------------------
    # Handle a message from the radio
    # -------------------------------
    def radio_rx(self, msg):
        # message structure is a meta data-data?
        try:
            meta = pmt.car(msg)
            data = pmt.cdr(msg)
        except:
            if self.debug_stderr:
                # log the error
                sys.stderr.write("in radio_rx(): message is not a PDU\n")
            return
        # data is a vector of unsigned chars?
        if pmt.is_u8vector(data):
            data = pmt.u8vector_elements(data)
        else:
            if self.debug_stderr:
                # log the error
                sys.stderr.write("in radio_rx(): data is not a u8vector\n")
            return
        # convert meta data dictionary from PMT to Python type
        meta_dict = pmt.to_python(meta)
        if not (type(meta_dict) is dict):
            meta_dict = {}
        # Get exclusive access
        with self.lock:
            self._radio_rx(data, meta_dict)

    # ------------------------------------------------------------
    # Handle a message from the radio, exclusive access is assumed
    # data = message content
    # meta_dict = dictionary of meta data, in Python type
    # ------------------------------------------------------------
    def _radio_rx(self, data, meta_dict):
        # validation
        # ----------
        # determine result of CRC evaluation
        crc_ok = True  # default
        if 'CRC_OK' in meta_dict.keys():
            crc_ok = meta_dict['CRC_OK']
        # valid CRC?
        if not crc_ok:
            # no! debug mode enabled?
            if self.debug_stderr:
                # log the error
                sys.stderr.write("in _radio_rx(): packet CRC error\n")
            # do nothing!
            return
        # valid protocol ID?
        if not data[self.PKT_PROT_ID] in [self.DATA_PROTO, self.SINK_PROTO, self.NOTI_PROTO]:
            # no! log the error
            if self.debug_stderr:
                sys.stderr.write("in _radio_rx(): invalid protocol ID: %d\n" %
                                 (data[self.PKT_PROT_ID]))
            return
        # valid packet length?
        if (data[self.PKT_PROT_ID] == self.DATA_PROTO and len(data) < self.DATA_PKT_MIN_LENGTH) or\
           (data[self.PKT_PROT_ID] == self.SINK_PROTO and len(data) != self.SINK_PKT_LENGTH) or \
           (data[self.PKT_PROT_ID] == self.NOTI_PROTO and len(data) != self.RECV_NOTI_LENGTH):
            # no! log the error
            if self.debug_stderr:
                sys.stderr.write("in _radio_rx(): invalid packet length: %d\n" %
                                 (len(data)))
            # do nothing!
            return
        # packet from self?
        if data[self.PKT_SNDR] == self.addr or data[self.PKT_SRC] == self.addr:
            # debug mode enabled?
            if self.debug_stderr:
                # yes! log the error
                sys.stderr.write(
                    "%d:in _radio_rx(): heard my own packet\n" % self.addr)
            # do nothing!
            return
        # debug mode enabled?
        if self.debug_stderr:
            # log the packet!
            sys.stderr.write(
                "%d:in _radio_rx(): receiving packet:\n" % self.addr)
            if data[self.PKT_PROT_ID] == self.DATA_PROTO:
                self.print_pkt(data)
            if data[self.PKT_PROT_ID] == self.SINK_PROTO:
                self.print_sink_pkt(data)
        if data[self.PKT_PROT_ID] == self.SINK_PROTO:
            # handle a data packet
            self.handle_sink_packet(data, meta_dict)
        elif data[self.PKT_PROT_ID] == self.DATA_PROTO:
            # handle a sink packet
            self.handle_data_packet(data, meta_dict)
        elif data[self.PKT_PROT_ID] == self.NOTI_PROTO:
            # handle a receive notification
            self.handle_receive_notification(data, meta_dict)
        return

    # -------------------
    # Sink packet handing
    # -------------------
    def handle_sink_packet(self, data, meta_dict):
        # --------------------------------------
        # Sink-neighbor table related processing
        # --------------------------------------
        # sink & neighbor in Sink-neighbor table?
        key = (data[self.PKT_SNDR], data[self.PKT_SRC])
        if not key in self.sinkNeighborTable.keys() and self.debug_stderr:
            nbi = self.broadcast_interval
            sys.stderr.write("%d:in handle_sink_packet(): "
                             "new sink-neighbor entry %s, "
                             "set newinterval %f\n" %
                             (self.addr, key, nbi))
        elif self.debug_stderr:
            lbt = self.sinkNeighborTable[key].last_time_heard
            obi = self.sinkNeighborTable[key].broadcast_interval
            nbi = 0.8 * obi + 0.2 * (time.time() - lbt)
            sys.stderr.write("%d:in handle_sink_packet(): "
                             "updating sink-neighbor entry %s, "
                             "set newinterval %f\n"
                             % (self.addr, key, nbi))
        # create or update a sink-neighbor entry
        aSinkNeighborVal = self.SinkNeighborVal(
            data[self.PKT_SN],  # last_rcvd_seq_nun
            data[self.PKT_HC],  # min_dx_to_sink (hop_counter)
            time.time(),  # last_time_heard
            nbi)  # new_broadcastinterval
        self.sinkNeighborTable[key] = aSinkNeighborVal
        if self.addr > self.minium_addr_in_sink_neighbor_table():
            self.broadcast_interval = self.sinkNeighborTable[key].broadcast_interval
            sys.stderr.write("%d:in handle_sink_packet(): "
                             "self broadcast interval changed to %f\n"
                             % (self.addr, self.broadcast_interval))
        if self.debug_stderr:
            sys.stderr.write("SN: %d HC: %d HEARD: %d BI: %f\n" %
                             aSinkNeighborVal)
        # -----------------------------
        # Sink table related processing
        # -----------------------------
        # sink in Sink table?
        key = data[self.PKT_SRC]
        if not key in self.sinkTable.keys():
            # sink is new! create a sink entry
            aSinkVal = self.SinkVal(
                data[self.PKT_SN],  # highest_rcvd_seq_num
                data[self.PKT_HC] + 1,  # min_dx_to_sink (hop_counter)
                time.time(),  # last_time_heard
                # schedule sink packet for tranmission
                time.time() + self.small_backoff,  # forwarding_time
                True,  # scheduled
                data[self.PKT_HC])  # temp_min_dx_to_sink
            self.sinkTable[key] = aSinkVal
            # debug mode enabled?
            if self.debug_stderr:
                sys.stderr.write("%d:in handle_sink_packet(): new sink entry %d\n" %
                                 (self.addr, key))
                sys.stderr.write(
                    "SN: %d HC: %d HEARD: %d SCHED TIME: %d SCHED: %r MIN DX: %d\n"
                    % aSinkVal)
        else:
            # get the value paired with the sink key
            aSinkVal = self.sinkTable[key]
            # save current values
            highest_rcvd_seq_num = aSinkVal.highest_rcvd_seq_num
            min_dx_to_sink = aSinkVal.min_dx_to_sink
            forwarding_time = aSinkVal.forwarding_time
            scheduled = aSinkVal.scheduled
            temp_min_dx_to_sink = aSinkVal.temp_min_dx_to_sink
            # info in sink packet is newer than info in sink table?
            if data[self.PKT_SN] > highest_rcvd_seq_num:
                highest_rcvd_seq_num = data[self.PKT_SN]
                # hop count in sink packet is better than info in sink table?
                if data[self.PKT_HC] > min_dx_to_sink:
                    # schedule packet for forwarding with karge backoff
                    forwarding_time = time.time() + self.large_backoff
                else:
                    # schedule packet for forwarding with small backoff
                    forwarding_time = time.time() + self.small_backoff
                scheduled = True
                temp_min_dx_to_sink = data[self.PKT_HC]
            # info in sink packet is same seq num as info in sink table?
            elif data[self.PKT_SN] == highest_rcvd_seq_num:
                # sink packet already scheduled with that seq num?
                if not aSinkVal.scheduled:
                    # no! info in sink packet is better than info in sink
                    # table?!
                    if data[self.PKT_HC] < min_dx_to_sink:
                        # yes! schedule packet for forwarding with low backoff
                        forwarding_time = time.time() + self.low_backoff
                        scheduled = True
                elif data[self.PKT_HC] < temp_min_dx_to_sink:
                    temp_min_dx_to_sink = data[self.PKT_HC]
            # update sink table entry
            aSinkVal = self.SinkVal(
                highest_rcvd_seq_num,  # highest_rcvd_seq_num
                min_dx_to_sink,  # min_dx_to_sink (hop_counter)
                time.time(),  # last_time_heard
                forwarding_time,  # forwarding_time
                scheduled,  # scheduled
                temp_min_dx_to_sink)  # temp_min_dx_to_sink
            self.sinkTable[key] = aSinkVal
            # debug mode enabled?
            if self.debug_stderr:
                sys.stderr.write("%d:in handle_sink_packet(): sink entry updated %d\n" %
                                 (self.addr, data[self.PKT_SRC]))
                sys.stderr.write("SN: %d HC: %d HEARD: %d SCHED TIME: %d SCHED: %r MIN DX: %d\n"
                                 % aSinkVal)

    # --------------------
    # Data packet handling
    # --------------------
    def handle_data_packet(self, data, meta_dict):
        # debug mode enabled?
        if self.debug_stderr:
            sys.stderr.write(
                "%d:in handle_data_packet(): receiving data pkt:\n" % self.addr)
        # sys.stderr.write("++++ %d: %d, %d\n" % \
        #        (self.addr, data[self.PKT_SNDR], data[self.PKT_HC]))
        # reached final destination?
        if data[self.DATA_PKT_DEST] == self.addr:
            # yes! send a one-hop Receive notification
            self.send_notification_radio(data[self.PKT_SRC], data[self.PKT_SN])
            # deliver upper layer protocol
            self.output_user_data((data, meta_dict))
        # destination in Sink table?
        elif data[self.DATA_PKT_DEST] in self.sinkTable.keys():
            # yes! get my dx to sink
            my_dx_to_sink = self.sinkTable[data[self.DATA_PKT_DEST]
                                           ].min_dx_to_sink
            # sys.stderr.write("**** %d: %d, %d, %d\n" % \
            #    (self.addr, data[self.PKT_SNDR], data[self.PKT_HC], my_dx_to_sink))
            # self.print_pkt(data)
            if data[self.DATA_PKT_TTL] - 1 < my_dx_to_sink:
                # drop the packet
                if self.debug_stderr:
                    sys.stderr.write(
                        "%d:in handle_data_packet(): TTL too small:\n" % self.addr)
                return
            # source-destination-sequence_number in Data packet table?
            key = (data[self.PKT_SRC],
                   data[self.DATA_PKT_DEST], data[self.PKT_SN])
            if not key in self.dataPacketTable:  # new packet!
                # update the packet sender and hop count
                data = list(data)
                data[self.PKT_SNDR] = self.addr
                data[self.PKT_HC] = my_dx_to_sink
                # update the TTL
                data[self.DATA_PKT_TTL] = data[self.DATA_PKT_TTL] - 1
                data = tuple(data)
                # create data packet table entry
                forwarding_time = time.time() +\
                    self.Tmin + random.random() * (self.Tmax - self.Tmin)
                self.dataPacketTable[key] = self.DataPktVal(
                    data,
                    time.time(),  # last_time_heard
                    forwarding_time,  # forwarding_time
                    True,  # scheduled
                    0)  # duplicates
                if self.debug_stderr:
                    sys.stderr.write("%d:in handle_data_packet(): new packet scheduled %d\n" %
                                     (self.addr, forwarding_time))
            elif data[self.PKT_HC] <= my_dx_to_sink:  # duplicate!
                # sys.stderr.write("**** %d:in handle_data_packet(): duplicate packet\n")
                aDataPktVal = self.dataPacketTable[key]
                # update packet table entry
                self.dataPacketTable[key] = self.DataPktVal(
                    aDataPktVal.data,
                    aDataPktVal.last_time_heard,
                    aDataPktVal.forwarding_time,
                    aDataPktVal.duplicates + 1 < self.Ndupl,  # scheduled
                    aDataPktVal.duplicates + 1)  # duplicates
                if self.debug_stderr:
                    sys.stderr.write("%d:in handle_data_packet(): duplicate packet\n" %
                                     self.addr)

    # -----------------------------
    # Receive notification handling
    # -----------------------------
    def handle_receive_notification(self, data, meta_dict):
        # source-destination-sequence_number in Data packet table?
        key = (data[self.PKT_SRC], data[self.PKT_SNDR], data[self.PKT_SN])
        if key in self.dataPacketTable:
            # update data packet table entry
            self.dataPacketTable[key] = self.DataPktVal(
                None,  # data
                self.dataPacketTable[key].last_time_heard,
                0,  # forwarding_time
                False,  # scheduled
                self.dataPacketTable[key].duplicates)  # duplicates ]=self.DataPktVal(
            if self.debug_stderr:
                sys.stderr.write("%d:in handle_receive_notificationt(): packet unscheduled\n" %
                                 self.addr)

    # ------------------------
    # push data to application
    # ------------------------
    def output_user_data(self, pdu_tuple):
        self.message_port_pub(pmt.intern('to_app'), \
                              # meta_dic
                              pmt.cons(pmt.to_pmt(pdu_tuple[1]), \
                                       # encapsulated data
                                       pmt.init_u8vector(len(pdu_tuple[0][self.DATA_PKT_MIN_LENGTH:]), \
                                                         pdu_tuple[0][self.DATA_PKT_MIN_LENGTH:])))
        # write packet to standard output
        sys.stdout.write(time.asctime(time.localtime(time.time())) + " : ");
        # print data
        for i in range(0, len(pdu_tuple[0])):
            sys.stdout.write("%d " % pdu_tuple[0][i])
        sys.stdout.write("\n")

    # --------------------------------
    # pretty printing of a sink packet
    # --------------------------------
    def print_sink_pkt(self, pkt):
        # valid sink packet length?
        if (len(pkt) != self.SINK_PKT_LENGTH):
            # yes!
            sys.stderr.write(
                "in print_sink_pkt(): sink packet invalid length!\n")
            return
        # no!
        # print protocol id
        sys.stderr.write("PROT ID: %d (SINK_PROTO) " % pkt[self.PKT_PROT_ID])
        # print sender address
        sys.stderr.write("SNDR: %d " % pkt[self.PKT_SNDR])
        # print sink address
        sys.stderr.write("SINK: %d " % pkt[self.PKT_SRC])
        # print sequence number
        sys.stderr.write("SN: %d " % pkt[self.PKT_SN])
        # print hop count
        sys.stderr.write("HC: %d\n" % pkt[self.PKT_HC])

    # ------------------------
    # transmit a sink packet
    # ------------------------
    def send_sink_pkt(self, addr, seq_num, hop_count):
        # beacon packet structure
        data = [self.SINK_PROTO, self.addr, addr, seq_num, hop_count]
        # debug mode enabled?
        if self.debug_stderr:  # Yes!
            # log the packet
            sys.stderr.write(
                "%d:in send_sink_pkt(): sending sink packet:\n" % self.addr)
            self.print_sink_pkt(data)
        # conversion to PMT PDU (meta data, data)
        pdu = pmt.cons(
            pmt.to_pmt({}),
            pmt.init_u8vector(len(data), data))
        # push to radio msg port
        self.message_port_pub(pmt.intern('to_radio'), pdu)
        # save current transmit time
        with self.lock:
            self.sink_pkt_xmit_time = time.time()

    # -------------------------------
    # Transmit a receive notification
    # -------------------------------
    def send_notification_radio(self, source, seq_num):
        # receiver notification structure
        data = [self.NOTI_PROTO, self.addr, source, seq_num]
        # debug mode enabled?
        if self.debug_stderr:
            # yes! log the packet
            sys.stderr.write(
                "%d:in send_notification_radio(): sending notification:\n" % self.addr)
        # conversion to PMT PDU (meta data, data)
        pdu = pmt.cons(
            pmt.to_pmt({}),
            pmt.init_u8vector(len(data), data))
        # push to radio msg port
        self.message_port_pub(pmt.intern('to_radio'), pdu)

    # ----------------------------------------------------------
    # Handle a control signal
    # Handler triggered on a periodic basis by a Message Strobe.
    # Sends hello messages. Updates the neighbor dictionary.
    # Runs the FSM.
    # ----------------------------------------------------------
    def ctrl_rx(self, msg):
        with self.lock:
            # if sink node?
            if self.addr == self.SINK_ADDR:
                if (self.broadcast_interval > 0) and \
                    (self.sink_pkt_xmit_time is None or
                     (time.time() - self.sink_pkt_xmit_time) >=
                     self.broadcast_interval * 2 * random.random()):  # randomization
                    # send a sink packet
                    self.send_sink_pkt(self.addr, self.sequence_number, 0)
                    self.sequence_number = (self.sequence_number + 1) % 256
            # sink packets scheduled for transmission?
            else:
                # take a copy of key list
                keys = self.sinkTable.keys()
                for k in keys:
                    # get the value paired with the sink key
                    aSinkVal = self.sinkTable[k]
                    # sink packet scheduled
                    if aSinkVal.scheduled and time.time() >= aSinkVal.forwarding_time:
                        self.send_sink_pkt(
                            k,
                            aSinkVal.highest_rcvd_seq_num,
                            aSinkVal.min_dx_to_sink)
                        # update sink table entry
                        aSinkVal = self.SinkVal(
                            aSinkVal.highest_rcvd_seq_num,  # highest_rcvd_seq_num
                            # min_dx_to_sink (hop_counter)
                            aSinkVal.temp_min_dx_to_sink + 1								,
                            aSinkVal.last_time_heard,  # last_time_heard
                            0,  # forwarding_time
                            False,  # scheduled
                            aSinkVal.temp_min_dx_to_sink)  # temp_min_dx_to_sink
            # data packets scheduled for transmission?
            # take a copy of key list
            keys = self.dataPacketTable.keys()
            for k in keys:
                # get the value paired with the key
                aDataPacketVal = self.dataPacketTable[k]
                # sink packet scheduled
                if aDataPacketVal.scheduled and \
                        aDataPacketVal.duplicates <= self.Ndupl and \
                        time.time() >= aDataPacketVal.forwarding_time:
                        # forward the packet
                    if self.debug_stderr:
                        # yes! log the packet
                        sys.stderr.write(
                            "%d:ctrl_rx: sending packet:\n" % self.addr)
                        self.print_pkt(aDataPacketVal.data)
                    # conversion to PMT PDU (meta data, data)
                    pdu = pmt.cons(
                        pmt.to_pmt({}),
                        pmt.init_u8vector(len(aDataPacketVal.data), aDataPacketVal.data))
                    # push to radio msg port
                    self.message_port_pub(pmt.intern('to_radio'), pdu)
                    # update data packet table entry
                    self.dataPacketTable[k] = self.DataPktVal(
                        None,  # data
                        aDataPacketVal.last_time_heard,  # last_time_heard
                        0,  # forwarding_time
                        False,  # scheduled
                        aDataPacketVal.duplicates)  # duplicates
            # update the sink-neighbor table
            self.check_sink_neighbor_table()
            # update the sink table
            self.check_sink_table()
            # update the data packet table
            self.check_data_packet_table()
