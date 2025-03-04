#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Aug 30 11:36:15 2023

@author: controls
"""
### V2 NOTES ###
# This is version two of the legacy picket fence code for LIGO with the objective of early warning for earthquakes at the observatories.
# See G2001601 and G2201345 for presentations on the matter. A short white paper outlining the performance can be found at T2300281 ###
# v2 Is written by Edgard L. Bonilla [ELB] based on the modifications made by Isaac Aguilar over the original code by Grace Johns, Anne Baer and Ryan Fisher.
# v2 is the first step in decoupling the connection and plotting aspects of the picket fence. We want to simplify modifications to the code by creating a single
# piece of code that can be called with different configurations.


### CODE EXPLANATION ###
#The code consists of three main classes: 
#-- seedlinkUpdater:
    # This class establishes a connection to a seedlink server, it is used to collect data from a list of public and private servers of seismic data.
    # The class is just a subclass of the ObsPy SLClient class: https://docs.obspy.org/packages/obspy.clients.seedlink.html
    # the methods run() and packetHandler() determine how the data is collected.
#-- seedlinkPlotter:
    # This class is based on the code from https://github.com/sbonaime/seedlink_plotter 
    # its main function is to update the display of data. It uses Tkinter to make a GUI that should plot dynamically.
#-- filteredStream:
    # This class is a subclass of ObsPy's stream: https://docs.obspy.org/packages/autogen/obspy.core.stream.Stream.html
    # The objective of the class is to handle all of the data processing of the raw stream that is collected by an instance of the seedlinkUpdater

#[ELB] 08/30/2023    


### IMPORTS ###
import warnings
warnings.filterwarnings("ignore", "Badly*")  # suppresses warning calls from lsim filter function

import matplotlib

# Set the backend for matplotlib.
matplotlib.use("TkAgg")
matplotlib.rc('figure.subplot', hspace=0)
matplotlib.rc('font', family="monospace")

import tkinter
from tkinter import ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator
from matplotlib.patheffects import withStroke
from matplotlib.dates import date2num
import matplotlib.pyplot as plt

# OBSPY imports
from obspy import Stream, Trace
from obspy import __version__ as OBSPY_VERSION
from obspy.core import UTCDateTime
from obspy.core.event import Catalog
from obspy.core.util import MATPLOTLIB_VERSION
from obspy.clients.seedlink.seedlinkexception import SeedLinkException


cartopyflag=1;
try:
    import cartopy
    from picketMapTools import picketMap
except ImportError:
    cartopyflag=0;
    pass


import threading
from time import sleep
from gwpy.time import tconvert
import subprocess
import sys
from scipy import signal

import logging
import numpy as np
import json

import os

pathname=os.path.dirname(os.path.realpath(__file__))+'/'
last_process_gps = 0

OBSPY_VERSION = [int(x) for x in OBSPY_VERSION.split(".")[:2]]
# check obspy version and warn if it's below 0.10.0, which means that a memory
# leak is present in the used seedlink client (unless working on some master
# branch version after obspy/obspy@5ce975c3710ca, which is impossible to check
# reliably). see #7 and obspy/obspy#918.
# imports depend of the obspy version
if OBSPY_VERSION < [0, 10]:
    warning_msg = (
        "ObsPy version < 0.10.0 has a memory leak in SeedLink Client. "
        "Please update your ObsPy installation to avoid being affected by "
        "the memory leak (see "
        "https://github.com/bonaime/seedlink_plotter/issues/7).")
    warnings.warn(warning_msg)
# Check if OBSPY_VERSION < 0.11
if OBSPY_VERSION < [0, 11]:
    # 0.10.x
    from obspy.seedlink.slpacket import SLPacket
    from obspy.seedlink.slclient import SLClient
    from obspy.fdsn import Client
else:
    # >= 0.11.0
    from obspy.clients.seedlink.slpacket import SLPacket
    from obspy.clients.seedlink import SLClient
    from obspy.clients.fdsn import Client

# Compatibility checks
# UTCDateTime
try:
    UTCDateTime.format_seedlink
except AttributeError:
    # create the new format_seedlink fonction using the old formatSeedLink
    # method
    def format_seedlink(self):
        return self.formatSeedLink()


    # add the function in the class
    setattr(UTCDateTime, 'format_seedlink', format_seedlink)
# SLPacket
try:
    SLPacket.get_type
except AttributeError:
    # create the new get_type fonction using the old getType method
    def get_type(self):
        return self.getType()

    # add the function in the class
    setattr(SLPacket, 'get_type', get_type)

try:
    SLPacket.get_trace
except AttributeError:
    # create the new get_trace fonction using the old getTrace method
    def get_trace(self):
        return self.getTrace()

    # add the function in the class
    setattr(SLPacket, 'get_trace', get_trace)

class SeedlinkUpdater(SLClient):
    
    def __init__(self, stream, myargs=None, lock=None):
        # loglevel NOTSET delegates messages to parent logger
        super(SeedlinkUpdater, self).__init__(loglevel="NOTSET")
        self.stream = stream
        self.lock = lock
        self.args = myargs
        self.stop_flag=False

    def run(self, packet_handler=None):
        """
        Start this SLClient.

        :type packet_handler: func
        :param packet_handler: Custom packet handler funtion to override
            `self.packet_handler` for this seedlink request. The function will
            be repeatedly called with two arguments: the current packet counter
            (`int`) and the currently served seedlink packet
            (:class:`~obspy.clients.seedlink.SLPacket`). The function should
            return `True` to abort the request or `False` to continue the
            request.
        """
        
        if packet_handler is None:
            packet_handler = self.packet_handler
        if self.infolevel is not None:
            self.slconn.request_info(self.infolevel)
        # Loop with the connection manager
        count = 1
        slpack = self.slconn.collect()
        while slpack is not None:
            if (slpack == SLPacket.SLTERMINATE):
                break
            try:
                # do something with packet
                terminate = packet_handler(count, slpack)
                if terminate:
                    break
            except SeedLinkException as sle:
                print(self.__class__.__name__ + ": " + sle.value)
            if count >= sys.maxsize:
                count = 1
                print("DEBUG INFO: " + self.__class__.__name__ + ":", end=' ')
                print("Packet count reset to 1")
            else:
                count += 1
            try:
                slpack = self.slconn.collect()
            except TimeoutError:
                print(f"Timeout waiting for packet from server '{str(self.slconn.get_sl_address())}'.")
            except SeedLinkException as e:
                print(f"Seedlink error '{str(e)}' while waiting for packet from server '{str(self.slconn.get_sl_address())}'.")
            if self.stop_flag:
                break

        # Close the SeedLinkConnection
        self.slconn.close()
    def packet_handler(self, count, slpack):
        """
        for compatibility with obspy 0.10.3 renaming
        """
        self.packetHandler(count, slpack)

    def packetHandler(self, count, slpack):
        """
        Processes each packet received from the SeedLinkConnection.
        :type count: int
        :param count:  Packet counter.
        :type slpack: :class:`~obspy.seedlink.SLPacket`
        :param slpack: packet to process.
        :return: Boolean true if connection to SeedLink server should be
            closed and session terminated, false otherwise.
        """

        # check if not a complete packet
        if slpack is None or (slpack == SLPacket.SLNOPACKET) or \
                (slpack == SLPacket.SLERROR):
            return False

        # get basic packet info
        type = slpack.get_type()

        # process INFO packets here
        if type == SLPacket.TYPE_SLINF:
            return False
        if type == SLPacket.TYPE_SLINFT:
            logging.info("Complete INFO:" + self.slconn.getInfoString())
            return self.infolevel is not None

        # process packet data
        trace = slpack.get_trace()
        if trace is None:
            logging.info(
                self.__class__.__name__ + ": blockette contains no trace")
            return False

        # new samples add to the main stream which is then trimmed
        with self.lock:
            self.stream += trace
            self.stream.merge(1,fill_value='interpolate')
            self.stream.trim(starttime=UTCDateTime()-3600)
            for trace in self.stream:
                trace.stats.processing = []
        global last_process_gps
        last_process_gps = tconvert('now').gpsSeconds
        return False

    def getTraceIDs(self):
        """
        Return a list of SEED style Trace IDs that the SLClient is trying to
        fetch data for.
        """
        ids = []
        streams = self.slconn.get_streams()
        for stream in streams:
            net = stream.net
            sta = stream.station
            selectors = stream.get_selectors()
            for selector in selectors:
                if len(selector) == 3:
                    loc = ""
                else:
                    loc = selector[:2]
                cha = selector[-3:]
                ids.append(".".join((net, sta, loc, cha)))
        ids.sort()
        return ids
class picketFenceArguments():
    def __init__(self, stream_time=3600, backtrace_time=15*60, x_position=0, y_position=0, x_size=800, y_size=600, title_size=12, time_legend_size=10,
    tick_format='%H:%M:%S',time_tick_nb=5,threshold=500,lookback=120,update_time=1, min_scale=1000, fullscreen=False,verbose=False,send_epics=False,epics_prefix=None):
    
        #Plot format properties
        self.x_position=x_position              # horizontal position of the graph
        self.y_position=y_position              # vertical position of the graph
        self.x_size=x_size                      # horizontal size of graph
        self.y_size=y_size                      # vertical size of graph
        self.title_size= title_size             # title size of each station in the graph
        self.time_legend_size=time_legend_size  # size of the numbers in the time (horizontal) axis
        self.tick_format=tick_format            # time format for the time ticks
        self.time_tick_nb=time_tick_nb          # number of time ticks
        self.fullscreen=fullscreen              # True toggles the fullscreen display
        self.min_scale=min_scale                # Minimum scale for the plots [nm/s]

        #Data display properties
        self.backtrace_time=backtrace_time      # time (in seconds) that will be displayed in plots
    
        #Data analysis properties
        self.stream_time=stream_time            # time in seconds that will be kept of the stream before deleting
        self.threshold=threshold                # threshold in (nm/s) for determining the triggers for color changes    
        self.lookback=lookback                  # time (in seconds) that we analyze in search of earthquake signals
        self.update_time=update_time            # refresh rate (in seconds) of the graph
    
        #other arguments
        self.verbose=verbose                    # True toggles the debug log
        self.send_epics=send_epics              # True enables data logging into EPICS variables  
        if self.send_epics:
            assert type(epics_prefix) == str , "the epics prefix should be a string"
        self.epics_prefix=epics_prefix
          
class filteredStream(Stream):
    
    def __init__(self, rawStream, myargs, filterTransientTime=180):
        super(filteredStream, self).__init__()
        
        #self.lock=lock
        self.args=myargs
        self.filterTransientTime=filterTransientTime
        
        #initialize the internal traces
        self.rawStream = rawStream
        self.traces=rawStream.copy().traces
        
        #Define Edgard's modification to the Lowpass filter that doesn't distort EQs [SEI aLog 2372] - NOTE: 5 second delay in this filter
        num =[0,	0.76318885484945,	0.90992993724968,	21.7100277548763,	19.255568102408,	75.3052756093984,	24.3578154023362,	64.5048931618441,	7.30919499736169,	15.8338176261434,	0]
        den =[1,	14.6909055035109,	78.5925152790263,	590.325637467408,	677.92614780260,	727.928526646198,	471.445913748708,	250.464075026040,	88.1450949736601,	22.7381207863554,	1.84567521372509]
        self.filter=(num,den)
        
        #Internal states for Brian's filter
        self.customMetadata=dict()
        for trace in self.traces:
            self.customMetadata[trace.id]=dict()
            self.FirstLowpass(trace)
            
    #Function that creates a hanning window for initial filtering of data, helps alleviate transients.
    def HanningWindow(self,trace): 
        trace_len = len(trace.data)
        window_len = trace_len // 2
        window_len -= (window_len % 2) # Make sure window length is an even number
        if trace_len > window_len:
            hw = np.hanning(window_len) # Hanning window size of window length
            hw = np.split(hw, 2)
            hw = hw[0]
            hw_num = trace_len - window_len / 2 # Only first half of hanning window, don't want
            # the right side of the data to be impacted (only care about the most recent n seconds of data)
            hw_num = int(hw_num)
            new = np.tile(1, hw_num) # Make everything after the hanning window one, don't want most recent n seconds to be impacted
            hwp = np.append(hw, new)
            trace.data = trace.data * hwp # Apply window
            
    #Function that applies a lowpass filter to an initial portion of data for which we have no internal filter states   
    def FirstLowpass(self,trace):
        dt = trace.stats.delta
        self.HanningWindow(trace)
        T=np.arange(0.0, len(trace.data))
        T *= dt
        tout, yout, xout =signal.lsim(self.filter, trace.data, T, X0=None)
        trace.data = yout
        trace.trim(starttime=trace.stats.starttime+self.filterTransientTime) #TODO: Change this to actually be useful, do we want to chop 3 minutes of data?
        #Initialize the metadata
        if trace.data.size>0:
            self.customMetadata[trace.id]['filterState']=xout[-1]
            self.customMetadata[trace.id]['endtime']=trace.stats.endtime
            self.customMetadata[trace.id]['Glitch_ABSMAX']=0
            self.customMetadata[trace.id]['MAX']=np.max(trace.data)
            self.customMetadata[trace.id]['MIN']=np.min(trace.data)
            self.customMetadata[trace.id]['MEAN']=np.mean(trace.data)
            
    #Function that updates the filtered Stream with new data from the rawStream that is connected to it
    def CollectAndAnalyze(self):
        #with self.lock:
        for trace in self.rawStream.traces:
            if trace.id in self.getTraceIDs(): #if we have the trace in the filtered stream
                oldEndtime=self.customMetadata[trace.id]['endtime']
                
                #Trim traces to isolate the new data
                if (trace.stats.endtime-oldEndtime)>0:
                    dt = trace.stats.delta
                    newTrace=trace.slice(starttime=oldEndtime+dt)
                    trace_len=len(newTrace.data)
                    if trace_len > 0:
                        #filter the new data and trim
                        xin=self.customMetadata[newTrace.id]['filterState'];
                        T=np.arange(0.0, trace_len)
                        T *= dt
                        tout, yout, xout =signal.lsim(self.filter, newTrace.data, T, X0=xin)
                        newTrace.data = yout

                        #Update the trace metadata
                        self.customMetadata[trace.id]['MAX']=np.max(newTrace.data)
                        self.customMetadata[trace.id]['MIN']=np.min(newTrace.data)
                        self.customMetadata[trace.id]['MEAN']=np.mean(newTrace.data)
                        self.customMetadata[newTrace.id]['filterState']=xout[-1]
                        self.customMetadata[newTrace.id]['endtime']=newTrace.stats.endtime
                        self.append(newTrace)
                    
            else:#This trace is only present in the raw stream but has never been filtered
                newTrace=trace.copy()
                self.customMetadata[trace.id]=dict()
                self.FirstLowpass(newTrace)    
                self.append(newTrace)
                
        #Merge and clean the trace information
        self.mergeAndCleanMetadata()
            
    #Function that returns the ids currently in the filtered stream        
    def getTraceIDs(self):
        return [tr.id for tr in self.traces]
    
    #This function keeps track of metadata for the traces over the last 'lookback' seconds
    def mergeAndCleanMetadata(self):
        self.merge(-1)
        #Trim and check for glitches
        self.trim(UTCDateTime()-2*self.args.backtrace_time) #TODO: make this trim not arbitrary
        for trace in self.traces:
            trace.stats.processing = []         
            #Check for Glitches
            dummyTrace=trace.slice(starttime=UTCDateTime()-self.args.backtrace_time)
            if len(dummyTrace.data)!=0:
                self.customMetadata[trace.id]['Glitch_ABSMAX']=abs(dummyTrace.max())
            else: #We don't have recent data, reset all values to 0 and wait for more data
                self.customMetadata[trace.id]['MAX']=0
                self.customMetadata[trace.id]['MIN']=0
                self.customMetadata[trace.id]['MEAN']=0
                self.customMetadata[trace.id]['Glitch_ABSMAX']=0
                
class SeedlinkPlotter(tkinter.Tk):
    """
    This module plots realtime seismic data from a Seedlink server
    """
    def __init__(self, stream=None, picket_dict=None, events=None, myargs=None, lock=None, leave=[False],
                 *args, **kwargs): # , send_epics=False
        tkinter.Tk.__init__(self, *args, **kwargs)
        self.wm_title("Picket Fence v2")
        self.focus_set()
        self._bind_keys()
        args = myargs
        self.lock = lock
        # size and position
        self.geometry(str(args.x_size) + 'x' + str(args.y_size) + '+' + str(
            args.x_position) + '+' + str(args.y_position))
        w, h, pad = self.winfo_screenwidth(), self.winfo_screenheight(), 3
        self._geometry = ("%ix%i+0+0" % (w - pad, h - pad))
        # hide the window decoration
        if args.fullscreen:
            self._toggle_fullscreen(None)

        # main figure
        self.figure = Figure()
        canvas = FigureCanvasTkAgg(self.figure, master=self)

        if MATPLOTLIB_VERSION[:2] >= [2, 2]:
            canvas.draw()
        else:
            canvas.show()
        canvas.get_tk_widget().pack(fill=tkinter.BOTH, expand=1)

        self.backtrace = args.backtrace_time
        self.canvas = canvas
        self.args = args
        self.pickets=picket_dict
        self.send_epics=self.args.send_epics
        self.epics_prefix=self.args.epics_prefix
        self.leave=leave
        self.stream = stream
        self.events = events
        self._define_thresholds_and_colors()
        self.threshold=self.args.threshold
        self.tracePlotSpecs=dict()
        self.lookback = args.lookback
        self.POTENTIAL_GLITCHES = []
        self.glitch_threshold=50000 #[nm/s]
        self.unglitch_threshold=1000 #[nm/s]
        self.glitch_cooldown_time=5*60 #[s] 5 Minutes total
        self.large_EQ_cooldown=0 #[s] Current glitch cooldown, it prevents stations from glitching it there's a large EQ
        self.plot_graph()

    def _close_window(self):
        self.event_generate("<KeyPress>", keysym="q")  ## simulates 'q' being pressed ('q' is binded with quit)

    def _quit(self, event):
        self.leave = [True]
        event.widget.quit()

    def _bind_keys(self):
        self.bind('<Escape>', self._quit)
        self.bind('q', self._quit)
        self.protocol("WM_DELETE_WINDOW", self._close_window)
        self.bind('f', self._toggle_fullscreen)

    def _toggle_fullscreen(self, event):
        g = self.geometry()
        self.geometry(self._geometry)
        self._geometry = g
        
    def _define_thresholds_and_colors(self):
        threshold_color_state=[
            (5000, "RED"),
            (1000, "ORANGE"),
            (500, "YELLOW"),
            (0,"NORMAL"),
            ]
        self.threshold_color_state=sorted(threshold_color_state,key=lambda tup: tup[0],reverse=True)
        
        with open(pathname+'picket_fence_styles.json','r') as f: #TODO: make it not load ALL styles.
            self.color_themes=json.load(f)
        self.current_style=self.color_themes["Anderson"]
        self.current_style_index=0; #TODO: change this so it dynamically picks the first style 
        return
    def change_styles(self, style_button):
        self.current_style_index=(self.current_style_index+1)%len(self.color_themes)        
        theme_name=list(self.color_themes.keys())[self.current_style_index]
        
        self.current_style=self.color_themes[theme_name]
        style_button["text"]="Palette: "+theme_name
    def plot_graph(self):
        now = UTCDateTime()
        self.start_time = now - self.backtrace
        self.stop_time = now
        with self.lock:
            self.stream.CollectAndAnalyze()
            stream=self.stream.copy()
        try:
            logging.info(str(stream.split()))
            if not stream:
                raise Exception("Empty stream for plotting")
             
        ### Handle colors and glitches     
            self.large_EQ_cooldown=max([0,self.large_EQ_cooldown-self.args.update_time]) #Decrease large EQ timer (assumes we are updating on time)              
            for trace in stream:
            
                max_val=np.max([abs(stream.customMetadata[trace.id]['MAX']),abs(stream.customMetadata[trace.id]['MIN'])])
                max_val_over_trace=stream.customMetadata[trace.id]['Glitch_ABSMAX']
                trace_name=trace.stats.station

                if trace.id not in self.tracePlotSpecs:
                    self.tracePlotSpecs[trace.id]=dict()
                    
                for (threshold, state) in self.threshold_color_state:
                    if max_val < threshold:
                        continue
                    self.tracePlotSpecs[trace.id]["STATE"]=state
                    break
                
                if max_val_over_trace > self.glitch_threshold and self.large_EQ_cooldown==0:  ## potential glitch and no large EQ
                    if trace_name not in self.POTENTIAL_GLITCHES:
                        self.POTENTIAL_GLITCHES.append(trace_name)
                else:
                    if trace_name in self.POTENTIAL_GLITCHES:
                        if max_val_over_trace < self.unglitch_threshold:  ## potential glitch no longer glitching
                            self.POTENTIAL_GLITCHES.remove(trace_name)
                                    
            if len(self.POTENTIAL_GLITCHES) > 1:  ## if multiple "glitches", they are probably not glitching (very large EQ??)
                self.POTENTIAL_GLITCHES.clear() ## since they aren't glitching, remove them from list
                self.large_EQ_cooldown=self.glitch_cooldown_time
                                      
            stream.trim(starttime=self.start_time, endtime=self.stop_time)
            np.set_printoptions(threshold=np.inf)
            
        ### Handle EPICS after Glitches                  
            if self.send_epics:
                self.post_EPICS(stream)
                
        ### PLOT      
            self.plot_lines(stream)

        except Exception as e:
            logging.error(e)
            pass
        dt=UTCDateTime()-now
        self.after(int(np.max([self.args.update_time-dt,0.01]) * 1000), self.plot_graph)
    
    def post_EPICS(self,stream):
        #TODO: Handle glitches independent of posting the EPICS
        
        #Find the max of all traces using the stream metadata
        max_station_name=""
        max_val = 0
        for trace in stream:
            if trace_get_name(trace) in self.POTENTIAL_GLITCHES:  ## won't consider glitches info for NETWORK EPICS
                continue
            best =np.max([abs(stream.customMetadata[trace.id]['MAX']),abs(stream.customMetadata[trace.id]['MIN'])])
            if max_val < best:
                max_station_name = "" + trace.stats.station
                max_val = best
        global last_process_gps
        
        prefix=self.epics_prefix
        
        #Picket Station Channels
        for trace in stream:
            starter = "STATION_0" + self.pickets[trace.stats.station]['index'] + "_"
            subprocess.Popen(["caput", prefix + starter + "MIN", f"{stream.customMetadata[trace.id]['MIN']}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  ## try different min method
            subprocess.Popen(["caput", prefix + starter + "MAX", f"{stream.customMetadata[trace.id]['MAX']}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  ## try different max method
            subprocess.Popen(["caput", prefix + starter + "MEAN", f"{stream.customMetadata[trace.id]['MEAN']}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  ## try different mean method
        #Global Picket Network Channels
        subprocess.Popen(["caput", prefix + "NETWORK_PEAK", f"{max_val}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.Popen(["caput", prefix + "NETWORK_STATION_NUM", f"{self.pickets[max_station_name]['index']}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.Popen(["caput", prefix + "NETWORK_STATION_NAME", f"{max_station_name}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        #Diagnostic Channels
        subprocess.Popen(["caput", prefix + "SERVER_GPS", f"{tconvert('now').gpsSeconds}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.Popen(["caput", prefix + "SERVER_START_GPS", start_time], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.Popen(["caput", prefix + "LAST_PROCESS_GPS", str(last_process_gps)], stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL)
        #AUX Channels
        
        ## update AUX1 channel to hold picket number that is glitching
        if len(self.POTENTIAL_GLITCHES) == 1:  ## if station is glitching, dont display EPICs variables
            trace_name = self.POTENTIAL_GLITCHES[0]
            i = self.pickets[trace_name]['index']
            subprocess.Popen(["caput", self.epics_prefix + "NETWORK_AUX1", f"{i}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen(["caput", self.epics_prefix + "NETWORK_AUX1", "-1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
        #subprocess.Popen(["caput", self.epics_prefix + "NETWORK_AUX2", "-1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        #subprocess.Popen(["caput", self.epics_prefix + "NETWORK_AUX3", "-1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        return
    
    def plot_lines(self, stream):
        
        stream.sort() #Ensures that the traces are in a set order before plotting (alphabetic order)
        self.figure.clear()
        fig = self.figure

        # avoid the differing trace.processing attributes prohibiting to plot
        # single traces of one id together.
        for trace in stream:
            trace.stats.processing = []     
            
        # Change equal_scale to False if auto-scaling should be turned off
        stream.plot(fig=fig, method="fast", draw=False, equal_scale=False,
                    size=(self.args.x_size, self.args.y_size), title="",
                    tick_format=self.args.tick_format,
                    number_of_ticks=self.args.time_tick_nb)
        fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
        bbox = dict(boxstyle="round", fc="w", alpha=0.8)
        path_effects = [withStroke(linewidth=4, foreground="w")]
        pad = 10

        
        
        #Reformat all of the stream plots
        for ax, trace in zip(fig.axes,stream):
            
            tracestate=self.tracePlotSpecs[trace.id]["STATE"]
            ax.set_title("")         
            #Format the text labels of all the traces
            try:
                text = ax.texts[0]
            # we should always have a single text, which is the stream
            # label of the axis, but catch index errors just in case
            except IndexError:
                pass
            else:
                if tracestate !="NORMAL" or trace_get_name(trace) in self.POTENTIAL_GLITCHES:
                    added_text=""
                    if trace_get_name(trace) in self.POTENTIAL_GLITCHES:
                        added_text=" |GLITCHING"
                    text.set_text(text.get_text()+" | "+ str(round_nm_to_microns(stream.customMetadata[trace.id]['Glitch_ABSMAX'],2))+u" \u03BCm/s"+added_text)
                text.set_fontsize(self.args.title_size)
                text.set_fontweight('bold')
                text.set_x(0.05)#TODO: add this positioning to the default arguments that could be changed
                
            xlabels = ax.get_xticklabels()
            ylabels = ax.get_yticklabels()
            plt.setp(ylabels, ha="left", path_effects=path_effects,fontsize=12)
            ax.yaxis.set_tick_params(pad=-pad)
            ylims_=np.array(ax.get_ylim())
            ylims_[0] = np.clip(ylims_[0], None, -self.args.min_scale)  ## changes made to fix min scaling
            ylims_[1] = np.clip(ylims_[1], self.args.min_scale, None)   ## changes made to fix max scaling
            ax.set_ylim(*ylims_)
            
            #Add boxes around the sides to separate the traces better
            width_we_like=2
            ax.spines["bottom"].set_linewidth(width_we_like)
            ax.spines["top"].set_linewidth(width_we_like)
            ax.spines["right"].set_linewidth(2*width_we_like)
            ax.spines["left"].set_linewidth(2*width_we_like)
            
            # treatment for bottom axes:
            if ax is fig.axes[-1]:
                plt.setp(
                    xlabels, va="bottom", size=self.args.time_legend_size, bbox=bbox)
                if OBSPY_VERSION < [0, 10]:
                    plt.setp(xlabels[:1], ha="left")
                    plt.setp(xlabels[-1:], ha="right")
                ax.xaxis.set_tick_params(pad=-pad)
            # all other axes
            else:
                plt.setp(xlabels, visible=False)
            locator = MaxNLocator(nbins=4, prune="both")
            ax.yaxis.set_major_locator(locator)
            
            ax.grid(True, axis="both",color='#666666',linewidth=0.5)
            
            ax.set_facecolor(self.current_style[tracestate]['facecolor'])
            try:
                line = ax.get_lines()[0]
            # we should always have a single trace, but catch index errors just in case
            except IndexError:
                pass
            else:
                line.set_color(self.current_style[tracestate]['linecolor'])

            if trace_get_name(trace) in self.POTENTIAL_GLITCHES:  ## display glitch in a different color
                ax.set_facecolor("#00FFFF")

        if OBSPY_VERSION >= [0, 10]:
            fig.axes[0].set_xlim(right=date2num(self.stop_time.datetime))
            fig.axes[0].set_xlim(left=date2num(self.start_time.datetime))
            
        fig.text(0.99, 0.99, self.stop_time.strftime("%Y-%m-%d %H:%M:%S UTC"),
                 ha="right", va="top", bbox=bbox, fontsize="medium")
        
        fig.canvas.draw()
                            
def trace_get_name(trace):
    return trace.stats.station

def name_get_trace(stream, name):
    for trace in stream:
        if trace_get_name(trace) == name:
            return trace
    return "No trace with that name"

def round_nm_to_microns(V_in_nm_per_sec,digits):
        return(round(V_in_nm_per_sec/1000,-(int(np.floor(np.log10(abs(V_in_nm_per_sec/1000))))-(digits-1))))

def ID_Creator(s):
    return int(''.join(str(format(ord(c), "x")) for c in s), 16)


def Reverse_ID(n):
    s = str(hex(n))
    itr = len(s)
    result = ""
    for i in range(2, itr, 2):
        result += chr(int(s[i:i+2], 16))
    return result

start_time = "not started"

def initEpics(picket_dict, prefix):
    global last_process_gps

    subprocess.Popen(["caput", prefix + "NETWORK_PEAK", "-1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.Popen(["caput", prefix + "NETWORK_STATION_NUM", "-1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.Popen(["caput", prefix + "NETWORK_STATION_NAME", ""], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.Popen(["caput", prefix + "NETWORK_AUX1", "-1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.Popen(["caput", prefix + "NETWORK_AUX2", "-1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.Popen(["caput", prefix + "NETWORK_AUX3", "-1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    for statName, statInfo in picket_dict.items():
                starter = "STATION_0" + statInfo['index'] + "_"
                subprocess.Popen(["caput", prefix + starter + "LAT", str(statInfo['Latitude'])], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.Popen(["caput", prefix + starter + "LON", str(statInfo['Longitude'])], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.Popen(["caput", prefix + starter + "MIN", "-1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.Popen(["caput", prefix + starter + "MAX", "-1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.Popen(["caput", prefix + starter + "MEAN", "-1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.Popen(["caput", prefix + starter + "ID", f"{ID_Creator(statName)}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.Popen(["caput", prefix + starter + "NAME", f"{statName}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)           
    subprocess.Popen(["caput", prefix + "SERVER_GPS", f"{tconvert('now').gpsSeconds}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.Popen(["caput", prefix + "SERVER_START_GPS", start_time], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.Popen(["caput", prefix + "LAST_PROCESS_GPS", str(last_process_gps)], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)

def load_pickets(picket_list):
    pickets=dict()
    ii=1
    with open(pathname+'possible_stations.json','r') as f:
        data=json.load(f)
    for station in picket_list:
        if station in data.keys():
           pickets[station]=data[station]
           pickets[station]['index']=str(ii)
           ii+=1
           continue
        print(station+" is not on the list of curated picket stations")
    return pickets

class PicketFence():
    def __init__(self, picket_list, myargs, epics_prefix,observatory_info=None):
        self.args=myargs
        self.pickets=load_pickets(picket_list)
        self.stop_flag = False
        self.leave = [False]
        self.send_epics = self.args.send_epics
        self.epics_prefix = epics_prefix
        if self.send_epics:
            assert type(epics_prefix) == str , "the epics prefix should be a string"
        self.args.epics_prefix=epics_prefix
        self.observatory_info=observatory_info
        
    def run(self):
        global start_time
        start_time = f"{tconvert('now').gpsSeconds}"
        while self.leave[0]==False:
            self.startnow = UTCDateTime()
            self.stream = Stream()
            self.events = Catalog()
            self.lock = threading.Lock()
    
            if self.args.send_epics:  ## will initialize the EPICs variables
                initEpics(self.pickets,self.epics_prefix)
            
            #create the strings to request stations from the server. They will be stored by server name
            server_dict=dict()
            for statName in self.pickets.keys():
                server_name=self.pickets[statName]['PreferredServer'];
                if server_name not in server_dict.keys(): #server not listed
                    server_dict[server_name]=self.pickets[statName]['Channel']
                else: #server has been listed
                    server_dict[server_name]=server_dict[server_name]+', ' + self.pickets[statName]['Channel']              
            self.server_dict=server_dict
        
            #Create a list of seedlink clients that will be watched
            self.seedlink_clients=[]
        
            ii=0
            for server_name in server_dict.keys():
                self.seedlink_clients.append(SeedlinkUpdater(self.stream, myargs=self.args, lock=self.lock))
                self.seedlink_clients[ii].slconn.set_sl_address(server_name)
                self.seedlink_clients[ii].multiselect = server_dict[server_name]
                self.seedlink_clients[ii].begin_time = (self.startnow - 1500).format_seedlink() #TODO make it not 2000 seconds flat
                self.seedlink_clients[ii].initialize()
                print('Downloading from server:  ', server_name)
                print(server_dict[server_name])
                ii+=1
            
            #Create the filtered stream and the plotter
            self.filtStream=filteredStream(self.stream, myargs=self.args)  
            self.master = SeedlinkPlotter(stream=self.filtStream, picket_dict=self.pickets, events=self.events, myargs=self.args, lock=self.lock, leave=self.leave) #, send_epics=args.epics)     
            

            self.style_button=ttk.Button(self.master, text="Change Palette",command=lambda: threading.Thread(target=self.master.change_styles(self.style_button)).start())
            self.style_button.pack(side=tkinter.RIGHT)
            
            if cartopyflag==1:
                self.picketMap=picketMap(picket_dict=self.pickets,central_station=self.observatory_info)  
                self.map_button=ttk.Button(self.master, text="Map",command=lambda: threading.Thread(target=self.picketMap.generate_plot()).start())
                self.map_button.pack()
            
            #Monitor the connections to seedlink
            self.watchers=[threading.Thread(target=self.watcher, args=(client.run,), daemon=True) for client in self.seedlink_clients] ## threads to monitor the connection with IRIS
        
            for watching_thread in self.watchers:
                watching_thread.start()
            sleep(3)

            self.master.mainloop()  ## main thread is now creating the display
            self.leave=self.master.leave;
            self.master.destroy()  ## mainloop was exited, now destroying master
            if self.leave[0]:
                return
            for watching_thread in self.watchers:
                watching_thread.join() ## ensures all threads are cleaned before restarting
        
    
    def watcher(self,function):
        thread = threading.Thread(target=function, daemon=True)
        thread.start()
        while True:
            sleep(20)  ## possible that this pings too often. Maybe exponential with some MAX?? (ASK EDGARD)
            if not thread.is_alive():  ## connection lost
                ## these are probably unnecessary
                print("A picket fence thread is dead. Attempting a restart")
                thread = threading.Thread(target=function, daemon=True)
                thread.start()
                # self.stop_flag = True  ## killing thread (I am basically resetting the entire main function with this)
                # for client in self.seedlink_clients:
                #     client.stop_flag=True
                # thread.join()
                # self.master.quit()  ## letting main thread break out of mainloop
                # ## break  ## allowing watching_conn to leave scope (terminating)
