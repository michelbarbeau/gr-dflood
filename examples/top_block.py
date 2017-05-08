#!/usr/bin/env python2
# -*- coding: utf-8 -*-
##################################################
# GNU Radio Python Flow Graph
# Title: Top Block
# Generated: Mon May  8 15:04:32 2017
##################################################

if __name__ == '__main__':
    import ctypes
    import sys
    if sys.platform.startswith('linux'):
        try:
            x11 = ctypes.cdll.LoadLibrary('libX11.so')
            x11.XInitThreads()
        except:
            print "Warning: failed to XInitThreads()"

from gnuradio import blocks
from gnuradio import eng_notation
from gnuradio import gr
from gnuradio.eng_option import eng_option
from gnuradio.filter import firdes
from grc_gnuradio import wxgui as grc_wxgui
from optparse import OptionParser
import dflood
import pmt
import wx


class top_block(grc_wxgui.top_block_gui):

    def __init__(self):
        grc_wxgui.top_block_gui.__init__(self, title="Top Block")
        _icon_path = "/usr/share/icons/hicolor/32x32/apps/gnuradio-grc.png"
        self.SetIcon(wx.Icon(_icon_path, wx.BITMAP_TYPE_ANY))

        ##################################################
        # Variables
        ##################################################
        self.samp_rate = samp_rate = 32000

        ##################################################
        # Blocks
        ##################################################
        self.dflood_dflood_3 = dflood.dflood(
          3, 0, 30, False, False, 
          5, 65, 2, 120, 50, 0, True, None
          )
        self.dflood_dflood_1 = dflood.dflood(
          1, 0, 30, False, False, 
          1, 5, 0, 120, 50, 2, True, None
          )
        self.dflood_dflood_0 = dflood.dflood(
          0, 0, 30, False, False, 
          5, 65, 2, 120, 50, 2, True, None
          )
        self.blocks_random_pdu_0 = blocks.random_pdu(6, 6, chr(0xFF), 2)
        self.blocks_message_strobe_3 = blocks.message_strobe(pmt.intern("TEST"), 20000)
        self.blocks_message_strobe_2_0 = blocks.message_strobe(pmt.intern("TEST"), 10000)
        self.blocks_message_strobe_1 = blocks.message_strobe(pmt.intern("TEST"), 20000)
        self.blocks_message_strobe_0 = blocks.message_strobe(pmt.intern("TEST"), 20000)
        self.blocks_message_debug_0 = blocks.message_debug()

        ##################################################
        # Connections
        ##################################################
        self.msg_connect((self.blocks_message_strobe_0, 'strobe'), (self.dflood_dflood_0, 'ctrl_in'))    
        self.msg_connect((self.blocks_message_strobe_1, 'strobe'), (self.dflood_dflood_1, 'ctrl_in'))    
        self.msg_connect((self.blocks_message_strobe_2_0, 'strobe'), (self.blocks_random_pdu_0, 'generate'))    
        self.msg_connect((self.blocks_message_strobe_3, 'strobe'), (self.dflood_dflood_3, 'ctrl_in'))    
        self.msg_connect((self.blocks_random_pdu_0, 'pdus'), (self.dflood_dflood_3, 'from_app'))    
        self.msg_connect((self.dflood_dflood_0, 'to_app'), (self.blocks_message_debug_0, 'print_pdu'))    
        self.msg_connect((self.dflood_dflood_0, 'to_radio'), (self.dflood_dflood_1, 'from_radio'))    
        self.msg_connect((self.dflood_dflood_1, 'to_radio'), (self.dflood_dflood_0, 'from_radio'))    
        self.msg_connect((self.dflood_dflood_1, 'to_radio'), (self.dflood_dflood_3, 'from_radio'))    
        self.msg_connect((self.dflood_dflood_3, 'to_radio'), (self.dflood_dflood_1, 'from_radio'))    

    def get_samp_rate(self):
        return self.samp_rate

    def set_samp_rate(self, samp_rate):
        self.samp_rate = samp_rate


def main(top_block_cls=top_block, options=None):

    tb = top_block_cls()
    tb.Start(True)
    tb.Wait()


if __name__ == '__main__':
    main()
