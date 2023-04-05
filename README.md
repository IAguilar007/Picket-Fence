# Picket-Fence
DESCRIPTION:

This program will display live data from USGS sites that feed data to IRIS.
___________


INSTALLATION:

First, start off with downloading conda which will make the rest of the installation much easier. It can be downloaded here https://conda.io/projects/conda/en/latest/user-guide/install/index.html and should only take a few minutes. Once conda is installed, we must download obspy, matplotlib, numpy, scipy, and pcas can be downloaded with the commands `conda install -c conda-forge obspy`, `conda install -c conda-forge matplotlib`, `conda install -c conda-forge numpy`, `conda install -c conda-forge scipy`, and `conda install -c conda-forge pcaspy`. The pcas module is for the EPICs server which both LHO and LLO now have.

Now that all dependencies are downloaded, to download the Picket-Fence files, open a terminal, enter the directory you would like the files to be located at, and finally use `git clone https://github.com/IAguilar007/Picket-Fence`. Whenever an update drops, we can use `git pull https://github.com/IAguilar007/Picket-Fence` should work.
___________

RUNNING THE PROGRAM:

To run, just open a terminal, go to the directory where you stored the file, and enter the command `python3 LLO_picket_fence.py` or `python3 LHO-picket-fence.py --epics` depending on the file you downloaded. It is recommended to run `python3 LLO-Server.py` before running the LLO/LHO Picket Fence due to the addition of EPICs variables to the code. This will simply initialize the EPICs variables with the desired starting values (such as -1). 

You may run the Picket Fence with the default parameters already chosen by me (the optional parameters I have set are good fits). When an earthquake crosses our preset threshold, the background for the plot of the station measuring the earthquake will turn a certain color. If the background is gray, then the seismic activity from the picket station is deemed to be normal. If the background is yellow, the seismic activity from the picket station is deemed to be slightly abnormal. If the background is orange, the seismic activity from the picket station is deemed to be fairly abnormal. If the background is red, the seismic activity from the picket station is deemed to be extremely abnormal and is most likely a large earthquake. If the background is teal, then that picket station is suspected of being glitched and its data should be taken with a grain of salt until the picket station is no longer teal (it will not affect NETWORK EPICs variables). Channel AUX1 of the EPICs variables channels is being used to record the picket number which is glitching. Default value is -1. If a station is not being plotted, this is because it is currently down/not feeding us data.

For any questions, you may email me at isaac007@stanford.edu and please make the subject involve Picket-Fence.

___________

OPTIONAL PARAMETERS (optional reading):

This program has many optional parameters and flags that can be changed:

At LHO, the --epics flag must be included for Picket Fence to set EPICS channels.  Only one instance of Picket Fence should be run with the --epics flag.

Stations can be changed by -s or --seedlink_streams \[SEEDLINK_STREAMS\]

Server can be changed by --seedlink_server \[SEEDLINK_SERVER\]

The amount of time the plot displays can be changed with -b or --backtrace_time \[BACKTRACE_TIME\]

The threshold velocity to make a plot turn red can be changed with --threshold \[THRESHOLD\]

The full list of parameters is in the main function of L?O_picket_fence.py. Anything in a `parser.add_argument` can be changed with a flag and for formatting help, look at the `default` or at the `type`.

EXAMPLE OF RUNNING CODE WITH CHANGED PARAMETERS:

`python3 LLO_picket_fence.py -s "US_KVTX:10BHZ, IU_HKT:00BHZ, IU_TEIG:00BHZ, US_MIAR:00BHZ, US_LRAL:00BHZ, IU_DWPF:00BHZ" -b 30m --seedlink_server "rtserve.iris.washington.edu:18000" --update_time 2s --threshold 200 --lookback 360`.

_________

OPTIONAL AESTHETIC CHANGES (optional reading):

If you would like the minimum y-axis to be the threshold (default 500 nm/s), then you need to open the waveform.py file from obspy and make some slight modifications (this is purely for aesthetic reasons, the code will run as it should without this being done). I would recommend doing so solely because it allows you to view the signals relative to the threshold as oppose to relative to the largest signal being shown. The modifications will not corrupt obspy in any other files where it is a dependency.

If you would like the aesthetics mentioned above, do the following in the obspy waveform.py file:

Find where it says `self.__plot_set_y_ticks()` and change it to `self.__plot_set_y_ticks(**kwargs)`. This allows us to pass our variable to the function. Once that is done, go to the function `__plot_set_y_ticks(self, *args, **kwargs)` and near the end of the first if statement. Directly under `ylims[:, 1] += yrange_paddings[:] / 2`, we can add the following lines of code:

```
if "min_bound" in kwargs:
                value = kwargs["min_bound"]
                ylims[:, 0] = np.clip(ylims[:, 0], None, -2 * value)  ## changes made to fix min scaling
                ylims[:, 1] = np.clip(ylims[:, 1], 2 * value, None)   ## changes made to fix max scaling
```

and now running the program should have the minimum y-axis of negative threshold to threshold.
