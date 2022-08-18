# Picket-Fence
This program will display live data from USGS sites that feed data to IRIS.

This program has many optional parameters and flags that can be changed:

Stations can be changed by -s or --seedlink_streams \[SEEDLINK_STREAMS\]

Server can be changed by --seedlink_server \[SEEDLINK_SERVER\]

The amount of time the plot displays can be changed with -b or --backtrace_time \[BACKTRACE_TIME\]

The threshold velocity to make a plot turn red can be changed with --threshold \[THRESHOLD\]

The full list of parameters is in the main function of L?O_picket_fence.py. Anything in a `parser.add_argument` can be changed with a flag and for formatting help, look at the `default` or at the `type`.

An example is `python3 LLO_picket_fence.py -s "US_KVTX:10BHZ, IU_HKT:00BHZ, IU_TEIG:00BHZ, US_MIAR:00BHZ, US_LRAL:00BHZ, IU_DWPF:00BHZ" -b 30m --seedlink_server "rtserve.iris.washington.edu:18000" --update_time 2s --threshold 200 --lookback 360`.
