#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Jul 12 16:53:05 2022

@author: controls
"""
from __future__ import print_function

import warnings
warnings.filterwarnings("ignore", "Badly*")  # suppresses warning calls from lsim filter function

import matplotlib

# Set the backend for matplotlib.
matplotlib.use("TkAgg")
matplotlib.rc('figure.subplot', hspace=0)
matplotlib.rc('font', family="monospace")
try:
    # Py3
    import tkinter
except ImportError:
    # Py2
    import Tkinter as tkinter
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator
from matplotlib.patheffects import withStroke
from matplotlib.dates import date2num
import matplotlib.pyplot as plt
from obspy import Stream, Trace
from obspy import __version__ as OBSPY_VERSION
from obspy.core import UTCDateTime
from obspy.core.event import Catalog
from obspy.core.util import MATPLOTLIB_VERSION
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter

import threading
from time import sleep
import warnings

import sys
from scipy import signal

try:
    # Py3
    from urllib.request import URLError
except ImportError:
    # Py2
    from urllib2 import URLError
import logging
import numpy as np

# ugly but simple Python 2/3 compat
if sys.version_info.major < 3:
    range_func = xrange
    input_func = raw_input
else:
    range_func = range
    input_func = input

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
if OBSPY_VERSION < [0, 11]: # ligo-5 has OBSPY_VERSION equal to [1, 2] (Isaac)
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


class SeedlinkPlotter(tkinter.Tk):
    """
    This module plots realtime seismic data from a Seedlink server
    """

    def __init__(self, stream=None, events=None, myargs=None, lock=None, 
                 trace_ids=None, *args, **kwargs):
        tkinter.Tk.__init__(self, *args, **kwargs)
        self.wm_title("seedlink-plotter {}".format(myargs.seedlink_server))
        self.focus_set()
        self._bind_keys()
        args = myargs
        self.lock = lock
        ### size and position
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
        self.stream = stream
        self.events = events
        self.ids = trace_ids
        self.threshold = args.threshold
        self.lookback = args.lookback
        # Regular colors: Black, Red, Blue, Green
        self.color = ('#000000', '#e50000', '#0000e5', '#448630')

        self.plot_graph()

    def _quit(self, event):
        event.widget.quit()

    def _bind_keys(self):
        self.bind('<Escape>', self._quit)
        self.bind('q', self._quit)
        self.bind('f', self._toggle_fullscreen)

    def _toggle_fullscreen(self, event):
        g = self.geometry()
        self.geometry(self._geometry)
        self._geometry = g

    def plot_graph(self):
        now = UTCDateTime()
        self.start_time = now - self.backtrace
        self.stop_time = now

        with self.lock:
            # leave some data left of our start for possible processing
            self.stream.trim(
                starttime=self.start_time - self.args.backtrace_time, nearest_sample=False)
            stream = self.stream.copy()

        try:
            logging.info(str(stream.split()))
            if not stream:
                raise Exception("Empty stream for plotting")

            stream.merge(-1)

            for trace in stream:
                trace_len = len(trace.data)
                flat_len = int(trace_len / 3) # Make first third of data the mean value to removethe startup transient
                window_len = trace_len // 2
                window_len -= (window_len % 2) # Make sure window length is an even number
                if trace_len > window_len:
                    hw = np.hanning(window_len) # Hanning window size of window length
                    hw = np.split(hw, 2)
                    hw = hw[0]
                    hw_num = trace_len - window_len / 2 # Only first half of hanning window, don't want
                    # the right side of the data to be impacted (only care about the most receent n seconds of data)
                    hw_num = int(hw_num)
                    new = np.tile(1, hw_num) # Make everything after the hanning window one, don't want most recent n
                                            # seconds to be impacted
                    hwp = np.append(hw, new)
                    trace.data = trace.data * hwp # Apply window

            # about to filter the data using Brian's Lowpass filter
            den=[1.0000, 9.8339, 58.7394, 205.0490, 463.7573, 745.4739, 577.9041, 455.8890, 180.6478, 70.4068, 6.7771]
            num=[0, 0.4726, 0.8729, 20.9160, 16.5661, 138.8009, 43.0143, 170.2868, 19.9511, 52.9649, 0]
            Filter=(num,den)
            counter = 0
            for trace in stream:
                dt = trace.stats.delta
                totalDuration = len(trace.data) * dt
                T=np.arange(0.0, totalDuration, dt)
                trace.data -= np.mean(trace.data)
                tout, yout, xout=signal.lsim(Filter, trace.data,T)  ## use xout in future implementation
                trace.data = yout
    
            threshold = self.threshold # 500 nm/s normally, can be changed in the parameters
            index_list = []
            for trace in stream:
                trace_len = len(trace.data)
                looking = int(trace.stats.sampling_rate * self.lookback) # How far back to look for
                # earthquakes, any earthquakes above the threshold within this time will trigger the warning
                if looking > trace_len:
                    raise ValueError("Lookback too far, not enough data")
                flat_len = int(trace_len / 3) # Length of flattening (1st third by default)
                mean_val = np.mean(trace.data[trace_len // 2:]) # Get the mean value
                flat_start = np.zeros(trace_len) # Make the array
                for j in range(flat_len):
                    flat_start[j] = mean_val # Make array the mean value instead of 0 to keep the intereface from zooming in too far
                trace.data[0:flat_len] = flat_start[0:flat_len]
                counter = 0
                for j in range(-1, -int(looking), -1):
                    if trace.data[j] > threshold:
                        counter += 1
                        index_list.append(trace) #If threshold is surpassed within the lookback time,
                        #put the trace ID in a list to pass to the plot_lines function
            stream.trim(starttime=self.start_time, endtime=self.stop_time)
            np.set_printoptions(threshold=np.inf)
            self.plot_lines(stream, index_list)

        except Exception as e:
            logging.error(e)
            pass

        self.after(int(self.args.update_time * 1000), self.plot_graph)

    def plot_lines(self, stream, index_list):
        for id_ in self.ids:
            if not any([tr.id == id_ for tr in stream]):
                net, sta, loc, cha = id_.split(".")
                header = {'network': net, 'station': sta, 'location': loc,
                          'channel': cha, 'starttime': self.start_time}
                data = np.zeros(2)
                stream.append(Trace(data=data, header=header))
        stream.sort()
        self.figure.clear()
        fig = self.figure
        # avoid the differing trace.processing attributes prohibiting to plot
        # single traces of one id together.
        for trace in stream:
            trace.stats.processing = []

        for trace in stream:  ## don't plot traces with no data
            if len(trace.data) in [2, 4]:
                stream.remove(trace)
        
        # Change equal_scale to False if auto-scaling should be turned off
        stream.plot(fig=fig, method="fast", draw=False, equal_scale=True,
                    size=(self.args.x_size, self.args.y_size), title="",
                    color='Blue', tick_format=self.args.tick_format,
                    number_of_ticks=self.args.time_tick_nb, min_bound=self.threshold)
        fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
        bbox = dict(boxstyle="round", fc="w", alpha=0.8)
        path_effects = [withStroke(linewidth=4, foreground="w")]
        pad = 10
        for ax in fig.axes[::2]:
            if MATPLOTLIB_VERSION[0] >= 2:
                ax.set_facecolor("0.8")
            else:
                ax.set_axis_bgcolor("0.8")
        for id_, ax in zip(self.ids, fig.axes):
            ax.set_title("")
            if OBSPY_VERSION < [0, 10]:
                ax.text(0.1, 0.9, id_, va="top", ha="left",
                        transform=ax.transAxes, bbox=bbox,
                        size=self.args.title_size)
            else:
                try:
                    text = ax.texts[0]
                # we should always have a single text, which is the stream
                # label of the axis, but catch index errors just in case
                except IndexError:
                    pass
                else:
                    text.set_fontsize(self.args.title_size)
            xlabels = ax.get_xticklabels()
            ylabels = ax.get_yticklabels()
            plt.setp(ylabels, ha="left", path_effects=path_effects)
            ax.yaxis.set_tick_params(pad=-pad)
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
            ax.yaxis.grid(False)
            ax.grid(True, axis="x")
            if len(ax.lines) == 1:
                ydata = ax.lines[0].get_ydata()
                # if station has no data we add a dummy trace and we end up in
                # a line with either 2 or 4 zeros (2 if dummy line is cut off
                # at left edge of time axis)
                if len(ydata) in [4, 2] and not ydata.any():  ## this is useless now
                    if MATPLOTLIB_VERSION[0] >= 2:
                        ax.set_facecolor("k") #Traces with no data turn black
                    else:
                        ax.set_axis_bgcolor("#ff6666")
        if OBSPY_VERSION >= [0, 10]:
            fig.axes[0].set_xlim(right=date2num(self.stop_time.datetime))
            fig.axes[0].set_xlim(left=date2num(self.start_time.datetime))
        if len(fig.axes) > 5:
            bbox["alpha"] = 0.6
        fig.text(0.99, 0.97, self.stop_time.strftime("%Y-%m-%d %H:%M:%S UTC"),
                 ha="right", va="top", bbox=bbox, fontsize="medium")
        for red_trace in index_list:  ## traces are passed threshold
            for j in range(len(stream)): ## obtaining its position in the stream
                if red_trace == stream[j]:
                    fig.axes[j].set_facecolor('r') #Plots that surpass the threshold within the lookback time
                                                        #turn red
        fig.canvas.draw()


class SeedlinkUpdater(SLClient):

    def __init__(self, stream, myargs=None, lock=None):
        # loglevel NOTSET delegates messages to parent logger
        super(SeedlinkUpdater, self).__init__(loglevel="NOTSET")
        self.stream = stream
        self.lock = lock
        self.args = myargs

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
            self.stream.merge(-1)
            for trace in self.stream:
                trace.stats.processing = []
        return False

    def getTraceIDs(self):
        """
        Return a list of SEED style Trace IDs that the SLClient is trying to
        fetch data for.
        """
        ids = []
        if OBSPY_VERSION < [1, 0]:
            streams = self.slconn.getStreams()
        else:
            streams = self.slconn.get_streams()
        for stream in streams:
            net = stream.net
            sta = stream.station
            if OBSPY_VERSION < [1, 0]:
                selectors = stream.getSelectors()
            else:
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


def _parse_time_with_suffix_to_seconds(timestring):
    """
    Parse a string to seconds as float.
    If string can be directly converted to a float it is interpreted as
    seconds. Otherwise the following suffixes can be appended, case
    insensitive: "s" for seconds, "m" for minutes, "h" for hours, "d" for days.
    >>> _parse_time_with_suffix_to_seconds("12.6")
    12.6
    >>> _parse_time_with_suffix_to_seconds("12.6s")
    12.6
    >>> _parse_time_with_suffix_to_minutes("12.6m")
    756.0
    >>> _parse_time_with_suffix_to_seconds("12.6h")
    45360.0
    :type timestring: str
    :param timestring: "s" for seconds, "m" for minutes, "h" for hours, "d" for
        days.
    :rtype: float
    """
    try:
        return float(timestring)
    except:
        timestring, suffix = timestring[:-1], timestring[-1].lower()
        mult = {'s': 1.0, 'm': 60.0, 'h': 3600.0, 'd': 3600.0 * 24}[suffix]
        return float(timestring) * mult


def _parse_time_with_suffix_to_minutes(timestring):
    try:
        return float(timestring)
    except:
        seconds = _parse_time_with_suffix_to_seconds(timestring)
    return seconds / 60.0


def main():
    parser = ArgumentParser(prog='seedlink_plotter',
                            description='Plot a realtime seismogram of a station',
                            formatter_class=ArgumentDefaultsHelpFormatter)
    
    parser.add_argument(
        '-s', '--seedlink_streams', type=str, required=False,
        help='The seedlink stream selector string. It has the format '
             '"stream1[:selectors1],stream2[:selectors2],...", with "stream" '
             'in "NETWORK"_"STATION" format and "selector" a space separated '
             'list of "LOCATION""CHANNEL", e.g. '
             '"IU_KONO:BHE BHN,MN_AQU:HH?.D".', 
             default="IU_COR:00BHZ, US_HLID:00BHZ, US_MSO:00BHZ, US_NEW:00BHZ, CN_SHB:HHZ")

    # Real-time parameters
    parser.add_argument(
        '--seedlink_server', type=str,
                        help='the seedlink server to connect to with port. "\
                        "ex: rtserver.ipgp.fr:18000 ', required=False, default="rtserve.iris.washington.edu:18000")

    parser.add_argument(
        '-b', '--backtrace_time',
                        help='the number of seconds to plot (3600=1h,86400=24h). The '
                             'following suffixes can be used as well: "m" for minutes, '
                             '"h" for hours and "d" for days.', required=False,
                        type=_parse_time_with_suffix_to_seconds, default="15m")
    parser.add_argument(
        '--x_position', type=int,
                        help='the x position of the graph', required=False, default=0)
    parser.add_argument(
        '--y_position', type=int,
                        help='the y position of the graph', required=False, default=0)
    parser.add_argument(
        '--x_size', type=int, help='the x size of the graph', required=False, default=800)
    parser.add_argument(
        '--y_size', type=int, help='the y size of the graph', required=False, default=600)
    parser.add_argument(
        '--title_size', type=int, help='the title size of each station in multichannel', required=False, default=10)
    parser.add_argument(
        '--time_legend_size', type=int, help='the size of time legend in multichannel', required=False, default=10)
    parser.add_argument(
        '--tick_format', type=str, help='the tick format of time legend ', required=False, default='%H:%M:%S')
    parser.add_argument(
        '--time_tick_nb', type=int, help='the number of time tick', required=False, default=5)

    parser.add_argument(
        '--threshold', type=int, help='maximum ground speed', required=False, default=500)
    parser.add_argument(
        '--lookback', type=int, help='how far back IN SECONDS (integer) the plotter checks for earthquakes', required=False, default=360)

    parser.add_argument(
        '--line_plot', help='regular real time plot for single station', required=False, action='store_true')
    parser.add_argument(
        '--update_time',
        help='time in seconds between each graphic update.'
             ' The following suffixes can be used as well: "s" for seconds, '
             '"m" for minutes, "h" for hours and "d" for days.',
        required=False, default=2,
        type=_parse_time_with_suffix_to_seconds)
    parser.add_argument('-f', '--fullscreen', default=True,
                        action="store_true",
                        help='set to full screen on startup')
    parser.add_argument('-v', '--verbose', default=False,
                        action="store_true", dest="verbose",
                        help='show verbose debugging output')
    # parse the arguments
    args = parser.parse_args()

    if args.verbose:
        loglevel = logging.DEBUG
    else:
        loglevel = logging.CRITICAL
    logging.basicConfig(level=loglevel)

    now = UTCDateTime()
    stream = Stream()
    events = Catalog()
    lock = threading.Lock()

    # cl is the seedlink client
    seedlink_client = SeedlinkUpdater(stream, myargs=args, lock=lock)
    if OBSPY_VERSION < [1, 0]:
        seedlink_client.slconn.setSLAddress(args.seedlink_server)
    else:
        seedlink_client.slconn.set_sl_address(args.seedlink_server)
    seedlink_client.multiselect = args.seedlink_streams

    # tes if drum plot or line plot
    if any([x in args.seedlink_streams for x in ", ?*"]) or args.line_plot:
        round_start = UTCDateTime(now.year, now.month, now.day, now.hour, 0, 0)
        round_start = round_start + 3600 - args.backtrace_time
        seedlink_client.begin_time = (round_start).format_seedlink()


    seedlink_client.begin_time = (now - args.backtrace_time).format_seedlink()    
    seedlink_client.initialize()
    ids = seedlink_client.getTraceIDs()
    # start cl in a thread
    thread = threading.Thread(target=seedlink_client.run)
    thread.setDaemon(True)
    thread.start()

    # Wait few seconds to get data for the first plot
    sleep(2)

    master = SeedlinkPlotter(stream=stream, events=events, myargs=args,
                             lock=lock, trace_ids=ids)
    master.mainloop()


if __name__ == '__main__':
    main()
